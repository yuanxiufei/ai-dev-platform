<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { agentChatStreamUrl } from '@/api/agent'
import type { ChatMessage, ToolCallRecord, SSEEventType } from '@/types/studio'
import { Send, Bot, User, Wrench, Loader2, Check, X, Zap } from 'lucide-vue-next'

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const currentToolCalls = ref<ToolCallRecord[]>([])
const currentTurn = ref(0)
const sessionId = ref(crypto.randomUUID())
const abortController = ref<AbortController | null>(null)
const preferredModel = ref('')

onMounted(() => {
  messages.value.push({
    id: crypto.randomUUID(),
    role: 'assistant',
    content: '你好！我是 AI Studio 管理端对话测试台。可以在这里调试 Agent、测试模型、验证工具调用。有什么可以帮你的？',
    timestamp: new Date().toISOString(),
  })
})

const scrollToBottom = async () => {
  await nextTick()
  const container = document.getElementById('chat-container')
  if (container) container.scrollTop = container.scrollHeight
}

const handleSend = async () => {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  const userMsg: ChatMessage = {
    id: crypto.randomUUID(),
    role: 'user',
    content: text,
    timestamp: new Date().toISOString(),
  }
  messages.value.push(userMsg)
  inputText.value = ''
  await scrollToBottom()

  const assistantMsg: ChatMessage = {
    id: crypto.randomUUID(),
    role: 'assistant',
    content: '',
    tool_calls: [],
    timestamp: new Date().toISOString(),
  }
  messages.value.push(assistantMsg)
  await scrollToBottom()

  isStreaming.value = true
  currentToolCalls.value = []

  const controller = new AbortController()
  abortController.value = controller

  try {
    const token = localStorage.getItem('token')
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (token) headers.Authorization = `Bearer ${token}`

    const res = await fetch(agentChatStreamUrl(), {
      method: 'POST',
      headers,
      body: JSON.stringify({
        message: text,
        agent_name: 'default',
        max_turns: 10,
        preferred_model: preferredModel.value || '',
        session_id: sessionId.value,
      }),
      signal: controller.signal,
    })

    if (!res.ok) {
      assistantMsg.content = `请求失败 (${res.status})`
      return
    }

    const reader = res.body?.getReader()
    if (!reader) {
      assistantMsg.content = '无法读取响应流'
      return
    }

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(line.slice(6))
            handleSSEEvent(assistantMsg, eventData)
            await scrollToBottom()
          } catch { /* ignore parse errors */ }
        }
      }
    }
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      assistantMsg.content += '\n\n[已停止生成]'
    } else {
      assistantMsg.content = `请求错误: ${err instanceof Error ? err.message : '未知错误'}`
    }
  } finally {
    isStreaming.value = false
    abortController.value = null
  }
}

const handleSSEEvent = (assistantMsg: ChatMessage, event: Record<string, unknown>) => {
  const type = event.type as SSEEventType

  switch (type) {
    case 'turn_start': {
      currentTurn.value = event.turn as number
      break
    }
    case 'tool_call': {
      const calls = event.tool_calls as { id: string; name: string; arguments: string }[]
      if (calls) {
        for (const tc of calls) {
          const record: ToolCallRecord = {
            id: tc.id,
            name: tc.name,
            arguments: typeof tc.arguments === 'string' ? JSON.parse(tc.arguments) : tc.arguments,
          }
          currentToolCalls.value.push(record)
          assistantMsg.tool_calls = assistantMsg.tool_calls || []
          assistantMsg.tool_calls.push(record)
        }
      }
      break
    }
    case 'tool_result': {
      const name = event.tool_name as string
      const success = event.success as boolean
      const result = event.result as string
      const existing = currentToolCalls.value.find((tc) => tc.name === name && !tc.result)
      if (existing) {
        existing.result = result
        existing.success = success
      }
      break
    }
    case 'final_answer': {
      assistantMsg.content = event.content as string
      if (event.model_used) {
        assistantMsg.metadata = { model_used: event.model_used, turns: event.turns }
      }
      break
    }
    case 'error': {
      assistantMsg.content = `错误: ${event.error || '未知错误'}`
      break
    }
  }
}

const handleStop = () => {
  abortController.value?.abort()
}

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

const modelOptions = [
  { value: '', label: '自动选择' },
  { value: 'openai-gpt4o', label: 'GPT-4o' },
  { value: 'claude-sonnet', label: 'Claude Sonnet 4' },
  { value: 'deepseek-v3', label: 'DeepSeek V3' },
  { value: 'zhipu-glm4', label: 'GLM-4 Plus' },
]
</script>

<template>
  <div class="flex flex-col h-full max-h-screen">
    <!-- 顶栏 -->
    <header class="shrink-0 h-14 border-b border-white/8 bg-surface-900/50 backdrop-blur flex items-center justify-between px-6">
      <div class="flex items-center gap-3">
        <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-400 to-purple-500 flex items-center justify-center">
          <Zap class="w-3.5 h-3.5 text-white" />
        </div>
        <h2 class="text-sm font-semibold text-gray-200">Agent 对话测试台</h2>
        <span
          v-if="isStreaming"
          class="flex items-center gap-1.5 text-xs text-brand-400"
        >
          <span class="w-1.5 h-1.5 rounded-full bg-brand-400 animate-pulse" />
          思考中...
        </span>
      </div>
      <div class="flex items-center gap-2">
        <select
          v-model="preferredModel"
          class="text-xs rounded-lg bg-white/5 border border-white/10 px-3 py-1.5 text-gray-300 focus:outline-none focus:border-brand-500/50 transition-colors"
        >
          <option v-for="m in modelOptions" :key="m.value" :value="m.value">{{ m.label }}</option>
        </select>
      </div>
    </header>

    <!-- 聊天区域 -->
    <div
      id="chat-container"
      class="flex-1 overflow-y-auto px-6 py-4 space-y-6"
    >
      <div
        v-for="msg in messages"
        :key="msg.id"
        :class="[
          'flex gap-4',
          msg.role === 'user' ? 'justify-end' : 'justify-start',
        ]"
      >
        <!-- 助手/系统头像 -->
        <div
          v-if="msg.role !== 'user'"
          :class="[
            'w-8 h-8 rounded-xl flex items-center justify-center shrink-0 mt-0.5',
            msg.role === 'assistant'
              ? 'bg-gradient-to-br from-brand-400 to-purple-500'
              : msg.role === 'tool'
                ? 'bg-amber-500/20'
                : 'bg-gray-700',
          ]"
        >
          <Bot v-if="msg.role === 'assistant'" class="w-4 h-4 text-white" />
          <Wrench v-else-if="msg.role === 'tool'" class="w-4 h-4 text-amber-400" />
        </div>

        <!-- 消息气泡 -->
        <div
          :class="[
            'max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed',
            msg.role === 'user'
              ? 'bg-gradient-to-r from-brand-500 to-brand-600 text-white rounded-br-md'
              : msg.role === 'system'
                ? 'bg-amber-500/10 text-amber-200/80 border border-amber-500/20'
                : msg.role === 'tool'
                  ? 'bg-white/5 text-gray-300 border border-white/10'
                  : 'bg-surface-800 text-gray-200 border border-white/5',
          ]"
        >
          <!-- 工具调用记录 -->
          <div
            v-if="msg.tool_calls && msg.tool_calls.length"
            class="mb-3 space-y-2"
          >
            <div
              v-for="tc in msg.tool_calls"
              :key="tc.id"
              class="rounded-xl bg-surface-900/80 border border-white/10 p-3"
            >
              <div class="flex items-center gap-2 mb-1">
                <Wrench class="w-3.5 h-3.5 text-brand-400" />
                <span class="text-xs font-medium text-brand-400">{{ tc.name }}</span>
                <span v-if="tc.success !== undefined" class="ml-auto">
                  <Check v-if="tc.success" class="w-3.5 h-3.5 text-green-400" />
                  <X v-else class="w-3.5 h-3.5 text-red-400" />
                </span>
                <Loader2 v-else class="w-3.5 h-3.5 text-brand-400 animate-spin ml-auto" />
              </div>
              <div
                v-if="tc.result"
                class="text-xs text-gray-400 font-mono whitespace-pre-wrap max-h-32 overflow-y-auto"
              >
                {{ tc.result }}
              </div>
            </div>
          </div>

          <!-- 文字内容 -->
          <div
            v-if="msg.content"
            class="whitespace-pre-wrap break-words"
          >
            {{ msg.content }}
          </div>

          <!-- 元信息 -->
          <div
            v-if="msg.metadata?.model_used"
            class="mt-2 text-xs text-gray-600"
          >
            模型: {{ msg.metadata.model_used }} · {{ msg.metadata.turns }} 轮
          </div>
        </div>

        <!-- 用户头像 -->
        <div
          v-if="msg.role === 'user'"
          class="w-8 h-8 rounded-xl bg-surface-700 flex items-center justify-center shrink-0 mt-0.5"
        >
          <User class="w-4 h-4 text-gray-300" />
        </div>
      </div>

      <!-- 流式加载指示器 -->
      <div
        v-if="isStreaming && currentTurn > 0"
        class="flex items-center gap-2 text-xs text-gray-500 pl-12"
      >
        <Loader2 class="w-3 h-3 animate-spin text-brand-400" />
        第 {{ currentTurn }} 轮
      </div>
    </div>

    <!-- 输入区 -->
    <div class="shrink-0 border-t border-white/8 bg-surface-900/50 backdrop-blur p-4">
      <div class="flex gap-3">
        <textarea
          v-model="inputText"
          :disabled="isStreaming"
          placeholder="输入消息，Enter 发送，Shift+Enter 换行..."
          rows="1"
          class="flex-1 resize-none rounded-xl bg-surface-800 border border-white/10 px-4 py-3 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500/50 transition-colors disabled:opacity-50"
          @keydown="handleKeydown"
          @input="(e) => { const t = e.target as HTMLTextAreaElement; t.style.height = 'auto'; t.style.height = Math.min(t.scrollHeight, 150) + 'px' }"
        />
        <button
          v-if="isStreaming"
          class="shrink-0 w-10 h-10 rounded-xl bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors flex items-center justify-center"
          @click="handleStop"
        >
          <X class="w-5 h-5" />
        </button>
        <button
          v-else
          :disabled="!inputText.trim()"
          class="shrink-0 w-10 h-10 rounded-xl bg-gradient-to-br from-brand-400 to-purple-500 text-white hover:shadow-lg hover:shadow-brand-500/25 transition-all flex items-center justify-center disabled:opacity-30 disabled:cursor-not-allowed"
          @click="handleSend"
        >
          <Send class="w-4 h-4" />
        </button>
      </div>
    </div>
  </div>
</template>
