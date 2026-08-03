/**
 * OpenAPI 发现 API 模块 — 外部 API 自动发现与工具生成
 * 对应后端: /openapi
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface OpenAPIServer {
  id: string
  name: string
  url: string
  description?: string
  spec_version?: string
  tool_count?: number
  status: "active" | "error" | "discovering"
  last_discovered?: string
}

export interface DiscoverRequest {
  url: string
  name?: string
  api_key?: string
  headers?: Record<string, string>
}

export interface OpenAPITool {
  id: string
  server_id: string
  name: string
  description: string
  method: string
  path: string
  parameters: OpenAPIParam[]
  category?: string
}

export interface OpenAPIParam {
  name: string
  in: "query" | "path" | "header" | "body"
  type: string
  required: boolean
  description?: string
  default?: unknown
  enum?: string[]
  schema?: Record<string, unknown>
}

export interface ToolCallRequest {
  parameters: Record<string, unknown>
  headers?: Record<string, string>
}

export interface ToolCallResult {
  tool_id: string
  status: number
  response: unknown
  latency_ms: number
  headers: Record<string, string>
}

/* ── 端点 ────────────────────────────────────── */

/** 列出已发现的 OpenAPI 服务器 */
export function listServers() {
  return apiClient.get<OpenAPIServer[]>("/openapi/servers")
}

/** 发现新的 OpenAPI 服务器 */
export function discoverServer(data: DiscoverRequest) {
  return apiClient.post<OpenAPIServer>("/openapi/discover", data)
}

/** 获取服务器详情 */
export function getServer(serverId: string) {
  return apiClient.get<OpenAPIServer>(`/openapi/servers/${serverId}`)
}

/** 删除服务器 */
export function deleteServer(serverId: string) {
  return apiClient.delete(`/openapi/servers/${serverId}`)
}

/** 列出所有工具 */
export function listTools(serverId?: string) {
  return apiClient.get<OpenAPITool[]>("/openapi/tools", {
    params: serverId ? { server_id: serverId } : {},
  })
}

/** 获取工具 Schema */
export function getToolSchemas(serverId?: string) {
  return apiClient.get<OpenAPITool[]>("/openapi/tools/schemas", {
    params: serverId ? { server_id: serverId } : {},
  })
}

/** 调用工具 */
export function callTool(toolId: string, data: ToolCallRequest) {
  return apiClient.post<ToolCallResult>(
    `/openapi/tools/${toolId}/call`,
    data,
  )
}
