/**
 * 聊天 API 模块 — Agent 对话交互
 * 对应后端: /agent/chat
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface AgentChatRequest {
  message: string
  session_id?: string
  model?: string
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  tools?: string[]
  context?: Record<string, unknown>
  images?: string[]
}

export interface AgentChatResponse {
  id: string
  session_id: string
  message: string
  role: "assistant"
  model: string
  usage?: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
  tool_calls?: ToolCallItem[]
  finish_reason?: string
  metadata?: Record<string, unknown>
}

export interface ToolCallItem {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: string
}

/* ── 端点 ────────────────────────────────────── */

/** 同步聊天 */
export function agentChat(data: AgentChatRequest) {
  return apiClient.post<AgentChatResponse>("/agent/chat", data)
}

/** 流式聊天 (SSE) */
export function agentChatStream(data: AgentChatRequest) {
  return apiClient.post("/agent/chat/stream", data, {
    responseType: "stream",
    headers: { Accept: "text/event-stream" },
  })
}

/** 简化聊天（返回纯字典） */
export function agentChatSimple(data: AgentChatRequest) {
  return apiClient.post<Record<string, unknown>>("/agent/chat/simple", data)
}
