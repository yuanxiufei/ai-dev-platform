<script setup lang="ts">
/**
 * Problems Panel — VSCode-style diagnostics (ERROR/WARNING/INFO)
 * Scans open tabs for syntax issues and shows in structured list
 */
import { computed, ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { AlertTriangle, AlertCircle, Info, X, ChevronRight, Filter, Search } from 'lucide-vue-next'

const store = useIDEStore()

interface Problem {
  file: string
  line: number
  column: number
  message: string
  severity: 'error' | 'warning' | 'info'
  code?: string
}

interface ProblemGroup {
  file: string
  problems: Problem[]
  count: { error: number; warning: number; info: number }
}

// Simple regex-based diagnostics for open files
function scanProblems(): Problem[] {
  const problems: Problem[] = []
  for (const tab of store.tabs) {
    if (!tab.language) continue
    const lines = tab.content.split('\n')
    const fileName = tab.filePath || tab.label

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      const lineNum = i + 1

      // Detect TODO/FIXME/HACK as info
      if (/\b(TODO|FIXME|HACK|XXX)\b/.test(line)) {
        problems.push({
          file: fileName, line: lineNum, column: 1,
          message: line.trim(),
          severity: 'info',
          code: 'TODO',
        })
      }

      // Simple common error patterns
      if (/console\.(log|debug|warn)\(/.test(line) && /^(?!\s*\/\/)/.test(line)) {
        problems.push({
          file: fileName, line: lineNum, column: 1,
          message: `console statement: ${line.trim().slice(0, 60)}`,
          severity: 'warning',
          code: 'no-console',
        })
      }

      // Empty catch
      if (/catch\s*\([^)]*\)\s*\{\s*\}/.test(line)) {
        problems.push({
          file: fileName, line: lineNum, column: 1,
          message: 'Empty catch block',
          severity: 'warning',
          code: 'no-empty-catch',
        })
      }
    }
  }
  return problems
}

const allProblems = computed(() => scanProblems())

const groupedProblems = computed(() => {
  const groups = new Map<string, ProblemGroup>()
  for (const p of allProblems.value) {
    if (!groups.has(p.file)) {
      groups.set(p.file, { file: p.file, problems: [], count: { error: 0, warning: 0, info: 0 } })
    }
    const g = groups.get(p.file)!
    g.problems.push(p)
    g.count[p.severity]++
  }
  return Array.from(groups.values())
})

const summary = computed(() => {
  let err = 0, warn = 0, info = 0
  for (const p of allProblems.value) {
    if (p.severity === 'error') err++
    else if (p.severity === 'warning') warn++
    else info++
  }
  return { err, warn, info }
})

const filterSeverity = ref<'all' | 'error' | 'warning' | 'info'>('all')
const searchQuery = ref("")
const collapsedFiles = ref<Record<string, boolean>>({})

function toggleFileCollapse(file: string): void {
  collapsedFiles.value[file] = !collapsedFiles.value[file]
}

const filteredGroups = computed(() => {
  let groups = groupedProblems.value
  // 按严重级别筛选
  if (filterSeverity.value !== 'all') {
    groups = groups
      .map(g => ({
        ...g,
        problems: g.problems.filter(p => p.severity === filterSeverity.value),
      }))
      .filter(g => g.problems.length > 0)
  }
  // 按搜索词筛选
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    groups = groups
      .map(g => ({
        ...g,
        problems: g.problems.filter(p =>
          p.message.toLowerCase().includes(q) ||
          p.file.toLowerCase().includes(q) ||
          (p.code && p.code.toLowerCase().includes(q))
        ),
      }))
      .filter(g => g.problems.length > 0)
  }
  return groups
})

function openProblem(problem: Problem) {
  store.openFile(problem.file)
}

const severityIcon = {
  error: AlertCircle,
  warning: AlertTriangle,
  info: Info,
}
const severityColor = {
  error: 'var(--color-ide-error)',
  warning: 'var(--color-ide-warning)',
  info: 'var(--color-ide-info)',
}
const severityBg = {
  error: 'rgba(239,68,68,0.1)',
  warning: 'rgba(251,191,36,0.1)',
  info: 'rgba(59,130,246,0.1)',
}
</script>

<template>
  <div class="h-full flex flex-col text-[12px]" style="background:var(--color-ide-bg)">
    <!-- Filter bar -->
    <div class="flex items-center gap-1 px-2 py-1.5 border-b" style="border-color:var(--color-ide-border)">
      <Filter :size="12" class="text-[var(--color-ide-text-dim)]" />
      <button
        v-for="s in (['all','error','warning','info'] as const)"
        :key="s"
        class="px-2 py-0.5 rounded text-[11px] transition-colors"
        :class="filterSeverity === s ? 'font-semibold' : 'opacity-60'"
        :style="{
          background: filterSeverity === s ? 'var(--color-ide-surface-active)' : 'transparent',
          color: filterSeverity === s ? 'var(--color-ide-text)' : 'var(--color-ide-text-dim)',
        }"
        @click="filterSeverity = s"
      >
        {{ s === 'all' ? '全部' : s === 'error' ? '错误' : s === 'warning' ? '警告' : '信息' }}
        <span v-if="s !== 'all'" class="ml-1 opacity-50">
          {{ s === 'error' ? summary.err : s === 'warning' ? summary.warn : summary.info }}
        </span>
      </button>
      <!-- 🔥 搜索框 -->
      <div class="flex-1" />
      <div class="flex items-center gap-1 border rounded-[3px] overflow-hidden"
        :style="{ background: searchQuery.trim() ? 'var(--color-chat-input-bg)' : 'transparent', borderColor: searchQuery.trim() ? 'var(--color-ide-border-focus)' : 'transparent' }">
        <Search :size="11" class="ml-1.5" style="color: var(--color-ide-text-dim);" />
        <input
          v-model="searchQuery"
          type="text"
          class="flex-1 h-5 bg-transparent text-[11px] outline-none px-1 w-24"
          placeholder="筛选..."
        />
        <button v-if="searchQuery" class="shrink-0 w-4 h-5 flex items-center justify-center"
          @click="searchQuery = ''">
          <X :size="9" style="color: var(--color-ide-text-dim);" />
        </button>
      </div>
    </div>

    <!-- Problem list -->
    <div class="flex-1 overflow-y-auto">
      <div v-if="filteredGroups.length === 0" class="flex flex-col items-center justify-center py-10 text-[var(--color-ide-text-dim)] opacity-50">
        <AlertCircle :size="24" class="mb-2" />
        <p class="text-[11px]">{{ searchQuery ? '没有匹配的问题' : '没有检测到问题' }}</p>
      </div>
      <div v-else>
        <div v-for="group in filteredGroups" :key="group.file" class="border-b" style="border-color:var(--color-ide-border)/30">
          <!-- 🔥 File header (可折叠) -->
          <div class="flex items-center gap-1.5 px-2 py-1.5 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors"
            @click="toggleFileCollapse(group.file)">
            <ChevronRight :size="12" class="text-[var(--color-ide-text-dim)] transition-transform"
              :class="collapsedFiles[group.file] ? '' : 'rotate-90'" />
            <span class="font-medium text-[var(--color-ide-text)] truncate">{{ group.file.split(/[\\/]/).pop() }}</span>
            <span class="text-[10px] text-[var(--color-ide-text-dim)] opacity-50 ml-1 truncate">{{ group.file }}</span>
            <span class="ml-auto flex gap-1.5 text-[10px]">
              <span v-if="group.count.error" class="px-1 rounded" :style="{background:severityBg.error,color:severityColor.error}">{{ group.count.error }}</span>
              <span v-if="group.count.warning" class="px-1 rounded" :style="{background:severityBg.warning,color:severityColor.warning}">{{ group.count.warning }}</span>
              <span v-if="group.count.info" class="px-1 rounded" :style="{background:severityBg.info,color:severityColor.info}">{{ group.count.info }}</span>
            </span>
          </div>
          <!-- Problem items -->
          <div v-if="!collapsedFiles[group.file]">
            <div v-for="p in group.problems" :key="`${p.file}:${p.line}:${p.column}`"
              class="flex items-start gap-1.5 px-4 py-1 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              @click="openProblem(p)">
              <component :is="severityIcon[p.severity]" :size="13" class="mt-0.5 shrink-0" :style="{ color: severityColor[p.severity] }" />
              <span class="flex-1 text-[11px] text-[var(--color-ide-text)] leading-relaxed truncate" :title="p.message">{{ p.message }}</span>
              <span class="text-[10px] text-[var(--color-ide-text-dim)] opacity-50 shrink-0 ml-2 tabular-nums">{{ p.line }}:{{ p.column }}</span>
              <span v-if="p.code" class="text-[9px] text-[var(--color-ide-text-dim)] opacity-30 shrink-0 w-20 text-right truncate">{{ p.code }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Summary bar -->
    <div class="flex items-center gap-2 px-2 py-1 border-t text-[10px]" style="border-color:var(--color-ide-border);background:var(--color-ide-bg-secondary)">
      <span class="flex items-center gap-1" :style="{color:severityColor.error}">
        <AlertCircle :size="10"/> {{ summary.err }} 错误
      </span>
      <span class="flex items-center gap-1" :style="{color:severityColor.warning}">
        <AlertTriangle :size="10"/> {{ summary.warn }} 警告
      </span>
      <span class="flex items-center gap-1" :style="{color:severityColor.info}">
        <Info :size="10"/> {{ summary.info }} 信息
      </span>
      <span class="ml-auto text-[var(--color-ide-text-dim)]">{{ allProblems.length }} 个问题</span>
    </div>
  </div>
</template>
