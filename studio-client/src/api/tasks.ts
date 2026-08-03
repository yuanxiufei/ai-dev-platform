/**
 * 任务 API 模块 — 任务配置（CRUD + 执行 + 队列）
 * 对应后端: /system/tasks, /tasks/queue
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface TaskDefinition {
  name: string
  type: string // shell | npm | python | docker | custom
  command: string
  args: string[]
  cwd: string
  env: Record<string, string>
  problem_matcher: string | null
  depends_on: string[]
  presentation: Record<string, unknown>
  label: string
  detail: string
  is_build: boolean
  is_test: boolean
  is_watch: boolean
}

export interface TaskExecution {
  execution_id: string
  task_name: string
  status: string // pending|running|completed|failed|cancelled
  started_at: number
  finished_at: number
  exit_code: number | null
  output_length: number
}

export interface TaskOutput {
  execution_id: string
  status: string
  exit_code: number | null
  stdout: string
  stderr: string
}

export interface QueueStats {
  queue_stats: Record<string, unknown>
  workers: Record<string, unknown>[]
}

export interface QueueTask {
  task_id: string
  name: string
  status: string
  args: unknown[]
  kwargs: Record<string, unknown>
  worker: string | null
  created_at: string
  started_at: string | null
}

/* ── 任务配置端点 ─────────────────────────────── */

/** 列出所有任务配置 */
export function listTasks() {
  return apiClient.get<TaskDefinition[]>("/system/tasks")
}

/** 创建任务配置 */
export function createTask(data: TaskDefinition) {
  return apiClient.post<TaskDefinition>("/system/tasks", data)
}

/** 更新任务配置 */
export function updateTask(taskName: string, data: TaskDefinition) {
  return apiClient.put<TaskDefinition>(`/system/tasks/${taskName}`, data)
}

/** 删除任务配置 */
export function deleteTask(taskName: string) {
  return apiClient.delete<{ ok: boolean }>(`/system/tasks/${taskName}`)
}

/** 执行任务 */
export function runTask(taskName: string) {
  return apiClient.post<{ execution_id: string; status: string }>(`/system/tasks/${taskName}/run`)
}

/** 查询执行状态 */
export function getExecution(executionId: string) {
  return apiClient.get<TaskExecution>(`/system/tasks/executions/${executionId}`)
}

/** 取消执行 */
export function cancelExecution(executionId: string) {
  return apiClient.post<{ ok: boolean }>(`/system/tasks/executions/${executionId}/cancel`)
}

/** 获取执行输出 */
export function getExecutionOutput(executionId: string, tail?: number) {
  return apiClient.get<TaskOutput>(`/system/tasks/executions/${executionId}/output`, { params: { tail: tail ?? 5000 } })
}

/** 自动检测工作区任务 */
export function autoDetectTasks(workspaceRoot?: string) {
  return apiClient.post<TaskDefinition[]>("/system/tasks/auto-detect", null, { params: { workspace_root: workspaceRoot ?? "." } })
}

/* ── 任务队列端点 ─────────────────────────────── */

/** 任务队列统计 */
export function taskQueueStats() {
  return apiClient.get<QueueStats>("/tasks/queue/stats")
}

/** 活跃任务列表 */
export function taskQueueActive(limit?: number) {
  return apiClient.get<QueueTask[]>("/tasks/queue/active", { params: { limit: limit ?? 50 } })
}

/** 单个任务状态 */
export function taskQueueStatus(taskId: string) {
  return apiClient.get<QueueTask>(`/tasks/queue/${taskId}`)
}

/** 撤销队列任务 */
export function taskQueueRevoke(taskId: string, terminate?: boolean) {
  return apiClient.post<{ task_id: string; revoked: boolean; terminated: boolean }>(`/tasks/queue/${taskId}/revoke`, null, { params: { terminate: terminate ?? false } })
}
