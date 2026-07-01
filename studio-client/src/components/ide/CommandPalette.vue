<template>
  <Teleport to="body">
    <Transition name="command-palette">
      <div
        v-if="visible"
        class="fixed inset-0 z-[9999] flex items-start justify-center pt-[12vh]"
        @click.self="close"
      >
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" />
        <div
          ref="panelRef"
          class="relative w-full max-w-2xl bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-xl shadow-2xl shadow-black/60 overflow-hidden"
          @click.stop
        >
          <!-- 🔍 Search Bar -->
          <div class="flex items-center px-5 py-4 border-b border-[var(--color-ide-border)]">
            <Search :size="18" class="text-[var(--color-ide-accent)] shrink-0 mr-3" />
            <input
              ref="inputRef"
              v-model="q"
              type="text"
              :placeholder="modePrefix + '输入命令或搜索...'"
              class="flex-1 bg-transparent text-sm text-[var(--color-ide-text)] outline-none placeholder:text-[var(--color-ide-text-dim)] font-mono"
              @input="onInput"
              @keydown.down.prevent="selectNext"
              @keydown.up.prevent="selectPrev"
              @keydown.enter="executeSelected"
              @keydown.escape="close"
            />
            <kbd
              class="hidden sm:inline-flex items-center gap-0.5 text-[11px] text-[var(--color-ide-text-dim)] bg-[var(--color-ide-bg-tertiary)] px-2 py-0.5 rounded-md border border-[var(--color-ide-border)] font-mono"
            >ESC</kbd>
          </div>

          <!-- 🏷 Category Tabs (when not searching) -->
          <div
            v-if="hasCategories && !q"
            class="flex items-center gap-1 px-4 py-2 overflow-x-auto border-b border-[var(--color-ide-border)] scrollbar-thin"
          >
            <button
              v-for="c in categoryList"
              :key="c"
              :class="[
                'px-3 py-1.5 text-xs rounded-lg whitespace-nowrap transition-all duration-150 font-medium',
                activeCat === c || (!activeCat && c === '全部')
                  ? 'bg-[var(--color-ide-accent)] text-white shadow-sm shadow-[var(--color-ide-accent)]/25'
                  : 'text-[var(--color-ide-text-secondary)] hover:bg-[var(--color-ide-hover)] hover:text-[var(--color-ide-text)]',
              ]"
              @click="activeCat = c === '全部' ? null : c; selectedIdx = 0"
            >
              {{ c }}
            </button>
          </div>

          <!-- 📋 Results List -->
          <div ref="resultsRef" class="max-h-[420px] overflow-y-auto py-1.5 scrollbar-thin">
            <!-- Recent Commands Header (Zed 风格) -->
            <div
              v-if="recentCommands.length > 0 && !q && !activeCat"
              class="px-5 pt-2 pb-1"
            >
              <span class="text-[10px] font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-widest">最近使用</span>
            </div>

            <button
              v-for="(item, idx) in filteredResults"
              :key="item.id + item.category"
              :ref="(el: any) => setItemRef(idx, el)"
              :class="[
                'w-full flex items-center px-5 py-3 transition-colors text-left group',
                selectedIdx === idx
                  ? 'bg-[var(--color-ide-selection)]'
                  : 'hover:bg-[var(--color-ide-hover)]',
              ]"
              @mouseenter="selectedIdx = idx"
              @click="execute(item)"
            >
              <!-- Icon -->
              <div
                class="w-9 h-9 mr-3 flex items-center justify-center rounded-lg shrink-0"
                :class="selectedIdx === idx
                  ? 'bg-[var(--color-ide-accent)]/15'
                  : 'bg-[var(--color-ide-bg-tertiary)]'"
              >
                <component
                  :is="getIconComponent(item.icon)"
                  :size="15"
                  :class="selectedIdx === idx
                    ? 'text-[var(--color-ide-accent)]'
                    : 'text-[var(--color-ide-text-secondary)]'"
                />
              </div>

              <!-- Text Content -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <!-- 🆕 高亮匹配文本 -->
                  <span
                    class="text-sm text-[var(--color-ide-text)] truncate"
                    v-html="highlightMatch(item.title)"
                  />
                  <!-- Score badge -->
                  <span
                    v-if="item.score && item.score >= 60 && q"
                    class="text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-accent)] font-medium shrink-0"
                  >{{ Math.round(item.score) }}%</span>
                  <!-- 🆕 最近使用标记 -->
                  <span
                    v-if="item._recent"
                    class="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-500/10 text-purple-400 font-medium shrink-0"
                  >最近</span>
                </div>
                <!-- Subtitle: category + id -->
                <span class="text-[11px] text-[var(--color-ide-text-dim)] truncate block mt-0.5">
                  {{ item.category }} <span class="opacity-50">·</span> {{ item.id }}
                </span>
              </div>

              <!-- Keyboard shortcut -->
              <kbd
                v-if="item.key"
                class="hidden sm:inline-flex items-center gap-0.5 text-[11px] text-[var(--color-ide-text-dim)] bg-[var(--color-ide-bg-tertiary)] px-2 py-1 rounded-md border border-[var(--color-ide-border)] ml-3 shrink-0 font-mono"
              >{{ formatKeybinding(item.key) }}</kbd>
            </button>

            <!-- Empty State -->
            <div
              v-if="filteredResults.length === 0"
              class="px-5 py-12 text-center"
            >
              <Inbox :size="36" class="mx-auto mb-3 opacity-25 text-[var(--color-ide-text-dim)]" />
              <p class="text-sm text-[var(--color-ide-text-dim)] mb-1">
                {{ q ? `没有找到 "${q}"` : '输入关键词搜索命令...' }}
              </p>
              <p class="text-[11px] text-[var(--color-ide-text-dim)]/60">
                {{ q ? '尝试不同关键词或首字母缩写' : '使用 ↑↓ 导航 · Enter 执行' }}
              </p>
            </div>
          </div>

          <!-- 🦶 Footer -->
          <div
            v-if="filteredResults.length > 0"
            class="sticky bottom-0 px-5 py-2.5 bg-[var(--color-ide-surface)]/95 backdrop-blur-sm border-t border-[var(--color-ide-border)] text-[11px] text-[var(--color-ide-text-dim)] flex justify-between"
          >
            <span>{{ filteredResults.length }} 个命令</span>
            <span class="flex items-center gap-2">
              <span class="flex items-center gap-1">
                <kbd class="text-[10px] px-1 rounded bg-[var(--color-ide-bg-tertiary)] border border-[var(--color-ide-border)]">↑↓</kbd> 选择
              </span>
              <span class="flex items-center gap-1">
                <kbd class="text-[10px] px-1 rounded bg-[var(--color-ide-bg-tertiary)] border border-[var(--color-ide-border)]">↵</kbd> 执行
              </span>
              <span class="flex items-center gap-1">
                <kbd class="text-[10px] px-1 rounded bg-[var(--color-ide-bg-tertiary)] border border-[var(--color-ide-border)]">ESC</kbd> 关闭
              </span>
            </span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * CommandPalette.vue — Zed 风格全局命令面板增强版
 *
 * 参考: Zed command_palette (Ctrl+Shift+P 全局命令搜索)
 *
 * 功能:
 *   - 模糊搜索 + 首字母缩写匹配 (Zed 风格 "JFP" → "Just File Picker")
 *   - 最近使用命令优先展示
 *   - 匹配文本高亮显示
 *   - 分类标签页筛选
 *   - 键盘导航 (↑↓/Enter/Escape)
 */
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Bug,
  CheckCircle2,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  CircleDot,
  ClipboardPaste,
  Code,
  Copy,
  Download,
  Eye,
  FilePlus,
  FileSearch,
  FileText,
  FolderOpen,
  GitBranch,
  GitBranchPlus,
  GitCommit,
  Inbox,
  Layers,
  Lightbulb,
  MessageSquare,
  PanelBottomClose,
  PanelLeftClose,
  Pause,
  Play,
  Plus,
  Redo,
  RotateCcw,
  Save,
  Search,
  Settings,
  SkipForward,
  Sparkles,
  Square,
  Terminal,
  TestTube2,
  Undo2,
  Variable,
  Wand2,
  Zap,
  ZoomIn,
  ZoomOut,
} from "lucide-vue-next"
import { computed, nextTick, ref, watch } from "vue"
import { usePlugins } from "@/composables/usePlugins"
import {
  type CommandPaletteItem,
  useShortcuts,
} from "@/composables/useShortcuts"

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{
  "update:visible": [val: boolean]
  execute: [cmdId: string]
}>()

const { getFiltered, getCategories, getRecent } = useShortcuts()
const { allCommands } = usePlugins()

const q = ref("")
const selectedIdx = ref(0)
const activeCat = ref<string | null>(null)
const inputRef = ref<HTMLInputElement>()
const panelRef = ref<HTMLDivElement>()
const resultsRef = ref<HTMLDivElement>()
const itemRefs = new Map<number, HTMLElement>()

// 🆕 Mode prefix (">" for command mode, "" for search mode)
const modePrefix = computed(() => (q.value.startsWith(">") ? ">" : ""))

// 🆕 Recent commands
const recentCommands = computed(() => getRecent())

// Categories
const hasCategories = computed(() => categoryList.value.length > 1)
const categoryList = computed(() => ["全部", ...getCategories()])

// 🆕 高亮匹配文本
function highlightMatch(text: string): string {
  if (!q.value.trim()) return escapeHtml(text)
  const ql = q.value.trim().toLowerCase()
  const tl = text.toLowerCase()
  let result = ""
  let i = 0
  while (i < tl.length) {
    // Try to find longest match starting at position i
    let bestMatchLen = 0
    for (let len = ql.length; len >= 1; len--) {
      const sub = ql.substring(0, len)
      if (tl.substring(i, i + len) === sub) {
        bestMatchLen = len
        break
      }
    }
    if (bestMatchLen > 0) {
      const matched = text.substring(i, i + bestMatchLen)
      result += `<mark class="text-[var(--color-ide-accent)] bg-[var(--color-ide-accent)]/10 rounded-sm px-0.5 font-semibold">${escapeHtml(matched)}</mark>`
      i += bestMatchLen
    } else {
      result += escapeHtml(text[i])
      i++
    }
  }
  return result
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

// Filtered results
const filteredResults = computed<(CommandPaletteItem & { _recent?: boolean })[]>(() => {
  const sc = getFiltered(q.value, activeCat.value) as (CommandPaletteItem & { _recent?: boolean })[]

  // 🆕 Merge plugin commands
  const pc: (CommandPaletteItem & { _recent?: boolean })[] = (allCommands.value || []).map((c: any) => ({
    id: c.id,
    title: c.title,
    category: c.category || "插件",
    key: "",
    icon: c.icon || "Puzzle",
    score: 0,
    keywords: `${c.title} ${c.category}`.toLowerCase(),
  }))

  let fp = pc
  if (q.value) {
    const ql = q.value.toLowerCase()
    fp = pc
      .filter((p: any) => p.keywords.includes(ql))
      .map((p: any) => ({ ...p, score: 60 }))
  }

  return [...sc, ...fp]
})

// Methods
function close() {
  emit("update:visible", false)
}

function onInput() {
  selectedIdx.value = 0
}

function selectNext() {
  if (filteredResults.value.length) {
    selectedIdx.value = (selectedIdx.value + 1) % filteredResults.value.length
    scrollToSelected()
  }
}

function selectPrev() {
  if (filteredResults.value.length) {
    selectedIdx.value =
      selectedIdx.value <= 0
        ? filteredResults.value.length - 1
        : selectedIdx.value - 1
    scrollToSelected()
  }
}

function executeSelected() {
  if (filteredResults.value[selectedIdx.value]) {
    execute(filteredResults.value[selectedIdx.value])
  }
}

function execute(item: CommandPaletteItem) {
  emit("execute", item.id)
  close()
}

function scrollToSelected() {
  nextTick(() => {
    const el = itemRefs.get(selectedIdx.value)
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" })
  })
}

function setItemRef(i: number, el: any) {
  el ? itemRefs.set(i, el) : itemRefs.delete(i)
}

// Icon registry
const iconMap: Record<string, any> = {
  FilePlus,
  FolderOpen,
  Save,
  Undo2,
  Redo,
  Copy,
  ClipboardPaste,
  PanelLeftClose,
  PanelBottomClose,
  ZoomIn,
  ZoomOut,
  FileSearch,
  Terminal,
  MessageSquare,
  Settings,
  GitBranch,
  Code,
  Sparkles,
  Play,
  Square,
  Pause,
  ChevronsRight,
  ChevronRight,
  ChevronsLeft,
  SkipForward,
  CircleDot,
  Variable,
  Eye,
  Layers,
  Lightbulb,
  Wand2,
  TestTube2,
  Bug,
  Zap,
  FileText,
  Plus,
  Download,
  CheckCircle2,
  ArrowUpFromLine,
  ArrowDownToLine,
  GitBranchPlus,
  GitCommit,
  RotateCcw,
  Search,
}

function getIconComponent(icon?: string): any {
  return iconMap[icon ?? ""] || Search
}

// 🆕 Format keybinding for display (Zed style: system-aware modifiers)
function formatKeybinding(k: string): string {
  const isMac = navigator.platform.toUpperCase().includes("MAC")
  return k
    .replace(/Ctrl/g, isMac ? "⌃" : "Ctrl")
    .replace(/Cmd/g, "⌘")
    .replace(/Shift/g, isMac ? "⇧" : "Shift")
    .replace(/Alt/g, isMac ? "⌥" : "Alt")
    .replace(/\+/g, "+")
}

// Watch visibility
watch(
  () => props.visible,
  (val: boolean) => {
    if (val) {
      q.value = ""
      selectedIdx.value = 0
      activeCat.value = null
      nextTick(() => inputRef.value?.focus())
    }
  },
)
</script>

<style scoped>
.command-palette-enter-active,
.command-palette-leave-active {
  transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}
.command-palette-enter-from {
  opacity: 0;
  transform: translateY(-12px) scale(0.97);
}
.command-palette-leave-to {
  opacity: 0;
  transform: translateY(-8px) scale(0.98);
}

/* Scrollbar */
.scrollbar-thin::-webkit-scrollbar {
  width: 4px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background: var(--color-ide-border);
  border-radius: 2px;
}
</style>
