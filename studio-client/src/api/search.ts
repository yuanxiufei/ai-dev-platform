// ============================================
// Search API — 全局搜索（对标 VSCode ISearchService）
// 后端端点: /system/search/text, /files, /replace, /engines
// ============================================

import apiClient from './client'

// ─── 前端类型（GlobalSearchPage 使用） ──────

export interface TextSearchParams {
  query: string
  max_results?: number
  file_pattern?: string       // ← 后端: include_patterns (list)
  directory?: string           // ← 后端: path
  case_sensitive?: boolean
  regex?: boolean              // ← 后端: use_regex
  whole_word?: boolean
  engine?: string
}

export interface FileSearchParams {
  query: string                // ← 后端: pattern
  max_results?: number
  directory?: string           // ← 后端: path
  case_sensitive?: boolean
}

export interface ReplaceParams {
  find: string                 // ← 后端: query
  replace: string              // ← 后端: replace_with
  file_pattern?: string        // ← 后端: include_patterns
  directory?: string           // ← 后端: path
  case_sensitive?: boolean
  regex?: boolean              // ← 后端: use_regex
  whole_word?: boolean
}

// ─── 后端原始类型 ──────

export interface SearchMatch {
  file: string
  line: number
  column: number
  match_text: string
  match_length: number
  line_text: string
  preview_before?: string
  preview_after?: string
}

export interface TextSearchResponse {
  results: SearchMatch[]
  total_matches: number
  files_scanned: number
  engine: string
  elapsed_ms: number
}

export interface FileSearchResponse {
  results: string[]
  total: number
  elapsed_ms: number
}

export interface ReplaceResponse {
  replaced: number
  files_modified: number
  errors: string[]
}

export interface EnginesInfo {
  engines: Record<string, { available: boolean; path?: string }>
  max_file_size_mb: number
  max_results: number
}

// ─── API 适配层 ──────

/**
 * 文本内容搜索（ripgrep → Python re 回退）
 * POST /system/search/text
 */
async function textSearch(params: TextSearchParams) {
  const body: Record<string, unknown> = {
    query: params.query,
    path: params.directory || '.',
    max_results: params.max_results ?? 200,
    use_regex: params.regex ?? false,
    case_sensitive: params.case_sensitive ?? false,
    whole_word: params.whole_word ?? false,
  }
  // 前端 file_pattern → 后端 include_patterns (list)
  if (params.file_pattern) {
    body.include_patterns = [params.file_pattern]
  }
  const res = await apiClient.post<TextSearchResponse>('/system/search/text', body)
  return res
}

/**
 * 文件名搜索（glob 模式）
 * POST /system/search/files
 */
async function fileSearch(params: FileSearchParams) {
  const res = await apiClient.post<FileSearchResponse>('/system/search/files', {
    pattern: params.query,
    path: params.directory || '.',
    max_results: params.max_results ?? 200,
  })
  return res
}

/**
 * 搜索替换（全项目或单文件/单行）
 * POST /system/search/replace
 */
async function replace(params: ReplaceParams) {
  const body: Record<string, unknown> = {
    query: params.find,
    replace_with: params.replace,
    path: params.directory || '.',
    use_regex: params.regex ?? false,
    case_sensitive: params.case_sensitive ?? false,
    whole_word: params.whole_word ?? false,
  }
  if (params.file_pattern) {
    body.include_patterns = [params.file_pattern]
  }
  const res = await apiClient.post<ReplaceResponse>('/system/search/replace', body)
  return res
}

/**
 * 获取可用搜索引擎列表
 * GET /system/search/engines
 *
 * 返回原始 engines dict → 前端 GlobalSearchPage 需自行提取 keys
 * res.data.engines → Object.keys(engines).filter(k => engines[k].available)
 */
async function getEngines() {
  const res = await apiClient.get<EnginesInfo>('/system/search/engines')
  return res
}

export const searchApi = {
  textSearch,
  fileSearch,
  replace,
  getEngines,
}
export default searchApi
