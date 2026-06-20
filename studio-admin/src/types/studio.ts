export interface Project {
  id: string
  name: string
  description: string
  status: 'draft' | 'building' | 'deploying' | 'running' | 'failed'
  template_id?: string
  created_at: string
  updated_at: string
}

export interface Template {
  id: string
  name: string
  description: string
  category: string
  preview_url?: string
  created_at: string
}

export interface ApiResponse<T = unknown> {
  message: string
  data?: T
}

export interface ApiPageResponse<T = unknown> {
  data: T[]
  total: number
  page: number
  size: number
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
