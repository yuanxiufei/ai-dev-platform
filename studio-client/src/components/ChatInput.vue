<script setup lang="ts">
/**
 * ChatInput.vue — 增强版聊天输入组件
 *
 * 参考项目：Continue (AtMentionPopover), Cline (chat input)
 *
 * 新增：
 *   - @-mention 触发 — 键入 "@" 自动弹出文件选择面板 (Continue 风格)
 *   - 文件引用标签 — 选择文件后在输入框中显示为可视化芯片
 *   - insertFileRef — 外部可通过 ref 调用插入文件引用
 */
import { ImageIcon, Paperclip, ArrowUp, X } from "lucide-vue-next"
import { computed, nextTick, ref } from "vue"

const props = defineProps<{
  disabled?: boolean
  isStreaming?: boolean
  placeholder?: string
  /** 已引用的文件路径列表（避免重复 @ 引用） */
  referencedPaths?: Set<string>
}>()

const emit = defineEmits<{
  (e: "send", text: string, files: AttachedFile[]): void
  (e: "stop"): void
  (e: "mention", show: boolean): void
  (e: "mentionFilter", query: string): void
}>()

export interface AttachedFile {
  id: string
  name: string
  size: string
  type: "image" | "file"
}

const inputText = ref("")
const attachedFiles = ref<AttachedFile[]>([])
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const focusInput = async () => {
  await nextTick()
  textareaRef.value?.focus()
}

// ═══════════════════ @-mention 逻辑 ═══════════════════
const mentionActive = ref(false)
const mentionQuery = ref("")

/**
 * 处理 textarea 的 input 事件 —— 检测 @ 触发
 * 参考 Continue: AtMentionPopover — 检测 @ 后自动弹出面板
 */
function handleInput(e: Event) {
  handleAutoResize()

  const el = textareaRef.value
  if (!el) return

  const text = inputText.value
  const cursorPos = el.selectionStart

  // 向前遍历找到最近的 @ 符号
  let mentionStart = -1
  for (let i = cursorPos - 1; i >= 0; i--) {
    const ch = text[i]
    if (ch === "@") {
      // 检查 @ 前面是否为空白字符或行首（避免匹配邮箱等）
      const prevChar = i > 0 ? text[i - 1] : " "
      if (/\s/.test(prevChar) || prevChar === undefined) {
        mentionStart = i
      }
      break
    }
    // 遇到空格就停止搜索
    if (/\s/.test(ch)) break
  }

  if (mentionStart >= 0) {
    // 提取 @ 之后的文本作为过滤词
    const query = text.slice(mentionStart + 1, cursorPos)
    mentionQuery.value = query
    mentionActive.value = true
    emit("mention", true)
    emit("mentionFilter", query)
  } else {
    if (mentionActive.value) {
      mentionActive.value = false
      emit("mention", false)
    }
  }
}

/**
 * 外部调用 —— 在输入框中插入文件引用标记
 * 格式: @file:path/to/file.ts
 */
function insertFileRef(filePath: string) {
  const el = textareaRef.value
  if (!el) {
    inputText.value += `@file:${filePath} `
    mentionActive.value = false
    emit("mention", false)
    return
  }

  // 找到光标前的 @ 位置，替换整个 "@xxx" 为 "@file:path"
  const cursorPos = el.selectionStart
  const text = inputText.value

  let mentionStart = -1
  for (let i = cursorPos - 1; i >= 0; i--) {
    if (text[i] === "@") {
      const prevChar = i > 0 ? text[i - 1] : " "
      if (/\s/.test(prevChar)) {
        mentionStart = i
      }
      break
    }
    if (/\s/.test(text[i])) break
  }

  if (mentionStart >= 0) {
    const before = text.slice(0, mentionStart)
    const after = text.slice(cursorPos)
    inputText.value = before + `@file:${filePath} ` + after
    const newPos = mentionStart + filePath.length + 7 // @file: + path + space
    nextTick(() => {
      el.focus()
      el.setSelectionRange(newPos, newPos)
    })
  } else {
    // 没有活跃的 @，直接在光标处插入
    const start = el.selectionStart
    const end = el.selectionEnd
    const before = text.slice(0, start)
    const after2 = text.slice(end)
    inputText.value = before + `@file:${filePath} ` + after2
    const newPos = start + filePath.length + 7
    nextTick(() => {
      el.focus()
      el.setSelectionRange(newPos, newPos)
    })
  }

  mentionActive.value = false
  emit("mention", false)
  handleAutoResize()
}

const handleSend = () => {
  const text = inputText.value.trim()
  if (!text || props.disabled) return
  emit("send", text, [...attachedFiles.value])
  inputText.value = ""
  attachedFiles.value = []
  mentionActive.value = false
  emit("mention", false)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === "Enter" && !e.shiftKey) {
    // 如果有 @ 面板弹出时 Enter 会触发选择，不发送消息
    if (mentionActive.value) {
      return // 让 AtMentionPopup 处理
    }
    e.preventDefault()
    handleSend()
  }
  if (e.key === "Escape" && mentionActive.value) {
    mentionActive.value = false
    emit("mention", false)
  }
}

function handleAutoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = "auto"
  el.style.height = `${Math.min(el.scrollHeight, 180)}px`
}

function removeFile(id: string) {
  attachedFiles.value = attachedFiles.value.filter((f) => f.id !== id)
}

function simulateAttach() {
  const id = crypto.randomUUID()
  attachedFiles.value.push({
    id,
    name: `screenshot_${Date.now()}.png`,
    size: `${(Math.random() * 1000 + 50).toFixed(2)} KB`,
    type: "image",
  })
  focusInput()
}

function simulateImage() {
  const id = crypto.randomUUID()
  attachedFiles.value.push({
    id,
    name: `image_${Date.now()}.png`,
    size: `${(Math.random() * 500 + 10).toFixed(2)} KB`,
    type: "image",
  })
  focusInput()
}

defineExpose({ focusInput, insertFileRef, inputText, textareaRef })
</script>

<template>
  <div class="flex flex-col">
    <!-- 附件预览 -->
    <div v-if="attachedFiles.length" class="flex flex-wrap gap-2 mb-3 px-1">
      <div
        v-for="f in attachedFiles"
        :key="f.id"
        class="flex items-center gap-2 rounded-lg bg-white/8 border border-[var(--color-ide-border)] px-2.5 py-1.5 text-xs text-[var(--color-ide-text)] group"
      >
        <ImageIcon v-if="f.type === 'image'" class="w-3.5 h-3.5 text-brand-400" />
        <Paperclip v-else class="w-3.5 h-3.5 text-[var(--color-ide-text-dim)]" />
        <span>{{ f.name }}</span>
        <span class="text-[var(--color-ide-text-dim)]">·</span>
        <span class="text-[var(--color-ide-text-dim)]">{{ f.size }}</span>
        <button
          class="ml-1 p-0.5 rounded hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
          @click="removeFile(f.id)"
        >
          <X class="w-3 h-3" />
        </button>
      </div>
    </div>

    <!-- 主输入区 -->
    <div class="flex items-end gap-2.5 bg-surface-800 border border-[var(--color-ide-border)] focus-within:border-brand-500/30 focus-within:shadow-lg focus-within:shadow-brand-500/5 rounded-2xl p-2.5 transition-all duration-300">
      <!-- 附件按钮区 -->
      <div class="flex items-center gap-1 mb-0.5">
        <button
          class="p-2 rounded-xl text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-white/8 transition-colors"
          title="附加文件"
          @click="simulateAttach"
        >
          <Paperclip class="w-4 h-4" />
        </button>
        <button
          class="p-2 rounded-xl text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-white/8 transition-colors"
          title="附加图片"
          @click="simulateImage"
        >
          <ImageIcon class="w-4 h-4" />
        </button>
      </div>

      <!-- 文本域 -->
      <textarea
        ref="textareaRef"
        v-model="inputText"
        :disabled="disabled"
        :placeholder="placeholder || '输入消息...（键入 @ 引用文件）'"
        rows="1"
        class="flex-1 resize-none bg-transparent text-sm text-[var(--color-ide-text)] placeholder-[var(--color-ide-text-dim)] focus:outline-none py-1.5 max-h-[180px]"
        @keydown="handleKeydown"
        @input="handleInput"
      />

      <!-- 发送按钮 -->
      <button
        v-if="!isStreaming"
        :disabled="!inputText.trim() || disabled"
        class="shrink-0 p-2 rounded-[3px] bg-[var(--color-ide-accent)] text-white hover:bg-[var(--color-ide-accent-hover)] transition-all duration-150 disabled:opacity-30 disabled:cursor-not-allowed"
        @click="handleSend"
      >
        <ArrowUp class="w-4 h-4" />
      </button>
      <button
        v-else
        class="shrink-0 p-2 rounded-xl bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors"
        @click="emit('stop')"
      >
        <X class="w-4 h-4" />
      </button>
    </div>
  </div>
</template>
