<template>
  <div class="chat-page">
    <!-- 左侧：聊天区 -->
    <div class="chat-main">
      <div class="chat-header">
        <div class="header-left">
          <MessageSquare class="h-5 w-5" />
          <h2>AI 对话</h2>
          <span class="badge" :class="mode">{{ mode === 'stream' ? 'SSE 流式' : mode === 'simple' ? '简化' : '标准' }}</span>
        </div>
        <div class="header-actions">
          <button class="btn btn-ghost btn-sm" @click="clearChat" :disabled="messages.length === 0">
            <Trash2 class="h-4 w-4" /> 清空
          </button>
          <select v-model="mode" class="input-sm">
            <option value="normal">标准模式</option>
            <option value="stream">流式模式</option>
            <option value="simple">简化模式</option>
          </select>
        </div>
      </div>

      <div class="chat-messages" ref="msgContainer">
        <div v-if="messages.length === 0" class="empty-state">
          <Bot class="h-12 w-12" />
          <p>发送消息开始与 AI 对话</p>
        </div>
        <div v-for="(msg, i) in messages" :key="i" :class="['msg', msg.role]">
          <div class="msg-avatar">
            <User v-if="msg.role === 'user'" class="h-4 w-4" />
            <Bot v-else class="h-4 w-4" />
          </div>
          <div class="msg-body">
            <div class="msg-content">{{ msg.content }}</div>
            <div v-if="msg.usage" class="msg-meta">
              {{ msg.usage.total_tokens }} tokens
            </div>
          </div>
        </div>
        <div v-if="loading" class="msg assistant">
          <div class="msg-avatar"><Bot class="h-4 w-4" /></div>
          <div class="msg-body"><span class="typing">思考中...</span></div>
        </div>
      </div>

      <div class="chat-input">
        <textarea
          v-model="input"
          @keydown.enter.exact.prevent="sendMessage"
          placeholder="输入消息... (Enter 发送)"
          rows="3"
          class="input-area"
        ></textarea>
        <button class="btn btn-primary" @click="sendMessage" :disabled="!input.trim() || loading">
          <Send class="h-4 w-4" /> 发送
        </button>
      </div>
    </div>

    <!-- 右侧：设置面板 -->
    <div class="chat-sidebar">
      <h3><Sliders class="h-4 w-4" /> 对话设置</h3>

      <label>系统提示词</label>
      <textarea v-model="systemPrompt" rows="4" placeholder="自定义系统提示..." class="input-field"></textarea>

      <label>模型</label>
      <input v-model="model" placeholder="gpt-4 / claude-3..." class="input-field" />

      <label>Temperature: {{ temperature }}</label>
      <input type="range" v-model.number="temperature" min="0" max="2" step="0.1" />

      <label>最大 Token 数</label>
      <input v-model.number="maxTokens" type="number" min="1" max="32768" class="input-field" />

      <label>工具 (逗号分隔)</label>
      <input v-model="toolsInput" placeholder="read_file, write_file..." class="input-field" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from "vue"
import {
  MessageSquare, Bot, User, Send, Trash2, Sliders,
} from "lucide-vue-next"
import { agentChat, agentChatSimple, agentChatStream } from "@/api/chat"

interface Msg {
  role: "user" | "assistant"
  content: string
  usage?: { total_tokens: number }
}

const mode = ref<"normal" | "stream" | "simple">("normal")
const input = ref("")
const loading = ref(false)
const messages = ref<Msg[]>([])
const msgContainer = ref<HTMLElement | null>(null)

const systemPrompt = ref("")
const model = ref("")
const temperature = ref(0.7)
const maxTokens = ref(4096)
const toolsInput = ref("")

function scrollBottom() {
  nextTick(() => {
    const el = msgContainer.value
    if (el) el.scrollTop = el.scrollHeight
  })
}

async function sendMessage() {
  const text = input.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: "user", content: text })
  input.value = ""
  scrollBottom()
  loading.value = true

  try {
    const payload = {
      message: text,
      system_prompt: systemPrompt.value || undefined,
      model: model.value || undefined,
      temperature: temperature.value,
      max_tokens: maxTokens.value,
      tools: toolsInput.value ? toolsInput.value.split(",").map(t => t.trim()) : undefined,
    }

    if (mode.value === "stream") {
      const resp = await agentChatStream(payload)
      const reader = (resp.data as ReadableStream).getReader()
      const decoder = new TextDecoder()
      let buffer = ""
      messages.value.push({ role: "assistant", content: "" })
      const aiMsg = messages.value[messages.value.length - 1]
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() || ""
        for (const line of lines) {
          if (line.startsWith("data: ")) {
            try {
              const json = JSON.parse(line.slice(6))
              aiMsg.content += json.content || json.delta || ""
            } catch { /* skip */ }
          }
        }
      }
    } else if (mode.value === "simple") {
      const resp = await agentChatSimple(payload)
      messages.value.push({ role: "assistant", content: JSON.stringify(resp.data, null, 2) })
    } else {
      const resp = await agentChat(payload)
      const d = resp.data
      messages.value.push({
        role: "assistant",
        content: d.message,
        usage: d.usage,
      })
    }
  } catch (e: unknown) {
    const errMsg = e instanceof Error ? e.message : "请求失败"
    messages.value.push({ role: "assistant", content: `❌ ${errMsg}` })
  } finally {
    loading.value = false
    scrollBottom()
  }
}

function clearChat() { messages.value = [] }
watch(messages, scrollBottom, { deep: true })
</script>

<style scoped>
.chat-page { display: flex; height: calc(100vh - 120px); gap: 16px; padding: 16px; }
.chat-main { flex: 1; display: flex; flex-direction: column; background: var(--color-ide-bg); border: 1px solid var(--color-ide-border); border-radius: 12px; overflow: hidden; }
.chat-sidebar { width: 280px; flex-shrink: 0; padding: 16px; background: var(--color-ide-bg); border: 1px solid var(--color-ide-border); border-radius: 12px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
.chat-sidebar h3 { display: flex; align-items: center; gap: 6px; font-size: 14px; margin: 0 0 4px; }

.chat-header { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--color-ide-border); }
.header-left { display: flex; align-items: center; gap: 8px; }
.header-left h2 { font-size: 16px; margin: 0; }
.header-actions { display: flex; gap: 8px; align-items: center; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 99px; }
.badge.normal { background: var(--color-ide-accent); color: #fff; }
.badge.stream { background: #8b5cf6; color: #fff; }
.badge.simple { background: #6b7280; color: #fff; }

.chat-messages { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
.empty-state { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--color-ide-text-secondary); gap: 12px; }

.msg { display: flex; gap: 10px; max-width: 85%; }
.msg.user { align-self: flex-end; flex-direction: row-reverse; }
.msg-avatar { width: 32px; height: 32px; border-radius: 8px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.msg.user .msg-avatar { background: var(--color-ide-accent); color: #fff; }
.msg.assistant .msg-avatar { background: var(--color-ide-border); color: var(--color-ide-text); }

.msg-body { display: flex; flex-direction: column; gap: 4px; }
.msg-content { padding: 10px 14px; border-radius: 12px; font-size: 14px; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.msg.user .msg-content { background: var(--color-ide-accent); color: #fff; border-bottom-right-radius: 4px; }
.msg.assistant .msg-content { background: var(--color-ide-surface); color: var(--color-ide-text); border-bottom-left-radius: 4px; }
.msg-meta { font-size: 11px; color: var(--color-ide-text-secondary); padding-left: 4px; }
.typing { color: var(--color-ide-text-secondary); animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { opacity: 1 } 50% { opacity: .3 } }

.chat-input { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--color-ide-border); align-items: flex-end; }
.input-area { flex: 1; resize: none; border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 8px 12px; font-size: 14px; background: var(--color-ide-surface); color: var(--color-ide-text); outline: none; min-height: 60px; }
.input-area:focus { border-color: var(--color-ide-accent); }

label { font-size: 12px; color: var(--color-ide-text-secondary); }
.input-field { width: 100%; box-sizing: border-box; border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 6px 10px; font-size: 13px; background: var(--color-ide-surface); color: var(--color-ide-text); outline: none; }
.input-field:focus { border-color: var(--color-ide-accent); }
textarea.input-field { resize: vertical; }
.input-sm { font-size: 12px; padding: 4px 8px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-surface); color: var(--color-ide-text); }

.btn { display: inline-flex; align-items: center; gap: 4px; border: none; cursor: pointer; border-radius: 8px; font-size: 13px; padding: 8px 14px; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-ghost { background: transparent; color: var(--color-ide-text-secondary); }
.btn-ghost:hover { background: var(--color-ide-surface); }
.btn-ghost:disabled { opacity: .3; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
</style>
