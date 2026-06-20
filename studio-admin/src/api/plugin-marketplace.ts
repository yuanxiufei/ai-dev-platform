import apiClient from './client'
import type { ApiPageResponse } from './studio'

// ── 类型定义 ────────────────────────────────────────────

export interface PluginRegistryItem {
  name: string
  display_name: string
  author: string
  version: string
  desc: string
  repo: string
  type: 'mcp' | 'awp'
  category: string
  tags: string[]
  download_url: string
  installs: number
  rating: number
  config_schema: Record<string, unknown>
  installed: boolean
  installed_version?: string | null
  installed_enabled?: boolean
  installed_config?: Record<string, unknown> | null
}

export interface PluginInstalled {
  name: string
  display_name: string
  version: string
  author: string
  desc: string
  type: 'mcp' | 'awp'
  installed_at: string
  config: Record<string, unknown>
  enabled: boolean
  registry_info?: PluginRegistryItem | null
}

export interface PluginInstallResult {
  success: boolean
  plugin: string
  version: string
  path: string
  message: string
}

export interface PluginRegistryResponse extends ApiPageResponse<PluginRegistryItem> {
  categories: string[]
  types: string[]
}

// ── API 方法 ────────────────────────────────────────────

export async function getPluginRegistry(params?: {
  search?: string
  category?: string
  plugin_type?: string
  page?: number
  size?: number
}): Promise<PluginRegistryResponse> {
  const { data } = await apiClient.get('/plugin-marketplace/registry', { params })
  return data
}

export async function getCategories(): Promise<{ categories: { name: string; count: number }[] }> {
  const { data } = await apiClient.get('/plugin-marketplace/registry/categories')
  return data
}

export async function getPluginDetail(name: string): Promise<PluginRegistryItem> {
  const { data } = await apiClient.get(`/plugin-marketplace/registry/${name}`)
  return data
}

export async function installPlugin(name: string, version?: string): Promise<PluginInstallResult> {
  const { data } = await apiClient.post('/plugin-marketplace/install', { name, version: version || 'latest' })
  return data
}

export async function uninstallPlugin(name: string): Promise<{ success: boolean; plugin: string; message: string }> {
  const { data } = await apiClient.delete(`/plugin-marketplace/install/${name}`)
  return data
}

export async function getInstalledPlugins(): Promise<{ data: PluginInstalled[]; total: number }> {
  const { data } = await apiClient.get('/plugin-marketplace/installed')
  return data
}

export async function updatePluginConfig(name: string, config: Record<string, unknown>): Promise<{ success: boolean; plugin: string; config: Record<string, unknown> }> {
  const { data } = await apiClient.put(`/plugin-marketplace/installed/${name}/config`, { config })
  return data
}

export async function togglePlugin(name: string): Promise<{ success: boolean; plugin: string; enabled: boolean }> {
  const { data } = await apiClient.post(`/plugin-marketplace/installed/${name}/toggle`)
  return data
}
