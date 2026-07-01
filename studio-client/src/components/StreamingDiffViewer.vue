<script setup lang="ts">
/**
 * StreamingDiffViewer.vue — Zed 风格流式 Diff 渲染器
 *
 * 参考: Zed crates/agent/streaming_diff.rs
 *
 * 特性:
 *   1. 字符级打字机效果 (逐字渲染新增内容)
 *   2. 实时颜色标注 (绿=新增, 红=删除, 黄=当前写入位置)
 *   3. 流式接收部分 diff 文本 (SSE chunk → 增量解析)
 *   4. 闪烁光标指示当前写入位置
 *   5. 支持 unified/split 双模式
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
  Pause,
  Play,
  Plus,
} from "lucide-vue-next"
import { computed, ref, watch, onBeforeUnmount } from "vue"

const props = defineProps<{
  /** 文件名 */
  fileName: string
  /** 🆕 流式模式: 部分 diff 文本 (会持续增长) */
  streamingDiff?: string
  /** 静态模式: 完整 diff 文本 */
  fullDiff?: string
  /** 变更类型 */
  changeType?: "CREATE" | "DELETE" | "MODIFY"
  /** 编程语言 */
  language?: string
  /** 总行数统计 (流式模式下外部提供) */
  linesAdded?: number
  linesRemoved?: number
  /** 打字机速度 (ms/字符), 0 = 全部立即显示 */
  typewriterSpeed?: number
  /** 是否正在流式接收数据 */
  isStreaming?: boolean
}>()

const emit = defineEmits<{
  (e: "close"): void
  (e: "apply"): void
  (e: "jumpToHunk", index: number): void
}>()

// ── 视图模式 ──
type ViewMode = "unified" | "split"
const viewMode = ref<ViewMode>("unified")
const collapsed = ref(false)

// ── 打字机状态 (Zed 风格) ──
const revealedLineCount = ref(0)
const revealedCharCount = ref(0)
const isTyping = ref(false)
let typewriterTimer: ReturnType<typeof setInterval> | null = null

// ── Hunk 导航 ──
const activeHunk = ref(-1)

// ── 数据源 ──
const diffText = computed(() => props.streamingDiff ?? props.fullDiff ?? "")
const isLiveStream = computed(() => props.isStreaming === true)

// ── 解析 hunks 为行级数据 ──
interface DiffLine {
  type: "add" | "remove" | "context" | "header"
  content: string
  oldLineNum?: number
  newLineNum?: number
}

const parsedLines = computed<DiffLine[]>(() => {
  const text = diffText.value
  if (!text) return []
  const lines: DiffLine[] = []
  let oldLine = 0
  let newLine = 0

  for (const line of text.split("\n")) {
    if (line.startsWith("@@")) {
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

// ── 🆕 打字机控制的显示行 ──
const visibleLines = computed(() => {
  const all = parsedLines.value
  if (props.typewriterSpeed === 0 || !isLiveStream.value) {
    return all // 全量显示
  }
  const count = revealedLineCount.value
  if (count >= all.length) return all

  const visible = all.slice(0, count + 1)
  // 最后一行可能只显示部分字符
  if (visible.length > 0 && count < all.length) {
    const lastLine = { ...all[count] }
    const maxChars = revealedCharCount.value
    if (lastLine.content.length > maxChars + 1) {
      lastLine.content = lastLine.content.slice(0, maxChars + 1)
    }
    visible[visible.length - 1] = lastLine
  }
  return visible
})

// ── 🆕 当前写入位置 (Zed 黄色光标) ──
const writePositionLine = computed(() => {
  if (!isLiveStream.value || props.typewriterSpeed === 0) return -1
  if (revealedLineCount.value >= parsedLines.value.length) return -1
  return revealedLineCount.value
})

// ── 🆕 打字机引擎 ──
function startTypewriter() {
  if (typewriterTimer || !isLiveStream.value || props.typewriterSpeed === 0) return
  isTyping.value = true
  const speed = props.typewriterSpeed ?? 30

  typewriterTimer = setInterval(() => {
    const all = parsedLines.value
    if (revealedLineCount.value >= all.length) {
      stopTypewriter()
      return
    }

    const currentLine = all[revealedLineCount.value]
    revealedCharCount.value++

    // 当前行显示完毕 → 进入下一行
    if (revealedCharCount.value >= currentLine.content.length) {
      revealedLineCount.value++
      revealedCharCount.value = 0
    }
  }, speed)
}

function stopTypewriter() {
  if (typewriterTimer) {
    clearInterval(typewriterTimer)
    typewriterTimer = null
  }
  isTyping.value = false
  // 揭示全部
  revealedLineCount.value = parsedLines.value.length
  revealedCharCount.value = 0
}

function toggleTypewriter() {
  if (isTyping.value) stopTypewriter()
  else startTypewriter()
}

// 流式更新时重置打字机
watch(
  () => diffText.value,
  () => {
    if (isLiveStream.value && props.typewriterSpeed !== 0) {
      // 流式到达新数据 → 确保打字机跟上
      if (!isTyping.value) startTypewriter()
    } else {
      revealedLineCount.value = parsedLines.value.length
    }
  },
)

watch(
  () => props.isStreaming,
  (streaming) => {
    if (!streaming) {
      // 流结束 → 揭示全部
      stopTypewriter()
      revealedLineCount.value = parsedLines.value.length
    } else if (streaming && props.typewriterSpeed !== 0) {
      startTypewriter()
    }
  },
)

onBeforeUnmount(() => stopTypewriter())

// ── Hunk 计算 ──
const hunkHeaders = computed(() => {
  const headers: { lineIndex: number; hunkIndex: number }[] = []
  let hunkIdx = -1
  for (let i = 0; i < visibleLines.value.length; i++) {
    if (visibleLines.value[i].type === "header") {
      hunkIdx++
      headers.push({ lineIndex: i, hunkIndex: hunkIdx })
    }
  }
  return headers
})

const totalHunks = computed(() => hunkHeaders.value.length)

function jumpToPrevHunk() {
  if (totalHunks.value === 0) return
  activeHunk.value = activeHunk.value <= 0 ? totalHunks.value - 1 : activeHunk.value - 1
  emit("jumpToHunk", activeHunk.value)
}

function jumpToNextHunk() {
  if (totalHunks.value === 0) return
  activeHunk.value = activeHunk.value >= totalHunks.value - 1 ? 0 : activeHunk.value + 1
  emit("jumpToHunk", activeHunk.value)
}

function isLineInActiveHunk(lineIndex: number): boolean {
  if (activeHunk.value < 0 || totalHunks.value === 0) return false
  const start = hunkHeaders.value[activeHunk.value]?.lineIndex
  const end = activeHunk.value + 1 < totalHunks.value
    ? hunkHeaders.value[activeHunk.value + 1]?.lineIndex
    : visibleLines.value.length
  return start !== undefined && lineIndex >= start && lineIndex < end!
}

// ── 图标 ──
const changeIcon = computed(() => {
  switch (props.changeType) {
    case "CREATE": return FilePlus
    case "DELETE": return FileMinus
    default: return FileEdit
  }
})

const changeLabel = computed(() => {
  switch (props.changeType) {
    case "CREATE": return "新建"
    case "DELETE": return "删除"
    default: return "修改"
  }
})

const changeColor = computed(() => {
  switch (props.changeType) {
    case "CREATE": return "text-emerald-400"
    case "DELETE": return "text-red-400"
    default: return "text-amber-400"
  }
})

const changeBg = computed(() => {
  switch (props.changeType) {
    case "CREATE": return "bg-emerald-500/8 border-emerald-500/15"
    case "DELETE": return "bg-red-500/8 border-red-500/15"
    default: return "bg-amber-500/8 border-amber-500/15"
  }
})

// ── 操作 ──
function copyDiff() {
  navigator.clipboard.writeText(diffText.value)
}

function downloadDiff() {
  const blob = new Blob([diffText.value], { type: "text/plain" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${props.fileName}.diff`
  a.click()
  URL.revokeObjectURL(url)
}

// ── 流式状态指示 ──
const streamStats = computed(() => {
  const all = parsedLines.value
  const visible = visibleLines.value
  if (!isLiveStream.value) return null
  return {
    totalLines: all.length,
    visibleLines: visible.length,
    pct: all.length > 0 ? Math.round((visible.length / all.length) * 100) : 0,
  }
})
</script>

<template>
  <div :class="['rounded-xl border overflow-hidden transition-all duration-200', changeBg]">
    <!-- ── 头部 ── -->
    <div class="flex items-center justify-between px-4 py-2.5 bg-white/[0.03] border-b border-[var(--color-ide-border)]">
      <div class="flex items-center gap-2.5 min-w-0">
        <button
          @click="collapsed = !collapsed"
          class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] shrink-0"
        >
          <ChevronDown v-if="!collapsed" class="w-3.5 h-3.5" />
          <ChevronRight v-else class="w-3.5 h-3.5" />
        </button>
        <component :is="changeIcon" :class="['w-4 h-4 shrink-0', changeColor]" />
        <span class="text-sm font-mono font-medium text-[var(--color-ide-text)] truncate">
          {{ fileName }}
        </span>
        <span :class="['text-[11px] font-semibold px-1.5 py-0.5 rounded', changeColor, changeBg]">
          {{ changeLabel }}
        </span>
        <!-- 🆕 流式状态指示器 -->
        <span
          v-if="isLiveStream"
          class="flex items-center gap-1 text-[10px]"
        >
          <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
            <span class="relative inline-flex rounded-full h-2 w-2 bg-amber-500" />
          </span>
          <span class="text-amber-400/80 font-medium">
            {{ isTyping ? '打字中...' : '接收中...' }}
          </span>
          <span v-if="streamStats" class="text-[var(--color-ide-text-dim)] ml-1">
            {{ streamStats.pct }}%
          </span>
        </span>
      </div>

      <!-- 统计 -->
      <div class="flex items-center gap-3 text-[11px] font-mono">
        <span v-if="linesAdded" class="text-emerald-400 flex items-center gap-0.5">
          <Plus class="w-3 h-3" /> {{ linesAdded }}
        </span>
        <span v-if="linesRemoved" class="text-red-400 flex items-center gap-0.5">
          <Minus class="w-3 h-3" /> {{ linesRemoved }}
        </span>
      </div>
    </div>

    <!-- ── 工具栏 ── -->
    <div v-if="!collapsed" class="flex items-center gap-1 px-4 py-1.5 bg-white/[0.02] border-b border-[var(--color-ide-border)]">
      <button
        @click="viewMode = 'unified'"
        :class="['p-1.5 rounded-md text-[11px] transition-colors', viewMode === 'unified' ? 'bg-white/10 text-[var(--color-ide-text)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]']"
      >
        <AlignLeft class="w-3.5 h-3.5" />
      </button>
      <button
        @click="viewMode = 'split'"
        :class="['p-1.5 rounded-md text-[11px] transition-colors', viewMode === 'split' ? 'bg-white/10 text-[var(--color-ide-text)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]']"
      >
        <Columns class="w-3.5 h-3.5" />
      </button>

      <!-- 🆕 打字机控制 -->
      <div v-if="isLiveStream && typewriterSpeed !== 0" class="w-px h-4 bg-[var(--color-ide-surface-hover)] mx-1" />
      <button
        v-if="isLiveStream && typewriterSpeed !== 0"
        @click="toggleTypewriter"
        class="p-1.5 rounded-md text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
        :title="isTyping ? '暂停动画' : '恢复动画'"
      >
        <Pause v-if="isTyping" class="w-3.5 h-3.5 text-amber-400" />
        <Play v-else class="w-3.5 h-3.5" />
      </button>

      <div class="w-px h-4 bg-[var(--color-ide-surface-hover)] mx-1" />

      <!-- Hunk 导航 -->
      <button
        @click="jumpToPrevHunk"
        :disabled="totalHunks === 0"
        class="p-1.5 rounded-md text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
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
      >
        <ArrowDown class="w-3.5 h-3.5" />
      </button>

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
    <div v-if="!collapsed" class="overflow-x-auto font-mono text-[13px] leading-[1.55] max-h-[600px] overflow-y-auto scrollbar-thin">
      <!-- Unified 视图 -->
      <table v-if="viewMode === 'unified'" class="w-full border-collapse">
        <tbody>
          <tr
            v-for="(line, i) in visibleLines"
            :key="i"
            :class="[
              line.type === 'add' ? 'bg-emerald-500/[0.08]' :
              line.type === 'remove' ? 'bg-red-500/[0.08]' :
              line.type === 'header' ? 'bg-blue-500/[0.06]' : '',
              isLineInActiveHunk(i) ? '!bg-brand-500/[0.06] ring-1 ring-inset ring-brand-500/20' : '',
              // 🆕 当前写入位置 (Zed 黄色光标)
              i === writePositionLine ? '!bg-amber-500/[0.1] ring-1 ring-inset ring-amber-400/30' : '',
            ]"
          >
            <template v-if="line.type === 'header'">
              <td colspan="3" class="py-0.5 px-4 text-blue-400/70 text-xs font-semibold">
                {{ line.content }}
              </td>
            </template>
            <template v-else>
              <td class="w-10 text-right px-2 py-0 text-[var(--color-ide-text-dim)] select-none border-r border-[var(--color-ide-border)] text-xs">
                {{ line.oldLineNum || '' }}
              </td>
              <td class="w-10 text-right px-2 py-0 text-[var(--color-ide-text-dim)] select-none border-r border-[var(--color-ide-border)] text-xs">
                {{ line.newLineNum || '' }}
              </td>
              <td
                class="w-4 text-center select-none text-xs py-0"
                :class="line.type === 'add' ? 'text-emerald-500' : line.type === 'remove' ? 'text-red-500' : 'text-gray-800'"
              >
                {{ line.type === 'add' ? '+' : line.type === 'remove' ? '-' : ' ' }}
              </td>
              <td
                class="px-3 py-0 whitespace-pre-wrap relative"
                :class="line.type === 'add' ? 'text-emerald-200/80' : line.type === 'remove' ? 'text-red-200/80' : 'text-[var(--color-ide-text)]'"
              >
                <span
                  :class="[
                    line.type === 'add' && i === writePositionLine
                      ? 'typewriter-reveal'
                      : '',
                  ]"
                >{{ line.content.slice(1) }}</span>
                <!-- 🆕 闪烁光标 (Zed 风格) -->
                <span
                  v-if="i === writePositionLine && isLiveStream"
                  class="inline-block w-[2px] h-[1.1em] bg-amber-400 align-text-bottom ml-[1px] animate-pulse"
                />
              </td>
            </template>
          </tr>
        </tbody>
      </table>

      <!-- Split 视图 -->
      <table v-else class="w-full border-collapse">
        <tbody>
          <tr
            v-for="(line, i) in visibleLines"
            :key="i"
            :class="[
              line.type === 'header' ? 'bg-blue-500/[0.06]' : '',
              i === writePositionLine ? '!bg-amber-500/[0.1]' : '',
            ]"
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
              <td
                class="px-3 py-0 bg-emerald-500/[0.08] whitespace-pre-wrap text-emerald-200/80 relative"
                colspan="3"
              >
                {{ line.content.slice(1) }}
                <span
                  v-if="i === writePositionLine && isLiveStream"
                  class="inline-block w-[2px] h-[1.1em] bg-amber-400 align-text-bottom ml-[1px] animate-pulse"
                />
              </td>
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

    <!-- 折叠摘要 -->
    <div v-if="collapsed" class="px-4 py-2 text-xs text-[var(--color-ide-text-dim)]">
      +{{ linesAdded ?? 0 }} −{{ linesRemoved ?? 0 }} {{ (linesAdded ?? 0) + (linesRemoved ?? 0) }} 行变更
    </div>
  </div>
</template>

<style scoped>
/* 🆕 打字机渐入动画 (Zed 风格) */
.typewriter-reveal {
  animation: typewriterFadeIn 0.3s ease-out;
}

@keyframes typewriterFadeIn {
  from {
    opacity: 0.4;
    filter: blur(1px);
  }
  to {
    opacity: 1;
    filter: blur(0);
  }
}

/* Scrollbar */
.scrollbar-thin::-webkit-scrollbar {
  width: 4px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 2px;
}
</style>
