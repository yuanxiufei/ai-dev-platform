import apiClient from "./client"

/* ========== Agent 调用追踪 API ========== */

// ── 类型定义 ──────────────────────────────────────

export interface TraceSummary {
  trace_id: string
  agent_name: string
  model_name: string
  status: "success" | "failed" | "running" | "cancelled"
  start_time: string
  end_time: string | null
  duration_ms: number
  total_tokens: number
  tool_call_count: number
  error_message: string | null
  created_at: string
}

export interface TraceDetail extends TraceSummary {
  input: string
  output: string | null
  plan: string | null
  metadata: Record<string, unknown>
}

export interface ToolCall {
  tool_call_id: string
  tool_name: string
  arguments: Record<string, unknown>
  result: string | null
  status: "success" | "failed" | "running"
  start_time: string
  end_time: string | null
  duration_ms: number
  error: string | null
}

export interface FileChange {
  file_path: string
  change_type: "create" | "modify" | "delete"
  content_before: string | null
  content_after: string | null
  diff: string | null
  timestamp: string
}

export interface TraceLog {
  log_id: string
  level: "info" | "warn" | "error" | "debug"
  message: string
  timestamp: string
  category: string
}

export interface TraceStats {
  total_traces: number
  success_count: number
  failed_count: number
  running_count: number
  avg_duration_ms: number
  avg_tokens: number
  avg_tool_calls: number
  by_agent: Record<string, number>
  by_model: Record<string, number>
  by_status: Record<string, number>
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  size: number
}

// ── API 方法 ──────────────────────────────────────

/** 获取调用追踪列表 */
export const listTraces = (params?: {
  page?: number
  size?: number
  agent_name?: string
  model_name?: string
  status?: string
}) =>
  apiClient.get<PaginatedResponse<TraceSummary>>("/agent/traces", { params })

/** 获取调用追踪详情 */
export const getTrace = (traceId: string) =>
  apiClient.get<TraceDetail>(`/agent/traces/${encodeURIComponent(traceId)}`)

/** 删除调用追踪 */
export const deleteTrace = (traceId: string) =>
  apiClient.delete<{ ok: boolean }>(`/agent/traces/${encodeURIComponent(traceId)}`)

/** 获取工具调用列表 */
export const listToolCalls = (traceId: string) =>
  apiClient.get<{ data: ToolCall[]; total: number }>(
    `/agent/traces/${encodeURIComponent(traceId)}/tool-calls`
  )

/** 获取文件变更列表 */
export const listFileChanges = (traceId: string) =>
  apiClient.get<{ data: FileChange[]; total: number }>(
    `/agent/traces/${encodeURIComponent(traceId)}/file-changes`
  )

/** 获取追踪日志 */
export const listTraceLogs = (traceId: string, params?: { level?: string; category?: string }) =>
  apiClient.get<{ data: TraceLog[]; total: number }>(
    `/agent/traces/${encodeURIComponent(traceId)}/logs`,
    { params }
  )

/** 获取追踪统计 */
export const getTraceStats = () =>
  apiClient.get<TraceStats>("/agent/traces/stats")
