<template>
  <div class="terminal-page">
    <div class="page-header">
      <h2>Web 终端</h2>
      <p class="subtitle">浏览器内交互式终端 — WebSocket 连接后端 Shell</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="openNewSessionDialog" :disabled="!!activeSession">
        + 新会话
      </button>
      <button class="btn btn-sm" @click="refreshSessions" :disabled="refreshing">刷新会话列表</button>
    </div>

    <!-- 新会话弹窗 -->
    <div v-if="showNewDialog" class="modal-mask" @click.self="showNewDialog = false">
      <div class="modal-card">
        <h4>新建终端会话</h4>
        <form @submit.prevent="createSession">
          <div class="form-group">
            <label>Shell</label>
            <input v-model="newShell" class="input" placeholder="/bin/bash" />
          </div>
          <div class="form-group">
            <label>工作目录 (可选)</label>
            <input v-model="newCwd" class="input" placeholder="留空使用默认" />
          </div>
          <div class="modal-actions">
            <button type="submit" class="btn btn-primary" :disabled="creating">创建</button>
            <button type="button" class="btn btn-outline" @click="showNewDialog = false">取消</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 会话列表 + 终端区域 -->
    <div class="layout">
      <!-- 侧边会话列表 -->
      <div class="session-panel" v-if="sessions.length">
        <h4>活跃会话</h4>
        <div v-for="s in sessions" :key="s.session_id || s.terminal_id"
             :class="['session-item', { active: activeSessionId === s.session_id }]"
             @click="switchSession(s)">
          <div class="session-info">
            <span class="session-id">{{ s.terminal_id || (s.session_id || '').slice(0, 8) }}</span>
            <span class="session-shell">{{ s.shell }}</span>
          </div>
          <button class="btn btn-sm btn-danger session-close" @click.stop="closeSession(s)" title="关闭">×</button>
        </div>
      </div>

      <!-- 终端主体 -->
      <div class="terminal-main" v-if="activeSessionId">
        <div class="terminal-header">
          <span class="term-title">会话 {{ activeSessionId.slice(0, 8) }}</span>
          <span :class="['term-status', wsConnected ? 'connected' : 'disconnected']">
            {{ wsConnected ? '已连接' : '断开' }}
          </span>
          <button class="btn btn-sm" @click="reconnectWs" v-if="!wsConnected">重连</button>
          <button class="btn btn-sm" @click="disconnectWs" v-if="wsConnected">断开</button>
        </div>
        <div class="terminal-viewport" ref="viewportRef" @click="focusInput">
          <div class="terminal-output">
            <div v-for="(line, i) in outputLines" :key="i" class="output-line">
              {{ line }}
            </div>
            <div class="input-line">
              <span class="prompt">$ </span>
              <input ref="inputRef" v-model="cmdInput"
                     class="cmd-input" @keyup.enter="sendCommand"
                     :disabled="!wsConnected" />
            </div>
          </div>
        </div>
      </div>

      <!-- 无会话占位 -->
      <div class="terminal-main" v-else>
        <div class="empty-terminal">点击"+ 新会话"创建终端连接</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onUnmounted, nextTick } from 'vue'
import { terminalApi } from '@/api/terminal'
import type { TerminalInfo, TerminalSession } from '@/api/terminal'

const sessions = ref<(TerminalSession | TerminalInfo)[]>([])
const activeSessionId = ref<string | null>(null)
const activeSession = ref<TerminalSession | null>(null)
const wsConnected = ref(false)
const refreshing = ref(false)
const creating = ref(false)

const showNewDialog = ref(false)
const newShell = ref('/bin/bash')
const newCwd = ref('')

const cmdInput = ref('')
const outputLines = ref<string[]>(['终端已就绪'])
const viewportRef = ref<HTMLDivElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)

let currentWs: WebSocket | null = null

async function refreshSessions() {
  refreshing.value = true
  try {
    const res = await terminalApi.listSessions()
    sessions.value = res.data?.sessions ?? res.data ?? []
  } finally {
    refreshing.value = false
  }
}

function openNewSessionDialog() {
  showNewDialog.value = true
  newShell.value = '/bin/bash'
  newCwd.value = ''
}

async function createSession() {
  creating.value = true
  try {
    const res = await terminalApi.createSession(newShell.value, newCwd.value || undefined)
    const sess = res.data
    sessions.value.push(sess)
    showNewDialog.value = false
    switchSession(sess)
    refreshSessions()
  } finally {
    creating.value = false
  }
}

function switchSession(sess: TerminalSession | TerminalInfo) {
  // 先断开旧连接
  if (currentWs) { currentWs.close(); currentWs = null }

  activeSessionId.value = sess.session_id || (sess as TerminalInfo).session_id
  activeSession.value = sess as TerminalSession
  outputLines.value = [`会话 ${activeSessionId.value?.slice(0, 8)} — 正在连接...`]
  connectWebSocket(activeSessionId.value!)
}

function connectWebSocket(sessionId: string) {
  try {
    const ws = terminalApi.connectWs(sessionId)
    currentWs = ws

    ws.onopen = () => {
      wsConnected.value = true
      outputLines.value.push('连接已建立')
    }

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.output || data.data) {
        outputLines.value.push(data.output || data.data)
        scrollToBottom()
      }
    }

    ws.onclose = () => {
      wsConnected.value = false
      outputLines.value.push('[连接已关闭]')
      currentWs = null
    }

    ws.onerror = () => {
      outputLines.value.push('[连接错误]')
    }
  } catch (err: any) {
    outputLines.value.push(`[连接失败: ${err.message}]`)
  }
}

function reconnectWs() {
  if (activeSessionId.value) {
    outputLines.value.push('重新连接...')
    connectWebSocket(activeSessionId.value)
  }
}

function disconnectWs() {
  if (currentWs) {
    currentWs.close()
    currentWs = null
    wsConnected.value = false
  }
}

function sendCommand() {
  if (!currentWs || !cmdInput.value.trim()) return
  outputLines.value.push('$ ' + cmdInput.value)
  currentWs.send(JSON.stringify({ command: cmdInput.value }))
  cmdInput.value = ''
  scrollToBottom()
}

function scrollToBottom() {
  nextTick(() => {
    if (viewportRef.value) {
      viewportRef.value.scrollTop = viewportRef.value.scrollHeight
    }
  })
}

function focusInput() {
  inputRef.value?.focus()
}

async function closeSession(sess: TerminalSession | TerminalInfo) {
  const sid = sess.session_id || (sess as TerminalInfo).session_id
  if (!confirm(`关闭会话 "${sid?.slice(0, 8)}"？`)) return
  try {
    await terminalApi.closeSession(sid)
    sessions.value = sessions.value.filter(s => (s.session_id || (s as TerminalInfo).session_id) !== sid)
    if (activeSessionId.value === sid) {
      disconnectWs()
      activeSessionId.value = null
      activeSession.value = null
    }
  } catch { /* empty */ }
}

onUnmounted(() => {
  if (currentWs) { currentWs.close(); currentWs = null }
})
</script>

<style scoped>
.terminal-page { padding: 24px; display: flex; flex-direction: column; height: calc(100vh - 60px); }
.page-header { margin-bottom: 16px; flex-shrink: 0; }
.page-header h2 { margin: 0; font-size: 20px; }
.subtitle { color: var(--color-ide-fg-secondary); margin: 4px 0 0; font-size: 13px; }

.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-shrink: 0; }

.layout { display: flex; gap: 12px; flex: 1; min-height: 0; }

.session-panel { width: 180px; border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 12px; overflow-y: auto; flex-shrink: 0; }
.session-panel h4 { margin: 0 0 10px; font-size: 13px; color: var(--color-ide-fg-secondary); }
.session-item { display: flex; justify-content: space-between; align-items: center; padding: 8px 10px; border: 1px solid var(--color-ide-border); border-radius: 6px; margin-bottom: 6px; cursor: pointer; font-size: 12px; }
.session-item:hover { background: var(--color-ide-bg-secondary); }
.session-item.active { border-color: var(--color-ide-accent, #4fc1ff); }
.session-info { display: flex; flex-direction: column; gap: 2px; }
.session-id { font-family: monospace; font-weight: 500; }
.session-shell { font-size: 10px; color: var(--color-ide-fg-secondary); }
.session-close { flex-shrink: 0; }

.terminal-main { flex: 1; border: 1px solid var(--color-ide-border); border-radius: 8px; display: flex; flex-direction: column; min-height: 0; }
.terminal-header { display: flex; align-items: center; gap: 10px; padding: 8px 14px; background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border); flex-shrink: 0; }
.term-title { font-weight: 500; font-size: 13px; }
.term-status { font-size: 11px; padding: 2px 8px; border-radius: 8px; }
.term-status.connected { background: #1a7f3711; color: #1a7f37; }
.term-status.disconnected { background: #cf222e11; color: #cf222e; }

.terminal-viewport { flex: 1; overflow-y: auto; padding: 12px; cursor: text; font-family: monospace; font-size: 13px; line-height: 1.5; background: #0d1117; }
.terminal-output { min-height: 100%; }
.output-line { white-space: pre-wrap; word-break: break-all; margin-bottom: 2px; }
.input-line { display: flex; align-items: center; margin-top: 4px; }
.prompt { color: #1a7f37; margin-right: 6px; flex-shrink: 0; }
.cmd-input { flex: 1; background: transparent; border: none; outline: none; color: inherit; font-family: inherit; font-size: inherit; }

.empty-terminal { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--color-ide-fg-secondary); font-size: 14px; }

.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { background: var(--color-ide-bg); border: 1px solid var(--color-ide-border); border-radius: 12px; padding: 24px; min-width: 360px; }
.modal-card h4 { margin: 0 0 16px; }
.form-group { margin-bottom: 12px; }
.form-group label { display: block; margin-bottom: 4px; font-size: 12px; color: var(--color-ide-fg-secondary); }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }

.input { width: 100%; background: var(--color-ide-bg-secondary); border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 6px 10px; font-size: 13px; color: var(--color-ide-fg); box-sizing: border-box; }
.btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--color-ide-border); background: var(--color-ide-bg); color: var(--color-ide-fg); }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent, #4fc1ff); color: #fff; border-color: var(--color-ide-accent, #4fc1ff); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-outline { background: transparent; }
.btn-danger { color: #cf222e; border-color: #cf222e; background: transparent; }
</style>
