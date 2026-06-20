<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getStorageStats, getStorageConfig, updateStorageConfig, cleanupStorage } from '@/api/system'
import { HardDrive, Database, Folder, Trash2, RefreshCw, AlertCircle, CheckCircle, Settings } from 'lucide-vue-next'

interface StorageStat {
  path: string
  total_gb: number
  used_gb: number
  free_gb: number
  file_count: number
  is_readable: boolean
}

const stats = ref<Record<string, StorageStat>>({})
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const cleanedCount = ref(-1)
const maxStorageGB = ref(100)
const maxWorkspaceGB = ref(10)

async function loadData() {
  loading.value = true
  error.value = ''
  try {
    const [sRes, cRes] = await Promise.all([getStorageStats(), getStorageConfig()])
    stats.value = sRes.data.categories
    maxStorageGB.value = cRes.data.max_storage_gb || 100
    maxWorkspaceGB.value = cRes.data.max_workspace_gb || 10
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    await updateStorageConfig({ max_storage_gb: maxStorageGB.value, max_workspace_gb: maxWorkspaceGB.value })
    await loadData()
  } catch (e: any) {
    error.value = e?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function clean(path: string) {
  try {
    const res = await cleanupStorage(path, 72)
    cleanedCount.value = res.data.deleted
    await loadData()
  } catch (e: any) {
    error.value = e?.message || '清理失败'
  }
}

function formatGB(gb: number) {
  return gb >= 1024 ? `${(gb / 1024).toFixed(1)} TB` : `${gb.toFixed(1)} GB`
}

onMounted(loadData)
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">存储设置</h1>
        <p class="text-gray-400 mt-1">管理你的存储空间</p>
      </div>
      <button class="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-gray-300" @click="loadData" :disabled="loading">
        <RefreshCw :class="['w-4 h-4', loading && 'animate-spin']" /> 刷新
      </button>
    </div>

    <div v-if="error" class="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
      <AlertCircle class="w-4 h-4 shrink-0" /> {{ error }}
    </div>
    <div v-if="cleanedCount >= 0" class="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/30 rounded-xl text-green-400 text-sm">
      <CheckCircle class="w-4 h-4 shrink-0" /> 已清理 {{ cleanedCount }} 个文件
    </div>

    <!-- 总体概览 -->
    <div v-if="stats['storage_root']" class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <div class="p-5 rounded-xl bg-gradient-to-br from-surface-800 to-surface-900 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2"><HardDrive class="w-4 h-4" /> 已使用</div>
        <p class="text-2xl font-bold text-white">{{ formatGB(stats['storage_root'].used_gb) }}</p>
        <p class="text-xs text-gray-500 mt-1">共 {{ formatGB(stats['storage_root'].total_gb) }}</p>
      </div>
      <div class="p-5 rounded-xl bg-gradient-to-br from-surface-800 to-surface-900 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2"><Database class="w-4 h-4" /> 剩余</div>
        <p class="text-2xl font-bold text-green-400">{{ formatGB(stats['storage_root'].free_gb) }}</p>
        <p class="text-xs text-gray-500 mt-1">{{ stats['storage_root'].total_gb > 0 ? ((stats['storage_root'].free_gb / stats['storage_root'].total_gb) * 100).toFixed(1) : 0 }}% 可用</p>
      </div>
      <div class="p-5 rounded-xl bg-gradient-to-br from-surface-800 to-surface-900 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2"><Folder class="w-4 h-4" /> 文件数</div>
        <p class="text-2xl font-bold text-brand-400">{{ stats['storage_root'].file_count.toLocaleString() }}</p>
      </div>
    </div>

    <!-- 配额 -->
    <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
      <h2 class="text-lg font-semibold text-white mb-4 flex items-center gap-2"><Settings class="w-5 h-5" /> 存储配额</h2>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm text-gray-400 mb-1">全局最大存储 (GB)</label>
          <input v-model.number="maxStorageGB" type="number" min="0" class="w-full px-3 py-2 bg-surface-900 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-brand-500" />
        </div>
        <div>
          <label class="block text-sm text-gray-400 mb-1">单工作区最大 (GB)</label>
          <input v-model.number="maxWorkspaceGB" type="number" min="0" class="w-full px-3 py-2 bg-surface-900 border border-white/10 rounded-xl text-white text-sm focus:outline-none focus:border-brand-500" />
        </div>
      </div>
      <button class="mt-4 px-4 py-2 bg-brand-500 hover:bg-brand-600 rounded-xl text-white text-sm transition-colors disabled:opacity-50" @click="saveConfig" :disabled="saving">
        {{ saving ? '保存中...' : '保存设置' }}
      </button>
    </div>

    <!-- 分类 -->
    <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
      <h2 class="text-lg font-semibold text-white mb-4">存储分类</h2>
      <div class="space-y-3">
        <div v-for="(s, key) in stats" :key="key" class="flex items-center justify-between p-3 bg-surface-700/50 rounded-xl">
          <div class="flex items-center gap-3">
            <div class="w-2 h-2 rounded-full" :class="(s.used_gb / s.total_gb) > 0.8 ? 'bg-red-500' : 'bg-brand-500'" />
            <div>
              <p class="text-white text-sm capitalize">{{ key.replace(/_/g, ' ') }}</p>
              <p class="text-xs text-gray-500">{{ formatGB(s.used_gb) }} / {{ formatGB(s.total_gb) }} · {{ s.file_count }} 文件</p>
            </div>
          </div>
          <button class="px-3 py-1 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-lg text-xs transition-colors" @click="clean(s.path)">
            <Trash2 class="w-3 h-3 inline mr-1" /> 清理
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
