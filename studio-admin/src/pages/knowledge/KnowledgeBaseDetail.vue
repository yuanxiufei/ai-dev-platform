<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getKnowledgeBase,
  deleteKnowledgeBase,
  batchUploadDocuments,
  importFromSite,
  importFromDify,
  listDocuments,
  deleteDocument,
  listChunks,
  deleteChunks,
  type KnowledgeBase,
  type SiteImportResponse,
  type KBDocument,
} from '@/api/rag'
import { ArrowLeft, Upload, Globe, Database, Trash2, RefreshCw, RotateCw, FileText, CheckCircle, XCircle, Loader2, AlertCircle, Search, Play, Server } from 'lucide-vue-next'
import { useTrainingProgress } from '@/composables/useTrainingProgress'

const route = useRoute()
const router = useRouter()
const kbId = computed(() => route.params.id as string)

/* ========== KB 信息 ========== */
const kb = ref<KnowledgeBase | null>(null)
const loadingKb = ref(true)
const kbError = ref('')

async function loadKB() {
  loadingKb.value = true
  kbError.value = ''
  try {
    kb.value = await getKnowledgeBase(kbId.value)
  } catch (e: any) {
    kbError.value = e?.message || '加载失败'
  } finally {
    loadingKb.value = false
  }
}

const docCount = computed(() => kb.value?.document_count ?? kb.value?.stats?.documents ?? 0)
const chunkCount = computed(() => kb.value?.chunk_count ?? kb.value?.stats?.chunks ?? 0)

/* ========== Tab 切换 ========== */
const activeTab = ref<'batch' | 'site' | 'dify' | 'documents'>('batch')

/* ========== 批量上传 ========== */
const batchFiles = ref<File[]>([])
const batchUploading = ref(false)
const batchResults = ref<{ filename: string; chunks: number; status: string; error?: string }[] | null>(null)
const batchError = ref('')

/* ========== 服务器端训练（WebSocket 实时进度） ========== */
const serverPath = ref('')
const {
  stage: trainStage,
  pct: trainPct,
  message: trainMessage,
  chunkCount: trainChunkCount,
  connected: trainConnected,
  error: trainError,
  done: trainDone,
  connect: connectTrain,
} = useTrainingProgress()

function handleServerTrain() {
  if (!serverPath.value.trim()) return
  connectTrain(kbId.value, serverPath.value.trim())
}

/* ========== 重新训练（retrain-ws 实时进度） ========== */
const {
  stage: retrainStage,
  pct: retrainPct,
  message: retrainMessage,
  connected: retrainConnected,
  error: retrainError,
  done: retrainDone,
  connectRetrain,
} = useTrainingProgress()

function handleRetrain() {
  if (!confirm('确认重新训练？将清空向量索引并重新嵌入所有文档，不可撤销。')) return
  connectRetrain(kbId.value)
}

function statusLabel(s?: string) {
  const map: Record<string, string> = {
    pending: '待嵌入',
    embedding: '嵌入中',
    completed: '已嵌入',
    failed: '失败',
  }
  return map[s ?? ''] || '待处理'
}

function onFilesSelected(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files) {
    batchFiles.value = Array.from(target.files)
    batchResults.value = null
    batchError.value = ''
  }
}

async function handleBatchUpload() {
  if (!batchFiles.value.length) return
  batchUploading.value = true
  batchResults.value = null
  batchError.value = ''
  try {
    const res = await batchUploadDocuments(kbId.value, batchFiles.value)
    batchResults.value = res.results
    batchFiles.value = []
    await loadKB()
  } catch (e: any) {
    batchError.value = e?.message || '批量上传失败'
  } finally {
    batchUploading.value = false
  }
}

/* ========== 整站导入 ========== */
const siteMode = ref<'sitemap' | 'urllist'>('sitemap')
const sitemapUrl = ref('')
const urlList = ref('')
const siteMaxPages = ref(50)
const siteMaxConcurrent = ref(5)
const siteImporting = ref(false)
const siteResult = ref<SiteImportResponse | null>(null)
const siteError = ref('')

async function handleSiteImport() {
  siteImporting.value = true
  siteResult.value = null
  siteError.value = ''
  try {
    const body: any = { max_pages: siteMaxPages.value, max_concurrent: siteMaxConcurrent.value }
    if (siteMode.value === 'sitemap') {
      if (!sitemapUrl.value.trim()) throw new Error('请输入 Sitemap URL')
      body.sitemap_url = sitemapUrl.value.trim()
    } else {
      const urls = urlList.value.split('\n').map(u => u.trim()).filter(Boolean)
      if (!urls.length) throw new Error('请输入至少一个 URL')
      body.urls = urls
    }
    siteResult.value = await importFromSite(kbId.value, body)
    await loadKB()
  } catch (e: any) {
    siteError.value = e?.message || '整站导入失败'
  } finally {
    siteImporting.value = false
  }
}

/* ========== Dify 导入 ========== */
const difyKbName = ref('')
const difyDocDir = ref('/app/knowledge-data/documents/')
const difyChunkSize = ref(1024)
const difyChunkOverlap = ref(256)
const difyImporting = ref(false)
const difyResult = ref<{ kb_name: string; total_documents: number; total_chunks: number; total_embedded: number; errors: string[]; duration_sec: number } | null>(null)
const difyError = ref('')

async function handleDifyImport() {
  if (!difyKbName.value.trim()) return
  difyImporting.value = true
  difyResult.value = null
  difyError.value = ''
  try {
    difyResult.value = await importFromDify({
      kb_name: difyKbName.value.trim(),
      doc_dir: difyDocDir.value.trim() || undefined,
      chunk_size: difyChunkSize.value,
      chunk_overlap: difyChunkOverlap.value,
    })
  } catch (e: any) {
    difyError.value = e?.message || 'Dify 导入失败'
  } finally {
    difyImporting.value = false
  }
}

/* ========== 文档列表 ========== */
const docs = ref<KBDocument[]>([])
const docsLoading = ref(false)
const docDeleting = ref<string | null>(null)

/* ========== Chunk 展开 ========== */
const expandedDocId = ref<string | null>(null)
const chunks = ref<Array<{ doc_id: string; content: string; metadata: Record<string, unknown> }>>([])
const chunksLoading = ref(false)
const chunkPage = ref(1)
const chunkTotal = ref(0)
const chunkDeleting = ref<string | null>(null)

const fetchDocs = async () => {
  if (!kbId.value) return
  docsLoading.value = true
  try {
    const res: any = await listDocuments(kbId.value)
    docs.value = res.data ?? []
  } catch (e: any) {
    console.error('加载文档列表失败', e)
  } finally {
    docsLoading.value = false
  }
}

const onDeleteDocument = async (d: KBDocument) => {
  if (!confirm(`确认删除文档「${d.doc_name}」？向量索引和元数据将被永久清除。`)) return
  docDeleting.value = d.doc_id
  try {
    await deleteDocument(kbId.value!, d.doc_id)
    await Promise.all([fetchDocs(), loadKB()])
  } catch (e: any) {
    alert(e?.response?.data?.detail || '删除失败')
  } finally {
    docDeleting.value = null
  }
}

/* ========== Chunk 展开 & 删除 ========== */

async function toggleChunks(doc: KBDocument) {
  if (expandedDocId.value === doc.doc_id) {
    expandedDocId.value = null
    chunks.value = []
    return
  }
  expandedDocId.value = doc.doc_id
  chunkPage.value = 1
  await loadChunks(doc)
}

async function loadChunks(doc: KBDocument) {
  chunksLoading.value = true
  try {
    const res: any = await listChunks(
      kbId.value!,
      doc.doc_id,
      chunkPage.value,
      50,
    )
    chunks.value = res.data ?? []
    chunkTotal.value = res.total ?? 0
  } catch (e: any) {
    console.error('加载 chunk 列表失败', e)
    chunks.value = []
    chunkTotal.value = 0
  } finally {
    chunksLoading.value = false
  }
}

async function onDeleteChunk(chunkDocId: string) {
  if (!confirm('确认删除此 chunk？')) return
  chunkDeleting.value = chunkDocId
  try {
    await deleteChunks(kbId.value!, [chunkDocId])
    chunks.value = chunks.value.filter(c => c.doc_id !== chunkDocId)
    chunkTotal.value = Math.max(0, chunkTotal.value - 1)
    await loadKB()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '删除 chunk 失败')
  } finally {
    chunkDeleting.value = null
  }
}

async function onDeleteSelectedChunks() {
  const selected = chunks.value.filter((c: any) => c._selected)
  if (selected.length === 0) {
    alert('请先勾选要删除的 chunk')
    return
  }
  if (!confirm(`确认删除 ${selected.length} 个 chunk？`)) return
  try {
    const ids = selected.map((c: any) => c.doc_id)
    await deleteChunks(kbId.value!, ids)
    chunks.value = chunks.value.filter((c: any) => !c._selected)
    chunkTotal.value = Math.max(0, chunkTotal.value - ids.length)
    await loadKB()
  } catch (e: any) {
    alert(e?.response?.data?.detail || '批量删除 chunk 失败')
  }
}

const formatFileSize = (bytes: number): string => {
  if (!bytes || bytes <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let v = bytes
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`
}

/* ========== 删除 KB ========== */
const confirmDelete = ref(false)
const deletingKb = ref(false)

async function handleDeleteKB() {
  confirmDelete.value = false
  deletingKb.value = true
  try {
    await deleteKnowledgeBase(kbId.value)
    router.replace('/knowledge')
  } catch (e: any) {
    alert(e?.message || '删除失败')
  } finally {
    deletingKb.value = false
  }
}

onMounted(() => {
  loadKB()
  fetchDocs()
})
</script>

<template>
  <div class="h-full overflow-y-auto p-6">
    <!-- 返回 -->
    <button
      class="flex items-center gap-1.5 text-sm text-gray-400 hover:text-gray-200 transition-colors mb-4"
      @click="router.push('/knowledge')"
    >
      <ArrowLeft class="w-4 h-4" />
      返回知识库列表
    </button>

    <!-- 加载中 -->
    <div v-if="loadingKb" class="flex items-center justify-center py-20">
      <Loader2 class="w-6 h-6 animate-spin text-brand-400" />
    </div>

    <!-- 错误 -->
    <div v-else-if="kbError" class="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400 text-sm">
      {{ kbError }}
    </div>

    <template v-else-if="kb">
      <!-- KB 头部 -->
      <div class="flex items-start justify-between mb-6">
        <div class="flex-1 min-w-0">
          <h1 class="text-2xl font-bold text-white truncate">{{ kb.name }}</h1>
          <p v-if="kb.description" class="text-sm text-gray-400 mt-1">{{ kb.description }}</p>
          <div class="flex gap-4 mt-3 text-xs text-gray-500">
            <span class="flex items-center gap-1">
              <FileText class="w-3.5 h-3.5" />
              {{ docCount }} 文档 · {{ chunkCount }} 分块
            </span>
            <span v-if="kb.chunk_size">
              📐 {{ kb.chunk_size }} / {{ kb.chunk_overlap ?? '-' }}
            </span>
            <span v-if="kb.chunk_strategy">
              📋 {{ kb.chunk_strategy }}
            </span>
          </div>
        </div>
        <button
          class="flex items-center gap-1 rounded-lg px-3 py-1.5 text-xs text-red-400 border border-red-500/30 hover:bg-red-500/10 transition-colors"
          :disabled="deletingKb"
          @click="confirmDelete = true"
        >
          <Trash2 class="w-3.5 h-3.5" />
          {{ deletingKb ? '删除中...' : '删除知识库' }}
        </button>
      </div>

      <!-- Tab 切换 -->
      <div class="flex gap-1 border-b border-white/10 mb-4">
        <button
          v-for="tab in [
            { key: 'batch' as const, label: '📦 批量上传' },
            { key: 'documents' as const, label: '📄 文档列表' },
            { key: 'site' as const, label: '🌐 整站导入' },
            { key: 'dify' as const, label: '🔗 Dify 导入' },
          ]"
          :key="tab.key"
          :class="[
            'px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px',
            activeTab === tab.key
              ? 'border-brand-400 text-brand-400'
              : 'border-transparent text-gray-400 hover:text-gray-200',
          ]"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- ===== Tab: 批量上传 ===== -->
      <div v-if="activeTab === 'batch'" class="space-y-4">
        <label
          class="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-white/15 hover:border-brand-400/50 p-10 cursor-pointer transition-colors"
        >
          <Upload class="w-8 h-8 text-gray-500" />
          <span class="text-sm text-gray-400">点击选择文件或拖拽到此处</span>
          <span class="text-xs text-gray-600">支持 .txt, .md, .pdf, .html, .json 等格式</span>
          <input type="file" multiple class="hidden" @change="onFilesSelected" />
        </label>

        <div v-if="batchFiles.length" class="rounded-lg border border-white/10 bg-surface-800 p-3">
          <div class="text-xs text-gray-400 mb-2">已选 {{ batchFiles.length }} 个文件</div>
          <div class="text-xs text-gray-500 space-y-1 max-h-32 overflow-y-auto">
            <div v-for="(f, i) in batchFiles" :key="i" class="truncate">
              · {{ f.name }} ({{ (f.size / 1024).toFixed(1) }} KB)
            </div>
          </div>
          <button
            class="mt-3 w-full flex items-center justify-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors disabled:opacity-50"
            :disabled="batchUploading"
            @click="handleBatchUpload"
          >
            <Loader2 v-if="batchUploading" class="w-4 h-4 animate-spin" />
            <Upload v-else class="w-4 h-4" />
            {{ batchUploading ? '上传中...' : '开始上传' }}
          </button>
        </div>

        <!-- 结果 -->
        <div v-if="batchResults" class="rounded-lg border border-white/10 bg-surface-800 p-3">
          <div class="text-sm font-medium text-white mb-2">上传结果</div>
          <div class="space-y-1.5 max-h-64 overflow-y-auto">
            <div
              v-for="(r, i) in batchResults"
              :key="i"
              :class="[
                'flex items-center gap-2 text-xs',
                r.status === 'ok' ? 'text-green-400' : 'text-red-400',
              ]"
            >
              <CheckCircle v-if="r.status === 'ok'" class="w-3.5 h-3.5 shrink-0" />
              <XCircle v-else class="w-3.5 h-3.5 shrink-0" />
              <span class="truncate">{{ r.filename }}</span>
              <span v-if="r.status === 'ok'" class="text-gray-500 shrink-0">({{ r.chunks }} chunks)</span>
              <span v-if="r.error" class="text-red-400 shrink-0 truncate">{{ r.error }}</span>
            </div>
          </div>
        </div>

        <div v-if="batchError" class="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          {{ batchError }}
        </div>

        <!-- ─── 服务器端训练（实时进度） ─── -->
        <div class="rounded-lg border border-white/10 bg-surface-800 p-4">
          <div class="flex items-center gap-2 text-sm font-medium text-gray-200 mb-3">
            <Server class="w-4 h-4" />
            服务器端文件训练（实时进度）
          </div>
          <div class="flex gap-2">
            <input
              v-model="serverPath"
              type="text"
              placeholder="输入服务器端文件路径, 如 /data/docs/paper.pdf"
              class="flex-1 rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:outline-none focus:border-brand-500/50"
              :disabled="trainConnected"
            />
            <button
              class="flex items-center gap-1.5 rounded-lg bg-brand-500 px-3 py-2 text-sm font-medium text-white hover:bg-brand-600 transition-colors disabled:opacity-50 shrink-0"
              :disabled="trainConnected || !serverPath.trim()"
              @click="handleServerTrain"
            >
              <Play class="w-3.5 h-3.5" />
              训练
            </button>
          </div>

          <!-- 进度条 -->
          <div v-if="trainConnected || trainDone || trainError" class="mt-3">
            <div class="flex items-center justify-between text-xs mb-1.5">
              <span class="text-gray-400">
                <Loader2 v-if="trainConnected && !trainDone" class="w-3 h-3 inline animate-spin mr-1" />
                <CheckCircle v-if="trainDone" class="w-3 h-3 inline text-green-400 mr-1" />
                <XCircle v-if="trainError" class="w-3 h-3 inline text-red-400 mr-1" />
                {{ trainMessage }}
              </span>
              <span class="text-gray-500">{{ trainPct }}%</span>
            </div>
            <div class="h-2 rounded-full bg-surface-900 overflow-hidden">
              <div
                :class="[
                  'h-full rounded-full transition-all duration-300',
                  trainDone ? 'bg-green-500' : trainError ? 'bg-red-500' : 'bg-brand-500',
                ]"
                :style="{ width: trainPct + '%' }"
              />
            </div>
            <div v-if="trainDone && trainChunkCount > 0" class="text-xs text-green-400 mt-1">
              共生成 {{ trainChunkCount }} 个 chunk
            </div>
          </div>
        </div>
      </div>

      <!-- ===== Tab: 整站导入 ===== -->
      <div v-if="activeTab === 'site'" class="space-y-4">
        <div class="flex gap-2">
          <button
            :class="[
              'px-3 py-1.5 rounded-md text-sm transition-colors',
              siteMode === 'sitemap' ? 'bg-brand-500/20 text-brand-400' : 'bg-surface-800 text-gray-400 hover:text-gray-200',
            ]"
            @click="siteMode = 'sitemap'"
          >
            Sitemap 模式
          </button>
          <button
            :class="[
              'px-3 py-1.5 rounded-md text-sm transition-colors',
              siteMode === 'urllist' ? 'bg-brand-500/20 text-brand-400' : 'bg-surface-800 text-gray-400 hover:text-gray-200',
            ]"
            @click="siteMode = 'urllist'"
          >
            URL 列表模式
          </button>
        </div>

        <div v-if="siteMode === 'sitemap'">
          <label class="block text-sm text-gray-400 mb-1.5">Sitemap URL</label>
          <input
            v-model="sitemapUrl"
            type="text"
            placeholder="https://example.com/sitemap.xml"
            class="w-full rounded-lg border border-white/10 bg-surface-800 px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-brand-400 focus:outline-none"
          />
          <p class="text-xs text-gray-600 mt-1">支持标准 sitemap.xml 及嵌套 sitemap 索引</p>
        </div>

        <div v-if="siteMode === 'urllist'">
          <label class="block text-sm text-gray-400 mb-1.5">URL 列表（每行一个）</label>
          <textarea
            v-model="urlList"
            rows="5"
            placeholder="https://example.com/page1&#10;https://example.com/page2"
            class="w-full rounded-lg border border-white/10 bg-surface-800 px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-brand-400 focus:outline-none resize-y"
          />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-gray-400 mb-1">最大抓取页面</label>
            <input
              v-model.number="siteMaxPages"
              type="number" min="1" max="500"
              class="w-full rounded-lg border border-white/10 bg-surface-800 px-3 py-1.5 text-sm text-white focus:border-brand-400 focus:outline-none"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">并发数</label>
            <input
              v-model.number="siteMaxConcurrent"
              type="number" min="1" max="10"
              class="w-full rounded-lg border border-white/10 bg-surface-800 px-3 py-1.5 text-sm text-white focus:border-brand-400 focus:outline-none"
            />
          </div>
        </div>

        <button
          class="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-600 transition-colors disabled:opacity-50"
          :disabled="siteImporting"
          @click="handleSiteImport"
        >
          <Loader2 v-if="siteImporting" class="w-4 h-4 animate-spin" />
          <Globe v-else class="w-4 h-4" />
          {{ siteImporting ? '导入中...' : '开始整站导入' }}
        </button>

        <div v-if="siteResult" class="rounded-lg border border-white/10 bg-surface-800 p-3 space-y-1">
          <div class="text-sm font-medium text-white mb-1">导入结果</div>
          <div class="text-xs text-gray-400">
            <div v-if="siteResult.total_found != null">发现页面：{{ siteResult.total_found }}</div>
            <div v-if="siteResult.crawled_ok != null">✅ 抓取成功：{{ siteResult.crawled_ok }}</div>
            <div v-if="siteResult.crawled_fail != null">❌ 抓取失败：{{ siteResult.crawled_fail }}</div>
            <div v-if="siteResult.imported != null">📥 已导入：{{ siteResult.imported }}</div>
            <div v-if="siteResult.base_domain">🌍 域名：{{ siteResult.base_domain }}</div>
          </div>
          <div v-if="siteResult.crawl_errors?.length" class="mt-2 text-xs text-red-400">
            <div class="font-medium text-red-500">抓取错误：</div>
            <div v-for="(e, i) in siteResult.crawl_errors.slice(0, 5)" :key="i" class="truncate">{{ e }}</div>
          </div>
        </div>

        <div v-if="siteError" class="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          {{ siteError }}
        </div>
      </div>

      <!-- ===== Tab: Dify 导入 ===== -->
      <div v-if="activeTab === 'dify'" class="space-y-4">
        <div>
          <label class="block text-sm text-gray-400 mb-1">
            知识库名称
            <span class="text-red-400">*</span>
          </label>
          <input
            v-model="difyKbName"
            type="text"
            placeholder="my-dify-kb"
            class="w-full rounded-lg border border-white/10 bg-surface-800 px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-brand-400 focus:outline-none"
          />
        </div>

        <div>
          <label class="block text-sm text-gray-400 mb-1">文档目录</label>
          <input
            v-model="difyDocDir"
            type="text"
            placeholder="/app/knowledge-data/documents/"
            class="w-full rounded-lg border border-white/10 bg-surface-800 px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-brand-400 focus:outline-none"
          />
          <p class="text-xs text-gray-600 mt-1">容器内挂载路径，默认 /app/knowledge-data/documents/</p>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-xs text-gray-400 mb-1">分块大小 (chunk_size)</label>
            <input
              v-model.number="difyChunkSize"
              type="number" min="256" max="4096"
              class="w-full rounded-lg border border-white/10 bg-surface-800 px-3 py-1.5 text-sm text-white focus:border-brand-400 focus:outline-none"
            />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">重叠大小 (overlap)</label>
            <input
              v-model.number="difyChunkOverlap"
              type="number" min="0" max="1024"
              class="w-full rounded-lg border border-white/10 bg-surface-800 px-3 py-1.5 text-sm text-white focus:border-brand-400 focus:outline-none"
            />
          </div>
        </div>

        <button
          class="w-full flex items-center justify-center gap-2 rounded-lg bg-brand-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-brand-600 transition-colors disabled:opacity-50"
          :disabled="difyImporting || !difyKbName.trim()"
          @click="handleDifyImport"
        >
          <Loader2 v-if="difyImporting" class="w-4 h-4 animate-spin" />
          <Database v-else class="w-4 h-4" />
          {{ difyImporting ? '导入中...' : '从 Dify 导入' }}
        </button>

        <div v-if="difyResult" class="rounded-lg border border-white/10 bg-surface-800 p-3 space-y-1">
          <div class="text-sm font-medium text-white mb-1">导入结果</div>
          <div class="text-xs text-gray-400">
            <div>知识库：{{ difyResult.kb_name }}</div>
            <div>📄 文档数：{{ difyResult.total_documents }}</div>
            <div>🧩 分块数：{{ difyResult.total_chunks }}</div>
            <div>📐 嵌入数：{{ difyResult.total_embedded }}</div>
            <div>⏱️ 耗时：{{ difyResult.duration_sec?.toFixed(1) }}s</div>
          </div>
          <div v-if="difyResult.errors?.length" class="mt-2 text-xs text-red-400">
            <div class="font-medium text-red-500">错误：</div>
            <div v-for="(err, i) in difyResult.errors.slice(0, 5)" :key="i" class="truncate">{{ err }}</div>
          </div>
        </div>

        <div v-if="difyError" class="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
          {{ difyError }}
        </div>
      </div>

      <!-- ===== 文档列表面板 ===== -->
      <div v-if="activeTab === 'documents'" class="space-y-3">
        <div class="flex items-center justify-between">
          <span class="text-sm text-gray-400">
            共 {{ docs.length }} 个文档
          </span>
          <div class="flex items-center gap-2">
            <!-- Retrain 按钮 -->
            <button
              class="flex items-center gap-1 text-xs text-orange-400 hover:text-orange-300 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="retrainConnected"
              @click="handleRetrain"
              title="重新嵌入所有文档"
            >
              <RotateCw :class="['w-3.5 h-3.5', retrainConnected && 'animate-spin']" />
              重新训练
            </button>
            <button
              class="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
              @click="fetchDocs"
              :disabled="docsLoading"
            >
              <RefreshCw :class="['w-3.5 h-3.5', docsLoading && 'animate-spin']" />
              刷新
            </button>
          </div>
        </div>

        <!-- Retrain 进度 -->
        <div v-if="retrainConnected || retrainDone || retrainError" class="rounded-lg border border-white/10 bg-surface-800 p-3">
          <div class="flex items-center justify-between text-xs mb-1.5">
            <span class="text-gray-400">
              <Loader2 v-if="retrainConnected && !retrainDone" class="w-3 h-3 inline animate-spin mr-1" />
              <CheckCircle v-if="retrainDone" class="w-3 h-3 inline text-green-400 mr-1" />
              <XCircle v-if="retrainError" class="w-3 h-3 inline text-red-400 mr-1" />
              {{ retrainMessage }}
            </span>
            <span class="text-gray-500">{{ retrainPct }}%</span>
          </div>
          <div class="h-2 rounded-full bg-surface-900 overflow-hidden">
            <div
              :class="[
                'h-full rounded-full transition-all duration-300',
                retrainDone ? 'bg-green-500' : retrainError ? 'bg-red-500' : 'bg-orange-500',
              ]"
              :style="{ width: retrainPct + '%' }"
            />
          </div>
        </div>

        <!-- 加载态 -->
        <div v-if="docsLoading && docs.length === 0" class="flex items-center justify-center py-8 text-sm text-gray-500">
          <Loader2 class="w-4 h-4 animate-spin mr-2" />
          加载中...
        </div>

        <!-- 空态 -->
        <div v-else-if="docs.length === 0" class="text-center py-12 text-gray-500">
          <FileText class="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p class="text-sm">暂无文档，请在「批量上传」或「整站导入」中添加</p>
        </div>

        <!-- 文档表格 -->
        <div v-else class="rounded-lg border border-white/10 overflow-hidden">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-white/10 bg-surface-800 text-left">
                <th class="px-4 py-2.5 font-medium text-gray-400 w-8">#</th>
                <th class="px-4 py-2.5 font-medium text-gray-400">文档名称</th>
                <th class="px-4 py-2.5 font-medium text-gray-400 w-24">类型</th>
                <th class="px-4 py-2.5 font-medium text-gray-400 w-24">大小</th>
                <th class="px-4 py-2.5 font-medium text-gray-400 w-20">分块</th>
                <th class="px-4 py-2.5 font-medium text-gray-400 w-24">嵌入</th>
                <th class="px-4 py-2.5 font-medium text-gray-400 w-40">上传时间</th>
                <th class="px-4 py-2.5 font-medium text-gray-400 w-28">操作</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="(d, idx) in docs" :key="d.doc_id">
                <tr
                  class="border-b border-white/5 hover:bg-surface-800/50 transition-colors cursor-pointer"
                  @click="toggleChunks(d)"
                >
                  <td class="px-4 py-2.5 text-gray-500 text-xs">{{ idx + 1 }}</td>
                  <td class="px-4 py-2.5 text-white truncate max-w-[240px]" :title="d.doc_name">
                    <span class="text-brand-400 text-xs mr-1">{{ expandedDocId === d.doc_id ? '▼' : '▶' }}</span>
                    {{ d.doc_name }}
                  </td>
                  <td class="px-4 py-2.5 text-gray-400 text-xs">
                    <span class="px-1.5 py-0.5 rounded bg-surface-700 text-gray-300">
                      {{ d.file_type || '—' }}
                    </span>
                  </td>
                  <td class="px-4 py-2.5 text-gray-400 text-xs">{{ formatFileSize(d.file_size) }}</td>
                  <td class="px-4 py-2.5 text-gray-400 text-xs">{{ d.chunk_count ?? '—' }}</td>
                  <td class="px-4 py-2.5 text-xs" @click.stop>
                    <span
                      :class="[
                        'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs',
                        d.embedding_status === 'completed' ? 'bg-green-500/15 text-green-400' :
                        d.embedding_status === 'embedding' ? 'bg-blue-500/15 text-blue-400' :
                        d.embedding_status === 'failed' ? 'bg-red-500/15 text-red-400' :
                        'bg-gray-500/15 text-gray-400',
                      ]"
                    >
                      <Loader2 v-if="d.embedding_status === 'embedding'" class="w-2.5 h-2.5 animate-spin" />
                      <CheckCircle v-else-if="d.embedding_status === 'completed'" class="w-2.5 h-2.5" />
                      <XCircle v-else-if="d.embedding_status === 'failed'" class="w-2.5 h-2.5" />
                      <AlertCircle v-else class="w-2.5 h-2.5" />
                      {{ statusLabel(d.embedding_status) }}
                    </span>
                  </td>
                  <td class="px-4 py-2.5 text-gray-500 text-xs" @click.stop>
                    {{ d.created_at ? new Date(d.created_at).toLocaleString('zh-CN') : '—' }}
                  </td>
                  <td class="px-4 py-2.5" @click.stop>
                    <div class="flex items-center gap-1">
                      <button
                        class="flex items-center gap-1 text-xs text-gray-400 hover:text-blue-400 transition-colors"
                        @click="toggleChunks(d)"
                      >
                        分块
                      </button>
                      <button
                        class="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-40"
                        :disabled="docDeleting === d.doc_id"
                        @click="onDeleteDocument(d)"
                      >
                        <Loader2 v-if="docDeleting === d.doc_id" class="w-3 h-3 animate-spin" />
                        <Trash2 v-else class="w-3 h-3" />
                      </button>
                    </div>
                  </td>
                </tr>
                <!-- Chunk 展开面板 -->
                <tr v-if="expandedDocId === d.doc_id" class="bg-surface-800/30">
                  <td :colspan="8" class="px-4 py-0">
                    <div class="rounded-md border border-white/10 bg-surface-800/80 my-2 overflow-hidden">
                      <!-- Chunk 面板头部 -->
                      <div class="flex items-center justify-between px-3 py-2 border-b border-white/5 bg-surface-800">
                        <span class="text-xs text-gray-300">
                          共 <span class="text-brand-400 font-medium">{{ chunkTotal }}</span> 个分块
                          <span v-if="chunkTotal > 50" class="text-gray-500 ml-1">(仅显示前 50 条)</span>
                        </span>
                        <div class="flex items-center gap-2">
                          <button
                            class="text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-40"
                            :disabled="!chunks.some((c: any) => c._selected)"
                            @click="onDeleteSelectedChunks"
                          >
                            删除选中
                          </button>
                          <button
                            class="text-xs text-gray-400 hover:text-gray-200 transition-colors"
                            :disabled="chunksLoading"
                            @click="loadChunks(d)"
                          >
                            <RefreshCw :class="['w-3 h-3', chunksLoading && 'animate-spin']" />
                          </button>
                        </div>
                      </div>
                      <!-- Loading -->
                      <div v-if="chunksLoading" class="flex items-center justify-center py-4 text-xs text-gray-500">
                        <Loader2 class="w-3 h-3 animate-spin mr-2" />
                        加载 chunk...
                      </div>
                      <!-- Empty -->
                      <div v-else-if="chunks.length === 0" class="text-center py-4 text-xs text-gray-600">
                        暂无分块数据
                      </div>
                      <!-- Chunk 列表 -->
                      <div v-else class="max-h-[320px] overflow-y-auto divide-y divide-white/5">
                        <div
                          v-for="c in chunks"
                          :key="c.doc_id"
                          class="flex items-start gap-2 px-3 py-2 hover:bg-surface-700/30 transition-colors"
                        >
                          <input
                            type="checkbox"
                            class="mt-1 w-3 h-3 rounded border-gray-600 bg-surface-700 text-brand-500 focus:ring-brand-400"
                            :checked="!!(c as any)._selected"
                            @change="(e: any) => (c as any)._selected = e.target.checked"
                          />
                          <div class="flex-1 min-w-0">
                            <div class="text-xs text-gray-500 mb-0.5 break-all font-mono">{{ (c as any).doc_id }}</div>
                            <div class="text-xs text-gray-300 line-clamp-2 leading-relaxed">{{ (c as any).content }}</div>
                          </div>
                          <button
                            class="mt-1 flex-shrink-0 text-xs text-red-400 hover:text-red-300 transition-colors disabled:opacity-40"
                            :disabled="chunkDeleting === (c as any).doc_id"
                            @click="onDeleteChunk((c as any).doc_id)"
                          >
                            <Loader2 v-if="chunkDeleting === (c as any).doc_id" class="w-3 h-3 animate-spin" />
                            <Trash2 v-else class="w-3 h-3" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ===== 文档统计区 ===== -->
      <div class="mt-8 border-t border-white/10 pt-4">
        <div class="flex items-center justify-between mb-3">
          <h3 class="text-base font-semibold text-white">知识库统计</h3>
          <button
            class="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-200 transition-colors"
            @click="loadKB"
          >
            <RefreshCw class="w-3.5 h-3.5" />
            刷新
          </button>
        </div>

        <div class="grid grid-cols-4 gap-3">
          <div class="rounded-lg border border-white/10 bg-surface-800 p-3 text-center">
            <div class="text-2xl font-bold text-brand-400">{{ docCount }}</div>
            <div class="text-xs text-gray-500 mt-1">文档数</div>
          </div>
          <div class="rounded-lg border border-white/10 bg-surface-800 p-3 text-center">
            <div class="text-2xl font-bold text-green-400">{{ chunkCount }}</div>
            <div class="text-xs text-gray-500 mt-1">分块数</div>
          </div>
          <div class="rounded-lg border border-white/10 bg-surface-800 p-3 text-center">
            <div class="text-2xl font-bold text-yellow-400">
              {{ kb.chunk_size ?? '-' }}
            </div>
            <div class="text-xs text-gray-500 mt-1">分块大小</div>
          </div>
          <div class="rounded-lg border border-white/10 bg-surface-800 p-3 text-center">
            <div class="text-2xl font-bold text-purple-400">
              {{ kb.chunk_overlap ?? '-' }}
            </div>
            <div class="text-xs text-gray-500 mt-1">重叠大小</div>
          </div>
        </div>
      </div>
    </template>

    <!-- 确认删除 KB 弹窗 -->
    <Teleport to="body">
      <div
        v-if="confirmDelete"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
        @click.self="confirmDelete = false"
      >
        <div class="bg-surface-800 rounded-xl border border-white/10 p-6 w-96 space-y-4">
          <div class="flex items-center gap-2 text-red-400">
            <AlertCircle class="w-5 h-5" />
            <span class="font-semibold">确认删除知识库？</span>
          </div>
          <p class="text-sm text-gray-400">
            知识库 "<span class="text-white">{{ kb?.name }}</span>" 及其所有文档和分块将被永久删除，无法恢复。
          </p>
          <div class="flex justify-end gap-3">
            <button
              class="rounded-lg border border-white/10 px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors"
              @click="confirmDelete = false"
            >
              取消
            </button>
            <button
              class="rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 transition-colors"
              @click="handleDeleteKB"
            >
              确认删除
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
input[type='file']::file-selector-button {
  display: none;
}
</style>
