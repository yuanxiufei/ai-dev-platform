import apiClient from './client'

/* ========== Agent 对话 ========== */

export interface AgentChatRequest {
  message: string
  agent_name?: string
  instructions?: string
  tools?: string[]
  tool_categories?: string[]
  max_turns?: number
  preferred_model?: string
  session_id?: string
}

export interface AgentChatResponse {
  answer: string
  turns: number
  tool_calls: number
  model_used: string
  provider: string
  tokens_used: number
  latency_ms: number
  error: string
}

export const agentChat = (data: AgentChatRequest) =>
  apiClient.post<AgentChatResponse>('/agent/chat', data)

export const agentChatSimple = (data: AgentChatRequest) =>
  apiClient.post<{ answer: string; model_used: string; provider: string; tokens_used: number }>(
    '/agent/chat/simple',
    data,
  )

/** SSE 流式 Agent 对话 —— 返回 ReadableStream 用于 fetch + EventSource 模式 */
export const agentChatStreamUrl = () => `${apiClient.defaults.baseURL}/agent/chat/stream`

/* ========== 工具管理 ========== */

export interface AgentTool {
  name: string
  description: string
  category: string
  tags: string[]
  version: string
  parameters: {
    name: string
    type: string
    required: boolean
    description: string
    default?: unknown
  }[]
  signature: string
  is_async: boolean
}

export interface AgentToolSummary {
  name: string
  description: string
  category: string
  tags: string[]
  version: string
}

export const listAgentTools = (category?: string) =>
  apiClient.get<{ total: number; tools: AgentToolSummary[]; categories: string[] }>(
    '/agent/tools',
    { params: category ? { category } : {} },
  )

export const getAgentTool = (name: string) =>
  apiClient.get<AgentTool>(`/agent/tools/${encodeURIComponent(name)}`)

export const callAgentTool = (name: string, args: Record<string, unknown>) =>
  apiClient.post<{ success: boolean; tool_name: string; result?: string; error?: string }>(
    `/agent/tools/${encodeURIComponent(name)}`,
    { arguments: args },
  )
