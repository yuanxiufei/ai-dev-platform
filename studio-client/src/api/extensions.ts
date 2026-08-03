/**
 * 扩展管理 API — 对标 VSCode 扩展市场与管理
 * 后端: /system/extensions
 */
import { apiClient } from './client'

/* ── 类型 ── */

export interface ExtensionInfo {
  id: string
  name: string
  display_name: string
  description: string
  version: string
  publisher: string
  publisher_display_name: string
  categories: string[]
  tags: string[]
  is_active: boolean
  is_builtin: boolean
  icon_url: string
  installed_at: number
  updated_at: number
  install_count: number
  rating: number
  rating_count: number
}

export interface SearchResult {
  total: number
  items: ExtensionInfo[]
}

export interface ExtensionsApi {
  /** 搜索扩展 (本地 + 模拟市场) */
  search(q?: string, category?: string, page?: number, size?: number): Promise<SearchResult>

  /** 列出已安装的扩展 */
  listInstalled(): Promise<ExtensionInfo[]>

  /** 获取扩展详情 */
  get(extensionId: string): Promise<ExtensionInfo>

  /** 安装扩展 (模拟) */
  install(extensionId: string, version?: string): Promise<ExtensionInfo>

  /** 卸载扩展 */
  uninstall(extensionId: string): Promise<{ ok: boolean }>

  /** 启用扩展 */
  enable(extensionId: string): Promise<{ ok: boolean; is_active: boolean }>

  /** 禁用扩展 */
  disable(extensionId: string): Promise<{ ok: boolean; is_active: boolean }>

  /** 获取扩展市场列表 */
  galleryList(category?: string, sortBy?: string, page?: number, size?: number): Promise<ExtensionInfo[]>
}

/* ── 实现 ── */

const BASE = '/system/extensions'

export const extensionsApi: ExtensionsApi = {
  async search(q = '', category, page = 1, size = 20) {
    const params: Record<string, any> = { q, page, size }
    if (category) params.category = category
    const res = await apiClient.get<SearchResult>(`${BASE}/search`, { params })
    return res.data
  },

  async listInstalled() {
    const res = await apiClient.get<ExtensionInfo[]>(`${BASE}/installed`)
    return res.data
  },

  async get(extensionId) {
    const res = await apiClient.get<ExtensionInfo>(`${BASE}/${extensionId}`)
    return res.data
  },

  async install(extensionId, version = 'latest') {
    const res = await apiClient.post<ExtensionInfo>(`${BASE}/install`, null, {
      params: { extension_id: extensionId, version },
    })
    return res.data
  },

  async uninstall(extensionId) {
    const res = await apiClient.post<{ ok: boolean }>(`${BASE}/${extensionId}/uninstall`)
    return res.data
  },

  async enable(extensionId) {
    const res = await apiClient.post<{ ok: boolean; is_active: boolean }>(
      `${BASE}/${extensionId}/enable`,
    )
    return res.data
  },

  async disable(extensionId) {
    const res = await apiClient.post<{ ok: boolean; is_active: boolean }>(
      `${BASE}/${extensionId}/disable`,
    )
    return res.data
  },

  async galleryList(category, sortBy = 'popular', page = 1, size = 20) {
    const params: Record<string, any> = { sort_by: sortBy, page, size }
    if (category) params.category = category
    const res = await apiClient.get<ExtensionInfo[]>(`${BASE}/gallery/list`, { params })
    return res.data
  },
}
