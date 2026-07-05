<script setup lang="ts">
/**
 * MergeEditor.vue — VS Code 3-way Merge 冲突编辑器
 *
 * 借鉴: VSCode workbench/contrib/mergeEditor/
 *
 * 能力:
 *   - 三栏布局: 当前更改 | 合并结果 | 传入更改
 *   - 冲突块高亮 (绿色=当前, 蓝色=传入, 红色=冲突)
 *   - 接受当前 / 接受传入 / 接受全部 / 手动编辑
 *   - 下一个/上一个冲突导航
 *   - 拒绝更改 (还原)
 */
import { Check, X, ChevronUp, ChevronDown, ArrowLeftRight, Save, GitMerge, Copy, FileCode } from 'lucide-vue-next'
import { computed, ref, watch } from 'vue'

export interface MergeConflict {
  startLine: number
  endLine: number
  current: string[]
  incoming: string[]
  base?: string[]
  resolved: boolean
  resolution?: 'current' | 'incoming' | 'both' | 'custom'
}

const props = defineProps<{
  visible: boolean
  filePath?: string
  currentContent: string
  incomingContent: string
  baseContent?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'resolve', content: string): void
  (e: 'accept-current'): void
  (e: 'accept-incoming'): void
}>()

// Parse conflict markers from content
function parseConflicts(current: string, incoming: string): MergeConflict[] {
  const conflicts: MergeConflict[] = []
  const currentLines = current.split('\n')
  const pattern = /^<{7}\s*(.*?)\s*$/
  let inConflict = false
  let currentBlock: string[] = []
  let incomingBlock: string[] = []
  let startLine = 0
  let reading: 'base' | 'current' | 'incoming' = 'base'

  for (let i = 0; i < currentLines.length; i++) {
    const line = currentLines[i]
    if (line.match(/^<{7}/)) {
      inConflict = true
      reading = 'current'
      currentBlock = []
      incomingBlock = []
      startLine = i
    } else if (inConflict && line.match(/^={7}/)) {
      reading = 'incoming'
      currentBlock = [...currentBlock]
    } else if (inConflict && line.match(/^>{7}/)) {
      conflicts.push({
        startLine, endLine: i,
        current: currentBlock.filter(l => !l.trim().startsWith('<<<<<<<') && !l.trim().startsWith('=======')),
        incoming: incomingBlock,
        resolved: false,
      })
      inConflict = false
      reading = 'base'
    } else if (inConflict) {
      if (reading === 'current') currentBlock.push(line)
      else incomingBlock.push(line)
    }
  }
  return conflicts
}

const conflicts = ref<MergeConflict[]>([])
const activeConflictIdx = ref(0)
const resolvedContent = ref(props.currentContent.replace(/^<{7}.*\n(?:[\s\S]*?\n)?={7}\n(?:[\s\S]*?\n)?>{7}.*(\n|$)/gm, (match) => {
  const parts = match.split(/^={7}/m)
  return parts[0]?.replace(/^<{7}.*\n/, '')?.trimEnd() ?? match
}))

const activeConflict = computed(() => conflicts.value[activeConflictIdx.value] ?? null)
const conflictCount = computed(() => conflicts.value.length)
const unresolvedCount = computed(() => conflicts.value.filter(c => !c.resolved).length)

function resolveConflict(choice: 'current' | 'incoming' | 'both'): void {
  const c = conflicts.value[activeConflictIdx.value]
  if (!c) return
  c.resolved = true
  c.resolution = choice
  // Apply to resolved content
  const lines = resolvedContent.value.split('\n')
  const replacement: string[] = choice === 'current' ? c.current : choice === 'both' ? [...c.current, ...c.incoming] : c.incoming
  lines.splice(c.startLine, c.endLine - c.startLine + 1, ...replacement)
  resolvedContent.value = lines.join('\n')
  nextConflict()
}

function nextConflict(): void {
  const unresolved = conflicts.value.findIndex((c, i) => !c.resolved && i > activeConflictIdx.value)
  if (unresolved >= 0) activeConflictIdx.value = unresolved
}

function prevConflict(): void {
  for (let i = activeConflictIdx.value - 1; i >= 0; i--) {
    if (!conflicts.value[i].resolved) { activeConflictIdx.value = i; return }
  }
}

function acceptAllCurrent(): void {
  for (const c of conflicts.value) { c.resolved = true; c.resolution = 'current' }
  resolveAll('current')
}

function acceptAllIncoming(): void {
  for (const c of conflicts.value) { c.resolved = true; c.resolution = 'incoming' }
  resolveAll('incoming')
}

function resolveAll(choice: 'current' | 'incoming'): void {
  let content = props.currentContent
  for (const c of [...conflicts.value].reverse()) {
    const lines = content.split('\n')
    const replacement = choice === 'current' ? c.current : c.incoming
    lines.splice(c.startLine, c.endLine - c.startLine + 1, ...replacement)
    content = lines.join('\n')
  }
  resolvedContent.value = content
}

function finishMerge(): void {
  emit('resolve', resolvedContent.value)
}

watch(() => props.visible, (v) => {
  if (v) {
    conflicts.value = parseConflicts(props.currentContent, props.incomingContent)
    resolvedContent.value = props.currentContent
    activeConflictIdx.value = 0
  }
}, { immediate: true })
</script>

<template>
  <div v-if="visible" class="merge-editor flex flex-col h-full" style="background:var(--color-ide-surface)">
    <!-- Header -->
    <div class="flex items-center justify-between shrink-0 px-3 h-9 gap-2" style="border-bottom:1px solid var(--color-ide-border)">
      <div class="flex items-center gap-2">
        <GitMerge :size="14" style="color:var(--color-ide-accent)" />
        <span class="text-[12px] font-semibold" style="color:var(--color-ide-text)">
          合并冲突 — {{ filePath?.split(/[\\/]/).pop() || '未知文件' }}
        </span>
        <span class="text-[11px] px-1.5 rounded" :style="{color:'var(--color-ide-text-dim)', background:'var(--color-ide-surface-hover)'}">
          {{ unresolvedCount }} / {{ conflictCount }} 冲突
        </span>
      </div>
      <div class="flex items-center gap-1">
        <button class="merge-btn" @click="acceptAllCurrent" title="全部采用当前更改">全部采用当前</button>
        <button class="merge-btn" @click="acceptAllIncoming" title="全部采用传入更改">全部采用传入</button>
        <button class="merge-btn primary" @click="finishMerge" :disabled="unresolvedCount > 0" title="完成合并">
          <Save :size="12" /> 完成合并
        </button>
        <button class="merge-btn-close" @click="emit('close')"><X :size="14" /></button>
      </div>
    </div>

    <!-- Conflict Navigator -->
    <div v-if="conflictCount > 0" class="flex items-center justify-center gap-2 shrink-0 py-1.5 px-3" style="border-bottom:1px solid var(--color-ide-border)">
      <button class="merge-nav-btn" @click="prevConflict"><ChevronUp :size="14" /></button>
      <span class="text-[11px]" style="color:var(--color-ide-text)">冲突 {{ activeConflictIdx + 1 }} / {{ conflictCount }}</span>
      <button class="merge-nav-btn" @click="nextConflict"><ChevronDown :size="14" /></button>
    </div>

    <!-- Three-way merge view -->
    <div class="flex-1 flex min-h-0 overflow-hidden">
      <!-- Current changes -->
      <div class="flex-1 flex flex-col min-w-0" style="border-right:1px solid var(--color-ide-border)">
        <div class="shrink-0 px-3 py-1 text-[11px] font-semibold" style="background:var(--color-ide-bg-secondary);color:var(--color-ide-accent)">
          当前更改 (Current)
        </div>
        <div class="flex-1 overflow-auto p-2 font-mono text-[12px]" style="color:var(--color-ide-text); background:var(--color-editor-bg)">
          <pre class="whitespace-pre-wrap">{{ currentContent }}</pre>
        </div>
        <div v-if="activeConflict" class="shrink-0 flex items-center gap-1 px-2 py-1" style="border-top:1px solid var(--color-ide-border)">
          <button class="merge-accept-btn accept-current" @click="resolveConflict('current')">
            <Check :size="12" /> 采用当前
          </button>
        </div>
      </div>

      <!-- Resolved result -->
      <div class="flex-1 flex flex-col min-w-0" style="border-right:1px solid var(--color-ide-border); border-left:1px solid var(--color-ide-border)">
        <div class="shrink-0 px-3 py-1 text-[11px] font-semibold" style="background:var(--color-ide-bg-secondary);color:var(--color-ide-text)">
          合并结果 (Result)
        </div>
        <div class="flex-1 overflow-auto p-2 font-mono text-[12px]" style="color:var(--color-ide-text); background:var(--color-editor-bg)">
          <pre class="whitespace-pre-wrap">{{ resolvedContent }}</pre>
        </div>
        <div v-if="activeConflict" class="shrink-0 flex items-center gap-1 px-2 py-1" style="border-top:1px solid var(--color-ide-border)">
          <button class="merge-accept-btn accept-both" @click="resolveConflict('both')">
            <Copy :size="12" /> 保留双方
          </button>
        </div>
      </div>

      <!-- Incoming changes -->
      <div class="flex-1 flex flex-col min-w-0">
        <div class="shrink-0 px-3 py-1 text-[11px] font-semibold" style="background:var(--color-ide-bg-secondary);color:#75beff">
          传入更改 (Incoming)
        </div>
        <div class="flex-1 overflow-auto p-2 font-mono text-[12px]" style="color:var(--color-ide-text); background:var(--color-editor-bg)">
          <pre class="whitespace-pre-wrap">{{ incomingContent }}</pre>
        </div>
        <div v-if="activeConflict" class="shrink-0 flex items-center gap-1 px-2 py-1" style="border-top:1px solid var(--color-ide-border)">
          <button class="merge-accept-btn accept-incoming" @click="resolveConflict('incoming')">
            <Check :size="12" /> 采用传入
          </button>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="flex items-center justify-center h-full" style="color:var(--color-ide-text-dim)">
    <div class="text-center">
      <GitMerge :size="32" class="mx-auto mb-3 opacity-20" />
      <p class="text-[13px]">无合并冲突</p>
      <p class="text-[11px] opacity-50 mt-1">工作区已是最新</p>
    </div>
  </div>
</template>

<style scoped>
.merge-btn {
  font-size: 11px; padding: 2px 8px; border-radius: 3px;
  color: var(--color-ide-text); background: var(--color-ide-surface-hover);
  transition: all 0.1s;
}
.merge-btn:hover { background: var(--color-ide-surface-active); }
.merge-btn.primary { background: var(--color-ide-accent); color: #fff; }
.merge-btn.primary:disabled { opacity: 0.4; cursor: not-allowed; }
.merge-btn-close {
  display:flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:3px;
  color:var(--color-ide-text-dim);
}
.merge-btn-close:hover { background:var(--color-ide-surface-hover); color:var(--color-ide-text); }
.merge-nav-btn {
  display:flex; align-items:center; justify-content:center;
  width:22px; height:22px; border-radius:3px;
  color:var(--color-ide-text-dim);
}
.merge-nav-btn:hover { background:var(--color-ide-surface-hover); color:var(--color-ide-text); }
.merge-accept-btn {
  display:flex; align-items:center; gap:4px;
  font-size:11px; padding:3px 10px; border-radius:3px;
  color:#fff; transition:all 0.1s;
}
.accept-current { background:var(--color-ide-accent) }
.accept-incoming { background:#0078d4 }
.accept-both { background:#6c5ce7 }
.merge-accept-btn:hover { filter:brightness(1.15) }
</style>
