<script setup lang="ts">
/**
 * 扩展管理页面 — 对标 VSCode 扩展管理
 * 支持: 已安装列表 / 市场搜索 / 安装卸载 / 启禁用
 */
import { ref, computed, onMounted, watch } from 'vue'
import {
  Search, Download, Trash2, ToggleLeft, ToggleRight, Package,
  Star, Shield, ExternalLink, RefreshCw, Filter, Layers, Puzzle,
  Sparkles, Loader2, AlertCircle, CheckCircle2, ChevronDown,
} from 'lucide-vue-next'
import { extensionsApi, type ExtensionInfo } from '@/api/extensions'

/* ── 状态 ── */
const activeTab = ref<'installed' | 'market'>('installed')
const searchQuery = ref('')
const selectedCategory = ref('')
const sortBy = ref('popular')
const page = ref(1)
const pageSize = 20
const loading = ref(false)
const error = ref('')
const actionLoading = ref<Record<string, boolean>>({})
const installedExtensions = ref<ExtensionInfo[]>([])
const marketExtensions = ref<ExtensionInfo[]>([])
const searchTotal = ref(0)
const detailExt = ref<ExtensionInfo | null>(null)

/* ── 类别列表 ── */
const categories = [
  'Programming Languages', 'Themes', 'Formatters', 'Linters',
  'Debuggers', 'SCM Providers', 'Other',
]

/* ── 计算属性 ── */
const displayExtensions = computed(() => {
  if (activeTab.value === 'installed') return installedExtensions.value
  return marketExtensions.value
})

const totalPages = computed(() => Math.max(1, Math.ceil(searchTotal.value / pageSize)))

const installedCount = computed(() => installedExtensions.value.length)

/* ── 数据加载 ── */
async function loadInstalled() {
  loading.value = true
  error.value = ''
  try {
    installedExtensions.value = await extensionsApi.listInstalled()
  } catch (e: any) {
    error.value = e?.message || '加载已安装扩展失败'
  } finally {
    loading.value = false
  }
}

async function loadMarket() {
  loading.value = true
  error.value = ''
  try {
    if (searchQuery.value) {
      const result = await extensionsApi.search(searchQuery.value, selectedCategory.value || undefined, page.value, pageSize)
      marketExtensions.value = result.items
      searchTotal.value = result.total
    } else {
      const items = await extensionsApi.galleryList(selectedCategory.value || undefined, sortBy.value, page.value, pageSize)
      marketExtensions.value = items
      searchTotal.value = items.length
    }
  } catch (e: any) {
    error.value = e?.message || '加载市场失败'
  } finally {
    loading.value = false
  }
}

async function loadData() {
  if (activeTab.value === 'installed') {
    await loadInstalled()
  } else {
    await loadMarket()
  }
}

/* ── 操作 ── */
async function doInstall(ext: ExtensionInfo) {
  actionLoading.value[ext.id] = true
  try {
    await extensionsApi.install(ext.id)
    await loadInstalled()
    await loadMarket()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '安装失败'
  } finally {
    actionLoading.value[ext.id] = false
  }
}

async function doUninstall(ext: ExtensionInfo) {
  if (!confirm(`确认卸载 "${ext.display_name}"？`)) return
  actionLoading.value[ext.id] = true
  try {
    await extensionsApi.uninstall(ext.id)
    await loadInstalled()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '卸载失败'
  } finally {
    actionLoading.value[ext.id] = false
  }
}

async function doToggle(ext: ExtensionInfo) {
  actionLoading.value[ext.id] = true
  try {
    if (ext.is_active) {
      await extensionsApi.disable(ext.id)
    } else {
      await extensionsApi.enable(ext.id)
    }
    await loadInstalled()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || '操作失败'
  } finally {
    actionLoading.value[ext.id] = false
  }
}

function showDetail(ext: ExtensionInfo) {
  detailExt.value = ext
}

function closeDetail() {
  detailExt.value = null
}

function formatCount(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

function formatDate(ts: number): string {
  if (!ts) return '-'
  return new Date(ts * 1000).toLocaleDateString('zh-CN')
}

function categoryBadgeClass(cat: string): string {
  const map: Record<string, string> = {
    'Programming Languages': 'lang',
    'Themes': 'theme',
    'Formatters': 'fmt',
    'Linters': 'lint',
    'Debuggers': 'debug',
    'SCM Providers': 'scm',
    'Other': 'other',
  }
  return map[cat] || 'other'
}

function isInstalled(id: string): boolean {
  return installedExtensions.value.some(e => e.id === id)
}

/* ── 切换 Tab / 搜索 ── */
watch(activeTab, () => {
  page.value = 1
  searchQuery.value = ''
  selectedCategory.value = ''
  loadData()
})

watch([searchQuery, selectedCategory, sortBy, page], () => {
  if (activeTab.value === 'market') loadMarket()
})

onMounted(() => {
  loadInstalled()
})
</script>

<template>
  <div class="extensions-page">
    <!-- 头部 -->
    <div class="page-header">
      <div class="header-left">
        <Puzzle class="header-icon" :size="24" />
        <div>
          <h1 class="page-title">扩展管理</h1>
          <p class="page-subtitle">管理平台扩展，发现和安装新功能</p>
        </div>
      </div>
      <button class="btn-refresh" @click="loadData" :disabled="loading">
        <RefreshCw :size="16" :class="{ spinning: loading }" />
        <span>刷新</span>
      </button>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="error-banner">
      <AlertCircle :size="16" />
      <span>{{ error }}</span>
      <button @click="error = ''">&times;</button>
    </div>

    <!-- Tab + 搜索工具栏 -->
    <div class="toolbar">
      <div class="tab-bar">
        <button
          :class="['tab-btn', { active: activeTab === 'installed' }]"
          @click="activeTab = 'installed'"
        >
          <Package :size="16" />
          <span>已安装</span>
          <span class="tab-badge">{{ installedCount }}</span>
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'market' }]"
          @click="activeTab = 'market'"
        >
          <Sparkles :size="16" />
          <span>扩展市场</span>
        </button>
      </div>

      <div v-if="activeTab === 'market'" class="toolbar-actions">
        <div class="search-box">
          <Search :size="14" class="search-icon" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="搜索扩展..."
            class="search-input"
          />
        </div>
        <select v-model="selectedCategory" class="filter-select">
          <option value="">所有类别</option>
          <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
        </select>
        <select v-model="sortBy" class="filter-select">
          <option value="popular">最热门</option>
          <option value="rating">最高评分</option>
          <option value="name">名称排序</option>
          <option value="recent">最近更新</option>
        </select>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="content-area">
      <!-- 加载中 -->
      <div v-if="loading" class="loading-state">
        <Loader2 :size="32" class="spinning" />
        <span>加载中...</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!loading && displayExtensions.length === 0" class="empty-state">
        <Layers :size="48" class="empty-icon" />
        <p v-if="activeTab === 'installed'">暂无已安装的扩展</p>
        <p v-else>未找到匹配的扩展</p>
      </div>

      <!-- 扩展列表 -->
      <div v-else class="extension-grid">
        <div
          v-for="ext in displayExtensions"
          :key="ext.id"
          :class="['extension-card', { inactive: !ext.is_active }]"
          @click="showDetail(ext)"
        >
          <div class="card-header">
            <div class="ext-icon" :class="categoryBadgeClass(ext.categories?.[0] || 'Other')">
              <component
                :is="ext.is_builtin ? Shield : Package"
                :size="20"
              />
            </div>
            <div class="ext-meta">
              <span class="ext-name">{{ ext.display_name }}</span>
              <span class="ext-publisher">{{ ext.publisher_display_name || ext.publisher }}</span>
            </div>
            <div class="ext-badges">
              <span v-if="ext.is_builtin" class="badge badge-builtin">内置</span>
              <span v-if="isInstalled(ext.id) && activeTab === 'market'" class="badge badge-installed">
                <CheckCircle2 :size="12" /> 已安装
              </span>
              <span v-if="!ext.is_active" class="badge badge-disabled">已禁用</span>
            </div>
          </div>

          <p class="ext-desc">{{ ext.description }}</p>

          <div class="card-footer">
            <div class="footer-left">
              <span v-if="ext.categories?.length" :class="['cat-tag', categoryBadgeClass(ext.categories[0])]">
                {{ ext.categories[0] }}
              </span>
              <span class="ext-version">v{{ ext.version }}</span>
            </div>
            <div class="footer-right">
              <span v-if="ext.rating" class="rating">
                <Star :size="12" class="star-icon" />
                {{ ext.rating.toFixed(1) }}
                <span class="rating-count">({{ formatCount(ext.rating_count) }})</span>
              </span>
              <span v-if="ext.install_count" class="installs">
                {{ formatCount(ext.install_count) }} 次安装
              </span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="card-actions" @click.stop>
            <template v-if="ext.is_builtin">
              <span class="builtin-hint">内置扩展</span>
            </template>
            <template v-else>
              <button
                v-if="isInstalled(ext.id)"
                class="action-btn toggle-btn"
                :title="ext.is_active ? '禁用' : '启用'"
                @click="doToggle(ext)"
                :disabled="actionLoading[ext.id]"
              >
                <Loader2 v-if="actionLoading[ext.id]" :size="14" class="spinning" />
                <component :is="ext.is_active ? ToggleRight : ToggleLeft" v-else :size="16" />
              </button>
              <button
                v-if="activeTab === 'market' && !isInstalled(ext.id)"
                class="action-btn install-btn"
                @click="doInstall(ext)"
                :disabled="actionLoading[ext.id]"
              >
                <Loader2 v-if="actionLoading[ext.id]" :size="14" class="spinning" />
                <Download v-else :size="14" />
                <span>安装</span>
              </button>
              <button
                v-if="activeTab === 'installed'"
                class="action-btn uninstall-btn"
                @click="doUninstall(ext)"
                :disabled="actionLoading[ext.id]"
              >
                <Loader2 v-if="actionLoading[ext.id]" :size="14" class="spinning" />
                <Trash2 v-else :size="14" />
                <span>卸载</span>
              </button>
            </template>
          </div>
        </div>
      </div>

      <!-- 分页 (仅市场) -->
      <div v-if="activeTab === 'market' && totalPages > 1" class="pagination">
        <button :disabled="page <= 1" @click="page--" class="page-btn">上一页</button>
        <span class="page-info">{{ page }} / {{ totalPages }}</span>
        <button :disabled="page >= totalPages" @click="page++" class="page-btn">下一页</button>
      </div>
    </div>

    <!-- 详情面板 -->
    <Teleport to="body">
      <div v-if="detailExt" class="detail-overlay" @click.self="closeDetail">
        <div class="detail-panel">
          <div class="detail-header">
            <div class="detail-icon" :class="categoryBadgeClass(detailExt.categories?.[0] || 'Other')">
              <component :is="detailExt.is_builtin ? Shield : Package" :size="28" />
            </div>
            <div>
              <h2 class="detail-name">{{ detailExt.display_name }}</h2>
              <p class="detail-id">{{ detailExt.id }}</p>
            </div>
            <button class="detail-close" @click="closeDetail">&times;</button>
          </div>

          <div class="detail-body">
            <p class="detail-desc">{{ detailExt.description }}</p>

            <div class="detail-grid">
              <div class="detail-item">
                <span class="detail-label">版本</span>
                <span class="detail-value">v{{ detailExt.version }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">发布者</span>
                <span class="detail-value">{{ detailExt.publisher_display_name || detailExt.publisher }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">类别</span>
                <span class="detail-value">{{ detailExt.categories?.join(', ') || '-' }}</span>
              </div>
              <div class="detail-item">
                <span class="detail-label">状态</span>
                <span class="detail-value">
                  <span v-if="detailExt.is_builtin" class="badge badge-builtin">内置</span>
                  <span v-else-if="detailExt.is_active" class="badge badge-active">已启用</span>
                  <span v-else class="badge badge-disabled">已禁用</span>
                </span>
              </div>
              <div v-if="detailExt.rating" class="detail-item">
                <span class="detail-label">评分</span>
                <span class="detail-value rating-value">
                  <Star :size="14" class="star-icon" />
                  {{ detailExt.rating.toFixed(1) }} ({{ formatCount(detailExt.rating_count) }})
                </span>
              </div>
              <div v-if="detailExt.install_count" class="detail-item">
                <span class="detail-label">安装量</span>
                <span class="detail-value">{{ formatCount(detailExt.install_count) }}</span>
              </div>
              <div v-if="detailExt.installed_at" class="detail-item">
                <span class="detail-label">安装时间</span>
                <span class="detail-value">{{ formatDate(detailExt.installed_at) }}</span>
              </div>
              <div v-if="detailExt.updated_at" class="detail-item">
                <span class="detail-label">更新时间</span>
                <span class="detail-value">{{ formatDate(detailExt.updated_at) }}</span>
              </div>
            </div>

            <div v-if="detailExt.tags?.length" class="detail-tags">
              <span class="detail-label">标签</span>
              <div class="tags-list">
                <span v-for="tag in detailExt.tags" :key="tag" class="tag-chip">{{ tag }}</span>
              </div>
            </div>
          </div>

          <div class="detail-actions">
            <template v-if="!detailExt.is_builtin">
              <button
                v-if="!isInstalled(detailExt.id)"
                class="action-btn install-btn primary"
                @click="doInstall(detailExt)"
                :disabled="actionLoading[detailExt.id]"
              >
                <Loader2 v-if="actionLoading[detailExt.id]" :size="14" class="spinning" />
                <Download v-else :size="14" />
                <span>安装</span>
              </button>
              <button
                v-else
                class="action-btn toggle-btn primary"
                @click="doToggle(detailExt)"
                :disabled="actionLoading[detailExt.id]"
              >
                <Loader2 v-if="actionLoading[detailExt.id]" :size="14" class="spinning" />
                <component :is="detailExt.is_active ? ToggleRight : ToggleLeft" v-else :size="16" />
                <span>{{ detailExt.is_active ? '禁用' : '启用' }}</span>
              </button>
              <button
                v-if="isInstalled(detailExt.id)"
                class="action-btn uninstall-btn danger"
                @click="doUninstall(detailExt)"
                :disabled="actionLoading[detailExt.id]"
              >
                <Loader2 v-if="actionLoading[detailExt.id]" :size="14" class="spinning" />
                <Trash2 v-else :size="14" />
                <span>卸载</span>
              </button>
            </template>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* ── 页面布局 ── */
.extensions-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 20px 24px;
  gap: 16px;
  overflow: hidden;
}

/* ── 头部 ── */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.header-icon {
  color: var(--color-ide-accent, #6c5ce7);
}
.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--color-ide-fg, #e0e0e0);
  margin: 0;
}
.page-subtitle {
  font-size: 13px;
  color: var(--color-ide-fg-dim, #888);
  margin: 2px 0 0 0;
}
.btn-refresh {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 6px;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  color: var(--color-ide-fg, #e0e0e0);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}
.btn-refresh:hover { border-color: var(--color-ide-accent, #6c5ce7); }

/* ── 错误提示 ── */
.error-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(255, 68, 68, .12);
  border: 1px solid rgba(255, 68, 68, .3);
  border-radius: 8px;
  color: #ff6b6b;
  font-size: 13px;
}
.error-banner button {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  font-size: 18px;
}

/* ── 工具栏 ── */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.tab-bar {
  display: flex;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  border-radius: 8px;
  padding: 3px;
}
.tab-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: none;
  background: transparent;
  color: var(--color-ide-fg-dim, #888);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all .2s;
}
.tab-btn.active {
  background: var(--color-ide-bg, #252525);
  color: var(--color-ide-fg, #e0e0e0);
}
.tab-badge {
  background: var(--color-ide-accent, #6c5ce7);
  color: #fff;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
}
.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.search-box {
  position: relative;
}
.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-ide-fg-dim, #888);
}
.search-input {
  width: 220px;
  padding: 6px 12px 6px 32px;
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 6px;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  color: var(--color-ide-fg, #e0e0e0);
  font-size: 13px;
  outline: none;
}
.search-input:focus { border-color: var(--color-ide-accent, #6c5ce7); }
.filter-select {
  padding: 6px 10px;
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 6px;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  color: var(--color-ide-fg, #e0e0e0);
  font-size: 13px;
  outline: none;
}

/* ── 内容区域 ── */
.content-area {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

/* ── 加载/空状态 ── */
.loading-state, .empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 0;
  color: var(--color-ide-fg-dim, #888);
}
.empty-icon { opacity: .3; }

/* ── 扩展网格 ── */
.extension-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}
.extension-card {
  background: var(--color-ide-bg-secondary, #1e1e1e);
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 10px;
  padding: 16px;
  cursor: pointer;
  transition: all .2s;
  display: flex;
  flex-direction: column;
  gap: 10px;
  position: relative;
}
.extension-card:hover {
  border-color: var(--color-ide-accent, #6c5ce7);
  transform: translateY(-1px);
}
.extension-card.inactive { opacity: .6; }

/* ── 卡片头部 ── */
.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ext-icon {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ext-icon.lang { background: rgba(52,152,219,.15); color: #3498db; }
.ext-icon.theme { background: rgba(155,89,182,.15); color: #9b59b6; }
.ext-icon.fmt { background: rgba(46,204,113,.15); color: #2ecc71; }
.ext-icon.lint { background: rgba(230,126,34,.15); color: #e67e22; }
.ext-icon.debug { background: rgba(231,76,60,.15); color: #e74c3c; }
.ext-icon.scm { background: rgba(241,196,15,.15); color: #f1c40f; }
.ext-icon.other { background: rgba(149,165,166,.15); color: #95a5a6; }
.ext-meta {
  flex: 1;
  min-width: 0;
}
.ext-name {
  display: block;
  font-weight: 600;
  font-size: 14px;
  color: var(--color-ide-fg, #e0e0e0);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ext-publisher {
  font-size: 12px;
  color: var(--color-ide-fg-dim, #888);
}
.ext-badges {
  display: flex;
  gap: 4px;
}

/* ── 描述 ── */
.ext-desc {
  font-size: 12.5px;
  color: var(--color-ide-fg-dim, #888);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin: 0;
}

/* ── 卡片底部 ── */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: var(--color-ide-fg-dim, #888);
}
.footer-left, .footer-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.cat-tag {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 500;
}
.cat-tag.lang { background: rgba(52,152,219,.15); color: #3498db; }
.cat-tag.theme { background: rgba(155,89,182,.15); color: #9b59b6; }
.cat-tag.fmt { background: rgba(46,204,113,.15); color: #2ecc71; }
.cat-tag.lint { background: rgba(230,126,34,.15); color: #e67e22; }
.cat-tag.debug { background: rgba(231,76,60,.15); color: #e74c3c; }
.cat-tag.scm { background: rgba(241,196,15,.15); color: #f1c40f; }
.cat-tag.other { background: rgba(149,165,166,.15); color: #95a5a6; }
.rating {
  display: flex;
  align-items: center;
  gap: 2px;
  color: #f1c40f;
}
.rating-count { color: var(--color-ide-fg-dim, #888); }

/* ── 卡片操作按钮 ── */
.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-ide-border, #333);
}
.builtin-hint {
  font-size: 11px;
  color: var(--color-ide-fg-dim, #888);
  font-style: italic;
}
.action-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 6px;
  background: transparent;
  color: var(--color-ide-fg, #e0e0e0);
  cursor: pointer;
  font-size: 12px;
  transition: all .2s;
}
.action-btn:disabled { opacity: .5; cursor: not-allowed; }
.install-btn:hover { border-color: #2ecc71; color: #2ecc71; }
.uninstall-btn:hover { border-color: #e74c3c; color: #e74c3c; }
.toggle-btn:hover { border-color: var(--color-ide-accent, #6c5ce7); }

/* ── 徽章 ── */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}
.badge-builtin { background: rgba(52,152,219,.15); color: #3498db; }
.badge-installed { background: rgba(46,204,113,.15); color: #2ecc71; }
.badge-disabled { background: rgba(149,165,166,.15); color: #95a5a6; }
.badge-active { background: rgba(46,204,113,.15); color: #2ecc71; }

/* ── 分页 ── */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 16px 0;
}
.page-btn {
  padding: 6px 16px;
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 6px;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  color: var(--color-ide-fg, #e0e0e0);
  cursor: pointer;
  font-size: 13px;
}
.page-btn:disabled { opacity: .4; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--color-ide-fg-dim, #888); }

/* ── 详情面板 ── */
.detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0,0,0,.5);
  display: flex;
  align-items: center;
  justify-content: center;
}
.detail-panel {
  width: 520px;
  max-height: 80vh;
  background: var(--color-ide-bg, #252525);
  border: 1px solid var(--color-ide-border, #333);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.detail-header {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  border-bottom: 1px solid var(--color-ide-border, #333);
}
.detail-icon {
  width: 52px;
  height: 52px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.detail-name { margin: 0; font-size: 18px; color: var(--color-ide-fg, #e0e0e0); }
.detail-id { margin: 2px 0 0; font-size: 12px; color: var(--color-ide-fg-dim, #888); font-family: monospace; }
.detail-close {
  margin-left: auto;
  background: none;
  border: none;
  color: var(--color-ide-fg-dim, #888);
  font-size: 24px;
  cursor: pointer;
  padding: 0 4px;
}
.detail-body {
  padding: 20px;
  overflow-y: auto;
  flex: 1;
}
.detail-desc {
  font-size: 13.5px;
  color: var(--color-ide-fg-dim, #aaa);
  line-height: 1.6;
  margin: 0 0 16px 0;
}
.detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.detail-item { display: flex; flex-direction: column; gap: 2px; }
.detail-label { font-size: 11px; color: var(--color-ide-fg-dim, #888); text-transform: uppercase; }
.detail-value { font-size: 13px; color: var(--color-ide-fg, #e0e0e0); }
.rating-value { display: flex; align-items: center; gap: 4px; color: #f1c40f; }
.detail-tags { margin-top: 14px; }
.tags-list { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.tag-chip {
  padding: 3px 8px;
  border-radius: 4px;
  background: var(--color-ide-bg-secondary, #1e1e1e);
  font-size: 11px;
  color: var(--color-ide-fg-dim, #888);
}
.detail-actions {
  display: flex;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid var(--color-ide-border, #333);
}
.action-btn.primary {
  flex: 1;
  justify-content: center;
  padding: 8px 16px;
  font-size: 13px;
}
.action-btn.danger { color: #e74c3c; border-color: rgba(231,76,60,.3); }
.action-btn.danger:hover { background: rgba(231,76,60,.1); }

/* ── 动画 ── */
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
