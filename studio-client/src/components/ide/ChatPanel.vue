<script setup lang="ts">
/**
 * CodeBuddy IDE — AI Chat Panel
 *
 * Session 31: ChatGPT 风格改造
 *   - 左侧 ChatHistoryPanel 统一管理历史对话（按时间分组、搜索、重命名、删除）
 *   - 删除冗余的 PanelRight/ListTree 侧栏图标
 *   - 顶部精简为标题栏（当前对话名 + 历史面板切换 + 清空）
 *   - 底部输入面板不变
 */
import { computed, nextTick, onMounted, onUnmounted, onUpdated, ref } from "vue"
import { ChevronDown, ImagePlus, Paperclip, Send, Sparkles, StopCircle, Mic, Wrench, Trash2, PanelLeftClose, PanelLeft } from "lucide-vue-next"
import apiClient from "@/api/client"
import { renderMarkdownToHtml, postProcessMarkdown } from "@/composables/useMarkdown"
import { useAgentTabsStore } from "@/stores/useAgentTabsStore"
import ChatHistoryPanel from "./ChatHistoryPanel.vue"

interface Message {
  role: "user" | "assistant" | "system"
  content: string
  timestamp: number
  toolCalls?: Array<{ name: string; args?: any; result?: string; status: 'running' | 'done' | 'error' }>
  modelUsed?: string
  provider?: string
}

const models = [
  { id: "llama3.1:8b", label: "Llama 3.1", desc: "本地 · 8B · 支持工具", group: "local" },
  { id: "qwen2.5-coder:7b", label: "Qwen2.5-Coder", desc: "本地 · 7B · 代码专精", group: "local" },
  { id: "gemma2:27b", label: "Gemma 2", desc: "本地 · 27B · 通用", group: "local" },
  { id: "deepseek-coder-v2", label: "DeepSeek Coder", desc: "本地 · 代码专精", group: "local" },
  { id: "gpt-4o", label: "GPT-4o", desc: "云端 · 最强综合", group: "cloud" },
  { id: "claude-sonnet", label: "Claude Sonnet", desc: "云端 · 长文本", group: "cloud" },
] as const

const modelGroups = [
  { id: "local", label: "内置模型", icon: "M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2zm7 14a1 1 0 1 0 0-2 1 1 0 0 0 0 2z" },
  { id: "cloud", label: "自定义模型", icon: "M3 15a4 4 0 0 1 4-4h.5a5.5 5.5 0 0 1 10.5 2A4 4 0 0 1 17 19H7a4 4 0 0 1-4-4z" },
] as const

const craftModes = [
  { id: "craft", label: "Craft", desc: "主动完成编码任务", icon: "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" },
  { id: "ask", label: "Ask", desc: "只读不修改，回答问题", icon: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" },
  { id: "plan", label: "Plan", desc: "规划任务，不执行", icon: "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" },
] as const

const craftActions = [
  { id: "auto", label: "Auto", desc: "自动选择最优工具" },
  { id: "manual", label: "Manual", desc: "手动确认每步" },
] as const

interface Attachment {
  name: string
  size: number
  kind: "file" | "image"
}

const messages = ref<Message[]>([])
const inputText = ref("")
const isLoading = ref(false)
const mc = ref<HTMLDivElement | null>(null)
const selectedModel = ref(models[0] ?? { id: 'default', label: '选择模型', desc: '', group: 'local' })
const selectedCraft = ref(craftModes[0])
const selectedAction = ref(craftActions[0])
const showModelMenu = ref(false)
const showCraftMenu = ref(false)
const showActionMenu = ref(false)
const abortController = ref<AbortController | null>(null)
const attachments = ref<Attachment[]>([])

/** Sessions — 通过 AgentTabsStore 统一管理 */
const agentTabsStore = useAgentTabsStore()
const activeAgentTab = computed(() => agentTabsStore.activeTab)

/** Tab 操作 */
function createAgentTab(): void {
  agentTabsStore.createTab()
  // 切换后清空当前消息让用户重新开始
  messages.value = []
  inputText.value = ""
}

function switchToAgentTab(tabId: string): void {
  // 先保存当前消息
  if (activeAgentTab.value) {
    saveCurrentMessages()
  }
  agentTabsStore.switchToTab(tabId)
  // 加载目标 Tab 的消息
  const stored = localStorage.getItem(`agent_msgs_${tabId}`)
  try {
    messages.value = stored ? JSON.parse(stored) : []
  } catch {
    messages.value = []
  }
}

function closeAgentTab(tabId: string): void {
  // 先保存
  if (activeAgentTab.value?.id === tabId) {
    saveCurrentMessages()
  }
  agentTabsStore.removeTab(tabId)
  // 加载新 active tab 的消息
  if (activeAgentTab.value) {
    const newTabId = activeAgentTab.value.id
    const stored = localStorage.getItem(`agent_msgs_${newTabId}`)
    try {
      messages.value = stored ? JSON.parse(stored) : []
    } catch {
      messages.value = []
    }
  } else {
    messages.value = []
  }
}

/** 兼容旧版 localStorage 键名迁移 */
function loadMessagesForTab(tabId: string): void {
  const stored = localStorage.getItem(`agent_msgs_${tabId}`)
  try {
    messages.value = stored ? JSON.parse(stored) : []
  } catch {
    messages.value = []
  }
}

const hasMessages = computed(() => messages.value.length > 0)

/** Chat History Panel — 默认收起，用户点击顶部按钮才打开 (VSCode 一致) */
const showHistory = ref(false)

/** 历史面板回调 */
function handleHistorySwitchTab(tabId: string): void {
  if (activeAgentTab.value) saveCurrentMessages()
  switchToAgentTab(tabId)
}

function handleHistoryCreateTab(): void {
  createAgentTab()
}

function handleHistoryDeleteTab(tabId: string): void {
  closeAgentTab(tabId)
}

function handleHistoryRenameTab(tabId: string, title: string): void {
  agentTabsStore.renameTab(tabId, title)
}

function handleHistoryTogglePin(tabId: string): void {
  agentTabsStore.togglePin(tabId)
}

function renderMessageHtml(content: string, msgIndex: number): string {
  return renderMarkdownToHtml(content, `chat-h-${msgIndex}`)
}

function saveCurrentMessages() {
  const tab = activeAgentTab.value
  if (!tab) return
  localStorage.setItem(`agent_msgs_${tab.id}`, JSON.stringify(messages.value))
  // 自动重命名 Tab 为首条用户消息
  if (messages.value.length > 0 && tab.title === '新对话') {
    const firstUser = messages.value.find(m => m.role === 'user')
    if (firstUser) {
      agentTabsStore.renameTab(tab.id, firstUser.content.slice(0, 30))
    }
  }
  // 同步给 store 的 messagesJson（用于跨 Tab 读取）
  agentTabsStore.saveMessages(tab.id, messages.value as any)
}

function closeAllMenus() {
  showModelMenu.value = false
  showCraftMenu.value = false
  showActionMenu.value = false
}

function sb(): void {
  nextTick(() => {
    if (mc.value) mc.value.scrollTop = mc.value.scrollHeight
  })
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

/** 快捷命令填入输入框，等待用户确认发送 */
function fillPrompt(prompt: string) {
  inputText.value = prompt
}

async function sendMessage(): Promise<void> {
  const text = inputText.value.trim()
  const hasAttachments = attachments.value.length > 0
  if ((!text && !hasAttachments) || isLoading.value) return

  // 若无 active Tab，自动创建
  if (!activeAgentTab.value) {
    createAgentTab()
  }

  // 构建用户消息内容（文本 + 附件描述）
  let userContent = text
  if (hasAttachments) {
    const attLines = attachments.value.map(a => `[附件: ${a.name} (${a.kind === 'image' ? '图片' : '文件'}, ${(a.size / 1024).toFixed(1)}KB)]`)
    userContent = text ? text + '\n\n' + attLines.join('\n') : attLines.join('\n')
  }

  messages.value.push({ role: "user", content: userContent, timestamp: Date.now() })
  inputText.value = ""
  // 快照当前附件列表后清空
  const sentAttachments = [...attachments.value]
  attachments.value = []
  isLoading.value = true
  abortController.value = new AbortController()
  sb()

  const am: Message = {
    role: "assistant",
    content: "",
    timestamp: Date.now(),
    toolCalls: [],
  }
  messages.value.push(am)
  sb()

  try {
    const resp = await apiClient.post("/agent/chat/simple", {
      message: userContent,
      tools: ["calculate", "datetime_now", "get_weather", "web_search", "file_read", "codebase_search"],
      preferred_model: selectedModel.value.id,
      craft_mode: selectedCraft.value.id,
      action_mode: selectedAction.value.id,
      attachments: sentAttachments.map(a => ({ name: a.name, size: a.size, kind: a.kind })),
      max_turns: 10,
      stream: true,
    }, {
      signal: abortController.value.signal,
      onDownloadProgress: (progressEvent: any) => {
        const txt = progressEvent.event?.target?.responseText || progressEvent.currentTarget?.responseText
        if (txt) {
          const lines = txt.split('\n')
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (data.type === 'chunk') {
                  am.content += data.content || ''
                } else if (data.type === 'tool_call') {
                  am.toolCalls = am.toolCalls || []
                  const existing = am.toolCalls.find(t => t.name === data.name && t.status === 'running')
                  if (existing) {
                    existing.result = data.result
                    existing.status = 'done'
                  } else {
                    am.toolCalls.push({ name: data.name, args: data.args, result: data.result, status: 'done' })
                  }
                } else if (data.type === 'tool_start') {
                  am.toolCalls = am.toolCalls || []
                  am.toolCalls.push({ name: data.tool, args: data.args, status: 'running' })
                }
              } catch {}
            }
          }
          sb()
        }
      },
    })
    if (!am.content && resp.data) {
      am.content = resp.data.answer || resp.data.content || JSON.stringify(resp.data)
      am.modelUsed = resp.data.model_used
      am.provider = resp.data.provider
    }
  } catch (e: any) {
    if (e?.name === 'AbortError' || e?.code === 'ERR_CANCELED') {
      if (!am.content) am.content = '⏹ 已停止生成'
    } else {
      const msg = e?.response?.data?.detail || e?.message || "请求失败，请检查后端是否启动。"
      am.content = `❌ ${msg}`
    }
  } finally {
    isLoading.value = false
    abortController.value = null
    saveCurrentMessages()
    sb()
  }
}

function stopGeneration() {
  abortController.value?.abort()
}

/** 工具栏交互 — 完整逻辑（非占位） */
const fileInputRef = ref<HTMLInputElement | null>(null)
const imageInputRef = ref<HTMLInputElement | null>(null)
const isRecording = ref(false)
let mediaRecorder: MediaRecorder | null = null

function handleAttach(): void {
  fileInputRef.value?.click()
}

function handleImage(): void {
  imageInputRef.value?.click()
}

async function handleVoice(): Promise<void> {
  if (isRecording.value) {
    // 停止录音
    try { mediaRecorder?.stop() } catch {}
    isRecording.value = false
    return
  }
  // 检查浏览器支持
  if (typeof navigator === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
    alert('当前环境不支持语音输入')
    return
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    const recorder = new MediaRecorder(stream)
    mediaRecorder = recorder
    isRecording.value = true
    const chunks: BlobPart[] = []
    recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data) }
    recorder.onstop = () => {
      const blob = new Blob(chunks, { type: 'audio/webm' })
      stream.getTracks().forEach(t => t.stop())
      isRecording.value = false
      // 生成 attachment chip，与文件/图片保持一致的交互体验
      attachments.value.push({ name: `语音录音 ${new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}.webm`, size: blob.size, kind: "file" })
    }
    recorder.start()
  } catch (e: any) {
    isRecording.value = false
    alert('无法访问麦克风：' + (e?.message || '权限被拒绝'))
  }
}

function onFilePicked(e: Event): void {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  attachments.value.push({ name: file.name, size: file.size, kind: "file" })
  input.value = ''
}

function onImagePicked(e: Event): void {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  attachments.value.push({ name: file.name, size: file.size, kind: "image" })
  input.value = ''
}

function removeAttachment(idx: number): void {
  attachments.value.splice(idx, 1)
}

function clearMessages() {
  messages.value = []
  const tab = activeAgentTab.value
  if (tab) {
    localStorage.removeItem(`agent_msgs_${tab.id}`)
    agentTabsStore.saveMessages(tab.id, [])
  }
}

onMounted(() => {
  // 加载当前 active Tab 的消息
  if (activeAgentTab.value) {
    loadMessagesForTab(activeAgentTab.value.id)
  }
  document.addEventListener('click', closeAllMenus)
})

let mdRenderTimer: ReturnType<typeof setTimeout> | null = null
onUpdated(() => {
  if (mdRenderTimer) clearTimeout(mdRenderTimer)
  mdRenderTimer = setTimeout(() => {
    const containers = document.querySelectorAll('.markdown-body')
    containers.forEach(c => postProcessMarkdown(c as HTMLElement))
  }, 50)
})

onUnmounted(() => {
  document.removeEventListener('click', closeAllMenus)
  if (mdRenderTimer) clearTimeout(mdRenderTimer)
})
</script>

<template>
  <div class="chat-panel h-full flex bg-[var(--color-ide-surface)]">
    <!-- ═══ 左侧：历史对话侧栏 ═══ -->
    <ChatHistoryPanel
      v-model="showHistory"
      :current-tab-id="activeAgentTab?.id ?? ''"
      @switch-tab="handleHistorySwitchTab"
      @create-tab="handleHistoryCreateTab"
      @delete-tab="handleHistoryDeleteTab"
      @rename-tab="handleHistoryRenameTab"
      @toggle-pin="handleHistoryTogglePin"
    />

    <!-- ═══ 右侧：对话主区域 ═══ -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- 顶部精简标题栏 (35px) -->
      <header
        class="flex items-center gap-1.5 px-2 shrink-0"
        style="height: 35px; border-bottom: 1px solid var(--color-ide-border); background: var(--color-ide-bg-secondary);"
      >
        <!-- 切换历史面板 -->
        <button
          class="w-6 h-6 flex items-center justify-center rounded hover:bg-[var(--color-ide-surface-hover)] shrink-0"
          :style="showHistory ? 'color: var(--color-ide-accent);' : 'color: var(--color-ide-text-dim);'"
          :title="showHistory ? '隐藏历史' : '显示历史'"
          @click="showHistory = !showHistory"
        >
          <PanelLeftClose v-if="showHistory" :size="14" />
          <PanelLeft v-else :size="14" />
        </button>

        <!-- 当前对话标题 (无 Tab 时不显示, 避免与左侧 ActivityBar 的 AI 入口标题重复) -->
        <span v-if="activeAgentTab" class="flex-1 text-[11px] truncate font-medium" style="color: var(--color-ide-text);">
          {{ activeAgentTab.title || '新对话' }}
        </span>
        <span v-else class="flex-1" />

        <!-- 清空当前对话 -->
        <button
          v-if="hasMessages"
          class="w-6 h-6 flex items-center justify-center rounded hover:bg-[var(--color-ide-surface-hover)] shrink-0"
          style="color: var(--color-ide-text-dim);"
          title="清空对话"
          @click="clearMessages"
        >
          <Trash2 :size="12" />
        </button>
      </header>

      <!-- Messages 区域 -->
      <div
        ref="mc"
        class="flex-1 overflow-y-auto px-4 py-3 space-y-3"
      >
        <!-- Welcome State -->
        <div v-if="!hasMessages && !isLoading" class="h-full flex flex-col items-center justify-center select-none">
          <div
            class="mb-4 w-14 h-14 rounded-2xl flex items-center justify-center border shadow-sm"
            style="background: var(--chat-welcome-icon-bg); border-color: var(--chat-welcome-icon-border);"
          >
            <Sparkles :size="28" style="color: var(--color-ide-accent);" />
          </div>
          <p class="text-[14px] mb-5" style="color: var(--color-ide-text-dim);">输入你的需求，比如「帮我分析项目结构」</p>

          <div class="w-full space-y-2.5 max-w-[400px]">
            <button
              v-for="action in [
                {text:'分析代码性能',prompt:'帮我分析当前组件的性能'},
                {text:'生成 Vue 组件',prompt:'生成一个 Vue 组件'},
                {text:'解释项目架构',prompt:'解释这个项目的架构'},
                {text:'调试报错',prompt:'帮我调试这段代码中的错误'}
              ]"
              :key="action.text"
              @click="fillPrompt(action.prompt)"
              class="w-full text-left text-[14px] px-5 py-3 rounded-xl border transition-all duration-150 hover:border-[var(--color-ide-accent)] hover:text-[var(--color-ide-text)] hover:shadow-sm"
              style="border-color: var(--color-ide-border); color: var(--color-ide-text-dim);"
            >
              {{ action.text }}
            </button>
          </div>
        </div>

        <!-- Messages List -->
        <template v-else>
          <div
            v-for="(msg, idx) in messages"
            :key="idx"
            class="flex gap-2 items-start"
            :class="{ 'flex-row-reverse': msg.role === 'user' }"
          >
            <template v-if="msg.role === 'assistant'">
              <div
                class="max-w-[88%] rounded-xl px-3 py-2.5 border-l-[3px] shadow-[0_2px_8px_rgba(0,0,0,0.15)]"
                style="border-left-color: var(--color-chat-ai-border); background: var(--color-chat-ai-bg);"
              >
                <div v-if="isLoading && !msg.content && (!msg.toolCalls || msg.toolCalls.length === 0)" class="flex items-center gap-2 py-1" style="color: var(--color-ide-text-dim);">
                  <span class="flex gap-1">
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce" style="background: var(--color-ide-accent); animation-delay: 0ms;" />
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce" style="background: var(--color-ide-accent); animation-delay: 150ms;" />
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce" style="background: var(--color-ide-accent); animation-delay: 300ms;" />
                  </span>
                  <span class="text-[12px]">正在思考...</span>
                </div>

                <div v-if="msg.toolCalls && msg.toolCalls.length > 0" class="mb-2 space-y-1">
                  <div
                    v-for="tc in msg.toolCalls"
                    :key="tc.name"
                    class="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-md border"
                    style="background: var(--chat-toolcall-bg); border-color: var(--chat-toolcall-border);"
                  >
                    <Wrench
                      :size="10"
                      class="shrink-0"
                      :class="tc.status === 'running' ? 'text-yellow-400 animate-pulse' : tc.status === 'error' ? 'text-red-400' : 'text-green-400'"
                    />
                    <span class="font-medium" style="color: var(--color-ide-text-dim);">{{ tc.name }}</span>
                    <span v-if="tc.status === 'running'" class="text-yellow-400 ml-auto">执行中...</span>
                    <span v-else-if="tc.status === 'error'" class="text-red-400 ml-auto">失败</span>
                    <span v-else class="ml-auto text-green-400/60">✓</span>
                  </div>
                </div>

                <div
                  v-if="msg.content"
                  class="text-[12px] leading-relaxed break-words markdown-body"
                  style="color: var(--color-ide-text);"
                  v-html="renderMessageHtml(msg.content, idx)"
                />
              </div>
              <span class="text-[9px] mt-auto ml-1.5 whitespace-nowrap flex flex-col items-center gap-0.5" style="color: var(--color-ide-text-dim);">
                {{ formatTime(msg.timestamp) }}
                <span v-if="msg.modelUsed" class="text-[8px] opacity-50">{{ msg.modelUsed?.split('-')[0] }}</span>
              </span>
            </template>

            <template v-else-if="msg.role === 'user'">
              <div
                class="rounded-xl px-3 py-2 max-w-[80%] border"
                style="background: var(--color-chat-user-bg); border-color: var(--color-chat-user-border);"
              >
                <div
                  class="text-[12px] leading-relaxed break-words markdown-body"
                  style="color: var(--color-ide-text);"
                  v-html="renderMessageHtml(msg.content, idx)"
                />
              </div>
              <span class="text-[9px] mt-auto ml-1.5 whitespace-nowrap" style="color: var(--color-ide-text-dim);">你</span>
            </template>
          </div>
        </template>
      </div>

      <!-- 底部输入面板 (Craft 风格：Craft/Auto 双下拉 + 工具按钮 + 圆形发送) -->
      <div
        class="shrink-0 pt-2 pb-3 px-3"
        style="background: var(--color-ide-bg-secondary);"
      >
        <!-- 单一容器：附件 chips + 输入框 + 工具栏 -->
        <div
          class="relative rounded-2xl transition-all duration-200 focus-within:shadow-lg"
          style="background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border); box-shadow: 0 1px 3px rgba(0,0,0,0.06);"
        >
          <!-- 附件 chip 列表 (有附件时显示) -->
          <div
            v-if="attachments.length > 0"
            class="flex flex-wrap items-center gap-1.5 px-4 pt-3"
          >
            <div
              v-for="(att, idx) in attachments"
              :key="idx"
              class="flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-md text-[11px] font-medium"
              style="background: var(--chat-craft-badge-bg); color: var(--color-ide-accent); border: 1px solid var(--chat-craft-badge-border);"
            >
              <Paperclip v-if="att.kind === 'file'" :size="11" class="opacity-80" />
              <ImagePlus v-else :size="11" class="opacity-80" />
              <span class="truncate max-w-[120px]">{{ att.name }}</span>
              <span class="opacity-60 text-[10px]">{{ (att.size / 1024).toFixed(1) }}KB</span>
              <button
                @click="removeAttachment(idx)"
                class="w-4 h-4 flex items-center justify-center rounded hover:bg-black/20 transition-colors"
                title="移除"
              >
                <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          <!-- 输入框 -->
          <textarea
            v-model="inputText"
            rows="3"
            placeholder="提问或输入“/”快捷命令"
            class="w-full resize-none outline-none text-[13px] leading-relaxed bg-transparent px-4 pt-3 pb-2"
            :class="attachments.length > 0 ? 'pt-2' : 'pt-3.5'"
            style="color: var(--color-ide-text); min-height: 64px; border: none; border-radius: 0;"
            @keydown.enter.exact.prevent="sendMessage"
            @keydown.shift.enter.prevent="inputText += '\n'"
          />

          <!-- 工具按钮行 (附件/图片/语音) -->
          <div class="flex items-center gap-0.5 px-3 pb-1.5">
            <button
              @click="handleAttach"
              class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              style="color: var(--color-ide-text-dim);"
              title="附件"
            >
              <Paperclip :size="14" />
            </button>
            <button
              @click="handleImage"
              class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              style="color: var(--color-ide-text-dim);"
              title="图片"
            >
              <ImagePlus :size="14" />
            </button>
            <button
              @click="handleVoice"
              class="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-[var(--color-ide-surface-hover)] transition-colors relative"
              :style="isRecording ? 'color: var(--color-ide-accent); background: var(--chat-recording-bg);' : 'color: var(--color-ide-text-dim);'"
              :title="isRecording ? '点击停止录音' : '语音输入'"
            >
              <Mic :size="14" />
              <span v-if="isRecording" class="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            </button>
          </div>

          <!-- 底部分隔 -->
          <div class="h-px mx-3" style="background: var(--color-ide-border); opacity: 0.5;" />

          <!-- 底部选择器 + 发送按钮 -->
          <div class="flex items-center justify-between gap-2 px-2.5 pb-2.5 pt-1.5">
            <!-- 左侧：Craft + Auto 双下拉 -->
            <div class="flex items-center gap-1.5 min-w-0 flex-1">
              <!-- Craft Selector (主模式) -->
              <div class="relative shrink-0" @click.stop>
                <button
                  @click="showCraftMenu = !showCraftMenu; showModelMenu = false; showActionMenu = false"
                  class="flex items-center gap-1.5 h-8 pl-2.5 pr-2 rounded-lg text-[12px] font-semibold transition-all hover:bg-[var(--color-ide-surface-hover)]"
                  :class="showCraftMenu ? 'bg-[var(--color-ide-surface-hover)]' : ''"
                  style="color: var(--color-ide-text);"
                  :aria-expanded="showCraftMenu"
                  :aria-haspopup="true"
                >
                  <!-- Craft 图标 -->
                  <div
                    class="w-5 h-5 rounded-md flex items-center justify-center shrink-0"
                    style="background: var(--color-ide-accent); color: white;"
                  >
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
                    </svg>
                  </div>
                  <span>{{ selectedCraft.label }}</span>
                  <ChevronDown :size="11" class="shrink-0 opacity-60 transition-transform" :class="showCraftMenu ? 'rotate-180' : ''" />
                </button>
                <Transition name="fade">
                  <div
                    v-if="showCraftMenu"
                    class="absolute bottom-full left-0 mb-2 w-[240px] z-50 py-1.5 rounded-2xl border overflow-hidden"
                    style="background: var(--color-ide-surface); border-color: var(--color-ide-border); box-shadow: 0 10px 40px rgba(0,0,0,0.35), 0 2px 8px rgba(0,0,0,0.15);"
                  >
                    <div class="px-3.5 py-2 flex items-center justify-between" style="background: var(--chat-popover-header-bg);">
                      <span class="text-[11px] font-semibold" style="color: var(--color-ide-text);">选择工作模式</span>
                    </div>
                    <div class="h-px" style="background: var(--color-ide-border);" />
                    <div class="py-1.5">
                      <button
                        v-for="m in craftModes"
                        :key="m.id"
                        @click="selectedCraft=m;showCraftMenu=false"
                        class="w-full text-left mx-1.5 px-2.5 py-2 rounded-lg text-[12px] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-2.5 transition-all"
                        :class="m.id===selectedCraft.id ? 'shadow-sm' : ''"
                        :style="m.id===selectedCraft.id ? 'background: var(--chat-item-selected-bg); color: var(--color-ide-text);' : 'color: var(--color-ide-text);'"
                      >
                        <div
                          class="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
                          :style="m.id===selectedCraft.id ? 'background: var(--color-ide-accent); color: white;' : 'background: var(--color-ide-bg); color: var(--color-ide-text-dim);'"
                        >
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                            <path :d="m.icon" />
                          </svg>
                        </div>
                        <div class="min-w-0 flex-1">
                          <div class="font-semibold truncate" :class="m.id===selectedCraft.id ? 'text-[var(--color-ide-accent)]' : ''">{{ m.label }}</div>
                          <div class="text-[10.5px] truncate font-normal" style="color: var(--color-ide-text-dim);">{{ m.desc }}</div>
                        </div>
                        <!-- 右侧 ⓘ 图标 -->
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 opacity-40">
                          <circle cx="12" cy="12" r="10"/>
                          <path d="M12 16v-4M12 8h.01"/>
                        </svg>
                      </button>
                    </div>
                    <div class="h-px" style="background: var(--color-ide-border);" />
                    <button
                      class="w-full text-left mx-1.5 my-1 px-2.5 py-1.5 rounded-lg text-[12px] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-1.5 transition-colors"
                      style="color: var(--color-ide-text-dim);"
                    >
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M12 5v14M5 12h14"/>
                      </svg>
                      <span>创建 Agent</span>
                    </button>
                  </div>
                </Transition>
              </div>

              <!-- Model Selector (更紧凑, icon-only chip) -->
              <div class="relative shrink-0" @click.stop>
                <button
                  @click="showModelMenu = !showModelMenu; showCraftMenu = false; showActionMenu = false"
                  class="flex items-center gap-1 h-8 pl-2 pr-1.5 rounded-lg text-[12px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
                  :class="showModelMenu ? 'bg-[var(--color-ide-surface-hover)]' : ''"
                  style="color: var(--color-ide-text-dim);"
                  :aria-expanded="showModelMenu"
                  :aria-haspopup="true"
                  :title="selectedModel.label + ' · ' + selectedModel.desc"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 opacity-70">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M12 1v6m0 10v6M4.22 4.22l4.24 4.24m7.08 7.08l4.24 4.24M1 12h6m10 0h6M4.22 19.78l4.24-4.24m7.08-7.08l4.24-4.24"/>
                  </svg>
                  <span class="truncate max-w-[80px]">{{ selectedModel.label }}</span>
                  <ChevronDown :size="11" class="shrink-0 opacity-60 transition-transform" :class="showModelMenu ? 'rotate-180' : ''" />
                </button>
                <Transition name="fade">
                  <div
                    v-if="showModelMenu"
                    class="absolute bottom-full left-0 mb-2 w-[300px] z-50 rounded-2xl border overflow-hidden"
                    style="background: var(--color-ide-surface); border-color: var(--color-ide-border); box-shadow: 0 10px 40px rgba(0,0,0,0.35), 0 2px 8px rgba(0,0,0,0.15);"
                  >
                    <div class="px-3.5 py-2.5 flex items-center justify-between" style="background: var(--chat-popover-header-bg);">
                      <span class="text-[11px] font-semibold" style="color: var(--color-ide-text);">选择模型</span>
                      <span class="text-[10px]" style="color: var(--color-ide-text-dim);">{{ models.length }} 个可用</span>
                    </div>
                    <div class="h-px" style="background: var(--color-ide-border);" />
                    <div class="max-h-[360px] overflow-y-auto py-1.5">
                      <div v-for="group in modelGroups" :key="group.id">
                        <div class="px-3.5 pt-2 pb-1 flex items-center gap-1.5">
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--color-ide-text-dim);">
                            <path :d="group.icon" />
                          </svg>
                          <span class="text-[10px] font-semibold uppercase tracking-wider" style="color: var(--color-ide-text-dim);">{{ group.label }}</span>
                        </div>
                        <button
                          v-for="m in models.filter(x => x.group === group.id)"
                          :key="m.id"
                          @click="selectedModel=m;showModelMenu=false"
                          class="w-full text-left mx-1.5 px-2.5 py-1.5 rounded-lg text-[12px] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-2.5 transition-all"
                          :class="m.id===selectedModel.id ? 'shadow-sm' : ''"
                          :style="m.id===selectedModel.id ? 'background: var(--chat-item-selected-bg); color: var(--color-ide-text);' : 'color: var(--color-ide-text);'"
                        >
                          <div
                            class="w-6 h-6 rounded-md flex items-center justify-center shrink-0"
                            :style="m.id===selectedModel.id ? 'background: var(--color-ide-accent); color: white;' : 'background: var(--color-ide-bg); color: var(--color-ide-text-dim);'"
                          >
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                              <path d="M12 2a4 4 0 0 0-4 4v1a3 3 0 0 0-3 3v.5A2.5 2.5 0 0 0 2.5 13v6A2.5 2.5 0 0 0 5 21.5h14a2.5 2.5 0 0 0 2.5-2.5v-6A2.5 2.5 0 0 0 19 10.5V10a3 3 0 0 0-3-3V6a4 4 0 0 0-4-4z" />
                              <circle cx="9" cy="16" r="1" fill="currentColor"/>
                              <circle cx="15" cy="16" r="1" fill="currentColor"/>
                            </svg>
                          </div>
                          <div class="min-w-0 flex-1">
                            <div class="font-semibold truncate" :class="m.id===selectedModel.id ? 'text-[var(--color-ide-accent)]' : ''">{{ m.label }}</div>
                            <div class="text-[10.5px] truncate font-normal" style="color: var(--color-ide-text-dim);">{{ m.desc }}</div>
                          </div>
                          <svg v-if="m.id===selectedModel.id" class="shrink-0" width="13" height="11" viewBox="0 0 12 9" fill="none">
                            <path d="M1 3l4 4 6-6" stroke="var(--color-ide-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                  </div>
                </Transition>
              </div>

              <!-- Action Selector (Auto/Manual) -->
              <div class="relative shrink-0" @click.stop>
                <button
                  @click="showActionMenu = !showActionMenu; showCraftMenu = false; showModelMenu = false"
                  class="flex items-center gap-1 h-8 pl-2 pr-1.5 rounded-lg text-[12px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
                  :class="showActionMenu ? 'bg-[var(--color-ide-surface-hover)]' : ''"
                  style="color: var(--color-ide-text-dim);"
                  :aria-expanded="showActionMenu"
                  :aria-haspopup="true"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 opacity-70">
                    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
                  </svg>
                  <span>{{ selectedAction.label }}</span>
                  <ChevronDown :size="11" class="shrink-0 opacity-60 transition-transform" :class="showActionMenu ? 'rotate-180' : ''" />
                </button>
                <Transition name="fade">
                  <div
                    v-if="showActionMenu"
                    class="absolute bottom-full left-0 mb-2 w-[200px] z-50 py-1.5 rounded-2xl border overflow-hidden"
                    style="background: var(--color-ide-surface); border-color: var(--color-ide-border); box-shadow: 0 10px 40px rgba(0,0,0,0.35), 0 2px 8px rgba(0,0,0,0.15);"
                  >
                    <div class="px-3.5 py-2" style="background: var(--chat-popover-header-bg);">
                      <span class="text-[11px] font-semibold" style="color: var(--color-ide-text);">执行方式</span>
                    </div>
                    <div class="h-px" style="background: var(--color-ide-border);" />
                    <div class="py-1.5">
                      <button
                        v-for="a in craftActions"
                        :key="a.id"
                        @click="selectedAction=a;showActionMenu=false"
                        class="w-full text-left mx-1.5 px-2.5 py-2 rounded-lg text-[12px] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-2.5 transition-all"
                        :class="a.id===selectedAction.id ? 'shadow-sm' : ''"
                        :style="a.id===selectedAction.id ? 'background: var(--chat-item-selected-bg); color: var(--color-ide-text);' : 'color: var(--color-ide-text);'"
                      >
                        <div class="min-w-0 flex-1">
                          <div class="font-semibold truncate" :class="a.id===selectedAction.id ? 'text-[var(--color-ide-accent)]' : ''">{{ a.label }}</div>
                          <div class="text-[10.5px] truncate font-normal" style="color: var(--color-ide-text-dim);">{{ a.desc }}</div>
                        </div>
                        <svg v-if="a.id===selectedAction.id" class="shrink-0" width="13" height="11" viewBox="0 0 12 9" fill="none">
                          <path d="M1 3l4 4 6-6" stroke="var(--color-ide-accent)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                      </button>
                    </div>
                  </div>
                </Transition>
              </div>
            </div>

            <!-- 右侧：发送 / 停止 按钮 (圆形图标按钮，紫色高亮) -->
            <button
              v-if="!isLoading"
              class="shrink-0 w-9 h-9 flex items-center justify-center rounded-full transition-all duration-150 active:scale-90"
              :class="(inputText.trim() || attachments.length > 0)
                ? 'opacity-100 hover:scale-105 cursor-pointer shadow-md'
                : 'opacity-30 cursor-not-allowed'"
              :style="(inputText.trim() || attachments.length > 0)
                ? 'background: var(--color-ide-accent); color: white;'
                : 'background: var(--color-ide-text-dim); color: var(--color-ide-bg-secondary);'"
              :disabled="!inputText.trim() && attachments.length === 0"
              @click="sendMessage"
              title="发送 (Enter)"
            >
              <Send :size="15" :stroke-width="2.5" />
            </button>
            <button
              v-else
              class="shrink-0 w-9 h-9 flex items-center justify-center rounded-full transition-all duration-150 hover:scale-105 active:scale-90 cursor-pointer shadow-md"
              style="background: #ef4444; color: white;"
              @click="stopGeneration"
              title="停止生成"
            >
              <StopCircle :size="15" :stroke-width="2.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 隐藏的原生文件输入 (供附件/图片按钮触发) -->
  <input ref="fileInputRef" type="file" class="hidden" @change="onFilePicked" />
  <input ref="imageInputRef" type="file" accept="image/*" class="hidden" @change="onImagePicked" />
</template>

<style scoped>
/* ═══ 聊天面板主题渐变（组件级 CSS 变量） ═══ */
.chat-panel {
  --chat-welcome-icon-bg: linear-gradient(135deg, rgba(192, 193, 255, 0.12), transparent);
  --chat-welcome-icon-border: rgba(192, 193, 255, 0.2);
  --chat-toolcall-bg: rgba(0, 0, 0, 0.2);
  --chat-toolcall-border: rgba(255, 255, 255, 0.05);
  --chat-craft-badge-bg: rgba(192, 193, 255, 0.14);
  --chat-craft-badge-border: rgba(192, 193, 255, 0.25);
  --chat-recording-bg: rgba(192, 193, 255, 0.12);
  --chat-popover-header-bg: linear-gradient(to bottom, rgba(255, 255, 255, 0.03), transparent);
  --chat-item-selected-bg: rgba(192, 193, 255, 0.12);
}
.fade-enter-active {
  transition: opacity 0.18s cubic-bezier(0.16, 1, 0.3, 1), transform 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}
.fade-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.97);
  transform-origin: bottom left;
}
</style>
