<script setup lang="ts">
/**
 * CodeBuddy IDE — Peek View (VSCode Peek Definition/References)
 *
 * Session 26: 悬浮预览窗口，不离开当前文件即可查看定义/引用
 * 借鉴: VSCode peekView/peekWidget — embedded editor overlay
 */

import { X, ChevronLeft, ChevronRight, ArrowUpDown, FileCode } from "lucide-vue-next"
import { computed, ref, shallowRef, onMounted, onBeforeUnmount, watch, nextTick } from "vue"
import type { EditorTab } from "@/types/ide"

export interface PeekItem {
  file: string
  label: string
  startLine: number
  startColumn?: number
  endLine?: number
  endColumn?: number
  content?: string
  language?: string
}

const props = defineProps<{
  visible: boolean
  items: PeekItem[]
  activeIndex: number
  /** 编辑器位置（相对于编辑器区域左上角） */
  x?: number
  y?: number
}>()

const emit = defineEmits<{
  (e: "close"): void
  (e: "next"): void
  (e: "prev"): void
  (e: "open-full", item: PeekItem): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const editorContainerRef = ref<HTMLElement | null>(null)
const editorRef = shallowRef<any>(null)
let monacoRaw: any = null

const currentItem = computed(() => props.items[props.activeIndex] ?? null)
const filename = computed(() => currentItem.value?.file.split(/[/\\]/).pop() ?? "")
const fileDir = computed(() => {
  const f = currentItem.value?.file ?? ""
  const idx = f.replace(/\\/g, "/").lastIndexOf("/")
  return idx > -1 ? f.substring(0, idx) : ""
})

/** VSCode 风格: 标题栏右侧导航 */
const hasMultiple = computed(() => props.items.length > 1)

/** 生成预览代码 */
function renderPreviewContent(item: PeekItem): string {
  if (item.content) return item.content
  // 生成模拟预览内容
  const lines: string[] = []
  const start = Math.max(1, item.startLine - 3)
  const end = (item.endLine ?? item.startLine) + 5
  for (let i = start; i <= end; i++) {
    const marker = i === item.startLine ? " → " : "   "
    lines.push(`${marker}${i}: // ... preview line ${i} ...`)
  }
  return lines.join("\n")
}

async function initEditor() {
  if (!editorContainerRef.value) return
  try {
    monacoRaw = (await import("monaco-editor")).default
    const item = currentItem.value
    if (!item) return

    const content = renderPreviewContent(item)
    const lang = item.language ?? detectLanguage(item.file)

    const editor = monacoRaw.editor.create(editorContainerRef.value, {
      value: content,
      language: lang,
      theme: "codebuddy-dark",
      automaticLayout: true,
      readOnly: true,
      fontSize: 12,
      fontFamily: "'JetBrains Mono', 'Cascadia Code', Consolas, monospace",
      lineHeight: 19,
      padding: { top: 4, bottom: 4 },
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      lineNumbers: "on",
      lineNumbersMinChars: 3,
      folding: false,
      glyphMargin: false,
      renderLineHighlight: "line",
      guides: { indentation: false, bracketPairs: false },
      overviewRulerLanes: 0,
      scrollbar: { vertical: "hidden", horizontal: "hidden", useShadows: false },
      stickyScroll: { enabled: false },
      contextmenu: false,
      wordWrap: "on",
    })

    // Reveal the target line
    editor.revealLineInCenter(item.startLine)
    editorRef.value = editor
  } catch (e) {
    console.warn("[PeekView] Monaco init error:", e)
  }
}

function detectLanguage(filePath: string): string {
  const ext = filePath.split(".").pop()?.toLowerCase() ?? ""
  const map: Record<string, string> = {
    ts: "typescript", tsx: "typescript", js: "javascript", jsx: "javascript",
    py: "python", rs: "rust", go: "go", vue: "html", css: "css",
    scss: "scss", html: "html", json: "json", yaml: "yaml", yml: "yaml",
    md: "markdown", toml: "ini", sh: "shell", sql: "sql",
  }
  return map[ext] ?? "plaintext"
}

watch(() => props.activeIndex, () => {
  nextTick(() => {
    if (editorRef.value) editorRef.value.dispose()
    editorRef.value = null
    initEditor()
  })
})

onMounted(() => initEditor())
onBeforeUnmount(() => {
  editorRef.value?.dispose()
  editorRef.value = null
})
</script>

<template>
  <Transition name="peek-slide">
    <div
      v-if="visible && currentItem"
      ref="containerRef"
      class="peek-view absolute left-0 right-0 z-50 mx-4 rounded-md shadow-2xl flex flex-col overflow-hidden"
      style="top: 0; bottom: 80px; min-height: 120px; max-height: 400px;"
      :style="{
        top: y != null ? `${y}px` : '0',
        left: x != null ? `${x}px` : undefined,
        right: x != null ? 'auto' : '16px',
        maxWidth: x != null ? 'calc(100% - 32px)' : '640px',
      }"
    >
      <!-- Header Bar (VSCode style) -->
      <div class="flex items-center h-8 px-3 shrink-0 border-b"
        style="background: var(--color-ide-surface); border-color: var(--color-ide-border);">
        <!-- File icon + name -->
        <FileCode :size="14" class="text-[var(--color-ide-text-dim)] mr-1.5 shrink-0" />
        <span class="text-[12px] font-medium text-[var(--color-ide-text)] truncate mr-2">
          {{ filename }}
        </span>
        <span class="text-[10px] text-[var(--color-ide-text-dim)] opacity-50 truncate flex-1">
          {{ fileDir }}
        </span>

        <!-- Navigation (VSCode: x of y + arrows) -->
        <template v-if="hasMultiple">
          <button
            class="p-0.5 rounded hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] transition-colors"
            title="上一个 (Shift+F12)" @click="emit('prev')"
          >
            <ChevronLeft :size="14" />
          </button>
          <span class="text-[10px] text-[var(--color-ide-text-dim)] mx-1 tabular-nums select-none">
            {{ activeIndex + 1 }}/{{ items.length }}
          </span>
          <button
            class="p-0.5 rounded hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] transition-colors"
            title="下一个 (F12)" @click="emit('next')"
          >
            <ChevronRight :size="14" />
          </button>
        </template>

        <!-- Actions -->
        <button
          class="p-0.5 rounded hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] transition-colors ml-1"
          title="在新编辑器中打开"
          @click="emit('open-full', currentItem)"
        >
          <ArrowUpDown :size="13" />
        </button>
        <button
          class="p-0.5 rounded hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] transition-colors ml-0.5"
          title="关闭 (Escape)" @click="emit('close')"
        >
          <X :size="14" />
        </button>
      </div>

      <!-- Editor Area -->
      <div
        ref="editorContainerRef"
        class="flex-1 min-h-0 overflow-hidden"
        style="background: var(--color-terminal-bg);"
      />

      <!-- Footer (file info + line) -->
      <div class="flex items-center h-6 px-3 shrink-0 border-t text-[10px]"
        style="background: var(--color-ide-surface); border-color: var(--color-ide-border);">
        <span class="text-[var(--color-ide-text-dim)]">
          {{ currentItem.label }} · 第 {{ currentItem.startLine }} 行
        </span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.peek-view {
  border: 1px solid var(--color-ide-border);
  background: var(--color-terminal-bg);
}

/* Slide-up animation */
.peek-slide-enter-active { transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); }
.peek-slide-leave-active { transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1); }
.peek-slide-enter-from { opacity: 0; transform: translateY(12px); }
.peek-slide-leave-to { opacity: 0; transform: translateY(8px); }
</style>
