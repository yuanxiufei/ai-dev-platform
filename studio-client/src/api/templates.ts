/**
 * 模板 API 模块 — 项目模板 CRUD + 使用
 * 对应后端: /studio/templates
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface StudioTemplate {
  id: string
  name: string
  description: string | null
  category: string
  framework: string
  stack: string
  preview_url: string | null
  usage_count: number
  is_public: boolean
  created_at: string
  template_data?: Record<string, unknown>
}

export interface TemplateCreate {
  name: string
  description?: string
  category?: string
  framework?: string
  stack?: string
  preview_url?: string
  template_data?: Record<string, unknown>
  is_public?: boolean
}

export interface TemplateUpdate {
  name?: string
  description?: string
  category?: string
  preview_url?: string
  template_data?: Record<string, unknown>
  is_public?: boolean
}

export interface PaginatedTemplates {
  data: StudioTemplate[]
  total: number
  page: number
  size: number
}

export interface TemplateUseResult {
  project_id: string
  project_name: string
  template_name: string
  template_data: Record<string, unknown> | null
}

/* ── 端点 ────────────────────────────────────── */

/** 分页列出模板 */
export function listTemplates(params?: {
  page?: number; size?: number; category?: string; framework?: string
}) {
  return apiClient.get<PaginatedTemplates>("/studio/templates", { params })
}

/** 创建模板 */
export function createTemplate(data: TemplateCreate) {
  return apiClient.post<StudioTemplate>("/studio/templates", data)
}

/** 获取模板详情（含 template_data） */
export function getTemplate(templateId: string) {
  return apiClient.get<StudioTemplate>(`/studio/templates/${templateId}`)
}

/** 更新模板 */
export function updateTemplate(templateId: string, data: TemplateUpdate) {
  return apiClient.put<StudioTemplate>(`/studio/templates/${templateId}`, data)
}

/** 删除模板 */
export function deleteTemplate(templateId: string) {
  return apiClient.delete<void>(`/studio/templates/${templateId}`)
}

/** 使用模板创建项目 */
export function useTemplate(templateId: string) {
  return apiClient.post<TemplateUseResult>(`/studio/templates/${templateId}/use`)
}
