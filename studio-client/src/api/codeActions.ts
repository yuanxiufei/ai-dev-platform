/**
 * 代码操作 API 模块 — QuickFix / Source Action / Refactoring
 * 对应后端: /system/code-actions
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export type CodeActionKind =
  | "quickfix"
  | "refactor"
  | "refactor.extract"
  | "refactor.inline"
  | "source"
  | "source.organizeImports"
  | "source.fixAll"

export type DiagnosticSeverity = "error" | "warning" | "info"

export interface DiagnosticItem {
  message: string
  severity?: DiagnosticSeverity
  code?: string
  line?: number
  column?: number
  source?: string
}

export interface TextEdit {
  range_start_line: number
  range_start_col: number
  range_end_line: number
  range_end_col: number
  new_text: string
}

export interface CodeActionItem {
  title: string
  kind: CodeActionKind
  is_preferred: boolean
  diagnostics: string[]
  edits: TextEdit[]
  command: string | null
}

export interface GetCodeActionsRequest {
  content: string
  language?: string
  diagnostics?: DiagnosticItem[]
  range_start_line?: number
  range_start_col?: number
  range_end_line?: number
  range_end_col?: number
}

export interface GetCodeActionsResponse {
  actions: CodeActionItem[]
  source: string
}

export interface ApplyCodeActionResponse {
  content: string
  changed: boolean
  reason?: string
}

/* ── 端点 ────────────────────────────────────── */

/** 获取代码操作建议（灯泡菜单） */
export function getCodeActions(data: GetCodeActionsRequest) {
  return apiClient.post<GetCodeActionsResponse>("/system/code-actions", data)
}

/** 应用代码操作 */
export function applyCodeAction(params: {
  content: string
  diagnostic_message?: string
  diagnostic_code?: string
  diagnostic_line?: number
}) {
  return apiClient.post<ApplyCodeActionResponse>("/system/code-actions/apply", null, { params })
}
