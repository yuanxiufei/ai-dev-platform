/**
 * FIM 代码补全 API — Fill-in-the-Middle 补全请求
 *
 * 借鉴 Tabby completions API + Continue autocomplete 设计
 */
import apiClient from "./client"

/* ========== 类型定义 ========== */

/** 补全触发类型 */
export type CompletionTrigger =
  | "keystroke"
  | "dot"
  | "import"
  | "function_call"
  | "newline"
  | "manual"

/** 单条补全项 */
export interface CompletionItem {
  text: string
  display_text?: string
  score?: number
  prefix_match?: number
  type_match?: number
  liveness?: number
  semantic?: number
  source?: string
  latency_ms?: number
}

/** 补全请求 */
export interface CompletionRequest {
  file_content: string
  cursor_line: number       // 0-based
  cursor_column: number      // 0-based
  file_path?: string
  language?: string
  trigger?: CompletionTrigger
  top_k?: number
  temperature?: number
  max_tokens?: number
}

/** 补全响应 */
export interface CompletionResponse {
  items: CompletionItem[]
  total: number
  cache_hit: boolean
  trigger: CompletionTrigger
  latency_ms: number
  model_used: string
}

/** 反馈请求 */
export interface CompletionFeedback {
  accepted: boolean
  completion_text: string
  file_path?: string
  cursor_line?: number
  cursor_column?: number
  latency_ms?: number
  source?: string
}

/* ========== API 方法 ========== */

/** 执行代码补全 */
export const requestCompletion = (data: CompletionRequest) =>
  apiClient.post<CompletionResponse>("/agent/code-completion/complete", data)

/** 分析光标上下文 */
export const analyzeContext = (data: {
  file_content: string
  cursor_line: number
  cursor_column: number
  file_path?: string
  language?: string
}) =>
  apiClient.post<{
    context: Record<string, unknown>
    imports: string[]
    functions: string[]
    nearby_code: string
  }>("/agent/code-completion/analyze-context", data)

/** 提交补全反馈 */
export const sendFeedback = (data: CompletionFeedback) =>
  apiClient.post<{ ok: boolean }>("/agent/code-completion/feedback", data)

/** 缓存统计 */
export const getCacheStats = () =>
  apiClient.get<{
    size: number
    max_size: number
    hit_rate: number
    total_queries: number
  }>("/agent/code-completion/cache-stats")
