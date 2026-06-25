<script setup lang="ts">
import { nextTick, ref } from "vue"

const props = defineProps<{
  disabled?: boolean
  isStreaming?: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  (e: "send", text: string, files: AttachedFile[]): void
  (e: "stop"): void
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

const handleSend = () => {
  const text = inputText.value.trim()
  if (!text || props.disabled) return
  emit("send", text, [...attachedFiles.value])
  inputText.value = ""
  attachedFiles.value = []
}

const _handleKeydown = (e: KeyboardEvent) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

const _handleAutoResize = () => {
  const el = textareaRef.value
  if (!el) return
  el.style.height = "auto"
  el.style.height = `${Math.min(el.scrollHeight, 180)}px`
}

const _removeFile = (id: string) => {
  attachedFiles.value = attachedFiles.value.filter((f) => f.id !== id)
}

const _simulateAttach = () => {
  // 模拟文件附加（后续可对接真实文件上传）
  const id = crypto.randomUUID()
  attachedFiles.value.push({
    id,
    name: `screenshot_${Date.now()}.png`,
    size: `${(Math.random() * 1000 + 50).toFixed(2)} KB`,
    type: "image",
  })
  focusInput()
}

const _simulateImage = () => {
  const id = crypto.randomUUID()
  attachedFiles.value.push({
    id,
    name: `image_${Date.now()}.png`,
    size: `${(Math.random() * 500 + 10).toFixed(2)} KB`,
    type: "image",
  })
  focusInput()
}

defineExpose({ focusInput })
</script>

<template>
  <div class="flex flex-col">
    <!-- 附件预览 -->
    <div v-if="attachedFiles.length" class="flex flex-wrap gap-2 mb-3 px-1">
      <div
        v-for="f in attachedFiles"
        :key="f.id"
        class="flex items-center gap-2 rounded-lg bg-white/8 border border-white/10 px-2.5 py-1.5 text-xs text-gray-300 group"
      >
        <ImageIcon v-if="f.type === 'image'" class="w-3.5 h-3.5 text-brand-400" />
        <Paperclip v-else class="w-3.5 h-3.5 text-gray-400" />
        <span>{{ f.name }}</span>
        <span class="text-gray-600">·</span>
        <span class="text-gray-500">{{ f.size }}</span>
        <button
          class="ml-1 p-0.5 rounded hover:bg-white/10 text-gray-500 hover:text-gray-300 transition-colors"
          @click="removeFile(f.id)"
        >
          <X class="w-3 h-3" />
        </button>
      </div>
    </div>

    <!-- 主输入区 -->
    <div class="flex items-end gap-2.5 bg-surface-800 border border-white/10 focus-within:border-brand-500/30 focus-within:shadow-lg focus-within:shadow-brand-500/5 rounded-2xl p-2.5 transition-all duration-300">
      <!-- 附件按钮区 -->
      <div class="flex items-center gap-1 mb-0.5">
        <button
          class="p-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-white/8 transition-colors"
          title="附加文件"
          @click="simulateAttach"
        >
          <Paperclip class="w-4 h-4" />
        </button>
        <button
          class="p-2 rounded-xl text-gray-500 hover:text-gray-300 hover:bg-white/8 transition-colors"
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
        :placeholder="placeholder || 'Ask anything...'"
        rows="1"
        class="flex-1 resize-none bg-transparent text-sm text-gray-200 placeholder-gray-500 focus:outline-none py-1.5 max-h-[180px]"
        @keydown="handleKeydown"
        @input="handleAutoResize"
      />

      <!-- 发送按钮 -->
      <button
        v-if="!isStreaming"
        :disabled="!inputText.trim() || disabled"
        class="shrink-0 p-2 rounded-xl bg-gradient-to-br from-brand-400 to-purple-500 text-white hover:shadow-lg hover:shadow-brand-500/25 transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:shadow-none"
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
