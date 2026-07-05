/**
 * Context Keys & Config Resolver API 客户端
 *
 * Session 55: 对标 VSCode context key service + configuration resolver
 */
import apiClient from "./client"

const CTX_BASE = "/system/context-keys"
const CFG_BASE = "/system/config-resolver"
const STATE_BASE = "/system/state"

/* ========== Context Keys ========== */

export interface ContextKeySnapshot {
  workspaceId: string
  keys: Record<string, any>
}

export interface WhenResult {
  result: boolean
  when: string
}

/** 求值 when 子句 */
export async function evaluateWhen(workspaceId: string, when: string): Promise<WhenResult> {
  const { data } = await apiClient.post(`${CTX_BASE}/evaluate`, { when, workspace_id: workspaceId })
  return data
}

/** 获取所有 context keys */
export async function getContextKeys(workspaceId: string): Promise<ContextKeySnapshot> {
  const { data } = await apiClient.get(`${CTX_BASE}/${encodeURIComponent(workspaceId)}`)
  return data
}

/** 批量设置 context keys */
export async function setContextKeys(
  workspaceId: string, updates: Record<string, any>, persist = false
): Promise<{ updated: number }> {
  const { data } = await apiClient.post(`${CTX_BASE}/${encodeURIComponent(workspaceId)}`, {
    updates, persist,
  })
  return data
}

/** 设置单个 context key */
export async function setContextKey(
  workspaceId: string, key: string, value: any, persist = false
): Promise<void> {
  await apiClient.put(`${CTX_BASE}/${encodeURIComponent(workspaceId)}/${encodeURIComponent(key)}`, {
    value, persist,
  })
}

/** 删除 context key */
export async function deleteContextKey(workspaceId: string, key: string): Promise<void> {
  await apiClient.delete(`${CTX_BASE}/${encodeURIComponent(workspaceId)}/${encodeURIComponent(key)}`)
}

/** 更新编辑器状态 context keys */
export async function updateEditorState(
  workspaceId: string, state: {
    langId?: string; hasSelection?: boolean; hasMultiSelections?: boolean
    readonly?: boolean; isModified?: boolean
    resourceExt?: string; resourceFilename?: string; resourcePath?: string
  }
): Promise<void> {
  await apiClient.post(`${CTX_BASE}/${encodeURIComponent(workspaceId)}/editor-state`, state)
}

/* ========== Config Resolver ========== */

export interface ResolveResult {
  original: string
  resolved: string
}

export interface ResolveAllResult {
  original: Record<string, any>
  resolved: Record<string, any>
}

/** 解析文本中的 ${variable} */
export async function resolveConfig(
  text: string,
  opts?: { workspaceRoot?: string; file?: string; configOverrides?: Record<string, any> }
): Promise<ResolveResult> {
  const { data } = await apiClient.post(`${CFG_BASE}/resolve`, {
    text,
    workspace_root: opts?.workspaceRoot || '',
    file: opts?.file || '',
    config_overrides: opts?.configOverrides || {},
  })
  return data
}

/** 递归解析 dict 中所有 ${variable} */
export async function resolveConfigAll(
  input: Record<string, any>,
  opts?: { workspaceRoot?: string; file?: string }
): Promise<ResolveAllResult> {
  const { data } = await apiClient.post(`${CFG_BASE}/resolve-all`, {
    data: input,
    workspace_root: opts?.workspaceRoot || '',
    file: opts?.file || '',
  })
  return data
}

/* ========== State Persistence ========== */

/** 获取全局状态 */
export async function getGlobalState(key: string, defaultVal?: any): Promise<any> {
  try {
    const { data } = await apiClient.get(`${STATE_BASE}/global/global/${encodeURIComponent(key)}`)
    return data.value ?? defaultVal
  } catch { return defaultVal }
}

/** 设置全局状态 */
export async function setGlobalState(key: string, value: any, ttl = 0): Promise<void> {
  await apiClient.post(`${STATE_BASE}/global/global/${encodeURIComponent(key)}`, { value, ttl })
}

/** 获取工作区状态 */
export async function getWorkspaceState(workspaceId: string, key: string, defaultVal?: any): Promise<any> {
  try {
    const { data } = await apiClient.get(`${STATE_BASE}/workspace/${encodeURIComponent(workspaceId)}/${encodeURIComponent(key)}`)
    return data.value ?? defaultVal
  } catch { return defaultVal }
}

/** 设置工作区状态 */
export async function setWorkspaceState(workspaceId: string, key: string, value: any, ttl = 0): Promise<void> {
  await apiClient.post(`${STATE_BASE}/workspace/${encodeURIComponent(workspaceId)}/${encodeURIComponent(key)}`, { value, ttl })
}
