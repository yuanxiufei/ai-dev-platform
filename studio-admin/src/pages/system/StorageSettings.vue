<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  getStorageStats,
  getStorageConfig,
  updateStorageConfig,
  cleanupStorage,
  checkStorageQuota,
} from '@/api/system'
import {
  HardDrive, Server, Database, Folder, Cpu, Trash2, RefreshCw, AlertCircle, CheckCircle, Settings
} from 'lucide-vue-next'

interface StorageStat {
  path: string
  total_gb: number
  used_gb: number
  free_gb: number
  file_count: number
  is_readable: boolean
}

interface StorageConfig {
  storage_root: string
  max_storage_gb: number
  max_workspace_gb: number
  models_dir: string
  kb_dir: string
  workspace_dir: string
  backups_dir: string
  data_dir: string
}

const stats = ref<Record<string, StorageStat>>({})
const config = ref<StorageConfig | null>(null)
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
    const [statsRes, configRes] = await Promise.all([
      getStorageStats(),
      getStorageConfig(),
    ])
    stats.value = statsRes.data.categories
    config.value = configRes.data
    maxStorageGB.value = configRes.data.max_storage_gb || 100
    maxWorkspaceGB.value = configRes.data.max_workspace_gb || 10
  } catch (e: any) {
    error.value = e?.message || 'Failed to load storage data'
  } finally {
    loading.value = false
  }
}

async function saveConfig() {
  saving.value = true
  try {
    await updateStorageConfig({
      max_storage_gb: maxStorageGB.value,
      max_workspace_gb: maxWorkspaceGB.value,
    })
    await loadData()
  } catch (e: any) {
    error.value = e?.message || 'Failed to save config'
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
    error.value = e?.message || 'Cleanup failed'
  }
}

function formatGB(gb: number) {
  if (gb >= 1024) return `${(gb / 1024).toFixed(1)} TB`
  return `${gb.toFixed(1)} GB`
}

function usagePercent(used: number, total: number) {
  if (!total) return 0
  return Math.min(100, (used / total) * 100)
}

const totalEntry = computed(() => stats.value['storage_root'])

onMounted(loadData)
</script>

<template>
  <div class="p-6 max-w-6xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">存储管理</h1>
        <p class="text-gray-400 mt-1">管理存储空间分配与文件清理</p>
      </div>
      <button
        class="flex items-center gap-2 px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300 transition-colors"
        @click="loadData"
        :disabled="loading"
      >
        <RefreshCw :class="['w-4 h-4', loading && 'animate-spin']" />
        刷新
      </button>
    </div>

    <!-- Error -->
    <div v-if="error" class="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
      <AlertCircle class="w-4 h-4 shrink-0" />
      {{ error }}
    </div>

    <div v-if="cleanedCount >= 0" class="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm">
      <CheckCircle class="w-4 h-4 shrink-0" />
      已清理 {{ cleanedCount }} 个文件
    </div>

    <!-- 总体概览 -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4" v-if="totalEntry">
      <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2">
          <HardDrive class="w-4 h-4" /> 已使用
        </div>
        <p class="text-2xl font-bold text-white">{{ formatGB(totalEntry.used_gb) }}</p>
        <p class="text-xs text-gray-500 mt-1">共 {{ formatGB(totalEntry.total_gb) }}</p>
      </div>
      <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2">
          <Server class="w-4 h-4" /> 剩余
        </div>
        <p class="text-2xl font-bold text-green-400">{{ formatGB(totalEntry.free_gb) }}</p>
        <p class="text-xs text-gray-500 mt-1">
          {{ totalEntry.total_gb > 0 ? ((totalEntry.free_gb / totalEntry.total_gb) * 100).toFixed(1) : 0 }}% 可用
        </p>
      </div>
      <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
        <div class="flex items-center gap-2 text-gray-400 text-sm mb-2">
          <Folder class="w-4 h-4" /> 文件数
        </div>
        <p class="text-2xl font-bold text-brand-400">{{ totalEntry.file_count.toLocaleString() }}</p>
      </div>
    </div>

    <!-- 配额配置 -->
    <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
      <h2 class="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Settings class="w-5 h-5" /> 存储配额
      </h2>
      <div class="grid grid-cols-2 gap-4">
        <div>
          <label class="block text-sm text-gray-400 mb-1">全局最大存储 (GB)</label>
          <input
            v-model.number="maxStorageGB"
            type="number"
            min="0"
            class="w-full px-3 py-2 bg-surface-900 border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-brand-500"
          />
          <p class="text-xs text-gray-500 mt-1">0 = 不限</p>
        </div>
        <div>
          <label class="block text-sm text-gray-400 mb-1">单工作区最大 (GB)</label>
          <input
            v-model.number="maxWorkspaceGB"
            type="number"
            min="0"
            class="w-full px-3 py-2 bg-surface-900 border border-white/10 rounded-lg text-white text-sm focus:outline-none focus:border-brand-500"
          />
          <p class="text-xs text-gray-500 mt-1">0 = 不限</p>
        </div>
      </div>
      <button
        class="mt-4 px-4 py-2 bg-brand-500 hover:bg-brand-600 rounded-lg text-white text-sm transition-colors disabled:opacity-50"
        @click="saveConfig"
        :disabled="saving"
      >
        {{ saving ? '保存中...' : '保存设置' }}
      </button>
    </div>

    <!-- 分类详情 -->
    <div class="p-5 rounded-xl bg-surface-800 border border-white/10">
      <h2 class="text-lg font-semibold text-white mb-4">存储分类</h2>
      <div class="overflow-x-auto">
        <table class="w-full text-sm">
          <thead>
            <tr class="text-left text-gray-400 border-b border-white/10">
              <th class="py-2 pr-4 font-medium">类别</th>
              <th class="py-2 pr-4 font-medium">路径</th>
              <th class="py-2 pr-4 font-medium text-right">已用/总量</th>
              <th class="py-2 pr-4 font-medium text-right">文件数</th>
              <th class="py-2 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="(s, key) in stats"
              :key="key"
              class="border-b border-white/5 text-gray-300 hover:bg-white/5"
            >
              <td class="py-3 pr-4 text-white capitalize">{{ key.replace(/_/g, ' ') }}</td>
              <td class="py-3 pr-4 font-mono text-xs text-gray-500">{{ s.path }}</td>
              <td class="py-3 pr-4 text-right">
                <div class="flex items-center justify-end gap-2">
                  <div class="w-20 h-1.5 bg-surface-700 rounded-full overflow-hidden">
                    <div
                      class="h-full rounded-full transition-all"
                      :class="usagePercent(s.used_gb, s.total_gb) > 80 ? 'bg-red-500' : 'bg-brand-500'"
                      :style="{ width: usagePercent(s.used_gb, s.total_gb) + '%' }"
                    />
                  </div>
                  <span>{{ formatGB(s.used_gb) }} / {{ formatGB(s.total_gb) }}</span>
                </div>
              </td>
              <td class="py-3 pr-4 text-right">{{ s.file_count.toLocaleString() }}</td>
              <td class="py-3 text-right">
                <button
                  class="px-3 py-1 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded text-xs transition-colors"
                  @click="clean(s.path)"
                >
                  清理
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
