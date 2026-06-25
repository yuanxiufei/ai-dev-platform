import apiClient from "./client"

/* ========== Prompt 模板 ========== */

export interface TemplateVariableDef {
  type: string
  default: string | number | boolean
  description: string
  required: boolean
  options: string[]
}

export interface PromptTemplateData {
  id: string
  command: string
  title: string
  prompt: string
  variables: Record<string, TemplateVariableDef>
  category: string
  version: string
  author: string
  tags: string[]
  is_public: boolean
  description: string
  icon: string
  created_at: string
  updated_at: string
  usage_count: number
}

export interface CommandSearchResult {
  id: string
  command: string
  title: string
  category: string
  icon: string
  variable_names: string[]
}

export interface TemplateCreatePayload {
  command: string
  title: string
  prompt: string
  variables?: Record<string, TemplateVariableDef>
  category?: string
  description?: string
  icon?: string
  tags?: string[]
}

export const promptTemplateApi = {
  /** 列出所有模板 */
  list: (category?: string, search?: string) =>
    apiClient.get<{ templates: PromptTemplateData[]; count: number }>(
      "/prompt-templates",
      { params: { category, search } },
    ),

  /** 获取分类列表 */
  categories: () =>
    apiClient.get<{ categories: { name: string; count: number }[] }>(
      "/prompt-templates/categories",
    ),

  /** 搜索斜杠命令 */
  search: (q: string) =>
    apiClient.get<{ commands: CommandSearchResult[] }>(
      "/prompt-templates/search",
      { params: { q } },
    ),

  /** 创建模板 */
  create: (data: TemplateCreatePayload) =>
    apiClient.post<{ template: PromptTemplateData }>("/prompt-templates", data),

  /** 获取单个模板 */
  get: (id: string) =>
    apiClient.get<{
      template: PromptTemplateData
      variable_names: string[]
    }>(`/prompt-templates/${id}`),

  /** 解析模板（填充变量） */
  resolve: (id: string, values: Record<string, string | number | boolean>) =>
    apiClient.post<{
      template_id: string
      command: string
      resolved_prompt: string
    }>(`/prompt-templates/${id}/resolve`, { values }),

  /** 删除模板 */
  delete: (id: string) => apiClient.delete(`/prompt-templates/${id}`),
}
