/**
 * 结构化输出 API 模块 — JSON Schema → GBNF 语法转换
 * 对应后端: /structured-output
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface SchemaToGBNFRequest {
  json_schema: Record<string, unknown>
  grammar_name?: string
}

export interface SchemaToGBNFResponse {
  gbnf: string
  warnings: string[]
  grammar_name?: string
}

export interface GBNFValidateRequest {
  gbnf: string
  sample_output?: string
}

export interface GBNFValidateResponse {
  valid: boolean
  errors: string[]
  sample_match?: boolean
}

export interface ResponseFormatPreviewRequest {
  json_schema: Record<string, unknown>
  model?: string
}

export interface ResponseFormatPreviewResponse {
  preview: string
  schema_used: Record<string, unknown>
  model?: string
}

export interface TemplateItem {
  name: string
  description: string
  schema: Record<string, unknown>
}

/* ── 端点 ────────────────────────────────────── */

/** JSON Schema → GBNF 语法 */
export function schemaToGbnf(data: SchemaToGBNFRequest) {
  return apiClient.post<SchemaToGBNFResponse>(
    "/structured-output/json-schema-to-gbnf",
    data,
  )
}

/** 验证 GBNF 语法 */
export function validateGbnf(data: GBNFValidateRequest) {
  return apiClient.post<GBNFValidateResponse>(
    "/structured-output/validate-gbnf",
    data,
  )
}

/** 列出所有模板 */
export function listTemplates() {
  return apiClient.get<TemplateItem[]>("/structured-output/templates")
}

/** 获取指定模板 */
export function getTemplate(name: string) {
  return apiClient.get<TemplateItem>(`/structured-output/templates/${name}`)
}

/** 预览生成格式 */
export function previewResponseFormat(data: ResponseFormatPreviewRequest) {
  return apiClient.post<ResponseFormatPreviewResponse>(
    "/structured-output/preview-response-format",
    data,
  )
}
