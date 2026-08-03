/**
 * 第三方集成 API 模块 — 外部服务连接管理
 * 对应后端: /integrations
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface Integration {
  id: string
  name: string
  category: string
  provider: string
  status: "connected" | "disconnected" | "error"
  config: Record<string, unknown>
  metadata?: Record<string, unknown>
  last_sync?: string
  created_at: string
  updated_at: string
}

export interface IntegrationCreate {
  name: string
  category: string
  provider: string
  config?: Record<string, unknown>
}

export interface IntegrationUpdate {
  name?: string
  config?: Record<string, unknown>
  metadata?: Record<string, unknown>
}

export interface ConnectRequest {
  credentials: Record<string, string>
  options?: Record<string, unknown>
}

export interface IntegrationStats {
  total: number
  connected: number
  disconnected: number
  error: number
  by_category: Record<string, number>
}

/* ── 端点 ────────────────────────────────────── */

/** 列出所有集成 */
export function listIntegrations(category?: string) {
  return apiClient.get<Integration[]>("/integrations", {
    params: category ? { category } : {},
  })
}

/** 获取集成详情 */
export function getIntegration(integrationId: string) {
  return apiClient.get<Integration>(`/integrations/${integrationId}`)
}

/** 创建集成 */
export function createIntegration(data: IntegrationCreate) {
  return apiClient.post<Integration>("/integrations", data)
}

/** 更新集成 */
export function updateIntegration(integrationId: string, data: IntegrationUpdate) {
  return apiClient.put<Integration>(`/integrations/${integrationId}`, data)
}

/** 删除集成 */
export function deleteIntegration(integrationId: string) {
  return apiClient.delete(`/integrations/${integrationId}`)
}

/** 连接集成 */
export function connectIntegration(integrationId: string, data: ConnectRequest) {
  return apiClient.post<Integration>(
    `/integrations/${integrationId}/connect`,
    data,
  )
}

/** 断开集成 */
export function disconnectIntegration(integrationId: string) {
  return apiClient.post<Integration>(
    `/integrations/${integrationId}/disconnect`,
  )
}

/** 获取集成统计 */
export function integrationsStats() {
  return apiClient.get<IntegrationStats>("/integrations/stats")
}
