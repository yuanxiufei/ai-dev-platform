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

  async function refreshGitStatus(workspaceRoot: string): Promise<void> {
    isRefreshing.value = true
    try {
      if (isTauriEnv() && workspaceRoot) {
        const { invoke } = await import('@tauri-apps/api/core')
        const status: any = await invoke('git_status', { path: workspaceRoot })
        gitBranch.value = status.branch ?? ''
        gitAhead.value = status.ahead ?? 0
        gitBehind.value = status.behind ?? 0
        remoteUrl.value = status.remote ?? ''

        const changes: GitFileChange[] = []
        for (const f of (status.staged || [])) changes.push({ path: f, status: 'staged' })
        for (const f of (status.modified || [])) changes.push({ path: f, status: 'modified' })
        for (const f of (status.added || [])) changes.push({ path: f, status: 'added' })
        for (const f of (status.deleted || [])) changes.push({ path: f, status: 'deleted' })
        for (const f of (status.untracked || [])) changes.push({ path: f, status: 'untracked' })
        for (const f of (status.renamed || [])) {
          if (typeof f === 'object') {
            changes.push({ path: f.to, status: 'renamed', oldPath: f.from })
          } else {
            changes.push({ path: f, status: 'renamed' })
          }
        }
        gitChanges.value = changes
      }
    } catch (e) {
      console.warn('[Git] Status refresh failed:', e)
    } finally {
      isRefreshing.value = false
    }
  }

  async function stageFile(filePath: string): Promise<void> {
    try {
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_stage', { path: filePath })
      }
      // Update local state optimistically
      const found = gitChanges.value.find(c => c.path === filePath)
      if (found) found.status = 'staged'
    } catch (e) {
      console.warn('[Git] Stage failed:', e)
    }
  }

  async function unstageFile(filePath: string): Promise<void> {
    try {
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_unstage', { path: filePath })
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
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_commit', { message: msg })
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
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_push', {})
      }
    } catch (e) {
      console.warn('[Git] Push failed:', e)
    }
  }

  async function pull(): Promise<void> {
    try {
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_pull', {})
      }
    } catch (e) {
      console.warn('[Git] Pull failed:', e)
    }
  }

  async function discardChanges(filePath: string): Promise<void> {
    try {
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('git_discard', { path: filePath })
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
