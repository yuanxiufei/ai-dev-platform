/** 项目 */
export interface Project {
  id: string
  name: string
  description: string
  status: 'draft' | 'building' | 'deploying' | 'running' | 'failed'
  template_id?: string
  created_at: string
  updated_at: string
}

/** 模板 */
export interface Template {
  id: string
  name: string
  description: string
  category: string
  preview_url?: string
  created_at: string
}

/** API 统一响应 */
export interface ApiResponse<T = unknown> {
  message: string
  data?: T
  [key: string]: unknown
}
