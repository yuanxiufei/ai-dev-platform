/**
 * 记忆 API 模块 — 长期向量化记忆管理
 * 对应后端: /memory
 */

import { apiClient } from "./client"

/* ── 类型 ────────────────────────────────────── */

export interface MemoryEntry {
  id: string
  key: string
  value: string
  domain: string
  importance: number
  access_count: number
  embedding_dim: number | null
  created_at: string | null
  updated_at: string | null
}

export interface MemoryCreate {
  key: string
  value: string
  domain?: string
  importance?: number
}

export interface MemoryUpdate {
  key?: string
  value?: string
  domain?: string
  importance?: number
}

export interface MemorySearchRequest {
  query: string
  domain?: string
  top_k?: number
  min_similarity?: number
}

export interface MemorySearchResult {
  id: string
  key: string
  value: string
  domain: string
  similarity: number
  importance: number
  score: number
}

export interface MemorySearchResponse {
  query: string
  results: MemorySearchResult[]
}

export interface PaginatedMemories {
  data: MemoryEntry[]
  total: number
  page: number
  size: number
}

export interface MemoryStats {
  total_memories: number
  total_accesses: number
  by_domain: Record<string, number>
}

/* ── 端点 ────────────────────────────────────── */

/** 分页列出记忆 */
export function listMemories(params?: { page?: number; size?: number; domain?: string }) {
  return apiClient.get<PaginatedMemories>("/memory/memory", { params })
}

/** 创建记忆 */
export function createMemory(data: MemoryCreate) {
  return apiClient.post<MemoryEntry>("/memory/memory", data)
}

/** 获取单条记忆 */
export function getMemory(memoryId: string) {
  return apiClient.get<MemoryEntry>(`/memory/memory/${memoryId}`)
}

/** 更新记忆 */
export function updateMemory(memoryId: string, data: MemoryUpdate) {
  return apiClient.put<MemoryEntry>(`/memory/memory/${memoryId}`, data)
}

/** 删除记忆 */
export function deleteMemory(memoryId: string) {
  return apiClient.delete<{ ok: boolean; message: string }>(`/memory/memory/${memoryId}`)
}

/** 语义检索记忆 */
export function searchMemories(data: MemorySearchRequest) {
  return apiClient.post<MemorySearchResponse>("/memory/memory/search", data)
}

/** 记忆统计 */
export function memoryStats() {
  return apiClient.get<MemoryStats>("/memory/memory/stats")
}
