<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  getPluginRegistry, getCategories, installPlugin,
  type PluginRegistryItem,
} from '@/api/plugin-marketplace'
import { Store, Download, ExternalLink, CheckCircle, Search, Loader2 } from '@/components/icons'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
const plugins = ref<PluginRegistryItem[]>([])
const categories = ref<string[]>([])
const types = ref<string[]>([])
const loading = ref(false)
const installing = ref<string | null>(null)
const total = ref(0)
const page = ref(1)
const size = 20

const search = ref('')
const selectedCategory = ref('')
const selectedType = ref('')

const categoryLabel = (cat: string) => {
  const map: Record<string, string> = {
    filesystem: '文件系统', devops: 'DevOps', database: '数据库',
    search: '搜索', browser: '浏览器', 'code-quality': '代码质量',
    generator: '代码生成', translation: '翻译', documentation: '文档',
  }
  return map[cat] || cat
}

const typeBadge = (t: string) => t === 'mcp' ? 'MCP' : 'AWP'

const ratingStars = (r: number) => '★'.repeat(Math.round(r)) + '☆'.repeat(5 - Math.round(r))

async function fetchData() {
  loading.value = true
  try {
    const res = await getPluginRegistry({
      search: search.value || undefined,
      category: selectedCategory.value || undefined,
      plugin_type: selectedType.value || undefined,
      page: page.value,
      size,
    })
    plugins.value = res.data
    total.value = res.total
    categories.value = res.categories
    types.value = res.types
  } catch (e) {
    console.error('Failed to fetch plugin registry', e)
    appStore.toast?.error('无法加载插件市场')
  } finally {
    loading.value = false
  }
}

async function handleInstall(plugin: PluginRegistryItem) {
  if (installing.value) return
  installing.value = plugin.name
  try {
    const res = await installPlugin(plugin.name)
    plugin.installed = true
    plugin.installed_version = res.version
    plugin.installed_enabled = true
    appStore.toast?.success(`插件 ${res.plugin} 安装成功`)
  } catch (e) {
    console.error('Install failed', e)
    appStore.toast?.error('安装失败')
  } finally {
    installing.value = null
  }
}

function handleSearch() {
  page.value = 1
  fetchData()
}

onMounted(() => {
  fetchData()
  getCategories().then(r => {
    categories.value = r.categories.map(c => c.name)
  }).catch((err: unknown) => {
    console.warn('[PluginMarketplace] Failed to fetch categories', err)
  })
})
</script>

<template>
  <div class="h-full flex flex-col p-6">
    <!-- Header -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-3">
          <Store class="w-7 h-7 text-brand-400" />
          插件市场
        </h1>
        <p class="text-sm text-gray-400 mt-1">发现并安装 MCP / AWP 插件，扩展平台能力</p>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex flex-wrap gap-3 mb-6">
      <div class="relative flex-1 min-w-[200px] max-w-md">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input
          v-model="search"
          type="text"
          placeholder="搜索插件名称、描述或标签..."
          class="w-full bg-white/5 border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-400/50 transition-colors"
          @keydown.enter="handleSearch"
        />
      </div>

      <select
        v-model="selectedCategory"
        class="bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-brand-400/50"
        @change="handleSearch"
      >
        <option value="">全部分类</option>
        <option v-for="cat in categories" :key="cat" :value="cat">{{ categoryLabel(cat) }}</option>
      </select>

      <select
        v-model="selectedType"
        class="bg-white/5 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-brand-400/50"
        @change="handleSearch"
      >
        <option value="">全部类型</option>
        <option value="mcp">MCP 服务器</option>
        <option value="awp">AWP 插件</option>
      </select>

      <span class="text-xs text-gray-500 self-center ml-auto">{{ total }} 个结果</span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <Loader2 class="w-8 h-8 animate-spin text-brand-400" />
    </div>

    <!-- Plugin Cards -->
    <div v-else class="flex-1 overflow-y-auto">
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <div
          v-for="plugin in plugins"
          :key="plugin.name"
          class="bg-white/5 border border-white/10 rounded-xl p-5 hover:border-brand-400/30 hover:bg-white/[0.07] transition-all duration-200 flex flex-col"
        >
          <!-- Header -->
          <div class="flex items-start justify-between mb-3">
            <div class="flex-1 min-w-0">
              <h3 class="text-white font-semibold truncate">{{ plugin.display_name }}</h3>
              <p class="text-xs text-gray-500 mt-0.5">{{ plugin.author }} · v{{ plugin.version }}</p>
            </div>
            <span
              :class="[
                'shrink-0 text-xs px-2 py-0.5 rounded font-medium',
                plugin.type === 'mcp'
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'bg-purple-500/20 text-purple-400',
              ]"
            >
              {{ typeBadge(plugin.type) }}
            </span>
          </div>

          <!-- Description -->
          <p class="text-sm text-gray-400 mb-4 line-clamp-2 flex-1">{{ plugin.desc }}</p>

          <!-- Tags -->
          <div class="flex flex-wrap gap-1.5 mb-3">
            <span
              v-for="tag in plugin.tags.slice(0, 4)"
              :key="tag"
              class="text-xs px-2 py-0.5 rounded-full bg-white/5 text-gray-500"
            >{{ tag }}</span>
          </div>

          <!-- Stats -->
          <div class="flex items-center gap-4 mb-4 text-xs text-gray-500">
            <span class="text-yellow-500">{{ ratingStars(plugin.rating) }}</span>
            <span>{{ (plugin.rating).toFixed(1) }}</span>
            <span>{{ (plugin.installs / 1000).toFixed(1) }}k 安装</span>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-2 pt-3 border-t border-white/5">
            <a
              v-if="plugin.repo"
              :href="plugin.repo"
              target="_blank"
              class="text-xs text-gray-500 hover:text-gray-300 flex items-center gap-1 transition-colors"
            >
              <ExternalLink class="w-3 h-3" />
              仓库
            </a>

            <button
              v-if="plugin.installed"
              disabled
              class="ml-auto px-3 py-1.5 rounded-lg bg-green-500/20 text-green-400 text-xs font-medium flex items-center gap-1.5 border border-green-500/30"
            >
              <CheckCircle class="w-3.5 h-3.5" />
              已安装
            </button>
            <button
              v-else
              class="ml-auto px-3 py-1.5 rounded-lg bg-brand-500/20 text-brand-400 hover:bg-brand-500/30 text-xs font-medium flex items-center gap-1.5 border border-brand-500/30 transition-colors"
              :disabled="installing === plugin.name"
              @click="handleInstall(plugin)"
            >
              <Loader2 v-if="installing === plugin.name" class="w-3.5 h-3.5 animate-spin" />
              <Download v-else class="w-3.5 h-3.5" />
              {{ installing === plugin.name ? '安装中...' : '安装' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Empty -->
      <div v-if="plugins.length === 0" class="flex flex-col items-center justify-center py-20 text-gray-500">
        <Store class="w-12 h-12 mb-4 opacity-50" />
        <p class="text-lg">未找到匹配的插件</p>
        <p class="text-sm mt-1">尝试其他搜索词或筛选条件</p>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > size" class="flex items-center justify-center gap-2 mt-4 pt-4 border-t border-white/5">
      <button
        class="px-3 py-1.5 text-sm rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 disabled:opacity-30 transition-colors"
        :disabled="page <= 1"
        @click="page--; fetchData()"
      >上一页</button>
      <span class="text-sm text-gray-500 px-3">{{ page }} / {{ Math.ceil(total / size) }}</span>
      <button
        class="px-3 py-1.5 text-sm rounded-lg bg-white/5 text-gray-400 hover:bg-white/10 disabled:opacity-30 transition-colors"
        :disabled="page >= Math.ceil(total / size)"
        @click="page++; fetchData()"
      >下一页</button>
    </div>
  </div>
</template>
