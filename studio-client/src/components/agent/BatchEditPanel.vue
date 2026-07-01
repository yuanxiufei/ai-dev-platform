<script setup lang="ts">/**
 * BatchEditPanel.vue — Aider 风格多文件批量编辑确认面板
 *
 * 借鉴 Aider 的搜索-替换（search-replace）模式：
 *   - 每次 AI 修改用 search/replace 块表示
 *   - 支持逐文件 Accept/Reject
 *   - 支持 Accept All / Reject All
 *   - Git 风格绿色新增 / 红色删除
 *
 * 使用场景：
 *   Agent 返回多文件修改建议时，展示此面板让用户逐文件审查确认
 */

import {
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileCode,
  GitBranch,
  XCircle,
} from "lucide-vue-next"
import { computed, ref } from "vue"

/** 单个文件的编辑操作 */
export interface FileEdit {
  /** 文件路径 */
  filePath: string
  /** 原始代码（搜索块） */
  original: string
  /** 新代码（替换块）*/
  modified: string
  /** 操作类型 */
  op: "modify" | "create" | "delete"
  /** 状态 */
  status: "pending" | "approved" | "rejected"
  /** 语言 */
  language?: string
  /** 描述 */
  description?: string
}

const props = defineProps<{
  edits: FileEdit[]
  /** 总描述 */
  title?: string
  /** 是否显示在面板中 */
  visible?: boolean
}>()

const emit = defineEmits<{
  (e: "approve", filePath: string): void
  (e: "reject", filePath: string): void
  (e: "approveAll"): void
  (e: "rejectAll"): void
  (e: "close"): void
}>()

// ── 状态 ──
const expandedFiles = ref<Set<string>>(new Set())
const viewMode = ref<"unified" | "split">("unified")

function toggleExpand(filePath: string) {
  if (expandedFiles.value.has(filePath)) {
    expandedFiles.value.delete(filePath)
  } else {
    expandedFiles.value.add(filePath)
  }
}

function expandAll() {
  props.edits.forEach((e) => expandedFiles.value.add(e.filePath))
}

function collapseAll() {
  expandedFiles.value.clear()
}

// ── 计算 ──
const pendingCount = computed(() => props.edits.filter((e) => e.status === "pending").length)
const approvedCount = computed(() => props.edits.filter((e) => e.status === "approved").length)
const rejectedCount = computed(() => props.edits.filter((e) => e.status === "rejected").length)

/** 操作类型标签 */
function opLabel(op: FileEdit["op"]): string {
  return { modify: "修改", create: "新建", delete: "删除" }[op]
}
function opColor(op: FileEdit["op"]): string {
  return { modify: "#FBBF24", create: "#4ADE80", delete: "#EF4444" }[op]
}

/** 生成统一 Diff 视图的行 */
function diffLines(edit: FileEdit): Array<{ type: "same" | "add" | "remove" | "header"; text: string }> {
  if (viewMode.value !== "unified") return []

  const lines: Array<{ type: "same" | "add" | "remove" | "header"; text: string }> = []
  const origLines = edit.original.split("\n")
  const modLines = edit.modified.split("\n")

  lines.push({ type: "header", text: `--- a/${edit.filePath}` })
  lines.push({ type: "header", text: `+++ b/${edit.filePath}` })

  // 简单逐行对比
  const maxLen = Math.max(origLines.length, modLines.length)
  for (let i = 0; i < maxLen; i++) {
    const o = origLines[i]
    const m = modLines[i]
    if (o === m) {
      if (o !== undefined) lines.push({ type: "same", text: `  ${o}` })
    } else {
      if (o !== undefined) lines.push({ type: "remove", text: `- ${o}` })
      if (m !== undefined) lines.push({ type: "add", text: `+ ${m}` })
    }
  }
  return lines
}

/** 截断文本 */
function truncate(text: string, max: number = 60): string {
  const firstLine = text.split("\n")[0]
  return firstLine.length > max ? firstLine.slice(0, max) + "..." : firstLine
}
</script>

<template>
  <Transition name="slide-up">
    <div
      v-if="visible"
      class="batch-edit-panel fixed bottom-0 left-0 right-0 z-[400] border-t border-[var(--color-ide-border)] shadow-2xl"
      style="background: var(--color-ide-surface); max-height: 50vh;"
    >
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-2.5 border-b border-[var(--color-ide-border)]">
        <div class="flex items-center gap-3">
          <GitBranch :size="16" class="text-sky-400" />
          <span class="text-sm font-semibold text-[var(--color-ide-text)]">
            {{ title || 'AI 建议的修改' }}
          </span>
          <span class="text-xs text-[var(--color-ide-text-dim)]">
            {{ pendingCount }} 待审核 / {{ approvedCount }} 已批准 / {{ rejectedCount }} 已拒绝
          </span>
        </div>
        <div class="flex items-center gap-2">
          <!-- 视图切换 -->
          <button
            class="px-2 py-1 text-xs rounded border border-[var(--color-ide-border)] hover:bg-white/5 text-[var(--color-ide-text-dim)]"
            @click="viewMode = viewMode === 'unified' ? 'split' : 'unified'"
          >
            {{ viewMode === 'unified' ? '统一' : '分栏' }}
          </button>
          <button
            class="px-2 py-1 text-xs rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]"
            @click="collapseAll"
          >
            全部折叠
          </button>
          <button
            class="px-2 py-1 text-xs rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]"
            @click="expandAll"
          >
            全部展开
          </button>
          <div class="w-px h-4 bg-[var(--color-ide-border)] mx-1" />
          <!-- 操作按钮 -->
          <button
            class="px-3 py-1 text-xs rounded bg-green-600/20 text-green-400 border border-green-500/30 hover:bg-green-600/30 transition-colors flex items-center gap-1"
            @click="emit('approveAll')"
          >
            <CheckCircle2 :size="13" /> 全部批准
          </button>
          <button
            class="px-3 py-1 text-xs rounded bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors flex items-center gap-1"
            @click="emit('rejectAll')"
          >
            <XCircle :size="13" /> 全部拒绝
          </button>
          <button
            class="px-2 py-1 text-xs rounded hover:bg-white/5 text-[var(--color-ide-text-dim)] ml-1"
            @click="emit('close')"
          >
            ✕
          </button>
        </div>
      </div>

      <!-- File List -->
      <div class="overflow-y-auto" style="max-height: calc(50vh - 52px);">
        <div
          v-for="edit in edits"
          :key="edit.filePath"
          class="border-b border-[var(--color-ide-border)]/50 last:border-b-0"
        >
          <!-- File Header -->
          <div
            class="flex items-center gap-2 px-4 py-2 hover:bg-white/[0.02] cursor-pointer select-none"
            @click="toggleExpand(edit.filePath)"
          >
            <!-- Status dot -->
            <span
              class="w-2 h-2 rounded-full shrink-0"
              :class="{
                'bg-yellow-400': edit.status === 'pending',
                'bg-green-400': edit.status === 'approved',
                'bg-red-400': edit.status === 'rejected',
              }"
            />
            <!-- Expand chevron -->
            <component
              :is="expandedFiles.has(edit.filePath) ? ChevronDown : ChevronRight"
              :size="14"
              class="text-[var(--color-ide-text-dim)]"
            />
            <!-- File icon + path -->
            <FileCode
              :size="14"
              class="shrink-0"
              :style="{ color: opColor(edit.op) }"
            />
            <span class="text-sm font-medium text-[var(--color-ide-text)] truncate">
              {{ edit.filePath }}
            </span>
            <!-- Operation badge -->
            <span
              class="text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0"
              :style="{ color: opColor(edit.op), background: `${opColor(edit.op)}15` }"
            >
              {{ opLabel(edit.op) }}
            </span>
            <!-- Description -->
            <span v-if="edit.description" class="text-xs text-[var(--color-ide-text-dim)] truncate ml-2">
              {{ edit.description }}
            </span>
            <div class="flex-1" />
            <!-- Per-file actions -->
            <div class="flex items-center gap-1" @click.stop>
              <button
                v-if="edit.status !== 'approved'"
                class="p-1 rounded hover:bg-green-500/20 text-green-400 transition-colors"
                title="批准此文件"
                @click="emit('approve', edit.filePath)"
              >
                <CheckCircle2 :size="14" />
              </button>
              <button
                v-if="edit.status !== 'rejected'"
                class="p-1 rounded hover:bg-red-500/20 text-red-400 transition-colors"
                title="拒绝此文件"
                @click="emit('reject', edit.filePath)"
              >
                <XCircle :size="14" />
              </button>
            </div>
          </div>

          <!-- Expanded Diff View -->
          <div v-if="expandedFiles.has(edit.filePath)" class="px-4 pb-3">
            <div
              class="rounded-lg border border-[var(--color-ide-border)] overflow-hidden font-mono text-xs leading-5"
              style="background: var(--color-editor-bg);"
            >
              <!-- Unified Diff View -->
              <template v-if="viewMode === 'unified'">
                <div
                  v-for="(line, li) in diffLines(edit)"
                  :key="li"
                  class="flex"
                  :class="{
                    'bg-green-500/10': line.type === 'add',
                    'bg-red-500/10': line.type === 'remove',
                    'bg-blue-500/10 text-blue-300': line.type === 'header',
                  }"
                >
                  <span
                    class="w-5 text-right mr-2 select-none shrink-0 opacity-50"
                    :class="{
                      'text-green-400': line.type === 'add',
                      'text-red-400': line.type === 'remove',
                    }"
                  >{{ line.type === 'header' ? ' ' : li }}</span>
                  <span
                    class="whitespace-pre-wrap break-all"
                    :class="{
                      'text-green-300': line.type === 'add',
                      'text-red-300': line.type === 'remove',
                      'text-[var(--color-ide-text-dim)]': line.type === 'same',
                    }"
                  >{{ line.text }}</span>
                </div>
              </template>

              <!-- Split View -->
              <template v-else>
                <div class="grid grid-cols-2 divide-x divide-[var(--color-ide-border)]">
                  <!-- 原始 (Left) -->
                  <div class="overflow-x-auto">
                    <div class="px-3 py-1 text-[10px] uppercase tracking-wider text-red-400/70 bg-red-500/5">原始</div>
                    <div
                      v-for="(line, li) in edit.original.split('\n')"
                      :key="'o' + li"
                      class="flex bg-red-500/5"
                    >
                      <span class="w-6 text-right mr-2 select-none shrink-0 opacity-40 text-red-400">{{ li + 1 }}</span>
                      <span class="text-red-300/80 whitespace-pre-wrap break-all">{{ line }}</span>
                    </div>
                  </div>
                  <!-- 修改后 (Right) -->
                  <div class="overflow-x-auto">
                    <div class="px-3 py-1 text-[10px] uppercase tracking-wider text-green-400/70 bg-green-500/5">修改后</div>
                    <div
                      v-for="(line, li) in edit.modified.split('\n')"
                      :key="'m' + li"
                      class="flex bg-green-500/5"
                    >
                      <span class="w-6 text-right mr-2 select-none shrink-0 opacity-40 text-green-400">{{ li + 1 }}</span>
                      <span class="text-green-300/80 whitespace-pre-wrap break-all">{{ line }}</span>
                    </div>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- Empty State -->
        <div v-if="edits.length === 0" class="flex flex-col items-center justify-center py-10 text-[var(--color-ide-text-dim)]">
          <CheckCircle2 :size="32" class="mb-2 opacity-30" />
          <span class="text-sm">没有待审核的修改</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.slide-up-enter-active {
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.slide-up-leave-active {
  transition: all 0.2s ease-in;
}
.slide-up-enter-from,
.slide-up-leave-to {
  transform: translateY(100%);
  opacity: 0;
}
</style>
