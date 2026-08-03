/**
 * Notebook Kernel API — 多语言代码单元执行
 * 后端: /system/notebook
 */
import { apiClient } from './client'

/* ── 类型 ── */

export interface KernelInfo {
  id: string
  name: string
  language: string
  available: boolean
  version: string
  description: string
}

export interface CellExecuteRequest {
  code: string
  kernel?: string
  cell_id?: string
  timeout?: number
  working_dir?: string
  env_vars?: Record<string, string>
}

export interface CellExecuteResponse {
  cell_id: string
  success: boolean
  output: string
  error: string
  duration_ms: number
  kernel: string
}

export interface BatchExecuteRequest {
  cells: CellExecuteRequest[]
}

export interface BatchExecuteResponse {
  results: CellExecuteResponse[]
  total_duration_ms: number
}

export interface SanitizeRequest {
  content: string
  max_length?: number
}

export interface SanitizeResponse {
  content: string
  original_length: number
  truncated: boolean
}

export interface NotebookApi {
  /** 列出所有可用 Kernel */
  listKernels(): Promise<KernelInfo[]>

  /** 执行单个 Cell */
  executeCell(req: CellExecuteRequest): Promise<CellExecuteResponse>

  /** 批量执行 Cell */
  executeBatch(req: BatchExecuteRequest): Promise<BatchExecuteResponse>

  /** 清理输出中的敏感信息 */
  sanitizeOutput(content: string, maxLength?: number): Promise<SanitizeResponse>
}

/* ── 实现 ── */

const BASE = '/system/notebook'

export const notebookApi: NotebookApi = {
  async listKernels() {
    const res = await apiClient.get<{ kernels: KernelInfo[] }>(`${BASE}/kernels`)
    return res.data.kernels
  },

  async executeCell(req) {
    const res = await apiClient.post<CellExecuteResponse>(`${BASE}/execute`, req)
    return res.data
  },

  async executeBatch(req) {
    const res = await apiClient.post<BatchExecuteResponse>(`${BASE}/execute-batch`, req)
    return res.data
  },

  async sanitizeOutput(content, maxLength) {
    const res = await apiClient.post<SanitizeResponse>(`${BASE}/sanitize`, {
      content,
      max_length: maxLength,
    })
    return res.data
  },
}
