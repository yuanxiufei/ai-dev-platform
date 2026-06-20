<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getHealth, getDetailedHealth, getGPUDevices,
  getSystemResources, getGPUStats,
  getHealthStats, listCheckpoints, createCheckpoint,
  restoreCheckpoint, deleteCheckpoint, reloadConfig,
} from '@/api/system'
import {
  Activity, Cpu, MemoryStick, HardDrive, Server, Zap,
  Wrench, RefreshCw, Shield, AlertCircle, CheckCircle,
  RotateCcw, Plus, Trash2,
} from 'lucide-vue-next'

const health = ref<any>(null)
const detailed = ref<any>(null)
const gpuDevices = ref<any[]>([])
const resources = ref<any>(null)
const checkpoints = ref<any[]>([])
const loading = ref(true)
const error = ref('')
const actionMsg = ref('')

async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [
      healthRes, detailedRes, gpuRes, resRes, gpuStatRes, statRes, cpRes,
    ] = await Promise.allSettled([
      getHealth(),
      getDetailedHealth(),
      getGPUDevices(),
      getSystemResources(),
      getGPUStats(),
      getHealthStats(),
      listCheckpoints(),
    ])
    if (healthRes.status === 'fulfilled') health.value = healthRes.value.data
    if (detailedRes.status === 'fulfilled') detailed.value = detailedRes.value.data
    if (gpuRes.status === 'fulfilled') gpuDevices.value = gpuRes.value.data?.devices || []
    if (resRes.status === 'fulfilled') resources.value = resRes.value.data
    if (cpRes.status === 'fulfilled') checkpoints.value = cpRes.value.data || []
  } catch (e: any) {
    error.value = e?.message || 'Failed to load system data'
  } finally {
    loading.value = false
  }
}

async function doCreateCheckpoint() {
  try {
    const res = await createCheckpoint('manual-snap')
    actionMsg.value = `检查点已创建: ${res.data.id}`
    await loadAll()
    setTimeout(() => (actionMsg.value = ''), 3000)
  } catch (e: any) {
    actionMsg.value = `创建失败: ${e?.message}`
  }
}

async function doRestore(id: string) {
  if (!confirm(`确定回滚到检查点 ${id}？`)) return
  try {
    await restoreCheckpoint(id)
    actionMsg.value = `已回滚到 ${id}`
    await loadAll()
    setTimeout(() => (actionMsg.value = ''), 3000)
  } catch (e: any) {
    actionMsg.value = `回滚失败: ${e?.message}`
  }
}

async function doDeleteCheckpoint(id: string) {
  try {
    await deleteCheckpoint(id)
    await loadAll()
  } catch (e: any) { /* ignore */ }
}

async function doReloadConfig() {
  try {
    await reloadConfig()
    actionMsg.value = '配置已重载'
    setTimeout(() => (actionMsg.value = ''), 3000)
  } catch (e: any) {
    actionMsg.value = `重载失败: ${e?.message}`
  }
}

onMounted(loadAll)
</script>

<template>
  <div class="p-6 max-w-6xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">系统管理</h1>
        <p class="text-gray-400 mt-1">健康状态、资源监控与安全设置</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 text-sm transition-colors"
          @click="doReloadConfig"
        >
          <RefreshCw class="w-4 h-4" /> 重载配置
        </button>
        <button
          class="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 text-sm transition-colors"
          @click="loadAll" :disabled="loading"
        >
          <RefreshCw :class="['w-4 h-4', loading && 'animate-spin']" />
          刷新
        </button>
      </div>
    </div>

    <div v-if="actionMsg" class="flex items-center gap-2 p-3 bg-brand-500/10 border border-brand-500/30 rounded-lg text-brand-400 text-sm">
      <Zap class="w-4 h-4 shrink-0" /> {{ actionMsg }}
    </div>

    <div v-if="error" class="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
      <AlertCircle class="w-4 h-4 shrink-0" /> {{ error }}
    </div>

    <!-- 健康状态 -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2">
          <Activity class="w-4 h-4" /> 服务状态
        </div>
        <p :class="['text-2xl font-bold', health?.status === 'ok' ? 'text-green-400' : 'text-red-400']">
          {{ health?.status || 'unknown' }}
        </p>
      </div>
      <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2">
          <Shield class="w-4 h-4" /> 数据库
        </div>
        <p :class="['text-2xl font-bold', detailed?.database === 'ok' ? 'text-green-400' : 'text-red-400']">
          {{ detailed?.database || 'unknown' }}
        </p>
      </div>
      <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2">
          <Cpu class="w-4 h-4" /> GPU 设备
        </div>
        <p class="text-2xl font-bold text-brand-400">{{ gpuDevices.length }}</p>
      </div>
    </div>

    <!-- GPU 设备 -->
    <div v-if="gpuDevices.length > 0" class="p-5 rounded-xl bg-surface-800 border border-white/10">
      <h2 class="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Cpu class="w-5 h-5" /> GPU 设备
      </h2>
      <div class="space-y-3">
        <div
          v-for="gpu in gpuDevices"
          :key="gpu.index"
          class="p-3 bg-surface-700/50 rounded-lg flex items-center justify-between"
        >
          <div>
            <p class="text-white font-medium">{{ gpu.name || `GPU ${gpu.index}` }}</p>
            <p class="text-xs text-gray-500 mt-1">
              VRAM: {{ gpu.memory_used_mb || 0 }}/{{ gpu.memory_total_mb || 0 }} MB
              | 温度: {{ gpu.temperature_c || '-' }}°C
            </p>
          </div>
          <div class="flex items-center gap-3">
            <div class="w-24 h-2 bg-surface-600 rounded-full overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="(gpu.memory_used_mb / gpu.memory_total_mb) > 0.85 ? 'bg-red-500' : 'bg-brand-500'"
                :style="{ width: gpu.memory_total_mb ? ((gpu.memory_used_mb / gpu.memory_total_mb) * 100) + '%' : '0%' }"
              />
            </div>
            <span class="text-xs text-gray-400">
              {{ gpu.memory_total_mb ? ((gpu.memory_used_mb / gpu.memory_total_mb) * 100).toFixed(0) : 0 }}%
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 检查点管理 -->
    <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-semibold text-white flex items-center gap-2">
          <RotateCcw class="w-5 h-5" /> Git 检查点
        </h2>
        <button
          class="flex items-center gap-1 px-3 py-1.5 bg-brand-500 hover:bg-brand-600 rounded-lg text-white text-sm transition-colors"
          @click="doCreateCheckpoint"
        >
          <Plus class="w-4 h-4" /> 创建检查点
        </button>
      </div>
      <div v-if="checkpoints.length === 0" class="text-gray-500 text-sm py-4 text-center">
        暂无检查点
      </div>
      <div v-else class="space-y-2">
        <div
          v-for="cp in checkpoints"
          :key="cp.id"
          class="flex items-center justify-between p-3 bg-surface-700/50 rounded-lg"
        >
          <div>
            <p class="text-white text-sm font-mono">{{ cp.id }}</p>
            <p class="text-xs text-gray-500 mt-1">
              ref: {{ cp.git_ref }} | {{ cp.file_count }} 文件 | {{ new Date(cp.timestamp).toLocaleString() }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="px-3 py-1 bg-amber-500/10 hover:bg-amber-500/20 text-amber-400 rounded text-xs transition-colors"
              @click="doRestore(cp.id)"
            >
              回滚
            </button>
            <button
              class="px-3 py-1 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded text-xs transition-colors"
              @click="doDeleteCheckpoint(cp.id)"
            >
              <Trash2 class="w-3 h-3" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 资源使用 -->
    <div v-if="resources" class="p-5 rounded-xl bg-surface-800 border border-white/10">
      <h2 class="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Activity class="w-5 h-5" /> 系统资源
      </h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
        <div class="p-3 bg-surface-700/50 rounded-lg">
          <p class="text-gray-400 text-xs mb-1">CPU</p>
          <p class="text-white text-lg font-bold">{{ resources?.cpu_percent || 0 }}%</p>
        </div>
        <div class="p-3 bg-surface-700/50 rounded-lg">
          <p class="text-gray-400 text-xs mb-1">内存</p>
          <p class="text-white text-lg font-bold">{{ resources?.memory_percent || 0 }}%</p>
        </div>
        <div class="p-3 bg-surface-700/50 rounded-lg">
          <p class="text-gray-400 text-xs mb-1">磁盘</p>
          <p class="text-white text-lg font-bold">{{ resources?.disk_percent || 0 }}%</p>
        </div>
        <div class="p-3 bg-surface-700/50 rounded-lg">
          <p class="text-gray-400 text-xs mb-1">网络</p>
          <p class="text-white text-lg font-bold">{{ resources?.network_mbps || 0 }} MB/s</p>
        </div>
      </div>
    </div>
  </div>
</template>
