<script setup lang="ts">
/**
 * MultiFileDiffPanel.vue — 多文件 Diff 追踪面板
 *
 * 参考项目：Aider (multi-file edit tracking), Monaco Editor (change navigation)
 *
 * 功能：
 *   1. 列出所有已变更文件（文件列表 + 变更统计）
 *   2. 每个文件有独立的变更摘要（+N/-N 行）
 *   3. 点击展开/折叠查看全文 diff
 *   4. Hunks 间快速跳转（上一个/下一个变更块）
 *   5. 全局 Accept All / Reject All 操作
 *   6. 变更类型筛选（新建/修改/删除）
 */
import {
  Check,
  ChevronDown,
  ChevronRight,
  FileEdit,
  FileMinus,
  FilePlus,
  Minus,
  Plus,
  X,
} from "lucide-vue-next"
import { computed, ref } from "vue"
import type { DiffData } from "@/types/studio"

const props = defineProps<{
  diffs: DiffData[]
  /** 是否显示操作按钮 */
  actions?: boolean
  /** 是否高亮当前活动文件 */
  activeFilePath?: string
}>()

const emit = defineEmits<{
  (e: "selectDiff", diff: DiffData): void
  (e: "acceptFile", filePath: string): void
  (e: "rejectFile", filePath: string): void
  (e: "acceptAll"): void
  (e: "rejectAll"): void
  (e: "jumpToHunk", filePath: string, hunkIndex: number): void
}>()

// ═══════════════════ 状态 ═══════════════════
const activeFile = ref<string | null>(null)
const expandedFiles = ref<Set<string>>(new Set())
const filterType = ref<"all" | "CREATE" | "MODIFY" | "DELETE">("all")

// 已接受/拒绝的文件集合
const acceptedFiles = ref<Set<string>>(new Set())
const rejectedFiles = ref<Set<string>>(new Set())

// ═══════════════════ 过滤后列表 ═══════════════════
const filteredDiffs = computed(() => {
  if (filterType.value === "all") return props.diffs
  return props.diffs.filter(d => d.change_type === filterType.value)
})

// 统计
const stats = computed(() => {
  const total = props.diffs.length
  const added = props.diffs.reduce((s, d) => s + d.lines_added, 0)
  const removed = props.diffs.reduce((s, d) => s + d.lines_removed, 0)
  const creates = props.diffs.filter(d => d.change_type === "CREATE").length
  const modifies = props.diffs.filter(d => d.change_type === "MODIFY").length
  const deletes = props.diffs.filter(d => d.change_type === "DELETE").length
  return { total, added, removed, creates, modifies, deletes }
})

// ═══════════════════ 操作 ═══════════════════
function toggleExpand(filePath: string) {
  const s = expandedFiles.value
  s.has(filePath) ? s.delete(filePath) : s.add(filePath)
}

function selectFile(filePath: string, diff: DiffData) {
  activeFile.value = filePath
  expandFile(filePath)
  emit("selectDiff", diff)
}

function expandFile(filePath: string) {
  expandedFiles.value.add(filePath)
}

function changeIcon(d: DiffData) {
  return d.change_type === "CREATE" ? FilePlus : d.change_type === "DELETE" ? FileMinus : FileEdit
}

function changeColor(d: DiffData) {
  return d.change_type === "CREATE" ? "text-emerald-400" : d.change_type === "DELETE" ? "text-red-400" : "text-amber-400"
}

// 解析简短的 diff 摘要
function diffSummary(d: DiffData): string {
  return `+${d.lines_added} −${d.lines_removed}`
}
</script>

<template>
  <div v-if="diffs.length > 0" class="multi-diff-panel rounded-xl border border-[var(--color-ide-border)] bg-white/[0.01] overflow-hidden">
    <!-- 头部：全局统计 + 批量操作 -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-white/[0.04] bg-white/[0.02]">
      <div class="flex items-center gap-3">
        <FileEdit class="w-4 h-4 text-brand-400" />
        <span class="text-sm font-semibold text-[var(--color-ide-text)]">{{ stats.total }} 文件变更</span>
        <div class="flex items-center gap-2 text-xs font-mono">
          <span class="text-emerald-400 flex items-center gap-0.5"><Plus class="w-3 h-3" />{{ stats.added }}</span>
          <span class="text-red-400 flex items-center gap-0.5"><Minus class="w-3 h-3" />{{ stats.removed }}</span>
        </div>
      </div>

      <!-- 筛选 Tab -->
      <div class="flex items-center gap-0.5">
        <button
          v-for="t in [{ k: 'all', l: '全部' }, { k: 'CREATE', l: '新增' }, { k: 'MODIFY', l: '修改' }, { k: 'DELETE', l: '删除' }]"
          :key="t.k"
          @click="filterType = t.k as any"
          :class="[
            'px-2 py-1 text-[10px] rounded-md font-medium transition-colors',
            filterType === t.k ? 'bg-white/10 text-[var(--color-ide-text)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'
          ]"
        >
          {{ t.l }}
          <span v-if="t.k === 'all'">({{ stats.total }})</span>
          <span v-else-if="t.k === 'CREATE'">({{ stats.creates }})</span>
          <span v-else-if="t.k === 'MODIFY'">({{ stats.modifies }})</span>
          <span v-else>({{ stats.deletes }})</span>
        </button>

        <!-- 批量操作 (Aider 风格 Accept All / Reject All) -->
        <div v-if="actions" class="flex items-center gap-1 ml-2 pl-2 border-l border-[var(--color-ide-border)]">
          <button
            @click="emit('acceptAll')"
            class="flex items-center gap-1 px-2 py-1 text-[11px] text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 rounded-md transition-colors"
          >
            <Check class="w-3 h-3" /> 接受全部
          </button>
          <button
            @click="emit('rejectAll')"
            class="flex items-center gap-1 px-2 py-1 text-[11px] text-red-400 bg-red-500/10 hover:bg-red-500/20 rounded-md transition-colors"
          >
            <X class="w-3 h-3" /> 拒绝全部
          </button>
        </div>
      </div>
    </div>

    <!-- 文件列表 -->
    <div class="divide-y divide-white/[0.03] max-h-[500px] overflow-y-auto custom-scroll">
      <div
        v-for="diff in filteredDiffs"
        :key="diff.file_path"
        :class="[
          'transition-colors duration-150',
          activeFilePath === diff.file_path ? 'bg-brand-500/[0.04]' : 'hover:bg-white/[0.01]'
        ]"
      >
        <!-- 文件行 -->
        <div
          @click="toggleExpand(diff.file_path)"
          class="flex items-center gap-2.5 px-4 py-2.5 cursor-pointer group"
        >
          <!-- 展开/折叠 -->
          <button class="p-0.5 rounded text-[var(--color-ide-text-dim)] group-hover:text-[var(--color-ide-text-dim)] transition-colors">
            <ChevronRight v-if="!expandedFiles.has(diff.file_path)" class="w-3.5 h-3.5" />
            <ChevronDown v-else class="w-3.5 h-3.5" />
          </button>

          <!-- 变更类型图标 -->
          <component :is="changeIcon(diff)" :class="['w-4 h-4 shrink-0', changeColor(diff)]" />

          <!-- 文件信息 -->
          <div class="flex-1 min-w-0" @click.stop="selectFile(diff.file_path, diff)">
            <p class="text-sm font-mono text-[var(--color-ide-text)] truncate">{{ diff.file_name }}</p>
            <p class="text-[11px] text-[var(--color-ide-text-dim)] truncate">{{ diff.file_path }}</p>
          </div>

          <!-- 变更统计 -->
          <span class="text-xs font-mono text-[var(--color-ide-text-dim)] shrink-0">{{ diffSummary(diff) }}</span>

          <!-- 单文件操作 (Aider 风格) -->
          <div v-if="actions" class="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              @click.stop="emit('acceptFile', diff.file_path)"
              class="p-1 rounded-md text-emerald-500 hover:bg-emerald-500/10 transition-colors"
              title="接受此文件变更"
            >
              <Check class="w-3.5 h-3.5" />
            </button>
            <button
              @click.stop="emit('rejectFile', diff.file_path)"
              class="p-1 rounded-md text-red-500 hover:bg-red-500/10 transition-colors"
              title="拒绝此文件变更"
            >
              <X class="w-3.5 h-3.5" />
            </button>
          </div>

          <!-- 语言标签 -->
          <span
            v-if="diff.language"
            class="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full bg-white/[0.03] text-[var(--color-ide-text-dim)] shrink-0"
          >
            {{ diff.language }}
          </span>
        </div>

        <!-- 展开的 Diff 内容 (复用 DiffViewer 逻辑简版) -->
        <div v-if="expandedFiles.has(diff.file_path)" class="border-t border-white/[0.04] bg-surface-900/50">
          <!-- Hunk 跳转导航 (Monaco Editor 风格) -->
          <div class="flex items-center gap-1 px-4 py-1.5 bg-white/[0.01] border-b border-white/[0.03]">
            <span class="text-[10px] text-[var(--color-ide-text-dim)] mr-1">
              {{ diff.hunks?.length || 0 }} 变更块
            </span>
            <template v-if="diff.hunks && diff.hunks.length > 0">
              <button
                v-for="(hunk, hi) in diff.hunks"
                :key="hi"
                @click="emit('jumpToHunk', diff.file_path, hi)"
                class="px-1.5 py-0.5 rounded text-[9px] bg-white/[0.03] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)] transition-colors font-mono"
                :title="hunk.header"
              >
                H{{ hi + 1 }}
              </button>
            </template>
          </div>

          <!-- 精简版 Diff 展示 -->
          <div class="overflow-x-auto font-mono text-[12px] leading-[1.5] max-h-[240px] overflow-y-auto custom-scroll">
            <table class="w-full border-collapse">
              <tbody>
                <tr
                  v-for="(hunk, hi) in diff.hunks || []"
                  :key="hi"
                >
                  <td
                    v-for="(line, li) in hunk.lines"
                    :key="li"
                    :class="[
                      'px-3 py-0 whitespace-pre-wrap',
                      line.startsWith('@@') ? 'bg-blue-500/5 text-blue-400/70 text-[11px] font-semibold' :
                      line.startsWith('+') ? 'bg-emerald-500/[0.08] text-emerald-200/80' :
                      line.startsWith('-') ? 'bg-red-500/[0.08] text-red-200/80' :
                      'text-[var(--color-ide-text-dim)]'
                    ]"
                    v-if="li === 0 && hunk.lines.length > 0"
                  >
                    {{ line }}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 操作栏 -->
          <div v-if="actions" class="flex items-center gap-2 px-4 py-1.5 border-t border-white/[0.03] bg-white/[0.01]">
            <button
              @click="emit('acceptFile', diff.file_path)"
              class="flex items-center gap-1 px-2 py-1 text-[11px] text-emerald-400 hover:bg-emerald-500/10 rounded-md transition-colors"
            >
              <Check class="w-3 h-3" /> 使用此变更
            </button>
            <button
              @click="emit('rejectFile', diff.file_path)"
              class="flex items-center gap-1 px-2 py-1 text-[11px] text-red-400 hover:bg-red-500/10 rounded-md transition-colors"
            >
              <X class="w-3 h-3" /> 放弃变更
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="filteredDiffs.length === 0 && diffs.length > 0" class="py-8 text-center text-xs text-[var(--color-ide-text-dim)]">
      当前筛选条件下没有变更文件
    </div>
  </div>
</template>

<style scoped>
.custom-scroll::-webkit-scrollbar { width: 3px; }
.custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.06); border-radius: 9999px; }
</style>
