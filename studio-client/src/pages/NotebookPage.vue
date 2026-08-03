<script setup lang="ts">
/**
 * Notebook 页面 — 多语言代码单元执行
 * 支持: Python3 / JavaScript(Node.js) / Shell / SQLite
 */
import { ref, reactive, onMounted, computed, nextTick } from 'vue'
import {
  Play, Square, Plus, Trash2, ChevronUp, ChevronDown,
  Terminal, Zap, Clock, CheckCircle2, XCircle, Loader2,
  Code2, FileCode, Database, Monitor, RefreshCw, Copy,
  Info, Check, AlertTriangle,
} from 'lucide-vue-next'
import { notebookApi, type KernelInfo, type CellExecuteResponse } from '@/api/notebook'

/* ── 类型 ── */
interface Cell {
  id: string
  code: string
  kernel: string
  result: CellExecuteResponse | null
  running: boolean
}

/* ── 状态 ── */
const kernels = ref<KernelInfo[]>([])
const cells = ref<Cell[]>([])
const runningAll = ref(false)
const error = ref('')
const copiedId = ref('')
let cellCounter = 1

/* ── 可用 Kernel ── */
const availableKernels = computed(() => kernels.value.filter(k => k.available))
const kernelMap = computed(() => {
  const map: Record<string, KernelInfo> = {}
  for (const k of kernels.value) map[k.id] = k
  return map
})

/* ── 数据加载 ── */
async function loadKernels() {
  error.value = ''
  try {
    kernels.value = await notebookApi.listKernels()
    if (cells.value.length === 0) addCell()
  } catch (e: any) {
    error.value = e?.message || '无法加载 Kernel 列表'
  }
}

/* ── Cell 管理 ── */
function addCell(afterIndex?: number) {
  const cell: Cell = {
    id: `cell-${cellCounter++}`,
    code: '',
    kernel: 'python3',
    result: null,
    running: false,
  }
  if (afterIndex !== undefined) {
    cells.value.splice(afterIndex + 1, 0, cell)
  } else {
    cells.value.push(cell)
  }
  nextTick(() => {
    const last = document.querySelector(`[data-cell-id="${cell.id}"] textarea`) as HTMLTextAreaElement
    last?.focus()
  })
}

function removeCell(index: number) {
  if (cells.value.length <= 1) return
  cells.value.splice(index, 1)
}

function moveCell(index: number, direction: -1 | 1) {
  const newIndex = index + direction
  if (newIndex < 0 || newIndex >= cells.value.length) return
  const [cell] = cells.value.splice(index, 1)
  cells.value.splice(newIndex, 0, cell)
}

function clearResult(index: number) {
  cells.value[index].result = null
}

function clearAllResults() {
  for (const c of cells.value) c.result = null
}

/* ── 执行 ── */
async function runCell(index: number) {
  const cell = cells.value[index]
  if (cell.running) return
  cell.running = true
  cell.result = null
  error.value = ''

  try {
    const result = await notebookApi.executeCell({
      code: cell.code,
      kernel: cell.kernel,
      cell_id: cell.id,
    })
    cell.result = result
  } catch (e: any) {
    cell.result = {
      cell_id: cell.id,
      success: false,
      output: '',
      error: e?.response?.data?.detail || e?.message || '执行失败',
      duration_ms: 0,
      kernel: cell.kernel,
    }
  } finally {
    cell.running = false
  }
}

async function runAll() {
  runningAll.value = true
  error.value = ''
  const validCells = cells.value.filter(c => c.code.trim())

  if (validCells.length === 0) {
    error.value = '没有可执行的 Cell'
    runningAll.value = false
    return
  }

  const batchReq = {
    cells: validCells.map(c => ({
      code: c.code,
      kernel: c.kernel,
      cell_id: c.id,
    })),
  }

  try {
    const batchResult = await notebookApi.executeBatch(batchReq)
    for (const result of batchResult.results) {
      const cell = cells.value.find(c => c.id === result.cell_id)
      if (cell) cell.result = result
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '批量执行失败'
  } finally {
    runningAll.value = false
  }
}

function stopCell(index: number) {
  // subprocess 无法优雅中断，仅标记
  cells.value[index].running = false
}

/* ── 工具函数 ── */
function copyOutput(text: string, cellId: string) {
  navigator.clipboard.writeText(text)
  copiedId.value = cellId
  setTimeout(() => { copiedId.value = '' }, 2000)
}

function kernelIcon(k: KernelInfo): any {
  const map: Record<string, any> = {
    python: FileCode, python3: FileCode,
    javascript: Code2, js: Code2, node: Code2,
    shell: Terminal, bash: Terminal,
    sqlite: Database, sql: Database,
  }
  return map[k.id] || Code2
}

function kernelColor(id: string): string {
  const map: Record<string, string> = {
    python3: '#3572A5', python: '#3572A5',
    javascript: '#f1e05a', js: '#f1e05a',
    shell: '#89e051', bash: '#89e051',
    sqlite: '#003b57', sql: '#003b57',
  }
  return map[id] || '#6c5ce7'
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms.toFixed(1)}ms`
  return `${(ms / 1000).toFixed(2)}s`
}
</script>

<template>
  <div class="notebook-page">
    <!-- 头部 -->
    <div class="page-header">
      <div class="header-left">
        <Zap class="header-icon" :size="24" />
        <div>
          <h1 class="page-title">笔记执行器</h1>
          <p class="page-subtitle">多语言代码单元，实时执行 &middot; Python · JS · Shell · SQLite</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn-secondary" @click="clearAllResults" :disabled="!cells.some(c => c.result)">
          <RefreshCw :size="14" />
          <span>清除输出</span>
        </button>
        <button class="btn-secondary" @click="loadKernels">
          <RefreshCw :size="14" />
          <span>重载 Kernel</span>
        </button>
        <button
          class="btn-primary"
          @click="runAll"
          :disabled="runningAll || cells.every(c => !c.code.trim())"
        >
          <Loader2 v-if="runningAll" :size="16" class="spinning" />
          <Play v-else :size="16" />
          <span>全部执行</span>
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-banner">
      <AlertTriangle :size="14" />
      <span>{{ error }}</span>
      <button @click="error = ''">&times;</button>
    </div>

    <!-- 主内容区: 左侧 Kernels + 右侧 Cell 区 -->
    <div class="notebook-layout">
      <!-- 左侧 Kernel 面板 -->
      <aside class="kernel-panel">
        <h3 class="panel-title">可用 Kernel</h3>
        <div class="kernel-list">
          <div
            v-for="k in kernels"
            :key="k.id"
            :class="['kernel-item', { unavailable: !k.available }]"
          >
            <div class="kernel-icon" :style="{ background: kernelColor(k.id) + '20', color: kernelColor(k.id) }">
              <component :is="kernelIcon(k)" :size="18" />
            </div>
            <div class="kernel-info">
              <span class="kernel-name">{{ k.name }}</span>
              <span class="kernel-desc">{{ k.description }}</span>
              <span v-if="k.version" class="kernel-ver">{{ k.version }}</span>
            </div>
            <span v-if="k.available" class="kernel-status available">
              <CheckCircle2 :size="12" />
            </span>
            <span v-else class="kernel-status unavailable">
              <XCircle :size="12" />
            </span>
          </div>
        </div>

        <!-- 快捷代码模板 -->
        <div class="templates-section">
          <h3 class="panel-title">快捷模板</h3>
          <div class="template-list">
            <button class="template-btn" @click="addCell(cells.length); nextTick(() => { const c = cells[cells.length-1]; c.kernel='python3'; c.code='# Hello World\nprint(\"Hello, Notebook!\")' })">
              <FileCode :size="13" />
              <span>Python Hello</span>
            </button>
            <button class="template-btn" @click="addCell(cells.length); nextTick(() => { const c = cells[cells.length-1]; c.kernel='javascript'; c.code='// Hello World\nconsole.log(\"Hello, Notebook!\");' })">
              <Code2 :size="13" />
              <span>JS Hello</span>
            </button>
            <button class="template-btn" @click="addCell(cells.length); nextTick(() => { const c = cells[cells.length-1]; c.kernel='shell'; c.code='# List files\necho \"Current dir:\"\nls -la' })">
              <Terminal :size="13" />
              <span>Shell ls</span>
            </button>
            <button class="template-btn" @click="addCell(cells.length); nextTick(() => { const c = cells[cells.length-1]; c.kernel='sqlite'; c.code='-- Sample table\nCREATE TABLE IF NOT EXISTS demo (id INTEGER, name TEXT);\nINSERT INTO demo VALUES (1, \"alice\"), (2, \"bob\");\nSELECT * FROM demo;' })">
              <Database :size="13" />
              <span>SQLite demo</span>
            </button>
          </div>
        </div>
      </aside>

      <!-- 右侧 Cell 区域 -->
      <main class="cells-area">
        <!-- 无 Cell 空状态 -->
        <div v-if="cells.length === 0" class="empty-state">
          <Monitor :size="40" class="empty-icon" />
          <p>暂无可执行的 Cell</p>
          <button class="btn-primary" @click="addCell()">
            <Plus :size="14" />
            <span>添加 Cell</span>
          </button>
        </div>

        <!-- Cell 列表 -->
        <TransitionGroup name="cell-list" tag="div" class="cell-list">
          <div
            v-for="(cell, idx) in cells"
            :key="cell.id"
            :data-cell-id="cell.id"
            :class="['cell-card', { running: cell.running }]"
          >
            <!-- Cell 头部工具栏 -->
            <div class="cell-header">
              <div class="cell-left">
                <span class="cell-index">[{{ idx + 1 }}]</span>
                <select v-model="cell.kernel" class="kernel-select">
                  <option v-for="k in availableKernels" :key="k.id" :value="k.id">
                    {{ k.name }}
                  </option>
                </select>
                <span
                  class="kernel-dot"
                  :style="{ background: kernelColor(cell.kernel) }"
                />
              </div>
              <div class="cell-right">
                <button
                  class="cell-action-btn"
                  title="向上移动"
                  @click="moveCell(idx, -1)"
                  :disabled="idx === 0"
                >
                  <ChevronUp :size="14" />
                </button>
                <button
                  class="cell-action-btn"
                  title="向下移动"
                  @click="moveCell(idx, 1)"
                  :disabled="idx === cells.length - 1"
                >
                  <ChevronDown :size="14" />
                </button>
                <button
                  class="cell-action-btn"
                  title="清除输出"
                  @click="clearResult(idx)"
                  :disabled="!cell.result"
                >
                  <RefreshCw :size="13" />
                </button>
                <button
                  v-if="!cell.running"
                  class="cell-action-btn run-btn"
                  title="执行此 Cell"
                  @click="runCell(idx)"
                  :disabled="!cell.code.trim()"
                >
                  <Play :size="14" />
                </button>
                <button
                  v-else
                  class="cell-action-btn stop-btn"
                  title="停止执行"
                  @click="stopCell(idx)"
                >
                  <Square :size="14" />
                </button>
                <button
                  v-if="cells.length > 1"
                  class="cell-action-btn delete-btn"
                  title="删除 Cell"
                  @click="removeCell(idx)"
                >
                  <Trash2 :size="13" />
                </button>
              </div>
            </div>

            <!-- 代码编辑器 -->
            <div class="code-editor-wrap">
              <textarea
                v-model="cell.code"
                class="code-textarea"
                :placeholder="`输入 ${kernelMap[cell.kernel]?.name || cell.kernel} 代码...`"
                spellcheck="false"
                :disabled="cell.running"
              />
            </div>

            <!-- 执行中指示 -->
            <div v-if="cell.running" class="exec-indicator">
              <Loader2 :size="14" class="spinning" />
              <span>执行中...</span>
            </div>

            <!-- 执行结果 -->
            <div v-if="cell.result" :class="['result-panel', cell.result.success ? 'success' : 'error']">
              <div class="result-header">
                <div class="result-status">
                  <CheckCircle2 v-if="cell.result.success" :size="14" class="status-icon success-icon" />
                  <XCircle v-else :size="14" class="status-icon error-icon" />
                  <span>{{ cell.result.success ? '成功' : '失败' }}</span>
                  <span class="result-kernel-badge" :style="{ background: kernelColor(cell.kernel) + '20', color: kernelColor(cell.kernel) }">
                    {{ cell.kernel }}
                  </span>
                </div>
                <div class="result-meta">
                  <span v-if="cell.result.duration_ms" class="result-time">
                    <Clock :size="12" />
                    {{ formatMs(cell.result.duration_ms) }}
                  </span>
                  <button
                    class="icon-btn"
                    title="复制输出"
                    @click="copyOutput(cell.result.error || cell.result.output, cell.id)"
                  >
                    <Check v-if="copiedId === cell.id" :size="13" class="copied-mark" />
                    <Copy v-else :size="13" />
                  </button>
                </div>
              </div>
              <pre class="result-content">{{ cell.result.output || cell.result.error || '(无输出)' }}</pre>
            </div>

            <!-- Cell 间分隔 + 添加按钮 -->
            <div class="cell-separator">
              <button class="add-between-btn" title="在下方添加 Cell" @click="addCell(idx)">
                <Plus :size="12" />
              </button>
            </div>
          </div>
        </TransitionGroup>

        <!-- 底部添加按钮 -->
        <div class="bottom-add">
          <button class="add-bottom-btn" @click="addCell()">
            <Plus :size="16" />
            <span>添加 Cell</span>
          </button>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
/* ── 页面布局 ── */
.notebook-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 头部 ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-ide-border, #333);
  flex-shrink: 0;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.header-icon { color: #ff6b6b; }
.page-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--color-ide-fg, #e0e0e0);
  margin: 0;
}
.page-subtitle {
  font-size: 12px;
  color: var(--color-ide-fg-dim, #888);
  margin: 2px 0 0 0;
}
.header-actions {
  display: flex;
  gap: 8px;
}

/* ── 按钮 ── */
.btn-primary, .btn-secondary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all .2s;
  border: 1px solid transparent;
}
.btn-primary {
  background: var(--color-ide-accent, #6c5ce7);
  color: #fff;
}
.btn-primary:hover { opacity: .9; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-secondary {
  background: var(--color-ide-bg-secondary, #1e1e1e);
  color: var(--color-ide-fg, #e0e0e0);
  border-color: var(--color-ide-border, #333);
}
.btn-secondary:hover { border-color: var(--color-ide-accent, #6c5ce7); }
.btn-secondary:disabled { opacity: .4; cursor: not-allowed; }

/* ── 错误提示 ── */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 20px;
  background: rgba(255,68,68,.1);
  border-bottom: 1px solid rgba(255,68,68,.2);
  color: #ff6b6b;
  font-size: 13px;
}
.error-banner button {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 16px;
}

/* ── 主布局 ── */
.notebook-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

/* ── 左侧 Kernel 面板 ── */
.kernel-panel {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid var(--color-ide-border, #333);
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-ide-fg-dim, #888);
  text-transform: uppercase;
  letter-spacing: .5px;
  margin: 0;
}
.kernel-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.kernel-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  transition: opacity .2s;
}
.kernel-item.unavailable { opacity: .4; }
.kernel-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.kernel-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.kernel-name { font-size: 13px; font-weight: 600; color: var(--color-ide-fg, #e0e0e0); }
.kernel-desc { font-size: 11px; color: var(--color-ide-fg-dim, #888); }
.kernel-ver { font-size: 10px; color: var(--color-ide-fg-dim, #888); font-family: monospace; }
.kernel-status { flex-shrink: 0; }
.kernel-status.available { color: #2ecc71; }
.kernel-status.unavailable { color: #e74c3c; }

/* ── 模板区 ── */
.templates-section {
  border-top: 1px solid var(--color-ide-border, #333);
  padding-top: 12px;
}
.template-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 8px;
}
.template-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--color-ide-fg-dim, #aaa);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  transition: all .2s;
}
.template-btn:hover {
  background: var(--color-ide-bg-secondary, #1e1e1e);
  border-color: var(--color-ide-border, #333);
  color: var(--color-ide-fg, #e0e0e0);
}

/* ── Cell 区域 ── */
.cells-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  min-width: 0;
}
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 0;
  color: var(--color-ide-fg-dim, #888);
}
.empty-icon { opacity: .2; }
.cell-list {
  display: flex;
  flex-direction: column;
}

/* ── Cell 卡片 ── */
.cell-card {
  background: var(--color-ide-bg-secondary, #1e1e1e);
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 10px;
  overflow: hidden;
  transition: border-color .2s;
}
.cell-card:hover { border-color: var(--color-ide-fg-dim, #555); }
.cell-card.running {
  border-color: var(--color-ide-accent, #6c5ce7);
  box-shadow: 0 0 8px rgba(108, 92, 231, .15);
}

/* ── Cell 头部 ── */
.cell-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: var(--color-ide-bg, #252525);
  border-bottom: 1px solid var(--color-ide-border, #333);
}
.cell-left, .cell-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cell-index {
  font-size: 11px;
  color: var(--color-ide-fg-dim, #888);
  font-family: monospace;
  font-weight: 600;
}
.kernel-select {
  padding: 3px 8px;
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 4px;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  color: var(--color-ide-fg, #e0e0e0);
  font-size: 12px;
  outline: none;
}
.kernel-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.cell-action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--color-ide-fg-dim, #888);
  cursor: pointer;
  transition: all .15s;
}
.cell-action-btn:hover { background: var(--color-ide-bg-secondary, #1e1e1e); color: var(--color-ide-fg, #e0e0e0); }
.cell-action-btn:disabled { opacity: .3; cursor: not-allowed; }
.run-btn { color: #2ecc71; }
.run-btn:hover { background: rgba(46,204,113,.1); color: #2ecc71; }
.stop-btn { color: #e74c3c; }
.stop-btn:hover { background: rgba(231,76,60,.1); }
.delete-btn:hover { background: rgba(231,76,60,.1); color: #e74c3c; }

/* ── 代码编辑器 ── */
.code-editor-wrap {
  padding: 10px 12px;
}
.code-textarea {
  width: 100%;
  min-height: 80px;
  padding: 10px;
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 6px;
  background: var(--color-ide-bg, #252525);
  color: var(--color-ide-fg, #e0e0e0);
  font-family: 'Fira Code', 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  tab-size: 4;
}
.code-textarea:focus { border-color: var(--color-ide-accent, #6c5ce7); }
.code-textarea:disabled { opacity: .6; }

/* ── 执行指示 ── */
.exec-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(108, 92, 231, .08);
  color: var(--color-ide-accent, #6c5ce7);
  font-size: 12px;
}

/* ── 结果面板 ── */
.result-panel {
  border-top: 1px solid var(--color-ide-border, #333);
}
.result-panel.success { border-top-color: rgba(46,204,113,.3); }
.result-panel.error { border-top-color: rgba(231,76,60,.3); }
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: var(--color-ide-bg, #252525);
}
.result-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-ide-fg, #e0e0e0);
}
.success-icon { color: #2ecc71; }
.error-icon { color: #e74c3c; }
.result-kernel-badge {
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
}
.result-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.result-time {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  color: var(--color-ide-fg-dim, #888);
}
.icon-btn {
  display: flex;
  align-items: center;
  background: none;
  border: none;
  color: var(--color-ide-fg-dim, #888);
  cursor: pointer;
  padding: 2px;
}
.icon-btn:hover { color: var(--color-ide-fg, #e0e0e0); }
.copied-mark { color: #2ecc71; }

.result-content {
  margin: 0;
  padding: 12px;
  font-family: 'Fira Code', 'JetBrains Mono', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-ide-fg, #e0e0e0);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 400px;
  overflow-y: auto;
  background: var(--color-ide-bg, #252525);
}

/* ── Cell 分隔器 ── */
.cell-separator {
  position: relative;
  height: 1px;
  margin: 0 12px;
}
.add-between-btn {
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 12px;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  color: var(--color-ide-fg-dim, #888);
  cursor: pointer;
  opacity: 0;
  transition: all .2s;
}
.cell-separator:hover .add-between-btn,
.cell-card:last-child .cell-separator .add-between-btn { opacity: 1; }
.add-between-btn:hover {
  border-color: var(--color-ide-accent, #6c5ce7);
  color: var(--color-ide-accent, #6c5ce7);
}

/* ── 底部添加 ── */
.bottom-add {
  display: flex;
  justify-content: center;
  padding: 16px 0 8px;
}
.add-bottom-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 24px;
  border: 1px dashed var(--color-ide-border, #444);
  border-radius: 8px;
  background: transparent;
  color: var(--color-ide-fg-dim, #888);
  font-size: 13px;
  cursor: pointer;
  transition: all .2s;
}
.add-bottom-btn:hover {
  border-color: var(--color-ide-accent, #6c5ce7);
  color: var(--color-ide-accent, #6c5ce7);
}

/* ── 动画 ── */
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.cell-list-enter-active { transition: all .3s ease; }
.cell-list-leave-active { transition: all .2s ease; }
.cell-list-enter-from { opacity: 0; transform: translateY(-10px); }
.cell-list-leave-to { opacity: 0; transform: translateY(10px); }
</style>
