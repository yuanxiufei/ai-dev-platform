/**
 * Integrations API — 第三方服务集成管理
 */
import apiClient from "./client"

export interface IntegrationItem {
  id: string
  name: string
  display_name: string
  description: string | null
  category: string
  connected: boolean
  status: string
  error_message: string | null
  config: Record<string, unknown> | null
  last_connected_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface IntegrationCreatePayload {
  name: string
  display_name: string
  description?: string
  category?: string
  config?: Record<string, unknown>
}

export interface IntegrationUpdatePayload {
  display_name?: string
  description?: string
  category?: string
  config?: Record<string, unknown>
}

export interface ConnectPayload {
  api_key?: string
  config?: Record<string, unknown>
}

// ── API Functions ────────────────────────────────────────

export async function listIntegrations(category?: string) {
  return apiClient.get("/integrations", {
    params: category ? { category } : undefined,
  })
}

export async function getIntegration(id: string) {
  return apiClient.get(`/integrations/${id}`)
}

export async function createIntegration(payload: IntegrationCreatePayload) {
  return apiClient.post("/integrations", payload)
}

export async function updateIntegration(
  id: string,
  payload: IntegrationUpdatePayload,
) {
  return apiClient.put(`/integrations/${id}`, payload)
}

export async function deleteIntegration(id: string) {
  return apiClient.delete(`/integrations/${id}`)
}

export async function connectIntegration(id: string, payload?: ConnectPayload) {
  return apiClient.post(`/integrations/${id}/connect`, payload || {})
}

export async function disconnectIntegration(id: string) {
  return apiClient.post(`/integrations/${id}/disconnect`)
}

export async function getIntegrationStats() {
  return apiClient.get("/integrations/stats")
}
