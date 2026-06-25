import apiClient from "./client"
import type { ApiPageResponse } from "./studio"

// ── 类型定义 ────────────────────────────────────────────

export interface PluginRegistryItem {
  name: string
  display_name: string
  author: string
  version: string
  desc: string
  repo: string
  type: "mcp" | "awp" | "skill" | "command" | "hook"
  category: string
  tags: string[]
  download_url: string
  installs: number
  rating: number
  config_schema: Record<string, unknown>
  source_id?: string
  installed: boolean
  installed_version?: string | null
  installed_enabled?: boolean
  installed_config?: Record<string, unknown> | null
}

export interface PluginRegistryResponse
  extends ApiPageResponse<PluginRegistryItem> {
  categories: string[]
  types: string[]
}

// ── 市场源 ──────────────────────────────────────────────

export interface MarketplaceSource {
  id: string
  name: string
  type: "builtin" | "github" | "zip" | "local"
  url: string
  description: string
  enabled: boolean
  plugin_count: number
  created_at: string
}

export interface MarketplaceSourcesResponse {
  sources: MarketplaceSource[]
  total: number
  enabled_count: number
}

// ── 市场统计 ────────────────────────────────────────────

export interface MarketplaceStats {
  total_plugins: number
  total_installed: number
  enabled_installed: number
  type_counts: Record<string, number>
  category_counts: Record<string, number>
  sources_count: number
  enabled_sources_count: number
}

// ── API 方法：插件注册表 ─────────────────────────────────

export async function getPluginRegistry(params?: {
  search?: string
  category?: string
  plugin_type?: string
  source_id?: string
  page?: number
  size?: number
}): Promise<PluginRegistryResponse> {
  const { data } = await apiClient.get("/plugin-marketplace/registry", {
    params,
  })
  return data
}

export async function getCategories(): Promise<{
  categories: { name: string; count: number }[]
}> {
  const { data } = await apiClient.get(
    "/plugin-marketplace/registry/categories",
  )
  return data
}

export async function getPluginDetail(
  name: string,
): Promise<PluginRegistryItem> {
  const { data } = await apiClient.get(`/plugin-marketplace/registry/${name}`)
  return data
}

export async function installPlugin(
  name: string,
  version?: string,
): Promise<{
  success: boolean
  plugin: string
  version: string
  path: string
  message: string
}> {
  const { data } = await apiClient.post("/plugin-marketplace/install", {
    name,
    version: version || "latest",
  })
  return data
}

export async function uninstallPlugin(
  name: string,
): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.delete(`/plugin-marketplace/install/${name}`)
  return data
}

// ── API 方法：已安装管理 ─────────────────────────────────

export async function getInstalledPlugins(): Promise<PluginRegistryItem[]> {
  const { data } = await apiClient.get("/plugin-marketplace/installed")
  return (data as any).data || data || []
}

export async function togglePlugin(
  name: string,
): Promise<{ name: string; enabled: boolean }> {
  const { data } = await apiClient.post(
    `/plugin-marketplace/installed/${name}/toggle`,
  )
  return data
}

export async function updatePluginConfig(
  name: string,
  config: Record<string, unknown>,
): Promise<{ name: string; config: Record<string, unknown> }> {
  const { data } = await apiClient.put(
    `/plugin-marketplace/installed/${name}/config`,
    { config },
  )
  return data
}

// ── API 方法：市场源管理 ─────────────────────────────────

export async function getMarketplaceSources(): Promise<MarketplaceSourcesResponse> {
  const { data } = await apiClient.get("/plugin-marketplace/sources")
  return data
}

export async function addMarketplaceSource(source: {
  name: string
  type: string
  url: string
  description: string
}): Promise<{ success: boolean; source: MarketplaceSource; message: string }> {
  const { data } = await apiClient.post("/plugin-marketplace/sources", source)
  return data
}

export async function removeMarketplaceSource(
  sourceId: string,
): Promise<{ success: boolean; message: string }> {
  const { data } = await apiClient.delete(
    `/plugin-marketplace/sources/${sourceId}`,
  )
  return data
}

export async function toggleMarketplaceSource(sourceId: string): Promise<{
  success: boolean
  source_id: string
  enabled: boolean
  message: string
}> {
  const { data } = await apiClient.post(
    `/plugin-marketplace/sources/${sourceId}/toggle`,
  )
  return data
}

// ── API 方法：统计 ───────────────────────────────────────

export async function getMarketplaceStats(): Promise<MarketplaceStats> {
  const { data } = await apiClient.get("/plugin-marketplace/stats")
  return data
}
