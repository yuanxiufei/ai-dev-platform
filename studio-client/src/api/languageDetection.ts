/**
 * 语言检测 API 模块 — 代码语言自动识别
 * 对应后端: /system/language
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface DetectRequest {
  code: string
  filename?: string
  hint_language?: string
}

export interface DetectResponse {
  language: string
  confidence: number
  alternatives: LanguageAlternative[]
  features?: {
    keywords: string[]
    patterns: string[]
    file_extensions: string[]
  }
}

export interface LanguageAlternative {
  language: string
  confidence: number
}

export interface LanguageInfo {
  id: string
  name: string
  extensions: string[]
  aliases: string[]
  mime_types: string[]
  ace_mode: string
  color?: string
}

/* ── 端点 ────────────────────────────────────── */

/** 检测代码语言 */
export function detectLanguage(data: DetectRequest) {
  return apiClient.post<DetectResponse>("/system/language/detect", data)
}

/** 获取语言映射 */
export function getLanguageMap() {
  return apiClient.get<LanguageInfo[]>("/system/language/map")
}
