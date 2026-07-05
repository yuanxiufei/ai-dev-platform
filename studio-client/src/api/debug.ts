/**
 * Debug API 客户端 — 连接后端 /api/v1/system/debug/
 *
 * Session 53: 对标 VSCode DAP (Debug Adapter Protocol)
 * 覆盖: start/stop/pause/continue/step/breakpoints/evaluate/variables/configs
 */
import apiClient from "./client"

const DEBUG_BASE = "/system/debug"

/* ========== 类型定义 ========== */

export interface DebugStackFrame {
  id: number
  name: string
  file: string
  line: number
  column: number
  is_external?: boolean
}

export interface DebugVariable {
  name: string
  value: string
  type: string
  children?: DebugVariable[]
  variables_reference?: number
}

export interface DebugBreakpoint {
  id: string
  file: string
  line: number
  enabled: boolean
  condition?: string
  hit_count?: number
}

export interface DebugState {
  session_id: string
  is_running: boolean
  is_paused: boolean
  stack_frames: DebugStackFrame[]
  variables: DebugVariable[]
  active_frame_id?: number
  stopped_reason?: string
  stopped_text?: string
}

export interface DebugConfig {
  name: string
  type: "python" | "node" | "custom"
  program: string
  args?: string[]
  env?: Record<string, string>
  cwd?: string
}

export interface DebugEvaluateResult {
  id: string
  expression: string
  value: string
  type?: string
  variables_reference?: number
}

export interface DebugSessionInfo {
  session_id: string
  type: string
  program: string
  is_running: boolean
  is_paused: boolean
}

/* ========== API 方法 ========== */

/** 启动调试会话 */
export async function startDebug(config: {
  config_name?: string
  workspace_root?: string
  program?: string
  args?: string[]
  env?: Record<string, string>
  cwd?: string
  type?: "python" | "node" | "custom"
}): Promise<{ session_id: string; status: string; is_paused: boolean }> {
  const { data } = await apiClient.post(`${DEBUG_BASE}/start`, {
    config_name: config.config_name ?? null,
    workspace_root: config.workspace_root ?? ".",
    program: config.program ?? null,
    args: config.args ?? [],
    env: config.env ?? {},
    cwd: config.cwd ?? null,
    type: config.type ?? "python",
  })
  return data
}

/** 停止调试 */
export async function stopDebug(sessionId: string): Promise<void> {
  await apiClient.post(`${DEBUG_BASE}/stop`, { session_id: sessionId })
}

/** 暂停执行 */
export async function pauseDebug(sessionId: string): Promise<void> {
  await apiClient.post(`${DEBUG_BASE}/pause`, { session_id: sessionId })
}

/** 继续执行 */
export async function continueDebug(sessionId: string): Promise<void> {
  await apiClient.post(`${DEBUG_BASE}/continue`, { session_id: sessionId })
}

/** 单步跳过 */
export async function stepOver(sessionId: string): Promise<{ ok: boolean; new_line?: number; file?: string }> {
  const { data } = await apiClient.post(`${DEBUG_BASE}/step-over`, { session_id: sessionId })
  return data
}

/** 单步进入 */
export async function stepInto(sessionId: string): Promise<{ ok: boolean; stack_frames?: DebugStackFrame[] }> {
  const { data } = await apiClient.post(`${DEBUG_BASE}/step-into`, { session_id: sessionId })
  return data
}

/** 单步跳出 */
export async function stepOut(sessionId: string): Promise<{ ok: boolean; stack_frames?: DebugStackFrame[] }> {
  const { data } = await apiClient.post(`${DEBUG_BASE}/step-out`, { session_id: sessionId })
  return data
}

/** 重启调试 */
export async function restartDebug(sessionId: string): Promise<{ session_id: string; status: string }> {
  const { data } = await apiClient.post(`${DEBUG_BASE}/restart`, { session_id: sessionId })
  return data
}

/** 获取调试状态 */
export async function getDebugState(sessionId: string): Promise<DebugState> {
  const { data } = await apiClient.get(`${DEBUG_BASE}/state`, { params: { session_id: sessionId } })
  return data
}

/** 同步断点 */
export async function setBreakpoints(
  sessionId: string,
  breakpoints: Array<{ file: string; line: number; condition?: string; enabled?: boolean }>,
): Promise<DebugBreakpoint[]> {
  const { data } = await apiClient.post(`${DEBUG_BASE}/breakpoints`, {
    session_id: sessionId,
    breakpoints,
  })
  return data
}

/** 求值表达式 */
export async function evaluate(
  sessionId: string,
  expression: string,
  frameId?: number,
): Promise<DebugEvaluateResult> {
  const { data } = await apiClient.post(`${DEBUG_BASE}/evaluate`, {
    session_id: sessionId,
    expression,
    frame_id: frameId ?? null,
  })
  return data
}

/** 获取变量 */
export async function getVariables(
  sessionId: string,
  variablesReference = 0,
): Promise<DebugVariable[]> {
  const { data } = await apiClient.get(`${DEBUG_BASE}/variables`, {
    params: { session_id: sessionId, variables_reference: variablesReference },
  })
  return data
}

/** 获取调试配置 */
export async function getDebugConfigs(workspaceRoot = "."): Promise<DebugConfig[]> {
  const { data } = await apiClient.get(`${DEBUG_BASE}/configs`, {
    params: { workspace_root: workspaceRoot },
  })
  return data
}

/** 列出活跃调试会话 */
export async function listDebugSessions(): Promise<DebugSessionInfo[]> {
  const { data } = await apiClient.get(`${DEBUG_BASE}/sessions`)
  return data
}
