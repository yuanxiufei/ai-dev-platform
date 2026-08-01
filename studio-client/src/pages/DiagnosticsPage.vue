<template>
  <div class="diagnostics-page">
    <div class="page-header">
      <h2>代码诊断</h2>
      <p class="subtitle">静态分析、错误检查、批量诊断</p>
    </div>

    <!-- 工具栏 -->
    <div class="toolbar">
      <div class="mode-switch">
        <button :class="['btn btn-sm', mode === 'single' ? 'btn-primary' : '']" @click="mode = 'single'">单文件</button>
        <button :class="['btn btn-sm', mode === 'batch' ? 'btn-primary' : '']" @click="mode = 'batch'">批量分析</button>
      </div>
      <span v-if="languages.length" class="lang-count">支持 {{ languages.length }} 种语言</span>
    </div>

    <!-- 单文件模式 -->
    <div v-if="mode === 'single'" class="panel">
      <div class="form-row">
        <input v-model="filePath" placeholder="文件路径 (可选)" class="input input-sm" />
        <select v-model="language" class="input input-sm">
          <option value="">自动检测</option>
          <option v-for="l in languages" :key="l" :value="l">{{ l }}</option>
        </select>
      </div>
      <textarea v-model="sourceCode" placeholder="粘贴代码或填写文件路径后自动读取..." class="code-input" rows="12"></textarea>
      <div class="btn-row">
        <button class="btn btn-primary" @click="runSingle" :disabled="analyzing">
          {{ analyzing ? '分析中...' : '分析' }}
        </button>
        <button class="btn btn-sm" @click="loadFile" :disabled="!filePath" v-if="filePath">读取文件</button>
      </div>
    </div>

    <!-- 批量模式 -->
    <div v-if="mode === 'batch'" class="panel">
      <div class="form-row">
        <input v-model="batchPattern" placeholder="文件模式 (如 src/**/*.py)" class="input" />
        <select v-model="batchLanguage" class="input input-sm">
          <option value="">自动检测</option>
          <option v-for="l in languages" :key="l" :value="l">{{ l }}</option>
        </select>
        <button class="btn btn-primary" @click="runBatch" :disabled="analyzing">
          {{ analyzing ? '分析中...' : '批量分析' }}
        </button>
      </div>
      <div v-if="batchFileList.length" class="file-selected-list">
        <span class="file-list-label">将分析 {{ batchFileList.length }} 个文件：</span>
        <span v-for="f in batchFileList.slice(0, 5)" :key="f" class="file-tag">{{ f }}</span>
        <span v-if="batchFileList.length > 5" class="file-tag">...还有 {{ batchFileList.length - 5 }} 个</span>
      </div>
    </div>

    <!-- 结果摘要 -->
    <div v-if="summary" class="summary-bar">
      <div class="summary-item error">
        <span class="sum-count">{{ summary.error }}</span><span class="sum-label">错误</span>
      </div>
      <div class="summary-item warn">
        <span class="sum-count">{{ summary.warning }}</span><span class="sum-label">警告</span>
      </div>
      <div class="summary-item info">
        <span class="sum-count">{{ summary.info }}</span><span class="sum-label">信息</span>
      </div>
    </div>

    <!-- 诊断列表 -->
    <div class="results-section" v-if="Object.keys(groupedDiagnostics).length">
      <div v-for="(items, file) in groupedDiagnostics" :key="file" class="file-block">
        <div class="file-block-header" @click="toggleDiagFile(file)">
          <span class="toggle-icon">{{ expandedDiag.has(file) ? '▼' : '▶' }}</span>
          <span class="file-block-name">{{ file }}</span>
          <span class="file-block-count">{{ items.length }} 条诊断</span>
        </div>
        <div v-if="expandedDiag.has(file)" class="diag-list">
          <div v-for="(d, di) in items" :key="di" :class="['diag-row', 'diag-' + d.severity]">
            <span class="diag-line">L{{ d.line }}:{{ d.column }}</span>
            <span :class="['diag-badge', d.severity]">{{ d.severity }}</span>
            <span class="diag-msg">{{ d.message }}</span>
            <span v-if="d.code" class="diag-code">{{ d.code }}</span>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="analyzed && !analyzing" class="empty">无诊断结果</div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { diagnosticsApi } from '@/api/diagnostics'
import type { DiagnosticItem } from '@/api/diagnostics'

const mode = ref('single')
const languages = ref<string[]>([])
const analyzing = ref(false)
const analyzed = ref(false)

// 单文件
const filePath = ref('')
const language = ref('')
const sourceCode = ref('')

// 批量
const batchPattern = ref('')
const batchLanguage = ref('')
const batchFileList = ref<string[]>([])

// 结果
const diagnostics = ref<DiagnosticItem[]>([])
const summary = ref<{ error: number; warning: number; info: number } | null>(null)
const expandedDiag = ref(new Set<string>())

const groupedDiagnostics = ref<Record<string, DiagnosticItem[]>>({})

function groupDiagnostics(items: DiagnosticItem[]) {
  const map: Record<string, DiagnosticItem[]> = {}
  for (const d of items) {
    const file = d.file || 'unknown'
    if (!map[file]) map[file] = []
    map[file].push(d)
  }
  return map
}

function toggleDiagFile(file: string) {
  const s = new Set(expandedDiag.value)
  if (s.has(file)) s.delete(file)
  else s.add(file)
  expandedDiag.value = s
}

async function fetchLanguages() {
  try {
    const res = await diagnosticsApi.listLanguages()
    languages.value = res.data?.languages ?? res.data ?? []
  } catch { /* empty */ }
}

async function loadFile() {
  if (!filePath.value) return
  try {
    // 使用 filesystem API 读取文件（通过内联引用）
    const { filesystemApi } = await import('@/api/filesystem')
    const res = await filesystemApi.readFile(filePath.value)
    sourceCode.value = typeof res.data === 'string' ? res.data : res.data?.content ?? ''
    language.value = ''
  } catch {
    alert('无法读取文件：' + filePath.value)
  }
}

async function runSingle() {
  if (!sourceCode.value.trim()) return
  analyzing.value = true
  analyzed.value = true
  expandedDiag.value.clear()
  try {
    const res = await diagnosticsApi.analyze({
      content: sourceCode.value,
      language: language.value || 'auto',
      file_path: filePath.value || undefined,
    })
    const data = res.data as any
    diagnostics.value = data.diagnostics ?? data ?? []
    summary.value = data.summary ?? {
      error: diagnostics.value.filter(d => d.severity === 'error').length,
      warning: diagnostics.value.filter(d => d.severity === 'warning').length,
      info: diagnostics.value.filter(d => d.severity === 'info').length,
    }
    groupedDiagnostics.value = groupDiagnostics(diagnostics.value)
    // 默认展开所有文件
    for (const f of Object.keys(groupedDiagnostics.value)) expandedDiag.value.add(f)
  } finally {
    analyzing.value = false
  }
}

async function runBatch() {
  if (!batchPattern.value.trim()) { alert('请输入文件模式'); return }
  analyzing.value = true
  analyzed.value = true
  expandedDiag.value.clear()
  try {
    // 先用搜索 API 找到匹配文件
    const { searchApi } = await import('@/api/search')
    const searchRes = await searchApi.fileSearch({ query: batchPattern.value } as any)
    const files = (searchRes.data?.files ?? searchRes.data ?? []).map((f: any) => f.path).filter(Boolean)
    batchFileList.value = files

    if (files.length === 0) { alert('未找到匹配的文件'); analyzing.value = false; return }

    // 批量诊断
    const req: any = {
      files: files.map((fp: string) => ({
        content: '', // 后端会自动读取
        language: batchLanguage.value || 'auto',
        file_path: fp,
      })),
    }
    const res = await diagnosticsApi.analyzeBatch(req)
    const data = res.data as any
    // 展开为扁平列表
    const allDiags: DiagnosticItem[] = []
    if (data.results) {
      for (const [file, result] of Object.entries(data.results)) {
        const r = result as any
        for (const d of (r.diagnostics ?? [])) {
          allDiags.push({ ...d, file: file as string })
        }
      }
    }
    diagnostics.value = allDiags
    summary.value = {
      error: diagnostics.value.filter(d => d.severity === 'error').length,
      warning: diagnostics.value.filter(d => d.severity === 'warning').length,
      info: diagnostics.value.filter(d => d.severity === 'info').length,
    }
    groupedDiagnostics.value = groupDiagnostics(diagnostics.value)
    for (const f of Object.keys(groupedDiagnostics.value)) expandedDiag.value.add(f)
  } finally {
    analyzing.value = false
  }
}

onMounted(() => fetchLanguages())
</script>

<style scoped>
.diagnostics-page { padding: 24px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; }
.subtitle { color: var(--color-ide-fg-secondary); margin: 4px 0 0; font-size: 13px; }

.toolbar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.mode-switch { display: flex; gap: 4px; }
.lang-count { font-size: 12px; color: var(--color-ide-fg-secondary); }

.panel { border: 1px solid var(--color-ide-border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.form-row { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.btn-row { display: flex; gap: 8px; margin-top: 10px; }

.code-input { width: 100%; font-family: monospace; font-size: 13px; background: var(--color-ide-bg-secondary); color: var(--color-ide-fg); border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 12px; resize: vertical; }

.file-selected-list { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; margin-top: 8px; }
.file-list-label { font-size: 12px; color: var(--color-ide-fg-secondary); }
.file-tag { font-size: 11px; background: var(--color-ide-bg-secondary); padding: 2px 8px; border-radius: 4px; border: 1px solid var(--color-ide-border); font-family: monospace; }

.summary-bar { display: flex; gap: 16px; margin-bottom: 20px; }
.summary-item { display: flex; align-items: center; gap: 6px; padding: 8px 14px; border-radius: 8px; }
.summary-item.error { background: #cf222e11; border: 1px solid #cf222e33; }
.summary-item.warn { background: #d4a72c11; border: 1px solid #d4a72c33; }
.summary-item.info { background: #4fc1ff11; border: 1px solid #4fc1ff33; }
.sum-count { font-size: 20px; font-weight: 700; }
.sum-label { font-size: 12px; color: var(--color-ide-fg-secondary); }

.results-section { margin-top: 12px; }

.file-block { border: 1px solid var(--color-ide-border); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
.file-block-header { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: var(--color-ide-bg-secondary); cursor: pointer; font-size: 13px; }
.file-block-header:hover { background: var(--color-ide-bg-hover, rgba(128,128,128,0.1)); }
.file-block-name { font-weight: 500; flex: 1; font-family: monospace; font-size: 12px; }
.file-block-count { font-size: 11px; color: var(--color-ide-fg-secondary); }
.toggle-icon { font-size: 10px; width: 14px; }

.diag-list { padding: 6px 0; }
.diag-row { display: flex; align-items: flex-start; gap: 8px; padding: 5px 14px; font-size: 13px; border-bottom: 1px solid var(--color-ide-border); }
.diag-row:last-child { border: none; }
.diag-row.diag-error { background: #cf222e08; }
.diag-row.diag-warning { background: #d4a72c08; }
.diag-line { font-family: monospace; font-size: 12px; color: var(--color-ide-fg-secondary); min-width: 50px; }
.diag-badge { padding: 1px 6px; border-radius: 8px; font-size: 10px; text-transform: uppercase; }
.diag-badge.error { background: #cf222e22; color: #cf222e; }
.diag-badge.warning { background: #d4a72c22; color: #d4a72c; }
.diag-badge.info { background: #4fc1ff22; color: #4fc1ff; }
.diag-msg { flex: 1; }
.diag-code { font-family: monospace; font-size: 11px; color: var(--color-ide-fg-secondary); white-space: nowrap; }

.empty { padding: 48px 0; text-align: center; color: var(--color-ide-fg-secondary); }

.input { background: var(--color-ide-bg-secondary); border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 6px 10px; font-size: 13px; color: var(--color-ide-fg); }
.input-sm { min-width: 120px; }
.btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--color-ide-border); background: var(--color-ide-bg); color: var(--color-ide-fg); }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent, #4fc1ff); color: #fff; border-color: var(--color-ide-accent, #4fc1ff); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
</style>
