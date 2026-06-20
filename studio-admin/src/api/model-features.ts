import apiClient from './client'
import type { ApiPageResponse } from '@/types/studio'

// ── 模型预设 ────────────────────────────────────────────

export interface ModelPreset {
  id: string
  name: string
  description: string | null
  model_name: string | null
  system_prompt: string | null
  temperature: number | null
  max_tokens: number | null
  top_p: number | null
  tools: string[] | null
  force_tools: boolean
  knowledge_bases: string[] | null
  variables: Record<string, string> | null
  is_public: boolean
  usage_count: number
  created_at: string
  updated_at: string
}

export interface PresetCreate {
  name: string
  description?: string
  model_name?: string
  system_prompt?: string
  temperature?: number
  max_tokens?: number
  top_p?: number
  tools?: string[]
  force_tools?: boolean
  knowledge_bases?: string[]
  variables?: Record<string, string>
  is_public?: boolean
}

export interface PresetResolved {
  preset_id: string
  model_name: string | null
  system_prompt: string
  temperature: number | null
  max_tokens: number | null
  tools: string[]
  knowledge_bases: string[]
  force_tools: boolean
  resolved_variables: Record<string, string>
}

export const presetApi = {
  list: (params?: { page?: number; size?: number; search?: string }) =>
    apiClient.get<ApiPageResponse<ModelPreset>>('/model-presets/presets', { params }),

  get: (id: string) =>
    apiClient.get<ModelPreset>(`/model-presets/presets/${id}`),

  create: (data: PresetCreate) =>
    apiClient.post<ModelPreset>('/model-presets/presets', data),

  update: (id: string, data: Partial<PresetCreate>) =>
    apiClient.put<ModelPreset>(`/model-presets/presets/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/model-presets/presets/${id}`),

  apply: (id: string) =>
    apiClient.post<ModelPreset>(`/model-presets/presets/${id}/apply`),

  resolve: (id: string, context?: Record<string, string>) =>
    apiClient.post<PresetResolved>(`/model-presets/presets/${id}/resolve`, context || {}),
}

// ── Arena 竞技场 ───────────────────────────────────────

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
    apiClient.post<ArenaCompareResult>('/arena/compare', data),

  vote: (comparisonId: string, winner: 'A' | 'B' | 'tie') =>
    apiClient.post('/arena/vote', { comparison_id: comparisonId, winner }),

  rankings: (category?: string) =>
    apiClient.get<{ rankings: EloRankingEntry[]; category: string | null }>('/arena/rankings', { params: { category } }),

  history: (params?: { page?: number; size?: number; category?: string }) =>
    apiClient.get('/arena/history', { params }),
}

// ── Analytics 分析 ──────────────────────────────────────

export interface AnalyticsOverview {
  period_days: number
  total_calls: number
  success_rate: number
  total_prompt_tokens: number
  total_completion_tokens: number
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
    apiClient.get<AnalyticsOverview>('/analytics/overview', { params: { days } }),

  byModel: (days?: number) =>
    apiClient.get<{ models: ModelStats[] }>('/analytics/by-model', { params: { days } }),

  trends: (days?: number, granularity?: 'hour' | 'day') =>
    apiClient.get<{ trends: TrendPoint[] }>('/analytics/trends', { params: { days, granularity } }),

  byCapability: (days?: number) =>
    apiClient.get('/analytics/by-capability', { params: { days } }),
}

// ── Memory 长期记忆 ────────────────────────────────────

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

export interface MemoryStats {
  total_memories: number
  total_accesses: number
  by_domain: Record<string, number>
}

export const memoryApi = {
  list: (params?: { page?: number; size?: number; domain?: string }) =>
    apiClient.get<ApiPageResponse<MemoryEntry>>('/memory', { params }),

  create: (data: { key: string; value: string; domain?: string; importance?: number }) =>
    apiClient.post<MemoryEntry>('/memory', data),

  get: (id: string) =>
    apiClient.get<MemoryEntry>(`/memory/${id}`),

  update: (id: string, data: { key?: string; value?: string; domain?: string; importance?: number }) =>
    apiClient.put<MemoryEntry>(`/memory/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/memory/${id}`),

  search: (query: string, domain?: string, topK?: number, minSimilarity?: number) =>
    apiClient.post<MemorySearchResult>('/memory/search', { query, domain, top_k: topK, min_similarity: minSimilarity }),

  stats: () =>
    apiClient.get<MemoryStats>('/memory/stats'),
}

// ── Structured Output 结构化输出 ─────────────────────────

export interface GBNFConvertResult {
  gbnf: string
  rules_count: number
  valid: boolean
}

export interface GBNFValidateResult {
  valid: boolean
  message: string
}

export interface ResponseFormatPreviewResult {
  openai_format: Record<string, unknown>
  gbnf_grammar: string | null
  system_prompt_hint: string
  provider_name: string
  provider_params: Record<string, unknown>
}

export const structuredOutputApi = {
  schemaToGbnf: (jsonSchema: Record<string, unknown>, rootName?: string) =>
    apiClient.post<GBNFConvertResult>('/structured-output/json-schema-to-gbnf', {
      json_schema: jsonSchema,
      root_name: rootName || 'root',
    }),

  validateGbnf: (gbnfString: string) =>
    apiClient.post<GBNFValidateResult>('/structured-output/validate-gbnf', { gbnf_string: gbnfString }),

  listTemplates: () =>
    apiClient.get<{ templates: Record<string, string> }>('/structured-output/templates'),

  previewResponseFormat: (responseFormat: Record<string, unknown>, providerName?: string) =>
    apiClient.post<ResponseFormatPreviewResult>('/structured-output/preview-response-format', {
      response_format: responseFormat,
      provider_name: providerName || 'openai',
    }),
}

// ── Image Generation 图像生成 ────────────────────────────

export interface ImageSizeOption {
  value: string
  label: string
}

export interface ImageGenResult {
  images: {
    url: string
    b64_json: string
    local_path: string
    revised_prompt: string
    seed: number
    width: number
    height: number
  }[]
  provider_used: string
  latency_ms: number
}

export interface BatchGenResult {
  results: { prompt: string; success: boolean; image?: { url: string; b64_json: string }; error?: string }[]
  total: number
  successful: number
}

export const imageGenApi = {
  providers: () =>
    apiClient.get<{ providers: string[] }>('/image-gen/providers'),

  generate: (data: {
    prompt: string; negative_prompt?: string; size?: string; style?: string
    n?: number; quality?: string; seed?: number; steps?: number
    cfg_scale?: number; engine?: string; model?: string
  }) =>
    apiClient.post<ImageGenResult>('/image-gen/generate', data),

  batchGenerate: (data: { prompts: string[]; size?: string; engine?: string }) =>
    apiClient.post<BatchGenResult>('/image-gen/batch-generate', data),
}

// ── Voice 语音 ──────────────────────────────────────────

export interface TTSResult {
  audio_base64: string
  audio_url: string
  format: string
  duration_seconds: number
  latency_ms: number
}

export interface STTResult {
  text: string
  language: string
  duration_seconds: number
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
  tts: (data: { text: string; voice?: string; format?: string; speed?: number; model?: string }) =>
    apiClient.post<TTSResult>('/voice/tts', data),

  ttsStreamUrl: (text: string, voice?: string, format?: string, speed?: number) => {
    const params = new URLSearchParams({ text, voice: voice || 'nova', format: format || 'mp3', speed: String(speed || 1.0) })
    return `/api/v1/voice/tts/stream?${params}`
  },

  stt: (file: File, language?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (language) form.append('language', language)
    return apiClient.post<STTResult>('/voice/stt', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  sttByUrl: (audioUrl: string, language?: string) =>
    apiClient.post<STTResult>('/voice/stt/url', { audio_url: audioUrl, language: language || '' }),

  voices: () =>
    apiClient.get<{ edge_tts: VoiceInfo[]; openai_tts: VoiceInfo[] }>('/voice/voices'),

  status: () =>
    apiClient.get<{ tts_available: boolean; stt_available: boolean; providers: Record<string, string[]> }>('/voice/tts/status'),
}

// ── Webhooks 事件钩子 ───────────────────────────────────

export interface WebhookConfig {
  id: string
  url: string
  name: string
  events: string[]
  is_active: boolean
  max_retries: number
  timeout_seconds: number
  headers: Record<string, string>
  description: string
  created_at: string
  last_triggered_at: string
  success_count: number
  failure_count: number
}

export interface WebhookCreate {
  url: string
  name: string
  events: string[]
  secret?: string
  max_retries?: number
  timeout_seconds?: number
  headers?: Record<string, string>
  description?: string
  is_active?: boolean
}

export interface WebhookDeliveryLog {
  id: string
  webhook_id: string
  event_type: string
  url: string
  status: number
  success: boolean
  error_message: string
  attempt: number
  sent_at: string
  latency_ms: number
}

export interface WebhookTestResult {
  success: boolean
  status: number
  error_message: string
  latency_ms: number
  delivery: WebhookDeliveryLog
}

export interface WebhookTriggerResult {
  event_type: string
  delivered_to: number
  deliveries: WebhookDeliveryLog[]
}

export const webhookApi = {
  eventTypes: () =>
    apiClient.get<{ event_types: { value: string; name: string; description: string }[] }>('/webhooks/event-types'),

  list: (params?: { event_type?: string; active_only?: boolean }) =>
    apiClient.get<{ webhooks: WebhookConfig[]; total: number }>('/webhooks', { params }),

  create: (data: WebhookCreate) =>
    apiClient.post<WebhookConfig & { id: string }>('/webhooks', data),

  get: (id: string) =>
    apiClient.get<WebhookConfig>(`/webhooks/${id}`),

  update: (id: string, data: Partial<WebhookCreate>) =>
    apiClient.put<WebhookConfig>(`/webhooks/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/webhooks/${id}`),

  test: (id: string) =>
    apiClient.post<WebhookTestResult>(`/webhooks/${id}/test`),

  trigger: (eventType: string, payload?: Record<string, unknown>) =>
    apiClient.post<WebhookTriggerResult>('/webhooks/trigger', { event_type: eventType, payload: payload || {} }),

  logs: (webhookId?: string, limit?: number) =>
    apiClient.get<{ logs: WebhookDeliveryLog[]; total: number }>('/webhooks/logs', { params: { webhook_id: webhookId, limit: limit || 50 } }),
}

// ── Skills 技能指令 ──────────────────────────────────────

export interface SkillInfo {
  name: string
  description: string
  category: string
  content: string
  author: string
  version: string
  tags: string[]
  path: string
  enabled: boolean
  usage_count: number
}

export interface SkillCreate {
  name: string
  description?: string
  category?: string
  content: string
  author?: string
  version?: string
  tags?: string[]
}

export const skillsApi = {
  load: () =>
    apiClient.post<{ message: string; count: number; categories: { name: string; count: number }[] }>('/skills/load'),

  list: (category?: string) =>
    apiClient.get<{ skills: SkillInfo[]; count: number }>('/skills', { params: { category } }),

  categories: () =>
    apiClient.get<{ categories: { name: string; count: number }[] }>('/skills/categories'),

  create: (data: SkillCreate) =>
    apiClient.post<{ skill: SkillInfo; path: string }>('/skills', data),

  parseMarkdown: (markdown: string) =>
    apiClient.post<{ skill: SkillInfo }>('/skills/parse-markdown', { markdown }),

  get: (name: string) =>
    apiClient.get<{ skill: SkillInfo }>(`/skills/${name}`),

  update: (name: string, data: SkillCreate) =>
    apiClient.put<{ skill: SkillInfo }>(`/skills/${name}`, data),

  delete: (name: string) =>
    apiClient.delete(`/skills/${name}`),

  toggle: (name: string) =>
    apiClient.post<{ name: string; enabled: boolean }>(`/skills/${name}/toggle`),

  apply: (skills: string[]) =>
    apiClient.post<{ system_prompt: string; skills_applied: number }>('/skills/apply', { skills }),
}

// ── Prompt Templates 模板 ─────────────────────────────

export interface TemplateVariableDef {
  type: string
  default: string | number | boolean
  description: string
  required: boolean
  options: string[]
}

export interface PromptTemplateData {
  id: string
  command: string
  title: string
  prompt: string
  variables: Record<string, TemplateVariableDef>
  category: string
  version: string
  author: string
  tags: string[]
  is_public: boolean
  description: string
  icon: string
  created_at: string
  updated_at: string
  usage_count: number
}

export interface CommandSearchResult {
  id: string
  command: string
  title: string
  category: string
  icon: string
  variable_names: string[]
}

export const promptTemplateApi = {
  list: (category?: string, search?: string) =>
    apiClient.get<{ templates: PromptTemplateData[]; count: number }>('/prompt-templates', { params: { category, search } }),

  categories: () =>
    apiClient.get<{ categories: { name: string; count: number }[] }>('/prompt-templates/categories'),

  search: (q: string) =>
    apiClient.get<{ commands: CommandSearchResult[] }>('/prompt-templates/search', { params: { q } }),

  create: (data: {
    command: string; title: string; prompt: string
    variables?: Record<string, TemplateVariableDef>
    category?: string; description?: string; icon?: string; tags?: string[]
  }) =>
    apiClient.post<{ template: PromptTemplateData }>('/prompt-templates', data),

  get: (id: string) =>
    apiClient.get<{ template: PromptTemplateData; variable_names: string[] }>(`/prompt-templates/${id}`),

  update: (id: string, data: Partial<PromptTemplateData>) =>
    apiClient.put<{ template: PromptTemplateData }>(`/prompt-templates/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/prompt-templates/${id}`),

  resolve: (id: string, values: Record<string, string | number | boolean>) =>
    apiClient.post<{ template_id: string; command: string; resolved_prompt: string }>(`/prompt-templates/${id}/resolve`, { values }),
}

// ── Task Management 任务管理 ────────────────────────

export interface TaskStepData {
  id: string
  title: string
  description: string
  status: 'todo' | 'in_progress' | 'blocked' | 'completed' | 'cancelled'
  order: number
  result: string
  started_at: string
  completed_at: string
}

export interface TaskData {
  id: string
  title: string
  description: string
  status: string
  priority: string
  category: string
  tags: string[]
  steps: TaskStepData[]
  assigned_model: string
  parent_id: string
  progress: number
  result_summary: string
  created_at: string
  updated_at: string
  started_at: string
  completed_at: string
  due_date: string
}

export interface TaskTreeData extends TaskData {
  children: TaskTreeData[]
}

export const tasksApi = {
  list: (params?: Record<string, string | number>) =>
    apiClient.get<{ data: TaskData[]; total: number; page: number; size: number }>('/tasks', { params }),

  categories: () =>
    apiClient.get<{ categories: { name: string; count: number }[] }>('/tasks/categories'),

  create: (data: {
    title: string; description?: string; priority?: string; category?: string
    steps?: TaskStepData[]; assigned_model?: string; parent_id?: string; due_date?: string
  }) =>
    apiClient.post<{ task: TaskData }>('/tasks', data),

  autoGenerate: (title: string, description?: string, category?: string, stepCount?: number) =>
    apiClient.post<{ task: TaskData; steps_generated: number }>('/tasks/auto-generate', {
      title, description, category, step_count: stepCount || 3,
    }),

  get: (id: string) =>
    apiClient.get<{ task: TaskData }>(`/tasks/${id}`),

  getTree: (id: string) =>
    apiClient.get<{ task: TaskTreeData }>(`/tasks/${id}/tree`),

  update: (id: string, data: Partial<TaskData>) =>
    apiClient.put<{ task: TaskData }>(`/tasks/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/tasks/${id}`),

  updateStep: (taskId: string, stepId: string, data: Record<string, unknown>) =>
    apiClient.put<{ step: TaskStepData; task_progress: number }>(`/tasks/${taskId}/steps/${stepId}`, data),

  start: (id: string) =>
    apiClient.post<{ task: TaskData; next_step: TaskStepData | null; message: string }>(`/tasks/${id}/start`),
}

// ── OpenAPI Discovery ─────────────────────────────

export interface OpenAPIServerInfo {
  id: string
  name: string
  url: string
  description: string
  tools: unknown[]
  spec_url: string
  is_active: boolean
  last_synced_at: string
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
    apiClient.get<{ servers: OpenAPIServerInfo[]; count: number }>('/openapi/servers'),

  discover: (specUrl: string, serverName?: string, headers?: Record<string, string>) =>
    apiClient.post<{ server: OpenAPIServerInfo; tool_count: number; message: string }>('/openapi/discover', {
      spec_url: specUrl, server_name: serverName, headers: headers || {},
    }),

  getServer: (id: string) =>
    apiClient.get<{ server: OpenAPIServerInfo }>(`/openapi/servers/${id}`),

  deleteServer: (id: string) =>
    apiClient.delete(`/openapi/servers/${id}`),

  tools: (serverId?: string) =>
    apiClient.get<{ tools: OpenAPIToolSchema[]; count: number }>('/openapi/tools', { params: { server_id: serverId } }),

  toolSchemas: (serverId?: string) =>
    apiClient.get<{ schemas: OpenAPIToolSchema[]; count: number }>('/openapi/tools/schemas', { params: { server_id: serverId } }),

  callTool: (toolId: string, args: Record<string, unknown>) =>
    apiClient.post<{ tool_id: string; tool_name: string; result: unknown }>(`/openapi/tools/${toolId}/call`, { arguments: args }),
}

// ── Knowledge Graph 知识图谱 ─────────────────────────────

export interface BacklinkItem {
  target_key: string
  sources: string[]
  source_count: number
}

export interface GraphNode {
  id: string
  label: string
  domain: string
  importance: number
  access_count: number
}

export interface GraphEdge {
  from: string
  to: string
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  node_count: number
  edge_count: number
}

export interface ParseResult {
  key: string
  value: string
  domain: string
  wikilinks: { target: string; display: string; heading: string; block_id: string }[]
  wikilink_count: number
  frontmatter: {
    title: string
    tags: string[]
    aliases: string[]
    status: string
    priority: string
    due_date: string
    created: string
    updated: string
    extra: Record<string, string>
  }
  callouts: { type: string; title: string; content: string; folded_default: boolean }[]
  callout_count: number
  tags: string[]
  plain_text: string
}

export interface CanvasDownload {
  filename: string
  content_type: string
  content: string
  spec: string
}

export interface GraphStats {
  total_memories: number
  total_links: number
  total_backlinks: number
  most_linked: { key: string; count: number }[]
  orphans: number
  orphan_keys: string[]
  domains: Record<string, number>
  graph_density: number
}

export const kgApi = {
  backlinks: () =>
    apiClient.get<{ backlinks: BacklinkItem[]; total: number }>('/knowledge-graph/backlinks'),

  links: (key: string) =>
    apiClient.get<{ key: string; forward_links: string[]; forward_count: number; backlinks: string[]; backlink_count: number }>(`/knowledge-graph/links/${key}`),

  parse: (key: string) =>
    apiClient.get<ParseResult>('/knowledge-graph/parse', { params: { key } }),

  graphData: () =>
    apiClient.get<GraphData>('/knowledge-graph/graph-data'),

  canvas: (includeCallouts?: boolean) =>
    apiClient.get<{ canvas: { nodes: unknown[]; edges: unknown[] }; node_count: number; edge_count: number }>('/knowledge-graph/canvas', { params: { include_callouts: includeCallouts ?? true } }),

  downloadCanvas: (includeCallouts?: boolean) =>
    apiClient.get<CanvasDownload>('/knowledge-graph/canvas/download', { params: { include_callouts: includeCallouts ?? true } }),

  domainCanvas: (domain: string) =>
    apiClient.get<{ domain: string; canvas: { nodes: unknown[]; edges: unknown[] }; node_count: number; edge_count: number }>(`/knowledge-graph/canvas/domain/${domain}`),

  stats: () =>
    apiClient.get<GraphStats>('/knowledge-graph/stats'),

  orphans: () =>
    apiClient.get<{ orphans: string[]; count: number; total: number }>('/knowledge-graph/orphans'),
}
