<template>
  <div class="p-6">
    <div class="max-w-6xl mx-auto">
      <header class="mb-8 text-center">
        <h1 class="text-3xl font-bold text-white">🏦 复合存储库</h1>
        <p class="text-[var(--color-ide-text-dim)] mt-2">BM25 检索 · 热缓存 · 嵌入缓存 · 上下文前缀</p>
      </header>

      <!-- 统计概览 -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <div class="p-4 rounded-xl bg-gray-900/50 border border-gray-800/50">
          <p class="text-xs text-[var(--color-ide-text-dim)] mb-1">BM25 文档数</p>
          <p class="text-2xl font-bold text-white">{{ statsData.bm25?.doc_count || '-' }}</p>
        </div>
        <div class="p-4 rounded-xl bg-gray-900/50 border border-gray-800/50">
          <p class="text-xs text-[var(--color-ide-text-dim)] mb-1">热缓存条目</p>
          <p class="text-2xl font-bold text-yellow-400">{{ statsData.hot_cache?.hot_count || '0' }}</p>
        </div>
        <div class="p-4 rounded-xl bg-gray-900/50 border border-gray-800/50">
          <p class="text-xs text-[var(--color-ide-text-dim)] mb-1">长期记忆</p>
          <p class="text-2xl font-bold text-purple-400">{{ statsData.hot_cache?.long_count || '0' }}</p>
        </div>
        <div class="p-4 rounded-xl bg-gray-900/50 border border-gray-800/50">
          <p class="text-xs text-[var(--color-ide-text-dim)] mb-1">嵌入缓存 (内存)</p>
          <p class="text-2xl font-bold text-brand-400">{{ embedMemUsage }}</p>
        </div>
      </div>

      <!-- 功能标签 -->
      <div class="flex gap-1 mb-6 bg-gray-900/50 rounded-xl p-1 border border-gray-800/50">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          @click="activeTab = tab.id"
          class="flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all"
          :class="activeTab === tab.id ? 'bg-brand-500/80 text-white shadow-lg' : 'text-[var(--color-ide-text-dim)] hover:text-white'"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- ======== 检索 ======== -->
      <div v-if="activeTab === 'search'">
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-6">
          <div class="flex flex-col sm:flex-row gap-3">
            <div class="flex-1 relative">
              <input
                v-model="searchQuery"
                @keyup.enter="doCompoundSearch"
                class="w-full px-4 py-2.5 pl-10 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-[var(--color-ide-text-dim)] outline-none focus:border-brand-500/50"
                placeholder="输入检索查询..."
              />
              <span class="absolute left-3 top-2.5 text-[var(--color-ide-text-dim)] text-sm">🔍</span>
            </div>
            <select
              v-model.number="searchTopK"
              class="px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none"
            >
              <option :value="3">Top 3</option>
              <option :value="5">Top 5</option>
              <option :value="10">Top 10</option>
              <option :value="20">Top 20</option>
            </select>
            <label class="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-xs text-white cursor-pointer">
              <input v-model="useBM25" type="checkbox" class="rounded accent-brand-500" />
              BM25
            </label>
            <label class="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-xs text-white cursor-pointer">
              <input v-model="useDense" type="checkbox" class="rounded accent-brand-500" />
              Dense
            </label>
            <button
              @click="doCompoundSearch"
              :disabled="searching || !searchQuery"
              class="px-6 py-2.5 rounded-xl bg-brand-500/80 text-white text-sm font-medium hover:bg-brand-500 disabled:opacity-50 transition-colors"
            >
              {{ searching ? '搜索中...' : '搜索' }}
            </button>
          </div>
        </div>

        <!-- 搜索结果 -->
        <div v-if="searchResults.length" class="space-y-3">
          <div
            v-for="(r, i) in searchResults"
            :key="r.chunk_id"
            class="p-4 rounded-xl bg-gray-900/50 border border-gray-800/50 hover:border-brand-500/20 transition-colors"
          >
            <div class="flex items-center gap-3 mb-2">
              <span class="w-6 h-6 rounded-md bg-brand-500/20 text-brand-400 text-xs flex items-center justify-center font-mono">{{ i + 1 }}</span>
              <code class="text-xs text-[var(--color-ide-text-dim)] font-mono">{{ r.chunk_id }}</code>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-medium" :class="r.source === 'bm25' ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'">{{ r.source.toUpperCase() }}</span>
              <span class="px-2 py-0.5 rounded-md bg-gray-800 text-xs text-[var(--color-ide-text-dim)] font-mono">{{ r.score.toFixed(4) }}</span>
            </div>
            <p class="text-xs text-[var(--color-ide-text-dim)] truncate font-mono">{{ r.path }}</p>
          </div>
        </div>
        <div v-else-if="searched && !searching" class="text-center py-12 text-[var(--color-ide-text-dim)]">
          <p class="text-4xl mb-3">🔎</p>
          <p class="text-sm">没有找到结果</p>
        </div>
      </div>

      <!-- ======== 摄入 ======== -->
      <div v-if="activeTab === 'ingest'">
        <!-- 单文档摄入 -->
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-6">
          <h2 class="text-lg font-bold text-white mb-4">📄 摄入单文档</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">文档路径</label>
              <input v-model="ingestForm.path" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50" placeholder="e.g. docs/my_file.md" />
            </div>
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">文档标题</label>
              <input v-model="ingestForm.title" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50" placeholder="文档标题" />
            </div>
          </div>
          <div class="mb-4">
            <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">文档内容</label>
            <textarea v-model="ingestForm.content" rows="6" class="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-[var(--color-ide-text-dim)] outline-none focus:border-brand-500/50 resize-none font-mono" placeholder="粘贴或输入文档内容..."></textarea>
          </div>
          <label class="flex items-center gap-2 mb-4 text-xs text-[var(--color-ide-text-dim)] cursor-pointer">
            <input v-model="ingestForm.generate_prefixes" type="checkbox" class="rounded accent-brand-500" />
            生成上下文前缀
          </label>
          <button @click="doIngest" :disabled="ingesting" class="w-full py-3 rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 text-white font-medium disabled:opacity-50 transition-all">
            {{ ingesting ? '⏳ 摄入中...' : '📥 摄入文档' }}
          </button>
          <!-- 摄入结果 -->
          <div v-if="ingestResult" class="mt-4 p-3 rounded-xl bg-green-500/10 border border-green-500/20 text-sm text-green-400">
            <p>✅ 成功摄入: <code class="text-white">{{ ingestResult.path }}</code></p>
            <p class="text-xs mt-1">分块: {{ ingestResult.chunk_count }} · 前缀等级: {{ ingestResult.prefix_tier }}</p>
          </div>
        </div>

        <!-- 批量摄入 -->
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50">
          <h2 class="text-lg font-bold text-white mb-4">📚 批量摄入 (JSON)</h2>
          <div class="mb-4">
            <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">批量文档 JSON 数组</label>
            <textarea v-model="batchJson" rows="10" class="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-[var(--color-ide-text-dim)] outline-none focus:border-brand-500/50 resize-none font-mono" :placeholder="batchJsonPlaceholder"></textarea>
          </div>
          <button @click="doBatchIngest" :disabled="batchIngesting" class="w-full py-3 rounded-xl bg-gradient-to-r from-brand-500 to-cyan-500 text-white font-medium disabled:opacity-50 transition-all">
            {{ batchIngesting ? '⏳ 批量摄入中...' : '📦 批量摄入' }}
          </button>
          <div v-if="batchResult" class="mt-4 p-3 rounded-xl bg-green-500/10 border border-green-500/20 text-sm text-green-400">
            <p>✅ 处理 {{ batchResult.documents }} 个文档 · 共 {{ batchResult.total_chunks }} 个分块</p>
          </div>
        </div>
      </div>

      <!-- ======== 热缓存 ======== -->
      <div v-if="activeTab === 'hotCache'">
        <!-- 添加入口 -->
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-6">
          <h2 class="text-lg font-bold text-white mb-4">🔥 添加热缓存</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">缓存键 (Key)</label>
              <input v-model="cacheForm.key" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50" placeholder="e.g. project-rules" />
            </div>
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">重要性 ({{ cacheForm.importance }})</label>
              <input v-model.number="cacheForm.importance" type="range" min="0" max="1" step="0.1" class="w-full accent-brand-500" />
            </div>
          </div>
          <div class="mb-4">
            <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">摘要内容</label>
            <textarea v-model="cacheForm.summary" rows="3" class="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-[var(--color-ide-text-dim)] outline-none focus:border-brand-500/50 resize-none" placeholder="1-2 句摘要描述..."></textarea>
          </div>
          <label class="flex items-center gap-2 mb-4 text-xs text-[var(--color-ide-text-dim)] cursor-pointer">
            <input v-model="cacheForm.promote_to_long" type="checkbox" class="rounded accent-brand-500" />
            同时写入长期记忆
          </label>
          <button @click="doAddHotCache" :disabled="addingCache" class="w-full py-3 rounded-xl bg-gradient-to-r from-yellow-500 to-orange-500 text-white font-medium disabled:opacity-50 transition-all">
            {{ addingCache ? '⏳ 添加中...' : '🔥 添加缓存' }}
          </button>
        </div>

        <!-- 热缓存上下文 -->
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-6">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-lg font-bold text-white">📋 热缓存上下文</h2>
            <div class="flex gap-2">
              <button @click="clearSessionCache" class="text-xs px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors">清除会话</button>
              <button @click="loadHotCacheContext" class="text-xs px-3 py-1.5 rounded-lg bg-gray-800 text-[var(--color-ide-text-dim)] hover:text-white transition-colors">刷新</button>
            </div>
          </div>
          <pre class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/30 text-xs text-[var(--color-ide-text-dim)] max-h-60 overflow-auto font-mono whitespace-pre-wrap">{{ hotCacheContext || '点击刷新加载...' }}</pre>
          <p v-if="hotCacheContextStats" class="text-xs text-[var(--color-ide-text-dim)] mt-2">
            会话缓存: {{ hotCacheContextStats.hot_count }} · 长期记忆: {{ hotCacheContextStats.long_count }} · 总访问: {{ hotCacheContextStats.total_accesses }}
          </p>
        </div>
      </div>

      <!-- ======== 管理 ======== -->
      <div v-if="activeTab === 'manage'">
        <!-- BM25 管理 -->
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-6">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-bold text-white">🔢 BM25 索引</h2>
            <button @click="doRebuildBM25" :disabled="rebuildingBM25" class="text-xs px-3 py-1.5 rounded-lg bg-yellow-500/20 text-yellow-400 hover:bg-yellow-500/30 disabled:opacity-50 transition-colors">
              {{ rebuildingBM25 ? '重建中...' : '重建索引' }}
            </button>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="p-3 rounded-lg bg-gray-800/50">
              <p class="text-xs text-[var(--color-ide-text-dim)]">文档数</p>
              <p class="text-lg font-bold text-white">{{ bm25StatsData.doc_count || '-' }}</p>
            </div>
            <div class="p-3 rounded-lg bg-gray-800/50">
              <p class="text-xs text-[var(--color-ide-text-dim)]">词汇量</p>
              <p class="text-lg font-bold text-white">{{ bm25StatsData.vocab_size || '-' }}</p>
            </div>
            <div class="p-3 rounded-lg bg-gray-800/50">
              <p class="text-xs text-[var(--color-ide-text-dim)]">平均长度</p>
              <p class="text-lg font-bold text-white">{{ bm25StatsData.avg_dl?.toFixed(1) || '-' }}</p>
            </div>
            <div class="p-3 rounded-lg bg-gray-800/50">
              <p class="text-xs text-[var(--color-ide-text-dim)]">版本</p>
              <p class="text-lg font-bold text-white">{{ bm25StatsData.schema_version || '-' }}</p>
            </div>
          </div>
        </div>

        <!-- 缓存管理 -->
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-6">
          <h2 class="text-lg font-bold text-white mb-4">🗑 缓存清理</h2>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <button @click="doClearPrefixes" class="w-full py-3 rounded-xl bg-gray-800 text-sm text-[var(--color-ide-text-dim)] hover:text-white border border-gray-700 transition-colors">
              清除所有前缀缓存
            </button>
            <button @click="doClearEmbedCache" class="w-full py-3 rounded-xl bg-gray-800 text-sm text-[var(--color-ide-text-dim)] hover:text-white border border-gray-700 transition-colors">
              清空嵌入缓存
            </button>
          </div>
          <div class="mt-4">
            <div class="flex gap-2">
              <input v-model="prefixPath" class="flex-1 px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-[var(--color-ide-text-dim)] outline-none" placeholder="按路径清除前缀缓存..." />
              <button @click="doClearPrefixes(prefixPath)" :disabled="!prefixPath" class="px-4 py-2.5 rounded-xl bg-gray-800 text-sm text-[var(--color-ide-text-dim)] hover:text-white border border-gray-700 disabled:opacity-50 transition-colors">清除</button>
            </div>
          </div>
        </div>

        <!-- 操作反馈 -->
        <div v-if="actionMessage" class="p-3 rounded-xl text-sm transition-colors" :class="actionError ? 'bg-red-500/10 border border-red-500/20 text-red-400' : 'bg-green-500/10 border border-green-500/20 text-green-400'">
          {{ actionMessage }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { compoundVaultApi, type IngestResult, type BatchIngestResult, type SearchResultItem, type BM25Stats, type HotCacheStats, type CompoundStats } from '@/api/compoundVault'

// ==================== 标签 ====================
const tabs = [
  { id: 'search', label: '🔍 混合检索' },
  { id: 'ingest', label: '📥 文档摄入' },
  { id: 'hotCache', label: '🔥 热缓存' },
  { id: 'manage', label: '⚙ 管理' },
]
const activeTab = ref<'search' | 'ingest' | 'hotCache' | 'manage'>('search')

// ==================== 检索 ====================
const searchQuery = ref('')
const searchTopK = ref(5)
const useBM25 = ref(true)
const useDense = ref(false)
const searchResults = ref<SearchResultItem[]>([])
const searching = ref(false)
const searched = ref(false)

// ==================== 摄入 ====================
const ingestForm = ref({ path: '', title: '', content: '', generate_prefixes: true })
const ingesting = ref(false)
const ingestResult = ref<IngestResult | null>(null)

const batchJson = ref('')
const batchJsonPlaceholder = `[
  {"path": "doc1.md", "content": "...", "title": "Doc 1"},
  {"path": "doc2.md", "content": "...", "title": "Doc 2"}
]`
const batchIngesting = ref(false)
const batchResult = ref<BatchIngestResult | null>(null)

// ==================== 热缓存 ====================
const cacheForm = ref({ key: '', summary: '', importance: 0.5, promote_to_long: false })
const addingCache = ref(false)
const hotCacheContext = ref('')
const hotCacheContextStats = ref<{ hot_count: number; long_count: number; total_accesses: number } | null>(null)

// ==================== 管理 ====================
const rebuildingBM25 = ref(false)
const bm25StatsData = ref<Partial<BM25Stats>>({})
const prefixPath = ref('')
const actionMessage = ref('')
const actionError = ref(false)

// ==================== 统计 ====================
const statsData = ref<Partial<CompoundStats>>({})
const embedMemUsage = computed(() => {
  const s = statsData.value.embed_cache
  if (!s?.mem_size && s?.mem_size !== 0) return '-'
  const max = s.mem_max || 1
  return `${s.mem_size}/${max}`
})

// ==================== 方法 ====================

// 检索
async function doCompoundSearch() {
  if (!searchQuery.value) return
  searching.value = true
  try {
    const res = await compoundVaultApi.search({
      query: searchQuery.value,
      top_k: searchTopK.value,
      use_bm25: useBM25.value,
      use_dense: useDense.value,
    })
    searchResults.value = res.data.results || []
    searched.value = true
  } catch (e) {
    console.error('search failed:', e)
  } finally {
    searching.value = false
  }
}

// 摄入
async function doIngest() {
  if (!ingestForm.value.content) return
  ingesting.value = true
  ingestResult.value = null
  try {
    const res = await compoundVaultApi.ingest({
      path: ingestForm.value.path || `docs/${Date.now()}.txt`,
      content: ingestForm.value.content,
      title: ingestForm.value.title,
      generate_prefixes: ingestForm.value.generate_prefixes,
    })
    ingestResult.value = res.data
    await loadStats()
  } catch (e) {
    console.error('ingest failed:', e)
  } finally {
    ingesting.value = false
  }
}

async function doBatchIngest() {
  if (!batchJson.value.trim()) return
  batchIngesting.value = true
  batchResult.value = null
  try {
    const docs = JSON.parse(batchJson.value)
    const res = await compoundVaultApi.ingestBatch({ documents: docs })
    batchResult.value = res.data
    await loadStats()
  } catch (e) {
    console.error('batch ingest failed:', e)
  } finally {
    batchIngesting.value = false
  }
}

// 热缓存
async function doAddHotCache() {
  if (!cacheForm.value.key || !cacheForm.value.summary) return
  addingCache.value = true
  try {
    await compoundVaultApi.addHotCache({
      key: cacheForm.value.key,
      summary: cacheForm.value.summary,
      importance: cacheForm.value.importance,
      promote_to_long: cacheForm.value.promote_to_long,
    })
    cacheForm.value = { key: '', summary: '', importance: 0.5, promote_to_long: false }
    await loadHotCacheContext()
  } catch (e) {
    console.error('add hot cache failed:', e)
  } finally {
    addingCache.value = false
  }
}

async function loadHotCacheContext() {
  try {
    const res = await compoundVaultApi.getHotCacheContext(2000)
    hotCacheContext.value = res.data.context || ''
    hotCacheContextStats.value = res.data.stats || null
  } catch (e) {
    console.error('load hot cache context failed:', e)
  }
}

async function clearSessionCache() {
  try {
    await compoundVaultApi.clearSessionHotCache()
    hotCacheContext.value = ''
    hotCacheContextStats.value = null
    showMessage('会话热缓存已清除')
  } catch (e) {
    console.error('clear session cache failed:', e)
  }
}

// 管理
async function loadBM25Stats() {
  try {
    const res = await compoundVaultApi.getBM25Stats()
    bm25StatsData.value = res.data
  } catch (e) { /* ignore */ }
}

async function doRebuildBM25() {
  rebuildingBM25.value = true
  try {
    await compoundVaultApi.rebuildBM25()
    showMessage('BM25 索引重建成功')
    await loadBM25Stats()
    await loadStats()
  } catch (e) {
    showMessage('BM25 重建失败', true)
    console.error('rebuild BM25 failed:', e)
  } finally {
    rebuildingBM25.value = false
  }
}

async function doClearPrefixes(path?: string) {
  try {
    await compoundVaultApi.clearPrefixes(path || undefined)
    showMessage(path ? `已清除: ${path}` : '所有前缀缓存已清除')
  } catch (e) {
    showMessage('清除失败', true)
  }
}

async function doClearEmbedCache() {
  try {
    await compoundVaultApi.clearEmbedCache()
    showMessage('嵌入缓存已清空')
    await loadStats()
  } catch (e) {
    showMessage('清空失败', true)
  }
}

// 统计
async function loadStats() {
  try {
    const res = await compoundVaultApi.getStats()
    statsData.value = res.data
  } catch (e) { /* ignore */ }
}

// 工具
let messageTimer: ReturnType<typeof setTimeout> | null = null
function showMessage(msg: string, isError = false) {
  actionMessage.value = msg
  actionError.value = isError
  if (messageTimer) clearTimeout(messageTimer)
  messageTimer = setTimeout(() => { actionMessage.value = '' }, 3000)
}

// ==================== 生命周期 ====================
onMounted(() => {
  loadStats()
  loadBM25Stats()
  loadHotCacheContext()
})
</script>
