import apiClient from './client'

/* ========== 知识库 ========== */

export interface KnowledgeBase {
  kb_id: string
  name: string
  description: string
  stats: { documents: number; chunks: number }
  created_at: string | null
}

export interface KnowledgeBaseDetail extends KnowledgeBase {
  chunk_strategy: string
  chunk_size: number
}

export interface CreateKBRequest {
  name: string
  description?: string
  chunk_strategy?: string
  chunk_size?: number
  chunk_overlap?: number
}

export const listKnowledgeBases = () =>
  apiClient.get<{ data: KnowledgeBase[]; total: number }>('/rag/knowledge-bases')

export const getKnowledgeBase = (kbId: string) =>
  apiClient.get<KnowledgeBaseDetail>(`/rag/knowledge-bases/${kbId}`)

export const createKnowledgeBase = (data: CreateKBRequest) =>
  apiClient.post<KnowledgeBase>(`/rag/knowledge-bases`, data)

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

export const ragHealth = () =>
  apiClient.get<{ status: string; knowledge_bases: number; kb_names: string[]; ready: boolean }>(
    '/rag/health',
  )
