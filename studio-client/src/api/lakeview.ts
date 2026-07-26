import apiClient from "./client"

/* ========== Lakeview 会话摘要 API ========== */

export interface LakeviewStep {
  turn: number
  tag: string
  summary: string
  tool_name: string
  tool_args_preview: string
  success: boolean
  latency_ms: number
  result_preview: string
}

export interface LakeviewRun {
  agent_id: string
  session_id: string
  total_turns: number
  total_tool_calls: number
  total_tokens: number
  total_latency_ms: number
  error: string | null
  final_answer_preview: string
  tags_summary: Record<string, any>
  steps: LakeviewStep[]
}

export const getLakeview = (sessionId: string) =>
  apiClient.get<{ data: LakeviewRun }>(`/agent/lakeview/${encodeURIComponent(sessionId)}`)

export const getLakeviewCompact = (sessionId: string, maxTokens = 2000) =>
  apiClient.get<{ data: { compact_summary: string } }>(
    `/agent/lakeview/${encodeURIComponent(sessionId)}/compact`,
    { params: { max_tokens: maxTokens } }
  )

export const getLakeviewMarkdown = (sessionId: string) =>
  apiClient.get<{ data: { markdown: string } }>(
    `/agent/lakeview/${encodeURIComponent(sessionId)}/markdown`
  )

export const clearLakeview = (sessionId: string) =>
  apiClient.delete<{ message: string }>(`/agent/lakeview/${encodeURIComponent(sessionId)}`)

export const lakeviewApi = {
  getLakeview,
  getLakeviewCompact,
  getLakeviewMarkdown,
  clearLakeview,
}
