import apiClient from "./client"

// ── Types ────────────────────────────────────────────

export interface ModelPreset {
  id: string
  name: string
  description: string | null
  model_name: string | null
  system_prompt: string | null
  temperature: number | null
  max_tokens: number | null
  top_p: number | null
  tools: string[] | null
  force_tools: boolean
  knowledge_bases: string[] | null
  variables: Record<string, string> | null
  is_public: boolean
  usage_count: number
  created_at: string | null
  updated_at: string | null
}

export interface PresetCreate {
  name: string
  description?: string
  model_name?: string
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  top_p?: number
  tools?: string[]
  force_tools?: boolean
  knowledge_bases?: string[]
  variables?: Record<string, string>
  is_public?: boolean
}

export interface PresetUpdate {
  name?: string
  description?: string
  model_name?: string
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  top_p?: number
  tools?: string[]
  force_tools?: boolean
  knowledge_bases?: string[]
  variables?: Record<string, string>
  is_public?: boolean
}

export interface ResolvedPreset {
  preset_id: string
  model_name: string | null
  system_prompt: string
  temperature: number | null
  max_tokens: number | null
  tools: string[]
  knowledge_bases: string[]
  force_tools: boolean
  resolved_variables: Record<string, string>
}

// ── API ──────────────────────────────────────────────

export const modelPresetsApi = {
  /** 列出预设（自己的 + 公开的） */
  list: (page = 1, size = 20, search?: string) =>
    apiClient.get<{ data: ModelPreset[]; total: number; page: number; size: number }>(
      "/model-presets/presets",
      { params: { page, size, search } },
    ),

  /** 创建预设 */
  create: (data: PresetCreate) =>
    apiClient.post<ModelPreset>("/model-presets/presets", data),

  /** 获取单个预设详情 */
  get: (presetId: string) =>
    apiClient.get<ModelPreset>(`/model-presets/presets/${presetId}`),

  /** 更新预设 */
  update: (presetId: string, data: PresetUpdate) =>
    apiClient.put<ModelPreset>(`/model-presets/presets/${presetId}`, data),

  /** 删除预设 */
  delete: (presetId: string) =>
    apiClient.delete(`/model-presets/presets/${presetId}`),

  /** 应用预设（增加使用计数） */
  apply: (presetId: string) =>
    apiClient.post<ModelPreset>(`/model-presets/presets/${presetId}/apply`),

  /** 解析预设中的动态变量 */
  resolve: (presetId: string, context?: Record<string, string>) =>
    apiClient.post<ResolvedPreset>(`/model-presets/presets/${presetId}/resolve`, context || {}),
}
