<script setup lang="ts">
/**
 * CodeBuddy IDE — AI Chat Panel (Hermes-Enhanced)
 * Streaming · Tool Traces · Session Search · Voice Ready
 */
import { computed, nextTick, onMounted, onUnmounted, onUpdated, ref } from "vue"
import { Bot, ChevronDown, ChevronRight, ImagePlus, Paperclip, Send, Sparkles, StopCircle, Mic, History, Wrench, Trash2, Pin, Archive, Download, Copy, Check, Square, MoreHorizontal, X, FolderOpen, Terminal, FileText, PanelRight, ListTree } from "lucide-vue-next"
import apiClient from "@/api/client"
import { renderMarkdownToHtml, postProcessMarkdown } from "@/composables/useMarkdown"
import ChatOutlinePanel from "./ChatOutlinePanel.vue"

interface Message {
  role: "user" | "assistant" | "system"
  content: string
  timestamp: number
  toolCalls?: Array<{ name: string; args?: any; result?: string; status: 'running' | 'done' | 'error' }>
  modelUsed?: string
  provider?: string
}

interface Session {
  id: string
  title: string
  lastMessage: string
  timestamp: number
  messageCount: number
  pinned?: boolean
  archived?: boolean
  workspace?: string
  model?: string
  agentMode?: string
}

const models = [
  { id: "llama3.1:8b", label: "Llama 3.1", desc: "(本地·8B·Tools)", active: true },
  { id: "qwen2.5-coder:7b", label: "Qwen2.5-Coder", desc: "(本地·7B·代码)", active: false },
  { id: "gemma2:27b", label: "Gemma 2", desc: "(本地·27B)", active: false },
  { id: "deepseek-coder-v2", label: "DeepSeek Coder", desc: "(本地·代码)", active: false },
  { id: "gpt-4o", label: "GPT-4o", desc: "(API·最强)", active: false },
  { id: "claude-sonnet", label: "Claude Sonnet", desc: "(API·长文本)", active: false },
]

const modes = [
  { id: "chat", label: "对话模式", active: true },
  { id: "agent", label: "Agent 模式", active: false },
]

const messages = ref<Message[]>([])
const inputText = ref("")
const isLoading = ref(false)
const mc = ref<HTMLDivElement | null>(null)
const selectedModel = ref(models[0] ?? { id: 'default', label: '选择模型', desc: '' })
const selectedMode = ref(modes[0])
const showModelMenu = ref(false)
const showModeMenu = ref(false)
const abortController = ref<AbortController | null>(null)

/** Hermes-style: Sessions */
const sessions = ref<Session[]>([])
const activeSessionId = ref<string | null>(null)
const showSessionSearch = ref(false)
const sessionSearchQuery = ref('')

const hasMessages = computed(() => messages.value.length > 0)

/** Hermes-enhanced: Pinned first, then recent */
const sortedSessions = computed(() => {
  const items = [...sessions.value]
  items.sort((a, b) => {
    if (a.pinned && !b.pinned) return -1
    if (!a.pinned && b.pinned) return 1
    return b.timestamp - a.timestamp
  })
  return items
})

const filteredSessions = computed(() => {
  const items = sortedSessions.value.filter(s => !s.archived)
  if (!sessionSearchQuery.value.trim()) return items
  const q = sessionSearchQuery.value.toLowerCase()
  return items.filter(s =>
    s.title.toLowerCase().includes(q) || s.lastMessage.toLowerCase().includes(q)
  )
})

const pinnedSessions = computed(() => sortedSessions.value.filter(s => s.pinned && !s.archived))
const unpinnedSessions = computed(() => sortedSessions.value.filter(s => !s.pinned && !s.archived))

/** Batch delete */
const batchDeleteMode = ref(false)
const selectedSessions = ref<Set<string>>(new Set())

/** Context menu */
const contextMenuSession = ref<string | null>(null)
const contextMenuPos = ref({ x: 0, y: 0 })

/** Rename */
const renameSessionId = ref<string | null>(null)
const renameText = ref('')

/** New Chat Drawer */
const showNewChatDrawer = ref(false)
const newChatAgent = ref('hermes')
const newChatMode = ref('global')
const newChatApiMode = ref('default')
const newChatModel = ref('')
const newChatWorkspace = ref('')

/** Chat Tool Panel (Files / Terminal) */
const showToolPanel = ref(false)
const toolPanelTab = ref<'files' | 'terminal'>('files')

/** Session 26: Chat Outline Panel */
const showOutline = ref(false)

function handleOutlineScrollTo(elementId: string): void {
  const container = mc.value
  if (!container) return
  const el = container.querySelector(`#${elementId}`)
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" })
    // 短暂高亮
    el.classList.add("outline-highlight")
    setTimeout(() => el.classList.remove("outline-highlight"), 2000)
  }
}

function loadSessions() {
  try {
    const stored = localStorage.getItem('chat_sessions')
    if (stored) sessions.value = JSON.parse(stored)
  } catch {}
}

function saveSessions() {
  try {
    localStorage.setItem('chat_sessions', JSON.stringify(sessions.value))
  } catch {}
}

/** Session 25: Markdown → HTML 渲染（支持 Mermaid/KaTeX/代码高亮）
 *  Session 26: 添加 headingPrefix 用于对话大纲跳转 */
function renderMessageHtml(content: string, msgIndex: number): string {
  return renderMarkdownToHtml(content, `chat-h-${msgIndex}`)
}

function newSession() {
  const id = `sess_${Date.now()}`
  activeSessionId.value = id
  messages.value = []
  sessions.value.unshift({
    id, title: '新对话', lastMessage: '', timestamp: Date.now(), messageCount: 0
  })
  saveSessions()
}

function switchSession(id: string) {
  activeSessionId.value = id
  showSessionSearch.value = false
  const stored = localStorage.getItem(`chat_msgs_${id}`)
  try { messages.value = stored ? JSON.parse(stored) : [] } catch { messages.value = [] }
}

function deleteSession(id: string) {
  sessions.value = sessions.value.filter(s => s.id !== id)
  localStorage.removeItem(`chat_msgs_${id}`)
  if (activeSessionId.value === id) {
    activeSessionId.value = null
    messages.value = []
  }
  saveSessions()
}

function saveCurrentMessages() {
  if (activeSessionId.value) {
    localStorage.setItem(`chat_msgs_${activeSessionId.value}`, JSON.stringify(messages.value))
    const session = sessions.value.find(s => s.id === activeSessionId.value)
    if (session) {
      const lastUser = [...messages.value].reverse().find(m => m.role === 'user')
      session.lastMessage = lastUser?.content?.slice(0, 60) || ''
      session.timestamp = Date.now()
      session.messageCount = messages.value.length
      if (session.title === '新对话' && lastUser) {
        session.title = lastUser.content.slice(0, 30) + (lastUser.content.length > 30 ? '...' : '')
      }
    }
    saveSessions()
  }
}

/** Toggle pin */
function togglePinSession(id: string, e?: MouseEvent) {
  e?.stopPropagation()
  const session = sessions.value.find(s => s.id === id)
  if (session) {
    session.pinned = !session.pinned
    saveSessions()
  }
}

/** Toggle archive */
function toggleArchiveSession(id: string) {
  const session = sessions.value.find(s => s.id === id)
  if (session) {
    session.archived = !session.archived
    saveSessions()
  }
}

/** Rename */
function startRename(id: string, currentTitle: string) {
  renameSessionId.value = id
  renameText.value = currentTitle
  nextTick(() => {
    const input = document.querySelector(`[data-rename-input="${id}"]`) as HTMLInputElement
    input?.focus()
    input?.select()
  })
}

function commitRename(id: string) {
  const session = sessions.value.find(s => s.id === id)
  if (session && renameText.value.trim()) {
    session.title = renameText.value.trim()
    saveSessions()
  }
  renameSessionId.value = null
  renameText.value = ''
}

function cancelRename() {
  renameSessionId.value = null
  renameText.value = ''
}

/** Batch delete */
function toggleBatchDeleteMode() {
  batchDeleteMode.value = !batchDeleteMode.value
  selectedSessions.value.clear()
}

function toggleSessionSelection(id: string) {
  if (selectedSessions.value.has(id)) {
    selectedSessions.value.delete(id)
  } else {
    selectedSessions.value.add(id)
  }
}

function batchDeleteSelected() {
  const ids = Array.from(selectedSessions.value)
  ids.forEach(id => {
    sessions.value = sessions.value.filter(s => s.id !== id)
    localStorage.removeItem(`chat_msgs_${id}`)
    if (activeSessionId.value === id) {
      activeSessionId.value = null
      messages.value = []
    }
  })
  selectedSessions.value.clear()
  batchDeleteMode.value = false
  saveSessions()
}

/** Context menu */
function openContextMenu(e: MouseEvent, id: string) {
  e.preventDefault()
  e.stopPropagation()
  contextMenuSession.value = id
  contextMenuPos.value = { x: e.clientX, y: e.clientY }
}

function closeContextMenu() {
  contextMenuSession.value = null
}

function closeAllMenus() {
  contextMenuSession.value = null
  showModelMenu.value = false
  showModeMenu.value = false
}

/** Export session as markdown */
function exportSession(id: string) {
  const session = sessions.value.find(s => s.id === id)
  if (!session) return
  const msgs = JSON.parse(localStorage.getItem(`chat_msgs_${id}`) || '[]') as Message[]
  let md = `# ${session.title}\n\n> ${new Date(session.timestamp).toLocaleString()}\n\n---\n\n`
  msgs.forEach(m => {
    md += `### ${m.role === 'user' ? '👤 User' : '🤖 Assistant'} — ${new Date(m.timestamp).toLocaleTimeString()}\n\n${m.content}\n\n`
    if (m.toolCalls?.length) {
      md += `**Tools Used:**\n${m.toolCalls.map(t => `- \`${t.name}\`: ${t.status}`).join('\n')}\n\n`
    }
    md += '---\n\n'
  })
  const blob = new Blob([md], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${session.title.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g, '_')}.md`
  a.click()
  URL.revokeObjectURL(url)
  closeContextMenu()
}

/** Copy session ID */
function copySessionId(id: string) {
  navigator.clipboard.writeText(id)
  closeContextMenu()
}

/** New Chat Drawer */
function openNewChatDrawer() {
  showNewChatDrawer.value = true
  // Default to current model
  newChatModel.value = selectedModel.value.id
}

function createFromDrawer() {
  const id = `sess_${Date.now()}`
  activeSessionId.value = id
  messages.value = []
  sessions.value.unshift({
    id,
    title: '新对话',
    lastMessage: '',
    timestamp: Date.now(),
    messageCount: 0,
    workspace: newChatWorkspace.value || undefined,
    model: newChatModel.value || undefined,
    agentMode: newChatAgent.value || undefined,
  })
  saveSessions()
  showNewChatDrawer.value = false
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

/** Hermes-style: Streaming chat with tool traces */
async function sendMessage(): Promise<void> {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  if (!activeSessionId.value) newSession()

  messages.value.push({ role: "user", content: text, timestamp: Date.now() })
  inputText.value = ""
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
      message: text,
      tools: ["calculate", "datetime_now", "get_weather", "web_search", "file_read", "codebase_search"],
      preferred_model: selectedModel.value.id,
      max_turns: 10,
      stream: true,
    }, {
      signal: abortController.value.signal,
      onDownloadProgress: (progressEvent: any) => {
        // Handle SSE streaming response
        const text = progressEvent.event?.target?.responseText || progressEvent.currentTarget?.responseText
        if (text) {
          const lines = text.split('\n')
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
    // Fallback: non-streaming response
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

function clearMessages() {
  messages.value = []
  if (activeSessionId.value) {
    localStorage.removeItem(`chat_msgs_${activeSessionId.value}`)
    saveSessions()
  }
}

onMounted(() => {
  loadSessions()
  document.addEventListener('click', closeAllMenus)
})

/** Session 25: 渲染 Mermaid/KaTeX 图表 */
let mdRenderTimer: ReturnType<typeof setTimeout> | null = null
onUpdated(() => {
  // 延迟渲染图表（等 v-html 更新 DOM）
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
  <div class="h-full flex flex-col bg-[var(--color-ide-surface)]">
    <!-- ── Header ───────────────────────────────────── -->
    <header class="flex items-center justify-between px-3 py-2 border-b border-[var(--color-ide-border)] shrink-0">
      <div class="flex items-center gap-2">
        <!-- Session switcher -->
        <button class="flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium hover:bg-[var(--color-ide-surface-hover)] transition-colors text-[var(--color-ide-text)]"
          @click="showSessionSearch = !showSessionSearch">
          <History :size="13" class="text-[var(--color-ide-text-dim)]" />
          <span class="max-w-[120px] truncate">{{ sessions.find(s => s.id === activeSessionId)?.title || '新对话' }}</span>
          <ChevronDown :size="10" class="text-[var(--color-ide-text-dim)]" />
        </button>
        <!-- New Chat Drawer button -->
        <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" title="新建对话（Agent/模型/工作区）" @click="openNewChatDrawer">
          <Sparkles :size="13" />
        </button>
        <!-- Toggle tool panel -->
        <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)]" :class="showToolPanel ? 'text-[var(--color-ide-accent)]' : 'text-[var(--color-ide-text-dim)]'"
          title="工具面板" @click="showToolPanel = !showToolPanel; showOutline = false">
          <PanelRight :size="13" />
        </button>
        <!-- Session 26: Toggle outline panel -->
        <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)]" :class="showOutline ? 'text-[var(--color-ide-accent)]' : 'text-[var(--color-ide-text-dim)]'"
          title="对话大纲" @click="showOutline = !showOutline; showToolPanel = false">
          <ListTree :size="13" />
        </button>
      </div>
      <div class="flex items-center gap-0.5">
        <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" title="清空对话" @click="clearMessages" v-if="hasMessages">
          <Trash2 :size="13" />
        </button>
      </div>
    </header>

    <!-- Session search overlay (enhanced) -->
    <div v-if="showSessionSearch" class="absolute top-10 left-3 right-3 z-50 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-lg shadow-xl max-h-80 overflow-y-auto" style="margin-top: -2px;">
      <!-- Search + Actions bar -->
      <div class="p-2 border-b border-[var(--color-ide-border)] space-y-1.5">
        <input v-model="sessionSearchQuery" type="text" placeholder="搜索对话..." class="w-full bg-[var(--color-ide-bg)] border border-[var(--color-ide-border)] rounded px-2 py-1 text-[12px] text-[var(--color-ide-text)] outline-none" autofocus />
        <div class="flex items-center gap-1">
          <button class="w-full text-left px-2 py-1 text-[11px] text-[var(--color-ide-accent)] hover:bg-[var(--color-ide-surface-hover)] rounded" @click="newSession();showSessionSearch=false">
            + 新建对话
          </button>
          <button class="px-2 py-1 text-[11px] rounded hover:bg-[var(--color-ide-surface-hover)] transition-colors"
            :class="batchDeleteMode ? 'text-red-400' : 'text-[var(--color-ide-text-dim)]'"
            @click="toggleBatchDeleteMode" title="批量管理">
            <Check :size="12" />
          </button>
        </div>
      </div>

      <!-- Batch delete action bar -->
      <div v-if="batchDeleteMode" class="px-2 py-1.5 border-b border-red-500/20 bg-red-500/5 flex items-center justify-between">
        <span class="text-[10px] text-red-400">已选 {{ selectedSessions.size }} 个</span>
        <button class="px-2 py-0.5 rounded text-[10px] font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 disabled:opacity-30"
          :disabled="selectedSessions.size === 0" @click="batchDeleteSelected">删除选中</button>
      </div>

      <!-- Pinned sessions -->
      <div v-if="pinnedSessions.length > 0 && !batchDeleteMode">
        <div class="px-3 py-1 text-[9px] font-semibold text-[var(--color-ide-text-dim)]/60 uppercase tracking-wider">已固定</div>
        <button v-for="s in pinnedSessions" :key="s.id"
          class="w-full text-left px-3 py-2 hover:bg-[var(--color-ide-surface-hover)] border-b border-[var(--color-ide-border)]/20 flex items-center justify-between group"
          :class="{ 'bg-[var(--color-ide-accent)]/5': s.id === activeSessionId }"
          @click="switchSession(s.id)" @contextmenu="openContextMenu($event, s.id)">
          <div class="flex items-center gap-1.5 min-w-0 flex-1">
            <Pin :size="10" class="text-[var(--color-ide-accent)] shrink-0" />
            <!-- Rename inline -->
            <template v-if="renameSessionId === s.id">
              <input :data-rename-input="s.id" v-model="renameText" type="text"
                class="bg-[var(--color-ide-bg)] border border-[var(--color-ide-accent)] rounded px-1 py-0 text-[11px] text-[var(--color-ide-text)] outline-none flex-1 min-w-0"
                @keydown.enter="commitRename(s.id)" @keydown.escape="cancelRename" @blur="commitRename(s.id)" @click.stop />
            </template>
            <template v-else>
              <div class="text-[12px] font-medium text-[var(--color-ide-text)] truncate">{{ s.title }}</div>
            </template>
          </div>
          <div class="flex items-center gap-0.5 shrink-0 ml-2">
            <span class="text-[9px] text-[var(--color-ide-text-dim)]">{{ s.messageCount }}</span>
            <button class="opacity-0 group-hover:opacity-100 p-0.5 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-accent)] transition-all" @click.stop="togglePinSession(s.id, $event)" title="取消固定">
              <Pin :size="10" />
            </button>
          </div>
        </button>
      </div>

      <!-- Recent sessions -->
      <div v-if="unpinnedSessions.length > 0 || batchDeleteMode">
        <div v-if="!batchDeleteMode" class="px-3 py-1 text-[9px] font-semibold text-[var(--color-ide-text-dim)]/60 uppercase tracking-wider">最近</div>
        <template v-for="s in (batchDeleteMode ? sortedSessions.filter(s => !s.archived) : unpinnedSessions)" :key="s.id">
          <div class="w-full flex items-center border-b border-[var(--color-ide-border)]/20 group"
            :class="{ 'bg-[var(--color-ide-accent)]/5': s.id === activeSessionId }">
            <!-- Batch select checkbox -->
            <button v-if="batchDeleteMode" class="px-2 py-2 text-[var(--color-ide-text-dim)]" @click.stop="toggleSessionSelection(s.id)">
              <Square v-if="!selectedSessions.has(s.id)" :size="12" />
              <Check v-else :size="12" class="text-red-400" />
            </button>
            <button v-else class="flex-1 text-left px-3 py-2 hover:bg-[var(--color-ide-surface-hover)] flex items-center justify-between min-w-0"
              @click="switchSession(s.id)" @contextmenu="openContextMenu($event, s.id)">
              <div class="min-w-0 flex-1">
                <template v-if="renameSessionId === s.id">
                  <input :data-rename-input="s.id" v-model="renameText" type="text"
                    class="bg-[var(--color-ide-bg)] border border-[var(--color-ide-accent)] rounded px-1 py-0 text-[11px] text-[var(--color-ide-text)] outline-none w-full"
                    @keydown.enter="commitRename(s.id)" @keydown.escape="cancelRename" @blur="commitRename(s.id)" @click.stop />
                </template>
                <template v-else>
                  <div class="text-[12px] font-medium text-[var(--color-ide-text)] truncate">{{ s.title }}</div>
                  <div class="text-[10px] text-[var(--color-ide-text-dim)] truncate mt-0.5 flex items-center gap-1">
                    <span v-if="s.model" class="px-1 py-0 rounded text-[9px] bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-accent)]/70">{{ s.model }}</span>
                    {{ s.lastMessage || '空对话' }}
                  </div>
                </template>
              </div>
              <div class="flex items-center gap-1 shrink-0 ml-2">
                <Pin v-if="s.pinned" :size="10" class="text-[var(--color-ide-accent)]" />
                <span class="text-[9px] text-[var(--color-ide-text-dim)]">{{ formatTime(s.timestamp) }}</span>
                <button class="opacity-0 group-hover:opacity-100 p-0.5 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-accent)] transition-all"
                  @click.stop="togglePinSession(s.id, $event)" title="固定">
                  <Pin :size="10" />
                </button>
                <MoreHorizontal v-if="!batchDeleteMode" :size="11" class="opacity-0 group-hover:opacity-100 text-[var(--color-ide-text-dim)]" @click.stop="openContextMenu($event, s.id)" />
              </div>
            </button>
          </div>
        </template>
      </div>

      <div v-if="filteredSessions.length === 0 && sessions.length === 0" class="px-3 py-4 text-center text-[11px] text-[var(--color-ide-text-dim)]">暂无对话记录</div>
      <div v-else-if="filteredSessions.length === 0" class="px-3 py-4 text-center text-[11px] text-[var(--color-ide-text-dim)]">无匹配对话</div>
    </div>

    <!-- Context menu (positioned absolute) -->
    <Teleport to="body">
      <div v-if="contextMenuSession"
        class="fixed z-[9999] bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-lg shadow-2xl py-1 min-w-[160px]"
        :style="{ left: contextMenuPos.x + 'px', top: contextMenuPos.y + 'px' }"
        @click.stop>
        <button class="w-full text-left px-3 py-1.5 text-[11px] text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-2"
          @click="togglePinSession(contextMenuSession!);closeContextMenu()">
          <Pin :size="11" /> {{ sessions.find(s => s.id === contextMenuSession)?.pinned ? '取消固定' : '固定到顶部' }}
        </button>
        <button class="w-full text-left px-3 py-1.5 text-[11px] text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-2"
          @click="startRename(contextMenuSession!, sessions.find(s => s.id === contextMenuSession)?.title || '');closeContextMenu()">
          <FileText :size="11" /> 重命名
        </button>
        <button class="w-full text-left px-3 py-1.5 text-[11px] text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-2"
          @click="toggleArchiveSession(contextMenuSession!);closeContextMenu()">
          <Archive :size="11" /> {{ sessions.find(s => s.id === contextMenuSession)?.archived ? '取消归档' : '归档' }}
        </button>
        <div class="border-t border-[var(--color-ide-border)]/30 my-0.5" />
        <button class="w-full text-left px-3 py-1.5 text-[11px] text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-2"
          @click="exportSession(contextMenuSession!)">
          <Download :size="11" /> 导出 Markdown
        </button>
        <button class="w-full text-left px-3 py-1.5 text-[11px] text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] flex items-center gap-2"
          @click="copySessionId(contextMenuSession!)">
          <Copy :size="11" /> 复制会话 ID
        </button>
        <div class="border-t border-[var(--color-ide-border)]/30 my-0.5" />
        <button class="w-full text-left px-3 py-1.5 text-[11px] text-red-400 hover:bg-red-500/10 flex items-center gap-2"
          @click="deleteSession(contextMenuSession!);closeContextMenu()">
          <Trash2 :size="11" /> 删除
        </button>
      </div>
    </Teleport>

    <!-- New Chat Drawer (slide-in from right) -->
    <Teleport to="body">
      <Transition name="drawer-slide">
        <div v-if="showNewChatDrawer" class="fixed inset-0 z-[9998] flex">
          <!-- Backdrop -->
          <div class="absolute inset-0 bg-black/30" @click="showNewChatDrawer = false" />
          <!-- Drawer -->
          <div class="ml-auto w-80 h-full bg-[var(--color-ide-surface)] border-l border-[var(--color-ide-border)] shadow-2xl flex flex-col z-10 overflow-y-auto">
            <div class="flex items-center justify-between px-4 py-3 border-b border-[var(--color-ide-border)] shrink-0">
              <h3 class="text-[13px] font-semibold text-[var(--color-ide-text)]">新建对话</h3>
              <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" @click="showNewChatDrawer = false">
                <X :size="14" />
              </button>
            </div>

            <div class="flex-1 p-4 space-y-5">
              <!-- Agent Selection -->
              <div>
                <label class="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ide-text-dim)]/60 mb-2 block">Agent</label>
                <div class="space-y-1">
                  <button v-for="agent in [{id:'hermes',label:'Hermes',desc:'全能AI助手'},{id:'claude-code',label:'Claude Code',desc:'代码专家'},{id:'codex',label:'Codex',desc:'快速代码生成'}]" :key="agent.id"
                    @click="newChatAgent = agent.id"
                    class="w-full text-left px-3 py-2 rounded-lg border transition-all"
                    :class="newChatAgent === agent.id ? 'border-[var(--color-ide-accent)] bg-[var(--color-ide-accent)]/5' : 'border-[var(--color-ide-border)] hover:border-[var(--color-ide-accent)]/30'">
                    <div class="text-[12px] font-medium text-[var(--color-ide-text)]">{{ agent.label }}</div>
                    <div class="text-[10px] text-[var(--color-ide-text-dim)]">{{ agent.desc }}</div>
                  </button>
                </div>
              </div>

              <!-- Agent Mode -->
              <div>
                <label class="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ide-text-dim)]/60 mb-2 block">Agent 模式</label>
                <div class="flex gap-2">
                  <button v-for="mode in [{id:'global',label:'全局'},{id:'scoped',label:'区域'}]" :key="mode.id"
                    @click="newChatMode = mode.id"
                    class="flex-1 px-3 py-1.5 rounded-md text-[11px] text-center transition-all border"
                    :class="newChatMode === mode.id ? 'border-[var(--color-ide-accent)] bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-text)]' : 'border-[var(--color-ide-border)] text-[var(--color-ide-text-dim)] hover:border-[var(--color-ide-accent)]/30'">
                    {{ mode.label }}
                  </button>
                </div>
              </div>

              <!-- Model Selection -->
              <div>
                <label class="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ide-text-dim)]/60 mb-2 block">模型</label>
                <div class="space-y-1">
                  <div class="text-[9px] uppercase tracking-wider text-[var(--color-ide-text-dim)]/40 px-1 mb-1">本地模型</div>
                  <button v-for="m in models.filter(m => m.id.includes(':') || m.id.includes('local'))" :key="m.id"
                    @click="newChatModel = m.id"
                    class="w-full text-left px-3 py-1.5 rounded-md text-[11px] transition-all border flex items-center justify-between"
                    :class="newChatModel === m.id ? 'border-[var(--color-ide-accent)] bg-[var(--color-ide-accent)]/5 text-[var(--color-ide-text)]' : 'border-transparent text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]'">
                    <span>{{ m.label }}</span>
                    <span class="text-[9px] opacity-50">{{ m.desc }}</span>
                  </button>
                  <div class="text-[9px] uppercase tracking-wider text-[var(--color-ide-text-dim)]/40 px-1 mb-1 mt-2">API 模型</div>
                  <button v-for="m in models.filter(m => !m.id.includes(':') && !m.id.includes('local'))" :key="m.id"
                    @click="newChatModel = m.id"
                    class="w-full text-left px-3 py-1.5 rounded-md text-[11px] transition-all border flex items-center justify-between"
                    :class="newChatModel === m.id ? 'border-[var(--color-ide-accent)] bg-[var(--color-ide-accent)]/5 text-[var(--color-ide-text)]' : 'border-transparent text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]'">
                    <span>{{ m.label }}</span>
                    <span class="text-[9px] opacity-50">{{ m.desc }}</span>
                  </button>
                </div>
              </div>

              <!-- Workspace -->
              <div>
                <label class="text-[10px] font-semibold uppercase tracking-wider text-[var(--color-ide-text-dim)]/60 mb-2 block">工作区目录</label>
                <div class="flex items-center gap-2">
                  <input v-model="newChatWorkspace" type="text" placeholder="可选，输入目录路径..."
                    class="flex-1 bg-[var(--color-ide-bg)] border border-[var(--color-ide-border)] rounded-md px-2 py-1.5 text-[11px] text-[var(--color-ide-text)] outline-none focus:border-[var(--color-ide-accent)]" />
                  <button class="p-1.5 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" title="选择目录">
                    <FolderOpen :size="14" />
                  </button>
                </div>
              </div>
            </div>

            <!-- Drawer Footer -->
            <div class="px-4 py-3 border-t border-[var(--color-ide-border)] flex items-center gap-2">
              <button class="flex-1 px-3 py-2 rounded-lg text-[12px] font-semibold bg-[var(--color-ide-accent)] text-white hover:brightness-110 transition-all"
                @click="createFromDrawer">
                开始对话
              </button>
              <button class="px-3 py-2 rounded-lg text-[12px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] transition-all"
                @click="showNewChatDrawer = false">
                取消
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- ── Messages + Tool Panel Split ──────────────── -->
    <div class="flex-1 flex min-h-0">
      <!-- Messages Area -->
      <div ref="mc" class="flex-1 overflow-y-auto px-4 py-3 space-y-3" :class="{ 'border-r border-[var(--color-ide-border)]': showToolPanel || showOutline }">
        <!-- Welcome State -->
        <div v-if="!hasMessages && !isLoading" class="h-full flex flex-col items-center justify-center select-none">
          <div class="mb-4 w-16 h-16 rounded-2xl flex items-center justify-center bg-gradient-to-br from-[rgba(192,193,255,0.08)] to-transparent border border-solid border-[rgba(192,193,255,0.15)]">
            <Sparkles :size="28" class="text-[var(--color-ide-accent)]" />
          </div>
          <p class="text-sm font-semibold mb-1 text-[var(--color-ide-text-bright)]">AI 编程助手</p>
          <p class="text-xs mb-5 text-[var(--color-ide-text-dim)]">有什么可以帮你的？</p>
          <div class="w-full space-y-1.5 max-w-[260px]">
            <button v-for="action in [
              {text:'分析代码性能',prompt:'帮我分析当前组件的性能'},
              {text:'生成 Vue 组件',prompt:'生成一个 Vue 组件'},
              {text:'解释项目架构',prompt:'解释这个项目的架构'},
              {text:'调试报错',prompt:'帮我调试这段代码中的错误'}
            ]" :key="action.text"
              @click="inputText=action.prompt; sendMessage()"
              class="quick-action-btn w-full text-left text-[12px] px-3 py-2 rounded-lg border border-solid transition-colors duration-150 border-[var(--color-ide-border)] text-[var(--color-ide-text-dim)] hover:border-[var(--color-ide-accent)]/30 hover:bg-[rgba(192,193,255,0.04)] hover:text-[var(--color-ide-text)]">
              {{ action.text }}
            </button>
          </div>
        </div>

        <!-- Messages List -->
        <template v-else>
          <div v-for="(msg, idx) in messages" :key="idx" class="flex gap-2 items-start" :class="{ 'flex-row-reverse': msg.role === 'user' }">
            <!-- AI Message Bubble -->
            <template v-if="msg.role === 'assistant'">
              <div class="ai-bubble max-w-[88%] rounded-xl px-3 py-2.5 border-l-[3px] border-l-[var(--color-chat-ai-border)] bg-[var(--color-chat-ai-bg)] shadow-[0_2px_8px_rgba(0,0,0,0.15)]">
                <!-- Loading dots -->
                <div v-if="isLoading && !msg.content && (!msg.toolCalls || msg.toolCalls.length === 0)" class="flex items-center gap-2 py-1 text-[var(--color-ide-text-dim)]">
                  <span class="flex gap-1">
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:0ms"/>
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:150ms"/>
                    <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:300ms"/>
                  </span>
                  <span class="text-[12px]">正在思考...</span>
                </div>

                <!-- Tool Calls -->
                <div v-if="msg.toolCalls && msg.toolCalls.length > 0" class="mb-2 space-y-1">
                  <div v-for="tc in msg.toolCalls" :key="tc.name"
                    class="flex items-center gap-1.5 text-[10px] px-2 py-1 rounded-md bg-[rgba(0,0,0,0.2)] border border-[var(--color-ide-border)]/30">
                    <Wrench :size="10" class="shrink-0" :class="tc.status === 'running' ? 'text-yellow-400 animate-pulse' : tc.status === 'error' ? 'text-red-400' : 'text-green-400'" />
                    <span class="text-[var(--color-ide-text-dim)] font-medium">{{ tc.name }}</span>
                    <span v-if="tc.status === 'running'" class="text-yellow-400 ml-auto">执行中...</span>
                    <span v-else-if="tc.status === 'error'" class="text-red-400 ml-auto">失败</span>
                    <span v-else class="text-green-400/60 ml-auto">✓</span>
                  </div>
                </div>

                <!-- Content — Markdown 渲染 (Session 25) -->
                <div v-if="msg.content" ref="mdMessageRef" class="text-[12px] leading-relaxed break-words text-[var(--color-ide-text)] markdown-body"
                  v-html="renderMessageHtml(msg.content, idx)" />
              </div>
              <span class="text-[9px] mt-auto ml-1.5 whitespace-nowrap text-[var(--color-ide-text-dim)] tabular-nums flex flex-col items-center gap-0.5">
                {{ formatTime(msg.timestamp) }}
                <span class="text-[8px] opacity-50" v-if="msg.modelUsed">{{ msg.modelUsed?.split('-')[0] }}</span>
              </span>
            </template>

            <!-- User Message Bubble -->
            <template v-else-if="msg.role === 'user'">
              <div class="user-bubble rounded-xl px-3 py-2 max-w-[80%] bg-[var(--color-chat-user-bg)] border border-solid border-[var(--color-chat-user-border)]">
                <div class="text-[12px] leading-relaxed break-words text-[var(--color-ide-text)] markdown-body"
                  v-html="renderMessageHtml(msg.content, idx)" />
              </div>
              <span class="text-[9px] mt-auto ml-1.5 whitespace-nowrap text-[var(--color-ide-text-dim)] tabular-nums">你</span>
            </template>
          </div>
        </template>
      </div>

      <!-- Session 26: Chat Outline Panel -->
      <ChatOutlinePanel
        :messages="messages"
        :visible="showOutline"
        @close="showOutline = false"
        @scroll-to="handleOutlineScrollTo"
      />

      <!-- Chat Tool Panel (Files / Terminal tabs) -->
      <div v-if="showToolPanel" class="w-60 shrink-0 flex flex-col bg-[var(--color-ide-bg-secondary)] border-l border-[var(--color-ide-border)]" style="resize: horizontal; overflow: auto; min-width: 180px; max-width: 400px;">
        <!-- Tab bar -->
        <div class="flex items-center border-b border-[var(--color-ide-border)] shrink-0">
          <button class="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-[10px] font-medium transition-colors border-b-2"
            :class="toolPanelTab === 'files' ? 'border-[var(--color-ide-accent)] text-[var(--color-ide-text)]' : 'border-transparent text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
            @click="toolPanelTab = 'files'">
            <FolderOpen :size="11" /> 文件
          </button>
          <button class="flex-1 flex items-center justify-center gap-1 px-3 py-2 text-[10px] font-medium transition-colors border-b-2"
            :class="toolPanelTab === 'terminal' ? 'border-[var(--color-ide-accent)] text-[var(--color-ide-text)]' : 'border-transparent text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
            @click="toolPanelTab = 'terminal'">
            <Terminal :size="11" /> 终端
          </button>
          <button class="px-2 py-2 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]" @click="showToolPanel = false">
            <X :size="11" />
          </button>
        </div>

        <!-- Files panel -->
        <div v-if="toolPanelTab === 'files'" class="flex-1 overflow-y-auto p-2">
          <div class="text-[10px] text-[var(--color-ide-text-dim)]/60 uppercase tracking-wider px-2 py-1 mb-1">项目文件</div>
          <div class="text-[11px] text-[var(--color-ide-text-dim)] px-2 py-4 text-center">选择工作区目录后可浏览文件</div>
          <!-- File tree placeholder - will be populated when workspace is set -->
          <div class="space-y-0.5">
            <div v-if="newChatWorkspace" class="text-[10px] text-[var(--color-ide-text)]/50 px-2">
              工作区: {{ newChatWorkspace }}
            </div>
          </div>
        </div>

        <!-- Terminal panel (read-only preview) -->
        <div v-if="toolPanelTab === 'terminal'" class="flex-1 overflow-y-auto p-2">
          <div class="text-[10px] text-[var(--color-ide-text-dim)]/60 uppercase tracking-wider px-2 py-1 mb-1">命令输出</div>
          <div class="bg-[var(--color-ide-bg)] rounded-md p-2 font-mono text-[10px] text-[var(--color-ide-text)]/70 leading-relaxed min-h-[100px] max-h-full overflow-y-auto">
            <span class="text-[var(--color-ide-text-dim)]">$ </span>等待命令执行...
          </div>
        </div>
      </div>
    </div>

    <!-- ── Bottom Input Panel (Hermes-style) ────────── -->
    <div class="shrink-0 border-t border-[var(--color-ide-border)] px-3 pt-2 pb-2 space-y-2 bg-[var(--color-ide-bg-secondary)]">
      <!-- Model & Mode Selectors Row -->
      <div class="flex items-center gap-1.5">
        <!-- Model Selector -->
        <div class="relative">
          <button @click="showModelMenu = !showModelMenu"
            class="flex items-center gap-1 h-6 pl-2 pr-1.5 rounded-md text-[10px] font-semibold transition-all duration-150 border border-solid bg-[var(--color-editor-bg)] border-[var(--color-ide-border)] text-[var(--color-ide-text)] hover:border-[var(--color-ide-accent)]/50">
            <span>{{ selectedModel.label }}</span>
            <ChevronDown :size="10" class="text-[var(--color-ide-text-dim)]" />
          </button>
          <Transition name="fade">
            <div v-if="showModelMenu" class="absolute bottom-full left-0 mb-1 min-w-[180px] z-50 py-1 rounded-md bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] shadow-xl">
              <button v-for="m in models" :key="m.id"
                @click="selectedModel=m;showModelMenu=false"
                class="w-full text-left px-3 py-1.5 text-[11px] text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] flex items-center justify-between gap-2">
                <span>{{ m.label }} <span class="text-[var(--color-ide-text-dim)] font-normal italic text-[10px]">{{ m.desc }}</span></span>
                <svg v-if="m.id===selectedModel.id" width="10" height="8" viewBox="0 0 12 9" fill="none"><path d="M1 3l4 4 6-6" stroke="var(--color-ide-accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
          </Transition>
        </div>
        <div class="w-px h-3 bg-[var(--color-ide-border)]" />
        <!-- Mode Selector -->
        <div class="relative">
          <button @click="showModeMenu = !showModeMenu"
            class="flex items-center gap-1 h-6 pl-2 pr-1.5 rounded-md text-[10px] font-medium transition-all duration-150 border border-solid bg-[var(--color-editor-bg)] border-[var(--color-ide-border)] text-[var(--color-ide-text)] hover:border-[var(--color-ide-accent)]/50">
            <span>{{ selectedMode.label }}</span>
            <ChevronDown :size="10" class="text-[var(--color-ide-text-dim)]" />
          </button>
          <Transition name="fade">
            <div v-if="showModeMenu" class="absolute bottom-full left-0 mb-1 min-w-[110px] z-50 py-1 rounded-md bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] shadow-xl">
              <button v-for="m in modes" :key="m.id"
                @click="selectedMode=m;showModeMenu=false"
                class="w-full text-left px-3 py-1.5 text-[11px] text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] flex items-center justify-between">
                <span>{{ m.label }}</span>
                <svg v-if="m.id===selectedMode.id" width="10" height="8" viewBox="0 0 12 9" fill="none"><path d="M1 3l4 4 6-6" stroke="var(--color-ide-accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
          </Transition>
        </div>
      </div>

      <!-- Input Box -->
      <div class="input-box relative rounded-lg border border-solid border-[var(--color-ide-border)] bg-[var(--color-chat-input-bg)] transition-all duration-150 focus-within:border-[var(--color-ide-border-focus)]">
        <textarea v-model="inputText" rows="1"
          placeholder="输入指令或提问 (Enter 发送)"
          class="w-full resize-none outline-none text-[12px] bg-transparent px-3 pt-2 pb-7 leading-relaxed text-[var(--color-ide-text)] placeholder:text-[rgba(144,143,160,0.45)]"
          @keydown.enter.exact.prevent="sendMessage"
          @keydown.shift.enter.prevent="inputText += '\n'" />

        <div class="absolute bottom-1.5 left-2 flex items-center gap-0.5">
          <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" title="附件">
            <Paperclip :size="12" />
          </button>
          <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" title="图片">
            <ImagePlus :size="12" />
          </button>
          <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" title="语音输入">
            <Mic :size="12" />
          </button>
        </div>

        <div class="absolute bottom-1.5 right-1.5 flex items-center gap-1">
          <button v-if="isLoading" class="stop-btn flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
            @click="stopGeneration">
            <StopCircle :size="11" /> 停止
          </button>
          <button v-else class="send-btn flex items-center gap-1 px-2.5 py-1 rounded-md text-[10px] font-bold transition-all duration-150 bg-[var(--color-ide-accent)] text-white hover:brightness-110 active:scale-[0.97]"
            :class="{ 'opacity-35 cursor-not-allowed pointer-events-none': !inputText.trim() || isLoading }"
            :disabled="!inputText.trim() || isLoading"
            @click="sendMessage">
            发送 <Send :size="10" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.quick-action-btn { background: transparent; cursor: pointer; }
.ai-bubble { box-shadow: 0 1px 2px rgba(0,0,0,0.08), 0 4px 16px rgba(0,0,0,0.1); }
.user-bubble { box-shadow: 0 1px 4px rgba(0,0,0,0.06); }
.fade-enter-active, .fade-leave-active { transition: opacity 0.12s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* New Chat Drawer slide-in animation */
.drawer-slide-enter-active { transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1); }
.drawer-slide-leave-active { transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.drawer-slide-enter-from,
.drawer-slide-leave-to {
  opacity: 0;
}
.drawer-slide-enter-from :deep(> div:last-child),
.drawer-slide-leave-to :deep(> div:last-child) {
  transform: translateX(100%);
}
.drawer-slide-enter-active :deep(> div:last-child),
.drawer-slide-leave-active :deep(> div:last-child) {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── Session 25: Markdown 渲染样式 ── */
.markdown-body :deep(.md-h1) { font-size: 18px; font-weight: 700; margin: 12px 0 6px; color: var(--color-ide-text); border-bottom: 1px solid var(--color-ide-border); padding-bottom: 4px; }
.markdown-body :deep(.md-h2) { font-size: 15px; font-weight: 700; margin: 10px 0 5px; color: var(--color-ide-text); border-bottom: 1px solid var(--color-ide-border); padding-bottom: 3px; }
.markdown-body :deep(.md-h3) { font-size: 14px; font-weight: 600; margin: 8px 0 4px; color: var(--color-ide-text); }
.markdown-body :deep(.md-h4) { font-size: 13px; font-weight: 600; margin: 6px 0 3px; color: var(--color-ide-text); }
.markdown-body :deep(.md-h5),
.markdown-body :deep(.md-h6) { font-size: 12px; font-weight: 600; margin: 4px 0 2px; color: var(--color-ide-text-dim); }
.markdown-body :deep(.md-p) { margin: 4px 0; line-height: 1.6; }
.markdown-body :deep(strong) { font-weight: 700; color: var(--color-ide-text); }
.markdown-body :deep(em) { font-style: italic; }
.markdown-body :deep(del) { text-decoration: line-through; opacity: 0.6; }
.markdown-body :deep(.md-link) { color: var(--color-ide-accent); text-decoration: underline; text-underline-offset: 2px; }
.markdown-body :deep(.md-link:hover) { opacity: 0.8; }
.markdown-body :deep(.md-inline-code) {
  background: var(--color-ide-surface-active);
  color: var(--color-ide-accent);
  padding: 1px 5px; border-radius: 3px;
  font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace;
  font-size: 11px;
}
.markdown-body :deep(.md-blockquote) {
  border-left: 3px solid var(--color-ide-accent);
  padding: 4px 12px; margin: 6px 0;
  background: var(--color-ide-surface);
  border-radius: 0 4px 4px 0;
  opacity: 0.85;
}
.markdown-body :deep(.md-ul),
.markdown-body :deep(.md-ol) { margin: 4px 0; padding-left: 20px; }
.markdown-body :deep(.md-ul li),
.markdown-body :deep(.md-ol li) { margin: 2px 0; line-height: 1.5; }
.markdown-body :deep(.md-hr) {
  border: none; border-top: 1px solid var(--color-ide-border);
  margin: 12px 0; opacity: 0.5;
}
.markdown-body :deep(.md-image) { max-width: 100%; height: auto; margin: 4px 0; }

/* Code Block */
.markdown-body :deep(.md-code-block) {
  margin: 6px 0; border-radius: 6px; overflow: hidden;
  border: 1px solid var(--color-ide-border);
  background: var(--color-terminal-bg);
}
.markdown-body :deep(.md-code-header) {
  display: flex; align-items: center; justify-content: space-between;
  padding: 3px 10px; font-size: 10px;
  background: var(--color-ide-surface);
  border-bottom: 1px solid var(--color-ide-border);
}
.markdown-body :deep(.md-code-lang) {
  color: var(--color-ide-text-dim); text-transform: uppercase; font-weight: 600;
  letter-spacing: 0.5px;
}
.markdown-body :deep(.md-code-copy) {
  padding: 2px 4px; border-radius: 3px; cursor: pointer;
  color: var(--color-ide-text-dim); background: transparent; border: none;
  display: flex; align-items: center;
}
.markdown-body :deep(.md-code-copy:hover) {
  background: var(--color-ide-surface-hover); color: var(--color-ide-text);
}
.markdown-body :deep(.md-code-content) {
  display: block; padding: 8px 10px; overflow-x: auto;
  font-family: 'JetBrains Mono', 'Cascadia Code', Consolas, monospace;
  font-size: 11px; line-height: 1.6; color: var(--color-ide-text-dim);
  white-space: pre; tab-size: 2;
}
/* 代码高亮 */
.markdown-body :deep(.md-kw) { color: #C678DD; font-weight: 600; }
.markdown-body :deep(.md-str) { color: #98C379; }
.markdown-body :deep(.md-cmt) { color: #5C6370; font-style: italic; }
.markdown-body :deep(.md-num) { color: #D19A66; }

/* Mermaid */
.markdown-body :deep(.md-mermaid-block) {
  margin: 6px 0; border-radius: 6px; overflow: hidden;
  border: 1px solid var(--color-ide-border);
  background: #fff;
}
.markdown-body :deep(.md-mermaid-render) {
  padding: 12px; display: flex; justify-content: center;
  overflow-x: auto;
}
.markdown-body :deep(.md-mermaid-render svg) {
  max-width: 100%; height: auto;
}

/* KaTeX */
.markdown-body :deep(.md-katex-block) {
  margin: 6px 0; padding: 8px 0;
  display: flex; justify-content: center;
  overflow-x: auto;
}
.markdown-body :deep(.katex-inline) {
  color: var(--color-ide-accent);
}

/* Table */
.markdown-body :deep(.md-table) {
  border-collapse: collapse; margin: 6px 0; width: 100%;
  font-size: 11px;
}
.markdown-body :deep(.md-table th),
.markdown-body :deep(.md-table td) {
  border: 1px solid var(--color-ide-border);
  padding: 4px 8px; text-align: left;
}
.markdown-body :deep(.md-table th) {
  background: var(--color-ide-surface);
  font-weight: 600; color: var(--color-ide-text);
}

/* Session 26: 大纲跳转高亮动画 */
.outline-highlight {
  animation: outline-flash 2s ease-out;
}
@keyframes outline-flash {
  0% { background: rgba(192, 193, 255, 0.15); }
  100% { background: transparent; }
}
</style>
