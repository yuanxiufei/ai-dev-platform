/**
 * useDebugStore — VSCode Debug 状态共享 Store
 *
 * Session 36: 调试状态从 DebugPanel 组件局部分离到全局 store
 * Session 54: 接入后端 REST API (DAP 桥接)，API 不可用时回退 mock
 */

import { defineStore } from 'pinia'
import { ref, computed, type Ref } from 'vue'

// ── 类型定义 ──

export interface Breakpoint {
  id: string
  file: string
  line: number
  enabled: boolean
  condition?: string
  hitCount?: number
}

export interface StackFrame {
  id: number
  name: string
  file: string
  line: number
  column: number
  isExternal?: boolean
}

export interface WatchExpression {
  id: string
  expression: string
  value?: string
  type?: string
}

export interface DebugVariable {
  name: string
  value: string
  type: string
  children?: DebugVariable[]
  expanded?: boolean
}

export const useDebugStore = defineStore('debug', () => {
  // ── 核心状态 ──
  const isRunning = ref(false)
  const isPaused = ref(false)
  const breakpoints: Ref<Breakpoint[]> = ref([])
  const stackFrames: Ref<StackFrame[]> = ref([])
  const variables: Ref<DebugVariable[]> = ref([])
  const watchExpressions: Ref<WatchExpression[]> = ref([])
  const activeStackFrame = ref<number | null>(null)
  /** 后端调试会话 ID (API 模式时有效) */
  const sessionId = ref<string | null>(null)
  /** 是否使用后端 API (false 时走 mock) */
  const useApi = ref(true)

  // ── 折叠状态 ──
  const variablesExpanded = ref(true)
  const watchExpanded = ref(true)
  const callStackExpanded = ref(true)
  const breakpointsExpanded = ref(true)

  // ── Computed ──
  const sortedBreakpoints = computed(() =>
    [...breakpoints.value].sort((a, b) => {
      if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
      if (a.file !== b.file) return a.file.localeCompare(b.file)
      return a.line - b.line
    }),
  )

  const breakpointGroups = computed(() => {
    const map = new Map<string, Breakpoint[]>()
    for (const bp of sortedBreakpoints.value) {
      if (!map.has(bp.file)) map.set(bp.file, [])
      map.get(bp.file)!.push(bp)
    }
    return Array.from(map.entries())
  })

  // ── 辅助: 映射 API 数据到 Store 类型 ──

  function mapApiState(apiState: any): void {
    isRunning.value = apiState.is_running ?? true
    isPaused.value = apiState.is_paused ?? false
    if (apiState.stack_frames) {
      stackFrames.value = apiState.stack_frames.map((f: any) => ({
        id: f.id,
        name: f.name,
        file: f.file,
        line: f.line,
        column: f.column,
        isExternal: f.is_external ?? false,
      }))
    }
    if (apiState.variables) {
      variables.value = apiState.variables.map((v: any) => ({
        name: v.name,
        value: v.value,
        type: v.type,
        children: v.children ?? undefined,
      }))
    }
    if (apiState.active_frame_id != null) {
      activeStackFrame.value = apiState.active_frame_id
    }
  }

  // ── 调试控制动作 ──

  async function startDebug(config?: { workspaceRoot?: string; program?: string; type?: string }): Promise<void> {
    useApi.value = true
    isRunning.value = true
    isPaused.value = false

    try {
      const { startDebug: apiStart } = await import('@/api/debug')
      const result = await apiStart({
        workspace_root: config?.workspaceRoot ?? '.',
        program: config?.program ?? undefined,
        type: (config?.type as any) ?? 'python',
      })
      sessionId.value = result.session_id
      isPaused.value = result.is_paused ?? false
    } catch (e) {
      console.warn('[Debug] Backend API unavailable, falling back to mock:', e)
      useApi.value = false
      sessionId.value = null
      // Mock: 2 秒后模拟命中断点
      setTimeout(() => {
        pauseDebug()
      }, 2000)
    }
  }

  async function stopDebug(): Promise<void> {
    try {
      if (useApi.value && sessionId.value) {
        const { stopDebug: apiStop } = await import('@/api/debug')
        await apiStop(sessionId.value)
      }
    } catch (e) {
      console.warn('[Debug] Stop API failed:', e)
    } finally {
      sessionId.value = null
      isRunning.value = false
      isPaused.value = false
      stackFrames.value = []
      variables.value = []
      activeStackFrame.value = null
    }
  }

  function pauseDebug(): void {
    isRunning.value = true
    isPaused.value = true
    if (!useApi.value || !sessionId.value) {
      // Mock 数据
      stackFrames.value = [
        { id: 0, name: "handleClick", file: "src/App.vue", line: 42, column: 15 },
        { id: 1, name: "onClick", file: "src/components/Button.vue", line: 128, column: 5 },
        { id: 2, name: "invokeGuardedCallback", file: "node_modules/react-dom/...", line: 405, column: 1, isExternal: true },
      ]
      activeStackFrame.value = 0
      variables.value = [
        {
          name: "event", value: "MouseEvent {...}", type: "MouseEvent",
          children: [
            { name: "clientX", value: "320", type: "number" },
            { name: "clientY", value: "180", type: "number" },
            { name: "target", value: "button.btn-primary", type: "HTMLElement" },
          ],
        },
        { name: "props", value: "{ title: 'Submit', disabled: false }", type: "object" },
        { name: "this", value: "Component {...}", type: "object" },
      ]
    } else {
      // API 模式: 从后端拉取状态
      refreshDebugState()
    }
  }

  async function resumeDebug(): Promise<void> {
    try {
      if (useApi.value && sessionId.value) {
        const { continueDebug } = await import('@/api/debug')
        await continueDebug(sessionId.value)
        await refreshDebugState()
      } else {
        isPaused.value = false
        stackFrames.value = []
        variables.value = []
        activeStackFrame.value = null
      }
    } catch (e) {
      console.warn('[Debug] Resume failed:', e)
      isPaused.value = false
    }
  }

  async function stepOver(): Promise<void> {
    if (!isPaused.value) return
    try {
      if (useApi.value && sessionId.value) {
        const { stepOver: apiStepOver } = await import('@/api/debug')
        const result = await apiStepOver(sessionId.value)
        await refreshDebugState()
        // 更新当前行
        if (result.new_line && stackFrames.value.length > 0) {
          stackFrames.value[0].line = result.new_line
        }
      } else {
        if (stackFrames.value.length > 0) {
          stackFrames.value[0].line += 1
        }
      }
    } catch (e) {
      console.warn('[Debug] StepOver failed:', e)
      if (stackFrames.value.length > 0) stackFrames.value[0].line += 1
    }
  }

  async function stepInto(): Promise<void> {
    if (!isPaused.value) return
    try {
      if (useApi.value && sessionId.value) {
        const { stepInto: apiStepInto } = await import('@/api/debug')
        const result = await apiStepInto(sessionId.value)
        if (result.stack_frames) {
          stackFrames.value = result.stack_frames.map((f: any) => ({
            id: f.id, name: f.name, file: f.file, line: f.line, column: f.column, isExternal: f.is_external ?? false,
          }))
        }
        await refreshDebugState()
      } else {
        const frame = stackFrames.value[0]
        if (frame) {
          stackFrames.value.unshift({
            id: stackFrames.value.length,
            name: "innerFunction",
            file: frame.file,
            line: 1,
            column: 1,
          })
        }
      }
    } catch (e) {
      console.warn('[Debug] StepInto failed:', e)
    }
  }

  async function stepOut(): Promise<void> {
    if (!isPaused.value || stackFrames.value.length <= 1) return
    try {
      if (useApi.value && sessionId.value) {
        const { stepOut: apiStepOut } = await import('@/api/debug')
        const result = await apiStepOut(sessionId.value)
        if (result.stack_frames) {
          stackFrames.value = result.stack_frames.map((f: any) => ({
            id: f.id, name: f.name, file: f.file, line: f.line, column: f.column, isExternal: f.is_external ?? false,
          }))
        }
        await refreshDebugState()
      } else {
        stackFrames.value.shift()
        activeStackFrame.value = 0
      }
    } catch (e) {
      console.warn('[Debug] StepOut failed:', e)
    }
  }

  async function restartDebug(): Promise<void> {
    try {
      if (useApi.value && sessionId.value) {
        const { restartDebug: apiRestart } = await import('@/api/debug')
        const result = await apiRestart(sessionId.value)
        sessionId.value = result.session_id
        isRunning.value = true
        isPaused.value = false
        stackFrames.value = []
        variables.value = []
        activeStackFrame.value = null
      } else {
        await stopDebug()
        setTimeout(() => startDebug(), 100)
      }
    } catch (e) {
      console.warn('[Debug] Restart failed:', e)
      await stopDebug()
      setTimeout(() => startDebug(), 100)
    }
  }

  /** 从后端 API 刷新调试状态 */
  async function refreshDebugState(): Promise<void> {
    if (!sessionId.value) return
    try {
      const { getDebugState } = await import('@/api/debug')
      const state = await getDebugState(sessionId.value)
      mapApiState(state)
    } catch (e) {
      console.warn('[Debug] Refresh state failed:', e)
    }
  }

  // ── 断点管理 ──

  function addBreakpoint(file: string, line: number, condition?: string): void {
    const id = `bp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
    breakpoints.value.push({ id, file, line, enabled: true, condition, hitCount: 0 })
    syncBreakpointsToBackend()
  }

  function removeBreakpoint(id: string): void {
    breakpoints.value = breakpoints.value.filter(bp => bp.id !== id)
    syncBreakpointsToBackend()
  }

  function toggleBreakpoint(id: string): void {
    const bp = breakpoints.value.find(b => b.id === id)
    if (bp) { bp.enabled = !bp.enabled }
    syncBreakpointsToBackend()
  }

  function removeAllBreakpoints(): void {
    breakpoints.value = []
    syncBreakpointsToBackend()
  }

  function toggleAllBreakpoints(): void {
    const allEnabled = breakpoints.value.every(b => b.enabled)
    breakpoints.value.forEach(b => { b.enabled = !allEnabled })
    syncBreakpointsToBackend()
  }

  function addBreakpointAtLine(file: string, line: number): void {
    const exists = breakpoints.value.some(bp => bp.file === file && bp.line === line)
    if (exists) {
      breakpoints.value = breakpoints.value.filter(bp => !(bp.file === file && bp.line === line))
    } else {
      addBreakpoint(file, line)
    }
  }

  /** 同步断点到后端 (异步，静默失败) */
  async function syncBreakpointsToBackend(): Promise<void> {
    if (!useApi.value || !sessionId.value) return
    try {
      const { setBreakpoints } = await import('@/api/debug')
      await setBreakpoints(
        sessionId.value,
        breakpoints.value.map(bp => ({
          file: bp.file,
          line: bp.line,
          condition: bp.condition,
          enabled: bp.enabled,
        })),
      )
    } catch (e) {
      // 静默失败 — 断点在本地也有效
    }
  }

  // ── 监视表达式 ──

  function addWatch(expression: string): void {
    watchExpressions.value.push({
      id: `watch-${Date.now()}`,
      expression,
    })
  }

  function removeWatch(id: string): void {
    watchExpressions.value = watchExpressions.value.filter(w => w.id !== id)
  }

  /** 求值监视表达式 (API 模式) */
  async function evaluateWatch(expressionId: string): Promise<void> {
    const w = watchExpressions.value.find(w => w.id === expressionId)
    if (!w) return
    try {
      if (useApi.value && sessionId.value) {
        const { evaluate } = await import('@/api/debug')
        const result = await evaluate(
          sessionId.value,
          w.expression,
          activeStackFrame.value ?? undefined,
        )
        w.value = result.value
        w.type = result.type
      } else {
        // Mock 求值
        w.value = `(evaluated: ${w.expression})`
        w.type = 'string'
      }
    } catch (e) {
      w.value = `Error: ${e}`
      w.type = 'error'
    }
  }

  // ── 变量树展开 ──

  function toggleVariable(v: DebugVariable): void {
    v.expanded = !v.expanded
  }

  /** 展开变量子节点 (fetch children from backend) */
  async function expandVariable(v: DebugVariable, variablesRef: number = 0): Promise<void> {
    if (!sessionId.value) return
    try {
      const { getVariables } = await import('@/api/debug')
      const children = await getVariables(sessionId.value, variablesRef)
      v.children = children.map(c => ({ name: c.name, value: c.value, type: c.type }))
      v.expanded = true
    } catch (e) {
      console.warn('[Debug] Expand variable failed:', e)
    }
  }

  return {
    // 状态
    isRunning,
    isPaused,
    breakpoints,
    stackFrames,
    variables,
    watchExpressions,
    activeStackFrame,
    sessionId,
    // 折叠
    variablesExpanded,
    watchExpanded,
    callStackExpanded,
    breakpointsExpanded,
    // 计算
    sortedBreakpoints,
    breakpointGroups,
    // 调试控制
    startDebug,
    pauseDebug,
    resumeDebug,
    stepOver,
    stepInto,
    stepOut,
    stopDebug,
    restartDebug,
    refreshDebugState,
    // 断点管理
    addBreakpoint,
    removeBreakpoint,
    toggleBreakpoint,
    removeAllBreakpoints,
    toggleAllBreakpoints,
    addBreakpointAtLine,
    // 监视
    addWatch,
    removeWatch,
    evaluateWatch,
    // 变量
    toggleVariable,
    expandVariable,
  }
})
