<template>
  <div class="pipeline-page">
    <div class="page-header">
      <h2>CLI 管道</h2>
      <p class="subtitle">运行 YAML 定义的命令行管道 — 多步骤有序执行</p>
    </div>

    <div class="layout">
      <!-- 左侧: 模板 -->
      <div class="panel">
        <h3>内置模板</h3>
        <div v-if="samplesLoading" class="loading-sm">加载中...</div>
        <div v-else class="sample-list">
          <div v-for="s in samples" :key="s.name" class="sample-card" @click="loadSample(s)">
            <strong>{{ s.name }}</strong>
            <p>{{ s.description }}</p>
          </div>
        </div>
      </div>

      <!-- 右侧: 编辑器 + 执行 -->
      <div class="panel panel-main">
        <h3>管道定义</h3>
        <textarea v-model="yamlContent" placeholder="输入 YAML 管道定义，或从左侧模板加载..." class="yaml-editor" rows="14"></textarea>
        <div class="actions-row">
          <input v-model="variablesJson" placeholder='变量 JSON (可选), 如 {"key":"val"}' class="input" />
          <button class="btn btn-primary" @click="runPipeline" :disabled="!yamlContent.trim() || running">
            {{ running ? '执行中...' : '运行管道' }}
          </button>
        </div>

        <div v-if="result" class="result-section">
          <h4>
            结果 —
            <span :class="result.success ? 'text-ok' : 'text-error'">
              {{ result.success ? '成功' : '失败' }}
            </span>
            ({{ result.total_duration_ms?.toFixed(0) ?? '?' }}ms)
          </h4>
          <div v-for="step in result.steps" :key="step.id" class="step-card">
            <div class="step-header">
              <span class="step-id">{{ step.id }}</span>
              <span :class="['badge', step.success ? 'badge-ok' : 'badge-error']">
                {{ step.success ? 'OK' : `退出码 ${step.exit_code}` }}
              </span>
              <span class="step-dur">{{ step.duration_ms?.toFixed(0) }}ms</span>
            </div>
            <div class="step-cmd">{{ step.command }}</div>
            <details v-if="step.stdout">
              <summary class="summary">stdout</summary>
              <pre class="output">{{ step.stdout }}</pre>
            </details>
            <details v-if="step.stderr">
              <summary class="summary summary-err">stderr</summary>
              <pre class="output output-err">{{ step.stderr }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { cliPipelineApi, type PipelineSample, type PipelineResult } from '@/api/cliPipeline'

const samples = ref<PipelineSample[]>([])
const samplesLoading = ref(false)
const yamlContent = ref('')
const variablesJson = ref('')
const running = ref(false)
const result = ref<PipelineResult | null>(null)

async function fetchSamples() {
  samplesLoading.value = true
  try {
    const res = await cliPipelineApi.getSamples()
    samples.value = (res.data as any)?.samples ?? []
  } finally {
    samplesLoading.value = false
  }
}

function loadSample(s: PipelineSample) {
  yamlContent.value = s.yaml
}

async function runPipeline() {
  running.value = true
  result.value = null
  try {
    let vars: Record<string, any> | undefined
    if (variablesJson.value.trim()) {
      try { vars = JSON.parse(variablesJson.value) } catch { alert('变量 JSON 格式错误') }
    }
    const res = await cliPipelineApi.runYaml(yamlContent.value)
    result.value = (res.data ?? res) as PipelineResult
  } catch (e: any) {
    result.value = { name: 'error', success: false, steps: [], total_duration_ms: 0 } as any
    alert(`管道失败: ${e?.message ?? e}`)
  } finally {
    running.value = false
  }
}

onMounted(fetchSamples)
</script>

<style scoped>
.pipeline-page { max-width: 1200px; margin: 0 auto; padding: 24px; }
.page-header h2 { margin: 0; font-size: 22px; }
.subtitle { color: var(--color-ide-text-secondary); margin: 4px 0 16px; font-size: 14px; }

.layout { display: grid; grid-template-columns: 260px 1fr; gap: 20px; }
.panel { }
.panel h3 { margin: 0 0 12px; font-size: 15px; }

.sample-list { display: grid; gap: 8px; }
.sample-card { padding: 10px; border: 1px solid var(--color-ide-border); border-radius: 8px; background: var(--color-ide-bg-secondary); cursor: pointer; transition: border-color 0.15s; }
.sample-card:hover { border-color: var(--color-ide-accent); }
.sample-card strong { font-size: 13px; }
.sample-card p { font-size: 11px; color: var(--color-ide-text-secondary); margin: 4px 0 0; }

.yaml-editor { width: 100%; padding: 12px; border: 1px solid var(--color-ide-border); border-radius: 8px; background: #0d1117; color: #d2d2d2; font-family: monospace; font-size: 13px; resize: vertical; box-sizing: border-box; }
.actions-row { display: flex; gap: 8px; margin-top: 10px; align-items: center; }
.input { flex: 1; padding: 6px 10px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-bg-secondary); color: var(--color-ide-text-primary); font-size: 13px; }

.result-section { margin-top: 20px; }
.result-section h4 { margin: 0 0 10px; font-size: 15px; }
.text-ok { color: #81c784; }
.text-error { color: #e57373; }

.step-card { padding: 10px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-bg-secondary); margin-bottom: 8px; }
.step-header { display: flex; gap: 8px; align-items: center; }
.step-id { font-weight: 600; font-family: monospace; font-size: 13px; }
.step-dur { font-size: 11px; color: var(--color-ide-text-secondary); margin-left: auto; }
.step-cmd { font-family: monospace; font-size: 12px; margin: 4px 0; padding: 4px 8px; background: var(--color-ide-bg-tertiary); border-radius: 4px; }
.summary { font-size: 12px; cursor: pointer; color: var(--color-ide-text-secondary); }
.summary-err { color: #e57373; }
.output { background: #0d1117; color: #d2d2d2; padding: 8px; border-radius: 4px; font-size: 11px; max-height: 150px; overflow: auto; white-space: pre-wrap; margin-top: 4px; }
.output-err { color: #e57373; }

.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-secondary); }
.badge-ok { background: #1e3a2e; color: #81c784; }
.badge-error { background: #3e1a1a; color: #e57373; }

.loading-sm { padding: 20px; text-align: center; color: var(--color-ide-text-secondary); font-size: 13px; }

.btn { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-primary); transition: opacity 0.15s; }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
