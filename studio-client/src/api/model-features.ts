import type { ApiPageResponse } from "@/types/studio"
import apiClient from "./client"

// ── Arena 竞技场 (C端) ──────────────────────────────────

export interface ArenaCompareRequest {
  prompt: string
  model_a: string
  model_b: string
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  category?: string
}

export interface ArenaCompareResult {
  comparison_id: string
  prompt: string
  model_a: string
  response_a: string
  latency_a_ms: number | null
  tokens_a: number | null
  model_b: string
  response_b: string
  latency_b_ms: number | null
  tokens_b: number | null
  category: string
}

export interface EloRankingEntry {
  model_name: string
  elo: number
  wins: number
  losses: number
  ties: number
  total_comparisons: number
  category: string | null
}

export const arenaApi = {
  compare: (data: ArenaCompareRequest) =>
    apiClient.post<ArenaCompareResult>("/arena/compare", data),

  vote: (comparisonId: string, winner: "A" | "B" | "tie") =>
    apiClient.post("/arena/vote", { comparison_id: comparisonId, winner }),

  rankings: (category?: string) =>
    apiClient.get<{ rankings: EloRankingEntry[]; category: string | null }>(
      "/arena/rankings",
      { params: { category } },
    ),
}

// ── Memory 长期记忆 (C端) ───────────────────────────────

export interface MemoryEntry {
  id: string
  key: string
  value: string
  domain: string
  importance: number
  access_count: number
  embedding_dim: number | null
  created_at: string
  updated_at: string
}

export interface MemorySearchResult {
  query: string
  results: {
    id: string
    key: string
    value: string
    domain: string
    similarity: number
    importance: number
    score: number
  }[]
}

export const memoryApi = {
  list: (params?: { page?: number; size?: number; domain?: string }) =>
    apiClient.get<ApiPageResponse<MemoryEntry>>("/memory", { params }),

  create: (data: {
    key: string
    value: string
    domain?: string
    importance?: number
  }) => apiClient.post<MemoryEntry>("/memory", data),

  get: (id: string) => apiClient.get<MemoryEntry>(`/memory/${id}`),

  update: (
    id: string,
    data: {
      key?: string
      value?: string
      domain?: string
      importance?: number
    },
  ) => apiClient.put<MemoryEntry>(`/memory/${id}`, data),

  delete: (id: string) => apiClient.delete(`/memory/${id}`),

  search: (query: string, domain?: string, topK?: number) =>
    apiClient.post<MemorySearchResult>("/memory/search", {
      query,
      domain,
      top_k: topK,
    }),

  stats: () =>
    apiClient.get<{
      total_memories: number
      total_accesses: number
      by_domain: Record<string, number>
    }>("/memory/stats"),
}

// ── Memory 关系图 (借鉴 HermesStudio Memory UI) ──────────

export interface MemoryGraphNode {
  id: string
  content: string
  memory_type: string
  importance: number
  access_count: number
  created_at: string
  last_accessed: string
  source: string
  tags: string[]
  metadata: Record<string, unknown>
}

export interface MemoryGraphEdge {
  id: string
  source_id: string
  target_id: string
  relation_type: string
  weight: number
  label: string
}

export interface MemoryGraphData {
  nodes: MemoryGraphNode[]
  edges: MemoryGraphEdge[]
}

export interface MemoryGraphStats {
  total_nodes: number
  total_edges: number
  by_type: Record<string, number>
  avg_importance: number
  top_connected: { id: string; content: string; degree: number }[]
}

export const memoryGraphApi = {
  graphData: (params?: { memory_type?: string; min_importance?: number }) =>
    apiClient.get<MemoryGraphData>("/memory/graph-data", { params }),

  graphStats: () =>
    apiClient.get<MemoryGraphStats>("/memory/graph-stats"),
}

// ── Analytics 分析 (C端) ───────────────────────────────

export interface AnalyticsOverview {
  period_days: number
  total_calls: number
  success_rate: number
  total_tokens: number
  estimated_cost_usd: number
  avg_latency_ms: number
}
export interface ModelStats {
  model_name: string
  provider: string
  calls: number
  total_tokens: number
  avg_latency_ms: number
  total_cost_usd: number
  success_rate: number
}
export interface TrendPoint {
  time: string
  calls: number
  total_tokens: number
}

export const analyticsApi = {
  overview: (days?: number) =>
    apiClient.get<AnalyticsOverview>("/analytics/overview", {
      params: { days },
    }),
  byModel: (days?: number) =>
    apiClient.get<{ models: ModelStats[] }>("/analytics/by-model", {
      params: { days },
    }),
  trends: (days?: number, granularity?: "hour" | "day") =>
    apiClient.get<{ trends: TrendPoint[] }>("/analytics/trends", {
      params: { days, granularity },
    }),
}

// ── Voice 语音 (C端) ───────────────────────────────────

export interface TTSResult {
  audio_base64: string
  duration_seconds: number
  latency_ms: number
}
export interface STTResult {
  text: string
  language: string
  segments: { start: number; end: number; text: string }[]
  latency_ms: number
}
export interface VoiceInfo {
  id: string
  name: string
  locale: string
  gender: string
}

export const voiceApi = {
  tts: (data: { text: string; voice?: string; speed?: number }) =>
    apiClient.post<TTSResult>("/voice/tts", data),
  stt: (file: File) => {
    const form = new FormData()
    form.append("file", file)
    return apiClient.post<STTResult>("/voice/stt", form, {
      headers: { "Content-Type": "multipart/form-data" },
    })
  },
  sttByUrl: (audioUrl: string) =>
    apiClient.post<STTResult>("/voice/stt/url", { audio_url: audioUrl }),
  voices: () =>
    apiClient.get<{ edge_tts: VoiceInfo[]; openai_tts: VoiceInfo[] }>(
      "/voice/voices",
    ),
  status: () =>
    apiClient.get<{ tts_available: boolean; stt_available: boolean }>(
      "/voice/tts/status",
    ),
}

// ── Structured Output 结构化输出 (C端) ──────────────────

export interface GBNFConvertResult {
  gbnf: string
  rules_count: number
  valid: boolean
}
export interface ResponseFormatPreviewResult {
  openai_format: Record<string, unknown>
  gbnf_grammar: string | null
  system_prompt_hint: string
  provider_name: string
}

export const structuredOutputApi = {
  schemaToGbnf: (jsonSchema: Record<string, unknown>) =>
    apiClient.post<GBNFConvertResult>(
      "/structured-output/json-schema-to-gbnf",
      { json_schema: jsonSchema, root_name: "root" },
    ),
  listTemplates: () =>
    apiClient.get<{ templates: Record<string, string> }>(
      "/structured-output/templates",
    ),
  previewResponseFormat: (
    responseFormat: Record<string, unknown>,
    providerName?: string,
  ) =>
    apiClient.post<ResponseFormatPreviewResult>(
      "/structured-output/preview-response-format",
      {
        response_format: responseFormat,
        provider_name: providerName || "openai",
      },
    ),
}

// ── Webhooks (C端) ─────────────────────────────────────

export interface WebhookConfig {
  id: string
  url: string
  name: string
  events: string[]
  is_active: boolean
  max_retries: number
  timeout_seconds: number
  description: string
  success_count: number
  failure_count: number
}
export interface WebhookTestResult {
  success: boolean
  status: number
  error_message: string
  latency_ms: number
}
export interface WebhookDeliveryLog {
  id: string
  webhook_id: string
  event_type: string
  status: number
  success: boolean
  error_message: string
  attempt: number
  sent_at: string
  latency_ms: number
}

export const webhookApi = {
  list: () => apiClient.get<{ webhooks: WebhookConfig[] }>("/webhooks"),
  create: (data: Record<string, unknown>) => apiClient.post("/webhooks", data),
  update: (id: string, data: Record<string, unknown>) =>
    apiClient.put(`/webhooks/${id}`, data),
  delete: (id: string) => apiClient.delete(`/webhooks/${id}`),
  test: (id: string) =>
    apiClient.post<WebhookTestResult>(`/webhooks/${id}/test`),
  logs: (webhookId: string) =>
    apiClient.get<{ logs: WebhookDeliveryLog[] }>("/webhooks/logs", {
      params: { webhook_id: webhookId },
    }),
}

// ── OpenAPI Discovery (C端) ────────────────────────────

export interface OpenAPIServerInfo {
  id: string
  name: string
  url: string
  tool_count: number
}
export interface OpenAPIToolSchema {
  type: string
  function: {
    name: string
    description: string
    parameters: Record<string, unknown>
  }
}

export const openapiDiscoveryApi = {
  servers: () =>
    apiClient.get<{ servers: OpenAPIServerInfo[] }>("/openapi/servers"),
  discover: (specUrl: string, serverName?: string) =>
    apiClient.post("/openapi/discover", {
      spec_url: specUrl,
      server_name: serverName,
    }),
  tools: (serverId?: string) =>
    apiClient.get<{ tools: OpenAPIToolSchema[] }>("/openapi/tools", {
      params: { server_id: serverId },
    }),
  callTool: (toolId: string, args: Record<string, unknown>) =>
    apiClient.post(`/openapi/tools/${toolId}/call`, { arguments: args }),
}

// ── Knowledge Graph (C端) ─────────────────────────────

export interface GraphNode {
  id: string
  label: string
  domain: string
  importance: number
}
export interface GraphEdge {
  from: string
  to: string
}
export interface BacklinkItem {
  target_key: string
  sources: string[]
  source_count: number
}

export const kgApi = {
  graphData: () =>
    apiClient.get<{
      nodes: GraphNode[]
      edges: GraphEdge[]
      node_count: number
      edge_count: number
    }>("/knowledge-graph/graph-data"),
  backlinks: () =>
    apiClient.get<{ backlinks: BacklinkItem[] }>("/knowledge-graph/backlinks"),
  parse: (key: string) =>
    apiClient.get("/knowledge-graph/parse", { params: { key } }),
  stats: () =>
    apiClient.get<{
      total_memories: number
      total_links: number
      most_linked: { key: string; count: number }[]
      domains: Record<string, number>
    }>("/knowledge-graph/stats"),
}

// ── Trajectory 轨迹回放 ────────────────────────────────

export interface TrajectoryFile {
  filename: string
  size_bytes: number
  modified_at: number
}

/** 分页列表项 (来自 /agent/trajectory/list) */
export interface TrajectoryListItem {
  agent_id: string
  session_id: string
  started_at: string
  completed_at: string
  total_steps: number
  total_tool_calls: number
  total_tokens: number
  total_latency_ms: number
  final_model: string
  final_provider: string
  has_error: boolean
  cancelled: boolean
  filename: string
  file_size_bytes: number
}

/** 聚合统计 (来自 /agent/trajectory/stats) */
export interface TrajectoryStats {
  total_runs: number
  success_runs: number
  error_runs: number
  cancelled_runs: number
  success_rate: number
  total_steps: number
  total_tool_calls: number
  total_tokens: number
  total_latency_ms: number
  avg_steps_per_run: number
  avg_tool_calls_per_run: number
  avg_tokens_per_run: number
  top_models: { model: string; count: number }[]
}

export interface TrajectorySummary {
  agent_id: string
  session_id: string
  total_steps: number
  total_time_ms: number
  success: boolean
  error: string
  started_at: string
  final_answer: string
}

export interface TrajectoryStep {
  step: number
  type: string
  action: string
  input: string
  output: string
  elapsed_ms: number
  error: string
  timestamp: string
}

export interface TrajectoryReplay {
  status: string
  summary: TrajectorySummary
  steps: TrajectoryStep[]
  _filename: string
}

export const trajectoryApi = {
  list: (agentId?: string) =>
    apiClient.get<{ status: string; trajectories: TrajectoryFile[] }>(
      "/agent/trajectory/",
      { params: agentId ? { agent_id: agentId } : {} },
    ),
  /** 分页列表 (带筛选) */
  listPaginated: (params?: {
    page?: number; size?: number; status?: string
    model?: string; agent_id?: string; search?: string
  }) =>
    apiClient.get<{
      status: string; data: TrajectoryListItem[]
      total: number; page: number; size: number
    }>("/agent/trajectory/list", { params }),
  /** 聚合统计 */
  stats: () =>
    apiClient.get<{ status: string; stats: TrajectoryStats }>(
      "/agent/trajectory/stats",
    ),
  getAgent: (agentId: string, sessionId?: string, limit?: number) =>
    apiClient.get<{ status: string; trajectories: any[]; total: number }>(
      `/agent/trajectory/${agentId}`,
      { params: { session_id: sessionId, limit } },
    ),
  replay: (agentId: string, sessionId?: string) =>
    apiClient.get<TrajectoryReplay>(
      `/agent/trajectory/${agentId}/replay`,
      { params: { session_id: sessionId } },
    ),
  delete: (agentId: string, sessionId?: string) =>
    apiClient.delete(`/agent/trajectory/${agentId}`, {
      params: { session_id: sessionId },
    }),
}
