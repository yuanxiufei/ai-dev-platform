<template>
  <div class="logs-page">
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">日志查看器</h1>
        <span class="page-desc">查看系统各通道日志，支持实时流式推送</span>
      </div>
      <div class="header-actions">
        <label class="auto-scroll-label">
          <input v-model="autoScroll" type="checkbox" /> 自动滚动
        </label>
        <button
          v-if="wsConnected && selectedChannel"
          class="btn-connected"
          title="实时流已连接"
        >
          <Radio :size="12" /> 实时
        </button>
      </div>
    </header>

    <div class="logs-layout">
      <!-- 左侧通道列表 -->
      <aside class="channel-sidebar">
        <div class="sidebar-header">通道列表</div>
        <div class="channel-list">
          <button
            v-for="ch in channels"
            :key="ch.name"
            :class="['channel-item', { active: selectedChannel === ch.name }]"
            @click="selectChannel(ch.name)"
          >
            <div class="ch-name-row">
              <span class="ch-dot" :class="`dot-${ch.name}`" />
              <span class="ch-name">{{ ch.name }}</span>
            </div>
            <span class="ch-count">{{ ch.count }}</span>
          </button>
        </div>
        <div v-if="channels.length === 0" class="sidebar-empty">暂无通道</div>
      </aside>

      <!-- 右侧日志内容 -->
      <main class="log-content">
        <!-- 工具栏 -->
        <div class="toolbar">
          <div class="toolbar-left">
            <div class="level-filters">
              <button
                v-for="lv in logLevels"
                :key="lv"
                :class="['level-btn', `level-${lv}`, { active: activeLevel === lv }]"
                @click="activeLevel = activeLevel === lv ? null : lv"
              >
                {{ lv.toUpperCase() }}
              </button>
            </div>
            <div class="search-box">
              <Search :size="14" class="search-icon" />
              <input
                v-model="searchQ"
                placeholder="搜索日志..."
                class="search-input"
                @keyup.enter="handleSearch"
              />
            </div>
          </div>
          <div class="toolbar-right">
            <button class="btn-ghost" @click="refreshLogs" :disabled="!selectedChannel">
              <RefreshCw :size="14" /> 刷新
            </button>
            <button
              class="btn-ghost btn-danger"
              @click="handleClear"
              :disabled="!selectedChannel"
            >
              <Trash2 :size="14" /> 清空
            </button>
          </div>
        </div>

        <!-- 日志列表 -->
        <div ref="logContainer" class="log-list">
          <div v-if="loading && entries.length === 0" class="loading-state">
            <Loader :size="18" class="spinner" /> 加载日志...
          </div>

          <div v-else-if="entries.length === 0" class="empty-state">
            <FileText :size="32" class="empty-icon" />
            <p>{{ selectedChannel ? '此通道暂无日志' : '请选择左侧通道' }}</p>
          </div>

          <div
            v-for="(entry, i) in filteredEntries"
            :key="i"
            :class="['log-entry', `entry-${entry.level}`]"
          >
            <span class="log-time">{{ formatTime(entry.timestamp) }}</span>
            <span class="log-level-badge" :class="`badge-${entry.level}`">{{ entry.level.toUpperCase() }}</span>
            <span v-if="entry.source" class="log-source">{{ entry.source }}</span>
            <span class="log-message">{{ entry.message }}</span>
            <button
              v-if="entry.metadata"
              class="log-detail-btn"
              @click="selectedEntry = selectedEntry === entry ? null : entry"
              title="查看详情"
            >
              <Info :size="12" />
            </button>
          </div>
        </div>

        <!-- 搜索结果 -->
        <div v-if="searchResults !== null" class="search-results-panel">
          <div class="sr-header">
            <h3>搜索结果: "{{ searchQ }}" ({{ searchResults.total }} 条)</h3>
            <button class="btn-ghost" @click="searchResults = null; searchQ = ''">关闭</button>
          </div>
          <div class="log-list">
            <div
              v-for="(entry, i) in searchResults.results"
              :key="i"
              :class="['log-entry', `entry-${entry.level}`]"
            >
              <span class="log-time">{{ formatTime(entry.timestamp) }}</span>
              <span :class="`chip-chip chip-${entry.channel}`">{{ entry.channel }}</span>
              <span class="log-level-badge" :class="`badge-${entry.level}`">{{ entry.level.toUpperCase() }}</span>
              <span class="log-message" v-html="highlightMatch(entry.message, searchQ)" />
            </div>
          </div>
        </div>
      </main>
    </div>

    <!-- 日志详情弹窗 -->
    <div v-if="selectedEntry?.metadata" class="detail-panel">
      <div class="detail-header">
        <h4>日志详情</h4>
        <button class="btn-close" @click="selectedEntry = null">&times;</button>
      </div>
      <pre class="detail-body">{{ JSON.stringify(selectedEntry.metadata, null, 2) }}</pre>
    </div>

    <!-- Toast -->
    <div v-if="toast" class="toast" :class="toast.type">{{ toast.message }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from "vue"
import { Search, RefreshCw, Loader, Radio, Trash2, FileText, Info } from "lucide-vue-next"
import { logsApi, type LogChannelInfo, type LogEntry, type LogSearchResponse } from "@/api/logs"

// ── State ────────────────────────────────────────────

const channels = ref<LogChannelInfo[]>([])
const selectedChannel = ref<string | null>(null)
const entries = ref<LogEntry[]>([])
const loading = ref(false)
const activeLevel = ref<string | null>(null)
const searchQ = ref("")
const searchResults = ref<LogSearchResponse | null>(null)
const autoScroll = ref(true)
const selectedEntry = ref<LogEntry | null>(null)
const logContainer = ref<HTMLElement | null>(null)

const logLevels = ["trace", "debug", "info", "warn", "error", "fatal"]
const levelOrder: Record<string, number> = {
  trace: 0, debug: 1, info: 2, warn: 3, error: 4, fatal: 5,
}

// ── WebSocket ────────────────────────────────────────

const wsConnected = ref(false)
let ws: WebSocket | null = null
let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null

function connectWs(channel: string) {
  disconnectWs()
  try {
    ws = logsApi.streamLogs(channel)
    ws.onopen = () => { wsConnected.value = true }
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.type === "ping") return
        // 追加实时日志
        entries.value.push(data as LogEntry)
        // 保持最多 1000 条
        if (entries.value.length > 1000) entries.value.shift()
        if (autoScroll.value) scrollToBottom()
      } catch {}
    }
    ws.onclose = () => {
      wsConnected.value = false
      // 自动重连
      if (selectedChannel.value === channel) {
        wsReconnectTimer = setTimeout(() => connectWs(channel), 3000)
      }
    }
    ws.onerror = () => { wsConnected.value = false }
  } catch {}
}

function disconnectWs() {
  if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null }
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
  wsConnected.value = false
}

// ── Channel Selection ────────────────────────────────

async function selectChannel(ch: string) {
  searchResults.value = null
  searchQ.value = ""
  selectedChannel.value = ch
  entries.value = []
  await fetchLogs()
  connectWs(ch)
}

async function fetchChannels() {
  try {
    const res = await logsApi.listChannels()
    channels.value = res.data.channels
  } catch {}
}

async function fetchLogs() {
  if (!selectedChannel.value) return
  loading.value = true
  try {
    const params: any = { limit: 500 }
    if (activeLevel.value) params.level = activeLevel.value
    const res = await logsApi.getLogs(selectedChannel.value, params)
    entries.value = res.data.entries
    if (autoScroll.value) await nextTick(() => scrollToBottom())
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载日志失败", "error")
  } finally {
    loading.value = false
  }
}

function refreshLogs() {
  searchResults.value = null
  searchQ.value = ""
  fetchLogs()
}

async function handleClear() {
  if (!selectedChannel.value) return
  if (!confirm(`确定清空通道 "${selectedChannel.value}" 的所有日志？`)) return
  try {
    await logsApi.clearChannel(selectedChannel.value)
    entries.value = []
    showToast(`通道 "${selectedChannel.value}" 已清空`)
    fetchChannels()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "清空失败", "error")
  }
}

async function handleSearch() {
  if (!searchQ.value.trim()) {
    searchResults.value = null
    return
  }
  try {
    const params: any = { limit: 200 }
    if (selectedChannel.value) params.channel = selectedChannel.value
    if (activeLevel.value) params.level = activeLevel.value
    const res = await logsApi.searchLogs(searchQ.value.trim(), params)
    searchResults.value = res.data
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "搜索失败", "error")
  }
}

// ── Filtered Entries ─────────────────────────────────

const filteredEntries = computed(() => {
  if (!activeLevel.value) return entries.value
  const threshold = levelOrder[activeLevel.value] ?? 0
  return entries.value.filter(e => (levelOrder[e.level] ?? 0) >= threshold)
})

// ── Helpers ──────────────────────────────────────────

function formatTime(ts: string) {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString("zh-CN", { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0")
  } catch {
    return ts
  }
}

function highlightMatch(text: string, q: string) {
  if (!q) return text
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  return text.replace(new RegExp(`(${escaped})`, "gi"), '<mark class="hl">$1</mark>')
}

function scrollToBottom() {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight
  }
}

// ── Toast ────────────────────────────────────────────

const toast = ref<{ message: string; type: string } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null
function showToast(message: string, type = "success") {
  toast.value = { message, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 3000)
}

// ── Lifecycle ────────────────────────────────────────

watch(activeLevel, () => {
  if (!searchResults.value) fetchLogs()
})

onMounted(() => {
  fetchChannels()
})

onUnmounted(() => {
  disconnectWs()
})
</script>

<style scoped>
/* ── Layout ── */
.logs-page {
  display: flex; flex-direction: column;
  height: 100%; overflow: hidden;
  background: var(--color-ide-bg); color: var(--color-ide-fg);
}

.page-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px; border-bottom: 1px solid var(--color-ide-border);
  flex-shrink: 0;
}
.header-left { display: flex; flex-direction: column; gap: 2px; }
.page-title { margin: 0; font-size: 18px; font-weight: 600; }
.page-desc { font-size: 12px; color: var(--color-ide-fg-muted); }

.header-actions { display: flex; align-items: center; gap: 12px; }
.auto-scroll-label {
  display: flex; align-items: center; gap: 6px; font-size: 12px;
  color: var(--color-ide-fg-muted); cursor: pointer;
}
.btn-connected {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 4px 10px; border: 1px solid #22c55e; border-radius: 12px;
  background: transparent; color: #22c55e; font-size: 12px; cursor: default;
}

/* ── Two-column ── */
.logs-layout {
  display: flex; flex: 1; overflow: hidden;
}

/* ── Channel Sidebar ── */
.channel-sidebar {
  width: 180px; flex-shrink: 0;
  border-right: 1px solid var(--color-ide-border);
  background: var(--color-ide-bg-panel);
  display: flex; flex-direction: column; overflow: hidden;
}
.sidebar-header {
  padding: 12px 14px; font-size: 11px; font-weight: 600;
  text-transform: uppercase; color: var(--color-ide-fg-muted);
  border-bottom: 1px solid var(--color-ide-border);
}
.channel-list { flex: 1; overflow-y: auto; padding: 4px 0; }

.channel-item {
  display: flex; align-items: center; justify-content: space-between;
  width: 100%; padding: 8px 14px; border: none;
  background: transparent; color: var(--color-ide-fg);
  font-size: 13px; cursor: pointer; transition: background 0.1s;
}
.channel-item:hover { background: var(--color-ide-bg-hover); }
.channel-item.active { background: color-mix(in srgb, var(--color-ide-accent) 15%, transparent); }

.ch-name-row { display: flex; align-items: center; gap: 6px; }
.ch-dot { width: 8px; height: 8px; border-radius: 50%; }
.dot-system { background: #3b82f6; }
.dot-agent { background: #8b5cf6; }
.dot-git { background: #ef4444; }
.dot-debug { background: #f59e0b; }
.dot-tasks { background: #22c55e; }
.dot-extensions { background: #ec4899; }
.dot-api { background: #06b6d4; }
.dot-default { background: #6b7280; }

.ch-count {
  font-size: 11px; color: var(--color-ide-fg-muted);
  background: var(--color-ide-bg-hover); padding: 1px 6px; border-radius: 8px;
}
.sidebar-empty { padding: 16px 14px; font-size: 12px; color: var(--color-ide-fg-muted); }

/* ── Content ── */
.log-content {
  flex: 1; display: flex; flex-direction: column; overflow: hidden;
}

/* ── Toolbar ── */
.toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px; border-bottom: 1px solid var(--color-ide-border);
  flex-shrink: 0; gap: 12px;
}
.toolbar-left { display: flex; align-items: center; gap: 12px; flex: 1; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }

.level-filters { display: flex; gap: 2px; }

.level-btn {
  padding: 3px 8px; border: 1px solid transparent; border-radius: 4px;
  background: transparent; font-size: 10px; font-weight: 600; cursor: pointer;
  transition: all 0.12s; opacity: 0.45;
}
.level-btn:hover { opacity: 0.7; }
.level-btn.active { opacity: 1; }

.level-trace { color: #6b7280; border-color: #6b7280; }
.level-trace.active { background: #6b7280; color: #fff; }
.level-debug { color: #6366f1; border-color: #6366f1; }
.level-debug.active { background: #6366f1; color: #fff; }
.level-info { color: #3b82f6; border-color: #3b82f6; }
.level-info.active { background: #3b82f6; color: #fff; }
.level-warn { color: #f59e0b; border-color: #f59e0b; }
.level-warn.active { background: #f59e0b; color: #fff; }
.level-error { color: #ef4444; border-color: #ef4444; }
.level-error.active { background: #ef4444; color: #fff; }
.level-fatal { color: #dc2626; border-color: #dc2626; }
.level-fatal.active { background: #dc2626; color: #fff; }

.search-box { position: relative; flex: 1; max-width: 240px; }
.search-icon { position: absolute; left: 8px; top: 50%; transform: translateY(-50%); color: var(--color-ide-fg-muted); }
.search-input {
  width: 100%; padding: 6px 10px 6px 28px;
  border: 1px solid var(--color-ide-border); border-radius: 5px;
  background: var(--color-ide-bg-input); color: var(--color-ide-fg);
  font-size: 12px; outline: none; box-sizing: border-box;
}
.search-input:focus { border-color: var(--color-ide-accent); }

/* ── Buttons ── */
.btn-ghost {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 5px 10px; border: 1px solid var(--color-ide-border); border-radius: 5px;
  background: transparent; color: var(--color-ide-fg); font-size: 12px; cursor: pointer;
}
.btn-ghost:hover { background: var(--color-ide-bg-hover); }
.btn-ghost:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-danger:hover { color: #ef4444; border-color: #ef4444; }

/* ── Log List ── */
.log-list {
  flex: 1; overflow-y: auto; padding: 8px 0;
  font-family: "Cascadia Code", "Fira Code", "JetBrains Mono", monospace;
  font-size: 12px; line-height: 1.5;
}
.loading-state, .empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 8px; padding: 60px 0; color: var(--color-ide-fg-muted); font-family: sans-serif;
}
.spinner { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.empty-icon { opacity: 0.3; }

.log-entry {
  display: flex; align-items: flex-start; gap: 6px;
  padding: 3px 16px; white-space: nowrap; transition: background 0.1s;
}
.log-entry:hover { background: var(--color-ide-bg-hover); }

.log-time {
  color: var(--color-ide-fg-muted); font-size: 11px; min-width: 90px; flex-shrink: 0;
}
.log-level-badge {
  display: inline-block; min-width: 48px; padding: 0 4px;
  text-align: center; font-size: 10px; font-weight: 700; border-radius: 3px;
  flex-shrink: 0; line-height: 18px;
}
.badge-trace { background: #374151; color: #9ca3af; }
.badge-debug { background: #312e81; color: #a5b4fc; }
.badge-info { background: #1e3a5f; color: #93c5fd; }
.badge-warn { background: #422006; color: #fcd34d; }
.badge-error { background: #450a0a; color: #fca5a5; }
.badge-fatal { background: #450a0a; color: #ff4444; font-weight: 900; }

.log-source {
  color: var(--color-ide-fg-muted); font-size: 11px; min-width: 80px; flex-shrink: 0;
  overflow: hidden; text-overflow: ellipsis;
}
.log-message { flex: 1; overflow: hidden; text-overflow: ellipsis; }

.log-detail-btn {
  border: none; background: transparent; color: var(--color-ide-fg-muted);
  cursor: pointer; padding: 0 2px; flex-shrink: 0;
}
.log-detail-btn:hover { color: var(--color-ide-accent); }

/* highlight in search */
:deep(.hl) { background: #fbbf24; color: #000; border-radius: 2px; padding: 0 1px; }

/* ── Search Results ── */
.search-results-panel {
  border-top: 2px solid var(--color-ide-accent);
  max-height: 300px; overflow: hidden; display: flex; flex-direction: column;
}
.sr-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 16px; background: var(--color-ide-bg-panel);
}
.sr-header h3 { margin: 0; font-size: 13px; font-weight: 600; }

.chip-chip {
  display: inline-block; padding: 0 5px; border-radius: 3px;
  font-size: 10px; font-weight: 600; flex-shrink: 0; line-height: 18px;
}
.chip-system { background: #1e3a5f; color: #93c5fd; }
.chip-agent { background: #3b1f6e; color: #c4b5fd; }
.chip-default, .chip-git, .chip-debug, .chip-tasks, .chip-extensions, .chip-api { background: #374151; color: #9ca3af; }

/* ── Detail Panel ── */
.detail-panel {
  position: fixed; right: 0; top: 0; width: 360px; height: 100%;
  background: var(--color-ide-bg-panel); border-left: 1px solid var(--color-ide-border);
  display: flex; flex-direction: column; z-index: 50; box-shadow: -4px 0 12px rgba(0,0,0,0.3);
}
.detail-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid var(--color-ide-border);
}
.detail-header h4 { margin: 0; font-size: 14px; }
.btn-close {
  border: none; background: transparent; color: var(--color-ide-fg-muted);
  font-size: 18px; cursor: pointer;
}
.btn-close:hover { color: var(--color-ide-fg); }
.detail-body {
  flex: 1; padding: 14px; margin: 0; overflow: auto;
  font-size: 12px; font-family: monospace; white-space: pre-wrap; word-break: break-all;
}

/* ── Toast ── */
.toast {
  position: fixed; bottom: 24px; right: 24px;
  padding: 10px 20px; border-radius: 6px; font-size: 13px; z-index: 200;
  animation: slideUp 0.25s ease;
}
.toast.success { background: #16a34a; color: #fff; }
.toast.error { background: #dc2626; color: #fff; }
@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
