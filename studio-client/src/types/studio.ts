export interface Project {
  id: string
  name: string
  description?: string
  status: 'draft' | 'building' | 'deploying' | 'running' | 'failed'
  created_at: string
  updated_at?: string
}

export interface Template {
  id: string
  name: string
  description?: string
  category?: string
  thumbnail_url?: string
}

// Agent 对话消息
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool' | 'system'
  content: string
  tool_calls?: ToolCallRecord[]
  metadata?: Record<string, unknown>
  timestamp: string
}

export interface ToolCallRecord {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: string
  success?: boolean
}

// SSE 事件类型
export type SSEEventType =
  | 'turn_start'
  | 'tool_call'
  | 'tool_executing'
  | 'tool_result'
  | 'final_answer'
  | 'error'
  | 'done'

export interface SSEEvent {
  type: SSEEventType
  data?: string
  turn?: number
  max_turns?: number
  tool_calls?: { id: string; name: string; arguments: string }[]
  tool_name?: string
  success?: boolean
  result?: string
  latency_ms?: number
  content?: string
  model_used?: string
  turns?: number
  error?: string
}

// 分页
export interface ApiPageResponse<T = unknown> {
  data: T[]
  total: number
  page: number
  size: number
}
