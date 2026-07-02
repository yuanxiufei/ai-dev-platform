<script setup lang="ts">
/**
 * TasksPanel — VS Code Tasks System (任务运行器)
 *
 * 功能对标 VS Code Tasks:
 *   - 自动检测项目任务 (npm/pnpm/yarn/make/pip)
 *   - 手动添加任务
 *   - 运行任务 (输出到输出面板)
 *   - 任务类型标识 (shell/process/npm/gulp)
 *   - 任务状态: idle/running/success/failed
 *   - 问题匹配器提示
 */
import { ref, computed } from "vue"
import {
  Play, Square, RotateCw, Terminal, Plus, Trash2, Settings,
  ChevronRight, CheckCircle2, XCircle, Clock, Code2, Package, Cog, Bug, TestTube2
} from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"

const store = useIDEStore()

// ── 任务类型 ──
interface Task {
  id: string
  name: string
  type: "npm" | "shell" | "process" | "gulp" | "make" | "pip"
  command: string
  args?: string[]
  cwd?: string
  group: "build" | "test" | "dev" | "custom"
  status: "idle" | "running" | "success" | "failed"
  problemMatcher?: string
  isAutoDetected: boolean
  detail?: string
}

// ── 自动检测任务 (模拟) ──
const tasks = ref<Task[]>([
  {
    id: "task-1",
    name: "dev",
    type: "npm",
    command: "npm run dev",
    group: "dev",
    status: "idle",
    isAutoDetected: true,
    detail: "启动开发服务器 (Vite)",
  },
  {
    id: "task-2",
    name: "build",
    type: "npm",
    command: "npm run build",
    group: "build",
    status: "idle",
    isAutoDetected: true,
    detail: "构建项目 (Vite + TypeScript)",
  },
  {
    id: "task-3",
    name: "lint",
    type: "npm",
    command: "npm run lint",
    group: "custom",
    status: "idle",
    isAutoDetected: true,
    detail: "运行 ESLint 代码检查",
    problemMatcher: "$eslint-stylish",
  },
  {
    id: "task-4",
    name: "test",
    type: "npm",
    command: "npm run test",
    group: "test",
    status: "idle",
    isAutoDetected: true,
    detail: "运行测试套件 (Vitest)",
    problemMatcher: "$vite-test",
  },
  {
    id: "task-5",
    name: "test:coverage",
    type: "npm",
    command: "npm run test:coverage",
    group: "test",
    status: "idle",
    isAutoDetected: true,
    detail: "运行测试并生成覆盖率报告",
  },
  {
    id: "task-6",
    name: "typecheck",
    type: "npm",
    command: "npm run typecheck",
    group: "build",
    status: "idle",
    isAutoDetected: true,
    detail: "TypeScript 类型检查",
    problemMatcher: "$tsc",
  },
  {
    id: "task-7",
    name: "preview",
    type: "npm",
    command: "npm run preview",
    group: "dev",
    status: "idle",
    isAutoDetected: true,
    detail: "预览生产构建",
  },
  {
    id: "task-8",
    name: "format",
    type: "npm",
    command: "npm run format",
    group: "custom",
    status: "idle",
    isAutoDetected: true,
    detail: "代码格式化 (Prettier)",
  },
  {
    id: "task-9",
    name: "Backend: run server",
    type: "shell",
    command: "cd backend && python -m uvicorn app.main:app --reload",
    group: "dev",
    status: "idle",
    isAutoDetected: false,
    detail: "启动 FastAPI 后端服务器",
  },
  {
    id: "task-10",
    name: "Backend: run tests",
    type: "shell",
    command: "cd backend && python -m pytest tests/ -v",
    group: "test",
    status: "idle",
    isAutoDetected: false,
    detail: "运行 Python 后端测试",
    problemMatcher: "$python",
  },
  {
    id: "task-11",
    name: "Clean build artifacts",
    type: "shell",
    command: "rm -rf dist/ node_modules/.vite",
    group: "custom",
    status: "idle",
    isAutoDetected: false,
    detail: "清理构建产物",
  },
])

// ── 分组 ──
const groups = computed(() => {
  const g = new Map<string, Task[]>()
  for (const t of tasks.value) {
    if (!g.has(t.group)) g.set(t.group, [])
    g.get(t.group)!.push(t)
  }
  return g
})

const collapsedGroups = ref<Record<string, boolean>>({})
const showAddTask = ref(false)
const newTaskName = ref("")
const newTaskCmd = ref("")
const newTaskType = ref<Task["type"]>("shell")

// ── 分组标签 ──
const groupLabels: Record<string, string> = { build: "构建", test: "测试", dev: "开发", custom: "自定义" }
const groupIcons: Record<string, any> = { build: Package, test: TestTube2, dev: Play, custom: Cog }

// ── 运行任务 ──
const runningTasks = ref<Set<string>>(new Set())

async function runTask(task: Task): Promise<void> {
  if (runningTasks.value.has(task.id)) return
  task.status = "running"
  runningTasks.value.add(task.id)

  // 输出到输出面板
  store.addOutputLine(`[任务] 开始: ${task.name}`)
  store.addOutputLine(`[任务] 命令: ${task.command}`)
  store.addOutputLine("")

  // 模拟执行
  await new Promise(r => setTimeout(r, 800 + Math.random() * 1200))
  store.addOutputLine(`> ${task.command}`)
  store.addOutputLine(`✓ ${task.name} 完成 (${Math.floor(Math.random() * 2000 + 300)}ms)`)
  task.status = Math.random() > 0.85 ? "failed" : "success"
  if (task.status === "failed") {
    store.addOutputLine(`✗ ${task.name} 失败: 错误代码 1`)
  }
  store.addOutputLine("")
  runningTasks.value.delete(task.id)
}

function stopTask(task: Task): void {
  task.status = "idle"
  runningTasks.value.delete(task.id)
  store.addOutputLine(`[任务] 终止: ${task.name}`)
}

function toggleGroup(key: string): void {
  collapsedGroups.value[key] = !collapsedGroups.value[key]
}

function addTask(): void {
  if (!newTaskName.value.trim() || !newTaskCmd.value.trim()) return
  tasks.value.push({
    id: `task-custom-${Date.now()}`,
    name: newTaskName.value.trim(),
    type: newTaskType.value,
    command: newTaskCmd.value.trim(),
    group: "custom",
    status: "idle",
    isAutoDetected: false,
    detail: newTaskCmd.value.trim(),
  })
  newTaskName.value = ""
  newTaskCmd.value = ""
  showAddTask.value = false
}

function removeTask(task: Task): void {
  if (task.isAutoDetected) return
  tasks.value = tasks.value.filter(t => t.id !== task.id)
}
</script>

<template>
  <div class="tasks-panel flex flex-col h-full text-[13px]"
    style="color: var(--color-ide-text); background: var(--color-ide-surface);">

    <!-- ═══ Header ═══ -->
    <div class="shrink-0 flex items-center px-3 h-9" style="border-bottom: 1px solid var(--color-ide-border);">
      <Cog :size="14" class="mr-2" style="color: var(--color-ide-accent);" />
      <span class="text-[12px] font-semibold uppercase tracking-wider">任务</span>
      <div class="flex-1" />
      <button
        class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
        title="添加任务"
        @click="showAddTask = !showAddTask"
      >
        <Plus :size="14" style="color: var(--color-ide-text-dim);" />
      </button>
    </div>

    <!-- ═══ 添加任务表单 ═══ -->
    <div v-if="showAddTask" class="shrink-0 px-3 py-2 space-y-1.5" style="border-bottom: 1px solid var(--color-ide-border); background: var(--color-ide-bg-secondary);">
      <input
        v-model="newTaskName"
        type="text"
        class="w-full h-7 bg-[var(--color-chat-input-bg)] border border-[var(--color-ide-border)] rounded-[3px] text-[12px] px-2 outline-none focus:border-[var(--color-ide-border-focus)]"
        placeholder="任务名称"
      />
      <div class="flex gap-1">
        <select
          v-model="newTaskType"
          class="h-7 text-[11px] rounded-[3px] px-2 border border-[var(--color-ide-border)] outline-none"
          style="background: var(--color-chat-input-bg); color: var(--color-ide-text);"
        >
          <option value="npm">npm</option>
          <option value="shell">shell</option>
          <option value="process">process</option>
          <option value="make">make</option>
          <option value="pip">pip</option>
        </select>
        <input
          v-model="newTaskCmd"
          type="text"
          class="flex-1 h-7 bg-[var(--color-chat-input-bg)] border border-[var(--color-ide-border)] rounded-[3px] text-[12px] px-2 outline-none focus:border-[var(--color-ide-border-focus)]"
          :placeholder="newTaskType === 'npm' ? 'npm run build' : 'echo hello'"
        />
      </div>
      <div class="flex justify-end gap-1">
        <button
          class="px-2.5 h-6 rounded-[3px] text-[11px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          style="color: var(--color-ide-text-dim);"
          @click="showAddTask = false"
        >取消</button>
        <button
          class="px-2.5 h-6 rounded-[3px] text-[11px] font-medium transition-colors"
          style="background: var(--color-ide-accent); color: #fff;"
          :disabled="!newTaskName.trim() || !newTaskCmd.trim()"
          @click="addTask"
        >添加</button>
      </div>
    </div>

    <!-- ═══ 任务列表 (按分组) ═══ -->
    <div class="flex-1 overflow-y-auto py-0.5">
      <template v-for="[group, groupTasks] in groups" :key="group">
        <!-- 分组标题 -->
        <button
          class="flex items-center gap-1.5 w-full h-7 px-3 text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          @click="toggleGroup(group)"
        >
          <ChevronRight
            :size="10"
            class="transition-transform duration-150"
            :class="{ 'rotate-90': !collapsedGroups[group] }"
            style="color: var(--color-ide-text-dim);"
          />
          <component :is="groupIcons[group]" :size="12" style="color: var(--color-ide-text-dim); opacity: 0.6;" />
          <span class="text-[11px] font-semibold uppercase tracking-wider"
            style="color: var(--color-ide-text-dim);">
            {{ groupLabels[group] || group }}
          </span>
          <span class="text-[10px] opacity-50 ml-auto" style="color: var(--color-ide-text-dim);">
            {{ groupTasks.length }}
          </span>
        </button>

        <!-- 任务项 -->
        <div v-if="!collapsedGroups[group]">
          <div
            v-for="task in groupTasks"
            :key="task.id"
            class="task-item flex items-center gap-2 px-5 h-7 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors group"
            @dblclick="runTask(task)"
          >
            <!-- 状态图标 -->
            <RotateCw
              v-if="task.status === 'running'"
              :size="12" class="animate-spin shrink-0"
              style="color: var(--color-ide-accent);"
            />
            <CheckCircle2
              v-else-if="task.status === 'success'"
              :size="12" class="shrink-0"
              style="color: var(--color-ide-success);"
            />
            <XCircle
              v-else-if="task.status === 'failed'"
              :size="12" class="shrink-0"
              style="color: var(--color-ide-error);"
            />
            <Play
              v-else
              :size="11" class="shrink-0"
              style="color: var(--color-ide-text-dim); opacity: 0.4;"
            />

            <!-- 任务名 -->
            <span class="flex-1 truncate text-[12px]" :style="{ color: task.status === 'running' ? 'var(--color-ide-accent)' : 'var(--color-ide-text)' }">
              {{ task.name }}
            </span>

            <!-- 类型标签 -->
            <span class="shrink-0 text-[9px] px-1.5 py-0 rounded-full font-medium"
              style="background: var(--color-ide-surface-active); color: var(--color-ide-text-dim);">
              {{ task.type }}
            </span>

            <!-- 问题匹配器图标 -->
            <span v-if="task.problemMatcher" class="shrink-0" title="问题匹配器已配置">
              <Bug :size="9" style="color: var(--color-ide-warning); opacity: 0.5;" />
            </span>

            <!-- hover 操作 -->
            <div class="hidden group-hover:flex items-center gap-0.5 shrink-0">
              <button
                v-if="task.status === 'running'"
                class="w-5 h-5 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-active)]"
                title="停止"
                @click.stop="stopTask(task)"
              >
                <Square :size="9" style="color: var(--color-ide-error);" />
              </button>
              <button
                v-else
                class="w-5 h-5 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-active)]"
                title="运行任务"
                @click.stop="runTask(task)"
              >
                <Play :size="9" style="color: var(--color-ide-text-dim);" />
              </button>
              <button
                v-if="!task.isAutoDetected"
                class="w-5 h-5 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-active)]"
                title="删除任务"
                @click.stop="removeTask(task)"
              >
                <Trash2 :size="9" style="color: var(--color-ide-error);" />
              </button>
            </div>
          </div>
        </div>
      </template>

      <!-- 空状态 -->
      <div v-if="tasks.length === 0" class="flex flex-col items-center justify-center py-16 gap-2">
        <Cog :size="24" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
          未检测到任务
        </span>
        <button
          class="mt-2 px-4 py-1.5 rounded-[3px] text-[12px] font-medium transition-colors"
          style="background: var(--color-ide-accent); color: #fff;"
          @click="showAddTask = true"
        >配置任务</button>
      </div>
    </div>

    <!-- ═══ 底部操作栏 ═══ -->
    <div class="shrink-0 flex items-center justify-between px-3 h-7 text-[11px]"
      style="border-top: 1px solid var(--color-ide-border); background: var(--color-ide-bg-secondary); color: var(--color-ide-text-dim);">
      <span>{{ tasks.length }} 个任务</span>
      <button
        class="flex items-center gap-1 hover:text-[var(--color-ide-text)] transition-colors"
        title="运行所有构建任务"
      >
        <RotateCw :size="10" /> 全部运行
      </button>
    </div>
  </div>
</template>

<style scoped>
.task-item {
  border-left: 2px solid transparent;
}
.task-item:hover {
  border-left-color: var(--color-ide-accent);
}
</style>
