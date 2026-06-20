import apiClient from './client'

/* ========== MCP 错误码 ========== */

export enum MCPErrCode {
  OK = 0,
  UNKNOWN = 1001,
  INVALID_CONFIG = 1002,
  ALREADY_EXISTS = 1003,
  NOT_FOUND = 1004,
  CONNECT_FAILED = 2001,
  CONNECT_TIMEOUT = 2002,
  DISCONNECTED = 2003,
  RECONNECT_EXHAUSTED = 2004,
  INIT_FAILED = 2005,
  PROTOCOL_ERROR = 3001,
  JSONRPC_ERROR = 3002,
  METHOD_NOT_FOUND = 3003,
  INVALID_PARAMS = 3004,
  TOOL_NOT_FOUND = 4001,
  TOOL_EXEC_ERROR = 4002,
  TOOL_TIMEOUT = 4003,
  RESOURCE_NOT_FOUND = 5001,
  SECURITY_VIOLATION = 6001,
  COMMAND_DENIED = 6002,
}

export interface MCPApiError {
  error_code: number
  error: string
  detail?: any
}

/* ========== MCP 连接状态 ========== */

export type MCPConnState =
  | 'disconnected' | 'connecting' | 'connected'
  | 'reconnecting' | 'failed' | 'disabled'

/* ========== MCP 服务器状态（后端返回的完整快照）========== */

export interface MCPServerStatus {
  name: string
  transport: string           // sse | streamable_http | stdio
  url: string                 // HTTP URL（SSE/HTTP模式）
  command: string             // 完整命令行（Stdio模式）
  state: MCPConnState         // 当前连接状态
  connected: boolean          // 是否已连接
  tools_count: number         // 已发现的工具数
  tools: any[]                // 工具详情列表（仅在 /servers/{name} 返回）
  tool_prefix: string
  auto_discover: boolean
  enabled: boolean
  timeout_seconds: number
  // 时间戳 (epoch seconds)
  connected_at: number        // 连接建立时间
  last_heartbeat_at: number   // 上次心跳时间
  // 错误 & 重试
  last_error: string          // 最近一次错误信息
  retry_count: number         // 当前重试次数
  total_retries: number       // 累计重试次数
  // 统计
  calls_total: number         // 累计调用次数
  calls_success: number       // 成功次数
  calls_failed: number        // 失败次数
  avg_latency_ms: number      // 平均延迟(ms)
  // 派生字段（后端计算）
  uptime_seconds?: number     // 运行时长(s)
  success_rate?: number       // 调用成功率(0~1)
}

/** 兼容旧接口 — 列表项使用精简版 */
export interface MCPServer extends Pick<MCPServerStatus,
  'name' | 'transport' | 'url' | 'command' | 'connected'
> {
  tools_count: number
  tool_prefix?: string
  auto_discover: boolean
  timeout: number
}

/* ========== 请求/响应类型 ========== */

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
  reconnect?: boolean
  max_retries?: number
  retry_delay?: number
  enabled?: boolean
  heartbeat_interval?: number
}

export interface MCPUpdateServerPayload {
  url?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  tool_prefix?: string
  headers?: Record<string, string>
  auto_discover?: boolean
  timeout?: number
  reconnect?: boolean
  max_retries?: number
  retry_delay?: number
  enabled?: boolean
  heartbeat_interval?: number
}

export interface MCPHealthResult {
  healthy: boolean
  latency_ms: number
  state: MCPConnState
  connected: boolean
  detail: string
  uptime_seconds: number
  success_rate: number
  last_heartbeat_age_seconds: number
}

export interface MCPAllHealthResult {
  overall_healthy: boolean
  servers_checked: number
  servers_healthy: number
  details: Record<string, MCPHealthResult>
}

export interface MCPCallToolPayload {
  server_name: string
  tool_name: string
  arguments?: Record<string, any>
}

export interface MCPCallToolResult {
  content: Array<{ type: string; text?: string; [key: string]: any }>
  is_error: boolean
  latency_ms: number
}

/* ========== MCP 市场 ========== */

export interface MCPMarketplaceServer {
  id: string
  name: string
  description: string
  icon: string
  category: string
  features: string[]
  tags: string[]
  author: string
  version: string
  stars: number
  installs: number
  transport: string
  url: string
  command: string
  args: string[]
  env_config: Record<string, string>
  setup_guide: string
  homepage: string
  source_code: string
  license: string
}

export interface MCPMarketplaceResponse {
  servers: MCPMarketplaceServer[]
  total: number
  categories: string[]
}

export interface MCPCategory {
  id: string
  name: string
  count: number
}

export interface MCPToolInfo {
  name: string
  description: string
  server: string
  parameters: Record<string, any>   // inputSchema.properties
  required: string[]               // inputSchema.required
}

/* ════════════════════════════════════════════
   API 函数
   ════════════════════════════════════════════ */

/* ---------- CRUD ---------- */

/** 列出所有 MCP 服务器（含完整状态） */
export const listMCPServers = () =>
  apiClient.get<{
    error_code: number; success: boolean
    servers: MCPServerStatus[]
    connected: boolean
    total_tools: number
    summary: { total_servers: number; connected_servers: number; by_transport: Record<string, number>; by_state: Record<string, number> }
  }>('/agent/mcp/servers')

/** 单个服务器详情（含工具列表） */
export const getMCPServerDetail = (name: string) =>
  apiClient.get<{
    error_code: number; success: boolean
    server: MCPServerStatus
    tools: MCPToolInfo[]
  }>(`/agent/mcp/servers/${encodeURIComponent(name)}`)

/** 添加并连接 MCP 服务器 */
export const addMCPServer = (data: MCPAddServerPayload) =>
  apiClient.post<{
    error_code: number; success: boolean
    message: string
    tools_discovered?: number
    tools?: string[]
    warnings?: string[]
    errors?: string[]
  }>('/agent/mcp/servers', data)

/** 更新服务器配置 */
export const updateMCPServer = (name: string, data: MCPUpdateServerPayload) =>
  apiClient.put<{
    error_code: number; success: boolean; message: string
  }>(`/agent/mcp/servers/${encodeURIComponent(name)}`, data)

/** 移除并断开 */
export const removeMCPServer = (name: string) =>
  apiClient.delete<{
    error_code: number; success: boolean; message: string
  }>(`/agent/mcp/servers/${encodeURIComponent(name)}`)

/* ---------- 运维操作 ---------- */

/** 扫描工具 */
export const discoverMCPTools = () =>
  apiClient.post<{
    error_code: number; success: boolean
    total: number
    tools: MCPToolInfo[]
    servers_scanned: number
  }>('/agent/mcp/servers/discover')

/** 注册到全局 ToolRegistry */
export const registerMCPTools = () =>
  apiClient.post<{
    error_code: number; success: boolean
    tools_registered: number; message: string
  }>('/agent/mcp/servers/register')

/** 重连单个服务器 */
export const reconnectMCPServer = (name: string) =>
  apiClient.post<{
    error_code: number; success: boolean; message: string; state: string
  }>(`/agent/mcp/servers/${encodeURIComponent(name)}/reconnect`)

/** 单服务器健康检查 */
export const checkMCPServerHealth = (name: string) =>
  apiClient.get<MCPHealthResult>(`/agent/mcp/servers/${encodeURIComponent(name)}/health`)

/** 全部健康检查 */
export const checkAllMCPHealth = () =>
  apiClient.post<MCPAllHealthResult>('/agent/mcp/health')

/** 直接调用工具（调试用） */
export const callMCPToolDirectly = (data: MCPCallToolPayload) =>
  apiClient.post<{
    error_code: number; success: boolean
    content: MCPCallToolResult['content']
    is_error: boolean
    latency_ms: number
  }>('/agent/mcp/tools/call', data)

/* ---------- 市场相关（不变）---------- */

export const getMCPMarketplace = (category?: string, search?: string) =>
  apiClient.get<MCPMarketplaceResponse>('/agent/mcp/marketplace', {
    params: { category, search },
  })

export const getMCPMarketplaceCategories = () =>
  apiClient.get<{ categories: MCPCategory[] }>('/agent/mcp/marketplace/categories')

export const getMCPPresetDetail = (presetId: string) =>
  apiClient.get<MCPMarketplaceServer>(`/agent/mcp/marketplace/${presetId}`)

export const installFromMarketplace = (data: {
  preset_id: string
  transport?: string
  url?: string
  command?: string
  args?: string[]
  env?: Record<string, string>
  timeout?: number
}) =>
  apiClient.post<{
    success: boolean
    message: string
    preset: string
    tools_discovered: number
    tools: string[]
    errors: string[]
  }>('/agent/mcp/marketplace/install', data)
