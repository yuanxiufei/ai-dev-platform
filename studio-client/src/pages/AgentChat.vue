<script setup lang="ts">
/**
 * AgentChat.vue — AI Agent 完整交互界面
 *
 * 功能模块：
 *   1. 顶栏状态栏 — Agent 状态指示器、模式切换、模型信息、操作按钮
 *   2. 左侧面板 — 会话历史列表（新建/切换/删除）
 *   3. 中间主区 — 对话消息流 + 流式输出 + 工具调用卡片
 *   4. 右侧面板 — 工具调用详情（参数/结果展开）
 *   5. 底部输入区 — 文本输入 + 发送/停止
 *
 * 数据流：
 *   用户输入 → handleSend() → runAgentStream() → fetch(SSE) → handleSSEEvent()
 * SSE事件: turn_start → tool_call → tool_executing → tool_result → final_answer → done
 */

import {
  AlertTriangle,
  AlertCircle,
  Bot,
  Brain,
  Check,
  Clock,
  Copy,
  Cpu,
  ChevronRight,
  FileCode,
  GitBranch,
  GitFork,
  Globe,
  History,
  Loader2,
  MessageSquare,
  PanelRightClose,
  PanelRightOpen,
  Plus,
  RotateCcw,
  Search,
  Send,
  Square,
  Terminal,
  Trash2,
  User,
  Wrench,
  Zap,
} from "lucide-vue-next"
import { computed, nextTick, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import DiffViewer from "@/components/DiffViewer.vue"
import { agentChatStreamUrl } from "@/api/agent"
import type {
  ChatMessage,
  DiffData,
  ModelOption,
  PipelineStage,
  ReasoningStep,
  ReferencedFile,
  SSEEvent,
  SSEEventType,
  ToolCallRecord,
} from "@/types/studio"
import { PRESET_AGENT_MODES } from "@/types/studio"
import AgentPipeline from "@/components/agent/AgentPipeline.vue"
import AgentReasoningSteps from "@/components/agent/AgentReasoningSteps.vue"
import AgentRunDashboard from "@/components/agent/AgentRunDashboard.vue"
import AgentTabBar from "@/components/agent/AgentTabBar.vue" // Session 10
import AtMentionPopup from "@/components/agent/AtMentionPopup.vue"
import ContextPanel from "@/components/agent/ContextPanel.vue"
import MultiFileDiffPanel from "@/components/agent/MultiFileDiffPanel.vue"
import SecurityApprovalPanel from "@/components/agent/SecurityApprovalPanel.vue"
import WorkflowGraph from "@/components/agent/WorkflowGraph.vue"
import { useAgentTabsStore } from "@/stores/useAgentTabsStore" // Session 10

// ════════════════════════════════════════════════
// 路由 & 项目上下文
// ════════════════════════════════════════════════
const route = useRoute()
const projectId = computed(() => route.params.id as string | undefined)

// ════════════════════════════════════════════════
// 对话核心状态
// ════════════════════════════════════════════════
const messages = ref<ChatMessage[]>([])
const isStreaming = ref(false)
const currentToolCalls = ref<ToolCallRecord[]>([])
const currentTurn = ref(0)
const maxTurns = ref(10)
const sessionId = ref(crypto.randomUUID())
const abortController = ref<AbortController | null>(null)

// Agent 运行时状态机
type AgentState = "idle" | "thinking" | "calling_tools" | "generating"
const agentState = ref<AgentState>("idle")
const lastModelUsed = ref("")
const lastProvider = ref("")
const totalLatencyMs = ref(0)

// 模式选择 — 使用 PRESET_AGENT_MODES
const chatMode = ref("craft")
const preferredModel = ref("")
const availableModels = ref<ModelOption[]>([])
const showModelPicker = ref(false)

// 🆕 推理步骤 & 管线 (Cline/LangGraph 参考)
const reasoningSteps = ref<ReasoningStep[]>([])
const pipelineStages = ref<PipelineStage[]>([])

// 🆕 上下文文件 (Continue @-mention 参考)
const contextFiles = ref<ReferencedFile[]>([])
const showMentionPopup = ref(false)
const mentionFilter = ref("")

// 🆕 工具审批队列 (Open Interpreter 参考)
const pendingApprovals = ref<ToolCallRecord[]>([])

// 面板开关
const hasStarted = ref(false)
const showRightPanel = ref(false)
const showHistoryPanel = ref(false)
const showContextPanel = ref(false)
const showPipelinePanel = ref(false)
const showModePicker = ref(false)

// 工具调用展开 ID 集合
const expandedToolIds = ref<Set<string>>(new Set())

// 右侧面板 Tab
const rightPanelTab = ref<"tools" | "dashboard">("tools")

// 🆕 Diff 数据收集
const collectedDiffs = ref<DiffData[]>([])
const showDiffPanel = ref(false)

// 输入框
const inputText = ref("")
const textareaEl = ref<HTMLTextAreaElement | null>(null)

// 🆕 激活技能列表
const activeSkills = ref<string[]>([])

// Toast 提示
const toastMsg = ref("")
let toastTimer: ReturnType<typeof setTimeout> | null = null

// ════════════════════════════════════════════════
// Session 10: Agent Tab Store
// ════════════════════════════════════════════════
const tabStore = useAgentTabsStore()

// ════════════════════════════════════════════════
// 会话历史数据结构 & 持久化
// ════════════════════════════════════════════════
interface ChatSession {
  id: string
  title: string
  createdAt: string
  messageCount: number
  agentMode: string
}
const sessions = ref<ChatSession[]>([])

function loadSessions() {
  try {
    const stored = localStorage.getItem("agent_chat_sessions")
    if (stored) sessions.value = JSON.parse(stored)
  } catch {
    /* ignore */
  }
}

function persistSessions() {
  try {
    localStorage.setItem("agent_chat_sessions", JSON.stringify(sessions.value))
  } catch {
    /* storage full */
  }
}

function saveCurrentSession() {
  if (messages.value.length === 0) return
  const firstUserMsg = messages.value.find((m) => m.role === "user")
  const title = (firstUserMsg?.content || "新对话").slice(0, 60)
  const existingIdx = sessions.value.findIndex((s) => s.id === sessionId.value)
  const sessionData: ChatSession = {
    id: sessionId.value,
    title,
    createdAt: messages.value[0]?.timestamp || new Date().toISOString(),
    messageCount: messages.value.filter((m) => m.role !== "system").length,
    agentMode: chatMode.value,
  }
  if (existingIdx >= 0) {
    sessions.value[existingIdx] = sessionData
  } else {
    sessions.value.unshift(sessionData)
    if (sessions.value.length > 30) sessions.value.pop()
  }
  persistSessions()

  // Session 10: sync to tab store
  tabStore.saveMessages(sessionId.value, messages.value)
  tabStore.updateTabMode(sessionId.value, chatMode.value)
  if (title !== "新对话") {
    tabStore.renameTab(sessionId.value, title)
  }
}

// ════════════════════════════════════════════════
// 生命周期
// ════════════════════════════════════════════════
onMounted(() => {
  loadSessions()
  loadModels()
})

/** 加载可用模型列表（直接 fetch，绕过 axios 401 拦截） */
async function loadModels() {
  try {
    const token = localStorage.getItem("token")
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    }
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch("/api/v1/system/models", { headers })
    if (!res.ok) return
    const data = await res.json()
    availableModels.value = data.models || []
  } catch {
    // 静默失败
  }
}

function selectModel(name: string) {
  preferredModel.value = name
  showModelPicker.value = false
  showToast(`已切换模型：${name || "自动选择"}`)
}

// ════════════════════════════════════════════════
// 工具函数
// ════════════════════════════════════════════════
function showToast(msg: string) {
  toastMsg.value = msg
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastMsg.value = ""
  }, 3000)
}

async function scrollToBottom() {
  await nextTick()
  const el = document.getElementById("chat-container")
  if (el) el.scrollTop = el.scrollHeight
}

function toggleExpand(id: string) {
  const s = expandedToolIds.value
  s.has(id) ? s.delete(id) : s.add(id)
}

/** 根据工具名推断图标组件 */
function toolIcon(name: string) {
  const n = name.toLowerCase()
  if (/read|search|find|list|grep/.test(n)) return Search
  if (/write|edit|replace|create|delete|save/.test(n)) return FileCode
  if (/bash|exec|shell|git|run|command/.test(n)) return Terminal
  if (/web|fetch|http|url|browse/.test(n)) return Globe
  if (/think|reason|reflect/.test(n)) return Brain
  return Wrench
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return "刚刚"
  if (min < 60) return `${min}分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}小时前`
  return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
}

function copyText(t: string) {
  navigator.clipboard
    .writeText(t)
    .then(() => showToast("已复制"))
    .catch((err: unknown) => {
      console.warn('[AgentChat] Clipboard write failed', err)
    })
}

/** 判断消息是否为当前最后一条助手消息（用于流式动画定位） */
function isLastAssistant(msg: ChatMessage): boolean {
  const len = messages.value.length
  if (len === 0) return false
  // 倒序查找最后一条 assistant 或 tool 角色
  for (let i = len - 1; i >= 0; i--) {
    const m = messages.value[i]
    if (m.role === "assistant" || m.role === "tool") return m.id === msg.id
    if (m.role === "user") break
  }
  return false
}

// ════════════════════════════════════════════════
// 会话管理操作
// ════════════════════════════════════════════════
function newChat() {
  saveCurrentSession()
  messages.value = []
  const newId = tabStore.createTab(undefined, chatMode.value)
  sessionId.value = newId
  agentState.value = "idle"
  currentToolCalls.value = []
  collectedDiffs.value = []
  reasoningSteps.value = []
  pipelineStages.value = []
  pendingApprovals.value = []
  showDiffPanel.value = false
  totalLatencyMs.value = 0
  showHistoryPanel.value = false
  inputText.value = ""
}

/** 切换 Agent 模式，自动绑定技能 */
function switchMode(modeId: string) {
  chatMode.value = modeId
  const mode = PRESET_AGENT_MODES.find(m => m.id === modeId)
  if (mode) {
    activeSkills.value = [...mode.skills]
    showToast(`已切换为 ${mode.label} 模式 · ${mode.skills.length} 项技能`)
  }
}

/** 获取当前模式的技能绑定 */
const currentModeSkills = computed(() =>
  PRESET_AGENT_MODES.find(m => m.id === chatMode.value)?.skills || []
)

/** 当前模式的主题色 */
const currentModeColor = computed(() => {
  const m = PRESET_AGENT_MODES.find(m => m.id === chatMode.value)
  return m?.color || '#6366f1'
})
/** 当前模式标签文字色 */
const currentModeLabelColor = computed(() => {
  // 从颜色中提取较亮的版本作为文字色
  return '#e2e8f0'
})

function switchToSession(s: ChatSession) {
  saveCurrentSession()
  sessionId.value = s.id
  messages.value = tabStore.loadMessages(s.id)
  hasStarted.value = true
  chatMode.value = (s.agentMode as any) || "craft"
  tabStore.switchToTab(s.id)
  showHistoryPanel.value = false
  showToast(`已切换到「${s.title}」`)
}

function deleteSession(id: string, e: Event) {
  e.stopPropagation()
  sessions.value = sessions.value.filter((s) => s.id !== id)
  persistSessions()
}

function resetChat() {
  messages.value = []
  sessionId.value = crypto.randomUUID()
  agentState.value = "idle"
  currentToolCalls.value = []
  collectedDiffs.value = []
  reasoningSteps.value = []
  pipelineStages.value = []
  pendingApprovals.value = []
  showDiffPanel.value = false
  totalLatencyMs.value = 0
  showToast("已清空对话")
  scrollToBottom()
}

// 🆕 @-mention 处理
function onInput(e: Event) {
  const target = e.target as HTMLTextAreaElement
  inputText.value = target.value
  // 检测 @ 符号触发文件提及
  const cursorPos = target.selectionStart || 0
  const textBeforeCursor = inputText.value.slice(0, cursorPos)
  const atMatch = textBeforeCursor.match(/@(\S*)$/)
  if (atMatch) {
    showMentionPopup.value = true
    mentionFilter.value = atMatch[1]
  } else {
    showMentionPopup.value = false
    mentionFilter.value = ""
  }
}

function addFileContext(path: string, name: string) {
  if (!contextFiles.value.find(f => f.path === path)) {
    contextFiles.value.push({ path, name, type: "full" })
  }
  // 替换 @mention 文本 — 使用 @file:path 格式
  const cursorPos = textareaEl.value?.selectionStart || 0
  const textBeforeCursor = inputText.value.slice(0, cursorPos)
  const atIdx = textBeforeCursor.lastIndexOf("@")
  if (atIdx >= 0) {
    inputText.value = inputText.value.slice(0, atIdx) + `@file:${path} ` + inputText.value.slice(cursorPos)
  }
  showMentionPopup.value = false
  textareaEl.value?.focus()
  showToast(`已引用: ${name}`)
}

function removeContextFile(path: string) {
  contextFiles.value = contextFiles.value.filter(f => f.path !== path)
}

function toggleSkill(name: string) {
  const idx = activeSkills.value.indexOf(name)
  if (idx >= 0) {
    activeSkills.value.splice(idx, 1)
  } else {
    activeSkills.value.push(name)
  }
}

/** 🆕 @-mention 选择回调 (Continue 风格) */
function onMentionSelect(file: ReferencedFile) {
  addFileContext(file.path, file.name)
  showMentionPopup.value = false
}

/** 🆕 @-mention 关闭回调 */
function onMentionClose() {
  showMentionPopup.value = false
  textareaEl.value?.focus()
}

/** 工具审批操作 */
function approveTool(toolId: string) {
  const tool = pendingApprovals.value.find(t => t.id === toolId)
  if (tool) {
    tool.approval_status = "approved"
    pendingApprovals.value = pendingApprovals.value.filter(t => t.id !== toolId)
    showToast("已批准工具执行")
  }
}

function rejectTool(toolId: string) {
  const tool = pendingApprovals.value.find(t => t.id === toolId)
  if (tool) {
    tool.approval_status = "rejected"
    pendingApprovals.value = pendingApprovals.value.filter(t => t.id !== toolId)
    showToast("已拒绝工具调用")
  }
}

function approveAllTools() {
  for (const t of pendingApprovals.value) t.approval_status = "approved"
  pendingApprovals.value = []
  showToast("已批准所有工具")
}

function rejectAllTools() {
  for (const t of pendingApprovals.value) t.approval_status = "rejected"
  pendingApprovals.value = []
  showToast("已拒绝所有工具")
}

// ════════════════════════════════════════════════
// 启动聊天 / 快捷提示
// ════════════════════════════════════════════════
function startChat() {
  hasStarted.value = true
  setTimeout(() => textareaEl.value?.focus(), 80)
}

function quickPrompt(text: string) {
  hasStarted.value = true
  setTimeout(() => {
    inputText.value = text
    doSend(text)
  }, 80)
}

// ════════════════════════════════════════════════
// 核心：发送消息 → SSE 流式对话引擎
// ════════════════════════════════════════════════

/** 主入口：发送用户消息并启动 SSE 流式对话 */
async function doSend(text?: string) {
  const content = (text || inputText.value).trim()
  if (!content || isStreaming.value) return
  inputText.value = ""

  // 1. 追加用户消息
  const userMsg: ChatMessage = {
    id: crypto.randomUUID(),
    role: "user",
    content,
    timestamp: new Date().toISOString(),
  }
  messages.value.push(userMsg)
  await scrollToBottom()

  // 2. 创建占位助手消息
  const assistantMsg: ChatMessage = {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "",
    tool_calls: [],
    timestamp: new Date().toISOString(),
  }
  messages.value.push(assistantMsg)
  await scrollToBottom()

  // 3. 启动 SSE 流
  await runSSEStream(assistantMsg, content)
}

/** 执行 SSE 流式请求并处理事件循环 */
async function runSSEStream(assistantMsg: ChatMessage, content: string) {
  isStreaming.value = true
  agentState.value = "thinking"
  currentToolCalls.value = []
  reasoningSteps.value = []
  pipelineStages.value = []
  pendingApprovals.value = []
  collectedDiffs.value = []

  const ctrl = new AbortController()
  abortController.value = ctrl

  // 🆕 注入上下文到消息 (Continue 风格)
  if (contextFiles.value.length > 0) {
    assistantMsg.referenced_files = [...contextFiles.value]
  }

  try {
    const token = localStorage.getItem("token")
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    }
    if (token) headers.Authorization = `Bearer ${token}`

    // 🆕 构建请求体：包含技能和上下文文件
    const requestBody: Record<string, unknown> = {
      message: content,
      agent_name: chatMode.value === "agent" ? "agent" : chatMode.value,
      instructions: "",
      tools: ["get_weather", "web_search", "calculate", "datetime_now", "file_read"],
      tool_categories: ["LOW", "MEDIUM", "HIGH"],
      max_turns: 3,
      preferred_model: preferredModel.value || "",
      session_id: sessionId.value,
    }
    // 附加技能
    if (activeSkills.value.length > 0) {
      requestBody.skills = activeSkills.value
    }
    // 附加上下文文件
    if (contextFiles.value.length > 0) {
      requestBody.context_files = contextFiles.value.map(f => f.path)
    }

    const res = await fetch(agentChatStreamUrl(), {
      method: "POST",
      headers,
      body: JSON.stringify(requestBody),
      signal: ctrl.signal,
    })

    if (!res.ok) {
      assistantMsg.content = `请求失败 (${res.status}: ${res.statusText})`
      assistantMsg.metadata = {
        ...assistantMsg.metadata,
        error: true,
        errorStatus: res.status,
      }
      agentState.value = "idle"
      return
    }

    const reader = res.body?.getReader()
    if (!reader) {
      assistantMsg.content = "无法读取响应流"
      agentState.value = "idle"
      return
    }

    const decoder = new TextDecoder()
    let buf = ""

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split("\n")
      buf = lines.pop() || ""
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue
        try {
          dispatchEvent(assistantMsg, JSON.parse(line.slice(6)))
        } catch {
          /* malformed json */
        }
        await scrollToBottom()
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      if (!assistantMsg.content) assistantMsg.content = "[已停止生成]"
      else assistantMsg.content += "\n\n[已停止生成]"
    } else {
      const msg = err instanceof Error ? err.message : String(err)
      assistantMsg.content = `请求错误: ${msg}`
      assistantMsg.metadata = { ...assistantMsg.metadata, error: true }
    }
  } finally {
    isStreaming.value = false
    agentState.value = "idle"
    abortController.value = null
    saveCurrentSession()
  }
}

/** SSE 事件分发器 —— 状态机驱动 UI 更新 (增强版) */
function dispatchEvent(msg: ChatMessage, ev: SSEEvent) {
  switch (ev.type as SSEEventType) {
    // ═══════ 编排管线 (LangGraph/AutoGen 参考) ═══════
    case "orchestration_start":
      pipelineStages.value = ev.pipeline_stages || []
      showPipelinePanel.value = true
      break

    case "stage_start":
      agentState.value = "thinking"
      // 更新对应阶段状态为 in_progress
      pipelineStages.value = pipelineStages.value.map(s =>
        s.agent_name === ev.agent_name ? { ...s, status: "in_progress" as const } : s
      )
      break

    case "stage_complete":
      pipelineStages.value = pipelineStages.value.map(s =>
        s.agent_name === ev.agent_name
          ? { ...s, status: "completed" as const, summary: ev.stage_summary || s.summary, tool_calls: [...currentToolCalls.value] }
          : s
      )
      break

    case "stage_error":
      pipelineStages.value = pipelineStages.value.map(s =>
        s.agent_name === ev.agent_name ? { ...s, status: "error" as const } : s
      )
      break

    // ═══════ 推理步骤 (Cline/RooCode 参考) ═══════
    case "reasoning":
    case "thinking": {
      agentState.value = "thinking"
      const step: ReasoningStep = ev.reasoning_step || {
        id: crypto.randomUUID(),
        type: "thinking",
        content: ev.reasoning_content || ev.content || "",
        status: "in_progress",
      }
      // 更新已有步骤或追加
      const existingIdx = reasoningSteps.value.findIndex(s => s.id === step.id)
      if (existingIdx >= 0) {
        reasoningSteps.value[existingIdx] = {
          ...reasoningSteps.value[existingIdx],
          ...step,
          status: "completed",
        }
      } else {
        reasoningSteps.value.push({ ...step, status: "completed" })
      }
      // 同步到消息
      msg.reasoning_steps = [...reasoningSteps.value]
      break
    }

    // ═══════ 上下文加载 (Continue 参考) ═══════
    case "context_loaded":
      if (ev.context_files) {
        contextFiles.value = [...contextFiles.value, ...ev.context_files]
      }
      break

    // ═══════ 工具审批 (Open Interpreter 参考) ═══════
    case "tool_approval_required": {
      const calls = ev.tool_calls || []
      for (const tc of calls) {
        const record: ToolCallRecord = {
          id: tc.id || crypto.randomUUID(),
          name: tc.name,
            arguments:
            typeof tc.arguments === "string"
              ? (() => { try { return JSON.parse(tc.arguments) } catch { return {} } })()
              : tc.arguments || {},
          requires_approval: true,
          approval_status: "pending",
          security_level: (ev.security_level || tc.security_level || "SYSTEM") as ToolCallRecord["security_level"],
          category: ev.tool_category || tc.category || "MEDIUM",
        }
        pendingApprovals.value.push(record)
      }
      break
    }

    case "tool_approved":
      // 标记审批通过的工具
      if (ev.tool_id) {
        pendingApprovals.value = pendingApprovals.value.filter(t => t.id !== ev.tool_id)
      }
      break

    case "tool_rejected":
      if (ev.tool_id) {
        const tool = pendingApprovals.value.find(t => t.id === ev.tool_id)
        if (tool) tool.approval_status = "rejected"
        pendingApprovals.value = pendingApprovals.value.filter(t => t.id !== ev.tool_id)
      }
      break

    // ═══════ 原有事件 (增强) ═══════
    case "turn_start":
      currentTurn.value = ev.turn ?? currentTurn.value + 1
      maxTurns.value = ev.max_turns ?? maxTurns.value
      agentState.value = "thinking"
      break

    case "tool_call": {
      agentState.value = "calling_tools"
      const calls = ev.tool_calls || []
      for (const tc of calls) {
        const record: ToolCallRecord = {
          id: tc.id || crypto.randomUUID(),
          name: tc.name,
          arguments:
            typeof tc.arguments === "string"
              ? (() => { try { return JSON.parse(tc.arguments) } catch { return {} } })()
              : tc.arguments || {},
          category: tc.category || "MEDIUM",
          security_level: (tc.security_level || "READ_ONLY") as ToolCallRecord["security_level"],
          requires_approval: tc.requires_approval || false,
        }
        currentToolCalls.value.push(record)
        msg.tool_calls = msg.tool_calls || []
        msg.tool_calls.push({ ...record })
      }
      break
    }

    case "tool_executing":
      agentState.value = "calling_tools"
      if (ev.tool_id) {
        const tc = currentToolCalls.value.find(t => t.id === ev.tool_id)
        if (tc && ev.latency_ms) tc.latency_ms = ev.latency_ms
      }
      break

    case "tool_result": {
      const name = ev.tool_name || ""
      const tid = ev.tool_id
      const match = (tid
        ? currentToolCalls.value.find(tc => tc.id === tid)
        : [...currentToolCalls.value].reverse().find(tc => tc.name === name && !tc.result))
      if (match) {
        match.result = ev.result || ""
        match.success = ev.success ?? false
        const mTc = msg.tool_calls?.find(t => t.id === match.id)
        if (mTc) {
          mTc.result = match.result
          mTc.success = match.success
        }
      }
      break
    }

    case "tool_error": {
      const name = ev.tool_name || ""
      const match = [...currentToolCalls.value].reverse().find(tc => tc.name === name)
      if (match) {
        match.result = ev.error || "工具执行出错"
        match.success = false
      }
      break
    }

    case "turn_end":
      // 轮次结束，保存当前管线状态到消息
      msg.pipeline_stages = pipelineStages.value.map(s => ({ ...s }))
      break

    // 🆕 分块流式输出
    case "chunk":
      if (ev.chunk_content) {
        msg.content += ev.chunk_content
        agentState.value = "generating"
      }
      break

    // 🆕 diff 事件 — 收集 diff 数据用于 DiffViewer 展示
    case "diff": {
      const diffData = ev.data as unknown as DiffData
      if (diffData) {
        collectedDiffs.value.push(diffData)
        msg.metadata = {
          ...msg.metadata,
          has_diffs: true,
          diff_count: ((msg.metadata?._diff_count as number) || 0) + 1,
          _diff_count: ((msg.metadata?._diff_count as number) || 0) + 1,
        }
      }
      break
    }

    case "final_answer":
      agentState.value = "generating"
      msg.content = ev.content || ""
      if (ev.model_used) lastModelUsed.value = ev.model_used
      lastProvider.value = ev.provider || ""
      if (ev.latency_ms) totalLatencyMs.value = ev.latency_ms
      if (ev.turns) currentTurn.value = ev.turns
      msg.metadata = {
        ...msg.metadata,
        model_used: ev.model_used,
        turns: ev.turns,
        provider: ev.provider,
        latency_ms: ev.latency_ms,
      }
      break

    case "error":
      msg.content += `\n\n⚠️ 错误: ${ev.error || "未知错误"}`
      msg.metadata = { ...msg.metadata, error: true }
      agentState.value = "idle"
      break

    case "done":
      agentState.value = "idle"
      // 最终保存管线状态到消息
      msg.pipeline_stages = pipelineStages.value.map(s => ({ ...s }))
      msg.reasoning_steps = [...reasoningSteps.value]
      break
  }
}

// ════════════════════════════════════════════════
// 操作：停止 / 重试
// ════════════════════════════════════════════════
function stopGeneration() {
  abortController.value?.abort()
}

async function retryMessage(targetMsg: ChatMessage) {
  if (isStreaming.value) return
  const idx = messages.value.indexOf(targetMsg)
  if (idx <= 0) return
  const userMsg = messages.value[idx - 1]
  if (userMsg.role !== "user") return

  // 移除目标消息及之后的所有消息
  messages.value.splice(idx)
  await scrollToBottom()

  // 重建空助手消息
  const fresh: ChatMessage = {
    id: crypto.randomUUID(),
    role: "assistant",
    content: "",
    tool_calls: [],
    timestamp: new Date().toISOString(),
  }
  messages.value.push(fresh)
  await scrollToBottom()
  await runSSEStream(fresh, userMsg.content)
}

// ════════════════════════════════════════════════
// 输入框交互
// ════════════════════════════════════════════════
function onInputKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault()
    doSend()
  }
}
</script>

<template>
  <div class="flex flex-col h-full w-full overflow-hidden bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">

    <!-- ═════ Toast ═════ -->
    <Transition name="toast">
      <div v-if="toastMsg" class="fixed top-4 left-1/2 -translate-x-1/2 z-[100] px-5 py-2.5 rounded-xl text-sm font-medium bg-emerald-500/12 border border-emerald-500/20 text-emerald-400 backdrop-blur-xl shadow-2xl pointer-events-none">
        {{ toastMsg }}
      </div>
    </Transition>

    <!-- ═════ 顶部导航栏 ═════ -->
    <header class="shrink-0 page-header backdrop-blur-md flex items-center justify-between px-4 gap-3 z-30">

      <!-- 左区：状态 -->
      <div class="flex items-center gap-3 min-w-0">
        <!-- 历史面板开关 -->
        <button
          @click="showHistoryPanel = !showHistoryPanel"
          :class="['p-2.5 rounded-xl transition-all duration-200 shrink-0', showHistoryPanel ? 'bg-brand-500/10 text-brand-400' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)]']"
          title="对话历史"
        >
          <History class="w-[20px] h-[20px]" />
        </button>

        <!-- Agent 状态指示灯 -->
        <div class="flex items-center gap-2.5">
          <span :class="['w-2.5 h-2.5 rounded-full transition-colors duration-300', isStreaming ? 'bg-emerald-400 animate-pulse' : 'bg-gray-600']" />
          <span class="text-[13px] font-medium truncate hidden sm:inline" :class="isStreaming ? 'text-[var(--color-ide-text)]' : 'text-[var(--color-ide-text-dim)]'">
            {{ isStreaming ? (agentState === 'thinking' ? '思考中' : agentState === 'calling_tools' ? '执行工具' : '生成回复') : 'Agent 对话' }}
          </span>
        </div>
      </div>

      <!-- 右区：精简操作按钮组 -->
      <div class="flex items-center gap-1.5 shrink-0">
        <!-- 模式选择器（紧凑版） -->
        <button
          @click="showModePicker = !showModePicker"
          class="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl text-[13px] font-medium transition-all cursor-pointer hover:bg-[var(--color-ide-surface-hover)]"
          :style="{ color: currentModeLabelColor }"
          title="切换模式"
        >
          <span class="w-3.5 h-3.5 rounded-full" :style="{ background: currentModeColor }" />
          <span class="hidden sm:inline">{{ PRESET_AGENT_MODES.find(m => m.id === chatMode)?.label || 'Craft' }}</span>
        </button>
        <Transition name="fade">
          <div v-if="showModePicker" class="fixed inset-0 z-40" @click="showModePicker = false" />
        </Transition>
        <Transition name="fade">
          <div v-if="showModePicker" class="absolute right-4 top-12 w-56 rounded-xl bg-surface-950/95 backdrop-blur-xl border border-[var(--color-ide-border)] shadow-2xl z-50 overflow-hidden py-1.5" @click.stop>
            <button v-for="m in PRESET_AGENT_MODES" :key="m.id"
                    @click="switchMode(m.id); showModePicker = false"
                    class="w-full flex items-center gap-2.5 px-4 py-2 text-[13px] text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors"
                    :class="chatMode === m.id ? 'text-white font-medium' : 'text-[var(--color-ide-text-dim)]'">
              <span class="w-2.5 h-2.5 rounded-full shrink-0" :style="{ background: m.color }" />
              <span>{{ m.label }}</span>
              <Check v-if="chatMode === m.id" class="w-4 h-4 ml-auto text-brand-400" />
            </button>
          </div>
        </Transition>

        <div class="w-px h-4 bg-[var(--color-ide-surface-hover)] mx-1" />

        <!-- 模型选择器 -->
        <button
          @click="showModelPicker = !showModelPicker"
          class="flex items-center gap-2.5 px-3.5 py-1.5 rounded-xl text-[13px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-all"
          title="切换模型"
        >
          <Cpu class="w-[18px] h-[18px]" />
          <span class="max-w-[100px] truncate hidden md:inline">{{ preferredModel || lastModelUsed || '自动' }}</span>
        </button>

        <!-- 遮罩层 -->
        <Transition name="fade">
          <div v-if="showModelPicker" class="fixed inset-0 z-40" @click="showModelPicker = false" />
        </Transition>
        <Transition name="fade">
          <div v-if="showModelPicker" class="absolute right-4 top-12 w-72 rounded-xl bg-surface-950/95 backdrop-blur-xl border border-[var(--color-ide-border)] shadow-2xl z-50 overflow-hidden" @click.stop>
            <div class="p-2.5 border-b border-[var(--color-ide-border)] flex items-center justify-between">
              <span class="text-[11px] font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider">可用模型</span>
              <span class="text-[11px] text-[var(--color-ide-text-dim)]">{{ availableModels.length }} 个</span>
            </div>
            <button @click="selectModel('')" class="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-[var(--color-ide-surface-hover)]" :class="!preferredModel ? 'bg-brand-500/8 text-brand-300' : 'text-[var(--color-ide-text-dim)]'">
              <Zap class="w-[18px] h-[18px] shrink-0" :class="!preferredModel ? 'text-brand-400' : 'text-[var(--color-ide-text-dim)]'" />
              <div><div class="text-[13px] font-medium">自动选择</div></div>
              <Check v-if="!preferredModel" class="w-[18px] h-[18px] ml-auto text-brand-400" />
            </button>
            <template v-if="availableModels.filter(m => m.is_local).length > 0">
              <div class="px-3.5 py-1.5 text-[11px] font-semibold text-emerald-400/70 uppercase">本地模型</div>
              <div class="max-h-40 overflow-y-auto custom-scroll">
                <button v-for="m in availableModels.filter(m => m.is_local)" :key="m.name"
                        @click="selectModel(m.name)" class="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-[var(--color-ide-surface-hover)]"
                        :class="preferredModel === m.name ? 'bg-brand-500/8 text-brand-300' : 'text-[var(--color-ide-text-dim)]'">
                  <Cpu class="w-[18px] h-[18px] shrink-0" :class="preferredModel === m.name ? 'text-brand-400' : 'text-emerald-500/60'" />
                  <div class="min-w-0 flex-1"><div class="text-[13px] font-medium truncate">{{ m.display_name || m.name }}</div></div>
                  <Check v-if="preferredModel === m.name" class="w-[18px] h-[18px] text-brand-400" />
                </button>
              </div>
            </template>
            <template v-if="availableModels.filter(m => !m.is_local).length > 0">
              <div class="px-3.5 py-1.5 text-[11px] font-semibold text-blue-400/70 uppercase">远程 API</div>
              <div class="max-h-40 overflow-y-auto custom-scroll">
                <button v-for="m in availableModels.filter(m => !m.is_local)" :key="m.name"
                        @click="selectModel(m.name)" class="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-[var(--color-ide-surface-hover)]"
                        :class="preferredModel === m.name ? 'bg-brand-500/8 text-brand-300' : 'text-[var(--color-ide-text-dim)]'">
                  <Globe class="w-[18px] h-[18px] shrink-0" :class="preferredModel === m.name ? 'text-brand-400' : 'text-blue-500/60'" />
                  <div class="min-w-0 flex-1"><div class="text-[13px] font-medium truncate">{{ m.display_name || m.name }}</div></div>
                  <Check v-if="preferredModel === m.name" class="w-[18px] h-[18px] text-brand-400" />
                </button>
              </div>
            </template>
            <div v-if="availableModels.length === 0" class="px-4 py-6 text-center text-[12px] text-[var(--color-ide-text-dim)]">暂无可用模型</div>
          </div>
        </Transition>

        <!-- 工具面板开关 -->
        <button :class="['p-2.5 rounded-xl transition-all duration-200', showRightPanel ? 'text-brand-400 bg-brand-500/10' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)]']"
                @click="showRightPanel = !showRightPanel" title="工具调用详情">
          <PanelRightOpen v-if="!showRightPanel" class="w-[20px] h-[20px]" />
          <PanelRightClose v-else class="w-[20px] h-[20px]" />
        </button>

        <!-- 新建对话 -->
        <button @click="newChat" class="p-2.5 rounded-xl text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-all duration-200" title="新建对话">
          <Plus class="w-[20px] h-[20px]" />
        </button>
      </div>
    </header>

    <!-- 🆕 Session 10: Agent 会话 Tab 栏 (RooCode 风格) -->
    <AgentTabBar
      @tab-switch="(tabId: string) => { sessionId = tabId; messages = tabStore.loadMessages(tabId); chatMode = (tabStore.activeTab?.mode ?? 'craft') as any; }"
      @new-tab="newChat()"
    />

    <!-- 🆕 工具审批栏 (Open Interpreter + AutoCLI 风格) -->
    <SecurityApprovalPanel
      v-if="pendingApprovals.length > 0"
      :pending="pendingApprovals"
      :autoApprove="false"
      autoApproveThreshold="READ_ONLY"
      @approve="approveTool"
      @reject="rejectTool"
      @approveAll="approveAllTools"
      @rejectAll="rejectAllTools"
    />

    <!-- ═════ 主体三栏布局 ═════ -->
    <div class="flex flex-1 min-h-0 overflow-hidden">

      <!-- ─── 左栏：会话历史 / 上下文 ─── -->
      <Transition name="slide-left">
        <aside v-if="showHistoryPanel" class="w-64 shrink-0 flex flex-col border-r border-[var(--color-ide-border)] bg-surface-900/40 overflow-hidden">
          <div class="p-3 border-b border-[var(--color-ide-border)] flex items-center justify-between shrink-0">
            <h3 class="text-[13px] font-semibold text-[var(--color-ide-text)] uppercase tracking-wider">对话历史</h3>
            <button @click="newChat()" class="p-2 rounded-lg hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] hover:text-brand-400 transition-colors" title="新建对话"><Plus class="w-[18px] h-[18px]" /></button>
          </div>
          <div class="flex-1 overflow-y-auto p-2 space-y-0.5 custom-scroll">

            <button
              @click="newChat()"
              class="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-[var(--color-ide-text-dim)] hover:text-white hover:bg-[var(--color-ide-surface-hover)] transition-all group"
            >
              <MessageSquare class="w-[18px] h-[18px] text-[var(--color-ide-text-dim)] group-hover:text-brand-400 transition-colors" />
              新建对话
            </button>

            <div class="pt-2 pb-1 px-3 text-[11px] font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider">最近会话</div>

            <button
              v-for="sess in sessions.slice(0, 20)"
              :key="sess.id"
              @click="switchToSession(sess)"
              :class="[
                'w-full text-left px-3 py-2 rounded-lg transition-all duration-150 group',
                sess.id === sessionId ? 'bg-brand-500/8 text-brand-300 ring-1 ring-brand-500/10' : 'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]'
              ]"
            >
              <div class="flex items-start gap-2.5">
                <MessageSquare :class="['w-[16px] h-[16px] mt-0.5 shrink-0', sess.id === sessionId ? 'text-brand-400' : 'text-[var(--color-ide-text-dim)]']" />
                <div class="min-w-0 flex-1">
                  <p class="text-[13px] truncate leading-relaxed">{{ sess.title }}</p>
                  <p class="text-[11px] text-[var(--color-ide-text-dim)] mt-0.5 flex items-center gap-2">
                    <Clock class="w-3 h-3 opacity-60" />{{ formatTime(sess.createdAt) }}
                    <span>· {{ sess.messageCount }}条</span>
                  </p>
                </div>
                <button
                  @click="deleteSession(sess.id, $event)"
                  class="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/10 text-[var(--color-ide-text-dim)] hover:text-red-400 transition-all shrink-0"
                  title="删除"
                ><Trash2 class="w-[14px] h-[14px]" /></button>
              </div>
            </button>

            <div v-if="sessions.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-700">
              <MessageSquare class="w-8 h-8 mb-2 opacity-20" />
              <p class="text-[13px]">暂无历史对话</p>
            </div>
          </div>
        </aside>
      </Transition>

      <!-- 🆕 上下文面板 (Continue 风格) -->
      <Transition name="slide-left">
        <aside v-if="showContextPanel" class="w-72 shrink-0 border-r border-[var(--color-ide-border)] bg-surface-900/40 overflow-hidden">
          <div class="h-full">
            <ContextPanel
              :files="contextFiles"
              :activeSkills="activeSkills"
              :memoryNodes="0"
              @refresh="loadModels"
              @removeFile="removeContextFile"
              @toggleSkill="toggleSkill"
            />
          </div>
        </aside>
      </Transition>

      <!-- ─── 中间：对话区域 ─── -->
      <main class="flex-1 flex flex-col min-w-0">

        <!-- ===== 欢迎页（功能引导） ===== -->
        <section v-if="!hasStarted" class="flex-1 flex flex-col overflow-hidden">
          <div class="flex-1 flex items-center justify-center px-4 py-8">
            <div class="w-full max-w-xl mx-auto space-y-8">

              <!-- 居中 Logo & 问候 -->
              <div class="text-center space-y-3">
                <div class="inline-flex items-center justify-center w-14 h-14 rounded-2xl
                            bg-gradient-to-br from-indigo-500/20 via-purple-500/15 to-cyan-500/10
                            border border-indigo-500/20 mb-2">
                  <Bot class="w-7 h-7 text-indigo-300" />
                </div>
                <h2 class="text-xl font-bold text-white">有什么可以帮你的？</h2>
                <p class="text-sm text-[var(--color-ide-text-dim)] max-w-md mx-auto leading-relaxed">
                  分析代码、生成组件、搜索重构、执行命令 — 直接输入或选择下方快捷开始
                </p>
              </div>

              <!-- 精简快捷卡片：4 个核心入口 -->
              <div class="grid grid-cols-2 gap-2.5">
                <button v-for="(card, ci) in [
                  { icon: '\u{1F50D}', label: '分析代码', prompt: '帮我分析当前项目的代码结构和性能瓶颈', color: 'from-blue-500/10 to-blue-500/5 hover:border-blue-500/20' },
                  { icon: '\u26A1', label: '生成组件', prompt: '帮我创建一个 Vue 3 组件', color: 'from-emerald-500/10 to-emerald-500/5 hover:border-emerald-500/20' },
                  { icon: '\u{1F3D7}\uFE0F', label: '解释架构', prompt: '解释这个项目的技术架构和模块关系', color: 'from-purple-500/10 to-purple-500/5 hover:border-purple-500/20' },
                  { icon: '\u{1F5A5}\uFE0F', label: '终端命令', prompt: '帮我执行开发环境初始化命令', color: 'from-orange-500/10 to-orange-500/5 hover:border-orange-500/20' },
                ]" :key="ci"
                        @click="quickPrompt(card.prompt)"
                        :class="['group text-left p-3.5 rounded-xl border bg-[var(--color-ide-surface-hover)] border-[var(--color-ide-border)] transition-all duration-200 hover:bg-[var(--color-ide-surface-hover)]', card.color]">
                  <div class="flex items-center gap-4">
                    <span class="text-xl">{{ card.icon }}</span>
                    <span class="text-sm font-medium text-[var(--color-ide-text)] group-hover:text-white transition-colors">{{ card.label }}</span>
                    <svg class="w-[18px] h-[18px] text-[var(--color-ide-text-dim)] group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all ml-auto shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
                  </div>
                </button>
              </div>

              <!-- 快捷标签 -->
              <div class="flex flex-wrap justify-center gap-2.5">
                <button v-for="(hint, i) in [
                  '截图转代码', '修复 Bug', '写测试', 'Git 提交',
                  '代码审查', 'Docker 配置'
                ]" :key="i"
                        @click="quickPrompt(hint + '，请帮我完成')"
                        class="px-3 py-1.5 rounded-full text-[13px] text-[var(--color-ide-text-dim)] bg-[var(--color-ide-surface-hover)]
                               border border-[var(--color-ide-border)] hover:text-white hover:bg-[var(--color-ide-surface-hover)]
                               hover:border-[var(--color-ide-accent)] transition-all cursor-pointer">
                  {{ hint }}
                </button>
              </div>

            </div>
          </div>

          <!-- 底部输入区（欢迎页专用） — VSCode: 撑满宽度，无 max-w 约束 -->
          <div class="shrink-0 border-t border-[var(--color-ide-border)] px-6 py-6 bg-surface-900/30 w-full">
            <div class="w-full" style="max-width: none;">
              <div class="relative group/input">
                <textarea
                  ref="textareaEl"
                  v-model="inputText"
                  rows="2"
                  placeholder="输入你的需求，比如「帮我分析项目结构」..."
                  class="welcome-textarea w-full"
                  @keydown="onInputKeydown"
                  @focus="startChat()"
                ></textarea>
                <!-- 发送按钮 -->
                <button
                  v-if="inputText.trim()"
                  @click="doSend()"
                  class="absolute right-3 bottom-3 p-2.5 rounded-[3px] bg-[var(--color-ide-accent)] text-white hover:bg-[var(--color-ide-accent-hover)] transition-all"
                  title="发送 (Enter)"
                >
                  <Send class="w-[20px] h-[20px]" />
                </button>
              </div>
              <div class="flex items-center justify-center gap-6 mt-3.5 px-1 text-[13px] text-[var(--color-ide-text-dim)]">
                <span><kbd class="kbd">Enter</kbd> 发送</span>
                <span><kbd class="kbd">Shift+Enter</kbd> 换行</span>
                <span>Claude Sonnet</span>
              </div>
            </div>
          </div>
        </section>

        <!-- ===== 对话模式 ===== -->
        <template v-else>
          <!-- 消息滚动容器 -->
          <div id="chat-container" class="flex-1 overflow-y-auto px-4 md:px-6 lg:px-8 py-6 space-y-5 custom-scroll">

            <!-- System 消息 -->
            <div v-for="msg in messages.filter(m => m.role === 'system')" :key="'sys-'+msg.id" class="flex justify-center">
              <div class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500/6 border border-cyan-500/12 text-[13px] text-cyan-300/80">
                <Zap class="w-[18px] h-[18px]" />{{ msg.content }}
              </div>
            </div>

            <!-- 🆕 Agent 编排管线透视 (LangGraph 风格) -->
            <div v-if="pipelineStages.length > 0 && messages.length > 0" class="flex justify-center">
              <AgentPipeline
                :stages="pipelineStages"
                :isActive="isStreaming"
                :activeStage="agentState === 'calling_tools' ? 'coder' : agentState === 'thinking' ? 'planner' : undefined"
                @stageClick="(s: PipelineStage) => { expandedToolIds.add(s.id) }"
                class="w-full max-w-2xl"
              />
            </div>

            <!-- User / Assistant 消息对 -->
            <div
              v-for="msg in messages.filter(m => m.role !== 'system')"
              :key="msg.id"
              :class="['flex gap-4', msg.role === 'user' ? 'justify-end' : 'justify-start']"
            >
              <!-- Avatar -->
              <div :class="[
                'w-8 h-8 rounded-xl flex items-center justify-center shrink-0 mt-0.5',
                msg.role === 'user' ? 'bg-surface-700 order-last' :
                'bg-gradient-to-br from-brand-500 to-purple-600'
              ]">
                <User v-if="msg.role === 'user'" class="w-[18px] h-[18px] text-[var(--color-ide-text)]" />
                <Bot v-else class="w-[18px] h-[18px] text-white" />
              </div>

              <!-- 气泡体 -->
              <div :class="['max-w-[85%] sm:max-w-[78%] min-w-0', msg.role === 'user' ? 'order-first' : '']">

                <!-- 用户消息气泡 -->
                <div v-if="msg.role === 'user'" class="rounded-2xl px-4 py-3 text-sm leading-relaxed bg-gradient-to-r from-brand-500 to-brand-600 text-white rounded-br-md whitespace-pre-wrap break-words">
                  {{ msg.content }}
                </div>

                <!-- Assistant 消息卡片 -->
                <div v-else class="rounded-2xl px-4 py-3.5 bg-surface-800/70 border border-[var(--color-ide-border)] text-sm">

                  <!-- 思考指示 -->
                  <div v-if="isLastAssistant(msg) && isStreaming && agentState === 'thinking'" class="mb-3 flex items-center gap-2 text-[13px] text-brand-400/60">
                    <Brain class="w-[18px] h-[18px] animate-pulse" />正在思考...
                  </div>

                  <!-- 🆕 推理步骤 (Cline 风格 step-by-step) -->
                  <AgentReasoningSteps
                    v-if="msg.reasoning_steps?.length"
                    :steps="msg.reasoning_steps"
                    :isStreaming="isStreaming && isLastAssistant(msg)"
                    class="mb-3"
                  />

                  <!-- ═══ 工具调用卡片组 ═══ -->
                  <div v-if="msg.tool_calls?.length" class="mb-3 space-y-2">
                    <div
                      v-for="tc in msg.tool_calls"
                      :key="tc.id"
                      class="tool-call-card"
                      :class="{ 'ring-1 ring-brand-500/15': !tc.result }"
                    >
                      <!-- 卡片头 -->
                      <button @click="toggleExpand(tc.id)" class="card-header">
                        <!-- 执行中动画 -->
                        <Loader2 v-if="tc.success === undefined" class="w-[16px] h-[16px] text-brand-400 animate-spin shrink-0" />
                        <Check v-else-if="tc.success" class="w-[16px] h-[16px] text-green-400 shrink-0" />
                        <X v-else class="w-[16px] h-[16px] text-red-400 shrink-0" />
                        <span class="card-name">{{ tc.name }}</span>
                        <!-- 折叠时显示结果缩略 -->
                        <span v-if="!expandedToolIds.has(tc.id) && tc.result" class="card-preview">{{
                          typeof tc.result === 'string' 
                            ? (() => { try { const p = JSON.parse(tc.result); return p.city ? `${p.city} ${p.temperature}\u00B0C ${p.condition || ''}` : p.error || p.result || '' } catch { return tc.result.slice(0, 40) } })()
                            : JSON.stringify(tc.result).slice(0, 40)
                        }}</span>
                        <span class="card-chevron" :class="{ rotated: expandedToolIds.has(tc.id) }">\u25B8</span>
                      </button>

                      <!-- 展开内容 -->
                      <div v-if="expandedToolIds.has(tc.id)" class="card-body">
                        <div v-if="tc.arguments && Object.keys(tc.arguments).length" class="card-section">
                          <span class="card-label">参数</span>
                          <code class="card-code">{{ typeof tc.arguments === 'string' ? tc.arguments : JSON.stringify(tc.arguments, null, 2) }}</code>
                        </div>
                        <div v-if="tc.result" class="card-section">
                          <span class="card-label" :class="tc.success ? 'text-green-400' : 'text-red-400'">结果</span>
                          <code :class="['card-code', tc.success ? '' : 'text-red-300']">{{ typeof tc.result === 'string' ? (() => { try { return JSON.stringify(JSON.parse(tc.result), null, 2) } catch { return tc.result } })() : JSON.stringify(tc.result, null, 2) }}</code>
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- 🆕 行内 Diff 展示 — 该消息相关的文件变更 -->
                  <div v-if="collectedDiffs.length > 0 && isLastAssistant(msg)" class="mb-3 space-y-2">
                    <DiffViewer
                      v-for="(d, di) in collectedDiffs"
                      :key="'diff-'+di"
                      :diff="d"
                      :collapsible="true"
                    />
                  </div>

                  <!-- 文字回复 -->
                  <div
                    v-if="msg.content"
                    class="whitespace-pre-wrap break-words text-[var(--color-ide-text)] leading-relaxed msg-content"
                  >
                    <template v-if="isLastAssistant(msg) && isStreaming && agentState === 'generating'">
                      {{ msg.content }}<span class="cursor-blink" />
                    </template>
                    <template v-else>{{ msg.content }}</template>
                  </div>

                  <!-- 处理中占位 -->
                  <div v-else-if="isLastAssistant(msg) && isStreaming && !msg.tool_calls?.length" class="flex items-center gap-2 text-[13px] text-[var(--color-ide-text-dim)] py-1">
                    <Loader2 class="w-[16px] h-[16px] animate-spin" /><span>正在处理...</span>
                  </div>

                  <!-- 错误重试栏 -->
                  <div v-if="msg.metadata?.error" class="mt-2 pt-2 border-t border-[var(--color-ide-border)] flex items-center gap-2">
                    <AlertCircle class="w-[16px] w-[16px] text-amber-400" />
                    <span class="text-[12px] text-amber-400/80">响应出错</span>
                    <button @click="retryMessage(msg)" class="retry-btn">
                      <RotateCcw class="w-[14px] h-[14px]" /> 重试
                    </button>
                  </div>

                  <!-- 元信息栏 -->
                  <div v-if="msg.metadata?.model_used && !msg.metadata.error" class="meta-bar">
                    <Cpu class="w-[14px] h-[14px]" />{{ msg.metadata.model_used }}
                    <template v-if="msg.metadata.provider">&nbsp;&middot;&nbsp;{{ msg.metadata.provider }}</template>
                    <template v-if="msg.metadata.turns">&nbsp;&middot;&nbsp;{{ msg.metadata.turns }}轮</template>
                    <template v-if="msg.metadata.latency_ms">&nbsp;&middot;&nbsp;{{ msg.metadata.latency_ms }}ms</template>
                    <button @click="copyText(msg.content)" class="copy-btn" title="复制"><Copy class="w-[14px] h-[14px]" /></button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 流式底部指示器 -->
            <div v-if="isStreaming" class="stream-indicator">
              <div class="dots">
                <span class="dot" /><span class="dot delay-1" /><span class="dot delay-2" />
              </div>
              <span class="text-[13px] text-[var(--color-ide-text-dim)]">
                <template v-if="agentState === 'thinking'">AI 正在思考...</template>
                <template v-else-if="agentState === 'calling_tools'">执行工具 &middot; 第 {{ currentTurn }}/{{ maxTurns }} 轮</template>
                <template v-else-if="agentState === 'generating'">生成回复中...</template>
                <template v-else>处理中...</template>
              </span>
            </div>
          </div>

          <!-- 底部输入区 -->
          <footer class="shrink-0 border-t border-[var(--color-ide-border)] bg-surface-900/50 backdrop-blur px-6 py-5">
            <div class="w-full mx-auto">
              <!-- 🆕 上下文文件标签 (Continue @-mention 风格) -->
              <div v-if="contextFiles.length > 0" class="flex flex-wrap gap-2 mb-3">
                <div
                  v-for="f in contextFiles"
                  :key="f.path"
                  class="flex items-center gap-2 px-2.5 py-1 rounded-full text-[13px] bg-brand-500/8 border border-brand-500/15 text-brand-400"
                >
                  <FileCode class="w-[14px] h-[14px]" />
                  {{ f.name }}
                  <button @click="removeContextFile(f.path)" class="hover:text-red-400 transition-colors">&times;</button>
                </div>
              </div>

              <div class="relative">
                <!-- 🆕 @-mention 弹窗 (Continue 风格) -->
                <AtMentionPopup
                  :show="showMentionPopup"
                  :files="contextFiles"
                  :filter="mentionFilter"
                  :loading="false"
                  @select="onMentionSelect"
                  @close="onMentionClose"
                />

                <textarea
                  ref="textareaEl"
                  v-model="inputText"
                  rows="1"
                  :placeholder="isStreaming ? 'AI 正在回复...' : '@ 引用文件  \u00B7  输入消息... Shift+Enter 换行'"
                  :disabled="isStreaming"
                  class="chat-textarea w-full"
                  @keydown="onInputKeydown"
                  @input="onInput"
                ></textarea>
                <div class="absolute right-3 bottom-2.5 flex items-center gap-3">
                  <button
                    v-if="isStreaming"
                    @click="stopGeneration()"
                    class="p-2.5 rounded-xl bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                    title="停止生成"
                  >
                    <Square class="w-[20px] h-[20px]" fill="currentColor" />
                  </button>
                  <button
                    v-else
                    @click="doSend()"
                    :disabled="!inputText.trim()"
                    class="send-btn"
                    title="发送 (Enter)"
                  >
                    <Send class="w-[20px] h-[20px]" />
                  </button>
                </div>
              </div>
              <div class="flex items-center justify-between mt-3.5 px-1">
                <div class="flex items-center gap-6 text-[13px] text-[var(--color-ide-text-dim)]">
                  <span>{{ messages.filter(m => m.role !== 'system').length }} 条消息</span>
                  <button v-if="messages.length > 1" @click="resetChat" class="hover:text-red-400 transition-colors flex items-center gap-2">
                    <Trash2 class="w-[16px] h-[16px]" /> 清空
                  </button>
                </div>
                <div class="text-[13px] text-[var(--color-ide-text-dim)]">Enter 发送 &middot; Shift+Enter 换行</div>
              </div>
            </div>
          </footer>
        </template>
      </main>

      <!-- ─── 右栏：工具调用 / 执行仪表盘 ─── -->
      <Transition name="slide-right">
        <aside v-if="showRightPanel" class="w-80 shrink-0 flex flex-col border-l border-[var(--color-ide-border)] bg-surface-900/40 overflow-hidden">
          <!-- 面板 Tab 切换 -->
          <div class="flex border-b border-[var(--color-ide-border)] shrink-0">
            <button
              @click="rightPanelTab = 'tools'"
              class="flex-1 flex items-center justify-center gap-2 py-2.5 text-[12px] font-medium transition-colors"
              :class="rightPanelTab === 'tools' ? 'text-brand-400 bg-brand-500/5 border-b border-brand-500/30' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
            >
              <Wrench class="w-[16px] w-[16px]" />工具调用
              <span v-if="currentToolCalls.length" class="text-[11px] px-1 rounded-full bg-brand-500/10">{{ currentToolCalls.length }}</span>
            </button>
            <button
              @click="rightPanelTab = 'dashboard'"
              class="flex-1 flex items-center justify-center gap-2 py-2.5 text-[12px] font-medium transition-colors"
              :class="rightPanelTab === 'dashboard' ? 'text-purple-400 bg-purple-500/5 border-b border-purple-500/30' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
            >
              <Zap class="w-[16px] w-[16px]" />仪表盘
              <span v-if="isStreaming" class="w-2 h-2 rounded-full bg-purple-400 animate-pulse" />
            </button>
          </div>

          <!-- 工具调用视图 -->
          <div v-if="rightPanelTab === 'tools'" class="flex-1 overflow-y-auto p-3 space-y-2 custom-scroll">
            <div v-if="currentToolCalls.length === 0" class="empty-panel">
              <Wrench class="w-8 h-8 opacity-20" />
              <p class="text-[13px]">暂无工具调用</p>
            </div>

            <div v-for="tc in currentToolCalls" :key="tc.id" class="rounded-xl bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)] overflow-hidden">
              <div class="flex items-center gap-2.5 px-3 py-2.5 border-b border-[var(--color-ide-border)]">
                <component :is="toolIcon(tc.name)" class="w-[18px] h-[18px] text-brand-400 shrink-0" />
                <span class="text-[13px] font-semibold text-[var(--color-ide-text)] truncate">{{ tc.name }}</span>
                <span class="ml-auto">
                  <Check v-if="tc.success === true" class="w-[18px] h-[18px] text-green-400" />
                  <Loader2 v-else-if="tc.success === undefined" class="w-[18px] h-[18px] text-brand-400 animate-spin" />
                  <X v-else class="w-[18px] h-[18px] text-red-400" />
                </span>
              </div>
              <div class="px-3 py-2 space-y-2">
                <div>
                  <p class="text-[10px] font-medium text-[var(--color-ide-text-dim)] mb-1">Arguments</p>
                  <pre class="panel-code">{{ JSON.stringify(tc.arguments, null, 2) }}</pre>
                </div>
                <div v-if="tc.result">
                  <p class="text-[10px] font-medium mb-1" :class="tc.success ? 'text-green-400/60' : 'text-red-400/60'">Result</p>
                  <pre :class="['panel-code', tc.success ? '' : 'text-red-300/80']">{{ typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2) }}</pre>
                </div>
              </div>
            </div>
          </div>

          <!-- 🆕 执行仪表盘视图 -->
          <div v-else class="flex-1 overflow-y-auto custom-scroll">
            <AgentRunDashboard
              :messages="messages"
              :isStreaming="isStreaming"
              :currentTurn="currentTurn"
              :maxTurns="maxTurns"
              :totalLatencyMs="totalLatencyMs"
              :modelUsed="lastModelUsed"
            />
          </div>
        </aside>
      </Transition>

      <!-- 🆕 右栏：Diff 面板（文件变更） -->
      <Transition name="slide-right">
        <aside v-if="showDiffPanel" class="w-80 shrink-0 flex flex-col border-l border-[var(--color-ide-border)] bg-surface-900/40 overflow-hidden">
          <div class="p-3 border-b border-[var(--color-ide-border)] flex items-center justify-between shrink-0">
            <h3 class="text-[13px] font-semibold text-[var(--color-ide-text)] uppercase tracking-wider">文件变更</h3>
            <span class="text-[11px] text-[var(--color-ide-text-dim)] tabular-nums">{{ collectedDiffs.length }} 个文件</span>
          </div>

          <div class="flex-1 overflow-y-auto p-3 space-y-2 custom-scroll">
            <div v-if="collectedDiffs.length === 0" class="empty-panel">
              <GitBranch class="w-8 h-8 opacity-20" />
              <p class="text-[13px]">暂无文件变更</p>
              <p class="text-[11px] text-[var(--color-ide-text-dim)] mt-1">AI 编辑文件后，diff 将自动显示</p>
            </div>

            <div v-for="(d, di) in collectedDiffs" :key="'dpanel-'+di" class="rounded-lg bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)] overflow-hidden text-[12px]">
              <div class="flex items-center gap-2.5 px-2.5 py-2 border-b border-[var(--color-ide-border)]">
                <FileCode class="w-[16px] h-[16px] text-emerald-400 shrink-0" />
                <span class="text-[13px] font-mono text-[var(--color-ide-text)] truncate">{{ d.file_name }}</span>
                <span class="ml-auto text-[11px] font-mono" :class="d.change_type === 'CREATE' ? 'text-emerald-400' : d.change_type === 'DELETE' ? 'text-red-400' : 'text-amber-400'">
                  +{{ d.lines_added }} &minus;{{ d.lines_removed }}
                </span>
              </div>
              <pre class="px-2.5 py-1.5 text-[11px] leading-relaxed overflow-x-auto text-[var(--color-ide-text-dim)] max-h-32 overflow-y-auto custom-scroll">{{ d.diff_text.slice(0, 500) }}{{ d.diff_text.length > 500 ? '\n...' : '' }}</pre>
            </div>
          </div>
        </aside>
      </Transition>

      <!-- 🆕 右栏：Agent 工作流图 (LangGraph 风格) -->
      <Transition name="slide-right">
        <aside v-if="showPipelinePanel" class="w-80 shrink-0 flex flex-col border-l border-[var(--color-ide-border)] bg-surface-900/40 overflow-hidden">
          <div class="p-3 border-b border-[var(--color-ide-border)] flex items-center justify-between shrink-0">
            <h3 class="text-[13px] font-semibold text-[var(--color-ide-text)] uppercase tracking-wider flex items-center gap-2.5">
              <GitFork class="w-[16px] w-[16px] text-purple-400" />
              工作流图
            </h3>
            <span class="text-[11px] text-[var(--color-ide-text-dim)] tabular-nums">{{ pipelineStages.length }} 节点</span>
          </div>

          <div class="flex-1 overflow-hidden">
            <WorkflowGraph
              :stages="pipelineStages"
              :isRunning="isStreaming"
              :currentTurn="currentTurn"
              :totalTurns="maxTurns"
              :totalLatencyMs="totalLatencyMs"
              @stageClick="(s: PipelineStage) => { expandedToolIds.add(s.id) }"
            />
          </div>
        </aside>
      </Transition>
    </div>
  </div>
</template>

<!-- isLastAssistant 已在主 <script setup> 中定义 -->

<style scoped>
/* ═══════════ 过渡动画 ════════════ */

.toast-enter-active, .toast-leave-active { transition: all 0.35s cubic-bezier(.4,0,.2,1); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-12px) translateX(-50%); }

.fade-enter-active, .fade-leave-active { transition: all 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; transform: translateY(-4px) scale(0.97); }

.slide-left-enter-active, .slide-left-leave-active,
.slide-right-enter-active, .slide-right-leave-active {
  transition: all .3s cubic-bezier(.4,0,.2,1);
}
.slide-left-enter-from, .slide-right-leave-to { width: 0; opacity: 0; margin-left: 0; }
.slide-left-enter-to, .slide-right-leave-from { width: 16rem; opacity: 1; }

/* ═══════════ 自定义滚动条 ════════════ */
.custom-scroll::-webkit-scrollbar { width: 4px; }
.custom-scroll::-webkit-scrollbar-track { background: transparent; }
.custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.06); border-radius: 9999px; }
.custom-scroll::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,.1); }

#chat-container::-webkit-scrollbar { width: 5px; }
#chat-container::-webkit-scrollbar-track { background: transparent; }
#chat-container::-webkit-scrollbar-thumb { background: rgba(255,255,255,.05); border-radius: 9999px; }
#chat-container::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,.09); }

/* ═══════════ 输入框样式 ════════════ */
.chat-textarea {
  width: 100%;
  background: var(--color-chat-input-bg, #3C3C3C);
  border: 1px solid transparent;
  border-radius: var(--radius-sm, 3px);
  padding: .875rem 5rem .875rem 1.15rem;
  font-size: .9rem;
  color: #fff;
  resize: none;
  outline: none;
  transition: all .2s;
  min-height: 52px;
  max-height: 160px;
  line-height: 1.5;
}
.chat-textarea::placeholder { color: rgba(204,204,204,.5); }
.chat-textarea:focus {
  border-color: var(--color-ide-border-focus);
  background: var(--color-chat-input-bg, #3C3C3C);
}
.chat-textarea:disabled { opacity: .5; cursor: not-allowed; }

.send-btn {
  padding: .625rem;
  border-radius: var(--radius-sm, 3px);
  background: var(--color-ide-accent);
  color: #fff;
  transition: all .15s;
}
.send-btn:hover:not(:disabled) { background: var(--color-ide-accent-hover); }
.send-btn:disabled { opacity: .3; cursor: default; }

/* ═══════════ 工具调用卡片 ════════════ */
.tool-call-card {
  border-radius: .5rem;
  background: rgba(0, 122, 204, 0.08);
  border: 1px solid rgba(0, 122, 204, 0.15);
  overflow: hidden;
  transition: all .2s;
}
.tool-call-card:hover { border-color: rgba(0, 122, 204, 0.30); }
.card-header {
  display: flex;
  align-items: center;
  gap: .625rem;
  width: 100%;
  padding: .5rem .75rem;
  cursor: pointer;
  background: transparent;
  border: none;
  color: inherit;
  font-size: inherit;
  text-align: left;
  transition: background .15s;
}
.card-header:hover { background: rgba(255,255,255,.03); }
.card-name { font-size: .75rem; font-weight: 600; color: rgb(199 210 254); white-space: nowrap; }
.card-preview {
  font-size: .7rem;
  color: rgb(148 163 184);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.card-chevron {
  font-size: .75rem;
  color: rgb(100 116 139);
  transition: transform .2s;
  flex-shrink: 0;
}
.card-chevron.rotated { transform: rotate(90deg); }
.card-body { padding: 0 .75rem .625rem; }
.card-section { margin-bottom: .5rem; }
.card-section:last-child { margin-bottom: 0; }
.card-label {
  display: block;
  font-size: .65rem;
  font-weight: 600;
  color: rgb(148 163 184);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: .25rem;
}
.card-code {
  display: block;
  font-size: .7rem;
  color: rgb(203 213 225);
  background: rgba(0,0,0,.3);
  border-radius: .375rem;
  padding: .5rem;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: ui-monospace, monospace;
  line-height: 1.5;
}

.card-body { border-top: 1px solid rgba(255,255,255,.03); }
.section { padding: .5rem .75rem; }
.section + .section { border-top: 1px dashed rgba(255,255,255,.04); }
.section .label { display: block; font-size: 10px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; color: rgb(107 114 128); margin-bottom: .375rem; }
.code-block {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  color: rgb(156 163 175);
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(0,0,0,.25);
  border-radius: .5rem;
  padding: .5rem .625rem;
  max-height: 192px;
  overflow-y: auto;
  line-height: 1.55;
}
.code-block.error-text { color: rgb(252 165 165 / .8); }

/* ═══════════ 消息内容 ════════════ */
.msg-content { }
.msg-content :deep(pre) { background: rgba(0,0,0,.3); border-radius: .5rem; padding: .75rem; font-size: .75rem; overflow-x: auto; }
.msg-content :deep(code) { color: rgb(165 180 252); }
.cursor-blink {
  display: inline-block;
  width: 6px;
  height: 1em;
  background: rgb(99 102 241 / .6);
  animation: blink 1s steps(2) infinite;
  vertical-align: text-bottom;
  margin-left: 2px;
}
@keyframes blink { to { opacity: 0; } }

/* ═══════════ 元信息栏 ════════════ */
.meta-bar {
  margin-top: .625rem;
  padding-top: .5rem;
  border-top: 1px solid rgba(255,255,255,.03);
  display: flex;
  align-items: center;
  gap: .5rem;
  font-size: 10px;
  color: rgb(75 85 99);
}
.meta-bar .copy-btn {
  margin-left: auto;
  padding: .25rem;
  border-radius: .375rem;
  color: rgb(107 114 128);
  transition: all .15s;
}
.meta-bar .copy-btn:hover { color: rgb(156 163 175); background: rgba(255,255,255,.05); }

/* ═══════════ 重试按钮 ════════════ */
.retry-btn {
  margin-left: auto;
  padding: .25rem .5rem;
  border-radius: .375rem;
  background: rgba(255,255,255,.04);
  font-size: 11px;
  color: rgb(156 163 175);
  display: inline-flex;
  align-items: center;
  gap: .375rem;
  transition: all .15s;
}
.retry-btn:hover { color: rgb(99 102 241); background: rgb(99 102 241 / .08); }

/* ═══════════ 流式指示器 ════════════ */
.stream-indicator {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding-left: 2.75rem;
  padding-top: .25rem;
}
.stream-indicator .dots { display: flex; gap: .25rem; }
.stream-indicator .dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: rgb(99 102 241);
  animation: pulse-dot 1.4s ease-in-out infinite;
}
.stream-indicator .dot.delay-1 { animation-delay: .16s; }
.stream-indicator .dot.delay-2 { animation-delay: .32s; }
@keyframes pulse-dot {
  0%, 80%, 100% { opacity: .3; transform: scale(.8); }
  40% { opacity: 1; transform: scale(1); }
}

/* ═══════════ 右侧面板代码块 ════════════ */
.panel-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 11px;
  color: rgb(156 163 175);
  white-space: pre-wrap;
  word-break: break-word;
  background: rgba(0,0,0,.2);
  border-radius: .5rem;
  padding: .5rem .625rem;
  max-height: 160px;
  overflow-y: auto;
  line-height: 1.5;
}
.empty-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4rem 0;
  color: rgb(55 65 81);
}
.empty-panel p { font-size: .75rem; margin-top: .5rem; }

/* ═══════════ 欢迎页样式 ═══════════ */
.welcome-textarea {
  width: 100%;
  background: var(--color-chat-input-bg, #3C3C3C);
  border: 1px solid transparent;
  border-radius: var(--radius-sm, 3px);
  padding: .875rem 4.2rem .875rem 1.15rem;
  font-size: .925rem;
  color: #fff;
  resize: none;
  outline: none;
  transition: all .25s cubic-bezier(.4,0,.2,1);
  min-height: 68px;
  max-height: 160px;
  line-height: 1.55;
  letter-spacing: .005em;
}
.welcome-textarea::placeholder { color: rgba(204,204,204,.5); }
.welcome-textarea:focus {
  border-color: var(--color-ide-border-focus);
  background: var(--color-chat-input-bg, #3C3C3C);
}
.kbd {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 22px; height: 20px; padding: 0 6px;
  border-radius: 5px;
  font-size: 11px; font-family: inherit; font-weight: 600;
  background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.1); color: rgba(156,163,175,.8);
  box-shadow: 0 1px 0 rgba(255,255,255,.04) inset;
}
</style>
