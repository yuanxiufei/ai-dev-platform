<template>
  <div class="bench-page">
    <div class="page-header">
      <h2>基准测试</h2>
      <p class="subtitle">模型性能评估 — 吞吐量、延迟、并发测试</p>
    </div>

    <!-- 新建测试 -->
    <form class="create-form" @submit.prevent="createTask">
      <div class="form-row">
        <input v-model="form.model_name" placeholder="模型名称 (如 deepseek-v2)" class="input" required />
        <select v-model="form.dataset" class="input">
          <option value="simple_questions">简单问答</option>
          <option value="complex_instructions">复杂指令</option>
          <option value="code_generation">代码生成</option>
          <option value="custom">自定义</option>
        </select>
        <input v-model.number="form.num_requests" type="number" placeholder="请求数" class="input-sm" />
        <input v-model.number="form.concurrency" type="number" placeholder="并发" class="input-sm" />
        <button type="submit" class="btn btn-primary" :disabled="creating">
          {{ creating ? '创建中...' : '创建测试' }}
        </button>
      </div>
    </form>

    <!-- 任务列表 -->
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="tasks.length === 0" class="empty">暂无基准测试任务</div>

    <div v-else class="task-list">
      <div v-for="t in tasks" :key="t.task_id" class="task-card">
        <div class="task-header">
          <span class="task-name">{{ t.model_name }}</span>
          <span :class="['badge', stateClass(t.state)]">{{ t.state }}</span>
        </div>
        <div class="task-body">
          <span class="task-info">{{ t.dataset }} | {{ t.num_requests }} req | 并发 {{ t.concurrency }}</span>
        </div>
        <div class="task-metrics" v-if="t.state === 'completed'">
          <div class="metric">
            <span class="metric-val">{{ t.metrics?.tokens_per_second?.toFixed(1) ?? '—' }}</span>
            <span class="metric-label">tokens/s</span>
          </div>
          <div class="metric">
            <span class="metric-val">{{ t.metrics?.latency_avg_ms?.toFixed(0) ?? '—' }}</span>
            <span class="metric-label">ms avg</span>
          </div>
        </div>
        <div class="progress-bar" v-if="t.state === 'running'">
          <div class="progress-fill" :style="{ width: (t.progress * 100) + '%' }"></div>
        </div>
        <div class="task-actions">
          <button v-if="t.state === 'created'" class="btn btn-sm btn-primary" @click="submitTask(t.task_id)">提交</button>
          <button v-if="t.state === 'running'" class="btn btn-sm btn-outline" @click="stopTask(t.task_id)">停止</button>
          <button v-if="t.state === 'completed'" class="btn btn-sm" @click="exportYaml(t.task_id)">导出 YAML</button>
          <button class="btn btn-sm" @click="wsConnect(t.task_id)" v-if="t.state === 'running'">实时日志</button>
        </div>
        <div v-if="t.state === 'running' && wsLogs[t.task_id]" class="ws-logs">
          <pre>{{ wsLogs[t.task_id] }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { benchmarkApi, type BenchmarkTask } from '@/api/benchmarks'

const tasks = ref<BenchmarkTask[]>([])
const loading = ref(false)
const creating = ref(false)
const wsSockets = reactive<Record<string, WebSocket>>({})
const wsLogs = reactive<Record<string, string>>({})

const form = reactive({
  model_name: '',
  dataset: 'simple_questions',
  num_requests: 10,
  concurrency: 1,
})

function stateClass(s: string) {
  return {
    created: 'badge-info',
    running: 'badge-running',
    completed: 'badge-ok',
    failed: 'badge-error',
    stopped: 'badge-warn',
  }[s] ?? ''
}

async function fetchTasks() {
  loading.value = true
  try {
    const res = await benchmarkApi.list()
    tasks.value = res.data ?? []
  } finally {
    loading.value = false
  }
}

async function createTask() {
  creating.value = true
  try {
    await benchmarkApi.create({
      model_name: form.model_name,
      dataset: form.dataset,
      num_requests: form.num_requests,
      concurrency: form.concurrency,
    })
    await fetchTasks()
  } catch (e: any) {
    alert(`创建失败: ${e?.message ?? e}`)
  } finally {
    creating.value = false
  }
}

async function submitTask(taskId: string) {
  await benchmarkApi.submit(taskId)
  await fetchTasks()
}

async function stopTask(taskId: string) {
  await benchmarkApi.stop(taskId)
  await fetchTasks()
}

async function exportYaml(taskId: string) {
  try {
    const res = await benchmarkApi.exportYaml(taskId)
    const yaml = (res as any)?.yaml ?? (res as any)?.data?.yaml ?? JSON.stringify(res)
    const blob = new Blob([yaml], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `benchmark_${taskId}.yaml`
    a.click()
    URL.revokeObjectURL(url)
  } catch { /* ignore */ }
}

function wsConnect(taskId: string) {
  if (wsSockets[taskId]) return
  try {
    const token = localStorage.getItem('token') ?? ''
    const url = benchmarkApi.wsUrl(taskId, token)
    const ws = new WebSocket(url)
    wsSockets[taskId] = ws
    ws.onmessage = (e) => {
      if (!wsLogs[taskId]) wsLogs[taskId] = ''
      wsLogs[taskId] += e.data + '\n'
    }
    ws.onclose = () => {
      delete wsSockets[taskId]
    }
  } catch { /* ignore */ }
}

function closeWs(taskId: string) {
  wsSockets[taskId]?.close()
}

onMounted(fetchTasks)
onUnmounted(() => {
  Object.values(wsSockets).forEach(ws => ws.close())
})
</script>

<style scoped>
.bench-page { max-width: 1000px; margin: 0 auto; padding: 24px; }
.page-header h2 { margin: 0; font-size: 22px; }
.subtitle { color: var(--color-ide-text-secondary); margin: 4px 0 16px; font-size: 14px; }

.create-form { margin-bottom: 24px; }
.form-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.input { padding: 6px 10px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-bg-secondary); color: var(--color-ide-text-primary); font-size: 13px; flex: 1; min-width: 120px; }
.input-sm { width: 80px; padding: 6px 8px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-bg-secondary); color: var(--color-ide-text-primary); font-size: 13px; }

.task-list { display: grid; gap: 12px; }
.task-card { padding: 14px; border: 1px solid var(--color-ide-border); border-radius: 8px; background: var(--color-ide-bg-secondary); }
.task-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.task-name { font-weight: 700; font-size: 15px; }
.task-body { font-size: 12px; color: var(--color-ide-text-secondary); margin-bottom: 8px; }
.task-info { }
.task-metrics { display: flex; gap: 24px; margin: 10px 0; }
.metric { display: flex; flex-direction: column; align-items: center; }
.metric-val { font-size: 18px; font-weight: 700; color: var(--color-ide-accent); }
.metric-label { font-size: 11px; color: var(--color-ide-text-secondary); }
.progress-bar { height: 5px; background: var(--color-ide-bg-tertiary); border-radius: 3px; margin: 8px 0; overflow: hidden; }
.progress-fill { height: 100%; background: var(--color-ide-accent); border-radius: 3px; transition: width 0.3s; }
.task-actions { display: flex; gap: 6px; margin-top: 8px; }
.ws-logs { margin-top: 8px; }
.ws-logs pre { background: #0d1117; color: #d2d2d2; padding: 10px; border-radius: 6px; font-size: 12px; max-height: 200px; overflow: auto; white-space: pre-wrap; }

.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-secondary); }
.badge-info { background: #1e3a5f; color: #64b5f6; }
.badge-running { background: #1e4a6e; color: #64b5f6; }
.badge-ok { background: #1e3a2e; color: #81c784; }
.badge-error { background: #3e1a1a; color: #e57373; }
.badge-warn { background: #3e3a1e; color: #ffb74d; }

.loading, .empty { text-align: center; padding: 40px; color: var(--color-ide-text-secondary); }

.btn { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-primary); transition: opacity 0.15s; }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-outline { border: 1px solid var(--color-ide-border); background: transparent; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
