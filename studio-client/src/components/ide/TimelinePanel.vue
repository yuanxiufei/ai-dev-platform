<script setup lang="ts">
/**
 * TimelinePanel — VS Code Timeline View (本地文件历史)
 *
 * 功能对标 VS Code Timeline:
 *   - 文件本地保存点 (自动快照)
 *   - Git 提交历史时间线
 *   - 时间分组: 今天/昨天/本周/更早
 *   - 文件内容对比恢复
 *   - 自动保存快照触发器
 */
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from "vue"
import { Clock, GitCommit, Save, FileText, ChevronRight, History, ArrowLeftRight, ArrowUpCircle, Check, X } from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"

const store = useIDEStore()

// ── Timeline 条目 ──
interface TimelineEntry {
  id: string
  type: "auto-save" | "git-commit" | "manual-save" | "file-save"
  timestamp: number
  label: string
  description: string
  file?: string
  commitHash?: string
  author?: string
  snapshot?: string
}

// ── 模拟时间线数据 ──
const entries = ref<TimelineEntry[]>([
  {
    id: "tl-1",
    type: "auto-save",
    timestamp: Date.now() - 5 * 60 * 1000,
    label: "自动保存",
    description: "编辑器自动保存",
    file: "App.vue",
  },
  {
    id: "tl-2",
    type: "git-commit",
    timestamp: Date.now() - 25 * 60 * 1000,
    label: "fix: 修复Sidebar布局",
    description: "修复ActivityBar与Sidebar分离后的布局问题",
    file: "src/components/ide/Sidebar.vue",
    commitHash: "a1b2c3d",
    author: "reginyuan",
  },
  {
    id: "tl-3",
    type: "file-save",
    timestamp: Date.now() - 60 * 60 * 1000,
    label: "文件保存",
    description: "保存 ActivityBar.vue",
    file: "src/components/ide/ActivityBar.vue",
  },
  {
    id: "tl-4",
    type: "git-commit",
    timestamp: Date.now() - 2 * 60 * 60 * 1000,
    label: "feat: Session 27 VS Code面板补齐",
    description: "新增SearchPanel/ExtensionsPanel/TestingPanel/ActivityBar独立分离",
    commitHash: "e4f5g6h",
    author: "reginyuan",
  },
  {
    id: "tl-5",
    type: "auto-save",
    timestamp: Date.now() - 3 * 60 * 60 * 1000,
    label: "自动保存",
    description: "编辑器自动保存",
    file: "src/stores/useTerminalStore.ts",
  },
  {
    id: "tl-6",
    type: "git-commit",
    timestamp: Date.now() - 24 * 60 * 60 * 1000,
    label: "feat: Session 26 VSCode功能对标",
    description: "PeekView/QuickDiff/ChatOutlinePanel/GlobalSearch增强",
    commitHash: "i7j8k9l",
    author: "reginyuan",
  },
  {
    id: "tl-7",
    type: "file-save",
    timestamp: Date.now() - 26 * 60 * 60 * 1000,
    label: "文件保存",
    description: "保存 Terminal.vue",
    file: "src/components/ide/Terminal.vue",
  },
  {
    id: "tl-8",
    type: "git-commit",
    timestamp: Date.now() - 3 * 24 * 60 * 60 * 1000,
    label: "feat: Session 25 Outline/Welcome/Markdown",
    description: "OutlinePanel/WelcomePage/useMarkdown/Monaco增强",
    commitHash: "m0n1o2p",
    author: "reginyuan",
  },
])

// ── 按时间分组 ──
const timeGroups = computed(() => {
  const now = Date.now()
  const todayStart = new Date().setHours(0, 0, 0, 0)
  const yesterdayStart = todayStart - 24 * 60 * 60 * 1000
  const weekStart = todayStart - 7 * 24 * 60 * 60 * 1000

  const groups: { label: string; entries: TimelineEntry[]; collapsed: boolean }[] = [
    { label: "今天", entries: [], collapsed: false },
    { label: "昨天", entries: [], collapsed: false },
    { label: "本周", entries: [], collapsed: false },
    { label: "更早", entries: [], collapsed: true },
  ]

  for (const e of entries.value) {
    if (e.timestamp >= todayStart) groups[0].entries.push(e)
    else if (e.timestamp >= yesterdayStart) groups[1].entries.push(e)
    else if (e.timestamp >= weekStart) groups[2].entries.push(e)
    else groups[3].entries.push(e)
  }

  return groups.filter(g => g.entries.length > 0)
})

// ── 文件过滤 (自定义下拉, 不使用浏览器原生 <select>) ──
const filterFile = ref<string | null>(null)
const filterOpen = ref(false)
const filterTriggerRef = ref<HTMLElement | null>(null)
const filterMenuStyle = ref<Record<string, string>>({})

const fileOptions = computed(() => {
  const set = new Set<string>()
  for (const e of entries.value) {
    if (e.file) set.add(e.file)
  }
  return Array.from(set)
})

const currentFilterLabel = computed(() => {
  if (!filterFile.value) return "所有文件"
  return filterFile.value.split(/[\\/]/).pop() || filterFile.value
})

function toggleFilter(e: MouseEvent): void {
  e.stopPropagation()
  if (filterOpen.value) {
    filterOpen.value = false
    return
  }
  filterOpen.value = true
  // 计算浮层位置 (基于 trigger 按钮)
  nextTick(() => {
    const el = filterTriggerRef.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    const menuWidth = 220
    const menuMaxHeight = 280
    const viewportH = window.innerHeight
    // 默认向下展开
    let top = rect.bottom + 4
    let height = Math.min(menuMaxHeight, fileOptions.value.length * 28 + 36)
    // 如果下方空间不够, 改为向上展开
    if (top + height > viewportH - 8) {
      top = Math.max(8, rect.top - height - 4)
    }
    filterMenuStyle.value = {
      top: `${top}px`,
      left: `${Math.max(8, rect.right - menuWidth)}px`,
      width: `${menuWidth}px`,
      maxHeight: `${menuMaxHeight}px`,
    }
  })
}

function selectFilter(value: string | null): void {
  filterFile.value = value
  filterOpen.value = false
}

function onDocClick(e: MouseEvent): void {
  if (!filterOpen.value) return
  const target = e.target as HTMLElement
  if (target.closest(".tl-filter-menu") || target.closest(".tl-filter-trigger")) return
  filterOpen.value = false
}

onMounted(() => document.addEventListener("click", onDocClick))
onBeforeUnmount(() => document.removeEventListener("click", onDocClick))

// ── 时间格式化 ──
function formatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
  }
  return d.toLocaleDateString("zh-CN", { month: "short", day: "numeric" }) +
    " " + d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })
}

function formatRelative(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60000) return "刚刚"
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return `${Math.floor(diff / 86400000)}天前`
}

// ── 恢复操作 (模拟) ──
function restoreEntry(entry: TimelineEntry): void {
  console.log("[Timeline] Restore:", entry.label)
}

function compareWithCurrent(entry: TimelineEntry): void {
  console.log("[Timeline] Compare:", entry.label)
  if (entry.file) store.openFile(entry.file)
}
</script>

<template>
  <div class="timeline-panel flex flex-col h-full text-[13px]"
    style="color: var(--color-ide-text); background: var(--color-ide-surface);">

    <!-- ═══ Header ═══ -->
    <div class="shrink-0 flex items-center px-3 h-9 gap-2" style="border-bottom: 1px solid var(--color-ide-border);">
      <History :size="14" style="color: var(--color-ide-accent);" />
      <span class="text-[12px] font-semibold uppercase tracking-wider">时间线</span>
      <div class="flex-1" />
      <!-- 自定义下拉过滤器 -->
      <button
        ref="filterTriggerRef"
        type="button"
        class="tl-filter-trigger flex items-center gap-1.5 h-6 px-2 rounded-[3px] text-[11px] transition-colors"
        :class="{ 'tl-filter-open': filterOpen }"
        :style="{
          background: filterOpen ? 'var(--color-ide-surface-active)' : 'var(--color-chat-input-bg)',
          color: 'var(--color-ide-text)',
          border: '1px solid var(--color-ide-border)',
        }"
        @click="toggleFilter"
      >
        <FileText :size="11" style="color: var(--color-ide-text-dim);" />
        <span class="truncate max-w-[110px]">{{ currentFilterLabel }}</span>
        <ChevronRight
          :size="10"
          class="transition-transform duration-150 -rotate-90"
          :class="{ 'rotate-90': filterOpen }"
          style="color: var(--color-ide-text-dim);"
        />
      </button>
    </div>

    <!-- ═══ 过滤浮层 (Teleport 到 body) ═══ -->
    <Teleport to="body">
      <div
        v-if="filterOpen"
        class="tl-filter-menu fixed z-50 rounded-[4px] overflow-hidden"
        :style="{
          ...filterMenuStyle,
          background: 'var(--color-ide-surface)',
          border: '1px solid var(--color-ide-border)',
          boxShadow: '0 4px 16px rgba(0,0,0,0.4)',
        }"
        @click.stop
      >
        <div class="text-[10px] uppercase tracking-wider px-2.5 py-1.5 font-semibold"
          style="color: var(--color-ide-text-dim); border-bottom: 1px solid var(--color-ide-border);">
          按文件过滤
        </div>
        <div class="overflow-y-auto">
          <button
            type="button"
            class="tl-filter-item flex items-center gap-2 w-full px-2.5 py-1.5 text-[12px] text-left"
            :class="{ 'tl-filter-active': filterFile === null }"
            @click="selectFilter(null)"
          >
            <Check :size="11" :class="filterFile === null ? 'opacity-100' : 'opacity-0'" style="color: var(--color-ide-accent);" />
            <span class="flex-1 truncate">所有文件</span>
          </button>
          <button
            v-for="file in fileOptions"
            :key="file"
            type="button"
            class="tl-filter-item flex items-center gap-2 w-full px-2.5 py-1.5 text-[12px] text-left"
            :class="{ 'tl-filter-active': filterFile === file }"
            @click="selectFilter(file)"
          >
            <Check :size="11" :class="filterFile === file ? 'opacity-100' : 'opacity-0'" style="color: var(--color-ide-accent);" />
            <FileText :size="11" style="color: var(--color-ide-text-dim);" />
            <span class="flex-1 truncate">{{ file.split(/[\\/]/).pop() }}</span>
            <span class="text-[10px] opacity-50 truncate max-w-[80px]" style="color: var(--color-ide-text-dim);">
              {{ file }}
            </span>
          </button>
        </div>
      </div>
    </Teleport>

    <!-- ═══ 时间线列表 ═══ -->
    <div class="flex-1 overflow-y-auto py-1">
      <template v-for="group in timeGroups" :key="group.label">
        <!-- 时间分组标题 -->
        <div class="flex items-center gap-1.5 px-3 h-7 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          @click="group.collapsed = !group.collapsed">
          <ChevronRight
            :size="10"
            class="transition-transform duration-150"
            :class="{ 'rotate-90': !group.collapsed }"
            style="color: var(--color-ide-text-dim);"
          />
          <span class="text-[11px] font-semibold uppercase tracking-wider"
            style="color: var(--color-ide-text-dim);">
            {{ group.label }}
          </span>
          <span class="text-[10px] opacity-50" style="color: var(--color-ide-text-dim);">
            ({{ group.entries.length }})
          </span>
        </div>

        <!-- 时间线条目 -->
        <div v-if="!group.collapsed">
          <div
            v-for="entry in group.entries"
            :key="entry.id"
            class="timeline-entry flex items-start gap-2.5 px-3 py-2 cursor-pointer transition-colors group"
            :class="{
              'tl-entry-commit': entry.type === 'git-commit',
              'tl-entry-save': entry.type === 'file-save',
              'tl-entry-auto': entry.type === 'auto-save',
            }"
          >
            <!-- 图标列 (与左侧时间线对齐) -->
            <div class="shrink-0 flex flex-col items-center gap-0.5 pt-0.5">
              <div class="w-5 h-5 flex items-center justify-center rounded-full"
                :style="{
                  background: entry.type === 'git-commit'
                    ? 'var(--color-ide-accent)'
                    : entry.type === 'file-save'
                      ? 'var(--color-ide-success)'
                      : 'var(--color-ide-surface-hover)',
                  border: entry.type === 'auto-save' ? '1px solid var(--color-ide-border)' : 'none',
                }">
                <GitCommit v-if="entry.type === 'git-commit'" :size="10" style="color: #fff;" />
                <Save v-else-if="entry.type === 'auto-save'" :size="10" style="color: var(--color-ide-text-dim);" />
                <FileText v-else :size="10" style="color: #fff;" />
              </div>
            </div>

            <!-- 主体内容 -->
            <div class="flex-1 min-w-0">
              <!-- 标签行 -->
              <div class="flex items-center gap-2 min-w-0">
                <span class="text-[12px] font-medium truncate"
                  style="color: var(--color-ide-text);">
                  {{ entry.label }}
                </span>
                <span class="shrink-0 text-[10px]" style="color: var(--color-ide-text-dim);">
                  {{ formatRelative(entry.timestamp) }}
                </span>
              </div>

              <!-- 描述 -->
              <div v-if="entry.description" class="text-[11px] truncate mt-0.5"
                style="color: var(--color-ide-text-dim);">
                {{ entry.description }}
              </div>

              <!-- 元信息行 (单行紧凑) -->
              <div class="flex items-center gap-2 mt-1 text-[10px] min-w-0">
                <span v-if="entry.file" class="flex items-center gap-1 truncate min-w-0"
                  style="color: var(--color-ide-text-dim);">
                  <FileText :size="9" />
                  <span class="truncate">{{ entry.file?.split(/[\\/]/).pop() || entry.file }}</span>
                </span>
                <span v-if="entry.commitHash" class="shrink-0 font-mono px-1 rounded-[2px]"
                  style="color: var(--color-ide-accent); background: color-mix(in srgb, var(--color-ide-accent) 12%, transparent);">
                  {{ entry.commitHash }}
                </span>
                <span v-if="entry.author" class="shrink-0" style="color: var(--color-ide-text-dim);">
                  {{ entry.author }}
                </span>
                <span class="shrink-0 opacity-40 ml-auto" style="color: var(--color-ide-text-dim);">
                  {{ formatTime(entry.timestamp) }}
                </span>
              </div>
            </div>

            <!-- hover 操作按钮 -->
            <div class="hidden group-hover:flex items-center gap-0.5 shrink-0 self-center">
              <button
                class="w-6 h-6 flex items-center justify-center rounded-[3px] transition-colors"
                title="与当前文件比较"
                @click.stop="compareWithCurrent(entry)"
              >
                <ArrowLeftRight :size="11" style="color: var(--color-ide-text-dim);" />
              </button>
              <button
                class="w-6 h-6 flex items-center justify-center rounded-[3px] transition-colors"
                title="恢复此版本"
                @click.stop="restoreEntry(entry)"
              >
                <ArrowUpCircle :size="11" style="color: var(--color-ide-text-dim);" />
              </button>
            </div>
          </div>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-if="timeGroups.length === 0" class="flex flex-col items-center justify-center py-16 gap-2">
        <Clock :size="24" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
          没有时间线条目
        </span>
        <span class="text-[10px] opacity-50" style="color: var(--color-ide-text-dim);">
          文件保存历史将显示在这里
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.timeline-entry {
  position: relative;
  border-bottom: 1px solid color-mix(in srgb, var(--color-ide-border) 40%, transparent);
}
.timeline-entry:last-child {
  border-bottom: none;
}
.timeline-entry:hover {
  background: var(--color-ide-surface-hover);
}

/* 类型 hover 强调 (左侧细线) */
.timeline-entry::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 2px;
  background: transparent;
  transition: background 0.15s;
}
.tl-entry-commit:hover::before { background: var(--color-ide-accent); }
.tl-entry-save:hover::before { background: var(--color-ide-success); }
.tl-entry-auto:hover::before { background: var(--color-ide-text-dim); }

/* 自定义下拉触发器 */
.tl-filter-trigger:hover {
  background: var(--color-ide-surface-hover) !important;
  border-color: color-mix(in srgb, var(--color-ide-accent) 50%, var(--color-ide-border)) !important;
}
.tl-filter-open {
  border-color: var(--color-ide-accent) !important;
}

/* 浮层菜单项 */
.tl-filter-item {
  color: var(--color-ide-text);
  background: transparent;
  transition: background 0.1s;
}
.tl-filter-item:hover {
  background: var(--color-ide-surface-hover);
}
.tl-filter-active {
  background: color-mix(in srgb, var(--color-ide-accent) 8%, transparent);
}
</style>
