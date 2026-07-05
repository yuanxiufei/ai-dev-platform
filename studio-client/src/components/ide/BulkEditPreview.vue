<script setup lang="ts">
/**
 * BulkEditPreview.vue — 批量编辑预览确认弹窗
 *
 * 借鉴: VSCode src/vs/workbench/contrib/bulkEdit/
 * 能力:
 *   - 展示所有将要被修改的文件和变更
 *   - 修改前/后对比 (diff 预览)
 *   - 接受全部 / 逐个确认 / 取消
 *   - 文件计数组统计
 */
import { ref, computed } from "vue"
import { AlertTriangle, Check, X, FileText, ArrowRight, ChevronDown, ChevronRight } from "lucide-vue-next"

export interface BulkEditEntry {
  file: string
  original: string
  modified: string
  description: string
  line?: number
}

const props = defineProps<{
  edits: BulkEditEntry[]
  title?: string
  description?: string
}>()

const emit = defineEmits<{
  (e: "apply-all"): void
  (e: "cancel"): void
  (e: "apply-one", index: number): void
}>()

const expandedFiles = ref<Set<number>>(new Set())
const appliedIndices = ref<Set<number>>(new Set())

const fileCount = computed(() => new Set(props.edits.map(e => e.file)).size)
const totalChanges = computed(() => props.edits.length)
const remainingChanges = computed(() => totalChanges.value - appliedIndices.value.size)

function toggleFile(idx: number): void {
  expandedFiles.value.has(idx) ? expandedFiles.value.delete(idx) : expandedFiles.value.add(idx)
}

function applyOne(idx: number): void {
  appliedIndices.value.add(idx)
  emit("apply-one", idx)
}

function applyAll(): void {
  emit("apply-all")
  appliedIndices.value = new Set(props.edits.map((_, i) => i))
}

function cancel(): void {
  emit("cancel")
}

function diffPreview(original: string, modified: string): string[] {
  const lines: string[] = []
  const oLines = original.split("\n")
  const mLines = modified.split("\n")
  const max = Math.max(oLines.length, mLines.length)
  for (let i = 0; i < max; i++) {
    if (i < mLines.length) lines.push(`+ ${mLines[i]}`)
    if (i < oLines.length && oLines[i] !== mLines[i]) lines.push(`- ${oLines[i]}`)
  }
  return lines.slice(0, 10)
}
</script>

<template>
  <Teleport to="body">
    <div class="bulk-edit-overlay" @click.self="cancel">
      <div class="bulk-edit-dialog" style="background:var(--color-ide-surface); color:var(--color-ide-text)">
        <!-- Header -->
        <div class="flex items-center justify-between px-4" style="height:48px;border-bottom:1px solid var(--color-ide-border)">
          <div class="flex items-center gap-2">
            <AlertTriangle :size="16" style="color:#f59e0b" />
            <span class="text-[14px] font-semibold">{{ title || "批量修改预览" }}</span>
          </div>
          <button class="w-7 h-7 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]"
            @click="cancel"><X :size="16" /></button>
        </div>

        <!-- Description -->
        <div class="px-4 py-2 text-[12px]" style="color:var(--color-ide-text-dim); border-bottom:1px solid var(--color-ide-border)">
          <p v-if="description">{{ description }}</p>
          <p v-else>
            此操作将修改 <b style="color:var(--color-ide-text)">{{ fileCount }}</b> 个文件，
            共 <b style="color:var(--color-ide-text)">{{ totalChanges }}</b> 处变更。
          </p>
        </div>

        <!-- Edit List -->
        <div class="bulk-edit-list overflow-y-auto">
          <div v-for="(edit, idx) in edits" :key="idx"
            class="bulk-edit-entry"
            :class="{ 'opacity-50': appliedIndices.has(idx) }">
            <!-- File header -->
            <button class="bulk-edit-file-header" @click="toggleFile(idx)">
              <ChevronRight :size="10" class="transition-transform" :class="{ 'rotate-90': expandedFiles.has(idx) }" />
              <FileText :size="12" style="color:var(--color-ide-accent)" />
              <span class="flex-1 truncate text-[12px]">{{ edit.file.split(/[\\/]/).pop() }}</span>
              <span class="text-[10px] opacity-50" v-if="edit.line">Ln {{ edit.line }}</span>
              <button v-if="!appliedIndices.has(idx)" class="bulk-edit-apply-one" @click.stop="applyOne(idx)" title="应用此变更">
                <Check :size="12" />
              </button>
              <Check v-else :size="12" class="text-green-400" />
            </button>

            <!-- Diff preview -->
            <div v-if="expandedFiles.has(idx)" class="bulk-edit-diff" style="background:var(--color-editor-bg)">
              <div class="text-[10px] text-[var(--color-ide-text-dim)] px-2 pt-1">{{ edit.description }}</div>
              <pre class="text-[11px] font-mono p-2 overflow-x-auto"><code><span v-for="(line, lidx) in diffPreview(edit.original, edit.modified)" :key="lidx"
  :class="line.startsWith('+') ? 'text-green-400' : line.startsWith('-') ? 'text-red-400' : 'text-[var(--color-ide-text-dim)]'">
  {{ line }}
</span></code></pre>
            </div>
          </div>
        </div>

        <!-- Footer -->
        <div class="flex items-center justify-between px-4" style="height:48px;border-top:1px solid var(--color-ide-border)">
          <span class="text-[11px] text-[var(--color-ide-text-dim)]">
            {{ remainingChanges > 0 ? `还有 ${remainingChanges} 处待处理` : "全部已应用" }}
          </span>
          <div class="flex gap-2">
            <button class="bulk-edit-btn cancel" @click="cancel">取消</button>
            <button class="bulk-edit-btn primary" :disabled="remainingChanges === 0" @click="applyAll">
              <Check :size="14" class="mr-1" /> 接受全部 ({{ remainingChanges }})
            </button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.bulk-edit-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center;
}
.bulk-edit-dialog {
  width: 640px; max-height: 80vh; border-radius: 6px;
  border: 1px solid var(--color-ide-border); box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  display: flex; flex-direction: column;
}
.bulk-edit-list { flex: 1; max-height: 50vh; }
.bulk-edit-entry { border-bottom: 1px solid color-mix(in srgb, var(--color-ide-border) 40%, transparent); }
.bulk-edit-file-header {
  display: flex; align-items: center; gap: 4px; width: 100%; padding: 6px 12px;
  cursor: pointer; border: none; background: transparent;
  color: var(--color-ide-text); font-size: 12px; text-align: left;
  transition: background 0.1s;
}
.bulk-edit-file-header:hover { background: var(--color-ide-surface-hover); }
.bulk-edit-apply-one { color: var(--color-ide-text-dim); padding: 2px; border-radius: 2px; }
.bulk-edit-apply-one:hover { background: rgba(34,197,94,0.15); color: #22c55e; }
.bulk-edit-diff { border-top: 1px solid color-mix(in srgb, var(--color-ide-border) 30%, transparent); }
.bulk-edit-btn {
  padding: 6px 16px; font-size: 12px; border-radius: 4px; font-weight: 500;
  border: none; cursor: pointer; transition: all 0.15s;
}
.bulk-edit-btn.cancel { background: transparent; border: 1px solid var(--color-ide-border); color: var(--color-ide-text-dim); }
.bulk-edit-btn.cancel:hover { background: var(--color-ide-surface-hover); }
.bulk-edit-btn.primary { background: var(--color-ide-accent); color: white; }
.bulk-edit-btn.primary:hover { filter: brightness(1.15); }
.bulk-edit-btn.primary:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
