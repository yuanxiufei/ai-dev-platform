<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import {
  Search, Loader2, ExternalLink, Download, CheckCircle, Store,
  Package, Wrench, Globe, Database, FileCode, Bot, Server, Unlink2,
  Settings2, X, RefreshCw, Plus, Trash2, FolderOpen,
  Github, Archive, FolderGit2, Tag, Sparkles, Terminal, Webhook, Eye, EyeOff,
} from 'lucide-vue-next'
import {
  getPluginRegistry, installPlugin, uninstallPlugin,
  getInstalledPlugins, togglePlugin, getCategories,
  getMarketplaceSources, addMarketplaceSource,
  removeMarketplaceSource, toggleMarketplaceSource,
  getMarketplaceStats,
  type PluginRegistryItem, type MarketplaceSource, type MarketplaceStats,
} from '@/api/plugin-marketplace'

// ── 响应式状态 ──────────────────────────────────────────
const plugins = ref<PluginRegistryItem[]>([])
const installedPlugins = ref<PluginRegistryItem[]>([])
const categories = ref<string[]>([])
const sources = ref<MarketplaceSource[]>([])
const stats = ref<MarketplaceStats | null>(null)
const loading = ref(false)
const installing = ref<string | null>(null)
const toastMsg = ref('')
const total = ref(0)
const page = ref(1)
const size = 20

const activeTab = ref<'market' | 'installed'>('market')
const search = ref('')
const selectedCategory = ref('')
const selectedType = ref('')
const selectedSource = ref('')
const showPluginDetail = ref<PluginRegistryItem | null>(null)
const showAddSource = ref(false)
const sourceType = ref<'github' | 'zip' | 'local'>('github')
const sourceUrl = ref('')
const sourceName = ref('')
const sourceDesc = ref('')

let searchTimer: ReturnType<typeof setTimeout> | null = null
let toastTimer: ReturnType<typeof setTimeout> | null = null

// ── 工具函数 ────────────────────────────────────────────

function showToast(msg: string) {
  toastMsg.value = msg
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastMsg.value = '' }, 3000)
}

const ratingStars = (r: number) => '★'.repeat(Math.round(r)) + '☆'.repeat(5 - Math.round(r))

const formatCount = (n: number): string => {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return `${n}`
}

// ── 类型标签配置 ────────────────────────────────────────

const typeMeta: Record<string, { label: string; icon: any; cls: string }> = {
  mcp: { label: 'MCP', icon: Server, cls: 'bg-blue-500/10 text-blue-400 border-blue-500/20' },
  awp: { label: 'AWP', icon: Package, cls: 'bg-purple-500/10 text-purple-400 border-purple-500/20' },
  skill: { label: 'Skill', icon: Sparkles, cls: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' },
  command: { label: '命令', icon: Terminal, cls: 'bg-amber-500/10 text-amber-400 border-amber-500/20' },
  hook: { label: 'Hook', icon: Webhook, cls: 'bg-rose-500/10 text-rose-400 border-rose-500/20' },
}

const categoryMeta: Record<string, { label: string; icon: any }> = {
  filesystem: { label: '文件系统', icon: FileCode },
  devops: { label: 'DevOps', icon: Wrench },
  database: { label: '数据库', icon: Database },
  search: { label: '搜索', icon: Search },
  browser: { label: '浏览器', icon: Globe },
  'code-quality': { label: '代码质量', icon: Package },
  generator: { label: '代码生成', icon: Bot },
  translation: { label: '翻译', icon: Globe },
  documentation: { label: '文档', icon: FileCode },
  communication: { label: '通讯', icon: Globe },
  design: { label: '设计', icon: Package },
  ai: { label: 'AI 模型', icon: Bot },
  agent: { label: 'Agent', icon: Bot },
}

const typeFilterOptions = [
  { value: '', label: '全部类型', icon: Package },
  { value: 'mcp', label: 'MCP 服务器', icon: Server },
  { value: 'awp', label: 'AWP 插件', icon: Package },
  { value: 'skill', label: '技能指令', icon: Sparkles },
  { value: 'command', label: '命令', icon: Terminal },
  { value: 'hook', label: '钩子', icon: Webhook },
]

// ── 计算属性 ────────────────────────────────────────────

const enabledSources = computed(() => sources.value.filter(s => s.enabled))

const filteredSources = computed(() => sources.value)

const installedCount = computed(() => installedPlugins.value.length)

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size)))

// ── 数据获取 ────────────────────────────────────────────

async function fetchData() {
  loading.value = true
  try {
    const res = await getPluginRegistry({
      search: search.value || undefined,
      category: selectedCategory.value || undefined,
      plugin_type: selectedType.value || undefined,
      source_id: selectedSource.value || undefined,
      page: page.value,
      size,
    })
    plugins.value = res.data || []
    total.value = res.total || 0
    if (!categories.value.length) categories.value = res.categories || []
  } catch {
    showToast('无法加载插件市场')
  } finally {
    loading.value = false
  }
}

async function fetchCategories() {
  try {
    const res = await getCategories()
    categories.value = res.categories?.map((c: any) => typeof c === 'string' ? c : c.name) || []
  } catch { /* */ }
}

async function fetchSources() {
  try {
    const res = await getMarketplaceSources()
    sources.value = res.sources || []
  } catch { /* */ }
}

async function fetchInstalled() {
  try {
    const result = await getInstalledPlugins()
    installedPlugins.value = Array.isArray(result) ? result : []
  } catch { /* */ }
}

async function fetchStats() {
  try {
    stats.value = await getMarketplaceStats()
  } catch { /* */ }
}

// ── 操作函数 ────────────────────────────────────────────

async function handleInstall(plugin: PluginRegistryItem) {
  if (installing.value) return
  installing.value = plugin.name
  try {
    await installPlugin(plugin.name)
    plugin.installed = true
    plugin.installed_version = plugin.version
    plugin.installed_enabled = true
    showToast(`${plugin.display_name} 安装成功`)
    fetchInstalled()
  } catch {
    showToast('安装失败')
  } finally {
    installing.value = null
  }
}

async function handleUninstall(plugin: PluginRegistryItem) {
  if (!confirm(`确定卸载 ${plugin.display_name}？`)) return
  installing.value = plugin.name
  try {
    await uninstallPlugin(plugin.name)
    plugin.installed = false
    plugin.installed_enabled = false
    showToast(`${plugin.display_name} 已卸载`)
    fetchInstalled()
  } catch {
    showToast('卸载失败')
  } finally {
    installing.value = null
  }
}

async function handleToggle(plugin: PluginRegistryItem) {
  try {
    const res = await togglePlugin(plugin.name)
    plugin.installed_enabled = res.enabled
    showToast(res.enabled ? `${plugin.display_name} 已启用` : `${plugin.display_name} 已禁用`)
  } catch { /* */ }
}

function handleSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => {
    page.value = 1
    fetchData()
  }, 300)
}

function handleSourceSelect(sourceId: string) {
  selectedSource.value = sourceId
  page.value = 1
  fetchData()
}

async function handleAddSource() {
  if (!sourceName.value.trim()) { showToast('请输入市场源名称'); return }
  if (!sourceUrl.value.trim() && sourceType.value !== 'local') { showToast('请输入市场源地址'); return }
  try {
    await addMarketplaceSource({
      name: sourceName.value.trim(),
      type: sourceType.value,
      url: sourceUrl.value.trim(),
      description: sourceDesc.value.trim(),
    })
    showToast(`市场源「${sourceName.value}」已添加`)
    sourceName.value = ''
    sourceUrl.value = ''
    sourceDesc.value = ''
    sourceType.value = 'github'
    showAddSource.value = false
    fetchSources()
  } catch {
    showToast('添加失败')
  }
}

async function handleRemoveSource(source: MarketplaceSource) {
  if (!confirm(`确定删除市场源「${source.name}」？`)) return
  try {
    await removeMarketplaceSource(source.id)
    showToast(`市场源「${source.name}」已删除`)
    if (selectedSource.value === source.id) {
      selectedSource.value = ''
      fetchData()
    }
    fetchSources()
  } catch { /* */ }
}

async function handleToggleSource(source: MarketplaceSource) {
  try {
    const res = await toggleMarketplaceSource(source.id)
    source.enabled = res.enabled
    showToast(res.enabled ? `已启用「${source.name}」` : `已禁用「${source.name}」`)
    fetchData()
  } catch { /* */ }
}

function onSearchKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    if (searchTimer) clearTimeout(searchTimer)
    page.value = 1
    fetchData()
  }
}

// ── 生命周期 ────────────────────────────────────────────

watch(search, handleSearch)

onMounted(() => {
  fetchData()
  fetchCategories()
  fetchSources()
  fetchInstalled()
  fetchStats()
})

// ── 样式辅助 ────────────────────────────────────────────

function tabClass(tab: string) {
  return [
    'px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200',
    activeTab === tab
      ? 'bg-brand-500/10 text-brand-400'
      : 'text-gray-500 hover:text-gray-300',
  ]
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Toast -->
    <Transition name="slide-down">
      <div v-if="toastMsg" class="fixed top-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl text-sm font-medium bg-green-500/15 border border-green-500/25 text-green-400 backdrop-blur-xl shadow-xl pointer-events-none">
        {{ toastMsg }}
      </div>
    </Transition>

    <!-- Header -->
    <div class="flex items-center justify-between px-8 pt-8 pb-4 border-b border-white/5">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/20 to-brand-500/10 border border-purple-500/20 flex items-center justify-center">
            <Store class="w-5 h-5 text-purple-400" />
          </div>
          插件市场
        </h1>
        <p class="text-sm text-gray-500 mt-1.5 ml-[3.25rem]">发现和安装技能指令、MCP服务器、命令钩子，扩展 AI 工作台能力</p>
      </div>
      <div class="flex items-center gap-3">
        <!-- 统计概览 -->
        <div v-if="stats" class="hidden xl:flex items-center gap-4 text-[10px] text-gray-600">
          <span class="flex items-center gap-1"><Package class="w-3 h-3" />{{ stats.total_plugins }} 个插件</span>
          <span class="flex items-center gap-1"><CheckCircle class="w-3 h-3 text-green-500/60" />{{ stats.total_installed }} 已安装</span>
        </div>
        <!-- Tabs -->
        <div class="flex bg-white/[0.03] border border-white/5 rounded-xl p-1 gap-0.5">
          <button @click="activeTab = 'market'" :class="tabClass('market')">
            <Store class="w-3.5 h-3.5 inline mr-1.5" />市场
          </button>
          <button @click="activeTab = 'installed'; fetchInstalled()" :class="tabClass('installed')">
            <Package class="w-3.5 h-3.5 inline mr-1.5" />已安装 {{ installedCount }}
          </button>
        </div>
      </div>
    </div>

    <!-- Source Tabs (Market only) -->
    <div v-if="activeTab === 'market'" class="flex items-center gap-1.5 px-8 py-3 border-b border-white/5 bg-white/[0.01] overflow-x-auto hide-scrollbar">
      <button
        @click="handleSourceSelect('')"
        :class="[
          'shrink-0 px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-200',
          selectedSource === ''
            ? 'bg-purple-500/15 border-purple-400/30 text-purple-400'
            : 'bg-white/[0.02] border-white/5 text-gray-500 hover:text-gray-300 hover:border-white/10'
        ]"
      >全部</button>
      <button
        v-for="src in sources"
        :key="src.id"
        @click="handleSourceSelect(src.id)"
        :class="[
          'shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all duration-200 group',
          selectedSource === src.id
            ? 'bg-purple-500/15 border-purple-400/30 text-purple-400'
            : src.enabled
              ? 'bg-white/[0.02] border-white/5 text-gray-500 hover:text-gray-300 hover:border-white/10'
              : 'bg-white/[0.01] border-white/[0.03] text-gray-700 opacity-60'
        ]">
        <div :class="['w-1.5 h-1.5 rounded-full', src.enabled ? 'bg-green-400' : 'bg-gray-600']" />
        {{ src.name }}
        <span class="text-[10px] opacity-60">{{ src.plugin_count }}</span>
        <!-- 源操作菜单 -->
        <div class="relative" @click.stop>
          <button
            class="ml-0.5 p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-white/10 transition-all"
            :title="src.enabled ? '禁用' : '启用'"
            @click="handleToggleSource(src)"
          >
            <EyeOff v-if="src.enabled" class="w-3 h-3" />
            <Eye v-else class="w-3 h-3" />
          </button>
        </div>
        <button
          v-if="src.type !== 'builtin'"
          @click.stop="handleRemoveSource(src)"
          class="ml-0.5 p-0.5 rounded opacity-0 group-hover:opacity-100 hover:bg-red-500/20 text-gray-500 hover:text-red-400 transition-all"
          title="删除"
        >
          <X class="w-3 h-3" />
        </button>
      </button>
      <!-- Add source button -->
      <button
        @click="showAddSource = true"
        class="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs font-medium bg-white/[0.02] border border-dashed border-white/10 text-gray-500 hover:text-purple-400 hover:border-purple-400/30 transition-all"
      >
        <Plus class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- Body -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Left sidebar -->
      <div v-if="activeTab === 'market'" class="w-52 shrink-0 border-r border-white/5 p-4 space-y-1 overflow-y-auto">
        <!-- Categories -->
        <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-3">分类</p>
        <button @click="selectedCategory = ''; page = 1; fetchData()" :class="['w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 text-left', selectedCategory === '' ? 'bg-brand-500/10 text-brand-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]']">
          <Tag class="w-4 h-4 shrink-0" /> 全部 <span class="ml-auto text-xs text-gray-600">{{ total }}</span>
        </button>
        <button
          v-for="cat in categories"
          :key="cat"
          @click="selectedCategory = cat; page = 1; fetchData()"
          :class="['w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 text-left', selectedCategory === cat ? 'bg-brand-500/10 text-brand-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]']"
        >
          <component :is="categoryMeta[cat]?.icon || Package" class="w-4 h-4 shrink-0" />
          {{ categoryMeta[cat]?.label || cat }}
        </button>

        <!-- Type filter -->
        <div class="mt-6 pt-4 border-t border-white/5">
          <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-3">类型</p>
          <button
            v-for="opt in typeFilterOptions"
            :key="opt.value"
            @click="selectedType = opt.value; page = 1; fetchData()"
            :class="['w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 text-left', selectedType === opt.value ? 'bg-brand-500/10 text-brand-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]']"
          >
            <component :is="opt.icon" class="w-4 h-4 shrink-0" /> {{ opt.label }}
          </button>
        </div>

        <!-- Stats -->
        <div v-if="stats" class="mt-6 pt-4 border-t border-white/5">
          <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-3">统计</p>
          <div class="space-y-2">
            <div class="flex items-center justify-between px-3 py-1.5">
              <span class="text-xs text-gray-500">总插件</span>
              <span class="text-xs text-gray-300 font-medium">{{ stats.total_plugins }}</span>
            </div>
            <div class="flex items-center justify-between px-3 py-1.5">
              <span class="text-xs text-gray-500">已安装</span>
              <span class="text-xs text-green-400 font-medium">{{ stats.total_installed }}</span>
            </div>
            <div class="flex items-center justify-between px-3 py-1.5">
              <span class="text-xs text-gray-500">市场源</span>
              <span class="text-xs text-gray-300 font-medium">{{ stats.enabled_sources_count }}/{{ stats.sources_count }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Main content -->
      <div class="flex-1 overflow-y-auto p-6">
        <!-- Search -->
        <div v-if="activeTab === 'market'" class="relative max-w-lg mb-6">
          <Search class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
          <input
            v-model="search"
            type="text"
            placeholder="搜索插件名称、描述、标签..."
            class="w-full bg-white/[0.03] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-400/40 focus:bg-white/[0.05] transition-all"
            @keydown="onSearchKeydown"
          />
        </div>

        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center py-24">
          <Loader2 class="w-8 h-8 animate-spin text-purple-400" />
        </div>

        <!-- Market empty -->
        <div v-else-if="activeTab === 'market' && plugins.length === 0" class="flex flex-col items-center justify-center py-24 text-gray-600">
          <Store class="w-12 h-12 mb-4 opacity-30" />
          <p class="text-sm">未找到匹配的插件</p>
          <p class="text-xs mt-1 opacity-70">尝试切换市场源或清除筛选条件</p>
        </div>

        <!-- Installed empty -->
        <div v-else-if="activeTab === 'installed' && installedPlugins.length === 0" class="flex flex-col items-center justify-center py-24 text-gray-600">
          <Package class="w-12 h-12 mb-4 opacity-30" />
          <p class="text-sm">还没有安装任何插件</p>
          <p class="text-xs mt-1 opacity-70 mb-4">去市场发现和安装插件</p>
          <button @click="activeTab = 'market'" class="flex items-center gap-2 px-4 py-2 rounded-xl bg-purple-500/15 text-purple-400 hover:bg-purple-500/25 text-sm transition-colors"><Store class="w-4 h-4" /> 浏览市场</button>
        </div>

        <!-- Market Grid -->
        <div v-else-if="activeTab === 'market'" class="plugin-grid">
          <article
            v-for="plugin in plugins"
            :key="plugin.name"
            class="plugin-card group rounded-2xl border border-white/8 bg-white/[0.02] hover:border-purple-400/20 hover:bg-white/[0.04] hover:shadow-lg hover:shadow-purple-500/5 transition-all duration-200 flex flex-col cursor-pointer"
            @click="showPluginDetail = plugin"
          >
            <!-- Header: name + type badge — 固定高度 -->
            <div class="flex items-start justify-between gap-3 plugin-card__header">
              <div class="min-w-0 flex-1">
                <h3 class="text-sm font-semibold text-white truncate group-hover:text-purple-300 transition-colors leading-tight">{{ plugin.display_name }}</h3>
                <p class="text-[10px] text-gray-600 mt-1 leading-none">
                  <span class="text-gray-500">{{ plugin.author }}</span>
                  <span v-if="plugin.source_id" class="ml-2 text-gray-700">{{ plugin.source_id }}</span>
                </p>
              </div>
              <span
                :class="[
                  'shrink-0 text-[10px] px-2 py-0.5 rounded-full font-medium border leading-none self-start',
                  typeMeta[plugin.type]?.cls || 'bg-gray-500/10 text-gray-400 border-gray-500/20'
                ]"
              >{{ typeMeta[plugin.type]?.label || plugin.type?.toUpperCase?.() || '插件' }}</span>
            </div>

            <!-- Description — 固定2行高度 -->
            <p class="text-xs text-gray-500 plugin-card__desc line-clamp-2 leading-relaxed">{{ plugin.desc }}</p>

            <!-- Tags — 最小高度容器 -->
            <div class="flex flex-wrap gap-1 plugin-card__tags">
              <span
                v-for="tag in (plugin.tags || []).slice(0, 4)"
                :key="tag"
                :class="[
                  'text-[10px] px-1.5 py-0.5 rounded-full border leading-none',
                  tag === 'skills' || tag === 'skill' ? 'bg-emerald-500/5 border-emerald-500/15 text-emerald-400/80' :
                  tag === 'mcp' ? 'bg-blue-500/5 border-blue-500/15 text-blue-400/80' :
                  tag === 'commands' || tag === 'command' ? 'bg-amber-500/5 border-amber-500/15 text-amber-400/80' :
                  tag === 'hooks' || tag === 'hook' ? 'bg-rose-500/5 border-rose-500/15 text-rose-400/80' :
                  'bg-white/[0.03] border-white/5 text-gray-500'
                ]"
              >{{ tag }}</span>
              <span v-if="(plugin.tags || []).length > 4" class="text-[10px] text-gray-600 leading-none self-center">+{{ plugin.tags.length - 4 }}</span>
            </div>

            <!-- Rating/stats — 固定高度 -->
            <div class="flex items-center gap-3 plugin-card__stats text-[10px] text-gray-600">
              <span class="text-yellow-500/80 whitespace-nowrap">{{ ratingStars(plugin.rating) }}</span>
              <span class="tabular-nums whitespace-nowrap">{{ (plugin.rating || 0).toFixed(1) }}</span>
              <span class="tabular-nums whitespace-nowrap">{{ formatCount(plugin.installs || 0) }} 安装</span>
              <span class="tabular-nums whitespace-nowrap">v{{ plugin.version }}</span>
            </div>

            <!-- Actions — 始终推底 -->
            <div class="flex items-center gap-2 pt-3 border-t border-white/5 mt-auto plugin-card__actions">
              <a v-if="plugin.repo" :href="plugin.repo" target="_blank" class="text-[10px] text-gray-600 hover:text-gray-400 flex items-center gap-1 transition-colors shrink-0" @click.stop><ExternalLink class="w-3 h-3" /> 源码</a>
              <button
                v-if="plugin.installed"
                disabled
                class="ml-auto px-3 py-1.5 rounded-lg bg-green-500/10 text-green-400 text-[11px] font-medium flex items-center gap-1.5 border border-green-500/20 shrink-0"
              ><CheckCircle class="w-3.5 h-3.5" /> 已安装</button>
              <button
                v-else
                @click.stop="handleInstall(plugin)"
                :disabled="installing === plugin.name"
                class="ml-auto px-3 py-1.5 rounded-lg bg-gradient-to-r from-purple-500/15 to-brand-500/10 text-purple-400 hover:from-purple-500/25 hover:to-brand-500/20 text-[11px] font-medium flex items-center gap-1.5 border border-purple-500/15 hover:border-purple-500/30 transition-all duration-200 shrink-0"
              >
                <Loader2 v-if="installing === plugin.name" class="w-3.5 h-3.5 animate-spin" />
                <Download v-else class="w-3.5 h-3.5" />
                {{ installing === plugin.name ? '安装中' : '安装' }}
              </button>
            </div>
          </article>
        </div>

        <!-- Installed List -->
        <div v-else-if="activeTab === 'installed'" class="space-y-3">
          <div
            v-for="plugin in installedPlugins"
            :key="plugin.name"
            class="rounded-2xl border border-white/8 bg-white/[0.02] p-5 hover:border-white/15 transition-all duration-200 group"
          >
            <div class="flex items-start justify-between">
              <div class="flex items-start gap-4 flex-1 min-w-0">
                <div class="relative mt-1">
                  <div :class="['w-2.5 h-2.5 rounded-full', plugin.installed_enabled !== false ? 'bg-green-400' : 'bg-gray-600']" />
                  <div v-if="plugin.installed_enabled !== false" class="absolute inset-0 w-2.5 h-2.5 rounded-full bg-green-400 animate-ping opacity-30" />
                </div>
                <div>
                  <div class="flex items-center gap-2 mb-1">
                    <h3 class="text-sm font-semibold text-white">{{ plugin.display_name }}</h3>
                    <span
                      :class="[
                        'text-[10px] px-1.5 py-0.5 rounded-full font-medium border',
                        typeMeta[plugin.type]?.cls || 'bg-gray-500/10 text-gray-400 border-gray-500/20'
                      ]"
                    >{{ typeMeta[plugin.type]?.label || plugin.type?.toUpperCase?.() || '插件' }}</span>
                  </div>
                  <p class="text-xs text-gray-500 mb-2">{{ plugin.desc }}</p>
                  <div class="flex items-center gap-2 text-[10px] text-gray-600">
                    <span :class="['px-1.5 py-0.5 rounded-full font-medium', plugin.installed_enabled !== false ? 'bg-green-500/10 text-green-400' : 'bg-gray-500/10 text-gray-500']">{{ plugin.installed_enabled !== false ? '已启用' : '已禁用' }}</span>
                    <span>v{{ plugin.installed_version || plugin.version }}</span>
                    <span>{{ plugin.author }}</span>
                  </div>
                </div>
              </div>
              <div class="flex items-center gap-1.5 shrink-0">
                <button
                  @click="handleToggle(plugin)"
                  :class="['px-2.5 py-1 rounded-lg text-[11px] font-medium transition-colors', plugin.installed_enabled !== false ? 'bg-amber-500/10 text-amber-400 hover:bg-amber-500/20' : 'bg-green-500/10 text-green-400 hover:bg-green-500/20']"
                >{{ plugin.installed_enabled !== false ? '禁用' : '启用' }}</button>
                <button
                  @click="handleUninstall(plugin)"
                  :disabled="installing === plugin.name"
                  class="px-2.5 py-1 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 text-[11px] font-medium transition-colors disabled:opacity-50"
                ><Unlink2 class="w-3 h-3 inline" /> 卸载</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="activeTab === 'market' && total > size" class="flex items-center justify-center gap-3 pt-6 mt-6 border-t border-white/5">
          <button :disabled="page <= 1" @click="page--; fetchData()" class="px-4 py-2 text-xs rounded-xl bg-white/[0.03] border border-white/10 text-gray-400 hover:bg-white/[0.06] disabled:opacity-30 transition-colors">上一页</button>
          <span class="text-xs text-gray-600 px-3">{{ page }} / {{ totalPages }}</span>
          <button :disabled="page >= totalPages" @click="page++; fetchData()" class="px-4 py-2 text-xs rounded-xl bg-white/[0.03] border border-white/10 text-gray-400 hover:bg-white/[0.06] disabled:opacity-30 transition-colors">下一页</button>
        </div>
      </div>
    </div>

    <!-- Plugin Detail Modal -->
    <Teleport to="body">
      <div v-if="showPluginDetail" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showPluginDetail = null">
        <div class="bg-surface-900 rounded-2xl border border-white/10 w-[560px] max-h-[80vh] flex flex-col shadow-2xl">
          <div class="flex items-center justify-between p-5 border-b border-white/8">
            <h3 class="font-semibold text-white flex items-center gap-2">
              <component :is="typeMeta[showPluginDetail.type]?.icon || Package" class="w-4 h-4 text-purple-400" />
              {{ showPluginDetail.display_name }}
            </h3>
            <button @click="showPluginDetail = null" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors"><X class="w-4 h-4" /></button>
          </div>
          <div class="flex-1 overflow-y-auto p-5 space-y-4">
            <div class="flex items-center gap-3 flex-wrap">
              <span
                :class="[
                  'text-[10px] px-2 py-0.5 rounded-full font-medium border',
                  typeMeta[showPluginDetail.type]?.cls || 'bg-gray-500/10 text-gray-400'
                ]"
              >{{ typeMeta[showPluginDetail.type]?.label || showPluginDetail.type?.toUpperCase() }}</span>
              <span class="text-xs text-gray-600">{{ showPluginDetail.author }} · v{{ showPluginDetail.version }}</span>
              <span class="text-xs text-yellow-500/80">{{ ratingStars(showPluginDetail.rating) }} {{ showPluginDetail.rating?.toFixed(1) }}</span>
              <span v-if="showPluginDetail.source_id" class="text-[10px] text-gray-700">来源: {{ showPluginDetail.source_id }}</span>
            </div>
            <p class="text-sm text-gray-400 leading-relaxed">{{ showPluginDetail.desc }}</p>
            <!-- Tags -->
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="tag in (showPluginDetail.tags || [])"
                :key="tag"
                :class="[
                  'text-[10px] px-2 py-0.5 rounded-full border',
                  tag === 'skills' || tag === 'skill' ? 'bg-emerald-500/5 border-emerald-500/15 text-emerald-400/80' :
                  tag === 'mcp' ? 'bg-blue-500/5 border-blue-500/15 text-blue-400/80' :
                  tag === 'commands' || tag === 'command' ? 'bg-amber-500/5 border-amber-500/15 text-amber-400/80' :
                  tag === 'hooks' || tag === 'hook' ? 'bg-rose-500/5 border-rose-500/15 text-rose-400/80' :
                  'bg-white/[0.03] border-white/5 text-gray-500'
                ]"
              >{{ tag }}</span>
            </div>
            <!-- Stats grid -->
            <div class="grid grid-cols-3 gap-3 text-center">
              <div class="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                <p class="text-lg font-semibold text-white">{{ formatCount(showPluginDetail.installs || 0) }}</p>
                <p class="text-[10px] text-gray-600 mt-0.5">安装量</p>
              </div>
              <div class="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                <p class="text-lg font-semibold text-white">{{ showPluginDetail.rating?.toFixed(1) || '-' }}</p>
                <p class="text-[10px] text-gray-600 mt-0.5">评分</p>
              </div>
              <div class="p-3 rounded-xl bg-white/[0.02] border border-white/5">
                <p class="text-lg font-semibold text-white">{{ showPluginDetail.category || '-' }}</p>
                <p class="text-[10px] text-gray-600 mt-0.5">分类</p>
              </div>
            </div>
            <div v-if="showPluginDetail.repo" class="pt-2">
              <a :href="showPluginDetail.repo" target="_blank" class="flex items-center gap-1.5 text-xs text-brand-400 hover:text-brand-300 transition-colors"><ExternalLink class="w-3.5 h-3.5" /> 查看源代码</a>
            </div>
          </div>
          <div class="flex gap-3 justify-end p-5 border-t border-white/8">
            <button @click="showPluginDetail = null" class="px-4 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">关闭</button>
            <button v-if="showPluginDetail.installed" disabled class="px-4 py-2.5 rounded-xl bg-green-500/10 text-green-400 text-sm font-medium flex items-center gap-1.5"><CheckCircle class="w-4 h-4" /> 已安装</button>
            <button v-else @click="handleInstall(showPluginDetail); showPluginDetail = null" class="px-4 py-2.5 rounded-xl bg-purple-500 hover:bg-purple-600 text-white text-sm font-medium transition-colors"><Download class="w-4 h-4 inline mr-1.5" />安装</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Add Source Modal -->
    <Teleport to="body">
      <div v-if="showAddSource" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" @click.self="showAddSource = false">
        <div class="bg-surface-900 rounded-2xl border border-white/10 w-full max-w-[520px] shadow-2xl flex flex-col max-h-[90vh]">
          <div class="flex items-center justify-between p-5 border-b border-white/8 shrink-0">
            <h3 class="font-semibold text-white flex items-center gap-2"><Plus class="w-4 h-4 text-purple-400" />添加市场</h3>
            <button @click="showAddSource = false" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors shrink-0"><X class="w-4 h-4" /></button>
          </div>
          <div class="p-5 space-y-4 overflow-y-auto">
            <!-- Source type tabs -->
            <div>
              <label class="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-2 block">来源类型 *</label>
              <div class="flex gap-2">
                <button
                  v-for="t in ([
                    { v: 'github', icon: Github, label: 'GitHub' },
                    { v: 'zip', icon: Archive, label: 'ZIP' },
                    { v: 'local', icon: FolderGit2, label: '本地' },
                  ] as const)"
                  :key="t.v"
                  @click="sourceType = t.v"
                  :class="[
                    'flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 rounded-xl text-xs font-medium border transition-all',
                    sourceType === t.v
                      ? 'bg-purple-500/10 border-purple-400/30 text-purple-400'
                      : 'bg-white/[0.02] border-white/8 text-gray-500 hover:text-gray-300'
                  ]"
                >
                  <component :is="t.icon" class="w-3.5 h-3.5 shrink-0" />
                  {{ t.label }}
                </button>
              </div>
            </div>
            <!-- Source name -->
            <div>
              <label class="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-2 block">名称 *</label>
              <input
                v-model="sourceName"
                type="text"
                placeholder="例如: cb_teams_marketplace"
                class="w-full bg-white/[0.03] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-400/40 focus:ring-1 focus:ring-purple-400/20 transition-all"
              />
            </div>
            <!-- Source URL / Path -->
            <div>
              <label class="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-2 block">
                {{ sourceType === 'github' ? '地址 *' : sourceType === 'zip' ? '地址 *' : '路径' }}
              </label>
              <input
                v-model="sourceUrl"
                type="text"
                :placeholder="sourceType === 'github' ? 'owner/repo, git@..., https://.../*.zip, or /path' : sourceType === 'zip' ? 'https://example.com/marketplace.zip (ZIP)' : '/path/to/marketplace (本地)'"
                class="w-full bg-white/[0.03] border border-white/10 rounded-xl px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-400/40 focus:ring-1 focus:ring-purple-400/20 transition-all"
              />
              <p class="text-[11px] text-gray-600 mt-1.5 leading-relaxed">
                示例：owner/repo（GitHub）、git@github.com:owner/repo.git（SSH）、https://example.com/marketplace.zip（ZIP）、/path/to/marketplace（本地）
              </p>
            </div>

            <!-- Preset quick-add -->
            <div>
              <label class="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-2 block">快速添加</label>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="preset in [
                    { n: 'CodeBuddy 社区', u: 'https://github.com/codebuddy-community/plugins', t: 'github' as const },
                    { n: 'MCP 官方', u: 'https://github.com/modelcontextprotocol/servers', t: 'github' as const },
                    { n: 'AI Studio 插件', u: 'https://plugins.ai-fullstack.dev/registry.json', t: 'zip' as const },
                  ]"
                  :key="preset.n"
                  @click="sourceName = preset.n; sourceUrl = preset.u; sourceType = preset.t"
                  class="px-2.5 py-1.5 rounded-lg bg-white/[0.02] border border-white/8 text-xs text-gray-500 hover:text-gray-300 hover:border-white/15 transition-all"
                >{{ preset.n }}</button>
              </div>
            </div>
          </div>
          <div class="flex gap-3 justify-end p-5 border-t border-white/8 shrink-0">
            <button @click="showAddSource = false" class="px-4 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">取消</button>
            <button @click="handleAddSource" class="px-4 py-2.5 rounded-xl bg-emerald-500/80 hover:bg-emerald-500 text-white text-sm font-medium transition-colors flex items-center gap-1.5 shrink-0"><Plus class="w-4 h-4" />提交</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.slide-down-enter-active, .slide-down-leave-active { transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1); }
.slide-down-enter-from, .slide-down-leave-to { opacity: 0; transform: translateY(-16px) translateX(-50%); }

.hide-scrollbar::-webkit-scrollbar { height: 0; }
.hide-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }

/* ── 插件网格：等高行 + 严格对齐 ── */
.plugin-grid {
  display: grid;
  grid-template-columns: repeat(1, minmax(0, 1fr));
  gap: 1rem;
  align-items: stretch;
}

@media (min-width: 768px) {
  .plugin-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (min-width: 1280px) {
  .plugin-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

/* ── 卡片内部：各区域固定/最小高度确保跨卡片对齐 ── */
.plugin-card {
  padding: 1.25rem;
}

/* Header 区域 — 固定最小高度，防止名称换行导致高度差异 */
.plugin-card__header {
  min-height: 2.75rem;
  margin-bottom: 0.75rem;
}

/* 描述区 — 恰好2行的高度 (line-height 1.625 * font-size 0.75rem * 2 ≈ 2.4375rem) */
.plugin-card__desc {
  min-height: 2.4375rem;
  margin-bottom: 0.75rem;
}

/* 标签区 — 最小高度容纳一行标签 */
.plugin-card__tags {
  min-height: 1.625rem;
  margin-bottom: 0.75rem;
}

/* 统计行 — 单行固定 */
.plugin-card__stats {
  min-height: 1rem;
  margin-bottom: 0.5rem;
}

/* 操作栏 — 始终在底部（mt-auto 已在 class 中）*/
.plugin-card__actions {
  /* border-t already applied */
}
</style>
