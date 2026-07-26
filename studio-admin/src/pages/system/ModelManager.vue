<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import {
  Download, Trash2, RefreshCw, Search, CheckCircle, Loader2,
  AlertCircle, XCircle, Zap, HardDrive, Cpu, RotateCcw,
  Clock, Plus
} from '@/components/icons'
import { useAppStore } from '@/stores/app'
import { modelManagerApi, type ModelItem, type DownloadProgress, type ModelUsageStats } from '@/api/model-features'

const appStore = useAppStore()

/* ── 下载源定义（对应后端 model_downloader.py） ── */
const DOWNLOAD_SOURCES = [
  { key: 'huggingface', name: 'Hugging Face (hf-mirror)', baseUrl: 'https://hf-mirror.com', available: true, desc: 'HF 镜像站，国内高速下载' },
  { key: 'modelscope', name: 'ModelScope', baseUrl: 'https://modelscope.cn', available: true, desc: '阿里魔搭社区' },
  { key: 'ollama', name: 'Ollama Registry', baseUrl: 'https://registry.ollama.ai', available: true, desc: 'Ollama 官方模型库' },
  { key: 'huggingface-direct', name: 'Hugging Face 直连', baseUrl: 'https://huggingface.co', available: true, desc: 'HF 官方源，需科学上网' },
]

/* ── 预定义模型目录（对应 downloader 配置） ── */
const MODEL_CATALOG = [
  { name: 'llama3.2:3b', type: 'chat', sizeHuman: '2.0 GB', source: 'ollama', desc: 'Meta Llama 3.2 3B，轻量通用' },
  { name: 'qwen2.5:7b', type: 'chat', sizeHuman: '4.7 GB', source: 'ollama', desc: '通义千问 2.5 7B，中英双语' },
  { name: 'deepseek-r1:7b', type: 'chat', sizeHuman: '4.7 GB', source: 'ollama', desc: 'DeepSeek R1 推理模型 7B' },
  { name: 'gemma3:4b', type: 'chat', sizeHuman: '2.6 GB', source: 'ollama', desc: 'Google Gemma 3 4B' },
  { name: 'phi4:14b', type: 'chat', sizeHuman: '8.2 GB', source: 'ollama', desc: 'Microsoft Phi-4 14B' },
  { name: 'codestral:22b', type: 'code', sizeHuman: '13.2 GB', source: 'ollama', desc: 'Mistral Codestral 代码模型' },
  { name: 'nomic-embed-text', type: 'embedding', sizeHuman: '274 MB', source: 'ollama', desc: 'Nomic 嵌入模型' },
  { name: 'Qwen/Qwen2.5-7B-Instruct-GGUF', type: 'chat', sizeHuman: '4.7 GB', source: 'huggingface', desc: 'Qwen2.5 7B GGUF 格式' },
  { name: 'unsloth/DeepSeek-R1-Distill-Qwen-7B-GGUF', type: 'chat', sizeHuman: '4.7 GB', source: 'huggingface', desc: 'DeepSeek R1 Distill 7B GGUF' },
  { name: 'unsloth/Llama-3.2-3B-Instruct-GGUF', type: 'chat', sizeHuman: '2.0 GB', source: 'huggingface', desc: 'Llama 3.2 3B GGUF 格式' },
]

/* ── 状态 ── */
const loading = ref(false)
const models = ref<ModelItem[]>([])
const stats = ref<ModelUsageStats | null>(null)
const searchQuery = ref('')
const activeTab = ref('all') // all | downloaded | not-downloaded | loaded
const refreshing = ref(false)

/* ── 下载状态 ── */
const showDownloadDialog = ref(false)
const downloadSource = ref('huggingface')
const downloadModel = ref('')
const customModelName = ref('')
const downloadTasks = ref<Map<string, DownloadProgress>>(new Map())
let progressIntervals: ReturnType<typeof setInterval>[] = []

/* ── 计算属性 ── */
const filteredModels = computed(() => {
  let list = models.value
  if (activeTab.value === 'downloaded') list = list.filter(m => m.downloaded)
  else if (activeTab.value === 'not-downloaded') list = list.filter(m => !m.downloaded)
  else if (activeTab.value === 'loaded') list = list.filter(m => m.loaded)
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(m => m.name.toLowerCase().includes(q) || (m.provider || '').toLowerCase().includes(q))
  }
  return list
})

const tabs = [
  { key: 'all', label: '全部', count: computed(() => models.value.length) },
  { key: 'downloaded', label: '已下载', count: computed(() => models.value.filter(m => m.downloaded).length) },
  { key: 'not-downloaded', label: '未下载', count: computed(() => models.value.filter(m => !m.downloaded).length) },
  { key: 'loaded', label: '已加载', count: computed(() => models.value.filter(m => m.loaded).length) },
]

/* ── 数据加载 ── */
async function loadData() {
  loading.value = true
  try {
    const [listRes, statsRes] = await Promise.allSettled([
      modelManagerApi.list({ size: 200 }),
      modelManagerApi.usageStats(),
    ])
    if (listRes.status === 'fulfilled') {
      models.value = (listRes.value.data as ModelItem[]) ?? []
    }
    if (statsRes.status === 'fulfilled') {
      stats.value = statsRes.value
    }
  } catch {
    // 静默失败
  } finally {
    loading.value = false
  }
}

async function refreshData() {
  refreshing.value = true
  await loadData()
  refreshing.value = false
}

/* ── 模型操作 ── */
async function handleDelete(model: ModelItem) {
  if (!confirm(`确定要删除模型 "${model.name}" 吗？此操作不可撤销。`)) return
  try {
    await modelManagerApi.remove(model.name)
    appStore.toast?.success(`模型 ${model.name} 已删除`)
    await loadData()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '删除失败'
    appStore.toast?.error(msg)
  }
}

async function handleLoad(model: ModelItem) {
  try {
    await modelManagerApi.load(model.name)
    appStore.toast?.success(`模型 ${model.name} 已加载`)
    await loadData()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '加载失败'
    appStore.toast?.error(msg)
  }
}

async function handleUnload(model: ModelItem) {
  try {
    await modelManagerApi.unload(model.name)
    appStore.toast?.success(`模型 ${model.name} 已卸载`)
    await loadData()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '卸载失败'
    appStore.toast?.error(msg)
  }
}

/* ── 下载功能 ── */
function openDownloadDialog() {
  downloadModel.value = ''
  customModelName.value = ''
  downloadSource.value = 'huggingface'
  showDownloadDialog.value = true
}

async function startDownload() {
  const modelName = downloadModel.value === '__custom__' ? customModelName.value.trim() : downloadModel.value
  if (!modelName) {
    appStore.toast?.warning('请选择或输入模型名称')
    return
  }
  try {
    const res = await modelManagerApi.download({
      model_name: modelName,
      source: downloadSource.value,
    })
    appStore.toast?.success(`下载任务已启动: ${res.task_id}`)
    showDownloadDialog.value = false
    // 开始轮询进度
    pollDownloadProgress(res.task_id)
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '启动下载失败'
    appStore.toast?.error(msg)
  }
}

function pollDownloadProgress(taskId: string) {
  const interval = setInterval(async () => {
    try {
      const progress = await modelManagerApi.downloadProgress(taskId)
      downloadTasks.value.set(taskId, progress)
      if (progress.status === 'completed' || progress.status === 'failed') {
        clearInterval(interval)
        if (progress.status === 'completed') {
          appStore.toast?.success(`模型 ${progress.model_name} 下载完成`)
          await loadData()
        } else {
          appStore.toast?.error(`模型 ${progress.model_name} 下载失败: ${progress.error || '未知错误'}`)
        }
        // 5 秒后从任务列表移除
        setTimeout(() => { downloadTasks.value.delete(taskId) }, 5000)
      }
    } catch {
      clearInterval(interval)
      downloadTasks.value.delete(taskId)
    }
  }, 1000)
  progressIntervals.push(interval)
}

/* ── 格式化 ── */
function formatBytes(bytes: number | null): string {
  if (bytes === null || bytes === undefined) return '未知'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let unitIndex = 0
  let size = bytes
  while (size >= 1024 && unitIndex < units.length - 1) { size /= 1024; unitIndex++ }
  return `${size.toFixed(unitIndex > 0 ? 1 : 0)} ${units[unitIndex]}`
}

function formatSpeed(bps: number | null): string {
  if (!bps) return '—'
  return formatBytes(bps) + '/s'
}

function formatEta(seconds: number | null): string {
  if (seconds === null) return '—'
  if (seconds < 60) return `${Math.round(seconds)}秒`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}分${Math.round(seconds % 60)}秒`
  return `${Math.floor(seconds / 3600)}时${Math.floor((seconds % 3600) / 60)}分`
}

function statusBadge(model: ModelItem) {
  if (model.loaded) return { label: '已加载', class: 'bg-green-500/15 text-green-400' }
  if (model.downloaded) return { label: '已下载', class: 'bg-blue-500/15 text-blue-400' }
  return { label: '未下载', class: 'bg-gray-500/15 text-gray-400' }
}

function progressPercent(task: DownloadProgress): string {
  return `${Math.round(task.progress * 100)}%`
}

/* ── 生命周期 ── */
onMounted(() => { loadData() })
onUnmounted(() => { progressIntervals.forEach(clearInterval) })
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <!-- 页头 -->
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white">模型管理</h1>
        <p class="text-gray-400 mt-1 text-sm">下载、加载和管理本地与远程 AI 模型 — 支持 HuggingFace 镜像 / ModelScope / Ollama</p>
      </div>
      <div class="flex items-center gap-3">
        <button
          :disabled="refreshing"
          class="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800/50 border border-gray-700/50 text-sm text-gray-300 hover:text-white transition-colors disabled:opacity-50"
          @click="refreshData"
        >
          <RefreshCw :class="['w-4 h-4', refreshing && 'animate-spin']" /> 刷新
        </button>
        <button
          class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition-colors text-sm font-medium"
          @click="openDownloadDialog"
        >
          <Download class="w-4 h-4" /> 下载模型
        </button>
      </div>
    </header>

    <!-- 统计卡片 -->
    <div class="grid grid-cols-4 gap-4 mb-6">
      <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50">
        <div class="flex items-center gap-2 mb-1"><Package class="w-4 h-4 text-brand-400" /><span class="text-xs text-gray-400">模型总数</span></div>
        <span class="text-xl font-bold text-white">{{ stats?.total_models ?? models.length }}</span>
      </div>
      <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50">
        <div class="flex items-center gap-2 mb-1"><HardDrive class="w-4 h-4 text-blue-400" /><span class="text-xs text-gray-400">已下载</span></div>
        <span class="text-xl font-bold text-white">{{ stats?.downloaded_models ?? models.filter(m => m.downloaded).length }}</span>
      </div>
      <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50">
        <div class="flex items-center gap-2 mb-1"><Zap class="w-4 h-4 text-green-400" /><span class="text-xs text-gray-400">已加载</span></div>
        <span class="text-xl font-bold text-white">{{ stats?.loaded_models ?? models.filter(m => m.loaded).length }}</span>
      </div>
      <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50">
        <div class="flex items-center gap-2 mb-1"><HardDrive class="w-4 h-4 text-yellow-400" /><span class="text-xs text-gray-400">存储占用</span></div>
        <span class="text-xl font-bold text-white">{{ stats?.total_storage_human ?? '—' }}</span>
      </div>
    </div>

    <!-- 下载中任务面板 -->
    <div v-if="downloadTasks.size" class="mb-6 space-y-3">
      <div v-for="[taskId, task] in downloadTasks" :key="taskId"
        class="p-4 rounded-xl bg-gray-800/50 border border-brand-500/30">
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <Loader2 class="w-4 h-4 text-brand-400 animate-spin" />
            <span class="text-sm font-medium text-white">{{ task.model_name }}</span>
            <span class="text-xs text-gray-500">· {{ progressPercent(task) }}</span>
          </div>
          <span class="text-xs text-gray-400">
            {{ formatSpeed(task.speed_bps) }}
            <template v-if="task.eta_seconds"> · 剩余 {{ formatEta(task.eta_seconds) }}</template>
          </span>
        </div>
        <!-- 进度条 -->
        <div class="w-full h-2 rounded-full bg-gray-700 overflow-hidden">
          <div class="h-full rounded-full bg-brand-500 transition-all duration-500"
            :style="{ width: progressPercent(task) }" />
        </div>
        <div class="flex justify-between mt-1.5">
          <span class="text-xs text-gray-500">{{ formatBytes(task.downloaded_bytes) }} / {{ formatBytes(task.total_bytes) }}</span>
          <span v-if="task.status === 'completed'" class="text-xs text-green-400">下载完成</span>
          <span v-else-if="task.status === 'failed'" class="text-xs text-red-400">{{ task.error }}</span>
          <span v-else class="text-xs text-gray-500">下载中...</span>
        </div>
      </div>
    </div>

    <!-- 搜索 + Tab -->
    <div class="flex items-center gap-4 mb-4">
      <div class="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-800/50 border border-gray-700/50">
        <Search class="w-4 h-4 text-gray-500" />
        <input v-model="searchQuery" placeholder="搜索模型名称或服务商..." class="flex-1 bg-transparent text-sm text-white placeholder-gray-500 outline-none" />
      </div>
    </div>
    <div class="flex gap-2 mb-4">
      <button v-for="tab in tabs" :key="tab.key"
        :class="[
          'px-4 py-1.5 rounded-lg text-sm transition-colors',
          activeTab === tab.key ? 'bg-brand-500/20 text-brand-400 border border-brand-500/30' : 'bg-gray-800/50 text-gray-400 border border-gray-700/50 hover:text-white'
        ]"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
        <span class="ml-1.5 text-xs opacity-60">{{ tab.count.value }}</span>
      </button>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="text-center py-16 text-gray-500">
      <Loader2 class="w-6 h-6 mx-auto mb-2 animate-spin" /> 加载中...
    </div>

    <!-- 空状态 -->
    <div v-else-if="!filteredModels.length" class="flex flex-col items-center justify-center py-20">
      <Package class="w-12 h-12 text-gray-600" />
      <p class="text-gray-500 mt-3">暂无模型数据</p>
      <button class="mt-3 text-sm text-brand-400 hover:text-brand-300" @click="openDownloadDialog">下载第一个模型</button>
    </div>

    <!-- 模型列表 -->
    <div v-else class="space-y-2">
      <div v-for="model in filteredModels" :key="model.name"
        class="flex items-center gap-4 p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 hover:border-gray-600/50 transition-colors">
        <!-- 状态图标 -->
        <div class="shrink-0">
          <CheckCircle v-if="model.loaded" class="w-5 h-5 text-green-400" />
          <HardDrive v-else-if="model.downloaded" class="w-5 h-5 text-blue-400" />
          <XCircle v-else class="w-5 h-5 text-gray-500" />
        </div>

        <!-- 信息 -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-white truncate">{{ model.name }}</span>
            <span :class="['px-2 py-0.5 text-xs rounded-full shrink-0', statusBadge(model).class]">
              {{ statusBadge(model).label }}
            </span>
            <span v-if="model.provider" class="px-2 py-0.5 text-xs rounded-full bg-gray-700/50 text-gray-400 shrink-0">
              {{ model.provider }}
            </span>
          </div>
          <div class="flex items-center gap-3 mt-1 text-xs text-gray-500">
            <span>{{ model.type || '通用' }}</span>
            <span v-if="model.size_bytes">· {{ formatBytes(model.size_bytes) }}</span>
            <span v-if="model.version">· v{{ model.version }}</span>
          </div>
        </div>

        <!-- 操作按钮 -->
        <div class="flex items-center gap-1.5 shrink-0">
          <template v-if="model.downloaded">
            <button v-if="!model.loaded"
              class="p-2 rounded-lg hover:bg-green-500/10 text-gray-400 hover:text-green-400 transition-colors"
              title="加载到内存"
              @click="handleLoad(model)"
            >
              <Zap class="w-4 h-4" />
            </button>
            <button v-else
              class="p-2 rounded-lg hover:bg-yellow-500/10 text-yellow-400 hover:text-yellow-300 transition-colors"
              title="卸载模型"
              @click="handleUnload(model)"
            >
              <RotateCcw class="w-4 h-4" />
            </button>
            <button
              class="p-2 rounded-lg hover:bg-red-500/10 text-gray-400 hover:text-red-400 transition-colors"
              title="删除模型"
              @click="handleDelete(model)"
            >
              <Trash2 class="w-4 h-4" />
            </button>
          </template>
          <button v-else
            class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-500/10 text-brand-400 hover:bg-brand-500/20 text-xs transition-colors"
            @click="downloadModel = model.name; downloadSource = 'huggingface'; showDownloadDialog = true"
          >
            <Download class="w-3.5 h-3.5" /> 下载
          </button>
        </div>
      </div>
    </div>

    <!-- 下载对话框 -->
    <Teleport to="body">
      <div v-if="showDownloadDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showDownloadDialog = false">
        <div class="w-full max-w-lg mx-4 p-6 rounded-2xl bg-gray-900 border border-gray-700/50 shadow-2xl">
          <h2 class="text-lg font-bold text-white mb-4">下载模型</h2>

          <!-- 模型选择 -->
          <label class="block text-sm text-gray-400 mb-1.5">选择模型</label>
          <select v-model="downloadModel" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500 mb-4">
            <option value="" disabled>— 选择预定义模型 —</option>
            <optgroup v-for="src in DOWNLOAD_SOURCES" :key="src.key" :label="src.name">
              <option v-for="m in MODEL_CATALOG.filter(c => c.source === src.key)" :key="m.name"
                :value="m.name">{{ m.name }} ({{ m.sizeHuman }})</option>
            </optgroup>
            <option value="__custom__">🔧 自定义模型名称</option>
          </select>

          <!-- 自定义名称 -->
          <div v-if="downloadModel === '__custom__'" class="mb-4">
            <label class="block text-sm text-gray-400 mb-1.5">模型名称 (HuggingFace repo_id 或 Ollama model:tag)</label>
            <input v-model="customModelName"
              placeholder="如 Qwen/Qwen2.5-7B-Instruct-GGUF 或 qwen2.5:7b"
              class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500" />
          </div>

          <!-- 下载源选择 -->
          <label class="block text-sm text-gray-400 mb-1.5">下载源 / 镜像</label>
          <div class="grid grid-cols-2 gap-2 mb-6">
            <button v-for="src in DOWNLOAD_SOURCES" :key="src.key"
              :class="[
                'p-3 rounded-lg text-left border transition-colors',
                downloadSource === src.key ? 'border-brand-500 bg-brand-500/10' : 'border-gray-700 bg-gray-800/50 hover:border-gray-600'
              ]"
              @click="downloadSource = src.key"
            >
              <div class="text-sm font-medium text-white">{{ src.name }}</div>
              <div class="text-xs text-gray-500 mt-0.5">{{ src.desc }}</div>
            </button>
          </div>

          <!-- 操作按钮 -->
          <div class="flex gap-3 justify-end">
            <button class="px-4 py-2 rounded-lg bg-gray-800 text-sm text-gray-400 hover:text-white transition-colors"
              @click="showDownloadDialog = false">取消</button>
            <button class="px-4 py-2 rounded-lg bg-brand-500 text-sm text-white hover:bg-brand-600 transition-colors font-medium"
              @click="startDownload">开始下载</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
