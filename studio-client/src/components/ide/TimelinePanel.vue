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
import { ref, computed } from "vue"
import { Clock, GitCommit, Save, FileText, RotateCw, ChevronRight, History, ArrowLeftRight, ArrowUpCircle } from "lucide-vue-next"
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

// ── 文件过滤 ──
const filterFile = ref<string | null>(null)

const filteredEntries = computed(() => {
  if (!filterFile.value) return entries.value
  return entries.value.filter(e => e.file === filterFile.value)
})

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

// ── 类型图标 ──
function entryIcon(type: string): string {
  switch (type) {
    case "auto-save": return "save"
    case "git-commit": return "commit"
    case "manual-save": return "save"
    case "file-save": return "file"
    default: return "clock"
  }
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
    <div class="shrink-0 flex items-center px-3 h-9" style="border-bottom: 1px solid var(--color-ide-border);">
      <History :size="14" class="mr-2" style="color: var(--color-ide-accent);" />
      <span class="text-[12px] font-semibold uppercase tracking-wider">时间线</span>
      <div class="flex-1" />
      <!-- 文件过滤 -->
      <select
        v-model="filterFile"
        class="h-6 text-[11px] rounded-[3px] px-2 border-0 outline-none cursor-pointer"
        :style="{
          background: 'var(--color-chat-input-bg)',
          color: 'var(--color-ide-text)',
          border: '1px solid var(--color-ide-border)',
        }"
      >
        <option :value="null">所有文件</option>
        <option v-for="tab in store.tabs" :key="tab.id" :value="tab.filePath || tab.label">
          {{ tab.label }}
        </option>
      </select>
    </div>

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
            class="timeline-entry flex items-start gap-2 px-5 py-1.5 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors group"
            :class="{
              'border-l-2': true,
              'border-[var(--color-ide-accent)]': entry.type === 'git-commit',
              'border-[var(--color-ide-success)]': entry.type === 'file-save',
              'border-[var(--color-ide-text-dim)]/30': entry.type === 'auto-save',
            }"
          >
            <!-- 图标 -->
            <div class="shrink-0 w-5 h-5 flex items-center justify-center rounded-full mt-0.5"
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

            <div class="flex-1 min-w-0">
              <!-- 标签行 -->
              <div class="flex items-center gap-2">
                <span class="text-[12px] font-medium truncate"
                  :style="{ color: entry.type === 'git-commit' ? 'var(--color-ide-text)' : 'var(--color-ide-text)' }">
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

              <!-- 元信息行 -->
              <div class="flex items-center gap-3 mt-0.5 text-[10px]">
                <span v-if="entry.file" class="flex items-center gap-0.5" style="color: var(--color-ide-text-dim);">
                  <FileText :size="9" />
                  {{ entry.file?.split(/[\\/]/).pop() || entry.file }}
                </span>
                <span v-if="entry.commitHash" class="font-mono" style="color: var(--color-ide-accent);">
                  {{ entry.commitHash }}
                </span>
                <span v-if="entry.author" style="color: var(--color-ide-text-dim);">
                  {{ entry.author }}
                </span>
                <span class="opacity-40" style="color: var(--color-ide-text-dim);">
                  {{ formatTime(entry.timestamp) }}
                </span>
              </div>
            </div>

            <!-- hover 操作按钮 -->
            <div class="hidden group-hover:flex items-center gap-0.5 shrink-0">
              <button
                class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-active)] transition-colors"
                title="与当前文件比较"
                @click.stop="compareWithCurrent(entry)"
              >
                <ArrowLeftRight :size="11" style="color: var(--color-ide-text-dim);" />
              </button>
              <button
                class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-active)] transition-colors"
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
  border-left-width: 2px;
  border-left-style: solid;
  margin-left: 11px;
  padding-left: 10px;
}
</style>
