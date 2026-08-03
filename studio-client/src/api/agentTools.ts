/**
 * Agent 工具 API 模块 — 工具列表/详情/直接调用
 * 对应后端: /agent/tools
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface ToolParameter {
  name: string
  type: string
  required: boolean
  description: string
  default: unknown | null
}

export interface ToolSummary {
  name: string
  description: string
  category: string
  tags: string[]
  version: string
  is_async?: boolean
}

export interface ToolDetail extends ToolSummary {
  parameters: ToolParameter[]
  signature: string
}

export interface ToolListResponse {
  total: number
  tools: ToolSummary[]
  categories: string[]
}

export interface ToolCallResponse {
  success: boolean
  tool_name: string
  result?: string
  error?: string
}

/* ── 端点 ────────────────────────────────────── */

/** 列出所有已注册工具 */
export function listTools(params?: { category?: string }) {
  return apiClient.get<ToolListResponse>("/agent/tools", { params })
}

/** 获取工具详情 */
export function getTool(name: string) {
  return apiClient.get<ToolDetail>(`/agent/tools/${encodeURIComponent(name)}`)
}

/** 直接调用工具（测试用） */
export function callTool(name: string, args: Record<string, unknown>) {
  return apiClient.post<ToolCallResponse>(`/agent/tools/${encodeURIComponent(name)}`, { arguments: args })
}
