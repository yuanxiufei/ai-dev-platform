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

  const stagedCount = computed(() => gitChanges.value.filter(c => c.status === 'staged').length)
  const unstagedCount = computed(() => gitChanges.value.filter(c => c.status !== 'staged' && c.status !== 'untracked').length)
  const untrackedCount = computed(() => gitChanges.value.filter(c => c.status === 'untracked').length)

  const stagedFiles = computed(() => gitChanges.value.filter(c => c.status === 'staged'))
  const unstagedFiles = computed(() => gitChanges.value.filter(c => c.status !== 'staged'))

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
        // Rust response: staged/unstaged are arrays of { path, status, staged }
        for (const f of (status.staged || [])) {
          const s = mapRustGitStatus(f.status, true)
          changes.push({ path: f.path, status: s })
        }
        for (const f of (status.unstaged || [])) {
          // dedup: already in staged
          if (changes.some(c => c.path === f.path)) continue
          const s = mapRustGitStatus(f.status, false)
          changes.push({ path: f.path, status: s })
        }
        for (const f of (status.untracked || [])) {
          changes.push({ path: typeof f === 'string' ? f : f.path, status: 'untracked' })
        }
        gitChanges.value = changes
        gitChangedFiles.value = changes.length
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

  /** Current workspace root (cached from refreshGitStatus) — used for stage/unstage/discard */
  let _wsRoot = ''

  async function stageFile(filePath: string): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        // Tauri git_stage(path=repo_root, file_path=relative_or_absolute)
        await invoke('git_stage', { path: _wsRoot, filePath })
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
        await invoke('git_unstage', { path: _wsRoot, filePath })
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
      }
    } catch (e) {
      console.warn('[Git] Pull failed:', e)
    }
  }

  async function discardChanges(filePath: string): Promise<void> {
    try {
      if (isTauriEnv() && _wsRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_discard', { path: _wsRoot, filePath })
      }
      gitChanges.value = gitChanges.value.filter(c => c.path !== filePath)
    } catch (e) {
      console.warn('[Git] Discard failed:', e)
    }
  }

  function reset() {
    gitBranch.value = ''
    gitAhead.value = 0
    gitBehind.value = 0
    gitChanges.value = []
    commitMessage.value = ''
  }

  return {
    gitBranch, gitAhead, gitBehind, gitChangedFiles,
    gitChanges, isRefreshing, isCommitting, commitMessage, remoteUrl,
    stagedCount, unstagedCount, untrackedCount,
    stagedFiles, unstagedFiles,
    refreshGitStatus, stageFile, unstageFile, stageAll, unstageAll,
    commit, push, pull, discardChanges, reset,
  }
})
