import apiClient from "./client"

/* ========== Git Worktree API ========== */

export interface WorktreeItem {
  path: string
  branch: string
  head: string
  bare: boolean
  locked: boolean
  prunable: boolean
}

export interface WorktreeStats {
  is_git_repo: boolean
  worktrees: WorktreeItem[]
  total: number
  message?: string
}

export interface BranchItem {
  name: string
  current: boolean
  remote: boolean
}

// ── Worktree CRUD ──────────────────────────────────

export const listWorktrees = () =>
  apiClient.get<WorktreeStats>("/agent/worktree")

export const getBranches = (includeWorktreeBranches = false) =>
  apiClient.get<{ branches: BranchItem[] }>("/agent/worktree/branches", {
    params: { include_worktree_branches: includeWorktreeBranches },
  })

export const createWorktree = (payload: {
  branch: string
  base_branch?: string
  create_new_branch?: boolean
  path_override?: string
  description?: string
}) => apiClient.post<{ success: boolean; message: string; worktree: any }>("/agent/worktree/create", payload)

export const deleteWorktree = (path: string, force = false) =>
  apiClient.post<{ success: boolean; message: string }>(
    `/agent/worktree/${encodeURIComponent(path)}/delete`,
    null,
    { params: { force } }
  )

export const cleanupWorktrees = () =>
  apiClient.post<{ success: boolean; message: string }>("/agent/worktree/cleanup")

// ── Worktree 操作 ──────────────────────────────────

export const checkoutBranch = (branch: string, worktree_path?: string) =>
  apiClient.post<{ success: boolean; message: string }>("/agent/worktree/checkout", {
    branch,
    worktree_path: worktree_path || "",
  })

export const mergeBranch = (source_branch: string, worktree_path?: string, message?: string) =>
  apiClient.post<{ success: boolean; message: string; conflict: boolean }>(
    "/agent/worktree/merge",
    { source_branch, worktree_path: worktree_path || "", message: message || "" }
  )

export const getWorktreeDiff = (path: string) =>
  apiClient.get<{ path: string; diff: string }>(`/agent/worktree/${encodeURIComponent(path)}/diff`)

// ── 任务管理 ───────────────────────────────────────

export interface WorktreeTask {
  task_id: string
  worktree_path: string
  branch: string
  description: string
  status: string
  created_at: string
  completed_at?: string
  error?: string
}

export const listTasks = (params?: { worktree_path?: string; status?: string }) =>
  apiClient.get<{ tasks: WorktreeTask[]; total: number }>("/agent/worktree/tasks", { params })

export const registerTask = (payload: {
  worktree_path: string
  branch?: string
  description?: string
  task_id?: string
}) => apiClient.post<{ task: WorktreeTask }>("/agent/worktree/tasks", payload)

export const completeTask = (task_id: string, payload: {
  success: boolean
  error?: string
  result?: Record<string, unknown>
}) => apiClient.post<{ task: WorktreeTask }>(`/agent/worktree/tasks/${encodeURIComponent(task_id)}/complete`, payload)
