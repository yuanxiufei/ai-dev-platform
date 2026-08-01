import apiClient from './client'

/* ========== 知识库 ========== */

export interface KnowledgeBase {
  kb_id: string
  name: string
  description: string
  summary: string
  document_count?: number
  chunk_count?: number
  chunk_size?: number
  chunk_overlap?: number
  chunk_strategy?: string
  stats?: { documents: number; chunks: number }
  created_at: string | null
}

/** 知识库中已上传的文档（与后端 KBDocument 一致） */
export interface KBDocument {
  doc_id: string
  doc_name: string
  file_type: string
  file_size: number
  chunk_count: number
  media_count: number
  embedding_status?: string   // pending | embedding | completed | failed
  embedded_at?: string | null  // ISO 时间戳
  created_at: string
}

export interface CreateKBRequest {
  name: string
  description?: string
  summary?: string
  chunk_strategy?: string
  chunk_size?: number
  chunk_overlap?: number
}

export const listKnowledgeBases = () =>
  apiClient.get<{ data: KnowledgeBase[]; total: number }>('/rag/knowledge-bases')

export const getKnowledgeBase = (kbId: string) =>
  apiClient.get<KnowledgeBase>(`/rag/knowledge-bases/${kbId}`)

export const createKnowledgeBase = (data: CreateKBRequest) =>
  apiClient.post<KnowledgeBase>(`/rag/knowledge-bases`, data, { timeout: 180000 })

export const updateKnowledgeBase = (kbId: string, data: Partial<CreateKBRequest>) =>
  apiClient.put<KnowledgeBase>(`/rag/knowledge-bases/${kbId}`, data)

export const deleteKnowledgeBase = (kbId: string) =>
  apiClient.delete(`/rag/knowledge-bases/${kbId}`)

export const uploadDocument = (
  kbId: string,
  payload: { file?: File; text?: string; title?: string; url?: string },
) => {
  const form = new FormData()
  if (payload.file) form.append('file', payload.file)
  if (payload.text) form.append('text', payload.text)
  if (payload.title) form.append('title', payload.title)
  if (payload.url) form.append('url', payload.url)
  return apiClient.post<{ status: string; kb_id: string; chunks: number }>(
    `/rag/knowledge-bases/${kbId}/documents`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } },
  )
}

/* ========== RAG 查询 ========== */

export interface RAGQueryResponse {
  answer: string
  sources: { content: string; score: number; source: string; kb_name: string }[]
  context: string
  original_chunks: number
  final_chunks: number
  compressed: boolean
}

export interface RAGSearchResult {
  content: string
  score: number
  source: string
  kb_name: string
  chunk_index: number
}

export const ragQuery = (question: string, kbIds?: string[], topK?: number) =>
  apiClient.post<RAGQueryResponse>('/rag/query', {
    question,
    kb_ids: kbIds || null,
    top_k: topK || 5,
    include_sources: true,
  })

export const ragSearch = (query: string, kbIds?: string[], topK?: number) =>
  apiClient.post<{ data: RAGSearchResult[]; total: number }>('/rag/search', {
    query,
    kb_ids: kbIds || null,
    top_k: topK || 10,
  })

/* ========== 批量上传 ========== */

export const batchUploadDocuments = (kbId: string, files: File[]) => {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  return apiClient.post<{
    kb_id: string
    results: { filename: string; chunks: number; status: string; error?: string }[]
  }>(`/rag/knowledge-bases/${kbId}/documents/batch`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

/* ========== 文档管理 ========== */

export const listDocuments = (kbId: string, skip?: number, limit?: number) =>
  apiClient.get<{ data: KBDocument[]; total: number; page: number; size: number }>(
    `/rag/knowledge-bases/${kbId}/documents`,
    { params: { skip: skip ?? 0, limit: limit ?? 50 } },
  )

export const deleteDocument = (kbId: string, docId: string) =>
  apiClient.delete<{ detail: string; message: string }>(
    `/rag/knowledge-bases/${kbId}/documents/${docId}`,
  )

/* ========== 整站导入 ========== */

export interface SiteImportRequest {
  sitemap_url?: string
  urls?: string[]
  max_pages?: number
  max_concurrent?: number
}

export interface SiteImportResponse {
  status: string
  kb_id: string
  total_found?: number
  crawled_ok?: number
  crawled_fail?: number
  imported?: number
  import_errors?: string[]
  crawl_errors?: string[]
  base_domain?: string
  message?: string
}

export const importFromSite = (kbId: string, body: SiteImportRequest) =>
  apiClient.post<SiteImportResponse>(
    `/rag/knowledge-bases/${kbId}/documents/import-from-site`,
    body,
    { timeout: 600000 }, // 10min — 整站抓取+导入可能耗时较长
  )

/* ========== Dify 知识桥接 ========== */

export interface DifyImportRequest {
  kb_name: string
  kb_description?: string
  doc_dir?: string
  chunk_size?: number
  chunk_overlap?: number
}

export interface DifyImportResponse {
  kb_name: string
  total_documents: number
  total_chunks: number
  total_embedded: number
  errors: string[]
  duration_sec: number
}

export const importFromDify = (body: DifyImportRequest) =>
  apiClient.post<DifyImportResponse>('/rag/knowledge-bases/import-from-dify', body)

/* ========== Dify Webhook 同步 ========== */

export interface DifyWebhookRequest {
  kb_name: string
  kb_description?: string
  doc_dir?: string
  chunk_size?: number
  chunk_overlap?: number
  mode?: 'replace' | 'append'
  secret?: string
}

export const difyWebhook = (body: DifyWebhookRequest) =>
  apiClient.post<DifyImportResponse & { status: string }>(
    '/rag/knowledge-bases/dify-webhook',
    body,
  )

export const ragHealth = () =>
  apiClient.get<{ status: string; knowledge_bases: number; kb_names: string[]; ready: boolean }>(
    '/rag/health',
  )

/* ========== Retrain ========== */

export interface RetrainResponse {
  kb_id: string
  total: number
  success: number
  failed: number
  errors: string[]
}

/** 重新训练知识库中所有文档（HTTP 同步） */
export const retrainKb = (kbId: string) =>
  apiClient.post<RetrainResponse>(`/rag/knowledge-bases/${kbId}/retrain`)

/* ========== Chunk 管理 ========== */

export interface ChunkItem {
  doc_id: string    // HybridStorage 内部 _doc_id
  content: string
  metadata: Record<string, unknown>
}

export const listChunks = (
  kbId: string,
  docId?: string,
  page?: number,
  size?: number,
) =>
  apiClient.get<{ data: ChunkItem[]; total: number; page: number; size: number }>(
    `/rag/knowledge-bases/${kbId}/chunks`,
    { params: { doc_id: docId, page: page ?? 1, size: size ?? 50 } },
  )

export const deleteChunks = (kbId: string, chunkIds: string[]) =>
  apiClient.delete<{ total: number; deleted: number }>(
    `/rag/knowledge-bases/${kbId}/chunks`,
    { data: { chunk_ids: chunkIds } },
  )

/* ========== Job 管理 ========== */

export interface KBJob {
  job_id: string
  job_type: string
  status: string  // pending | running | completed | failed
  progress: number
  payload_json: string | null
  result_json: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export const createJob = (kbId: string, jobType: string, payload?: Record<string, unknown>) =>
  apiClient.post<KBJob>(`/rag/knowledge-bases/${kbId}/jobs`, {
    job_type: jobType,
    payload: payload ?? {},
  })

export const listJobs = (kbId: string, page?: number, size?: number) =>
  apiClient.get<{ data: KBJob[]; total: number; page: number; size: number }>(
    `/rag/knowledge-bases/${kbId}/jobs`,
    { params: { page: page ?? 1, size: size ?? 100 } },
  )
