<script setup lang="ts">
/**
 * Markdown Preview — VSCode Ctrl+Shift+V 对标
 * 
 * 使用 marked 渲染 Markdown 为 HTML，显示在编辑器右侧分屏
 */
import { computed, ref, onMounted, onUnmounted } from "vue"
import { marked } from "marked"
import { useThemeStore } from "@/stores/useThemeStore"
import { X, ExternalLink, Maximize2, Minimize2 } from "lucide-vue-next"

const props = defineProps<{
  content: string
  /** 关闭预览回调 */
  onClose?: () => void
}>()

const emit = defineEmits<{
  (e: "close"): void
}>()

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.isDark())
const scrollSync = ref(true)
const fullWidth = ref(false)

/** 渲染 Markdown */
const renderedHtml = computed(() => {
  if (!props.content) return ""
  try {
    return marked.parse(props.content, { 
      async: false,
      gfm: true,
      breaks: true,
    }) as string
  } catch {
    return `<p style="color:var(--color-ide-error)">Markdown 解析错误</p>`
  }
})

/** 滚动同步 */
const editorContainer = ref<HTMLElement | null>(null)
const previewContainer = ref<HTMLElement | null>(null)

function onEditorScroll(e: Event): void {
  if (!scrollSync.value || !previewContainer.value) return
  const el = e.target as HTMLElement
  const ratio = el.scrollTop / (el.scrollHeight - el.clientHeight)
  previewContainer.value.scrollTop = ratio * (previewContainer.value.scrollHeight - previewContainer.value.clientHeight)
}

function onPreviewScroll(e: Event): void {
  if (!scrollSync.value || !editorContainer.value) return
  const el = e.target as HTMLElement
  const ratio = el.scrollTop / (el.scrollHeight - el.clientHeight)
  editorContainer.value.scrollTop = ratio * (editorContainer.value.scrollHeight - editorContainer.value.clientHeight)
}

function close(): void {
  emit("close")
  props.onClose?.()
}

// Keyboard: Escape to close
function onKeydown(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    e.preventDefault()
    close()
  }
}

onMounted(() => {
  document.addEventListener("keydown", onKeydown)
})

onUnmounted(() => {
  document.removeEventListener("keydown", onKeydown)
})
</script>

<template>
  <div class="markdown-preview flex-1 flex flex-col min-w-0 overflow-hidden"
    :style="{ background: isDark ? '#1e1e1e' : '#ffffff' }">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 shrink-0"
      style="height: 35px; border-bottom: 1px solid var(--color-ide-border); background: var(--color-ide-bg-secondary);">
      <div class="flex items-center gap-2 text-[12px]" style="color: var(--color-ide-text-dim);">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14,2 14,8 20,8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
          <polyline points="10,9 9,9 8,9"/>
        </svg>
        <span>预览</span>
        <span class="text-[10px] opacity-50">Markdown</span>
      </div>
      <div class="flex items-center gap-1">
        <!-- Scroll sync toggle -->
        <button
          class="w-6 h-6 flex items-center justify-center rounded-[3px] transition-colors"
          :style="{ color: scrollSync ? 'var(--color-ide-accent)' : 'var(--color-ide-text-dim)' }"
          :title="scrollSync ? '已启用滚动同步' : '启用滚动同步'"
          @click="scrollSync = !scrollSync"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="18,15 12,9 6,15"/>
          </svg>
        </button>
        <!-- Full width toggle -->
        <button
          class="w-6 h-6 flex items-center justify-center rounded-[3px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
          :style="{ color: 'var(--color-ide-text-dim)' }"
          :title="fullWidth ? '分屏显示' : '全宽显示'"
          @click="fullWidth = !fullWidth"
        >
          <Maximize2 v-if="!fullWidth" :size="12" />
          <Minimize2 v-else :size="12" />
        </button>
        <!-- Open in browser -->
        <button
          class="w-6 h-6 flex items-center justify-center rounded-[3px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
          style="color: var(--color-ide-text-dim);"
          title="在浏览器打开"
          @click="() => {
            const blob = new Blob([renderedHtml], { type: 'text/html' })
            window.open(URL.createObjectURL(blob), '_blank')
          }"
        >
          <ExternalLink :size="12" />
        </button>
        <!-- Close -->
        <button
          class="w-6 h-6 flex items-center justify-center rounded-[3px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
          style="color: var(--color-ide-text-dim);"
          title="关闭预览 (Escape)"
          @click="close"
        >
          <X :size="14" />
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-hidden relative">
      <div
        ref="previewContainer"
        class="h-full overflow-y-auto px-8 py-6 markdown-body"
        :style="{ background: isDark ? '#1e1e1e' : '#ffffff' }"
        @scroll="onPreviewScroll"
      >
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-if="renderedHtml" v-html="renderedHtml" class="prose max-w-3xl mx-auto" />
        <div v-else class="flex flex-col items-center justify-center h-full gap-2 text-[12px]" style="color: var(--color-ide-text-dim);">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14,2 14,8 20,8"/>
          </svg>
          <span>无内容可预览</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* GitHub-style Markdown rendering */
.markdown-body :deep(h1) {
  font-size: 2em;
  font-weight: 600;
  margin: 0.67em 0;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--color-ide-border);
}
.markdown-body :deep(h2) {
  font-size: 1.5em;
  font-weight: 600;
  margin: 0.83em 0;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--color-ide-border);
}
.markdown-body :deep(h3) {
  font-size: 1.25em;
  font-weight: 600;
  margin: 1em 0;
}
.markdown-body :deep(h4) {
  font-size: 1em;
  font-weight: 600;
  margin: 1.33em 0;
}
.markdown-body :deep(p) {
  margin: 0.5em 0;
  line-height: 1.6;
}
.markdown-body :deep(code) {
  font-family: 'Cascadia Code', 'Fira Code', monospace;
  background: var(--color-ide-surface-active);
  padding: 0.2em 0.4em;
  border-radius: 3px;
  font-size: 0.9em;
}
.markdown-body :deep(pre) {
  background: var(--color-ide-surface-active);
  padding: 16px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 0.8em 0;
  border: 1px solid var(--color-ide-border);
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--color-ide-accent);
  padding: 0.5em 1em;
  margin: 0.8em 0;
  color: var(--color-ide-text-dim);
  background: var(--color-ide-surface-active);
}
.markdown-body :deep(ul), .markdown-body :deep(ol) {
  padding-left: 2em;
  margin: 0.5em 0;
}
.markdown-body :deep(li) {
  margin: 0.25em 0;
}
.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 0.8em 0;
  width: 100%;
}
.markdown-body :deep(th), .markdown-body :deep(td) {
  border: 1px solid var(--color-ide-border);
  padding: 6px 13px;
  text-align: left;
}
.markdown-body :deep(th) {
  background: var(--color-ide-bg-secondary);
  font-weight: 600;
}
.markdown-body :deep(tr:nth-child(even)) {
  background: var(--color-ide-surface-active);
}
.markdown-body :deep(a) {
  color: var(--color-ide-accent);
  text-decoration: none;
}
.markdown-body :deep(a:hover) {
  text-decoration: underline;
}
.markdown-body :deep(img) {
  max-width: 100%;
  border-radius: 4px;
}
.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid var(--color-ide-border);
  margin: 1.5em 0;
}
.markdown-body :deep(input[type="checkbox"]) {
  margin-right: 0.5em;
}
</style>
