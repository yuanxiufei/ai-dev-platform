<script setup lang="ts">
/**
 * DiffViewer.vue — 代码差异对比组件
 *
 * 能力：
 *   - 统一 diff 展示（unified / split 双模式）
 *   - 行级高亮（新增/删除/上下文）
 *   - 语言语法高亮（Monaco）
 *   - 折叠/展开 + 工具栏（模式切换、复制、下载）
 *   - 文件操作摘要条（创建/修改/删除 + 行数统计）
 *
 * 数据源：AgentChat SSE 事件 {"type":"diff","data": DiffData}
 */

import {
  AlignLeft,
  ArrowDown,
  ArrowUp,
  Columns,
  Copy,
  Download,
  FileEdit,
  FileMinus,
  FilePlus,
  ChevronDown,
  ChevronRight,
  Minus,
  Plus,
} from "lucide-vue-next"
import { computed, ref } from "vue"
import type { DiffData } from "@/types/studio"

const props = defineProps<{
  diff: DiffData | null
  /** 当前 diff 是否可折叠 */
  collapsible?: boolean
  /** 初始高亮的 hunk 索引（-1 表示不高亮） */
  activeHunkIndex?: number
}>()

const emit = defineEmits<{
  (e: "close"): void
  (e: "apply"): void
  /** Monaco 风格 — 跳转到指定 hunk */
  (e: "jumpToHunk", index: number): void
}>()

// ── 视图模式 ──
type ViewMode = "unified" | "split"
const viewMode = ref<ViewMode>("unified")
const collapsed = ref(false)

// ── Hunk 导航 (Monaco Editor 风格) ──
const activeHunk = ref(props.activeHunkIndex ?? -1)

/** 重置当前高亮 hunk */
function resetActiveHunk() {
  activeHunk.value = -1
}

// 计算 hunks 索引映射 (header line → hunk index)
const hunkHeaders = computed(() => {
  const headers: { lineIndex: number; hunkIndex: number }[] = []
  let hunkIdx = -1
  for (let i = 0; i < parsedLines.value.length; i++) {
    if (parsedLines.value[i].type === "header") {
      hunkIdx++
      headers.push({ lineIndex: i, hunkIndex: hunkIdx })
    }
  }
  return headers
})

const totalHunks = computed(() => hunkHeaders.value.length)

function jumpToPrevHunk() {
  if (totalHunks.value === 0) return
  if (activeHunk.value <= 0) {
    activeHunk.value = totalHunks.value - 1
  } else {
    activeHunk.value--
  }
  emit("jumpToHunk", activeHunk.value)
}

function jumpToNextHunk() {
  if (totalHunks.value === 0) return
  if (activeHunk.value >= totalHunks.value - 1) {
    activeHunk.value = 0
  } else {
    activeHunk.value++
  }
  emit("jumpToHunk", activeHunk.value)
}

function isLineInActiveHunk(lineIndex: number): boolean {
  if (activeHunk.value < 0) return false
  const start = hunkHeaders.value[activeHunk.value]?.lineIndex
  const end = activeHunk.value + 1 < totalHunks.value
    ? hunkHeaders.value[activeHunk.value + 1]?.lineIndex
    : parsedLines.value.length
  return start !== undefined && lineIndex >= start && lineIndex < end!
}

// ── 解析 hunks 为行级数据 ──
interface DiffLine {
  type: "add" | "remove" | "context" | "header"
  content: string
  oldLineNum?: number
  newLineNum?: number
}

const parsedLines = computed<DiffLine[]>(() => {
  if (!props.diff) return []
  const lines: DiffLine[] = []
  let oldLine = 0
  let newLine = 0

  for (const line of props.diff.diff_text.split("\n")) {
    if (line.startsWith("@@")) {
      // 解析行号
      const match = line.match(/@@ -(\d+),?\d* \+(\d+),?\d* @@/)
      if (match) {
        oldLine = parseInt(match[1], 10) - 1
        newLine = parseInt(match[2], 10) - 1
      }
      lines.push({ type: "header", content: line })
    } else if (line.startsWith("+") && !line.startsWith("+++")) {
      newLine++
      lines.push({ type: "add", content: line, newLineNum: newLine })
    } else if (line.startsWith("-") && !line.startsWith("---")) {
      oldLine++
      lines.push({ type: "remove", content: line, oldLineNum: oldLine })
    } else if (
      line.startsWith("---") ||
      line.startsWith("+++") ||
      line.startsWith("index ")
    ) {
      lines.push({ type: "header", content: line })
    } else {
      oldLine++
      newLine++
      lines.push({
        type: "context",
        content: line,
        oldLineNum: oldLine,
        newLineNum: newLine,
      })
    }
  }
  return lines
})

// ── 变更类型图标 ──
const changeIcon = computed(() => {
  if (!props.diff) return FileEdit
  switch (props.diff.change_type) {
    case "CREATE":
      return FilePlus
    case "DELETE":
      return FileMinus
    default:
      return FileEdit
  }
})

const changeLabel = computed(() => {
  if (!props.diff) return "修改"
  switch (props.diff.change_type) {
    case "CREATE":
      return "新建"
    case "DELETE":
      return "删除"
    default:
      return "修改"
  }
})

const changeColor = computed(() => {
  if (!props.diff) return "text-blue-400"
  switch (props.diff.change_type) {
    case "CREATE":
      return "text-emerald-400"
    case "DELETE":
      return "text-red-400"
    default:
      return "text-amber-400"
  }
})

const changeBg = computed(() => {
  if (!props.diff) return "bg-blue-500/8 border-blue-500/15"
  switch (props.diff.change_type) {
    case "CREATE":
      return "bg-emerald-500/8 border-emerald-500/15"
    case "DELETE":
      return "bg-red-500/8 border-red-500/15"
    default:
      return "bg-amber-500/8 border-amber-500/15"
  }
})

// ── 操作 ──
function copyDiff() {
  if (!props.diff) return
  navigator.clipboard.writeText(props.diff.diff_text)
}

function downloadDiff() {
  if (!props.diff) return
  const blob = new Blob([props.diff.diff_text], { type: "text/plain" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${props.diff.file_name}.diff`
  a.click()
  URL.revokeObjectURL(url)
}

// ── 语法高亮类名映射 ──
function langClass(lang: string): string {
  const map: Record<string, string> = {
    python: "language-python",
    javascript: "language-javascript",
    typescript: "language-typescript",
    tsx: "language-tsx",
    vue: "language-html",
    css: "language-css",
    html: "language-html",
    json: "language-json",
    yaml: "language-yaml",
    markdown: "language-markdown",
    sql: "language-sql",
    shell: "language-bash",
    go: "language-go",
    rust: "language-rust",
    java: "language-java",
    cpp: "language-cpp",
    c: "language-c",
    kotlin: "language-kotlin",
    swift: "language-swift",
    ruby: "language-ruby",
    php: "language-php",
    dart: "language-dart",
    graphql: "language-graphql",
    xml: "language-xml",
    toml: "language-toml",
  }
  return map[lang] || ""
}
</script>

<template>
  <div v-if="diff" :class="['rounded-xl border overflow-hidden transition-all duration-200', changeBg]">
    <!-- ── 头部：文件信息 + 变更状态 ── -->
    <div class="flex items-center justify-between px-4 py-2.5 bg-white/[0.03] border-b border-[var(--color-ide-border)]">
      <div class="flex items-center gap-2.5 min-w-0">
        <button
          v-if="collapsible"
          @click="collapsed = !collapsed"
          class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] shrink-0"
        >
          <ChevronDown v-if="!collapsed" class="w-3.5 h-3.5" />
          <ChevronRight v-else class="w-3.5 h-3.5" />
        </button>
        <component :is="changeIcon" :class="['w-4 h-4 shrink-0', changeColor]" />
        <span class="text-sm font-mono font-medium text-[var(--color-ide-text)] truncate">
          {{ diff.file_name }}
        </span>
        <span :class="['text-[11px] font-semibold px-1.5 py-0.5 rounded', changeColor, changeBg]">
          {{ changeLabel }}
        </span>
        <span class="text-[11px] text-[var(--color-ide-text-dim)] font-mono ml-1">
          <template v-if="diff.language">{{ diff.language }}</template>
        </span>
      </div>

      <!-- 统计 -->
      <div class="flex items-center gap-3 text-[11px] font-mono">
        <span v-if="diff.lines_added" class="text-emerald-400 flex items-center gap-0.5">
          <Plus class="w-3 h-3" /> {{ diff.lines_added }}
        </span>
        <span v-if="diff.lines_removed" class="text-red-400 flex items-center gap-0.5">
          <Minus class="w-3 h-3" /> {{ diff.lines_removed }}
        </span>
      </div>
    </div>

    <!-- ── 工具栏 ── -->
    <div v-if="!collapsed" class="flex items-center gap-1 px-4 py-1.5 bg-white/[0.02] border-b border-[var(--color-ide-border)]">
      <button
        @click="viewMode = 'unified'"
        :class="['p-1.5 rounded-md text-[11px] transition-colors', viewMode === 'unified' ? 'bg-white/10 text-[var(--color-ide-text)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]']"
        title="统一视图"
      >
        <AlignLeft class="w-3.5 h-3.5" />
      </button>
      <button
        @click="viewMode = 'split'"
        :class="['p-1.5 rounded-md text-[11px] transition-colors', viewMode === 'split' ? 'bg-white/10 text-[var(--color-ide-text)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]']"
        title="双栏视图"
      >
        <Columns class="w-3.5 h-3.5" />
      </button>

      <div class="w-px h-4 bg-[var(--color-ide-surface-hover)] mx-1" />

      <!-- Hunk 导航 (Monaco 风格) -->
      <button
        @click="jumpToPrevHunk"
        :disabled="totalHunks === 0"
        class="p-1.5 rounded-md text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="上一个变更 (Shift+F3)"
      >
        <ArrowUp class="w-3.5 h-3.5" />
      </button>
      <span class="text-[10px] text-[var(--color-ide-text-dim)] font-mono min-w-[36px] text-center select-none">
        {{ activeHunk >= 0 ? `${activeHunk + 1}/${totalHunks}` : `${totalHunks}` }}
      </span>
      <button
        @click="jumpToNextHunk"
        :disabled="totalHunks === 0"
        class="p-1.5 rounded-md text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="下一个变更 (F3)"
      >
        <ArrowDown class="w-3.5 h-3.5" />
      </button>

      <div class="w-px h-4 bg-[var(--color-ide-surface-hover)] mx-1" />

      <!-- Hunk 快速跳转圆点 (类似 Monaco diff navigator) -->
      <div v-if="totalHunks > 1" class="flex items-center gap-1 mr-1">
        <button
          v-for="h in totalHunks"
          :key="h"
          @click="activeHunk = h - 1; emit('jumpToHunk', h - 1)"
          :class="[
            'w-3.5 h-3.5 rounded-full transition-all duration-200',
            activeHunk === h - 1
              ? 'bg-brand-400 scale-110 shadow-sm shadow-brand-500/30'
              : 'bg-[var(--color-ide-surface-hover)] hover:bg-[var(--color-ide-surface-active)]'
          ]"
          :title="`跳转到变更 ${h}`"
        />
      </div>

      <div class="w-px h-4 bg-[var(--color-ide-surface-hover)] mx-1" />

      <button
        @click="copyDiff"
        class="p-1.5 rounded-md text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
        title="复制 diff"
      >
        <Copy class="w-3.5 h-3.5" />
      </button>
      <button
        @click="downloadDiff"
        class="p-1.5 rounded-md text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
        title="下载 .diff"
      >
        <Download class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- ── Diff 内容 ── -->
    <div v-if="!collapsed" class="overflow-x-auto font-mono text-[13px] leading-[1.55]">
      <!-- Unified 视图 -->
      <table v-if="viewMode === 'unified'" class="w-full border-collapse">
        <tbody>
          <tr
            v-for="(line, i) in parsedLines"
            :key="i"
            :class="[
              line.type === 'add' ? 'bg-emerald-500/[0.08]' :
              line.type === 'remove' ? 'bg-red-500/[0.08]' :
              line.type === 'header' ? 'bg-blue-500/[0.06]' : '',
              isLineInActiveHunk(i) ? '!bg-brand-500/[0.06] outline outline-[0.5px] outline-brand-500/20' : ''
            ]"
            :style="isLineInActiveHunk(i) ? { boxShadow: 'inset 4px 0 0 var(--brand-400, #6366f1)' } : undefined"
          >
            <!-- 行号 -->
            <td v-if="line.type === 'header'" colspan="3" class="py-0.5 px-4 text-blue-400/70 text-xs font-semibold">
              {{ line.content }}
            </td>
            <template v-else>
              <td class="w-10 text-right px-2 py-0 text-[var(--color-ide-text-dim)] select-none border-r border-[var(--color-ide-border)] text-xs">
                {{ line.oldLineNum || '' }}
              </td>
              <td class="w-10 text-right px-2 py-0 text-[var(--color-ide-text-dim)] select-none border-r border-[var(--color-ide-border)] text-xs">
                {{ line.newLineNum || '' }}
              </td>
              <td class="w-4 text-center select-none text-xs py-0"
                :class="line.type === 'add' ? 'text-emerald-500' : line.type === 'remove' ? 'text-red-500' : 'text-gray-800'">
                {{ line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' ' }}
              </td>
              <td class="px-3 py-0 whitespace-pre-wrap"
                :class="line.type === 'add' ? 'text-emerald-200/80' : line.type === 'remove' ? 'text-red-200/80' : 'text-[var(--color-ide-text)]'">
                {{ line.content.slice(1) }}
              </td>
            </template>
          </tr>
        </tbody>
      </table>

      <!-- Split 视图 -->
      <table v-else class="w-full border-collapse">
        <tbody>
          <tr
            v-for="(line, i) in parsedLines"
            :key="i"
            :class="[line.type === 'header' ? 'bg-blue-500/[0.06]' : '']"
          >
            <template v-if="line.type === 'header'">
              <td colspan="4" class="py-0.5 px-4 text-blue-400/70 text-xs font-semibold">{{ line.content }}</td>
            </template>
            <template v-else-if="line.type === 'remove'">
              <td class="w-10 text-right px-2 py-0 text-[var(--color-ide-text-dim)] select-none border-r border-[var(--color-ide-border)] text-xs">{{ line.oldLineNum }}</td>
              <td class="px-3 py-0 bg-red-500/[0.08] whitespace-pre-wrap text-red-200/80" colspan="3">{{ line.content.slice(1) }}</td>
            </template>
            <template v-else-if="line.type === 'add'">
              <td class="w-10 px-2 py-0 text-[var(--color-ide-text-dim)] select-none border-r border-[var(--color-ide-border)] text-xs" />
              <td class="px-3 py-0 bg-emerald-500/[0.08] whitespace-pre-wrap text-emerald-200/80" colspan="3">{{ line.content.slice(1) }}</td>
            </template>
            <template v-else>
              <td class="w-10 text-right px-2 py-0 text-[var(--color-ide-text-dim)] select-none border-r border-[var(--color-ide-border)] text-xs">{{ line.oldLineNum }}</td>
              <td class="px-3 py-0 whitespace-pre-wrap text-[var(--color-ide-text)]">{{ line.content }}</td>
              <td class="w-px bg-[var(--color-ide-surface-hover)]" />
              <td class="w-10 text-right px-2 py-0 text-[var(--color-ide-text-dim)] select-none border-r border-[var(--color-ide-border)] text-xs">{{ line.newLineNum }}</td>
              <td class="px-3 py-0 whitespace-pre-wrap text-[var(--color-ide-text)]">{{ line.content }}</td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 折叠时只显示摘要 -->
    <div v-if="collapsed" class="px-4 py-2 text-xs text-[var(--color-ide-text-dim)]">
      +{{ diff.lines_added }} −{{ diff.lines_removed }} {{ diff.lines_added + diff.lines_removed }} 行变更
    </div>
  </div>
</template>
