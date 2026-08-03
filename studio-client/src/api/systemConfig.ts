/**
 * 系统配置 API — 配置查看/热加载
 * 对应后端: /system/config
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface ReloadResult {
  status: string
  reload_count?: number
  timestamp?: string
  message?: string
}

/* ── 端点 ────────────────────────────────────── */

/** 获取当前配置（敏感值脱敏） */
export function getConfig() {
  return apiClient.get<Record<string, unknown>>("/system/config")
}

/** 热加载配置 */
export function reloadConfig() {
  return apiClient.post<ReloadResult>("/system/config/reload")
}
