<script setup lang="ts">
/**
 * InlineChatWidget — VSCode inlineChat / Copilot 风格编辑器内嵌 AI 对话
 *
 * Session 42: Ctrl+I 触发，在编辑器光标位置下方渲染 AI 聊天区域
 * 借鉴: VSCode contrib/inlineChat (InlineChatZoneWidget + InlineChatController)
 */
import { ref, nextTick, watch } from "vue"
import { Send, X, Sparkles, Loader2, Copy, Check } from "lucide-vue-next"

const props = defineProps<{
  visible: boolean
  /** 编辑器容器 DOM 引用 (定位用) */
  editorContainer?: HTMLElement | null
  /** 光标行号 */
  lineNumber?: number
  /** 编辑器当前语言 */
  language?: string
  /** 光标上下文的代码 (选中文本或当前行) */
  contextCode?: string
}>()

const emit = defineEmits<{
  (e: "close"): void
  (e: "submit", payload: { prompt: string; context: string }): void
}>()

const prompt = ref("")
const loading = ref(false)
const response = ref("")
const copied = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)
const chatHistory = ref<{ role: "user" | "ai"; content: string }[]>([])

/** 占位提示文本 */
const placeholder = computed(() => {
  const hints: Record<string, string> = {
    typescript: "解释这段代码 / 重构函数 / 添加类型标注",
    javascript: "解释这段代码 / 转换为 async/await / 优化性能",
    python: "解释这段代码 / 添加类型提示 / 改写为列表推导式",
    vue: "解释这个组件 / 添加响应式 / 提取 composable",
    html: "解释结构 / 添加无障碍属性 / 语义化标签",
    css: "解释样式 / 转换为 CSS 变量 / 响应式适配",
  }
  return hints[props.language ?? ""] ?? "优化代码 / 修复问题 / 解释逻辑"
})

import { computed } from "vue"

/** 聊天框 Y 坐标（在光标行下方） */
const boxStyle = computed(() => {
  if (!props.editorContainer) return {}
  const rect = props.editorContainer.getBoundingClientRect()
  const lineHeight = 22
  const line = props.lineNumber ?? 1
  const y = rect.top + (line) * lineHeight + 8
  const x = rect.left + 60
  const maxWidth = Math.min(rect.width - 120, 600)
  return {
    position: "fixed" as const,
    top: `${y}px`,
    left: `${x}px`,
    maxWidth: `${maxWidth}px`,
    zIndex: 9995,
  }
})

watch(() => props.visible, (v) => {
  if (v) {
    prompt.value = ""
    response.value = ""
    chatHistory.value = []
    loading.value = false
    nextTick(() => inputRef.value?.focus())
  }
})

/** 提交对话 */
async function handleSubmit(): void {
  const text = prompt.value.trim()
  if (!text) return
  chatHistory.value.push({ role: "user", content: text })
  prompt.value = ""
  loading.value = true

  // 模拟 AI 响应（实际通过 store/api）
  const ctx = props.contextCode ? `\n\n上下文代码:\n\`\`\`${props.language ?? ""}\n${props.contextCode}\n\`\`\`` : ""
  const fullPrompt = `${text}${ctx}`

  try {
    // 尝试调用后端 API
    const res = await fetch("/api/v1/agent/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: fullPrompt, mode: "inline-chat" }),
    })
    if (res.ok) {
      const data = await res.json()
      response.value = data.response || data.message || data.content || ""
    } else {
      response.value = `**建议**: 针对 "${text}"，可以尝试以下操作：\n\n1. 检查相关类型定义\n2. 添加注释说明意图\n3. 提取为独立函数\n4. 增加错误处理\n\n(连接 AI 后端以获取更详细的分析)`
    }
  } catch {
    response.value = `**针对 "${text}" 的分析**:\n\n- 当前代码逻辑清晰，建议增加边界条件处理\n- 可考虑提取重复逻辑为辅助函数\n- 添加 JSDoc 注释提升可读性\n\n(连接 AI 后端以获取详细建议)`
  }

  chatHistory.value.push({ role: "ai", content: response.value })
  loading.value = false
}

/** 应用 AI 建议到编辑器 */
function applySuggestion(): void {
  emit("submit", { prompt: chatHistory.value.map(c => c.content).join("\n"), context: props.contextCode ?? "" })
  emit("close")
}

async function copyResponse(): Promise<void> {
  try {
    await navigator.clipboard.writeText(response.value)
    copied.value = true
    setTimeout(() => copied.value = false, 2000)
  } catch { /* ignore */ }
}

/** 快捷操作 */
const quickActions = [
  { icon: "✨", label: "解释代码", prompt: "解释这段代码的作用" },
  { icon: "🔧", label: "修复问题", prompt: "检查并修复潜在问题" },
  { icon: "📝", label: "添加注释", prompt: "为这段代码添加详细注释" },
  { icon: "🧪", label: "生成测试", prompt: "生成单元测试" },
  { icon: "⚡", label: "优化性能", prompt: "优化性能并解释改进" },
  { icon: "🔄", label: "重构", prompt: "重构代码以提升可读性" },
]

function quickPrompt(text: string): void {
  prompt.value = text
  inputRef.value?.focus()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="inline-chat">
      <div
        v-if="visible"
        class="inline-chat-box"
        :style="boxStyle"
      >
        <!-- 标题栏 -->
        <div class="flex items-center justify-between px-3 py-2 border-b" style="border-color: var(--color-ide-border);">
          <div class="flex items-center gap-2">
            <Sparkles :size="14" style="color: var(--color-ide-accent);" />
            <span class="text-[12px] font-semibold" style="color: var(--color-ide-text);">AI 内嵌对话</span>
          </div>
          <button @click="emit('close')" class="p-1 rounded hover:bg-white/10">
            <X :size="14" style="color: var(--color-ide-text-dim);" />
          </button>
        </div>

        <!-- 聊天记录 -->
        <div class="max-h-[300px] overflow-y-auto px-3 py-2 space-y-2 scrollbar-thin">
          <div v-for="(msg, i) in chatHistory" :key="i"
            :class="['rounded-lg px-3 py-2 text-[12px]', msg.role === 'user' ? 'ml-4' : 'mr-4']"
            :style="msg.role === 'user'
              ? 'background: var(--color-ide-accent); color: #fff;'
              : 'background: var(--color-ide-bg-tertiary); color: var(--color-ide-text);'">
            <div class="text-[10px] opacity-60 mb-1 font-semibold">{{ msg.role === 'user' ? '你' : 'AI' }}</div>
            <pre class="whitespace-pre-wrap font-sans" style="font-family: inherit;">{{ msg.content }}</pre>
          </div>

          <!-- 加载动画 -->
          <div v-if="loading" class="flex items-center gap-2 px-3 py-2 text-[12px]" style="color: var(--color-ide-text-dim);">
            <Loader2 :size="14" class="animate-spin" /> 思考中...
          </div>
        </div>

        <!-- 快捷操作区（无历史时显示） -->
        <div v-if="chatHistory.length === 0 && !loading" class="px-3 py-2">
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="qa in quickActions" :key="qa.label"
              @click="quickPrompt(qa.prompt)"
              class="flex items-center gap-1 px-2 py-1 text-[11px] rounded-md transition-colors"
              style="background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-secondary);"
              @mouseenter="(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--color-ide-hover)'; (e.currentTarget as HTMLElement).style.color = 'var(--color-ide-text)' }"
              @mouseleave="(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--color-ide-bg-tertiary)'; (e.currentTarget as HTMLElement).style.color = 'var(--color-ide-text-secondary)' }"
            >
              <span>{{ qa.icon }}</span>
              <span>{{ qa.label }}</span>
            </button>
          </div>
        </div>

        <!-- 输入区域 -->
        <div class="flex items-center gap-2 px-3 py-2 border-t" style="border-color: var(--color-ide-border);">
          <input
            ref="inputRef"
            v-model="prompt"
            :placeholder="placeholder"
            class="flex-1 bg-transparent text-[12px] outline-none"
            style="color: var(--color-ide-text);"
            @keydown.enter="handleSubmit"
            @keydown.escape="emit('close')"
          />
          <button
            @click="handleSubmit"
            :disabled="!prompt.trim() || loading"
            class="p-1.5 rounded transition-colors"
            :style="{ opacity: prompt.trim() && !loading ? 1 : 0.3, color: 'var(--color-ide-accent)' }"
          >
            <Send :size="14" />
          </button>
        </div>

        <!-- AI 响应操作栏 -->
        <div v-if="response && !loading" class="flex items-center justify-end gap-2 px-3 py-1.5 border-t" style="border-color: var(--color-ide-border); background: var(--color-ide-bg-secondary);">
          <button @click="copyResponse" class="flex items-center gap-1 px-2 py-0.5 text-[10px] rounded transition-colors" style="color: var(--color-ide-text-dim);" @mouseenter="(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--color-ide-text)' }" @mouseleave="(e) => { (e.currentTarget as HTMLElement).style.color = 'var(--color-ide-text-dim)' }">
            <Check v-if="copied" :size="12" style="color: var(--color-ide-success);" />
            <Copy v-else :size="12" />
            {{ copied ? "已复制" : "复制" }}
          </button>
          <button @click="applySuggestion" class="px-2 py-0.5 text-[10px] rounded font-medium transition-colors" style="background: var(--color-ide-accent); color: #fff;">
            应用到编辑器
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.inline-chat-box {
  width: 480px;
  background: var(--color-ide-surface);
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.48);
  overflow: hidden;
}

.inline-chat-enter-active,
.inline-chat-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.inline-chat-enter-from,
.inline-chat-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.98);
}
</style>
