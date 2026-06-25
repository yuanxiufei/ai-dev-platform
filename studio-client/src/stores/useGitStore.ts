// ============================================
// Git Store — branch status & change tracking
// ============================================
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { isTauriEnv } from './shared'

export const useGitStore = defineStore('git', () => {
  const gitBranch = ref('')
  const gitAhead = ref(0)
  const gitBehind = ref(0)
  const gitChangedFiles = ref(0)

  async function refreshGitStatus(workspaceRoot: string): Promise<void> {
    if (!isTauriEnv() || !workspaceRoot) return
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const status = await invoke<any>('git_status', { path: workspaceRoot })
      gitBranch.value = status.branch ?? ''
      gitAhead.value = status.ahead ?? 0
      gitBehind.value = status.behind ?? 0
      const staged = status.staged?.length ?? 0
      const unstaged = status.unstaged?.length ?? 0
      const untracked = status.untracked?.length ?? 0
      gitChangedFiles.value = staged + unstaged + untracked
    } catch {
      gitBranch.value = ''
    }
  }

  return { gitBranch, gitAhead, gitBehind, gitChangedFiles, refreshGitStatus }
})
