/**
 * 分析 API 模块 — Agent 使用分析面板
 * 对应后端: /analytics
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface AnalyticsOverview {
  total_requests: number
  total_tokens: number
  avg_tokens_per_request: number
  active_models: number
  success_rate: number
  period_days: number
}

export interface ModelUsage {
  model_name: string
  request_count: number
  total_tokens: number
  avg_latency_ms: number
  success_count: number
  failure_count: number
}

export interface TrendPoint {
  date: string
  request_count: number
  token_count: number
  avg_latency_ms: number
}

export interface CapabilityUsage {
  capability: string
  request_count: number
  total_tokens: number
  avg_latency_ms: number
}

export interface TopPrompt {
  prompt_hash: string
  prompt_preview: string
  use_count: number
  last_used: string
  avg_tokens: number
}

/* ── 端点 ────────────────────────────────────── */

/** 分析概览 */
export function analyticsOverview(params?: { days?: number }) {
  return apiClient.get<AnalyticsOverview>("/analytics/overview", { params })
}

/** 按模型统计 */
export function analyticsByModel(params?: { days?: number; limit?: number }) {
  return apiClient.get<ModelUsage[]>("/analytics/by-model", { params })
}

/** 时间趋势 */
export function analyticsTrends(params?: { days?: number; granularity?: string }) {
  return apiClient.get<TrendPoint[]>("/analytics/trends", { params })
}

/** 按能力统计 */
export function analyticsByCapability(params?: { days?: number }) {
  return apiClient.get<CapabilityUsage[]>("/analytics/by-capability", { params })
}

/** 热门提示词 */
export function analyticsTopPrompts(params?: { days?: number; limit?: number }) {
  return apiClient.get<TopPrompt[]>("/analytics/top-prompts", { params })
}
