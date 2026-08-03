import { apiClient } from './client'

// ==================== 请求/响应类型 ====================
export interface FilterInfo {
  name: string
  description: string
  class_name: string
}

export interface FilterApplyRequest {
  text: string
  filter_names?: string[]
  preset?: 'rag_ingest' | 'markdown_clean' | 'webpage_clean'
}

export interface FilterApplyResponse {
  original: string
  filtered: string
  filters_applied: string[]
  original_length: number
  filtered_length: number
  compression_ratio: number
}

export interface FilterPreviewItem {
  filter_name: string
  before: string
  after: string
  chars_removed: number
}

export interface FilterPreviewResponse {
  original: string
  stages: FilterPreviewItem[]
}

// ==================== API ====================
const BASE = '/rag/filters'

export const ragFiltersApi = {
  /** 列出所有可用过滤器 */
  listFilters() {
    return apiClient.get<{ filters: FilterInfo[] }>(`${BASE}/list`)
  },

  /** 应用过滤器链并返回结果 */
  applyFilters(data: FilterApplyRequest) {
    return apiClient.post<FilterApplyResponse>(`${BASE}/apply`, data)
  },

  /** 预览过滤器链的逐级效果 */
  previewFilters(data: FilterApplyRequest) {
    return apiClient.post<FilterPreviewResponse>(`${BASE}/preview`, data)
  },
}
