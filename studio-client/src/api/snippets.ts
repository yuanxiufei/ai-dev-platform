import apiClient from "./client"

// ============================================
// 代码片段管理 API — CRUD + 导入导出 + 语言分类
// ============================================

export interface SnippetItem {
  id: string
  prefix: string
  name: string
  description: string
  body: string
  language: string | null
  tags: string[]
  is_builtin: boolean
}

export interface SnippetCreate {
  prefix: string
  name: string
  description?: string
  body: string
  language?: string | null
  tags?: string[]
}

export interface SnippetUpdate {
  prefix?: string | null
  name?: string | null
  description?: string | null
  body?: string | null
  language?: string | null
  tags?: string[] | null
}

export const snippetsApi = {
  /** 列出所有片段（支持按语言/标签/关键词筛选） */
  listAll: (params?: { language?: string; tag?: string; search?: string }) =>
    apiClient.get("/system/snippets", { params }),

  /** 创建新片段 */
  create: (data: SnippetCreate) =>
    apiClient.post("/system/snippets", data),

  /** 获取单个片段详情 */
  getById: (sid: string) =>
    apiClient.get(`/system/snippets/${sid}`),

  /** 更新片段 */
  update: (sid: string, data: SnippetUpdate) =>
    apiClient.put(`/system/snippets/${sid}`, data),

  /** 删除片段（内置片段不可删除） */
  delete: (sid: string) =>
    apiClient.delete(`/system/snippets/${sid}`),

  /** 获取所有语言列表 */
  listLanguages: () =>
    apiClient.get("/system/snippets/languages"),

  /** 获取指定语言及通用片段（Monaco 补全 Provider 专用） */
  forLanguage: (lang: string) =>
    apiClient.get(`/system/snippets/for-language/${lang}`),

  /** 批量导入片段 */
  importSnippets: (data: SnippetCreate[]) =>
    apiClient.post("/system/snippets/import", data),

  /** 导出片段（按语言可选过滤） */
  exportSnippets: (language?: string) =>
    apiClient.get("/system/snippets/export", { params: language ? { language } : {} }),
}
