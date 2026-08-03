/**
 * 护栏 API 模块 — 工具调用授权护栏管理
 * 对应后端: /system/guardrails
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface GuardrailCheckRequest {
  tool_name: string
  tool_params: Record<string, string>
}

export interface GuardrailDecision {
  level: string
  reason: string
  blocked_params: string[]
  suggestions: string[]
}

export interface GuardrailConfig {
  enabled: boolean
  default_level: string
  file_path_whitelist: string[]
  file_path_blacklist: string[]
  sensitive_commands: string[]
  blocked_domains: string[]
  max_file_size_mb: number
  max_command_length: number
}

/* ── 端点 ────────────────────────────────────── */

/** 检查工具调用是否安全 */
export function checkToolCall(data: GuardrailCheckRequest) {
  return apiClient.post<GuardrailDecision>("/system/guardrails/check", data)
}

/** 获取护栏配置 */
export function getGuardrailConfig() {
  return apiClient.get<GuardrailConfig>("/system/guardrails/config")
}
