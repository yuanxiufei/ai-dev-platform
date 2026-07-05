// ============================================
// Git Store — full SCM with staged/unstaged/commit/diff
// ============================================
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { isTauriEnv } from './shared'

export interface GitFileChange {
  path: string
  status: 'staged' | 'modified' | 'added' | 'deleted' | 'untracked' | 'renamed'
  oldPath?: string
}

export interface GitStatus {
  branch: string
  ahead: number
  behind: number
  changes: GitFileChange[]
}

export const useGitStore = defineStore('git', () => {
  const gitBranch = ref('')
  const gitAhead = ref(0)
  const gitBehind = ref(0)
  const gitChangedFiles = ref(0)
  const gitChanges = ref<GitFileChange[]>([])
  const isRefreshing = ref(false)
  const isCommitting = ref(false)
  const commitMessage = ref('')
  const remoteUrl = ref('')
  /** Whether Git integration is available (Tauri or backend API) */
  const gitAvailable = computed(() => isTauriEnv() || !!_wsRoot)

  const stagedCount = computed(() => gitChanges.value.filter(c => c.status === 'staged').length)
  const unstagedCount = computed(() => gitChanges.value.filter(c => c.status !== 'staged' && c.status !== 'untracked').length)
  const untrackedCount = computed(() => gitChanges.value.filter(c => c.status === 'untracked').length)

  const stagedFiles = computed(() => gitChanges.value.filter(c => c.status === 'staged'))
  const unstagedFiles = computed(() => gitChanges.value.filter(c => c.status !== 'staged'))

  /** Branches list (Tauri-only) */
  const branches = ref<Array<{ name: string; isCurrent: boolean; isRemote: boolean }>>([])
  /** Diff data for current file/repo */
  const diffData = ref<Array<{
    path: string
    oldPath?: string
    status: string
    additions: number
    deletions: number
    hunks: Array<{ header: string; lines: Array<{ type: string; content: string; lineNumber?: number }> }>
  }>>([])

  /**
   * Rust git_status 返回格式：
   *   { branch, ahead, behind, staged: [{path, status, staged}], unstaged: [{path, status, staged}], untracked: [string], clean }
   * 前端将其展开到统一的 GitFileChange[] 中。
   */
  async function refreshGitStatus(workspaceRoot: string): Promise<void> {
    isRefreshing.value = true
    _wsRoot = workspaceRoot
    try {
      if (isTauriEnv() && workspaceRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        const status: any = await invoke('git_status', { path: workspaceRoot })
        gitBranch.value = status.branch ?? ''
        gitAhead.value = status.ahead ?? 0
        gitBehind.value = status.behind ?? 0

        const changes: GitFileChange[] = []
        for (const f of (status.staged || [])) {
          const s = mapRustGitStatus(f.status, true)
          changes.push({ path: f.path, status: s })
        }
        for (const f of (status.unstaged || [])) {
          if (changes.some(c => c.path === f.path)) continue
          const s = mapRustGitStatus(f.status, false)
          changes.push({ path: f.path, status: s })
        }
        for (const f of (status.untracked || [])) {
          changes.push({ path: typeof f === 'string' ? f : f.path, status: 'untracked' })
        }
        gitChanges.value = changes
        gitChangedFiles.value = changes.length
      } else {
        // Web模式: 调用后端 REST API
        const { getStatus } = await import('@/api/git')
        const status = await getStatus(workspaceRoot)
        gitBranch.value = status.branch
        gitAhead.value = status.ahead
        gitBehind.value = status.behind
        gitChanges.value = status.changes.map(c => ({
          path: c.path,
          status: c.status as GitFileChange['status'],
          oldPath: c.old_path,
        }))
        gitChangedFiles.value = status.changes.length
      }
    } catch (e) {
      console.warn('[Git] Status refresh failed:', e)
    } finally {
      isRefreshing.value = false
    }
  }

  /** Map Rust git porcelain status codes to frontend status enum */
  function mapRustGitStatus(code: string, staged: boolean): GitFileChange['status'] {
    if (staged) return 'staged'
    switch (code) {
      case 'M': return 'modified'
      case 'A': return 'added'
      case 'D': return 'deleted'
      case 'R': return 'renamed'
      default: return 'modified'
    }
  }

  /** Commit log entries (from git_log) */
  const commitLog = ref<Array<{ hash: string; shortHash: string; message: string; author: string; email: string; date: string }>>([])

  /** Current workspace root (cached from refreshGitStatus) — used for stage/unstage/discard */
  let _wsRoot = ''

  async function stageFile(filePath: string): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_stage', { path: _wsRoot, file_path: filePath })
      } else if (_wsRoot) {
        const { stageFile: apiStageFile } = await import('@/api/git')
        await apiStageFile(_wsRoot, filePath)
      }
      const found = gitChanges.value.find(c => c.path === filePath)
      if (found) found.status = 'staged'
    } catch (e) {
      console.warn('[Git] Stage failed:', e)
    }
  }

  async function unstageFile(filePath: string): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_unstage', { path: _wsRoot, file_path: filePath })
      } else if (_wsRoot) {
        const { unstageFile: apiUnstageFile } = await import('@/api/git')
        await apiUnstageFile(_wsRoot, filePath)
      }
      const found = gitChanges.value.find(c => c.path === filePath)
      if (found) found.status = 'modified'
    } catch (e) {
      console.warn('[Git] Unstage failed:', e)
    }
  }

  async function stageAll(): Promise<void> {
    for (const c of gitChanges.value.filter(c => c.status !== 'staged')) {
      await stageFile(c.path)
    }
  }

  async function unstageAll(): Promise<void> {
    for (const c of stagedFiles.value) {
      await unstageFile(c.path)
    }
  }

  async function commit(message?: string): Promise<boolean> {
    const msg = message || commitMessage.value.trim()
    if (!msg) return false
    isCommitting.value = true
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_commit', { path: _wsRoot, message: msg })
      } else if (_wsRoot) {
        const { commit: apiCommit } = await import('@/api/git')
        await apiCommit(_wsRoot, msg)
      }
      commitMessage.value = ''
      return true
    } catch (e) {
      console.warn('[Git] Commit failed:', e)
      return false
    } finally {
      isCommitting.value = false
    }
  }

  async function push(): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_push', { path: _wsRoot })
      } else if (_wsRoot) {
        const { push: apiPush } = await import('@/api/git')
        await apiPush(_wsRoot)
      }
    } catch (e) {
      console.warn('[Git] Push failed:', e)
    }
  }

  async function pull(): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_pull', { path: _wsRoot })
      } else if (_wsRoot) {
        const { pull: apiPull } = await import('@/api/git')
        await apiPull(_wsRoot)
      }
    } catch (e) {
      console.warn('[Git] Pull failed:', e)
    }
  }

  async function discardChanges(filePath: string): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_discard', { path: _wsRoot, file_path: filePath })
      } else if (_wsRoot) {
        const { discardChanges: apiDiscard } = await import('@/api/git')
        await apiDiscard(_wsRoot, filePath)
      }
      gitChanges.value = gitChanges.value.filter(c => c.path !== filePath)
    } catch (e) {
      console.warn('[Git] Discard failed:', e)
    }
  }

  /** O1: Get diff for a file or entire repo */
  async function getDiff(file?: string, staged?: boolean): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        const diffs: any = await invoke('git_diff', { path: _wsRoot, file: file ?? null, staged: staged ?? false })
        diffData.value = diffs || []
      } else if (_wsRoot) {
        const { getDiff: apiGetDiff } = await import('@/api/git')
        const diffs = await apiGetDiff(_wsRoot, file, staged)
        diffData.value = diffs.map(d => ({
          path: d.path,
          oldPath: d.old_path,
          status: d.status,
          additions: d.additions,
          deletions: d.deletions,
          hunks: d.hunks.map(h => ({
            header: h.header,
            lines: h.lines.map(l => ({
              type: l.type as 'added' | 'removed' | 'context',
              content: l.content,
              lineNumber: l.line_number,
            })),
          })),
        }))
      }
    } catch (e) {
      console.warn('[Git] Diff failed:', e)
    }
  }

  /** O1: List all branches */
  async function listBranches(): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        const result: any = await invoke('git_branch', { path: _wsRoot })
        branches.value = result || []
      } else if (_wsRoot) {
        const { listBranches: apiListBranches } = await import('@/api/git')
        const result = await apiListBranches(_wsRoot)
        branches.value = result.map(b => ({
          name: b.name,
          isCurrent: b.is_current,
          isRemote: b.is_remote,
        }))
      }
    } catch (e) {
      console.warn('[Git] List branches failed:', e)
    }
  }

  /** O1: Checkout a branch (or create new one) */
  async function checkoutBranch(branch: string, createNew?: boolean): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_checkout', { path: _wsRoot, branch, create_new: createNew ?? false })
      } else if (_wsRoot) {
        const { checkoutBranch: apiCheckout } = await import('@/api/git')
        await apiCheckout(_wsRoot, branch, createNew)
      }
      // Refresh status after checkout
      await refreshGitStatus(_wsRoot)
    } catch (e) {
      console.warn('[Git] Checkout failed:', e)
    }
  }

  /** Get commit log (git log) */
  async function getLog(limit?: number): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        const result: any = await invoke('git_log', { path: _wsRoot, limit: limit ?? 20 })
        commitLog.value = result || []
      } else if (_wsRoot) {
        const { getLog: apiGetLog } = await import('@/api/git')
        const result = await apiGetLog(_wsRoot, limit ?? 20)
        commitLog.value = result.map(e => ({
          hash: e.hash,
          shortHash: e.short_hash,
          message: e.message,
          author: e.author,
          email: e.email,
          date: e.date,
        }))
      }
    } catch (e) {
      console.warn('[Git] Get log failed:', e)
    }
  }

  /** O1: Stash current changes (or pop stash) */
  async function stash(message?: string, pop?: boolean): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_stash', { path: _wsRoot, message: message ?? null, pop: pop ?? false })
      } else if (_wsRoot) {
        const { stash: apiStash } = await import('@/api/git')
        await apiStash(_wsRoot, message, pop)
      }
    } catch (e) {
      console.warn('[Git] Stash failed:', e)
    }
  }

  function reset() {
    gitBranch.value = ''
    gitAhead.value = 0
    gitBehind.value = 0
    gitChanges.value = []
    commitMessage.value = ''
    branches.value = []
    diffData.value = []
  }

  return {
    gitBranch, gitAhead, gitBehind, gitChangedFiles,
    gitChanges, isRefreshing, isCommitting, commitMessage, remoteUrl,
    gitAvailable, branches, diffData,
    stagedCount, unstagedCount, untrackedCount,
    stagedFiles, unstagedFiles,
    refreshGitStatus, stageFile, unstageFile, stageAll, unstageAll,
    commit, push, pull, discardChanges,
    getDiff, listBranches, checkoutBranch, stash, getLog,
    commitLog,
    reset,
  }
})
