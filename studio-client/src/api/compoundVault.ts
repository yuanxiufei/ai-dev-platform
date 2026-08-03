import { apiClient } from './client'

// ==================== 请求类型 ====================
export interface DocumentIngest {
  path: string
  content: string
  title?: string
  generate_prefixes?: boolean
}

export interface BatchIngest {
  documents: DocumentIngest[]
}

export interface CompoundSearchRequest {
  query: string
  top_k?: number
  use_bm25?: boolean
  use_dense?: boolean
}

export interface HotCacheAdd {
  key: string
  summary: string
  importance?: number
  promote_to_long?: boolean
}

// ==================== 响应类型 ====================
export interface IngestResult {
  path: string
  title: string
  chunk_count: number
  prefix_tier: string
  indexed: boolean
}

export interface BatchIngestResult {
  documents: number
  total_chunks: number
  results: IngestResult[]
}

export interface SearchResultItem {
  chunk_id: string
  score: number
  source: 'bm25' | 'dense'
  path: string
}

export interface SearchResult {
  query: string
  results: SearchResultItem[]
  total: number
}

export interface BM25Stats {
  ok: boolean
  doc_count?: number
  vocab_size?: number
  avg_dl?: number
  index_path?: string
  schema_version?: number
  reason?: string
}

export interface HotCacheEntry {
  key: string
  summary: string
  importance: number
  access_count: number
  created_at: string
  last_accessed_at?: string
}

export interface HotCacheAddResult {
  ok: boolean
  entry: HotCacheEntry
}

export interface HotCacheContext {
  context: string
  stats: { hot_count: number; long_count: number; total_accesses: number }
}

export interface HotCacheStats {
  hot_count: number
  long_count: number
  total_accesses: number
}

export interface EmbedCacheStats {
  ok: boolean
  mem_size?: number
  mem_max?: number
  disk_size?: number
  disk_path?: string
  reason?: string
}

export interface CompoundStats {
  bm25: BM25Stats
  hot_cache: HotCacheStats
  embed_cache: EmbedCacheStats
}

// ==================== API ====================
const BASE = '/compound'

export const compoundVaultApi = {
  // --- 摄入 ---
  ingest(doc: DocumentIngest) {
    return apiClient.post<IngestResult>(`${BASE}/ingest`, doc)
  },
  ingestBatch(data: BatchIngest) {
    return apiClient.post<BatchIngestResult>(`${BASE}/ingest/batch`, data)
  },

  // --- 检索 ---
  search(req: CompoundSearchRequest) {
    return apiClient.post<SearchResult>(`${BASE}/search`, req)
  },

  // --- BM25 ---
  rebuildBM25() {
    return apiClient.post(`${BASE}/bm25/rebuild`)
  },
  getBM25Stats() {
    return apiClient.get<BM25Stats>(`${BASE}/bm25/stats`)
  },

  // --- 热缓存 ---
  addHotCache(data: HotCacheAdd) {
    return apiClient.post<HotCacheAddResult>(`${BASE}/hot-cache`, data)
  },
  getHotCacheContext(maxChars?: number) {
    return apiClient.get<HotCacheContext>(`${BASE}/hot-cache/context`, {
      params: maxChars ? { max_chars: maxChars } : {},
    })
  },
  clearSessionHotCache() {
    return apiClient.delete(`${BASE}/hot-cache/session`)
  },
  deleteHotCacheEntry(key: string) {
    return apiClient.delete(`${BASE}/hot-cache/${encodeURIComponent(key)}`)
  },
  promoteHotCacheEntry(key: string) {
    return apiClient.post(`${BASE}/hot-cache/${encodeURIComponent(key)}/promote`)
  },
  getHotCacheStats() {
    return apiClient.get<HotCacheStats>(`${BASE}/hot-cache/stats`)
  },

  // --- 前缀缓存 ---
  clearPrefixes(path?: string) {
    return apiClient.delete(`${BASE}/prefixes`, { params: path ? { path } : {} })
  },

  // --- 嵌入缓存 ---
  getEmbedCacheStats() {
    return apiClient.get<EmbedCacheStats>(`${BASE}/embed-cache/stats`)
  },
  clearEmbedCache() {
    return apiClient.delete(`${BASE}/embed-cache`)
  },

  // --- 整体统计 ---
  getStats() {
    return apiClient.get<CompoundStats>(`${BASE}/stats`)
  },
}
