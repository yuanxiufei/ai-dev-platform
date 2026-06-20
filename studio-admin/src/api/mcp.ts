import apiClient from './client'

/* ========== MCP 服务器管理 ========== */

export interface MCPServer {
  name: string
  transport: string
  url?: string
  command?: string
  args?: string[]
  tool_prefix?: string
  auto_discover: boolean
  timeout: number
  connected: boolean
  tools_count: number
}

export interface MCPAddServerPayload {
  name: string
  transport: 'sse' | 'streamable_http' | 'stdio'
  url?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  tool_prefix?: string
  headers?: Record<string, string>
  auto_discover?: boolean
  timeout?: number
}

export const listMCPServers = () =>
  apiClient.get<{ servers: MCPServer[]; connected: boolean; total_tools: number }>(
    '/agent/mcp/servers',
  )

export const addMCPServer = (data: MCPAddServerPayload) =>
  apiClient.post<{
    success: boolean
    message: string
    tools_discovered?: number
    tools?: string[]
  }>('/agent/mcp/servers', data)

export const discoverMCPTools = () =>
  apiClient.post<{
    total: number
    tools: { name: string; description: string; server: string }[]
  }>('/agent/mcp/servers/discover')

export const registerMCPTools = () =>
  apiClient.post<{ success: boolean; tools_registered: number; message: string }>(
    '/agent/mcp/servers/register',
  )

export const removeMCPServer = (name: string) =>
  apiClient.delete<{ success: boolean; message: string }>(`/agent/mcp/servers/${name}`)
