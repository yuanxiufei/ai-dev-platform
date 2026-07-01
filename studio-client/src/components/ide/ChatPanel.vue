<script setup lang="ts">
/**
 * CodeBuddy IDE — AI Chat Panel (Redesigned)
 * Unified theme tokens · Clean component primitives
 */

import { computed, nextTick, ref } from "vue"
import { Bot, ChevronDown, ImagePlus, Paperclip, Send, Sparkles } from "lucide-vue-next"
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

  messages.value.push({ role: "user", content: text, timestamp: Date.now() })
  inputText.value = ""
  isLoading.value = true
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
      tools: ["calculate", "datetime_now", "get_weather", "web_search", "file_read"],
      preferred_model: selectedModel.value.id,
      max_turns: 10,
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
    <header class="flex items-center justify-between px-5 py-3 border-b border-[var(--color-ide-border)] shrink-0">
      <div class="flex items-center gap-2.5">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center bg-[rgba(192,193,255,0.1)]">
          <Bot :size="17" class="text-[var(--color-ide-accent)]" />
        </div>
        <div>
          <span class="text-sm font-semibold text-[var(--color-ide-text)]">AI 编程助手</span>
        </div>
      </div>
      <div class="flex items-center gap-0.5">
        <button class="btn-ghost p-1.5" title="最小化">
          <svg width="14" height="12" viewBox="0 0 24 20" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>
        <button class="btn-ghost p-1.5" title="最大化">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg>
        </button>
      </div>
    </header>

    <!-- ── Messages Area ──────────────────────────────── -->
    <div ref="mc" class="flex-1 overflow-y-auto px-5 py-4 space-y-4">
      <!-- Welcome State -->
      <div v-if="!hasMessages && !isLoading" class="h-full flex flex-col items-center justify-center select-none">
        <div class="mb-5 w-20 h-20 rounded-2xl flex items-center justify-center bg-gradient-to-br from-[rgba(192,193,255,0.08)] to-transparent border border-solid border-[rgba(192,193,255,0.15)] shadow-[0_0_40px_rgba(192,193,255,0.06)]">
          <Sparkles :size="32" class="text-[var(--color-ide-accent)]" />
        </div>
        <p class="text-base font-semibold mb-1 text-[var(--color-ide-text-bright)]">AI 编程助手</p>
        <p class="text-xs mb-6 text-[var(--color-ide-text-dim)]">有什么可以帮你的？</p>

        <div class="w-full space-y-2 max-w-[280px]">
          <button @click="inputText='帮我分析当前组件的性能'; sendMessage()"
            class="quick-action-btn w-full text-left text-[13px] px-4 py-2.5 rounded-xl border border-solid transition-colors duration-150 border-[var(--color-ide-border)] text-[var(--color-ide-text)] hover:border-[var(--color-ide-accent)]/30 hover:bg-[rgba(192,193,255,0.04)]">
            分析代码性能
          </button>
          <button @click="inputText='生成一个 Vue 组件'; sendMessage()"
            class="quick-action-btn w-full text-left text-[13px] px-4 py-2.5 rounded-xl border border-solid transition-colors duration-150 border-[var(--color-ide-border)] text-[var(--color-ide-text)] hover:border-[var(--color-ide-accent)]/30 hover:bg-[rgba(192,193,255,0.04)]">
            生成 Vue 组件
          </button>
          <button @click="inputText='解释这个项目的架构'; sendMessage()"
            class="quick-action-btn w-full text-left text-[13px] px-4 py-2.5 rounded-xl border border-solid transition-colors duration-150 border-[var(--color-ide-border)] text-[var(--color-ide-text)] hover:border-[var(--color-ide-accent)]/30 hover:bg-[rgba(192,193,255,0.04)]">
            解释项目架构
          </button>
        </div>
      </div>

      <!-- Messages List -->
      <template v-else>
        <div v-for="(msg, idx) in messages" :key="idx" class="flex gap-2.5 items-start" :class="{ 'flex-row-reverse': msg.role === 'user' }">

          <!-- AI Message Bubble -->
          <template v-if="msg.role === 'assistant'">
            <div class="ai-bubble max-w-[88%] rounded-xl px-4 py-3 backdrop-blur-md border-l-[3px] border-l-[var(--color-chat-ai-border)] bg-[var(--color-chat-ai-bg)] shadow-[0_2px_8px_rgba(0,0,0,0.15)]">
              <!-- Loading dots -->
              <div v-if="isLoading && !msg.content" class="flex items-center gap-2 py-1 text-[var(--color-ide-text-dim)]">
                <span class="flex gap-1">
                  <span class="w-2 h-2 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:0ms"/>
                  <span class="w-2 h-2 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:150ms"/>
                  <span class="w-2 h-2 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:300ms"/>
                </span>
                <span class="text-[13px]">正在思考...</span>
              </div>
              <!-- Content -->
              <div v-else class="text-[13px] leading-relaxed whitespace-pre-wrap break-words text-[var(--color-ide-text)]">{{ msg.content }}</div>
            </div>
            <span class="text-[10px] mt-auto ml-2 whitespace-nowrap text-[var(--color-ide-text-dim)] tabular-nums">
              {{ formatTime(msg.timestamp) }} · AI
            </span>
          </template>

          <!-- User Message Bubble -->
          <template v-else-if="msg.role === 'user'">
            <div class="user-bubble rounded-xl px-4 py-2.5 max-w-[80%] bg-[var(--color-chat-user-bg)] border border-solid border-[var(--color-chat-user-border)]">
              <p class="text-[13px] leading-relaxed whitespace-pre-wrap break-words text-[var(--color-ide-text)]">{{ msg.content }}</p>
            </div>
            <span class="text-[10px] mt-auto ml-2 whitespace-nowrap text-[var(--color-ide-text-dim)] tabular-nums">
              {{ formatTime(msg.timestamp) }} · 你
            </span>
          </template>
        </div>
      </template>
    </div>

    <!-- ── Bottom Input Panel ────────────────────────── -->
    <div class="shrink-0 border-t border-[var(--color-ide-border)] px-4 pt-3 pb-3 space-y-3 bg-[var(--color-ide-bg-secondary)]">
      <!-- Model & Mode Selectors Row -->
      <div class="flex items-center justify-center gap-2">
        <!-- Model Selector -->
        <div class="relative model-select-wrapper">
          <button
            @click="showModelMenu = !showModelMenu"
            class="model-trigger flex items-center gap-1.5 h-7 pl-3 pr-2.5 rounded-lg text-[11px] font-semibold transition-all duration-150 border border-solid bg-[var(--color-editor-bg)] border-[var(--color-ide-border)] text-[var(--color-ide-text)] hover:border-[var(--color-ide-accent)]/50 focus:border-[var(--color-ide-border-focus)]"
            @blur="setTimeout(()=>showModelMenu=false,200)"
          >
            <span>{{ selectedModel.label }}</span>
            <span class="text-[var(--color-ide-text-dim)] font-normal">{{ selectedModel.desc }}</span>
            <ChevronDown :size="11" class="ml-0.5 text-[var(--color-ide-text-dim)]" />
          </button>
          <!-- Dropdown -->
          <Transition name="fade">
            <div v-if="showModelMenu" class="dropdown-menu absolute bottom-full left-0 mb-1.5 min-w-[180px] z-50">
              <button v-for="m in models" :key="m.id"
                @mousedown.prevent
                @click="selectedModel=m;showModelMenu=false"
                class="dropdown-item"
                :class="{ 'active': m.id === selectedModel.id }"
              >
                <span>{{ m.label }} <em class="font-normal text-[var(--color-ide-text-dim)]">{{ m.desc }}</em></span>
                <svg v-if="m.id===selectedModel.id" width="12" height="9" viewBox="0 0 12 9" fill="none" class="shrink-0 text-[var(--color-ide-accent)]"><path d="M1 3l4 4 6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
          </Transition>
        </div>

        <div class="w-px h-4 bg-[var(--color-ide-border)]" />

        <!-- Mode Selector -->
        <div class="relative mode-select-wrapper">
          <button
            @click="showModeMenu = !showModeMenu"
            class="mode-trigger flex items-center gap-1.5 h-7 pl-3 pr-2.5 rounded-lg text-[11px] font-medium transition-all duration-150 border border-solid bg-[var(--color-editor-bg)] border-[var(--color-ide-border)] text-[var(--color-ide-text)] hover:border-[var(--color-ide-accent)]/50 focus:border-[var(--color-ide-border-focus)]"
            @blur="setTimeout(()=>showModeMenu=false,200)"
          >
            <span>{{ selectedMode.label }}</span>
            <ChevronDown :size="11" class="ml-0.5 text-[var(--color-ide-text-dim)]" />
          </button>
          <Transition name="fade">
            <div v-if="showModeMenu" class="dropdown-menu absolute bottom-full left-0 mb-1.5 min-w-[120px] z-50">
              <button v-for="m in modes" :key="m.id"
                @mousedown.prevent
                @click="selectedMode=m;showModeMenu=false"
                class="dropdown-item"
                :class="{ 'active': m.id === selectedMode.id }"
              >
                <span>{{ m.label }}</span>
                <svg v-if="m.id===selectedMode.id" width="12" height="9" viewBox="0 0 12 9" fill="none" class="shrink-0 text-[var(--color-ide-accent)]"><path d="M1 3l4 4 6-6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </button>
            </div>
          </Transition>
        </div>
      </div>

      <!-- Input Box -->
      <div class="input-box relative rounded-xl border border-solid border-[var(--color-ide-border)] bg-[var(--color-chat-input-bg)] transition-all duration-150 focus-within:border-[var(--color-ide-border-focus)] focus-within:shadow-[0_0_0_3px_rgba(192,193,255,0.06)]">
        <textarea
          v-model="inputText"
          rows="2"
          placeholder="在此输入指令或提问..."
          class="w-full resize-none outline-none text-[13px] bg-transparent px-4 pt-3 pb-9 leading-relaxed text-[var(--color-ide-text)] placeholder:text-[rgba(144,143,160,0.45)]"
          @keydown.enter.exact.prevent="sendMessage"
        />

        <!-- Bottom toolbar inside textarea area -->
        <div class="absolute bottom-2 left-3 flex items-center gap-1">
          <button class="btn-ghost p-1.5" title="附件">
            <Paperclip :size="14" />
          </button>
          <button class="btn-ghost p-1.5" title="图片">
            <ImagePlus :size="14" />
          </button>
        </div>

        <!-- Send Button -->
        <button
          class="send-btn absolute bottom-2 right-2 flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all duration-150 bg-[var(--color-ide-accent)] text-[var(--color-chat-btn-primary-text)] hover:brightness-110 active:scale-[0.97]"
          :class="{ 'opacity-35 cursor-not-allowed pointer-events-none': !inputText.trim() || isLoading }"
          :disabled="!inputText.trim() || isLoading"
          @click="sendMessage"
        >
          发送
          <Send :size="11" />
        </button>
      </div>

      <!-- Keyboard Hint -->
      <div class="flex items-center justify-center gap-1.5 text-[10px] text-[var(--color-ide-text-dim)]">
        按 <kbd>Ctrl</kbd> + <kbd>Enter</kbd> 换行
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Component-scoped refinements on top of global tokens */
.quick-action-btn {
  background: transparent;
  cursor: pointer;
}

.ai-bubble {
  box-shadow:
    0 1px 2px rgba(0,0,0,0.08),
    0 4px 16px rgba(0,0,0,0.1);
}

.user-bubble {
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
</style>
