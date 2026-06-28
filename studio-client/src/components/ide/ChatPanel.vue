<script setup lang="ts">
/**
 * CodeBuddy IDE — AI Chat Panel
 * Figma Design: studio-ai (node-id=9-195) — Right Panel "AI 编程助手"
 *
 * Features:
 *  - Glassmorphism message bubbles (AI: blur+left-border, User: light purple)
 *  - Model selector (GPT-4o / Claude / DeepSeek)
 *  - Mode selector (对话模式 / Agent模式)
 *  - Loading dots animation
 *  - Ctrl+Enter hint
 */

import { computed, nextTick, ref } from "vue"
import { agentChatSimple } from "@/api/agent"
import apiClient from "@/api/client"

interface Message {
  role: "user" | "assistant" | "system"
  content: string
  timestamp: number
  toolCalls?: Array<{ name: string; args?: any; result?: string }>
  modelUsed?: string
  provider?: string
}

/** Available AI models for selector */
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

const hasMessages = computed(() => messages.value.length > 0)

function sb(): void {
  nextTick(() => {
    if (mc.value) mc.value.scrollTop = mc.value.scrollHeight
  })
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

async function sendMessage(): Promise<void> {
  const text = inputText.value.trim()
  if (!text || isLoading.value) return

  // Add user message
  messages.value.push({ role: "user", content: text, timestamp: Date.now() })
  inputText.value = ""
  isLoading.value = true
  sb()

  // Add assistant placeholder
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
      tools: ["calculate", "datetime_now", "get_weather", "web_search", "file_read"],
      preferred_model: selectedModel.value.id,
      max_turns: 3,
      max_turns: 2,
    })
    am.content = resp.data.answer || resp.data.content
    am.modelUsed = resp.data.model_used
    am.provider = resp.data.provider
  } catch (e: any) {
    const msg =
      e?.response?.data?.detail ||
      e?.message ||
      "请求失败，请检查后端是否启动。"
    am.content = `❌ ${msg}`
  } finally {
    isLoading.value = false
    sb()
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--color-ide-surface)]">
    <!-- ── Header ───────────────────────────────────── -->
    <div class="flex items-center justify-between px-4 py-4 border-b border-[var(--color-ide-border)] shrink-0">
      <div class="flex items-center gap-2.5">
        <!-- Bot Icon -->
        <div class="w-7 h-7 rounded flex items-center justify-center" style="background:#C0C1FF20;">
          <Bot :size="16" style="color:#C0C1FF;" />
        </div>
        <span class="text-sm font-semibold" style="color:#DFE2F1;">AI 编程助手</span>
      </div>
      <div class="flex items-center gap-1">
        <button class="p-1 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)] transition-colors">
          <svg width="14" height="12" viewBox="0 0 24 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
        <button class="p-1 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)] transition-colors">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
        </button>
      </div>
    </div>

    <!-- ── Messages Area ──────────────────────────────── -->
    <div ref="mc" class="flex-1 overflow-y-auto p-4 space-y-4">
      <!-- No messages → Welcome -->
      <div v-if="!hasMessages && !isLoading" class="h-full flex flex-col items-center justify-center text-center select-none">
        <div class="mb-4 w-16 h-16 rounded-xl flex items-center justify-center" style="background: linear-gradient(135deg, #C0C1FF15, #C0C1FF05); border: 1px solid #C0C1FF25;">
          <Sparkles :size="28" style="color:#C0C1FF;" />
        </div>
        <p class="text-sm font-medium mb-1" style="color:#DFE2F1;">AI 编程助手</p>
        <p class="text-xs mb-5" style="color:#908FA0;">有什么可以帮你的？</p>
        <div class="w-full space-y-2 max-w-xs">
          <button @click="inputText='帮我分析当前组件的性能'; sendMessage()"
            class="w-full text-left text-xs px-3 py-2 rounded-lg border transition-colors"
            style="border-color: var(--color-ide-border); color: var(--color-ide-text);"
            :class="'hover:border-[#C0C1FF40]'">
            分析代码性能
          </button>
          <button @click="inputText='生成一个 Vue 组件'; sendMessage()"
            class="w-full text-left text-xs px-3 py-2 rounded-lg border transition-colors"
            style="border-color: var(--color-ide-border); color: var(--color-ide-text);"
            :class="'hover:border-[#C0C1FF40]'">
            生成 Vue 组件
          </button>
        </div>
      </div>

      <!-- Messages List -->
      <template v-else>
        <!-- AI Message (Glassmorphism bubble) -->
        <div v-for="(msg, idx) in messages" :key="idx" class="flex gap-2 items-start">
          <!-- AI message -->
          <template v-if="msg.role === 'assistant'">
            <div
              class="max-w-[90%] rounded-lg px-3.5 py-3 relative backdrop-blur-md"
              style="background: rgba(28,31,42,0.7); border-left: 4px solid #C0C1FF; box-shadow: 0 4px 6px -4px rgba(0,0,0,0.1), 0 10px 15px -3px rgba(0,0,0,0.1);"
            >
              <!-- Loading state -->
              <div v-if="isLoading && !msg.content" class="flex items-center gap-1.5 py-1" style="color:#908FA0;">
                <span class="flex gap-1">
                  <span class="w-1.5 h-1.5 rounded-full animate-bounce" style="background:#C0C1FF;animation-delay:0ms;"/>
                  <span class="w-1.5 h-1.5 rounded-full animate-bounce" style="background:#C0C1FF;animation-delay:150ms;"/>
                  <span class="w-1.5 h-1.5 rounded-full animate-bounce" style="background:#C0C1FF;animation-delay:300ms;"/>
                </span>
                <span class="text-xs">正在分析代码...</span>
              </div>
              <!-- Content -->
              <div v-else class="text-xs leading-relaxed whitespace-pre-wrap break-words" style="color:#DFE2F1;">{{ msg.content }}</div>
            </div>
            <!-- Timestamp -->
            <span class="text-[10px] mt-auto ml-2 whitespace-nowrap" style="color:#908FA0;">
              {{ formatTime(msg.timestamp) }} · AI 助手
            </span>
          </template>

          <!-- User message (Light purple bubble) -->
          <template v-else-if="msg.role === 'user'">
            <div class="flex-1" />
            <div
              class="rounded-lg px-4 py-2.5 max-w-[85%]"
              style="background: rgba(192,193,255,0.1); border: 1px solid rgba(192,193,255,0.2);"
            >
              <p class="text-xs leading-relaxed whitespace-pre-wrap break-words" style="color:#DFE2F1;">{{ msg.content }}</p>
            </div>
            <!-- Timestamp -->
            <span class="text-[10px] mt-auto ml-2 whitespace-nowrap" style="color:#908FA0;">
              {{ formatTime(msg.timestamp) }} · 您
            </span>
          </template>
        </div>
      </template>
    </div>

    <!-- ── Bottom Input Panel ────────────────────────── -->
    <div class="shrink-0 border-t border-[var(--color-ide-border)] px-4 py-3 space-y-3" style="background:#262A35;">
      <!-- Model & Mode Selectors Row -->
      <div class="flex items-center justify-center gap-2">
        <!-- Model Selector -->
        <div class="relative">
          <button
            @click="showModelMenu = !showModelMenu"
            class="flex items-center gap-1.5 h-6 pl-2.5 pr-2 rounded text-[11px] font-semibold transition-colors border"
            style="background: var(--color-editor-bg); border-color: var(--color-ide-border); color: var(--color-ide-text);"
            @blur="setTimeout(()=>showModelMenu=false,250)"
          >
            <span>{{ selectedModel.label }} {{ selectedModel.desc }}</span>
            <ChevronDown :size="10" />
          </button>
          <!-- Dropdown -->
          <div v-if="showModelMenu" class="absolute bottom-full mb-1 left-0 min-w-[140px] rounded-lg shadow-xl overflow-hidden z-50" style="background:#262A35;border:1px solid #464554;">
            <button v-for="m in models" :key="m.id"
              @mousedown.prevent
              @click="selectedModel=m;showModelMenu=false"
              class="w-full text-left text-[11px] font-semibold px-3 py-1.5 transition-colors flex items-center justify-between gap-2"
              :style="{ color: m.active ? '#DFE2F1' : '#908FA0', background: m.id === selectedModel.id ? '#C0C1FF15' : 'transparent' }"
            >
              <span>{{ m.label }} {{ m.desc }}</span>
              <svg v-if="m.id===selectedModel.id" width="12" height="9" viewBox="0 0 12 9" fill="none" style="stroke:#C0C1FF;"><path d="M1 3l4 4 6-6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>

        <!-- Mode Selector -->
        <div class="relative">
          <button
            @click="showModeMenu = !showModeMenu"
            class="flex items-center gap-1.5 h-6 pl-2.5 pr-2 rounded text-[11px] font-medium transition-colors border"
            style="background: var(--color-editor-bg); border-color: var(--color-ide-border); color: var(--color-ide-text);"
            @blur="setTimeout(()=>showModeMenu=false,250)"
          >
            <span>{{ selectedMode.label }}</span>
            <ChevronDown :size="10" />
          </button>
          <div v-if="showModeMenu" class="absolute bottom-full mb-1 left-0 min-w-[110px] rounded-lg shadow-xl overflow-hidden z-50" style="background:#262A35;border:1px solid #464554;">
            <button v-for="m in modes" :key="m.id"
              @mousedown.prevent
              @click="selectedMode=m;showModeMenu=false"
              class="w-full text-left text-[11px] font-medium px-3 py-1.5 transition-colors flex items-center justify-between gap-2"
              :style="{ color: m.active ? '#DFE2F1' : '#908FA0', background: m.id === selectedMode.id ? '#C0C1FF15' : 'transparent' }"
            >
              <span>{{ m.label }}</span>
              <svg v-if="m.id===selectedMode.id" width="12" height="9" viewBox="0 0 12 9" fill="none" style="stroke:#C0C1FF;"><path d="M1 3l4 4 6-6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Input Box -->
      <div class="relative">
        <textarea
          v-model="inputText"
          rows="3"
          placeholder="在此输入指令或提问，按下回车发送..."
          class="w-full resize-none outline-none text-[13px] rounded-lg border px-3 pt-2.5 pb-8 leading-relaxed"
          style="background: var(--color-editor-bg); border-color: var(--color-ide-border); color: var(--color-ide-text);"
          @keydown.enter.exact.prevent="sendMessage"
        />

        <!-- Bottom toolbar inside textarea area -->
        <div class="absolute bottom-2 left-3 flex items-center gap-1.5">
          <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="附件">
            <Paperclip :size="15" />
          </button>
          <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="图片">
            <ImagePlus :size="15" />
          </button>
        </div>

        <!-- Send Button (absolute positioned bottom-right) -->
        <button
          class="absolute bottom-2 right-2 flex items-center gap-1 px-2.5 py-1.5 rounded text-[11px] font-bold transition-all"
          style="background:#C0C1FF; color:#1000A9;"
          :class="{ 'opacity-40 cursor-not-allowed': !inputText.trim() || isLoading }"
          :disabled="!inputText.trim() || isLoading"
          @click="sendMessage"
        >
          发送
          <Send :size="11" />
        </button>
      </div>

      <!-- Keyboard Hint -->
      <div class="flex items-center justify-center gap-1 text-[10px]" style="color:#908FA0;">
        按
        <kbd class="inline-flex items-center justify-center rounded px-1.5" style="background:var(--color-ide-surface);border:1px solid var(--color-ide-border);font-family:'Liberation Mono',monospace;height:13px;font-size:9px;line-height:13px;">Ctrl</kbd>
        +
        <kbd class="inline-flex items-center justify-center rounded px-1.5" style="background:var(--color-ide-surface);border:1px solid var(--color-ide-border);font-family:'Liberation Mono',monospace;height:13px;font-size:9px;line-height:13px;">Enter</kbd>
        换行
      </div>
    </div>
  </div>
</template>

<style scoped>
textarea::placeholder {
  color: rgba(144, 143, 160, 0.5);
}
</style>
