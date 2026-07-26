import apiClient from "./client"

/* ========== Agent 自省/反思 API ========== */

export interface ReflectionResult {
  reflection_id: string
  trace_id: string
  agent_name: string
  dimensions: Record<string, number>  // 维度 → 评分 (0-1)
  summary: string
  strengths: string[]
  weaknesses: string[]
  suggestions: string[]
  score_overall: number
  created_at: string
}

export interface SelfCritique {
  critique_id: string
  trace_id: string
  agent_name: string
  result: string
  issues: string[]
  improvements: string[]
  severity: "low" | "medium" | "high"
  created_at: string
}

export interface ReflectionHistoryItem {
  reflection_id: string
  trace_id: string
  agent_name: string
  score_overall: number
  created_at: string
}

export interface ReflectionStats {
  total_reflections: number
  avg_score: number
  max_score: number
  min_score: number
  by_agent: Record<string, { count: number; avg_score: number }>
}

// ── API 方法 ──────────────────────────────────────

/** 执行自省评估 (多维度评分) */
export const reflect = (payload: {
  trace_id: string
  agent_name?: string
  input?: string
  output?: string
}) =>
  apiClient.post<ReflectionResult>("/agent/reflection/reflect", payload)

/** 执行自我批评 */
export const selfCritique = (payload: {
  trace_id: string
  agent_name?: string
  content: string
}) =>
  apiClient.post<SelfCritique>("/agent/reflection/self-critique", payload)

/** 获取自省历史 */
export const getReflectionHistory = (params?: {
  agent_name?: string
  page?: number
  size?: number
}) =>
  apiClient.get<{ data: ReflectionHistoryItem[]; total: number; page: number; size: number }>(
    "/agent/reflection/history",
    { params }
  )

/** 获取自省统计 */
export const getReflectionStats = (params?: { agent_name?: string }) =>
  apiClient.get<ReflectionStats>("/agent/reflection/stats", { params })

/** 获取单次反思详情 */
export const getReflection = (reflectionId: string) =>
  apiClient.get<ReflectionResult>(`/agent/reflection/${encodeURIComponent(reflectionId)}`)
