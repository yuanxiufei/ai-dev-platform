/**
 * useTasksStore — VSCode Tasks 任务系统
 *
 * 借鉴: VSCode src/vs/workbench/contrib/tasks/
 * 能力:
 *   - 管理构建/测试/监听任务
 *   - 任务配置 (command, args, cwd, env)
 *   - 运行/停止任务
 *   - 任务输出记录
 *   - tasks.json 风格模板
 */
import { defineStore } from "pinia"
import { ref, computed } from "vue"
import { v4 as uuid } from "uuid"
import { useIDEStore } from "./useIDEStore"

export interface TaskDefinition {
  id: string
  label: string
  type: "shell" | "process" | "npm" | "gulp" | "grunt" | "jake" | "tsc" | "custom"
  command: string
  args?: string[]
  cwd?: string
  env?: Record<string, string>
  group?: "build" | "test" | "clean" | "watch" | "none"
  isBackground?: boolean
  dependsOn?: string[]
  presentation?: {
    reveal?: "always" | "silent" | "never"
    panel?: "shared" | "dedicated" | "new"
    clear?: boolean
  }
}

export interface TaskRun {
  id: string
  taskId: string
  label: string
  startTime: number
  endTime?: number
  status: "running" | "success" | "failed" | "killed"
  output: string[]
  exitCode?: number
}

/** 内置任务模板 */
const DEFAULT_TASKS: TaskDefinition[] = [
  {
    id: uuid(), label: "npm: install",
    type: "npm", command: "install",
    group: "build",
    presentation: { reveal: "always", panel: "shared", clear: true },
  },
  {
    id: uuid(), label: "npm: dev",
    type: "npm", command: "run dev",
    group: "watch", isBackground: true,
    presentation: { reveal: "always", panel: "dedicated" },
  },
  {
    id: uuid(), label: "npm: build",
    type: "npm", command: "run build",
    group: "build",
    presentation: { reveal: "always", panel: "shared" },
  },
  {
    id: uuid(), label: "npm: test",
    type: "npm", command: "run test",
    group: "test",
    presentation: { reveal: "always", panel: "shared" },
  },
  {
    id: uuid(), label: "npm: lint",
    type: "npm", command: "run lint",
    group: "test",
    presentation: { reveal: "silent", panel: "shared" },
  },
  {
    id: uuid(), label: "python: run main.py",
    type: "shell", command: "python main.py",
    group: "none",
    presentation: { reveal: "always", panel: "shared" },
  },
]

export const useTasksStore = defineStore("tasks", () => {
  const tasks = ref<TaskDefinition[]>([])
  const runs = ref<TaskRun[]>([])
  const activeTaskId = ref<string | null>(null)
  const outputVisible = ref(false)

  const tasksByGroup = computed(() => {
    const groups: Record<string, TaskDefinition[]> = { build: [], test: [], watch: [], clean: [], none: [] }
    for (const t of tasks.value) {
      (groups[t.group ?? "none"] ??= []).push(t)
    }
    return groups
  })

  const runningTasks = computed(() => runs.value.filter(r => r.status === "running"))

  function init(): void {
    if (tasks.value.length === 0) {
      tasks.value = [...DEFAULT_TASKS]
    }
  }

  function addTask(task: Omit<TaskDefinition, "id">): TaskDefinition {
    const t: TaskDefinition = { id: uuid(), ...task }
    tasks.value.push(t)
    return t
  }

  function removeTask(id: string): void {
    tasks.value = tasks.value.filter(t => t.id !== id)
    runs.value = runs.value.filter(r => r.taskId !== id)
  }

  function updateTask(id: string, patch: Partial<TaskDefinition>): void {
    const idx = tasks.value.findIndex(t => t.id === id)
    if (idx !== -1) Object.assign(tasks.value[idx], patch)
  }

  function startTask(taskId: string): TaskRun {
    const task = tasks.value.find(t => t.id === taskId)
    if (!task) throw new Error(`Task not found: ${taskId}`)

    const run: TaskRun = {
      id: uuid(),
      taskId,
      label: task.label,
      startTime: Date.now(),
      status: "running",
      output: [`> Executing task: ${task.command} ${(task.args ?? []).join(" ")}\n`],
    }
    runs.value.unshift(run)
    activeTaskId.value = taskId
    outputVisible.value = true

    // 模拟任务执行
    setTimeout(() => {
      const success = Math.random() > 0.15
      run.output.push(...[
        `[task] ${task.command} starting...`,
        `[task] Working directory: ${task.cwd || process.cwd()}`,
        ...(task.env ? [`[task] Environment: ${JSON.stringify(task.env)}`] : []),
      ])

      // 模拟输出
      for (let i = 0; i < 3; i++) {
        setTimeout(() => {
          run.output.push(`[output] Line ${i + 1}: processing...`)
        }, 300 * i)
      }

      setTimeout(() => {
        if (success) {
          run.output.push(`[success] Task completed successfully.`)
          run.status = "success"
          run.exitCode = 0
        } else {
          run.output.push(`[error] Task failed with exit code 1`)
          run.output.push(`[error] Error: Something went wrong during execution`)
          run.status = "failed"
          run.exitCode = 1
        }
        run.endTime = Date.now()
        if (activeTaskId.value === taskId) activeTaskId.value = null
      }, 1500)
    }, 200)

    return run
  }

  function stopTask(runId: string): void {
    const run = runs.value.find(r => r.id === runId)
    if (!run || run.status !== "running") return
    run.status = "killed"
    run.output.push("[killed] Task was terminated by user")
    run.endTime = Date.now()
    run.exitCode = -1
    if (activeTaskId.value === run.taskId) activeTaskId.value = null
  }

  function clearRuns(): void {
    runs.value = []
  }

  return {
    tasks, runs, activeTaskId, outputVisible,
    tasksByGroup, runningTasks,
    init, addTask, removeTask, updateTask,
    startTask, stopTask, clearRuns,
  }
})
