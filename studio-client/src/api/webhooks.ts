/**
 * Webhook API 模块 — 回调注册/触发/测试/日志
 * 对应后端: /webhooks
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface EventType {
  value: string
  name: string
  description: string
}

export interface WebhookRegistration {
  id: string
  url: string
  name: string
  events: string[]
  is_active: boolean
  max_retries: number
  timeout_seconds: number
  headers: Record<string, string>
  description: string
  secret?: string
  created_at: string
  last_triggered_at: string
  success_count: number
  failure_count: number
}

export interface WebhookCreate {
  url: string
  name: string
  events: string[]
  secret?: string
  max_retries?: number
  timeout_seconds?: number
  headers?: Record<string, string>
  description?: string
  is_active?: boolean
}

export interface WebhookUpdate {
  url?: string
  name?: string
  events?: string[]
  secret?: string
  max_retries?: number
  timeout_seconds?: number
  headers?: Record<string, string>
  description?: string
  is_active?: boolean
}

export interface DeliveryLog {
  id: string
  webhook_id: string
  event_type: string
  url: string
  status: number
  success: boolean
  error_message: string
  attempt: number
  sent_at: string
  latency_ms: number
}

export interface TestResult {
  success: boolean
  status: number
  error_message: string
  latency_ms: number
  delivery: DeliveryLog
}

export interface TriggerRequest {
  event_type: string
  payload?: Record<string, unknown>
}

export interface TriggerResponse {
  event_type: string
  delivered_to: number
  deliveries: DeliveryLog[]
}

/* ── 端点 ────────────────────────────────────── */

/** 列出所有事件类型 */
export function listEventTypes() {
  return apiClient.get<{ event_types: EventType[] }>("/webhooks/event-types")
}

/** 列出 webhook */
export function listWebhooks(params?: { event_type?: string; active_only?: boolean }) {
  return apiClient.get<{ webhooks: WebhookRegistration[]; total: number }>("/webhooks", { params })
}

/** 创建 webhook */
export function createWebhook(data: WebhookCreate) {
  return apiClient.post<{ id: string } & WebhookRegistration>("/webhooks", data)
}

/** 获取 webhook */
export function getWebhook(webhookId: string) {
  return apiClient.get<WebhookRegistration>(`/webhooks/${webhookId}`)
}

/** 更新 webhook */
export function updateWebhook(webhookId: string, data: WebhookUpdate) {
  return apiClient.put<WebhookRegistration>(`/webhooks/${webhookId}`, data)
}

/** 删除 webhook */
export function deleteWebhook(webhookId: string) {
  return apiClient.delete<{ message: string; id: string }>(`/webhooks/${webhookId}`)
}

/** 测试 webhook */
export function testWebhook(webhookId: string) {
  return apiClient.post<TestResult>(`/webhooks/${webhookId}/test`)
}

/** 手动触发事件 */
export function triggerEvent(data: TriggerRequest) {
  return apiClient.post<TriggerResponse>("/webhooks/trigger", data)
}

/** 获取投递日志 */
export function getDeliveryLogs(params: { webhook_id?: string; limit?: number }) {
  return apiClient.get<{ logs: DeliveryLog[]; total: number }>("/webhooks/logs", { params })
}
