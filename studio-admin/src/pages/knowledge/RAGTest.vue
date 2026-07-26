<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { Search, Brain, RefreshCw, CheckCircle, AlertCircle, Loader2, Database, FileText, XCircle, Cpu, Zap, Eye, EyeOff } from 'lucide-vue-next'
import { listKnowledgeBases, ragQuery, ragSearch, ragHealth, type KnowledgeBase, type RAGQueryResponse, type RAGSearchResult } from '@/api/rag'

const kbList = ref<KnowledgeBase[]>([])
const selectedKbIds = ref<string[]>([])
const queryText = ref('')
const topK = ref(5)
const mode = ref<'search' | 'query'>('search')
const loading = ref(false)
const error = ref('')

// Results
const searchResults = ref<RAGSearchResult[]>([])
const queryResult = ref<RAGQueryResponse | null>(null)
const healthStatus = ref<{ ready: boolean; knowledge_bases: number; kb_names: string[] } | null>(null)

// Expanded source content
const expandedSources = ref<Set<number>>(new Set())

onMounted(() => {
  loadKBList()
  checkHealth()
})

async function loadKBList() {
  try {
    const res = await listKnowledgeBases()
    kbList.value = res.data?.data ?? []
  } catch (e: any) {
    console.error('Failed to load knowledge bases:', e)
    error.value = '加载知识库列表失败'
  }
}

async function checkHealth() {
  try {
    const res = await ragHealth()
    healthStatus.value = res.data as any
  } catch { /* silent */ }
}

const selectedKB = computed(() =>
  kbList.value.filter((kb) => selectedKbIds.value.includes(kb.kb_id)),
)

function toggleKB(kbId: string) {
  const idx = selectedKbIds.value.indexOf(kbId)
  if (idx > -1) {
    selectedKbIds.value.splice(idx, 1)
  } else {
    selectedKbIds.value.push(kbId)
  }
}

function selectAllKB() {
  if (selectedKbIds.value.length === kbList.value.length) {
    selectedKbIds.value = []
  } else {
    selectedKbIds.value = kbList.value.map((kb) => kb.kb_id)
  }
}

function toggleSource(idx: number) {
  const s = new Set(expandedSources.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedSources.value = s
}

async function executeSearch() {
  if (!queryText.value.trim()) return
  if (selectedKbIds.value.length === 0) {
    error.value = '请至少选择一个知识库'
    return
  }
  error.value = ''
  loading.value = true
  try {
    const res = await ragSearch(queryText.value, selectedKbIds.value, topK.value)
    searchResults.value = res.data?.data ?? []
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e?.message ?? '搜索失败'
    searchResults.value = []
  } finally {
    loading.value = false
  }
}

async function executeQuery() {
  if (!queryText.value.trim()) return
  if (selectedKbIds.value.length === 0) {
    error.value = '请至少选择一个知识库'
    return
  }
  error.value = ''
  loading.value = true
  try {
    const res = await ragQuery(queryText.value, selectedKbIds.value, topK.value)
    queryResult.value = res.data as RAGQueryResponse
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e?.message ?? '查询失败'
    queryResult.value = null
  } finally {
    loading.value = false
  }
}

function execute() {
  searchResults.value = []
  queryResult.value = null
  if (mode.value === 'search') {
    executeSearch()
  } else {
    executeQuery()
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    execute()
  }
}

function truncateContent(content: string, maxLen = 80) {
  if (!content) return ''
  return content.length > maxLen ? content.slice(0, maxLen) + '...' : content
}

function scoreColor(score: number): string {
  if (score >= 0.8) return 'text-green-400'
  if (score >= 0.6) return 'text-yellow-400'
  return 'text-red-400'
}
</script>

<template>
  <div class="flex flex-col h-full overflow-hidden bg-surface-950">
    <!-- Header -->
    <header class="flex items-center justify-between border-b border-white/10 px-6 py-4 shrink-0">
      <div class="flex items-center gap-3">
        <div class="flex items-center justify-center w-9 h-9 rounded-lg bg-purple-500/15">
          <Cpu class="w-5 h-5 text-purple-400" />
        </div>
        <div>
          <h1 class="text-lg font-semibold text-white">RAG 测试台</h1>
          <p class="text-xs text-gray-500">检索增强生成 · 调试与验证</p>
        </div>
      </div>
      <div class="flex items-center gap-3">
        <button
          class="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:bg-white/5 transition-colors"
          @click="loadKBList(); checkHealth()"
        >
          <RefreshCw class="w-3.5 h-3.5" />
          刷新
        </button>
      </div>
    </header>

    <!-- Body -->
    <div class="flex flex-1 overflow-hidden">
      <!-- Left: Config Panel -->
      <div class="w-80 border-r border-white/10 flex flex-col shrink-0 overflow-y-auto p-5 gap-5">
        <!-- Health Status -->
        <div v-if="healthStatus" class="flex items-center gap-2 text-xs">
          <span
            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px]"
            :class="healthStatus.ready ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'"
          >
            <span class="w-1.5 h-1.5 rounded-full" :class="healthStatus.ready ? 'bg-green-400' : 'bg-red-400'" />
            {{ healthStatus.ready ? '就绪' : '未就绪' }}
          </span>
          <span class="text-gray-500">{{ healthStatus.knowledge_bases }} 个知识库</span>
        </div>

        <!-- Mode Switch -->
        <div>
          <label class="text-xs font-medium text-gray-400 mb-2 block">查询模式</label>
          <div class="flex bg-white/5 rounded-lg p-0.5">
            <button
              v-for="m in (['search', 'query'] as const)"
              :key="m"
              class="flex-1 flex items-center justify-center gap-1.5 py-2 text-xs rounded-md transition-all"
              :class="mode === m ? 'bg-brand-500/20 text-brand-400 font-medium' : 'text-gray-500 hover:text-gray-300'"
              @click="mode = m"
            >
              <Search v-if="m === 'search'" class="w-3.5 h-3.5" />
              <Brain v-else class="w-3.5 h-3.5" />
              {{ m === 'search' ? '检索' : '生成' }}
            </button>
          </div>
          <p class="text-[11px] text-gray-600 mt-1.5 leading-relaxed">
            {{ mode === 'search' ? '向量检索最相关文档片段，不调用 LLM' : '检索 + LLM 生成完整答案，引用源文档' }}
          </p>
        </div>

        <!-- KB Selector -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <label class="text-xs font-medium text-gray-400">选择知识库</label>
            <button
              class="text-[11px] text-purple-400 hover:text-purple-300 transition-colors"
              @click="selectAllKB"
            >
              {{ selectedKbIds.length === kbList.length ? '取消全选' : '全选' }}
            </button>
          </div>
          <div v-if="kbList.length === 0" class="text-xs text-gray-600 py-3 text-center bg-white/[0.02] rounded-lg">
            暂无知识库
          </div>
          <div v-else class="space-y-1 max-h-48 overflow-y-auto pr-1">
            <label
              v-for="kb in kbList"
              :key="kb.kb_id"
              class="flex items-center gap-2 rounded-lg px-2.5 py-2 cursor-pointer transition-colors hover:bg-white/[0.03]"
              :class="selectedKbIds.includes(kb.kb_id) ? 'bg-purple-500/8 ring-1 ring-purple-500/20' : ''"
            >
              <input
                type="checkbox"
                :checked="selectedKbIds.includes(kb.kb_id)"
                class="w-3.5 h-3.5 rounded border-gray-600 bg-transparent text-purple-500 focus:ring-purple-500/30"
                @change="toggleKB(kb.kb_id)"
              />
              <div class="flex-1 min-w-0">
                <div class="text-sm text-white truncate">{{ kb.name }}</div>
                <div class="text-[11px] text-gray-500">
                  {{ kb.document_count ?? kb.stats?.documents ?? 0 }} 文档 · {{ kb.chunk_count ?? kb.stats?.chunks ?? 0 }} 分块
                </div>
              </div>
            </label>
          </div>
          <div v-if="selectedKbIds.length > 0" class="text-[11px] text-purple-400/80 mt-1.5">
            已选 {{ selectedKbIds.length }} / {{ kbList.length }} 个知识库
          </div>
        </div>

        <!-- Top K -->
        <div>
          <label class="text-xs font-medium text-gray-400 mb-2 block">Top-K 结果数</label>
          <div class="flex items-center gap-3">
            <input
              type="range"
              v-model.number="topK"
              min="1"
              max="20"
              class="flex-1 h-1.5 rounded-full appearance-none bg-white/10 accent-purple-500 cursor-pointer"
            />
            <span class="text-sm font-mono text-purple-400 w-8 text-right tabular-nums">{{ topK }}</span>
          </div>
          <div class="flex justify-between text-[10px] text-gray-600 mt-1">
            <span>1</span><span>20</span>
          </div>
        </div>
      </div>

      <!-- Right: Main Area -->
      <div class="flex-1 flex flex-col overflow-hidden">
        <!-- Query Input -->
        <div class="p-5 pb-0 shrink-0">
          <div class="flex gap-3">
            <div class="flex-1 relative">
              <textarea
                v-model="queryText"
                placeholder="输入查询文本，按 Enter 执行..."
                rows="2"
                class="w-full bg-surface-800 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-500 resize-none focus:outline-none focus:ring-2 focus:ring-purple-500/30 focus:border-purple-500/50 transition-all"
                @keydown="handleKeydown"
              />
            </div>
            <button
              class="flex items-center justify-center gap-2 px-5 rounded-xl text-sm font-medium transition-all shrink-0"
              :class="
                loading || !queryText.trim()
                  ? 'bg-white/5 text-gray-600 cursor-not-allowed'
                  : 'bg-purple-500 text-white hover:bg-purple-600 active:scale-[0.98]'
              "
              :disabled="loading || !queryText.trim()"
              @click="execute"
            >
              <Loader2 v-if="loading" class="w-4 h-4 animate-spin" />
              <Search v-else class="w-4 h-4" />
              {{ mode === 'search' ? '检索' : '查询' }}
            </button>
          </div>
        </div>

        <!-- Error Banner -->
        <div
          v-if="error"
          class="mx-5 mt-3 flex items-start gap-2 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-red-400 text-sm"
        >
          <AlertCircle class="w-4 h-4 shrink-0 mt-0.5" />
          {{ error }}
          <button class="ml-auto text-red-400/60 hover:text-red-300" @click="error = ''">
            <XCircle class="w-4 h-4" />
          </button>
        </div>

        <!-- Results -->
        <div class="flex-1 overflow-y-auto p-5">
          <!-- Empty State -->
          <div
            v-if="!loading && searchResults.length === 0 && !queryResult"
            class="flex flex-col items-center justify-center h-full text-gray-600 gap-3"
          >
            <div class="w-16 h-16 rounded-2xl bg-purple-500/10 flex items-center justify-center">
              <Database class="w-8 h-8 text-purple-400/40" />
            </div>
            <p class="text-sm">输入查询文本开始检索或生成</p>
            <p class="text-xs text-gray-700">选择一个或多个知识库，然后输入内容</p>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="flex flex-col items-center justify-center h-full gap-3">
            <Loader2 class="w-8 h-8 text-purple-400 animate-spin" />
            <p class="text-sm text-gray-500">{{ mode === 'search' ? '正在检索...' : '正在生成...' }}</p>
          </div>

          <!-- Search Mode Results -->
          <div v-if="!loading && mode === 'search' && searchResults.length > 0" class="space-y-3">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-medium text-gray-300">
                检索结果 <span class="text-purple-400 font-mono">{{ searchResults.length }}</span> 条
              </h3>
            </div>
            <div
              v-for="(item, idx) in searchResults"
              :key="idx"
              class="rounded-xl border border-white/5 bg-surface-800/50 hover:bg-surface-800 transition-colors overflow-hidden"
            >
              <div class="p-4">
                <div class="flex items-center justify-between mb-2">
                  <div class="flex items-center gap-2 min-w-0">
                    <span class="text-xs font-mono text-gray-600 bg-white/5 px-1.5 py-0.5 rounded">#{{ idx + 1 }}</span>
                    <span class="text-xs text-gray-500 truncate max-w-[300px]" :title="item.source">
                      <FileText class="w-3 h-3 inline-block mr-1" />
                      {{ item.source }}
                    </span>
                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-400 shrink-0">
                      {{ item.kb_name }}
                    </span>
                  </div>
                  <span class="text-xs font-mono font-medium shrink-0 ml-2" :class="scoreColor(item.score)">
                    {{ (item.score * 100).toFixed(1) }}%
                  </span>
                </div>
                <div class="relative">
                  <p
                    class="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap break-all"
                    :class="{ 'line-clamp-3': !expandedSources.has(idx) }"
                  >
                    {{ item.content || '(空内容)' }}
                  </p>
                  <button
                    v-if="item.content && item.content.length > 150"
                    class="text-xs text-purple-400 hover:text-purple-300 mt-1 inline-flex items-center gap-1"
                    @click="toggleSource(idx)"
                  >
                    <Eye v-if="!expandedSources.has(idx)" class="w-3 h-3" />
                    <EyeOff v-else class="w-3 h-3" />
                    {{ expandedSources.has(idx) ? '收起' : '展开全文' }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Query Mode Result -->
          <div v-if="!loading && mode === 'query' && queryResult" class="space-y-4">
            <!-- Answer -->
            <div class="rounded-xl border border-white/5 bg-surface-800/50 overflow-hidden">
              <div class="flex items-center gap-2 px-4 py-3 border-b border-white/5">
                <Brain class="w-4 h-4 text-purple-400" />
                <span class="text-sm font-medium text-white">生成回答</span>
                <span class="text-[10px] text-gray-500 ml-auto">
                  {{ queryResult.original_chunks }} → {{ queryResult.final_chunks }} 分块
                  <span v-if="queryResult.compressed" class="ml-1 text-purple-400">已压缩</span>
                </span>
              </div>
              <div class="p-4">
                <p class="text-sm text-gray-200 leading-relaxed whitespace-pre-wrap break-all">
                  {{ queryResult.answer }}
                </p>
              </div>
            </div>

            <!-- Sources -->
            <div v-if="queryResult.sources?.length" class="rounded-xl border border-white/5 bg-surface-800/50 overflow-hidden">
              <div class="flex items-center gap-2 px-4 py-3 border-b border-white/5">
                <FileText class="w-4 h-4 text-green-400" />
                <span class="text-sm font-medium text-white">引用来源</span>
                <span class="text-[10px] text-gray-500">{{ queryResult.sources.length }} 条</span>
              </div>
              <div class="p-4 space-y-3">
                <div
                  v-for="(src, idx) in queryResult.sources"
                  :key="idx"
                  class="border border-white/5 rounded-lg p-3 bg-white/[0.02]"
                >
                  <div class="flex items-center gap-2 mb-1.5">
                    <span class="text-xs font-mono text-gray-600">[{{ idx + 1 }}]</span>
                    <span class="text-xs text-gray-500 truncate">{{ src.source }}</span>
                    <span class="text-[10px] text-purple-400 bg-purple-500/10 px-1.5 py-0.5 rounded">{{ src.kb_name }}</span>
                    <span class="text-xs font-mono font-medium ml-auto shrink-0" :class="scoreColor(src.score)">
                      {{ (src.score * 100).toFixed(1) }}%
                    </span>
                  </div>
                  <p class="text-xs text-gray-400 leading-relaxed"
                    :class="{ 'line-clamp-2': !expandedSources.has(idx + 100) }"
                  >
                    {{ src.content || '(空内容)' }}
                  </p>
                  <button
                    v-if="src.content && src.content.length > 150"
                    class="text-[10px] text-purple-400 hover:text-purple-300 mt-1 inline-flex items-center gap-1"
                    @click="toggleSource(idx + 100)"
                  >
                    {{ expandedSources.has(idx + 100) ? '收起' : '展开' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
