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
 *   SSE事件: turn_start → tool_call → tool_executing → tool_result → final_answer → done
 */

import {
  Brain,
  FileCode,
  Globe,
  Search,
  Terminal,
  Wrench,
} from "lucide-vue-next"
import { computed, nextTick, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { agentChatStreamUrl } from "@/api/agent"
import type {
  ChatMessage,
  DiffData,
  ModelOption,
  SSEEvent,
  SSEEventType,
  ToolCallRecord,
} from "@/types/studio"

// ════════════════════════════════════════════════
// 路由 & 项目上下文
// ════════════════════════════════════════════════
const route = useRoute()
const _projectId = computed(() => route.params.id as string | undefined)

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

// 模式选择
const chatMode = ref<"craft" | "ask" | "plan" | "agent">("craft")
const preferredModel = ref("")
const availableModels = ref<ModelOption[]>([])
const showModelPicker = ref(false)

// 面板开关 — 默认为 true，独立 /chat 页面直接显示对话界面
const hasStarted = ref(true)
const _showRightPanel = ref(false)
const showHistoryPanel = ref(false)

// 工具调用展开 ID 集合
const expandedToolIds = ref<Set<string>>(new Set())

// 🆕 Diff 数据收集
const collectedDiffs = ref<DiffData[]>([])
const showDiffPanel = ref(false)

// 输入框
const inputText = ref("")
const textareaEl = ref<HTMLTextAreaElement | null>(null)

// Toast 提示
const toastMsg = ref("")
let toastTimer: ReturnType<typeof setTimeout> | null = null

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

function _selectModel(name: string) {
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

function _toggleExpand(id: string) {
  const s = expandedToolIds.value
  s.has(id) ? s.delete(id) : s.add(id)
}

/** 根据工具名推断图标组件 */
function _toolIcon(name: string) {
  const n = name.toLowerCase()
  if (/read|search|find|list|grep/.test(n)) return Search
  if (/write|edit|replace|create|delete|save/.test(n)) return FileCode
  if (/bash|exec|shell|git|run|command/.test(n)) return Terminal
  if (/web|fetch|http|url|browse/.test(n)) return Globe
  if (/think|reason|reflect/.test(n)) return Brain
  return Wrench
}

function _formatTime(iso: string): string {
  const d = new Date(iso)
  const diff = Date.now() - d.getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return "刚刚"
  if (min < 60) return `${min}分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}小时前`
  return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" })
}

function _copyText(t: string) {
  navigator.clipboard
    .writeText(t)
    .then(() => showToast("已复制"))
    .catch(() => {})
}

/** 判断消息是否为当前最后一条助手消息（用于流式动画定位） */
function _isLastAssistant(msg: ChatMessage): boolean {
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
function _newChat() {
  saveCurrentSession()
  messages.value = []
  sessionId.value = crypto.randomUUID()
  agentState.value = "idle"
  currentToolCalls.value = []
  collectedDiffs.value = []
  showDiffPanel.value = false
  totalLatencyMs.value = 0
  showHistoryPanel.value = false
  inputText.value = ""
}

function _switchToSession(s: ChatSession) {
  saveCurrentSession()
  sessionId.value = s.id
  messages.value = []
  hasStarted.value = true
  chatMode.value = (s.agentMode as any) || "craft"
  showHistoryPanel.value = false
  showToast(`已切换到「${s.title}」`)
}

function _deleteSession(id: string, e: Event) {
  e.stopPropagation()
  sessions.value = sessions.value.filter((s) => s.id !== id)
  persistSessions()
}

function _resetChat() {
  messages.value = []
  sessionId.value = crypto.randomUUID()
  agentState.value = "idle"
  currentToolCalls.value = []
  collectedDiffs.value = []
  showDiffPanel.value = false
  totalLatencyMs.value = 0
  showToast("已清空对话")
  scrollToBottom()
}

// ════════════════════════════════════════════════
// 启动聊天 / 快捷提示
// ════════════════════════════════════════════════
function _startChat() {
  hasStarted.value = true
  setTimeout(() => textareaEl.value?.focus(), 80)
}

function _quickPrompt(text: string) {
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

  const ctrl = new AbortController()
  abortController.value = ctrl

  try {
    const token = localStorage.getItem("token")
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    }
    if (token) headers.Authorization = `Bearer ${token}`

    const res = await fetch(agentChatStreamUrl(), {
      method: "POST",
      headers,
      body: JSON.stringify({
        message: content,
        agent_name: chatMode.value === "agent" ? "agent" : "default",
        instructions: "",
        max_turns:
          chatMode.value === "plan" ? 15 : chatMode.value === "ask" ? 5 : 10,
        preferred_model: preferredModel.value || undefined,
        session_id: sessionId.value,
      }),
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

/** SSE 事件分发器 —— 状态机驱动 UI 更新 */
function dispatchEvent(msg: ChatMessage, ev: SSEEvent) {
  switch (ev.type as SSEEventType) {
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
              ? (() => {
                  try {
                    return JSON.parse(tc.arguments)
                  } catch {
                    return {}
                  }
                })()
              : tc.arguments || {},
        }
        currentToolCalls.value.push(record)
        msg.tool_calls = msg.tool_calls || []
        msg.tool_calls.push({ ...record })
        expandedToolIds.value.add(record.id)
      }
      break
    }

    case "tool_executing":
      agentState.value = "calling_tools"
      break

    case "tool_result": {
      const name = ev.tool_name || ""
      const match = [...currentToolCalls.value]
        .reverse()
        .find((tc) => tc.name === name && !tc.result)
      if (match) {
        match.result = ev.result || ""
        match.success = ev.success ?? false
        const mTc = msg.tool_calls?.find((t) => t.id === match.id)
        if (mTc) {
          mTc.result = match.result
          mTc.success = match.success
        }
      }
      break
    }

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
      break
  }
}

// ════════════════════════════════════════════════
// 操作：停止 / 重试
// ════════════════════════════════════════════════
function _stopGeneration() {
  abortController.value?.abort()
}

async function _retryMessage(targetMsg: ChatMessage) {
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
function _onInputKeydown(e: KeyboardEvent) {
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
    <header class="shrink-0 h-14 border-b border-white/[0.06] bg-surface-900/70 backdrop-blur-md flex items-center justify-between px-4 gap-3 z-30">

      <!-- 左区：历史 + Agent 状态 -->
      <div class="flex items-center gap-3 min-w-0">
        <!-- 历史面板开关 -->
        <button
          @click="showHistoryPanel = !showHistoryPanel"
          :class="['p-2 rounded-xl transition-all duration-200 shrink-0', showHistoryPanel ? 'bg-brand-500/10 text-brand-400' : 'text-gray-500 hover:text-gray-300 hover:bg-white/5']"
          title="对话历史"
        >
          <History class="w-[18px] h-[18px]" />
        </button>

        <!-- Agent 状态指示灯 -->
        <div class="flex items-center gap-2">
          <span :class="['w-2 h-2 rounded-full transition-colors duration-300', isStreaming ? 'bg-brand-400 animate-pulse' : 'bg-gray-600']" />
          <span class="text-sm font-medium truncate hidden sm:inline">
            <template v-if="isStreaming">
              <template v-if="agentState === 'thinking'">思考中</template>
              <template v-else-if="agentState === 'calling_tools'">调用工具</template>
              <template v-else-if="agentState === 'generating'">生成回复</template>
            </template>
            <template v-else>Agent 对话</template>
          </span>
          <span v-if="isStreaming" class="text-[11px] text-gray-500 tabular-nums hidden md:inline">
            R{{ currentTurn }}/{{ maxTurns }}
          </span>
        </div>

        <!-- 模式标签组 -->
        <div class="hidden sm:flex items-center gap-0.5 ml-1">
          <button
            v-for="m in ([
              {v:'craft', l:'Craft'},
              {v:'ask', l:'Ask'},
              {v:'plan', l:'Plan'},
              {v:'agent', l:'Agent'},
            ] as const)"
            :key="m.v"
            @click="chatMode = m.v"
            :class="[
              'px-2 py-0.5 rounded-md text-[11px] font-medium cursor-pointer transition-all duration-150',
              chatMode === m.v ? 'bg-brand-500/12 text-brand-400' : 'text-gray-600 hover:text-gray-400'
            ]"
          >{{ m.l }}</button>
        </div>
      </div>

      <!-- 右区：模型 + 统计 + 操作 -->
      <div class="flex items-center gap-2 shrink-0">
        <!-- 模型选择器 -->
        <div class="relative hidden sm:block" data-model-picker>
          <button
            @click="showModelPicker = !showModelPicker"
            class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/[0.03] border border-white/[0.06] text-[11px] text-gray-400 hover:text-gray-200 hover:border-white/[0.12] transition-all cursor-pointer"
            title="切换模型"
          >
            <Cpu class="w-3 h-3" :class="preferredModel ? 'text-brand-400' : 'text-purple-400/50'" />
            <span class="max-w-[120px] truncate">{{ preferredModel || (lastModelUsed || '自动选择') }}</span>
            <ChevronRight class="w-3 h-3 transition-transform duration-200" :class="{ 'rotate-90': showModelPicker }" />
          </button>

          <!-- 下拉面板 -->
          <Transition name="fade">
            <!-- 遮罩层：点击关闭 -->
            <div
              v-if="showModelPicker"
              class="fixed inset-0 z-40"
              @click="showModelPicker = false"
            />
          </Transition>
          <Transition name="fade">
            <div
              v-if="showModelPicker"
              class="absolute right-0 top-full mt-1.5 w-72 rounded-xl bg-surface-950/95 backdrop-blur-xl border border-white/[0.08] shadow-2xl z-50 overflow-hidden"
              @click.stop
            >
              <div class="p-2 border-b border-white/[0.06] flex items-center justify-between">
                <span class="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">可用模型</span>
                <span class="text-[10px] text-gray-600">{{ availableModels.length }} 个</span>
              </div>

              <!-- 自动选择选项 -->
              <button
                @click="selectModel('')"
                class="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-white/[0.04] transition-colors group"
                :class="!preferredModel ? 'bg-brand-500/8 text-brand-300' : 'text-gray-400'"
              >
                <Zap class="w-4 h-4 shrink-0" :class="!preferredModel ? 'text-brand-400' : 'text-gray-600 group-hover:text-gray-400'" />
                <div class="min-w-0 flex-1">
                  <div class="text-xs font-medium truncate">自动选择</div>
                  <div class="text-[10px] text-gray-600 truncate">由调度器根据能力自动分配</div>
                </div>
                <Check v-if="!preferredModel" class="w-3.5 h-3.5 text-brand-400 shrink-0" />
              </button>

              <!-- 本地模型分组 -->
              <template v-if="availableModels.filter(m => m.is_local).length > 0">
                <div class="px-3 py-1.5 text-[10px] font-semibold text-emerald-400/70 uppercase tracking-wider flex items-center gap-1.5">
                  <Sparkles class="w-3 h-3" /> 本地模型
                </div>
                <div class="max-h-40 overflow-y-auto custom-scroll">
                  <button
                    v-for="m in availableModels.filter(m => m.is_local)"
                    :key="m.name"
                    @click="selectModel(m.name)"
                    class="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-white/[0.04] transition-colors group"
                    :class="preferredModel === m.name ? 'bg-brand-500/8 text-brand-300' : 'text-gray-400'"
                  >
                    <Cpu class="w-4 h-4 shrink-0" :class="preferredModel === m.name ? 'text-brand-400' : 'text-emerald-500/60 group-hover:text-emerald-400'" />
                    <div class="min-w-0 flex-1">
                      <div class="text-xs font-medium truncate">{{ m.display_name || m.name }}</div>
                      <div class="flex items-center gap-1.5">
                        <span v-if="m.is_downloaded !== false" class="text-[10px] text-emerald-500/70">已就绪</span>
                        <span v-else class="text-[10px] text-amber-500/70">未下载</span>
                        <span v-if="m.format" class="text-[10px] text-gray-600">{{ m.format }}</span>
                        <span class="text-[10px] text-gray-700">{{ m.capability }}</span>
                      </div>
                    </div>
                    <Check v-if="preferredModel === m.name" class="w-3.5 h-3.5 text-brand-400 shrink-0" />
                  </button>
                </div>
              </template>

              <!-- 远程 API 模型分组 -->
              <template v-if="availableModels.filter(m => !m.is_local).length > 0">
                <div class="px-3 py-1.5 text-[10px] font-semibold text-blue-400/70 uppercase tracking-wider flex items-center gap-1.5">
                  <Globe class="w-3 h-3" /> 远程 API
                </div>
                <div class="max-h-40 overflow-y-auto custom-scroll">
                  <button
                    v-for="m in availableModels.filter(m => !m.is_local)"
                    :key="m.name"
                    @click="selectModel(m.name)"
                    class="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-white/[0.04] transition-colors group"
                    :class="preferredModel === m.name ? 'bg-brand-500/8 text-brand-300' : 'text-gray-400'"
                  >
                    <Globe class="w-4 h-4 shrink-0" :class="preferredModel === m.name ? 'text-brand-400' : 'text-blue-500/60 group-hover:text-blue-400'" />
                    <div class="min-w-0 flex-1">
                      <div class="text-xs font-medium truncate">{{ m.display_name || m.name }}</div>
                      <div class="flex items-center gap-1.5">
                        <span v-if="m.provider" class="text-[10px] text-blue-400/60">{{ m.provider }}</span>
                        <span class="text-[10px] text-gray-600">{{ m.capability }}</span>
                        <span class="text-[10px] text-gray-700">p{{ m.priority }}</span>
                      </div>
                    </div>
                    <Check v-if="preferredModel === m.name" class="w-3.5 h-3.5 text-brand-400 shrink-0" />
                  </button>
                </div>
              </template>

              <div v-if="availableModels.length === 0" class="px-4 py-6 text-center text-[11px] text-gray-600">
                暂无可用模型
              </div>
            </div>
          </Transition>
        </div>

        <!-- 延迟 -->
        <span v-if="totalLatencyMs > 0 && !isStreaming" class="hidden md:inline-flex items-center gap-1 text-[11px] text-gray-600">
          <Clock class="w-3 h-3" />{{ totalLatencyMs }}ms
        </span>

        <!-- 工具面板开关 -->
        <button
          :class="['p-2 rounded-xl transition-all duration-200', showRightPanel ? 'text-brand-400 bg-brand-500/10' : 'text-gray-500 hover:text-gray-300 hover:bg-white/5']"
          @click="showRightPanel = !showRightPanel"
          title="工具调用详情"
        >
          <PanelRightOpen v-if="!showRightPanel" class="w-[18px] h-[18px]" />
          <PanelRightClose v-else class="w-[18px] h-[18px]" />
        </button>

        <!-- 🆕 Diff 面板开关 -->
        <button
          :class="[
            'p-2 rounded-xl transition-all duration-200 relative',
            showDiffPanel ? 'text-emerald-400 bg-emerald-500/10' : 'text-gray-500 hover:text-gray-300 hover:bg-white/5'
          ]"
          @click="showDiffPanel = !showDiffPanel"
          title="文件变更 (Diff)"
        >
          <GitBranch class="w-[18px] h-[18px]" />
          <span
            v-if="collectedDiffs.length > 0 && !showDiffPanel"
            class="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-emerald-500 text-[9px] font-bold text-white flex items-center justify-center"
          >{{ collectedDiffs.length }}</span>
        </button>

        <!-- 新建对话 -->
        <button @click="newChat" class="p-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-all duration-200" title="新建对话">
          <Plus class="w-[18px] h-[18px]" />
        </button>
      </div>
    </header>

    <!-- ═════ 主体三栏布局 ═════ -->
    <div class="flex flex-1 min-h-0 overflow-hidden">

      <!-- ─── 左栏：会话历史 ─── -->
      <Transition name="slide-left">
        <aside v-if="showHistoryPanel" class="w-64 shrink-0 flex flex-col border-r border-white/[0.06] bg-surface-900/40 overflow-hidden">
          <div class="p-3 border-b border-white/[0.06] flex items-center justify-between shrink-0">
            <h3 class="text-xs font-semibold text-gray-300 uppercase tracking-wider">对话历史</h3>
            <button @click="newChat()" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 hover:text-brand-400 transition-colors" title="新建对话"><Plus class="w-3.5 h-3.5" /></button>
          </div>
          <div class="flex-1 overflow-y-auto p-2 space-y-0.5 custom-scroll">

            <button
              @click="newChat()"
              class="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl text-sm text-gray-400 hover:text-white hover:bg-white/[0.04] transition-all group"
            >
              <MessageSquare class="w-4 h-4 text-gray-500 group-hover:text-brand-400 transition-colors" />
              新建对话
            </button>

            <div class="pt-2 pb-1 px-3 text-[10px] font-semibold text-gray-600 uppercase tracking-wider">最近会话</div>

            <button
              v-for="sess in sessions.slice(0, 20)"
              :key="sess.id"
              @click="switchToSession(sess)"
              :class="[
                'w-full text-left px-3 py-2 rounded-lg transition-all duration-150 group',
                sess.id === sessionId ? 'bg-brand-500/8 text-brand-300 ring-1 ring-brand-500/10' : 'text-gray-400 hover:bg-white/[0.03] hover:text-gray-200'
              ]"
            >
              <div class="flex items-start gap-2">
                <MessageSquare :class="['w-3.5 h-3.5 mt-0.5 shrink-0', sess.id === sessionId ? 'text-brand-400' : 'text-gray-600']" />
                <div class="min-w-0 flex-1">
                  <p class="text-xs truncate leading-relaxed">{{ sess.title }}</p>
                  <p class="text-[10px] text-gray-600 mt-0.5 flex items-center gap-1.5">
                    <Clock class="w-2.5 h-2.5 opacity-60" />{{ formatTime(sess.createdAt) }}
                    <span>· {{ sess.messageCount }}条</span>
                  </p>
                </div>
                <button
                  @click="deleteSession(sess.id, $event)"
                  class="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-500/10 text-gray-600 hover:text-red-400 transition-all shrink-0"
                  title="删除"
                ><Trash2 class="w-3 h-3" /></button>
              </div>
            </button>

            <div v-if="sessions.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-700">
              <MessageSquare class="w-8 h-8 mb-2 opacity-20" />
              <p class="text-xs">暂无历史对话</p>
            </div>
          </div>
        </aside>
      </Transition>

      <!-- ─── 中间：对话区域 ─── -->
      <main class="flex-1 flex flex-col min-w-0">

        <!-- ===== 欢迎页 ===== -->
        <section v-if="!hasStarted" class="flex-1 flex flex-col">
          <div class="flex-1 flex flex-col items-center justify-center px-6 overflow-y-auto">
            <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-brand-500/20 to-purple-500/10 border border-brand-500/20 flex items-center justify-center mb-6">
              <Bot class="w-8 h-8 text-brand-400" />
            </div>
            <h2 class="text-xl font-bold text-white mb-2">AI Agent 助手</h2>
            <p class="text-sm text-gray-500 mb-8 text-center max-w-md leading-relaxed">我可以帮你搜索信息、读写文件、执行命令、生成代码。输入需求即可开始。</p>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full max-w-lg">
              <button
                v-for="(prompt, i) in [
                  '帮我分析当前项目的代码结构',
                  '搜索项目中所有 API 路由定义',
                  '帮我写一个单元测试',
                  '解释这段代码的作用',
                ]"
                :key="i"
                @click="quickPrompt(prompt)"
                class="text-left px-4 py-3 rounded-xl bg-white/[0.02] border border-white/[0.06] text-sm text-gray-300 hover:bg-white/[0.05] hover:border-brand-500/20 hover:text-brand-300 transition-all duration-200 group"
              >
                <Sparkles class="w-4 h-4 inline mr-2 text-brand-500/50 group-hover:text-brand-400 transition-colors" />
                {{ prompt }}
              </button>
            </div>
          </div>

          <!-- 底部输入 -->
          <div class="shrink-0 border-t border-white/[0.06] p-4 bg-surface-900/30">
            <div class="w-full mx-auto max-w-3xl">
              <div class="relative">
                <textarea
                  ref="textareaEl"
                  v-model="inputText"
                  rows="1"
                  placeholder="描述你想让 AI 做什么..."
                  class="chat-textarea w-full"
                  @keydown="onInputKeydown"
                ></textarea>
                <div class="absolute right-2 bottom-2 flex items-center gap-1.5">
                  <button
                    @click="doSend()"
                    :disabled="!inputText.trim()"
                    class="p-2 rounded-xl bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-30 disabled:hover:bg-brand-500 transition-colors shadow-lg shadow-brand-500/20"
                    title="发送"
                  >
                    <Send class="w-4 h-4" />
                  </button>
                </div>
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
              <div class="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-cyan-500/6 border border-cyan-500/12 text-xs text-cyan-300/80">
                <Zap class="w-3.5 h-3.5" />{{ msg.content }}
              </div>
            </div>

            <!-- User / Assistant 消息对 -->
            <div
              v-for="msg in messages.filter(m => m.role !== 'system')"
              :key="msg.id"
              :class="['flex gap-3', msg.role === 'user' ? 'justify-end' : 'justify-start']"
            >
              <!-- Avatar -->
              <div :class="[
                'w-8 h-8 rounded-xl flex items-center justify-center shrink-0 mt-0.5',
                msg.role === 'user' ? 'bg-surface-700 order-last' :
                'bg-gradient-to-br from-brand-500 to-purple-600'
              ]">
                <User v-if="msg.role === 'user'" class="w-4 h-4 text-gray-300" />
                <Bot v-else class="w-4 h-4 text-white" />
              </div>

              <!-- 气泡体 -->
              <div :class="['max-w-[85%] sm:max-w-[78%] min-w-0', msg.role === 'user' ? 'order-first' : '']">

                <!-- 用户消息气泡 -->
                <div v-if="msg.role === 'user'" class="rounded-2xl px-4 py-3 text-sm leading-relaxed bg-gradient-to-r from-brand-500 to-brand-600 text-white rounded-br-md whitespace-pre-wrap break-words">
                  {{ msg.content }}
                </div>

                <!-- Assistant 消息卡片 -->
                <div v-else class="rounded-2xl px-4 py-3.5 bg-surface-800/70 border border-white/[0.04] text-sm">

                  <!-- 思考指示 -->
                  <div v-if="isLastAssistant(msg) && isStreaming && agentState === 'thinking'" class="mb-3 flex items-center gap-2 text-xs text-brand-400/60">
                    <Brain class="w-3.5 h-3.5 animate-pulse" />正在思考...
                  </div>

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
                        <component :is="toolIcon(tc.name)" class="icon" />
                        <span class="name truncate">{{ tc.name }}</span>

                        <!-- 状态图标 -->
                        <span v-if="tc.success === true" class="status-icon success"><Check class="w-3.5 h-3.5" /></span>
                        <Loader2 v-else-if="tc.success === undefined" class="status-icon spinning text-brand-400 animate-spin" />
                        <X v-else class="status-icon error" />

                        <ChevronRight :class="['chevron', expandedToolIds.has(tc.id) && 'rotated']" />
                      </button>

                      <!-- 展开内容 -->
                      <div v-if="expandedToolIds.has(tc.id)" class="card-body">
                        <div v-if="tc.arguments && Object.keys(tc.arguments).length" class="section">
                          <span class="label">参数 Arguments</span>
                          <pre class="code-block">{{ JSON.stringify(tc.arguments, null, 2) }}</pre>
                        </div>
                        <div v-if="tc.result" class="section">
                          <span class="label" :class="tc.success ? 'text-green-400/60' : 'text-red-400/60'">结果 Result</span>
                          <pre :class="['code-block', tc.success ? '' : 'error-text']">{{ typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2) }}</pre>
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
                    class="whitespace-pre-wrap break-words text-gray-200 leading-relaxed msg-content"
                  >
                    <template v-if="isLastAssistant(msg) && isStreaming && agentState === 'generating'">
                      {{ msg.content }}<span class="cursor-blink" />
                    </template>
                    <template v-else>{{ msg.content }}</template>
                  </div>

                  <!-- 处理中占位 -->
                  <div v-else-if="isLastAssistant(msg) && isStreaming && !msg.tool_calls?.length" class="flex items-center gap-2 text-xs text-gray-500 py-1">
                    <Loader2 class="w-3.5 h-3.5 animate-spin" /><span>正在处理...</span>
                  </div>

                  <!-- 错误重试栏 -->
                  <div v-if="msg.metadata?.error" class="mt-2 pt-2 border-t border-white/[0.03] flex items-center gap-2">
                    <AlertCircle class="w-3.5 h-3.5 text-amber-400" />
                    <span class="text-[11px] text-amber-400/80">响应出错</span>
                    <button @click="retryMessage(msg)" class="retry-btn">
                      <RotateCcw class="w-3 h-3" /> 重试
                    </button>
                  </div>

                  <!-- 元信息栏 -->
                  <div v-if="msg.metadata?.model_used && !msg.metadata.error" class="meta-bar">
                    <Cpu class="w-3 h-3" />{{ msg.metadata.model_used }}
                    <template v-if="msg.metadata.provider">&nbsp;·&nbsp;{{ msg.metadata.provider }}</template>
                    <template v-if="msg.metadata.turns">&nbsp;·&nbsp;{{ msg.metadata.turns }}轮</template>
                    <template v-if="msg.metadata.latency_ms">&nbsp;·&nbsp;{{ msg.metadata.latency_ms }}ms</template>
                    <button @click="copyText(msg.content)" class="copy-btn" title="复制"><Copy class="w-3 h-3" /></button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 流式底部指示器 -->
            <div v-if="isStreaming" class="stream-indicator">
              <div class="dots">
                <span class="dot" /><span class="dot delay-1" /><span class="dot delay-2" />
              </div>
              <span class="text-xs text-gray-500">
                <template v-if="agentState === 'thinking'">AI 正在思考...</template>
                <template v-else-if="agentState === 'calling_tools'">执行工具 · 第 {{ currentTurn }}/{{ maxTurns }} 轮</template>
                <template v-else-if="agentState === 'generating'">生成回复中...</template>
                <template v-else>处理中...</template>
              </span>
            </div>
          </div>

          <!-- 底部输入区 -->
          <footer class="shrink-0 border-t border-white/[0.06] bg-surface-900/50 backdrop-blur p-4">
            <div class="w-full mx-auto">
              <div class="relative">
                <textarea
                  ref="textareaEl"
                  v-model="inputText"
                  rows="1"
                  :placeholder="isStreaming ? 'AI 正在回复...' : '输入消息... Shift+Enter 换行'"
                  :disabled="isStreaming"
                  class="chat-textarea w-full"
                  @keydown="onInputKeydown"
                ></textarea>
                <div class="absolute right-2 bottom-2 flex items-center gap-1.5">
                  <button
                    v-if="isStreaming"
                    @click="stopGeneration()"
                    class="p-2 rounded-xl bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                    title="停止生成"
                  >
                    <Square class="w-4 h-4" fill="currentColor" />
                  </button>
                  <button
                    v-else
                    @click="doSend()"
                    :disabled="!inputText.trim()"
                    class="send-btn"
                    title="发送 (Enter)"
                  >
                    <Send class="w-4 h-4" />
                  </button>
                </div>
              </div>
              <div class="flex items-center justify-between mt-2 px-1">
                <div class="flex items-center gap-3 text-[10px] text-gray-600">
                  <span>{{ messages.filter(m => m.role !== 'system').length }} 条消息</span>
                  <button v-if="messages.length > 1" @click="resetChat" class="hover:text-red-400 transition-colors flex items-center gap-1">
                    <Trash2 class="w-3 h-3" /> 清空
                  </button>
                </div>
                <div class="text-[10px] text-gray-700">Enter 发送 · Shift+Enter 换行</div>
              </div>
            </div>
          </footer>
        </template>
      </main>

      <!-- ─── 右栏：工具调用详情面板 ─── -->
      <Transition name="slide-right">
        <aside v-if="showRightPanel" class="w-80 shrink-0 flex flex-col border-l border-white/[0.06] bg-surface-900/40 overflow-hidden">
          <div class="p-3 border-b border-white/[0.06] flex items-center justify-between shrink-0">
            <h3 class="text-xs font-semibold text-gray-300 uppercase tracking-wider">工具调用</h3>
            <span class="text-[10px] text-gray-600 tabular-nums">{{ currentToolCalls.length }} 次</span>
          </div>

          <div class="flex-1 overflow-y-auto p-3 space-y-2 custom-scroll">
            <div v-if="currentToolCalls.length === 0" class="empty-panel">
              <Wrench class="w-8 h-8 opacity-20" />
              <p class="text-xs">暂无工具调用</p>
            </div>

            <div v-for="tc in currentToolCalls" :key="tc.id" class="rounded-xl bg-white/[0.02] border border-white/[0.05] overflow-hidden">
              <div class="flex items-center gap-2 px-3 py-2.5 border-b border-white/[0.03]">
                <component :is="toolIcon(tc.name)" class="w-4 h-4 text-brand-400 shrink-0" />
                <span class="text-xs font-semibold text-gray-200 truncate">{{ tc.name }}</span>
                <span class="ml-auto">
                  <Check v-if="tc.success === true" class="w-4 h-4 text-green-400" />
                  <Loader2 v-else-if="tc.success === undefined" class="w-4 h-4 text-brand-400 animate-spin" />
                  <X v-else class="w-4 h-4 text-red-400" />
                </span>
              </div>
              <div class="px-3 py-2 space-y-2">
                <div>
                  <p class="text-[10px] font-medium text-gray-500 mb-1">Arguments</p>
                  <pre class="panel-code">{{ JSON.stringify(tc.arguments, null, 2) }}</pre>
                </div>
                <div v-if="tc.result">
                  <p class="text-[10px] font-medium mb-1" :class="tc.success ? 'text-green-400/60' : 'text-red-400/60'">Result</p>
                  <pre :class="['panel-code', tc.success ? '' : 'text-red-300/80']">{{ typeof tc.result === 'string' ? tc.result : JSON.stringify(tc.result, null, 2) }}</pre>
                </div>
              </div>
            </div>
          </div>
        </aside>
      </Transition>

      <!-- 🆕 右栏：Diff 面板（文件变更） -->
      <Transition name="slide-right">
        <aside v-if="showDiffPanel" class="w-80 shrink-0 flex flex-col border-l border-white/[0.06] bg-surface-900/40 overflow-hidden">
          <div class="p-3 border-b border-white/[0.06] flex items-center justify-between shrink-0">
            <h3 class="text-xs font-semibold text-gray-300 uppercase tracking-wider">文件变更</h3>
            <span class="text-[10px] text-gray-600 tabular-nums">{{ collectedDiffs.length }} 个文件</span>
          </div>

          <div class="flex-1 overflow-y-auto p-3 space-y-2 custom-scroll">
            <div v-if="collectedDiffs.length === 0" class="empty-panel">
              <GitBranch class="w-8 h-8 opacity-20" />
              <p class="text-xs">暂无文件变更</p>
              <p class="text-[10px] text-gray-600 mt-1">AI 编辑文件后，diff 将自动显示</p>
            </div>

            <div v-for="(d, di) in collectedDiffs" :key="'dpanel-'+di" class="rounded-lg bg-white/[0.02] border border-white/[0.05] overflow-hidden text-[11px]">
              <div class="flex items-center gap-2 px-2.5 py-2 border-b border-white/[0.03]">
                <FileCode class="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                <span class="text-xs font-mono text-gray-200 truncate">{{ d.file_name }}</span>
                <span class="ml-auto text-[10px] font-mono" :class="d.change_type === 'CREATE' ? 'text-emerald-400' : d.change_type === 'DELETE' ? 'text-red-400' : 'text-amber-400'">
                  +{{ d.lines_added }} −{{ d.lines_removed }}
                </span>
              </div>
              <pre class="px-2.5 py-1.5 text-[11px] leading-relaxed overflow-x-auto text-gray-400 max-h-32 overflow-y-auto custom-scroll">{{ d.diff_text.slice(0, 500) }}{{ d.diff_text.length > 500 ? '\n...' : '' }}</pre>
            </div>
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
  background: rgba(255,255,255,.03);
  border: 1px solid rgba(255,255,255,.08);
  border-radius: 1rem;
  padding: .75rem 4rem .75rem 1rem;
  font-size: .875rem;
  color: #fff;
  resize: none;
  outline: none;
  transition: all .2s;
  min-height: 48px;
  max-height: 160px;
  line-height: 1.5;
}
.chat-textarea::placeholder { color: rgba(255,255,255,.25); }
.chat-textarea:focus {
  border-color: rgba(99,102,241,.35);
  box-shadow: 0 0 0 1px rgba(99,102,241,.15);
  background: rgba(255,255,255,.04);
}
.chat-textarea:disabled { opacity: .5; cursor: not-allowed; }

.send-btn {
  padding: .5rem;
  border-radius: .75rem;
  background: #4f46e5;
  color: #fff;
  transition: all .2s;
}
.send-btn:hover:not(:disabled) { background: #4338ca; }
.send-btn:disabled { opacity: .3; cursor: default; }

/* ═══════════ 工具调用卡片 ════════════ */
.tool-call-card {
  border-radius: .75rem;
  background: rgba(0,0,0,.25);
  border: 1px solid rgba(255,255,255,.05);
  overflow: hidden;
  transition: all .2s;
}
.card-header {
  display: flex;
  align-items: center;
  gap: .5rem;
  width: 100%;
  padding: .625rem .75rem;
  cursor: pointer;
  background: transparent;
  border: none;
  color: inherit;
  font-size: inherit;
  text-align: left;
  transition: background .15s;
}
.card-header:hover { background: rgba(255,255,255,.02); }
.card-header .icon { width: 14px; height: 14px; flex-shrink: 0; color: rgb(99 102 241); }
.card-header .name { font-size: .75rem; font-weight: 600; color: rgb(199 210 254); flex: 1; min-width: 0; }
.card-header .status-icon { width: 14px; height: 14px; flex-shrink: 0; }
.card-header .status-icon.success { color: rgb(74 222 128); }
.card-header .status-icon.error { color: rgb(248 113 113); }
.card-header .spinning { margin-left: auto; }
.card-header .chevron { width: 14px; height: 14px; flex-shrink: 0; color: rgb(75 85 99); transition: transform .2s; }
.card-header .chevron.rotated { transform: rotate(90deg); }

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
  gap: .375rem;
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
  gap: .25rem;
  transition: all .15s;
}
.retry-btn:hover { color: rgb(99 102 241); background: rgb(99 102 241 / .08); }

/* ═══════════ 流式指示器 ════════════ */
.stream-indicator {
  display: flex;
  align-items: center;
  gap: .75rem;
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
</style>
