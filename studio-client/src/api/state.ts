import apiClient from "./client"

/* ========== 状态项 ========== */

export interface StateItem {
  key: string
  value: unknown
  scope: string
  ttl: number
}

export interface StateListResponse {
  scope: string
  workspaceId: string
  data: Record<string, unknown>
}

export interface StateSetPayload {
  value: unknown
  ttl: number
}

/* ========== CRUD ========== */

/** 列出状态下所有键值对 */
export const listState = (scope: string, workspaceId: string) =>
  apiClient.get<StateListResponse>(`/system/state/${scope}/${workspaceId}`)

/** 设置状态值 */
export const setState = (
  scope: string,
  workspaceId: string,
  key: string,
  payload: StateSetPayload,
) =>
  apiClient.post<{ key: string; set: boolean }>(
    `/system/state/${scope}/${workspaceId}/${encodeURIComponent(key)}`,
    payload,
  )

/** 删除状态值 */
export const deleteState = (scope: string, workspaceId: string, key: string) =>
  apiClient.delete<{ key: string; deleted: boolean }>(
    `/system/state/${scope}/${workspaceId}/${encodeURIComponent(key)}`,
  )

/* ========== 批量操作 ========== */

/** 清理过期状态 */
export const cleanupExpired = () =>
  apiClient.post<{ cleaned: number }>("/system/state/cleanup")

/** 清除工作区所有状态 */
export const clearAllState = (workspaceId: string) =>
  apiClient.post<{ workspaceId: string; cleared: boolean }>(
    `/system/state/clear/${workspaceId}`,
  )

/** 强制持久化所有状态 */
export const flushState = () =>
  apiClient.post<{ flushed: boolean }>("/system/state/flush")

/* ========== 聚合导出（兼容 Page 层的 stateApi 用法） ========== */

export const stateApi = {
  list: listState,
  set: setState,
  delete: deleteState,
  cleanup: cleanupExpired,
  clearAll: clearAllState,
  flush: flushState,
}
