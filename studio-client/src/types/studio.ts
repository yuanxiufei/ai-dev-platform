export interface Project {
  id: string
  name: string
  description?: string
  status: "draft" | "building" | "deploying" | "running" | "failed"
  created_at: string
  updated_at?: string
}

export interface Template {
  id: string
  name: string
  description?: string
  category?: string
  thumbnail_url?: string
}

// ═══════════════════════════════════════
// Agent 对话消息 — 增强版 (参考 Continue/Cline)
// ═══════════════════════════════════════
export interface ChatMessage {
  id: string
  role: "user" | "assistant" | "tool" | "system"
  content: string
  tool_calls?: ToolCallRecord[]
  /** 推理步骤 (Cline/RooCode 参考) */
  reasoning_steps?: ReasoningStep[]
  /** 编排管线阶段 (LangGraph/AutoGen 参考) */
  pipeline_stages?: PipelineStage[]
  /** 引用的文件 (Continue @-mention 参考) */
  referenced_files?: ReferencedFile[]
  metadata?: Record<string, unknown>
  timestamp: string
}

export interface ToolCallRecord {
  id: string
  name: string
  arguments: Record<string, unknown>
  result?: string
  success?: boolean
  /** 是否需要审批 (Open Interpreter 参考) */
  requires_approval?: boolean
  /** 审批状态 */
  approval_status?: "pending" | "approved" | "rejected"
  /** 安全级别 */
  security_level?: "READ_ONLY" | "FILE_CREATE" | "FILE_MODIFY" | "SYSTEM" | "UNSAFE"
  /** 执行耗时 (ms) */
  latency_ms?: number
  /** 工具类别 */
  category?: string
}

/** 推理步骤 (Cline 风格 step-by-step reasoning) */
export interface ReasoningStep {
  id: string
  type: "thinking" | "planning" | "analyzing" | "deciding" | "executing"
  content: string
  status: "pending" | "in_progress" | "completed" | "error"
  timestamp?: string
  /** Cline 风格: 该步骤耗时 (ms) */
  elapsed_ms?: number
  /** Cline 风格: 该步骤引用的文件/符号 */
  references?: string[]
  /** Cline 风格: 错误详情 (当 status=error 时) */
  error_detail?: string
}

/** 编排管线阶段 (LangGraph/AutoGen 风格) */
export interface PipelineStage {
  id: string
  agent_name: string // Planner | Coder | Reviewer
  status: "pending" | "in_progress" | "completed" | "error"
  /** 该阶段产生的工具调用 */
  tool_calls?: ToolCallRecord[]
  /** 该阶段输出摘要 */
  summary?: string
}

/** 引用的文件 (Continue @-mention 风格) */
export interface ReferencedFile {
  path: string
  name: string
  language?: string
  /** 是全文还是片段 */
  type: "full" | "snippet"
  /** 代码片段行范围 */
  line_start?: number
  line_end?: number
}

// ═══════════════════════════════════════
// SSE 事件类型 — 增强版
// ═══════════════════════════════════════
export type SSEEventType =
  // 管线阶段
  | "orchestration_start"
  | "stage_start"
  | "stage_complete"
  | "stage_error"
  // 推理步骤 (Cline 风格)
  | "reasoning"
  | "thinking"
  // 工具调用 (增强)
  | "tool_approval_required"
  | "tool_approved"
  | "tool_rejected"
  | "tool_call"
  | "tool_executing"
  | "tool_result"
  | "tool_error"
  // 轮次
  | "turn_start"
  | "turn_end"
  // 上下文注入 (Continue 风格)
  | "context_loaded"
  // 最终回复 & diff
  | "final_answer"
  | "chunk"
  | "diff"
  // 终止
  | "error"
  | "done"

export interface SSEEvent {
  type: SSEEventType
  data?: string
  turn?: number
  max_turns?: number
  tool_calls?: { id: string; name: string; arguments: string; category?: string; security_level?: string; requires_approval?: boolean }[]
  tool_name?: string
  tool_id?: string
  success?: boolean
  result?: string
  latency_ms?: number
  content?: string
  model_used?: string
  turns?: number
  error?: string
  provider?: string
  // diff
  file_path?: string
  // 管线 (LangGraph 风格)
  stage_name?: string
  agent_name?: string
  stage_summary?: string
  pipeline_stages?: PipelineStage[]
  // 推理 (Cline 风格)
  reasoning_step?: ReasoningStep
  reasoning_content?: string
  // 审批 (Open Interpreter 风格)
  security_level?: string
  tool_category?: string
  // 上下文 (Continue 风格)
  context_files?: ReferencedFile[]
  context_summary?: string
  // 分块
  chunk_content?: string
  is_final?: boolean
}

// ═══════════════════════════════════════
// Diff 数据模型
// ═══════════════════════════════════════
export interface DiffData {
  file_path: string
  file_name: string
  language: string
  change_type: "CREATE" | "MODIFY" | "DELETE"
  is_new_file: boolean
  diff_text: string
  hunks: DiffHunk[]
  old_line_count: number
  new_line_count: number
  lines_added: number
  lines_removed: number
  content_before: string
  content_after: string
}

export interface DiffHunk {
  header: string
  lines: string[]
}

// ═══════════════════════════════════════
// 模型选项
// ═══════════════════════════════════════
export interface ModelOption {
  name: string
  display_name: string
  capability: string
  format?: string
  provider?: string
  priority: number
  is_local: boolean
  is_downloaded?: boolean
  is_remote?: boolean
}

// ═══════════════════════════════════════
// Agent 模式 (6 modes × skills 绑定)
// ═══════════════════════════════════════
export interface AgentModeInfo {
  id: string
  label: string
  description: string
  icon: string
  skills: string[]
  color: string
}

/** 预设 Agent 模式 (与后端 agent_modes.py PRESET_MODES 对齐) */
export const PRESET_AGENT_MODES: AgentModeInfo[] = [
  { id: "craft",  label: "Craft",   description: "全栈开发，理解需求→编码→审查", icon: "Wand2",     skills: ["frontend-design", "refactor"],       color: "#6366f1" },
  { id: "ask",    label: "Ask",     description: "问答模式，解释代码、文档生成", icon: "MessageCircle", skills: ["explain"],                     color: "#22d3ee" },
  { id: "plan",   label: "Plan",    description: "架构设计，先计划再执行",       icon: "Lightbulb", skills: ["code-review", "explain"],         color: "#f59e0b" },
  { id: "agent",  label: "Agent",   description: "全自动Agent，多工具协作",      icon: "Bot",        skills: ["frontend-design", "refactor", "debug", "test-gen", "webapp-testing"], color: "#10b981" },
  { id: "debug",  label: "Debug",   description: "调试模式，定位并修复问题",     icon: "Bug",        skills: ["debug", "explain"],               color: "#ef4444" },
  { id: "review", label: "Review",  description: "代码审查模式",                  icon: "GitPullRequest", skills: ["code-review"],            color: "#8b5cf6" },
  { id: "test",   label: "Test",    description: "测试生成模式",                  icon: "FlaskConical", skills: ["test-gen", "webapp-testing"], color: "#ec4899" },
  { id: "docs",   label: "Docs",    description: "文档生成模式",                  icon: "BookOpen",   skills: ["explain"],                     color: "#f97316" },
]

// ═══════════════════════════════════════
// 分页
// ═══════════════════════════════════════
export interface ApiPageResponse<T = unknown> {
  data: T[]
  total: number
  page: number
  size: number
}
