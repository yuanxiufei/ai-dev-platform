/**
 * Session Tree API — 会话树/分支/检查点管理
 * 对应后端: /system/session-tree
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface TreeNode {
  node_id: string
  parent_id: string | null
  session_id: string
  agent_id: string
  branch_name: string
  branch_reason: string
  total_turns: number
  total_tokens: number
  created_at: string
  updated_at: string
  agent_config?: Record<string, unknown>
}

export interface TreeOverview {
  summary: {
    total_nodes: number
    total_branches: number
    total_sessions: number
  }
  roots: TreeNode[]
}

export interface NodeDetail {
  node: TreeNode
  children: TreeNode[]
  branch_chain: TreeNode[]
  checkpoints: Checkpoint[]
}

export interface Checkpoint {
  checkpoint_id: string
  session_id: string
  agent_id: string
  label: string
  description: string
  turn: number
  total_tokens: number
  created_at: string
  messages_count?: number
}

export interface ForkRequest {
  node_id: string
  branch_name?: string
  branch_reason?: string
  save_checkpoint?: boolean
}

export interface SaveCheckpointRequest {
  session_id: string
  agent_id?: string
  label?: string
  description?: string
  turn?: number
}

export interface RestoreRequest {
  checkpoint_id: string
  agent_config?: Record<string, unknown>
  user_message?: string
}

/* ── 端点 ────────────────────────────────────── */

/** 获取 Session 树总览 */
export function getTreeOverview() {
  return apiClient.get<TreeOverview>("/system/session-tree")
}

/** 获取节点详情（含子树） */
export function getNodeDetail(nodeId: string, includeMessages = false) {
  return apiClient.get<NodeDetail>(`/system/session-tree/${nodeId}`, {
    params: includeMessages ? { include_messages: true } : {},
  })
}

/** 获取节点的完整子树 */
export function getSubtree(nodeId: string) {
  return apiClient.get<{ root_id: string; node_count: number; nodes: TreeNode[] }>(
    `/system/session-tree/${nodeId}/subtree`,
  )
}

/** Fork 新分支 */
export function forkBranch(data: ForkRequest) {
  return apiClient.post<{ branch: TreeNode }>("/system/session-tree/fork", data)
}

/** 列出所有分支 */
export function listAllBranches(rootId?: string) {
  return apiClient.get<{ branches: unknown[]; total: number }>("/system/session-tree/branches/all", {
    params: rootId ? { root_id: rootId } : {},
  })
}

/** 保存检查点 */
export function saveCheckpoint(data: SaveCheckpointRequest) {
  return apiClient.post<{ checkpoint: Checkpoint }>("/system/session-tree/checkpoints", data)
}

/** 列出所有检查点 */
export function listCheckpoints() {
  return apiClient.get<{ checkpoints: Checkpoint[]; total: number }>(
    "/system/session-tree/checkpoints",
  )
}

/** 获取检查点详情 */
export function getCheckpoint(checkpointId: string) {
  return apiClient.get<{ checkpoint: Checkpoint; messages_count: number }>(
    `/system/session-tree/checkpoints/${checkpointId}`,
  )
}

/** 删除检查点 */
export function deleteCheckpoint(checkpointId: string) {
  return apiClient.delete(`/system/session-tree/checkpoints/${checkpointId}`)
}

/** 从检查点恢复会话 */
export function restoreFromCheckpoint(data: RestoreRequest) {
  return apiClient.post<{ restored_session: TreeNode; messages_count: number }>(
    "/system/session-tree/restore",
    data,
  )
}
