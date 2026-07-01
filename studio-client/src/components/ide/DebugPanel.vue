<script setup lang="ts">
/**
 * DebugPanel.vue — VSCode 风格调试面板
 *
 * 借鉴 VSCode src/vs/workbench/contrib/debug/browser/
 *   - debugToolBar   : 继续/单步跳过/单步进入/单步跳出/重启/停止
 *   - variablesView  : 本地变量/全局/监视表达式
 *   - callStackView  : 线程 + 调用栈帧列表
 *   - breakpointsView: 全部断点列表 (文件+行号+条件)
 *
 * Session 24: 独立 DebugPanel 组件，注册到底部面板
 */
import { computed, ref, watch, onMounted, onUnmounted, type Ref } from "vue"
import {
  Play, Pause, SkipForward, ArrowDownToLine,
  ArrowUpFromLine, RotateCcw, Square,
  CircleDot, X, Plus, Trash2, Eye, Triangle,
} from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"
import type { EditorTab } from "@/types/ide"

const store = useIDEStore()

// ── 断点类型定义 ──
interface Breakpoint {
  id: string
  file: string
  line: number
  /** 断点是否启用 */
  enabled: boolean
  /** 条件断点 (可选) */
  condition?: string
  /** 命中计数 (可选) */
  hitCount?: number
}

interface StackFrame {
  id: number
  name: string
  file: string
  line: number
  column: number
  /** 是否为外部库 */
  isExternal?: boolean
}

interface WatchExpression {
  id: string
  expression: string
  value?: string
  type?: string
}

interface Variable {
  name: string
  value: string
  type: string
  children?: Variable[]
  expanded?: boolean
}

// ── 调试状态 ──
const isRunning = ref(false)
const isPaused = ref(false)
const breakpoints: Ref<Breakpoint[]> = ref([])
const stackFrames: Ref<StackFrame[]> = ref([])
const variables: Ref<Variable[]> = ref([])
const watchExpressions: Ref<WatchExpression[]> = ref([])
const activeStackFrame = ref<number | null>(null)

// ── 折叠状态 ──
const variablesExpanded = ref(true)
const watchExpanded = ref(true)
const callStackExpanded = ref(true)
const breakpointsExpanded = ref(true)

// ── 新增监视 ──
const newWatchExpr = ref("")
function addWatch() {
  const expr = newWatchExpr.value.trim()
  if (!expr) return
  watchExpressions.value.push({
    id: `watch-${Date.now()}`,
    expression: expr,
    value: undefined,
    type: undefined,
  })
  newWatchExpr.value = ""
  evaluateWatch()
}
function removeWatch(id: string) {
  watchExpressions.value = watchExpressions.value.filter(w => w.id !== id)
}
function evaluateWatch() {
  // TODO: 实际评估需要连接到调试器后端
  for (const w of watchExpressions.value) {
    if (!w.value) {
      w.value = "<未在调试会话中>"
      w.type = "string"
    }
  }
}

// ── 变量树展开 ──
function toggleVariable(v: Variable) {
  v.expanded = !v.expanded
}

// ── 断点管理 ──
function addBreakpoint(file: string, line: number, condition?: string): void {
  const id = `bp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
  breakpoints.value.push({ id, file, line, enabled: true, condition, hitCount: 0 })
}

function removeBreakpoint(id: string): void {
  breakpoints.value = breakpoints.value.filter(bp => bp.id !== id)
}

function toggleBreakpoint(id: string): void {
  const bp = breakpoints.value.find(b => b.id === id)
  if (bp) bp.enabled = !bp.enabled
}

function removeAllBreakpoints(): void {
  breakpoints.value = []
}

function toggleAllBreakpoints(): void {
  const allEnabled = breakpoints.value.every(b => b.enabled)
  breakpoints.value.forEach(b => { b.enabled = !allEnabled })
}

// ── 跳转到断点文件 ──
function gotoBreakpointLocation(bp: Breakpoint) {
  store.openFile(bp.file)
  // TODO: scroll to line
}

// ── 调试控制动作 ──
function startDebug() {
  isRunning.value = true
  isPaused.value = false
  // 模拟断点命中
  setTimeout(() => {
    pauseDebug()
  }, 2000)
}
function pauseDebug() {
  isRunning.value = true
  isPaused.value = true
  // 模拟调用栈
  stackFrames.value = [
    { id: 0, name: "handleClick", file: "src/App.vue", line: 42, column: 15 },
    { id: 1, name: "onClick", file: "src/components/Button.vue", line: 128, column: 5 },
    { id: 2, name: "invokeGuardedCallback", file: "node_modules/react-dom/cjs/...", line: 405, column: 1, isExternal: true },
  ]
  activeStackFrame.value = 0
  variables.value = [
    { name: "event", value: "MouseEvent {...}", type: "MouseEvent", children: [
      { name: "clientX", value: "320", type: "number" },
      { name: "clientY", value: "180", type: "number" },
      { name: "target", value: "button.btn-primary", type: "HTMLElement" },
    ]},
    { name: "props", value: "{ title: 'Submit', disabled: false }", type: "object" },
    { name: "this", value: "Component {...}", type: "object" },
  ]
}
function resumeDebug() {
  isPaused.value = false
  stackFrames.value = []
  variables.value = []
  activeStackFrame.value = null
}
function stepOver() {
  if (!isPaused.value) return
  // 模拟单步跳过到下一行
  if (stackFrames.value.length > 0) {
    stackFrames.value[0].line += 1
  }
}
function stepInto() {
  if (!isPaused.value) return
  // 模拟进入函数
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
function stepOut() {
  if (!isPaused.value || stackFrames.value.length <= 1) return
  stackFrames.value.shift()
  activeStackFrame.value = 0
}
function stopDebug() {
  isRunning.value = false
  isPaused.value = false
  stackFrames.value = []
  variables.value = []
  activeStackFrame.value = null
}
function restartDebug() {
  stopDebug()
  setTimeout(() => startDebug(), 100)
}

// ── 从当前编辑器文件添加断点 ──
function addBreakpointAtCurrentLine() {
  const tab = store.activeTab
  if (!tab?.filePath) return
  const line = store.cursorPosition.line
  const exists = breakpoints.value.some(bp => bp.file === tab.filePath && bp.line === line)
  if (exists) {
    breakpoints.value = breakpoints.value.filter(bp => !(bp.file === tab.filePath && bp.line === line))
  } else {
    addBreakpoint(tab.filePath, line)
  }
}

// ── 文件路径缩略 ──
function shortPath(p: string): string {
  const parts = p.split(/[/\\]/)
  if (parts.length <= 2) return p
  return parts.slice(-2).join("/")
}

// ── 排序: 启用的在前，按文件→行号 ──
const sortedBreakpoints = computed(() =>
  [...breakpoints.value].sort((a, b) => {
    if (a.enabled !== b.enabled) return a.enabled ? -1 : 1
    if (a.file !== b.file) return a.file.localeCompare(b.file)
    return a.line - b.line
  }),
)

// ── 按文件分组的断点 ──
const breakpointGroups = computed(() => {
  const map = new Map<string, Breakpoint[]>()
  for (const bp of sortedBreakpoints.value) {
    if (!map.has(bp.file)) map.set(bp.file, [])
    map.get(bp.file)!.push(bp)
  }
  return Array.from(map.entries())
})

// 监听 Ctrl+Shift+D 快捷键(在外部处理)
// 暴露 API 给外部
defineExpose({
  addBreakpoint,
  removeBreakpoint,
  removeAllBreakpoints,
  toggleAllBreakpoints,
  addBreakpointAtCurrentLine,
  startDebug,
  stopDebug,
  breakpoints,
  isRunning,
  isPaused,
})

// ── 样式常量 ──
const BG = "var(--color-ide-bg)"
const BG_SECONDARY = "var(--color-ide-bg-secondary)"
const BORDER = "var(--color-ide-border)"
const TEXT = "var(--color-ide-text)"
const TEXT_DIM = "var(--color-ide-text-dim)"
const ACCENT = "var(--color-ide-accent)"
const SURFACE_HOVER = "var(--color-ide-surface-hover)"
const ERROR = "var(--color-ide-error)"
const WARNING = "var(--color-ide-warning)"
const INFO = "var(--color-ide-info)"
</script>

<template>
  <div class="debug-panel h-full flex flex-col" :style="{ background: BG }">
    <!-- ═══ Debug Toolbar (VSCode debugToolBar) ═══ -->
    <div
      class="debug-toolbar flex items-center shrink-0 px-2"
      :style="{ height: '36px', background: BG_SECONDARY, borderBottom: `1px solid ${BORDER}`, gap: '2px' }"
    >
      <!-- 继续 / 暂停 -->
      <button v-if="isPaused"
        class="debug-action-btn"
        :style="getBtnStyle(ACCENT, '10%')"
        title="继续 (F5)"
        @click="resumeDebug"
      >
        <Play :size="14" />
      </button>
      <button v-else-if="!isRunning"
        class="debug-action-btn"
        :style="getBtnStyle('#4EC9B0', '10%')"
        title="启动调试 (F5)"
        @click="startDebug"
      >
        <Play :size="14" />
      </button>
      <button v-else
        class="debug-action-btn"
        :style="getBtnStyle('#CCA700', '10%')"
        title="暂停 (F6)"
        @click="pauseDebug"
      >
        <Pause :size="14" />
      </button>

      <!-- Step Over -->
      <button class="debug-action-btn" :style="getBtnStyle()"
        title="单步跳过 (F10)"
        :disabled="!isPaused"
        @click="stepOver"
      >
        <SkipForward :size="14" />
      </button>

      <!-- Step Into -->
      <button class="debug-action-btn" :style="getBtnStyle()"
        title="单步进入 (F11)"
        :disabled="!isPaused"
        @click="stepInto"
      >
        <ArrowDownToLine :size="14" />
      </button>

      <!-- Step Out -->
      <button class="debug-action-btn" :style="getBtnStyle()"
        title="单步跳出 (Shift+F11)"
        :disabled="!isPaused"
        @click="stepOut"
      >
        <ArrowUpFromLine :size="14" />
      </button>

      <!-- Restart -->
      <button class="debug-action-btn" :style="getBtnStyle()"
        title="重新启动 (Ctrl+Shift+F5)"
        :disabled="!isRunning"
        @click="restartDebug"
      >
        <RotateCcw :size="14" />
      </button>

      <!-- Stop -->
      <button class="debug-action-btn"
        :style="getBtnStyle(ERROR, '10%')"
        title="停止 (Shift+F5)"
        :disabled="!isRunning"
        @click="stopDebug"
      >
        <Square :size="12" />
      </button>

      <div :style="{ width: '1px', height: '18px', background: BORDER, margin: '0 6px' }" />

      <!-- 当前调试状态 -->
      <span v-if="isPaused" class="text-[11px] font-medium"
        :style="{ color: '#CCA700' }"
      >
        已在断点处暂停
      </span>
      <span v-else-if="isRunning" class="text-[11px]"
        :style="{ color: '#4EC9B0' }"
      >
        调试中...
      </span>
      <span v-else class="text-[11px]" :style="{ color: TEXT_DIM }">
        未启动调试
      </span>
    </div>

    <!-- ═══ 调试内容区域 ═══ -->
    <div class="debug-content flex-1 overflow-y-auto" :style="{ fontSize: '12px' }">
      <!-- ── Variables 区域 ── -->
      <div class="debug-section" :style="{ borderBottom: `1px solid ${BORDER}` }">
        <button
          class="section-header flex items-center gap-1 w-full text-left px-3 py-1.5 font-semibold uppercase tracking-wide"
          :style="{
            background: BG_SECONDARY,
            color: TEXT,
            fontSize: '11px',
            letterSpacing: '0.4px',
            borderBottom: `1px solid ${BORDER}`,
          }"
          @click="variablesExpanded = !variablesExpanded"
        >
          <Triangle
            :size="8"
            :style="{
              transform: variablesExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 0.15s',
              color: TEXT_DIM,
            }"
          />
          变量
          <span v-if="variables.length > 0" class="ml-auto text-[10px] opacity-50">
            {{ variables.length }}
          </span>
        </button>
        <div v-if="variablesExpanded" class="py-1">
          <!-- 本地变量 -->
          <div v-if="variables.length === 0 && !isPaused" class="px-5 py-4 text-center" :style="{ color: TEXT_DIM, fontSize: '11px' }">
            暂停调试时显示变量
          </div>
          <div v-else-if="variables.length === 0" class="px-5 py-4 text-center" :style="{ color: TEXT_DIM, fontSize: '11px' }">
            当前作用域无变量
          </div>
          <div v-else>
            <div v-for="v in variables" :key="v.name" class="variable-row" :style="{ paddingLeft: '16px' }">
              <button class="variable-item w-full text-left flex items-center gap-1.5 px-2 py-0.5"
                :style="{
                  color: TEXT,
                  fontSize: '12px',
                  lineHeight: '22px',
                  cursor: v.children?.length ? 'pointer' : 'default',
                }"
                :class="v.children?.length ? 'hover:bg-white/5 rounded-sm' : ''"
                @click="v.children?.length && toggleVariable(v)"
              >
                <!-- 展开箭头 -->
                <span v-if="v.children?.length" class="shrink-0 inline-flex items-center justify-center"
                  :style="{ width: '14px', color: TEXT_DIM }"
                >
                  <Triangle
                    :size="7"
                    :style="{
                      transform: v.expanded ? 'rotate(90deg)' : 'rotate(0deg)',
                      transition: 'transform 0.12s',
                    }"
                  />
                </span>
                <span v-else class="shrink-0" :style="{ width: '14px' }" />
                <!-- 变量名 -->
                <span class="font-medium" :style="{ color: '#9CDCFE' }">{{ v.name }}</span>
                <span class="mx-1" :style="{ color: TEXT_DIM }">:</span>
                <!-- 类型 -->
                <span class="text-[11px] opacity-50 mr-1" :style="{ color: TEXT_DIM }">{{ v.type }}</span>
                <!-- 值 -->
                <span class="flex-1 truncate" :style="{ color: '#CE9178' }">= {{ v.value }}</span>
              </button>
              <!-- 子变量 -->
              <div v-if="v.children && v.expanded" class="ml-2 border-l" :style="{ borderColor: BORDER, marginLeft: '24px' }">
                <div v-for="child in v.children" :key="child.name" class="flex items-center gap-1.5 px-2 py-0.5"
                  :style="{ color: TEXT, fontSize: '12px', lineHeight: '22px' }"
                >
                  <span class="shrink-0" :style="{ width: '14px' }" />
                  <span :style="{ color: '#9CDCFE' }">{{ child.name }}</span>
                  <span :style="{ color: TEXT_DIM }">:</span>
                  <span class="opacity-50 text-[11px]" :style="{ color: TEXT_DIM }">{{ child.type }}</span>
                  <span :style="{ color: '#CE9178' }">= {{ child.value }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Watch 监视区 ── -->
      <div class="debug-section" :style="{ borderBottom: `1px solid ${BORDER}` }">
        <button
          class="section-header flex items-center gap-1 w-full text-left px-3 py-1.5 font-semibold uppercase tracking-wide"
          :style="{
            background: BG_SECONDARY,
            color: TEXT,
            fontSize: '11px',
            letterSpacing: '0.4px',
            borderBottom: `1px solid ${BORDER}`,
          }"
          @click="watchExpanded = !watchExpanded"
        >
          <Triangle
            :size="8"
            :style="{
              transform: watchExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 0.15s',
              color: TEXT_DIM,
            }"
          />
          监视
          <span v-if="watchExpressions.length > 0" class="ml-auto text-[10px] opacity-50">
            {{ watchExpressions.length }}
          </span>
        </button>
        <div v-if="watchExpanded">
          <!-- 新增监视输入框 -->
          <div class="flex items-center gap-1 px-2 py-1" :style="{ borderBottom: `1px solid ${BORDER}` }">
            <input
              v-model="newWatchExpr"
              class="flex-1 bg-transparent border-none outline-none text-[12px] px-1.5 py-0.5 rounded-sm"
              :style="{
                color: TEXT,
                background: 'rgba(255,255,255,0.05)',
              }"
              placeholder="添加监视表达式..."
              @keydown.enter="addWatch"
            />
            <button class="p-1 rounded-sm hover:bg-white/10 text-[11px]"
              :style="{ color: ACCENT }"
              @click="addWatch"
            >
              <Plus :size="12" />
            </button>
          </div>
          <!-- 监视列表 -->
          <div v-if="watchExpressions.length === 0" class="px-5 py-4 text-center" :style="{ color: TEXT_DIM, fontSize: '11px' }">
            无监视表达式
          </div>
          <div v-else>
            <div v-for="w in watchExpressions" :key="w.id"
              class="group flex items-center gap-1.5 px-3 py-0.5 hover:bg-white/5"
              :style="{ lineHeight: '22px' }"
            >
              <Eye :size="12" :style="{ color: TEXT_DIM }" />
              <span class="font-medium" :style="{ color: '#9CDCFE' }">{{ w.expression }}</span>
              <span v-if="w.value" class="ml-1">
                <span class="mx-1" :style="{ color: TEXT_DIM }">=</span>
                <span :style="{ color: '#CE9178' }">{{ w.value }}</span>
              </span>
              <button class="ml-auto opacity-0 group-hover:opacity-60 hover:opacity-100 p-0.5"
                title="移除监视"
                @click="removeWatch(w.id)"
              >
                <X :size="10" :style="{ color: TEXT_DIM }" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Call Stack 调用栈 ── -->
      <div class="debug-section" :style="{ borderBottom: `1px solid ${BORDER}` }">
        <button
          class="section-header flex items-center gap-1 w-full text-left px-3 py-1.5 font-semibold uppercase tracking-wide"
          :style="{
            background: BG_SECONDARY,
            color: TEXT,
            fontSize: '11px',
            letterSpacing: '0.4px',
            borderBottom: `1px solid ${BORDER}`,
          }"
          @click="callStackExpanded = !callStackExpanded"
        >
          <Triangle
            :size="8"
            :style="{
              transform: callStackExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 0.15s',
              color: TEXT_DIM,
            }"
          />
          调用堆栈
          <span v-if="stackFrames.length > 0" class="ml-auto text-[10px] opacity-50">
            {{ stackFrames.length }}
          </span>
        </button>
        <div v-if="callStackExpanded">
          <div v-if="stackFrames.length === 0" class="px-5 py-4 text-center" :style="{ color: TEXT_DIM, fontSize: '11px' }">
            暂停调试时显示调用堆栈
          </div>
          <div v-else>
            <!-- 线程信息 -->
            <div class="px-3 py-1 flex items-center gap-1.5 text-[11px]" :style="{ color: TEXT_DIM, borderBottom: `1px solid ${BORDER}` }">
              <CircleDot :size="9" :style="{ color: '#4EC9B0' }" />
              主线程 (Thread 1)
            </div>
            <!-- 栈帧列表 -->
            <div
              v-for="frame in stackFrames"
              :key="frame.id"
              class="stack-frame-item flex items-start gap-1.5 px-3 py-1 cursor-pointer"
              :style="{
                color: frame.id === activeStackFrame ? TEXT : TEXT_DIM,
                background: frame.id === activeStackFrame ? 'var(--color-ide-surface-active)' : 'transparent',
                borderLeft: frame.id === activeStackFrame ? `2px solid ${ACCENT}` : '2px solid transparent',
                fontSize: '12px',
                lineHeight: '20px',
                opacity: frame.isExternal ? 0.5 : 1,
              }"
              :title="`${frame.file}:${frame.line}`"
              @click="activeStackFrame = frame.id"
            >
              <Triangle
                v-if="frame.id === activeStackFrame"
                :size="10"
                class="shrink-0 mt-1"
                :style="{ color: ACCENT, transform: 'rotate(90deg)' }"
              />
              <span v-else class="shrink-0" :style="{ width: '10px' }" />
              <div class="min-w-0">
                <div class="font-medium truncate" :style="{ color: '#DCDCAA' }">{{ frame.name }}</div>
                <div class="text-[10px] opacity-60 truncate">
                  {{ shortPath(frame.file) }}:{{ frame.line }}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Breakpoints 断点区 ── -->
      <div class="debug-section">
        <div class="section-header flex items-center px-3 py-1.5"
          :style="{
            background: BG_SECONDARY,
            color: TEXT,
            fontSize: '11px',
            letterSpacing: '0.4px',
            borderBottom: `1px solid ${BORDER}`,
          }"
        >
          <button
            class="flex items-center gap-1 font-semibold uppercase tracking-wide"
            @click="breakpointsExpanded = !breakpointsExpanded"
          >
            <Triangle
              :size="8"
              :style="{
                transform: breakpointsExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                transition: 'transform 0.15s',
                color: TEXT_DIM,
              }"
            />
            断点
          </button>
          <span class="ml-auto text-[10px] opacity-50">{{ breakpoints.length }}</span>
          <!-- 操作按钮 -->
          <div class="flex items-center gap-0.5 ml-2" v-if="breakpoints.length > 0">
            <button
              class="px-1.5 py-0.5 rounded-sm text-[10px] hover:bg-white/10"
              :style="{ color: TEXT_DIM }"
              title="全部启用/禁用"
              @click="toggleAllBreakpoints"
            >
              {{ breakpoints.every(b => b.enabled) ? '全部禁用' : '全部启用' }}
            </button>
            <button
              class="px-1 py-0.5 rounded-sm hover:text-red-400"
              :style="{ color: TEXT_DIM }"
              title="删除所有断点"
              @click="removeAllBreakpoints"
            >
              <Trash2 :size="11" />
            </button>
          </div>
        </div>
        <div v-if="breakpointsExpanded">
          <div v-if="breakpoints.length === 0" class="px-5 py-4 text-center" :style="{ color: TEXT_DIM, fontSize: '11px' }">
            未设置断点
          </div>
          <div v-else>
            <template v-for="[file, bps] in breakpointGroups" :key="file">
              <!-- 文件头 -->
              <div class="flex items-center px-3 py-0.5 text-[11px]"
                :style="{ color: TEXT_DIM, borderBottom: `1px solid ${BORDER}`, opacity: 0.7 }"
              >
                <span class="truncate">{{ shortPath(file) }}</span>
              </div>
              <!-- 断点项 -->
              <div
                v-for="bp in bps"
                :key="bp.id"
                class="group flex items-center gap-1.5 px-3 py-0.5 hover:bg-white/5 cursor-pointer"
                :style="{
                  lineHeight: '22px',
                  opacity: bp.enabled ? 1 : 0.4,
                }"
                @click="gotoBreakpointLocation(bp)"
              >
                <!-- 启用/禁用复选框 -->
                <button
                  class="shrink-0 p-0.5"
                  @click.stop="toggleBreakpoint(bp.id)"
                  :style="{ color: bp.enabled ? ERROR : TEXT_DIM }"
                >
                  <CircleDot :size="14" v-if="bp.enabled" />
                  <CircleDot :size="14" v-else :style="{ color: TEXT_DIM, opacity: 0.4 }" />
                </button>
                <!-- 行号 + 文件 -->
                <span class="font-medium text-[11px]" :style="{ color: bp.enabled ? TEXT : TEXT_DIM }">
                  行 {{ bp.line }}
                </span>
                <!-- 条件标签 -->
                <span v-if="bp.condition"
                  class="px-1 py-0 rounded text-[9px]"
                  :style="{ background: 'rgba(251,191,36,0.15)', color: WARNING }"
                >
                  {{ bp.condition }}
                </span>
                <!-- 删除 -->
                <button
                  class="ml-auto opacity-0 group-hover:opacity-60 hover:opacity-100 p-0.5"
                  @click.stop="removeBreakpoint(bp.id)"
                >
                  <X :size="10" :style="{ color: TEXT_DIM }" />
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 底部状态栏 ═══ -->
    <div
      class="shrink-0 flex items-center px-2 text-[10px]"
      :style="{
        height: '22px',
        background: BG_SECONDARY,
        color: TEXT_DIM,
        borderTop: `1px solid ${BORDER}`,
        gap: '6px',
      }"
    >
      <span>
        {{ breakpoints.filter(b => b.enabled).length }}/{{ breakpoints.length }} 个断点已启用
      </span>
      <span v-if="isPaused" :style="{ color: '#CCA700' }">⚠ 已暂停</span>
      <span v-if="isRunning && !isPaused" :style="{ color: '#4EC9B0' }">▶ 运行中</span>
    </div>
  </div>
</template>

<script lang="ts">
/** 按钮样式辅助函数 */
function getBtnStyle(color?: string, bgAlpha?: string) {
  const base: Record<string, string> = {
    width: "28px",
    height: "28px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "4px",
    border: "none",
    cursor: "pointer",
    color: "var(--color-ide-text-dim)",
    background: "transparent",
    transition: "background 0.15s, color 0.15s",
  }
  if (color && bgAlpha) {
    base.color = color
    base.background = color.replace(")", `,${bgAlpha})`).replace("rgb", "rgba")
  }
  return base
}
</script>

<style scoped>
.debug-action-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1) !important;
  color: var(--color-ide-text) !important;
}
.debug-action-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.stack-frame-item:hover {
  background: var(--color-ide-surface-hover) !important;
}
</style>
