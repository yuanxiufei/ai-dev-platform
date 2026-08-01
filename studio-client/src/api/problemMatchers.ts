/**
 * Problem Matchers API — VSCode 风格任务输出解析器
 *
 * POST /system/problem-matchers/parse          — 用指定匹配器解析输出
 * GET  /system/problem-matchers                — 列出所有内置+自定义匹配器
 * POST /system/problem-matchers/custom         — 注册自定义匹配器
 * DELETE /system/problem-matchers/custom/{id}  — 删除自定义匹配器
 */

import apiClient from './client'

// ═══════════════════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════════════════

export type SeverityLevel = 'error' | 'warning' | 'info' | 'hint'
export type MatcherMode = 'single_line' | 'multi_line'

export interface ProblemPattern {
  regexp: string
  file_group: number
  line_group: number
  column_group?: number
  end_line_group?: number
  end_column_group?: number
  message_group: number
  severity_group?: number
  code_group?: number
  kind?: string
}

export interface MatcherItem {
  id: string
  label: string
  owner: string
  source: string
  mode: MatcherMode
  is_builtin: boolean
  is_custom: boolean
  severity: SeverityLevel
}

export interface MatcherListResponse {
  total: number
  matchers: MatcherItem[]
}

export interface DiagnosticItem {
  file_path: string
  line: number
  column?: number
  end_line?: number
  end_column?: number
  severity: SeverityLevel
  message: string
  code?: string
  source: string
  matcher: string
  raw_line: string
}

export interface ParseResponse {
  diagnostics: DiagnosticItem[]
  total: number
  matcher_used: string
  lines_processed: number
}

export interface CustomMatcherPayload {
  id: string
  label: string
  owner?: string
  source?: string
  mode?: MatcherMode
  file_location?: string
  severity?: SeverityLevel
  pattern: ProblemPattern
  watching?: { beginsPattern?: string; endsPattern?: string }
}

// ═══════════════════════════════════════════════════
// API 函数
// ═══════════════════════════════════════════════════

/** 列出所有可用匹配器 (内置 + 自定义) */
export async function listMatchers(): Promise<MatcherListResponse> {
  const { data } = await apiClient.get<MatcherListResponse>('/system/problem-matchers')
  return data
}

/** 解析构建/任务输出为结构化诊断 */
export async function parseOutput(
  matcherId: string,
  content: string,
): Promise<ParseResponse> {
  const { data } = await apiClient.post<ParseResponse>('/system/problem-matchers/parse', {
    matcher_id: matcherId,
    content,
  })
  return data
}

/** 注册自定义问题匹配器 */
export async function registerCustomMatcher(
  payload: CustomMatcherPayload,
): Promise<{ status: string; id: string; label: string }> {
  const { data } = await apiClient.post('/system/problem-matchers/custom', payload)
  return data
}

/** 删除自定义匹配器 */
export async function deleteCustomMatcher(
  matcherId: string,
): Promise<{ status: string; id: string }> {
  const { data } = await apiClient.delete(`/system/problem-matchers/custom/${matcherId}`)
  return data
}
