<template>
  <div class="model-manager-page">
    <div class="page-header">
      <h2>模型管理</h2>
      <p class="subtitle">本地模型下载、加载/卸载、API 提供商配置</p>
    </div>

    <!-- 操作栏 -->
    <div class="toolbar">
      <button class="btn btn-primary" @click="showDownload = true" v-if="!showDownload">下载模型</button>
      <button class="btn btn-outline" @click="refreshAll">刷新</button>
      <button class="btn btn-sm" @click="triggerOptimize" :disabled="optimizing">
        {{ optimizing ? '优化中...' : '触发优化' }}
      </button>
    </div>

    <!-- 下载面板 -->
    <div v-if="showDownload" class="download-panel">
      <h4>下载新模型</h4>
      <form @submit.prevent="startDownload" class="download-form">
        <input v-model="downloadForm.model_name" placeholder="模型名称 (如 meta-llama/Llama-3-8B)" class="input" required />
        <select v-model="downloadForm.source" class="input input-sm">
          <option value="huggingface">HuggingFace</option>
          <option value="hf-mirror">HF Mirror</option>
          <option value="modelscope">ModelScope</option>
          <option value="ollama">Ollama</option>
        </select>
        <button type="submit" class="btn btn-primary" :disabled="downloading">
          {{ downloading ? '下载中...' : '开始下载' }}
        </button>
        <button type="button" class="btn btn-outline" @click="showDownload = false">取消</button>
      </form>
      <!-- 下载进度 -->
      <div v-if="downloadTask" class="download-progress">
        <span>{{ downloadTask.task_id }}</span>
        <div class="progress-bar">
          <div class="progress-fill" :style="{ width: (downloadProgress * 100) + '%' }"></div>
        </div>
        <span>{{ (downloadProgress * 100).toFixed(1) }}%</span>
        <button class="btn btn-sm btn-outline" @click="pollDownloadProgress">刷新进度</button>
      </div>
    </div>

    <!-- 已加载模型 -->
    <div class="section" v-if="loadedModels.length">
      <h3>已加载模型 ({{ loadedModels.length }})</h3>
      <div class="card-grid">
        <div v-for="m in loadedModels" :key="m.name" class="card card-loaded">
          <div class="card-header">
            <span class="card-title">{{ m.name }}</span>
            <span class="badge badge-ok">已加载</span>
          </div>
          <div class="card-actions">
            <button class="btn btn-sm btn-danger" @click="unloadModel(m.name)">卸载</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 提供商配置 -->
    <div class="section">
      <h3>API 提供商配置</h3>
      <div class="provider-list">
        <div v-for="p in providers" :key="p.name" class="provider-row">
          <span class="provider-name">{{ p.name }}</span>
          <button class="btn btn-sm" @click="openProviderConfig(p)">配置</button>
        </div>
      </div>
      <!-- 配置弹窗 -->
      <div v-if="providerConfig" class="modal-mask" @click.self="providerConfig = null">
        <div class="modal-card">
          <h4>配置 {{ providerConfig.name }}</h4>
          <form @submit.prevent="saveProviderConfig">
            <input v-model="configForm.api_key" placeholder="API Key" class="input" type="password" required />
            <input v-model="configForm.endpoint" placeholder="自定义 Endpoint (可选)" class="input" />
            <div class="modal-actions">
              <button type="submit" class="btn btn-primary">保存</button>
              <button type="button" class="btn btn-outline" @click="providerConfig = null">取消</button>
            </div>
          </form>
        </div>
      </div>
    </div>

    <!-- 模型列表 -->
    <div class="section">
      <h3>模型列表</h3>
      <div class="list-toolbar">
        <select v-model="capabilityFilter" @change="fetchModels" class="input input-sm">
          <option value="">全部能力</option>
          <option value="chat">对话</option>
          <option value="embedding">嵌入</option>
          <option value="vision">视觉</option>
          <option value="code">代码</option>
        </select>
      </div>
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="models.length === 0" class="empty">暂无可用的模型</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>模型名称</th>
              <th>来源</th>
              <th>状态</th>
              <th>大小</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in models" :key="m.name || m.id">
              <td>
                <span class="model-name" @click="showDetail(m.name || m.id)" style="cursor:pointer;color:var(--color-ide-accent)">
                  {{ m.name || m.id }}
                </span>
              </td>
              <td>{{ m.provider || m.source || '本地' }}</td>
              <td>
                <span :class="['badge', m.state === 'loaded' ? 'badge-ok' : m.state === 'downloading' ? 'badge-running' : '']">
                  {{ m.state || '未加载' }}
                </span>
              </td>
              <td>{{ formatSize(m.size_bytes) }}</td>
              <td class="actions-cell">
                <button v-if="m.state !== 'loaded'" class="btn btn-sm btn-primary" @click="loadModel(m.name || m.id)">加载</button>
                <button v-if="m.state === 'loaded'" class="btn btn-sm btn-outline" @click="unloadModel(m.name || m.id)">卸载</button>
                <button class="btn btn-sm" @click="deleteModel(m.name || m.id)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 使用统计 -->
    <div class="section" v-if="usageStats">
      <h3>使用统计</h3>
      <div class="stats-grid">
        <div v-for="(v, k) in usageStats" :key="k" class="stat-card">
          <span class="stat-val">{{ v }}</span>
          <span class="stat-label">{{ k }}</span>
        </div>
      </div>
    </div>

    <!-- 模型详情弹窗 -->
    <div v-if="detailModel" class="modal-mask" @click.self="detailModel = null">
      <div class="modal-card">
        <h4>模型详情 — {{ detailModel.name || detailModel.id }}</h4>
        <pre class="detail-json">{{ JSON.stringify(detailModel, null, 2) }}</pre>
        <div class="modal-actions">
          <button class="btn btn-outline" @click="detailModel = null">关闭</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { modelsApi } from '@/api/models'

const models = ref<any[]>([])
const loadedModels = ref<any[]>([])
const providers = ref<any[]>([])
const loading = ref(false)
const downloading = ref(false)
const optimizing = ref(false)
const showDownload = ref(false)
const capabilityFilter = ref('')
const usageStats = ref<Record<string, any> | null>(null)
const detailModel = ref<any>(null)
const providerConfig = ref<any>(null)
const downloadTask = ref<any>(null)
const downloadProgress = ref(0)

const downloadForm = reactive({ model_name: '', source: 'huggingface' })
const configForm = reactive({ api_key: '', endpoint: '' })

function formatSize(bytes?: number) {
  if (!bytes) return '—'
  const gb = bytes / (1024 ** 3)
  return gb >= 1 ? gb.toFixed(1) + ' GB' : (bytes / (1024 ** 2)).toFixed(0) + ' MB'
}

async function fetchModels() {
  loading.value = true
  try {
    const res = await modelsApi.listAll(capabilityFilter.value || undefined)
    models.value = res.data?.models ?? res.data ?? []
  } finally {
    loading.value = false
  }
}

async function fetchLoaded() {
  try {
    const res = await modelsApi.listLoaded()
    loadedModels.value = res.data?.loaded ?? res.data ?? []
  } catch { /* empty */ }
}

async function fetchProviders() {
  try {
    const res = await modelsApi.listProviders()
    providers.value = res.data ?? []
  } catch { /* empty */ }
}

async function fetchUsageStats() {
  try {
    const res = await modelsApi.getUsageStats({ days: 7 })
    usageStats.value = res.data ?? null
  } catch { /* empty */ }
}

async function refreshAll() {
  await Promise.all([fetchModels(), fetchLoaded(), fetchProviders(), fetchUsageStats()])
}

async function showDetail(name: string) {
  try {
    const res = await modelsApi.getDetail(name)
    detailModel.value = res.data
  } catch { /* empty */ }
}

async function startDownload() {
  downloading.value = true
  try {
    const res = await modelsApi.startDownload(downloadForm.model_name, downloadForm.source)
    downloadTask.value = res.data
    downloadProgress.value = 0
  } finally {
    downloading.value = false
  }
}

async function pollDownloadProgress() {
  if (!downloadTask.value) return
  try {
    const res = await modelsApi.getDownloadStatus(downloadTask.value.task_id)
    downloadProgress.value = res.data?.progress ?? 0
    if (downloadProgress.value >= 1) {
      downloadTask.value = null
      fetchModels()
    }
  } catch { /* empty */ }
}

async function deleteModel(name: string) {
  if (!confirm(`确定要删除模型 "${name}"？`)) return
  try {
    await modelsApi.deleteModel(name)
    fetchModels()
  } catch { /* empty */ }
}

async function loadModel(name: string) {
  try {
    await modelsApi.loadModel(name)
    fetchModels()
    fetchLoaded()
  } catch { /* empty */ }
}

async function unloadModel(name: string) {
  try {
    await modelsApi.unloadModel(name)
    fetchModels()
    fetchLoaded()
  } catch { /* empty */ }
}

function openProviderConfig(p: any) {
  providerConfig.value = p
  configForm.api_key = ''
  configForm.endpoint = ''
}

async function saveProviderConfig() {
  if (!providerConfig.value) return
  try {
    await modelsApi.configureProvider(providerConfig.value.name, configForm.api_key, configForm.endpoint || undefined)
    providerConfig.value = null
  } catch { /* empty */ }
}

async function triggerOptimize() {
  optimizing.value = true
  try {
    await modelsApi.triggerOptimize(7)
  } finally {
    optimizing.value = false
  }
}

onMounted(() => refreshAll())
</script>

<style scoped>
.model-manager-page { padding: 24px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; }
.subtitle { color: var(--color-ide-fg-secondary); margin: 4px 0 0; font-size: 13px; }

.toolbar { display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; }

.download-panel { border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 16px; margin-bottom: 20px; }
.download-panel h4 { margin: 0 0 12px; }
.download-form { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.download-progress { display: flex; align-items: center; gap: 8px; margin-top: 12px; font-size: 13px; }

.section { margin-bottom: 28px; }
.section h3 { margin: 0 0 12px; font-size: 16px; }

.list-toolbar { margin-bottom: 10px; }

.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.card { border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 14px; }
.card-loaded { border-color: var(--color-ide-accent, #4fc1ff); }
.card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.card-title { font-weight: 600; }
.card-actions { display: flex; gap: 6px; }

.provider-list { display: flex; gap: 8px; flex-wrap: wrap; }
.provider-row { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border: 1px solid var(--color-ide-border); border-radius: 6px; }
.provider-name { font-weight: 500; }

.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; }
.stat-card { border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 12px; text-align: center; }
.stat-val { display: block; font-size: 20px; font-weight: 700; }
.stat-label { font-size: 12px; color: var(--color-ide-fg-secondary); }

.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--color-ide-border); }
th { font-size: 12px; color: var(--color-ide-fg-secondary); font-weight: 600; }
.actions-cell { display: flex; gap: 4px; flex-wrap: wrap; }

.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { background: var(--color-ide-bg); border: 1px solid var(--color-ide-border); border-radius: 12px; padding: 24px; min-width: 380px; max-width: 90vw; max-height: 80vh; overflow-y: auto; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.detail-json { font-size: 12px; background: var(--color-ide-bg-secondary); padding: 12px; border-radius: 6px; max-height: 300px; overflow-y: auto; }

.loading, .empty { padding: 32px 0; text-align: center; color: var(--color-ide-fg-secondary); }

.progress-bar { flex: 1; height: 6px; background: var(--color-ide-bg-secondary); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; background: var(--color-ide-accent, #4fc1ff); transition: width 0.3s; }

.badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.badge-ok { background: #1a7f3711; color: #1a7f37; }
.badge-running { background: #4fc1ff11; color: #4fc1ff; }
</style>
