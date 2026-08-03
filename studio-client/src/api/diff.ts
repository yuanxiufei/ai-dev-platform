/**
 * Diff API 模块 — 服务端文本差异计算
 * 对应后端: /system/diff (text/files/apply/formats)
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export type DiffFormat = "unified" | "context" | "line" | "side"

export interface DiffLine {
  type: string // same | added | removed | header
  content: string
  old_line: number | null
  new_line: number | null
}

export interface DiffStats {
  total_lines: number
  added: number
  removed: number
  changed: number
  unchanged: number
  original_label: string
  modified_label: string
}

export interface DiffRequest {
  original: string
  modified: string
  format?: DiffFormat
  context_lines?: number
  original_label?: string
  modified_label?: string
}

export interface DiffResponse {
  diff_text: string
  lines: DiffLine[]
  stats: DiffStats
  format: string
}

export interface PatchRequest {
  original: string
  patch: string
  strict?: boolean
}

export interface PatchResponse {
  result: string
  changed: boolean
  hunks_applied: number
  hunks_failed: number
}

export interface FormatOption {
  id: string
  label: string
  supports_context: boolean
}

/* ── 端点 ────────────────────────────────────── */

/** 计算文本差异 */
export function computeTextDiff(data: DiffRequest) {
  return apiClient.post<DiffResponse>("/system/diff/text", data)
}

/** 计算文件差异 */
export function computeFileDiff(data: DiffRequest) {
  return apiClient.post<DiffResponse>("/system/diff/files", data)
}

/** 应用 patch */
export function applyPatch(data: PatchRequest) {
  return apiClient.post<PatchResponse>("/system/diff/apply", data)
}

/** 列出支持的格式 */
export function listDiffFormats() {
  return apiClient.get<{ formats: FormatOption[] }>("/system/diff/formats")
}
