<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  getInstalledPlugins, uninstallPlugin, togglePlugin, updatePluginConfig,
  type PluginInstalled,
} from '@/api/plugin-marketplace'
import { Puzzle, Trash2, Package, RefreshCw, Settings, Loader2, CheckCircle, X } from '@/components/icons'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const plugins = ref<PluginInstalled[]>([])
const loading = ref(false)
const actionLoading = ref<string | null>(null)
const showConfig = ref<string | null>(null)
const configForm = ref<Record<string, unknown>>({})

async function fetchInstalled() {
  loading.value = true
  try {
    const res = await getInstalledPlugins()
    plugins.value = res.data
  } catch (e) {
    console.error('Failed to fetch installed plugins', e)
    appStore.toast?.error('无法加载已安装插件')
  } finally {
    loading.value = false
  }
}

async function handleUninstall(plugin: PluginInstalled) {
  if (!confirm(`确定要卸载 "${plugin.display_name}" 吗？此操作不可撤销。`)) return
  actionLoading.value = plugin.name
  try {
    await uninstallPlugin(plugin.name)
    plugins.value = plugins.value.filter(p => p.name !== plugin.name)
    appStore.toast?.success(`插件 ${plugin.display_name} 已卸载`)
  } catch (e) {
    appStore.toast?.error('卸载失败')
  } finally {
    actionLoading.value = null
  }
}

async function handleToggle(plugin: PluginInstalled) {
  actionLoading.value = plugin.name
  try {
    const res = await togglePlugin(plugin.name)
    plugin.enabled = res.enabled
    appStore.toast?.success(res.enabled ? `${plugin.display_name} 已启用` : `${plugin.display_name} 已禁用`)
  } catch (e) {
    appStore.toast?.error('切换状态失败')
  } finally {
    actionLoading.value = null
  }
}

function openConfig(plugin: PluginInstalled) {
  showConfig.value = plugin.name
  configForm.value = { ...(plugin.config || {}) }
}

async function saveConfig(plugin: PluginInstalled) {
  actionLoading.value = plugin.name
  try {
    const res = await updatePluginConfig(plugin.name, configForm.value)
    plugin.config = res.config
    showConfig.value = null
    appStore.toast?.success('配置已更新')
  } catch (e) {
    appStore.toast?.error('保存配置失败')
  } finally {
    actionLoading.value = null
  }
}

onMounted(fetchInstalled)
</script>

<template>
  <div class="h-full flex flex-col p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-3">
          <Package class="w-7 h-7 text-brand-400" />
          我的插件
        </h1>
        <p class="text-sm text-gray-400 mt-1">管理已安装的 MCP / AWP 插件</p>
      </div>
      <button
        class="px-4 py-2 rounded-lg bg-white/5 text-sm text-gray-300 hover:bg-white/10 flex items-center gap-2 transition-colors"
        @click="fetchInstalled"
      >
        <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': loading }" />
        刷新
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <Loader2 class="w-8 h-8 animate-spin text-brand-400" />
    </div>

    <!-- Plugin List -->
    <div v-else class="flex-1 overflow-y-auto">
      <div v-if="plugins.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-500">
        <Package class="w-12 h-12 mb-4 opacity-50" />
        <p class="text-lg">还没有安装任何插件</p>
        <p class="text-sm mt-1">前往插件市场发现并安装插件</p>
      </div>

      <div v-else class="space-y-3">
        <div
          v-for="plugin in plugins"
          :key="plugin.name"
          class="bg-white/5 border border-white/10 rounded-xl p-5 hover:border-white/20 transition-all"
        >
          <div class="flex items-start justify-between">
            <!-- Info -->
            <div class="flex-1">
              <div class="flex items-center gap-3 mb-2">
                <Puzzle
                  :class="[
                    'w-5 h-5',
                    plugin.type === 'mcp' ? 'text-blue-400' : 'text-purple-400',
                  ]"
                />
                <h3 class="text-white font-semibold">{{ plugin.display_name }}</h3>
                <span
                  :class="[
                    'text-xs px-2 py-0.5 rounded font-medium',
                    plugin.type === 'mcp'
                      ? 'bg-blue-500/20 text-blue-400'
                      : 'bg-purple-500/20 text-purple-400',
                  ]"
                >
                  {{ plugin.type === 'mcp' ? 'MCP' : 'AWP' }}
                </span>
                <span
                  :class="[
                    'text-xs px-2 py-0.5 rounded',
                    plugin.enabled
                      ? 'bg-green-500/20 text-green-400'
                      : 'bg-gray-500/20 text-gray-400',
                  ]"
                >
                  {{ plugin.enabled ? '已启用' : '已禁用' }}
                </span>
              </div>
              <p class="text-sm text-gray-400 mb-2">{{ plugin.desc || '无描述' }}</p>
              <div class="flex items-center gap-4 text-xs text-gray-500">
                <span>{{ plugin.author }}</span>
                <span>v{{ plugin.version }}</span>
                <span>安装于 {{ plugin.installed_at ? new Date(plugin.installed_at).toLocaleDateString() : '-' }}</span>
              </div>
            </div>

            <!-- Actions -->
            <div class="flex items-center gap-2 ml-4">
              <!-- Toggle -->
              <button
                class="px-3 py-1.5 text-xs rounded-lg transition-colors"
                :class="[
                  plugin.enabled
                    ? 'bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30'
                    : 'bg-green-500/20 text-green-400 hover:bg-green-500/30',
                ]"
                :disabled="actionLoading === plugin.name"
                @click="handleToggle(plugin)"
              >
                <Loader2 v-if="actionLoading === plugin.name" class="w-3.5 h-3.5 animate-spin" />
                <template v-else>{{ plugin.enabled ? '停用' : '启用' }}</template>
              </button>

              <!-- Config -->
              <button
                class="px-3 py-1.5 text-xs rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 transition-colors flex items-center gap-1"
                @click="openConfig(plugin)"
              >
                <Settings class="w-3.5 h-3.5" />
                配置
              </button>

              <!-- Uninstall -->
              <button
                class="px-3 py-1.5 text-xs rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors flex items-center gap-1"
                :disabled="actionLoading === plugin.name"
                @click="handleUninstall(plugin)"
              >
                <Trash2 class="w-3.5 h-3.5" />
                卸载
              </button>
            </div>
          </div>

          <!-- Config Panel -->
          <div
            v-if="showConfig === plugin.name"
            class="mt-4 p-4 bg-black/20 rounded-lg border border-white/5"
          >
            <h4 class="text-sm font-medium text-white mb-3">插件配置</h4>
            <div v-if="Object.keys(plugin.config).length === 0" class="text-xs text-gray-500 mb-3">
              此插件暂无配置项
            </div>
            <div v-else class="space-y-3">
              <div v-for="(value, key) in configForm" :key="key" class="flex items-start gap-3">
                <label class="text-xs text-gray-400 w-40 shrink-0 pt-1.5">{{ key }}</label>
                <input
                  v-if="typeof value === 'string'"
                  v-model="configForm[key as string]"
                  type="text"
                  class="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-brand-400/50"
                />
                <input
                  v-else-if="typeof value === 'number'"
                  v-model="configForm[key as string]"
                  type="number"
                  class="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-brand-400/50"
                />
                <label v-else-if="typeof value === 'boolean'" class="flex items-center gap-2">
                  <input v-model="configForm[key as string]" type="checkbox" class="accent-brand-400" />
                  <span class="text-sm text-gray-400">{{ configForm[key as string] ? 'true' : 'false' }}</span>
                </label>
                <input
                  v-else
                  v-model="configForm[key as string]"
                  type="text"
                  class="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-brand-400/50"
                />
              </div>
            </div>
            <div class="flex justify-end gap-2 mt-4">
              <button
                class="px-3 py-1.5 text-xs rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 transition-colors"
                @click="showConfig = null"
              >
                取消
              </button>
              <button
                class="px-3 py-1.5 text-xs rounded-lg bg-brand-500/20 text-brand-400 hover:bg-brand-500/30 transition-colors"
                :disabled="actionLoading === plugin.name"
                @click="saveConfig(plugin)"
              >
                <Loader2 v-if="actionLoading === plugin.name" class="w-3.5 h-3.5 animate-spin mr-1 inline" />
                保存配置
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
