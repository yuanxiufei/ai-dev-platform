<script setup lang="ts">
/**
 * TestingPanel — VS Code Testing View (测试资源管理器)
 *
 * 功能对齐 VS Code Testing API:
 *   - 测试树结构 (Directory > File > Suite > Test Case)
 *   - 测试状态: passed / failed / skipped / running
 *   - 运行/调试单个测试、全部测试
 *   - 测试输出面板
 *   - 测试覆盖率统计
 *   - 按状态筛选 (all / failed / passed)
 *   - 测试搜索过滤
 *
 * Session 50: 对接 /system/testing/discover + /system/testing/run 后端 API，
 * 替换硬编码 mock 数据为真实测试发现和执行
 */
import { ref, computed, onMounted } from "vue"
import {
  FlaskConical, Play, Bug, RotateCw, ChevronRight, ChevronDown,
  CheckCircle2, XCircle, SkipForward, Circle, Clock, BarChart3,
  Filter, Search, X, FileText, FolderOpen, TestTube2, RefreshCw,
} from "lucide-vue-next"

// ── 测试类型 ──
interface TestCase {
  id: string
  name: string
  file: string
  status: "passed" | "failed" | "skipped" | "running" | "idle"
  duration?: number  // ms
  errorMessage?: string
  errorStack?: string
  line?: number
}

interface TestSuite {
  id: string
  name: string
  file: string
  cases: TestCase[]
  collapsed: boolean
  status: "passed" | "failed" | "skipped" | "running" | "idle"
}

interface TestFile {
  path: string
  name: string
  suites: TestSuite[]
  collapsed: boolean
}

// ── API 辅助 ──
function getApiBase(): string {
  return (window as any).__apiBaseUrl || '/api/v1'
}

// ── 测试数据 (Session 50: 由 API 填充) ──
const testFiles = ref<TestFile[]>([])
const framework = ref<string>('auto')
const discovering = ref(false)

// ── 搜索与筛选 ──
const searchQuery = ref("")
const statusFilter = ref<"all" | "failed" | "passed">("all")
const running = ref(false)
const selectedTestCase = ref<TestCase | null>(null)

// ── 展开/折叠 ──
function toggleFile(path: string): void {
  const f = testFiles.value.find(f => f.path === path)
  if (f) f.collapsed = !f.collapsed
}

function toggleSuite(suiteId: string): void {
  for (const f of testFiles.value) {
    const s = f.suites.find(s => s.id === suiteId)
    if (s) { s.collapsed = !s.collapsed; break }
  }
}

// ── 计算统计 ──
const allCases = computed(() => {
  const cases: TestCase[] = []
  for (const f of testFiles.value)
    for (const s of f.suites)
      cases.push(...s.cases)
  return cases
})

const stats = computed(() => {
  const total = allCases.value.length
  const passed = allCases.value.filter(c => c.status === "passed").length
  const failed = allCases.value.filter(c => c.status === "failed").length
  const skipped = allCases.value.filter(c => c.status === "skipped").length
  return { total, passed, failed, skipped }
})

// ── 过滤后的测试文件 ──
const filteredFiles = computed(() => {
  // 按搜索词过滤
  let files = testFiles.value
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    files = files.filter(f => {
      const matchFile = f.name.toLowerCase().includes(q)
      const matchCase = f.suites.some(s =>
        s.cases.some(c => c.name.toLowerCase().includes(q))
      )
      return matchFile || matchCase
    })
  }

  // 按状态筛选
  if (statusFilter.value !== "all") {
    files = files.map(f => ({
      ...f,
      suites: f.suites.map(s => ({
        ...s,
        cases: s.cases.filter(c => c.status === statusFilter.value),
      })).filter(s => s.cases.length > 0),
    })).filter(f => f.suites.length > 0)
  }

  return files
})

// ── Session 50: 测试发现 ──
async function discoverTests(): Promise<void> {
  discovering.value = true
  try {
    const baseUrl = getApiBase()
    const resp = await fetch(`${baseUrl}/system/testing/discover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: '.', framework: 'auto' }),
    })
    if (resp.ok) {
      const data = await resp.json()
      framework.value = data.framework || 'auto'
      testFiles.value = (data.files || []).map((f: any) => ({
        path: f.path,
        name: f.name,
        collapsed: false,
        suites: (f.suites || []).map((s: any) => ({
          id: s.id,
          name: s.name,
          file: s.file_path || f.path,
          collapsed: true,
          status: 'idle',
          cases: (s.cases || []).map((c: any) => ({
            id: c.id,
            name: c.name,
            file: c.file_path || f.path,
            status: c.status || 'idle',
            duration: c.duration_ms || 0,
            errorMessage: c.error_message || '',
            errorStack: c.error_stack || '',
            line: c.line || 0,
          })),
        })),
      }))
    }
  } catch { /* 静默 */ }
  finally { discovering.value = false }
}

onMounted(() => { discoverTests() })

// ── Session 50: 真实测试执行 ──
async function runAllTests(): Promise<void> {
  running.value = true
  for (const f of testFiles.value)
    for (const s of f.suites)
      for (const c of s.cases)
        c.status = "running"

  try {
    const baseUrl = getApiBase()
    const resp = await fetch(`${baseUrl}/system/testing/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: '.', framework: framework.value }),
    })
    if (resp.ok) {
      const data = await resp.json()
      const results: any[] = data.results?.results || []
      _applyResults(results)
    }
  } catch { /* 静默 */ }
  finally { running.value = false }
}

async function runFile(file: TestFile): Promise<void> {
  running.value = true
  for (const s of file.suites)
    for (const c of s.cases)
      c.status = "running"

  try {
    const baseUrl = getApiBase()
    const resp = await fetch(`${baseUrl}/system/testing/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: '.', framework: framework.value, file_path: file.path }),
    })
    if (resp.ok) {
      const data = await resp.json()
      _applyResults(data.results?.results || [])
    }
  } catch { /* 静默 */ }
  finally { running.value = false }
}

async function runTest(testCase: TestCase): Promise<void> {
  testCase.status = "running"
  try {
    const baseUrl = getApiBase()
    const resp = await fetch(`${baseUrl}/system/testing/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_path: '.', framework: framework.value, test_ids: [testCase.id] }),
    })
    if (resp.ok) {
      const data = await resp.json()
      _applyResults(data.results?.results || [])
    }
  } catch { /* 静默 */ }
}

function _applyResults(results: any[]): void {
  for (const r of results) {
    for (const f of testFiles.value) {
      for (const s of f.suites) {
        for (const c of s.cases) {
          if (c.name === r.name || c.id === r.id) {
            c.status = r.status
            c.duration = r.duration_ms || 0
            c.errorMessage = r.error_message || ''
            c.errorStack = r.error_stack || ''
          }
        }
        // 更新 suite 状态
        s.status = s.cases.some(c => c.status === 'failed') ? 'failed'
          : s.cases.every(c => c.status === 'passed') ? 'passed'
          : s.cases.some(c => c.status === 'skipped') ? 'skipped' : 'idle'
      }
    }
  }
}

// ── 状态图标 ──
function statusIcon(status: string): string {
  switch (status) {
    case "passed": return "check-circle"
    case "failed": return "x-circle"
    case "skipped": return "skip-forward"
    case "running": return "loader"
    default: return "circle"
  }
}

// ── 选中测试详情 ──
function selectTestCase(tc: TestCase): void {
  selectedTestCase.value = selectedTestCase.value?.id === tc.id ? null : tc
}
</script>

<template>
  <div class="testing-panel flex flex-col h-full" style="color: var(--color-ide-text); background: var(--color-ide-surface);">

    <!-- ═══ 控制栏 ═══ -->
    <div class="shrink-0 flex items-center gap-1 px-3 h-9" style="border-bottom: 1px solid var(--color-ide-border);">
      <!-- 🔥 全部运行按钮 -->
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors"
        :style="{ background: running ? 'var(--color-ide-surface-hover)' : 'var(--color-ide-accent)', color: running ? 'var(--color-ide-text-dim)' : '#FFFFFF' }"
        :disabled="running"
        @click="runAllTests"
      >
        <RotateCw v-if="running" :size="11" class="animate-spin" />
        <Play v-else :size="11" />
        {{ running ? '运行中...' : '运行测试' }}
      </button>

      <!-- 🔥 调试全部测试 -->
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        style="color: var(--color-ide-text-dim);"
        title="调试全部测试"
      >
        <Bug :size="11" /> 调试
      </button>

      <!-- 🔥 覆盖率 -->
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        style="color: var(--color-ide-text-dim);"
        title="测试覆盖率"
      >
        <BarChart3 :size="11" /> 覆盖率
      </button>

      <div class="flex-1" />

      <!-- 🔥 搜索 -->
      <div class="flex items-center gap-1 border rounded-[3px] overflow-hidden"
        :style="{ background: searchQuery.trim() ? 'var(--color-chat-input-bg)' : 'transparent', borderColor: searchQuery.trim() ? 'var(--color-ide-border-focus)' : 'transparent' }">
        <input
          v-model="searchQuery"
          type="text"
          class="flex-1 h-6 bg-transparent text-[11px] outline-none px-1.5"
          placeholder="筛选测试"
          style="width: 120px;"
        />
        <button v-if="searchQuery" class="shrink-0 w-5 h-6 flex items-center justify-center" @click="searchQuery = ''">
          <X :size="10" style="color: var(--color-ide-text-dim);" />
        </button>
      </div>

      <!-- 🔥 状态筛选 -->
      <button
        class="flex items-center gap-0.5 px-1.5 h-6 rounded-[3px] text-[11px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        :class="{ 'bg-[var(--color-ide-surface-active)]': statusFilter !== 'all' }"
        style="color: var(--color-ide-text-dim);"
        @click="statusFilter = statusFilter === 'all' ? 'failed' : statusFilter === 'failed' ? 'passed' : 'all'"
      >
        <Filter :size="11" />
        {{ statusFilter === 'all' ? '全部' : statusFilter === 'failed' ? '失败' : '通过' }}
      </button>
    </div>

    <!-- ═══ 统计栏 ═══ -->
    <div class="shrink-0 flex items-center gap-3 px-3 h-7 text-[11px]" style="border-bottom: 1px solid var(--color-ide-border);">
      <span style="color: var(--color-ide-text-dim);">
        测试: <strong style="color: var(--color-ide-text);">{{ stats.total }}</strong>
      </span>
      <span class="flex items-center gap-1" style="color: var(--color-ide-success);">
        <CheckCircle2 :size="11" /> {{ stats.passed }}
      </span>
      <span class="flex items-center gap-1" :style="{ color: stats.failed > 0 ? 'var(--color-ide-error)' : 'var(--color-ide-text-dim)' }">
        <XCircle :size="11" /> {{ stats.failed }}
      </span>
      <span class="flex items-center gap-1" style="color: var(--color-ide-text-dim);">
        <SkipForward :size="11" /> {{ stats.skipped }}
      </span>
    </div>

    <!-- ═══ 测试树 ═══ -->
    <div class="flex-1 overflow-y-auto min-h-0 py-0.5">
      <div v-if="filteredFiles.length === 0" class="flex flex-col items-center justify-center py-16 gap-2">
        <TestTube2 :size="28" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
          {{ searchQuery ? '没有匹配的测试' : '未发现测试文件' }}
        </span>
      </div>

      <template v-for="file in filteredFiles" :key="file.path">
        <!-- 🔥 文件节点 -->
        <button
          class="test-file-node flex items-center gap-1.5 w-full h-7 px-3 text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors group"
          @click="toggleFile(file.path)"
        >
          <ChevronRight
            v-if="file.collapsed"
            :size="12"
            style="color: var(--color-ide-text-dim); transition: transform 0.1s;"
          />
          <ChevronDown
            v-else
            :size="12"
            style="color: var(--color-ide-text-dim); transition: transform 0.1s;"
          />
          <FileText :size="12" style="color: var(--color-ide-text-dim); opacity: 0.6;" />
          <span class="text-[12px] font-medium truncate flex-1">{{ file.name }}</span>
          <!-- 🔥 运行单个文件 -->
          <span
            class="shrink-0 w-5 h-5 flex items-center justify-center rounded-[3px] opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[var(--color-ide-surface-active)]"
            role="button"
            tabindex="0"
            @click.stop="runFile(file)"
            @keydown.enter.stop="runFile(file)"
            @keydown.space.prevent.stop="runFile(file)"
            title="运行此文件中的测试"
          >
            <Play :size="10" style="color: var(--color-ide-text-dim);" />
          </span>
        </button>

        <!-- 🔥 Suite & Test Cases -->
        <div v-if="!file.collapsed">
          <template v-for="suite in file.suites" :key="suite.id">
            <!-- Suite 节点 -->
            <button
              class="test-suite-node flex items-center gap-1.5 w-full h-6 px-6 text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              @click="toggleSuite(suite.id)"
            >
              <ChevronRight
                v-if="suite.collapsed"
                :size="10"
                style="color: var(--color-ide-text-dim);"
              />
              <ChevronDown
                v-else
                :size="10"
                style="color: var(--color-ide-text-dim);"
              />
              <!-- 🔥 Suite status icon -->
              <CheckCircle2 v-if="suite.status === 'passed'" :size="11" style="color: var(--color-ide-success);" />
              <XCircle v-else-if="suite.status === 'failed'" :size="11" style="color: var(--color-ide-error);" />
              <SkipForward v-else-if="suite.status === 'skipped'" :size="11" style="color: var(--color-ide-text-dim);" />
              <RotateCw v-else-if="suite.status === 'running'" :size="11" class="animate-spin" style="color: var(--color-ide-accent);" />
              <Circle v-else :size="10" style="color: var(--color-ide-text-dim);" />
              <span class="text-[12px] truncate flex-1">{{ suite.name }}</span>
              <span class="text-[10px]" style="color: var(--color-ide-text-dim);">{{ suite.cases.length }}</span>
            </button>

            <!-- Test Cases -->
            <div v-if="!suite.collapsed">
              <div
                v-for="tc in suite.cases"
                :key="tc.id"
                class="test-case-node flex items-start gap-1.5 w-full px-9 py-0.5 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors"
                :class="{ 'bg-[var(--color-ide-surface-active)]': selectedTestCase?.id === tc.id }"
                @click="selectTestCase(tc)"
              >
                <!-- 🔥 状态图标 -->
                <CheckCircle2 v-if="tc.status === 'passed'" :size="11" class="shrink-0 mt-0.5" style="color: var(--color-ide-success);" />
                <XCircle v-else-if="tc.status === 'failed'" :size="11" class="shrink-0 mt-0.5" style="color: var(--color-ide-error);" />
                <SkipForward v-else-if="tc.status === 'skipped'" :size="11" class="shrink-0 mt-0.5" style="color: var(--color-ide-text-dim);" />
                <RotateCw v-else-if="tc.status === 'running'" :size="11" class="animate-spin shrink-0 mt-0.5" style="color: var(--color-ide-accent);" />
                <Circle v-else :size="10" class="shrink-0 mt-0.5" style="color: var(--color-ide-text-dim);" />

                <div class="flex-1 min-w-0">
                  <span class="text-[12px] truncate block">{{ tc.name }}</span>
                  <span v-if="tc.duration" class="text-[10px]" style="color: var(--color-ide-text-dim);">
                    {{ tc.duration }}ms · {{ tc.file }}
                  </span>
                </div>

                <!-- 运行单个测试 -->
                <div class="flex items-center gap-0.5 shrink-0 opacity-0 hover-parent:opacity-100">
                  <button
                    class="w-4 h-4 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-active)]"
                    @click.stop="runTest(tc)"
                    title="运行测试"
                  >
                    <Play :size="9" style="color: var(--color-ide-text-dim);" />
                  </button>
                </div>
              </div>
            </div>
          </template>
        </div>
      </template>
    </div>

    <!-- ═══ 测试输出 (当选中某个失败测试时) ═══ -->
    <div
      v-if="selectedTestCase?.status === 'failed'"
      class="shrink-0 max-h-40 overflow-y-auto"
      style="border-top: 1px solid var(--color-ide-border);"
    >
      <div class="flex items-center gap-2 px-3 h-7 text-[11px]"
        style="border-bottom: 1px solid var(--color-ide-border); background: var(--color-ide-bg-secondary);">
        <XCircle :size="11" style="color: var(--color-ide-error);" />
        <span class="font-semibold" style="color: var(--color-ide-error);">测试失败: {{ selectedTestCase.name }}</span>
        <button class="ml-auto w-4 h-4 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-hover)]"
          @click="selectedTestCase = null">
          <X :size="10" style="color: var(--color-ide-text-dim);" />
        </button>
      </div>
      <div class="p-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap"
        style="background: var(--color-terminal-bg); color: var(--color-ide-error);">
        {{ selectedTestCase.errorMessage }}
      </div>
      <div v-if="selectedTestCase.errorStack" class="px-3 pb-3 font-mono text-[11px] leading-relaxed whitespace-pre-wrap"
        style="background: var(--color-terminal-bg); color: var(--color-ide-text-dim);">
        {{ selectedTestCase.errorStack }}
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══ 测试树交互 ═══ */
.test-file-node,
.test-suite-node,
.test-case-node {
  border: none;
  background: transparent;
  cursor: default;
  outline: none;
}
.test-file-node:focus-visible,
.test-suite-node:focus-visible,
.test-case-node:focus-visible {
  outline: 1px solid var(--color-ide-border-focus);
  outline-offset: -1px;
}

.test-case-node .hover-parent\:opacity-100 {
  opacity: 0;
}
.test-case-node:hover .hover-parent\:opacity-100 {
  opacity: 1;
}
</style>
