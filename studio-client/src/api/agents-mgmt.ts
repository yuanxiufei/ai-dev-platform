/**
 * Agent Management API — Agent 配置 CRUD + 工具元数据
 */
import apiClient from './client'

export interface AgentItem {
  id: string
  name: string
  description: string | null
  mode: 'craft' | 'ask' | 'plan'
  agentic_mode: 'agentic' | 'manual'
  model: string
  system_prompt: string | null
  tools: string[] | null
  tool_categories: string[] | null
  mcp_servers: string[] | null
  auto_run: boolean
  enabled: boolean
  sort_order: number
  scope: 'user' | 'project'
  project_id: string | null
  created_at: string | null
  updated_at: string | null
}

export interface AgentCreatePayload {
  name: string
  description?: string
  mode?: string
  agentic_mode?: 'agentic' | 'manual'
  model?: string
  system_prompt: string
  tools?: string[]
  tool_categories?: string[]
  mcp_servers?: string[]
  auto_run?: boolean
  enabled?: boolean
  sort_order?: number
  scope?: 'user' | 'project'
  project_id?: string | null
}

export interface AgentUpdatePayload {
  name?: string
  description?: string
  mode?: string
  agentic_mode?: 'agentic' | 'manual'
  model?: string
  system_prompt?: string
  tools?: string[]
  tool_categories?: string[]
  mcp_servers?: string[]
  auto_run?: boolean
  enabled?: boolean
  sort_order?: number
  scope?: string
  project_id?: string | null
}

// ── Tools Metadata Types ───────────────────────────────

export interface ToolMetaItem {
  id: string
  name: string
  description: string
  enabled: boolean
}

export interface ToolCategory {
  id: string
  name: string
  label: string
  icon: string
  description: string
  tools: ToolMetaItem[]
}

export interface MCPStatus {
  connected: boolean
  servers: Array<{ name: string; transport: string; url: string; connected: boolean }>
  tools: Array<{ name: string; description: string; server: string }>
}

export interface ToolsMetadataResponse {
  categories: ToolCategory[]
  mcp: MCPStatus
}

// ── API Functions ───────────────────────────────────────

export async function listAgents(mode?: string, scope?: string) {
  return apiClient.get('/agents', { params: { mode, scope } })
}

export async function getAgent(id: string) {
  return apiClient.get(`/agents/${id}`)
}

export async function createAgent(payload: AgentCreatePayload) {
  return apiClient.post('/agents', payload)
}

export async function updateAgent(id: string, payload: AgentUpdatePayload) {
  return apiClient.put(`/agents/${id}`, payload)
}

export async function deleteAgent(id: string) {
  return apiClient.delete(`/agents/${id}`)
}

export async function toggleAgent(id: string) {
  return apiClient.post(`/agents/${id}/toggle`)
}

export async function cloneAgent(id: string) {
  return apiClient.post(`/agents/${id}/clone`)
}

/** 获取工具分类元数据（含 MCP 状态） */
export async function getToolsMetadata(): Promise<{ data: ToolsMetadataResponse }> {
  return apiClient.get('/agents/tools-metadata')
}
