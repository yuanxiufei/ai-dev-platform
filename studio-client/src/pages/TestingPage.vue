<template>
  <div class="testing-page">
    <div class="testing-toolbar">
      <h2>测试管理 (Test Runner)</h2>
      <div class="toolbar-actions">
        <select v-model="selectedFramework" class="framework-select">
          <option value="auto">自动检测</option>
          <option v-for="fw in frameworks" :key="fw" :value="fw">{{ fw }}</option>
        </select>
        <button class="btn-primary" @click="handleDiscover" :disabled="discovering">
          {{ discovering ? '扫描中...' : '发现测试' }}
        </button>
        <button class="btn-play" @click="handleRunAll" :disabled="running || testFiles.length === 0">
          ▶ 运行全部
        </button>
        <button class="btn-play" @click="handleRunSelected" :disabled="running || selectedIds.length === 0">
          ▶ 运行选中 ({{ selectedIds.length }})
        </button>
      </div>
    </div>

    <div class="testing-body">
      <!-- 文件/用例树 -->
      <div class="test-tree">
        <div v-if="testFiles.length === 0" class="empty-state">
          <p>点击「发现测试」扫描项目中的测试文件</p>
        </div>
        <div v-for="file in testFiles" :key="file.path" class="file-node">
          <div class="file-header" @click="toggleFile(file.path)">
            <span class="arrow">{{ expandedFiles[file.path] ? '▼' : '▶' }}</span>
            <span class="file-icon">🧪</span>
            <span class="file-name">{{ file.name }}</span>
            <span class="file-path">{{ file.path }}</span>
          </div>
          <div v-if="expandedFiles[file.path]" class="suite-list">
            <div v-for="(suite, si) in file.suites" :key="si" class="suite-node">
              <div class="suite-header" @click="toggleSuite(file.path, si)">
                <span class="arrow">{{ expandedSuites[`${file.path}-${si}`] ? '▼' : '▶' }}</span>
                <span class="suite-badge" :class="suite.status">{{ suite.status }}</span>
                <span class="suite-name">{{ suite.name }}</span>
                <span class="case-count">({{ suite.cases.length }})</span>
              </div>
              <div v-if="expandedSuites[`${file.path}-${si}`]" class="case-list">
                <div v-for="(tc, ci) in suite.cases" :key="tc.id" class="case-node" @click="toggleCase(tc.id)">
                  <input
                    type="checkbox"
                    :checked="selectedIds.has(tc.id)"
                    @click.stop
                    @change="toggleSelectCase(tc.id)"
                    class="case-checkbox"
                  />
                  <span class="case-badge" :class="tc.status">{{ tc.status === 'idle' ? '⏳' : tc.status === 'running' ? '🔄' : tc.status === 'passed' ? '✅' : tc.status === 'failed' ? '❌' : '⏭️' }}</span>
                  <span class="case-name">{{ tc.name }}</span>
                  <span class="case-duration" v-if="tc.duration_ms > 0">{{ tc.duration_ms }}ms</span>
                  <div v-if="expandedCases[tc.id] && tc.error_message" class="case-error">
                    <pre>{{ tc.error_message }}</pre>
                    <pre v-if="tc.error_stack" class="stack-trace">{{ tc.error_stack }}</pre>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 运行结果汇总 -->
      <div class="results-panel" v-if="lastResult">
        <h3>运行结果</h3>
        <div class="result-summary">
          <div class="stat total">总计: {{ lastResult.total }}</div>
          <div class="stat passed">✅ {{ lastResult.passed }}</div>
          <div class="stat failed">❌ {{ lastResult.failed }}</div>
          <div class="stat skipped">⏭️ {{ lastResult.skipped }}</div>
          <div class="stat duration">⏱ {{ lastResult.duration_ms }}ms</div>
        </div>
        <div class="failures" v-if="lastResult.failed > 0">
          <h4>失败用例:</h4>
          <div v-for="r in lastResult.results.filter(r => r.status === 'failed')" :key="r.id" class="failure-item">
            <strong>{{ r.name }}</strong> <span class="file-ref">{{ r.file_path }}:{{ r.line }}</span>
            <pre class="error-msg">{{ r.error_message }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from "vue"
import { testingApi, type TestFile, type TestRunResult } from "@/api/testing"

const frameworks = ref<string[]>([])
const selectedFramework = ref("auto")
const testFiles = ref<TestFile[]>([])
const discovering = ref(false)
const running = ref(false)
const expandedFiles = reactive<Record<string, boolean>>({})
const expandedSuites = reactive<Record<string, boolean>>({})
const expandedCases = reactive<Record<string, boolean>>({})
const selectedIds = reactive(new Set<string>())
const lastResult = ref<TestRunResult | null>(null)
const error = ref("")

onMounted(async () => {
  try {
    const res = await testingApi.listFrameworks()
    frameworks.value = res.data?.frameworks ?? []
  } catch {
    // 框架列表加载失败不影响主功能
  }
})

const handleDiscover = async () => {
  discovering.value = true
  error.value = ""
  try {
    const res = await testingApi.discover({
      project_path: undefined,
      framework: selectedFramework.value as any,
    })
    testFiles.value = res.data?.files ?? []
    // 默认折叠全部
    Object.keys(expandedFiles).forEach(k => delete expandedFiles[k])
    Object.keys(expandedSuites).forEach(k => delete expandedSuites[k])
    Object.keys(expandedCases).forEach(k => delete expandedCases[k])
    selectedIds.clear()
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e.message
  } finally {
    discovering.value = false
  }
}

const handleRunAll = () => executeRun({})
const handleRunSelected = () => executeRun({ test_ids: [...selectedIds] })

const executeRun = async (extra: any) => {
  running.value = true
  error.value = ""
  try {
    const res = await testingApi.run({
      framework: selectedFramework.value as any,
      ...extra,
    })
    lastResult.value = res.data
    // 刷新用例状态
    if (res.data?.results) {
      for (const r of res.data.results) {
        for (const f of testFiles.value) {
          for (const s of f.suites) {
            const tc = s.cases.find(c => c.id === r.id)
            if (tc) {
              tc.status = r.status
              tc.duration_ms = r.duration_ms
              tc.error_message = r.error_message
              tc.error_stack = r.error_stack
            }
          }
        }
      }
    }
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e.message
  } finally {
    running.value = false
  }
}

const toggleFile = (path: string) => { expandedFiles[path] = !expandedFiles[path] }
const toggleSuite = (filePath: string, idx: number) => {
  expandedSuites[`${filePath}-${idx}`] = !expandedSuites[`${filePath}-${idx}`]
}
const toggleCase = (id: string) => { expandedCases[id] = !expandedCases[id] }
const toggleSelectCase = (id: string) => {
  if (selectedIds.has(id)) selectedIds.delete(id)
  else selectedIds.add(id)
}
</script>

<style scoped>
.testing-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  color: var(--color-ide-fg);
  background: var(--color-ide-bg);
}
.testing-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.testing-toolbar h2 { margin: 0; font-size: 1.2rem; }
.toolbar-actions { display: flex; gap: 8px; align-items: center; }
.framework-select {
  padding: 4px 8px;
  background: var(--color-ide-bg2);
  color: var(--color-ide-fg);
  border: 1px solid var(--color-ide-border);
  border-radius: 4px;
}
.btn-primary, .btn-play {
  padding: 6px 14px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
}
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-play { background: #22863a; color: #fff; }
.btn-primary:disabled, .btn-play:disabled { opacity: 0.5; cursor: not-allowed; }
.testing-body { display: flex; gap: 16px; flex: 1; overflow: hidden; }
.test-tree { flex: 1; overflow-y: auto; border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 8px; }
.empty-state { text-align: center; padding: 40px; opacity: 0.5; }
.file-node { margin-bottom: 4px; }
.file-header { display: flex; align-items: center; gap: 4px; padding: 4px; cursor: pointer; border-radius: 4px; }
.file-header:hover { background: var(--color-ide-bg2); }
.file-name { font-weight: 600; }
.file-path { font-size: 0.75rem; opacity: 0.5; margin-left: auto; }
.suite-list { margin-left: 16px; }
.suite-header { display: flex; align-items: center; gap: 4px; padding: 3px 4px; cursor: pointer; border-radius: 4px; }
.suite-header:hover { background: var(--color-ide-bg2); }
.suite-badge, .case-badge { font-size: 0.75rem; }
.suite-badge.passed, .case-badge.passed { color: #22863a; }
.suite-badge.failed, .case-badge.failed { color: #cb2431; }
.suite-badge.running, .case-badge.running { color: #dbab0a; }
.suite-badge.idle, .case-badge.idle { opacity: 0.4; }
.case-list { margin-left: 16px; }
.case-node { display: flex; align-items: flex-start; gap: 4px; padding: 2px 4px; cursor: pointer; border-radius: 4px; }
.case-node:hover { background: var(--color-ide-bg2); }
.case-checkbox { margin-top: 2px; }
.case-duration { font-size: 0.7rem; opacity: 0.5; margin-left: auto; }
.case-error { margin-left: 20px; padding: 4px 8px; background: rgba(203,36,49,.1); border-radius: 4px; }
.case-error pre { margin: 0; font-size: 0.75rem; white-space: pre-wrap; }
.stack-trace { opacity: 0.6; margin-top: 4px !important; }
.results-panel { width: 320px; border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 12px; overflow-y: auto; flex-shrink: 0; }
.results-panel h3 { margin: 0 0 8px; }
.result-summary { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.stat { padding: 4px 10px; background: var(--color-ide-bg2); border-radius: 4px; font-size: 0.85rem; }
.stat.passed { border-left: 3px solid #22863a; }
.stat.failed { border-left: 3px solid #cb2431; }
.failure-item { margin-bottom: 8px; padding: 6px; background: rgba(203,36,49,.05); border-radius: 4px; }
.file-ref { font-size: 0.7rem; opacity: 0.5; }
.error-msg { margin: 4px 0 0; font-size: 0.75rem; white-space: pre-wrap; }
.arrow { font-size: 0.65rem; width: 12px; display: inline-block; }
</style>
