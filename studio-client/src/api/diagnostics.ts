import apiClient from "./client"

// ============================================
// 代码诊断 API — 静态分析 / 批量分析 / 支持语言
// ============================================

export interface DiagnosticItem {
  file: string
  line: number
  column: number
  message: string
  severity: "error" | "warning" | "info"
  code?: string
}

export interface DiagnosticRequest {
  content: string
  language: string
  file_path?: string
}

export interface DiagnosticResponse {
  diagnostics: DiagnosticItem[]
  summary: { error: number; warning: number; info: number }
}

export interface BatchDiagnosticItem {
  content: string
  language: string
  file_path: string
}

export interface BatchDiagnosticRequest {
  files: BatchDiagnosticItem[]
}

export interface BatchDiagnosticResponse {
  results: Record<string, { diagnostics: DiagnosticItem[]; summary: { error: number; warning: number; info: number } }>
}

export const diagnosticsApi = {
  /** 分析单文件代码，返回诊断列表（Error Lens / Problems Panel 使用） */
  analyze: (req: DiagnosticRequest) =>
    apiClient.post("/system/diagnostics/analyze", req),

  /** 批量分析多个文件 */
  analyzeBatch: (req: BatchDiagnosticRequest) =>
    apiClient.post("/system/diagnostics/analyze-batch", req),

  /** 列出支持诊断的语言 */
  listLanguages: () =>
    apiClient.get("/system/diagnostics/languages"),
}
