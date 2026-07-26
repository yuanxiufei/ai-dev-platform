<script setup lang="ts">
/**
 * TasksPanel.vue — VSCode Tasks 任务面板
 *
 * 借鉴: VSCode workbench/contrib/tasks/ + problemMatcher.ts
 * Session 49: 集成 Problem Matchers API — 构建输出 → 结构化诊断
 * 能力:
 *   - 分类展示任务 (build/test/watch/clean)
 *   - 运行/停止任务
 *   - 终端输出切换 (含问题匹配器解析)
 *   - 新建/编辑任务
 *   - Ctrl+Shift+B 运行默认构建任务
 */
import { ref, computed, onMounted } from "vue"
import {
  Play, Square, Plus, Settings, Terminal as TerminalIcon,
  ChevronDown, ChevronRight, Trash2, Hammer, FlaskConical, Eye, Clock, Loader2, CheckCircle2, XCircle, StopCircle,
  AlertTriangle, AlertCircle, Info, Lightbulb, SearchCode,
} from "lucide-vue-next"
import { useTasksStore } from "@/stores/useTasksStore"
import { useIDEStore } from "@/stores/useIDEStore"

const store = useTasksStore()
const ideStore = useIDEStore()

onMounted(() => store.init())

// ── 分组展开折叠
const expandedGroup = ref<Set<string>>(new Set(["build", "test", "watch"]))
function toggleGroup(g: string) { expandedGroup.value.has(g) ? expandedGroup.value.delete(g) : expandedGroup.value.add(g) }

const groups = [
  { id: "build", label: "构建", icon: Hammer },
  { id: "test", label: "测试", icon: FlaskConical },
  { id: "watch", label: "监听", icon: Eye },
  { id: "clean", label: "清理", icon: Trash2 },
  { id: "none", label: "其他", icon: Settings },
]

// ── 新建任务
const showNewForm = ref(false)
const newTask = ref({ label: "", type: "shell" as const, command: "", group: "none" as const })

function addNewTask() {
  if (!newTask.value.label || !newTask.value.command) return
  store.addTask({ label: newTask.value.label, type: newTask.value.type, command: newTask.value.command, group: newTask.value.group })
  newTask.value = { label: "", type: "shell", command: "", group: "none" }
  showNewForm.value = false
}

// ── 运行输出切换
const showOutput = ref(false)
const currentRun = computed(() => store.runs[0])
const runningRun = computed(() => store.runs.find(r => r.status === "running"))

// Session 49: Problem Matchers — 解析任务输出为结构化诊断
const diagnostics = ref<any[]>([])
const diagnosticsLoading = ref(false)
const parsedRunId = ref<string | null>(null)
const showDiagnostics = ref(false)

async function parseOutputWithMatcher(run: any): Promise<void> {
  if (!run.output || run.output.length === 0) return
  const content = run.output.join("\n")
  diagnosticsLoading.value = true
  try {
    const res = await fetch(`${(window as any).__apiBaseUrl || "/api/v1"}/system/problem-matchers/parse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ matcher_id: "auto", content }),
    })
    if (res.ok) {
      const data = await res.json()
      diagnostics.value = data.diagnostics || []
      parsedRunId.value = run.id
      if (diagnostics.value.length > 0) showDiagnostics.value = true
    }
  } catch { /* 静默 */ }
  finally { diagnosticsLoading.value = false }
}

function openDiagnostic(diag: any): void {
  const ideStore = useIDEStore()
  if (diag.file_path) {
    ideStore.openFile(diag.file_path)
    setTimeout(() => {
      const editor = (window as any).__activeMonacoEditor
      if (editor && diag.line) {
        editor.revealLineInCenter(diag.line)
        editor.setPosition({ lineNumber: diag.line, column: diag.column || 1 })
        editor.focus()
      }
    }, 300)
  }
}

function getSeverityIcon(severity: string) {
  switch (severity) {
    case "error": return AlertCircle
    case "warning": return AlertTriangle
    case "info": return Info
    case "hint": return Lightbulb
    default: return AlertCircle
  }
}

function getSeverityColor(severity: string) {
  switch (severity) {
    case "error": return "#ef4444"
    case "warning": return "#f59e0b"
    case "info": return "#3b82f6"
    case "hint": return "#8b5cf6"
    default: return "#9ca3af"
  }
}

/** 任务完成时自动解析输出 */
function onRunFinished(run: any): void {
  if (run.status === "failed") {
    parseOutputWithMatcher(run)
  }
}
</script>

<template>
  <div class="tasks-panel flex flex-col h-full text-[13px]" style="color:var(--color-ide-text); background:var(--color-ide-surface)">
    <!-- Header -->
    <div class="shrink-0 flex items-center px-3" style="height:38px;border-bottom:1px solid var(--color-ide-border)">
      <TerminalIcon :size="14" style="color:var(--color-ide-accent)" class="mr-2" />
      <span class="text-[12px] font-semibold uppercase tracking-wider flex-1">任务</span>
      <button
        class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]"
        title="运行默认构建任务 (Ctrl+Shift+B)" @click="store.startTask(store.tasks[0]?.id ?? '')"
      >
        <Play :size="12" />
      </button>
      <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]"
        title="新建任务" @click="showNewForm = !showNewForm">
        <Plus :size="14" />
      </button>
    </div>

    <!-- 新建任务表单 -->
    <div v-if="showNewForm" class="shrink-0 px-3 py-2 border-b space-y-1.5" style="border-color:var(--color-ide-border);background:var(--color-ide-surface-hover)">
      <input v-model="newTask.label" class="task-input" placeholder="任务名称" />
      <div class="flex gap-1.5">
        <select v-model="newTask.type" class="task-input flex-1">
          <option value="shell">Shell</option><option value="npm">npm</option>
          <option value="tsc">TypeScript</option><option value="custom">自定义</option>
        </select>
        <select v-model="newTask.group" class="task-input flex-1">
          <option value="build">构建</option><option value="test">测试</option>
          <option value="watch">监听</option><option value="clean">清理</option>
          <option value="none">其他</option>
        </select>
      </div>
      <input v-model="newTask.command" class="task-input" :placeholder="newTask.type==='npm'?'run build':newTask.type==='tsc'?'tsc -p tsconfig.json':'echo Hello'" />
      <div class="flex gap-1">
        <button class="task-btn-primary" @click="addNewTask">创建</button>
        <button class="task-btn-secondary" @click="showNewForm=false">取消</button>
      </div>
    </div>

    <!-- 运行状态栏 -->
    <div v-if="runningRun" class="shrink-0 flex items-center px-3 h-8 gap-2 text-[11px] border-b" style="border-color:var(--color-ide-border); background: rgba(76,175,80,0.08)">
      <Loader2 :size="12" class="animate-spin text-green-400" />
      <span class="truncate flex-1">{{ runningRun.label }}</span>
      <button class="w-5 h-5 flex items-center justify-center rounded-[2px] hover:bg-red-500/20 text-red-400" title="停止"
        @click="store.stopTask(runningRun.id)">
        <Square :size="10" />
      </button>
    </div>

    <!-- 任务列表 (分组) -->
    <div class="flex-1 overflow-y-auto">
      <div v-for="group in groups" :key="group.id" v-show="store.tasksByGroup[group.id]?.length">
        <button class="task-group-header" @click="toggleGroup(group.id)">
          <ChevronRight :size="10" class="transition-transform" :class="{ 'rotate-90': expandedGroup.has(group.id) }" />
          <component :is="group.icon" :size="12" class="text-[var(--color-ide-text-dim)]" />
          <span>{{ group.label }}</span>
          <span class="text-[10px] opacity-50">({{ store.tasksByGroup[group.id]?.length ?? 0 }})</span>
        </button>
        <div v-if="expandedGroup.has(group.id)">
          <div v-for="task in store.tasksByGroup[group.id]" :key="task.id"
            class="task-item group" @dblclick="store.startTask(task.id)">
            <div class="flex items-center gap-1.5">
              <TerminalIcon :size="11" class="shrink-0" style="color:var(--color-ide-accent)" />
              <span class="flex-1 truncate text-[12px]">{{ task.label }}</span>
              <span class="text-[10px] opacity-40 shrink-0">{{ task.type }}</span>
              <button class="task-run-btn" title="运行" @click.stop="store.startTask(task.id)">
                <Play :size="10" />
              </button>
              <button class="task-del-btn" title="删除" @click.stop="store.removeTask(task.id)">
                <Trash2 :size="10" />
              </button>
            </div>
            <div class="text-[10px] mt-0.5 ml-5 opacity-40">{{ task.command }}</div>
          </div>
        </div>
      </div>

      <div v-if="store.tasks.length === 0" class="flex flex-col items-center justify-center py-16 text-[var(--color-ide-text-dim)]">
        <Settings :size="24" class="mb-2 opacity-20" />
        <p class="text-[12px]">暂无任务</p>
        <p class="text-[10px] opacity-50 mt-1">创建构建/测试/监听任务</p>
      </div>
    </div>

    <!-- 运行历史 / 输出 -->
    <div v-if="store.runs.length > 0" class="shrink-0 border-t" style="border-color:var(--color-ide-border)">
      <div class="task-group-header" @click="showOutput = !showOutput" role="button" tabindex="0">
        <ChevronRight :size="10" class="transition-transform" :class="{ 'rotate-90': showOutput }" />
        <Clock :size="12" />
        <span>运行历史</span>
        <span class="text-[10px] opacity-50">({{ store.runs.length }})</span>
        <button class="ml-auto text-[10px] text-[var(--color-ide-text-dim)] hover:text-red-400" @click.stop="store.clearRuns()">清除</button>
      </div>
      <div v-if="showOutput" class="max-h-48 overflow-y-auto font-mono text-[11px] p-2"
        style="background: var(--color-editor-bg); border-top: 1px solid var(--color-ide-border)">
        <div v-for="run in store.runs" :key="run.id" class="mb-1">
          <div class="flex items-center gap-1 mb-0.5 text-[10px]">
            <CheckCircle2 v-if="run.status==='success'" :size="10" class="text-green-400" />
            <XCircle v-else-if="run.status==='failed'" :size="10" class="text-red-400" />
            <StopCircle v-else-if="run.status==='killed'" :size="10" class="text-yellow-400" />
            <Loader2 v-else :size="10" class="animate-spin text-blue-400" />
            <span :class="run.status==='failed'?'text-red-400':''">{{ run.label }}</span>
            <span class="opacity-40 ml-auto">exit: {{ run.exitCode ?? '...' }}</span>
            <button
              v-if="run.status === 'failed' && run.id !== parsedRunId"
              class="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-accent)] hover:bg-[var(--color-ide-accent)]/20 transition-colors"
              @click="parseOutputWithMatcher(run)"
            >
              <SearchCode :size="10" class="inline mr-0.5" />解析问题
            </button>
          </div>
        </div>
      </div>

      <!-- Session 49: Problem Matchers 解析结果 -->
      <div v-if="diagnostics.length > 0" class="shrink-0 border-t" style="border-color:var(--color-ide-border)">
        <button class="task-group-header" @click="showDiagnostics = !showDiagnostics">
          <ChevronRight :size="10" class="transition-transform" :class="{ 'rotate-90': showDiagnostics }" />
          <AlertTriangle :size="12" :style="{ color: diagnostics.some((d: any) => d.severity === 'error') ? '#ef4444' : '#f59e0b' }" />
          <span>问题</span>
          <span class="text-[10px] opacity-50">
            ({{ diagnostics.filter((d: any) => d.severity === 'error').length }} 错误, {{ diagnostics.filter((d: any) => d.severity === 'warning').length }} 警告)
          </span>
        </button>
        <div v-if="showDiagnostics" class="max-h-64 overflow-y-auto">
          <div
            v-for="(diag, idx) in diagnostics"
            :key="idx"
            class="flex items-start gap-2 px-3 py-1.5 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors border-b border-[var(--color-ide-border)]/30"
            :style="{ borderLeft: `3px solid ${getSeverityColor(diag.severity)}` }"
            @click="openDiagnostic(diag)"
          >
            <component :is="getSeverityIcon(diag.severity)" :size="13" class="mt-0.5 shrink-0" :style="{ color: getSeverityColor(diag.severity) }" />
            <div class="flex-1 min-w-0">
              <div class="flex items-baseline gap-2">
                <span class="text-[12px] font-medium text-[var(--color-ide-text)] truncate">{{ diag.message }}</span>
                <span v-if="diag.code" class="text-[10px] px-1 py-px rounded bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] shrink-0">{{ diag.code }}</span>
              </div>
              <div class="text-[10px] text-[var(--color-ide-text-dim)] opacity-60 mt-0.5">
                {{ diag.file_path || '(无文件)' }}{{ diag.line ? `:${diag.line}` : '' }}{{ diag.column ? `:${diag.column}` : '' }}
                <span v-if="diag.source" class="ml-2">[{{ diag.source }}]</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 加载中 -->
      <div v-if="diagnosticsLoading" class="shrink-0 flex items-center justify-center py-2 text-[11px] text-[var(--color-ide-text-dim)] border-t" style="border-color:var(--color-ide-border)">
        <Loader2 :size="12" class="animate-spin mr-1.5" /> 解析构建输出...
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-input {
  width: 100%; padding: 3px 6px; font-size: 11px;
  background: var(--color-editor-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.task-input:focus { border-color: var(--color-ide-accent); }
.task-input::placeholder { color: var(--color-ide-text-dim); opacity: 0.5; }
.task-btn-primary {
  padding: 3px 10px; font-size: 11px; border-radius: 3px; background: var(--color-ide-accent);
  color: white; border: none; cursor: pointer;
}
.task-btn-secondary {
  padding: 3px 10px; font-size: 11px; border-radius: 3px; border: 1px solid var(--color-ide-border);
  color: var(--color-ide-text-dim); background: transparent; cursor: pointer;
}
.task-group-header {
  display: flex; align-items: center; gap: 4px; width: 100%; height: 26px; padding: 0 8px;
  font-size: 11px; font-weight: 600; color: var(--color-ide-text-dim); cursor: pointer;
  border: none; background: transparent;
}
.task-group-header:hover { background: var(--color-ide-surface-hover); }
.task-item {
  padding: 4px 8px 4px 20px; cursor: pointer; border-bottom: 1px solid color-mix(in srgb, var(--color-ide-border) 30%, transparent);
  transition: background 0.1s;
}
.task-item:hover { background: var(--color-ide-surface-hover); }
.task-run-btn {
  width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;
  border-radius: 2px; color: var(--color-ide-text-dim); opacity: 0; transition: all 0.1s;
}
.task-item:hover .task-run-btn { opacity: 1; }
.task-run-btn:hover { background: var(--color-ide-accent); color: white; }
.task-del-btn {
  width: 20px; height: 20px; display: flex; align-items: center; justify-content: center;
  border-radius: 2px; color: var(--color-ide-text-dim); opacity: 0; transition: all 0.1s;
}
.task-item:hover .task-del-btn { opacity: 1; }
.task-del-btn:hover { background: rgba(239,68,68,0.15); color: #ef4444; }
</style>
