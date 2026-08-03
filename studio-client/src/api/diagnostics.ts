/**
 * 代码诊断 API 模块 — 代码分析与问题诊断
 * 对应后端: /system/diagnostics
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface DiagnosticRequest {
  code: string
  language: string
  file_path?: string
  check_types?: string[] /* lint | type | security | style | performance */
}

export interface DiagnosticIssue {
  line: number
  column?: number
  end_line?: number
  end_column?: number
  severity: "error" | "warning" | "info" | "hint"
  code: string
  message: string
  source: string
  fix?: string
}

export interface DiagnosticResponse {
  file_path?: string
  language: string
  issues: DiagnosticIssue[]
  summary: {
    errors: number
    warnings: number
    info: number
    hints: number
    total: number
  }
  duration_ms: number
}

export interface BatchDiagnosticRequest {
  files: Array<{
    code: string
    language: string
    file_path: string
  }>
  check_types?: string[]
}

export interface BatchDiagnosticResponse {
  results: DiagnosticResponse[]
  total_files: number
  total_issues: number
  duration_ms: number
}

/* ── 端点 ────────────────────────────────────── */

/** 分析代码 */
export function analyzeCode(data: DiagnosticRequest) {
  return apiClient.post<DiagnosticResponse>(
    "/system/diagnostics/analyze",
    data,
  )
}

/** 批量分析 */
export function analyzeBatch(data: BatchDiagnosticRequest) {
  return apiClient.post<BatchDiagnosticResponse>(
    "/system/diagnostics/analyze-batch",
    data,
  )
}

/** 获取支持的语言列表 */
export function listSupportedLanguages() {
  return apiClient.get<string[]>("/system/diagnostics/languages")
}
