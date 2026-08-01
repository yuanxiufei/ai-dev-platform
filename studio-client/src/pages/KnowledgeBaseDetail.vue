<template>
  <div class="kb-detail">
    <!-- 返回按钮 -->
    <div class="kb-detail__header">
      <button class="kb-detail__back" @click="$router.push('/knowledge')">
        ← 返回知识库列表
      </button>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="kb-detail__loading">加载中...</div>

    <template v-else-if="kb">
      <!-- 知识库信息卡片 -->
      <div class="kb-detail__card">
        <div class="kb-detail__info">
          <h2 class="kb-detail__name">{{ kb.name }}</h2>
          <p v-if="kb.description" class="kb-detail__desc">{{ kb.description }}</p>
          <p v-if="kb.summary" class="kb-detail__summary">{{ kb.summary }}</p>
          <div class="kb-detail__meta">
            <span>文档 {{ kb.stats?.documents ?? kb.document_count ?? 0 }}</span>
            <span>分块 {{ kb.stats?.chunks ?? kb.chunk_count ?? 0 }}</span>
            <span>策略 {{ kb.chunk_strategy || "default" }}</span>
            <span>大小 {{ kb.chunk_size || 500 }}</span>
          </div>
        </div>
        <div class="kb-detail__actions">
          <button
            class="kb-detail__btn kb-detail__btn--primary"
            :disabled="retraining"
            @click="doRetrain"
          >
            {{ retraining ? "训练中..." : "重新训练" }}
          </button>
          <button
            class="kb-detail__btn kb-detail__btn--outline"
            @click="$router.push(`/knowledge/${kbId}/hit-test`)"
          >
            🔬 检索命中测试
          </button>
          <button
            class="kb-detail__btn kb-detail__btn--danger"
            @click="doDeleteKb"
          >
            删除知识库
          </button>
        </div>
      </div>

      <!-- Retrain 进度 -->
      <div v-if="wsProgress" class="kb-detail__progress">
        <div class="kb-detail__progress-bar">
          <div
            class="kb-detail__progress-fill"
            :style="{ width: (wsProgress.total > 0 ? (wsProgress.done / wsProgress.total) * 100 : 0) + '%' }"
          />
        </div>
        <p class="kb-detail__progress-text">
          {{ wsProgress.message }} ({{ wsProgress.done }}/{{ wsProgress.total }})
        </p>
      </div>

      <!-- Tab 导航 -->
      <div class="kb-detail__tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['kb-detail__tab', { 'kb-detail__tab--active': activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
        </button>
      </div>

      <!-- Tab: 文档列表 -->
      <div v-if="activeTab === 'documents'" class="kb-detail__panel">
        <div class="kb-detail__panel-header">
          <span class="kb-detail__panel-title">已有文档 ({{ docTotal }})</span>
          <label class="kb-detail__file-label" v-if="singleFile">
            单文件上传: <input type="file" accept=".txt,.md,.pdf,.html,.htm,.json,.csv,.docx" @change="doUploadFile" />
          </label>
          <div class="kb-detail__panel-actions">
            <label class="kb-detail__file-btn kb-detail__btn--small">
              上传单个文件
              <input type="file" accept=".txt,.md,.pdf,.html,.htm,.json,.csv,.docx" hidden @change="doUploadFile" />
            </label>
          </div>
        </div>

        <!-- 文档表格 -->
        <table v-if="documents.length > 0" class="kb-detail__table">
          <thead>
            <tr>
              <th>文档名</th>
              <th>类型</th>
              <th>大小</th>
              <th>分块数</th>
              <th>上传时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="doc in documents"
              :key="doc.doc_id"
              :class="{ 'kb-detail__row--expanded': expandedDoc === doc.doc_id }"
            >
              <td class="kb-detail__doc-name" @click="toggleDoc(doc.doc_id)">
                {{ doc.doc_name }}
              </td>
              <td>{{ doc.file_type }}</td>
              <td>{{ formatSize(doc.file_size) }}</td>
              <td>{{ doc.chunk_count }}</td>
              <td>{{ formatTime(doc.created_at) }}</td>
              <td class="kb-detail__doc-actions">
                <button
                  class="kb-detail__btn--small-text"
                  @click="toggleDoc(doc.doc_id)"
                >
                  {{ expandedDoc === doc.doc_id ? "收起分块" : "查看分块" }}
                </button>
                <button class="kb-detail__btn--small-text kb-detail__btn--danger-text" @click="doDeleteDoc(doc.doc_id)">
                  删除
                </button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="kb-detail__empty">暂无文档</div>

        <!-- 分块面板 -->
        <div v-if="expandedDoc" class="kb-detail__chunks-layout">
          <div class="kb-detail__chunks-panel">
            <div class="kb-detail__chunks-header">
              <span>分块列表 (共 {{ chunkTotal }} 条)</span>
            <div class="kb-detail__chunks-actions">
              <button
                v-if="selectedChunks.size > 0"
                class="kb-detail__btn--small kb-detail__btn--danger-text"
                @click="doDeleteSelectedChunks"
              >
                删除已选 ({{ selectedChunks.size }})
              </button>
              <select v-model="chunkSize" @change="loadChunks">
                <option :value="20">20条/页</option>
                <option :value="50">50条/页</option>
              </select>
            </div>
          </div>
          <div v-if="chunks.length > 0" class="kb-detail__chunks-list">
            <div
              v-for="(chunk, idx) in chunks"
              :key="idx"
              class="kb-detail__chunk-item"
            >
              <input
                type="checkbox"
                :checked="selectedChunks.has(String(chunk.metadata._id || idx))"
                @change="toggleChunk(String(chunk.metadata._id || idx))"
              />
              <div class="kb-detail__chunk-content">
                <code class="kb-detail__chunk-text">{{ chunk.content }}</code>
                <div v-if="chunk.metadata._doc_id" class="kb-detail__chunk-meta">
                  文档: {{ chunk.metadata._doc_id }}
                </div>
              </div>
            </div>
          </div>
          <div v-else class="kb-detail__empty">暂无分块</div>
          <div v-if="chunkTotal > chunkSize" class="kb-detail__chunks-pager">
            <button :disabled="chunkPage <= 1" @click="chunkPage--; loadChunks()">
              上一页
            </button>
            <span>{{ chunkPage }} / {{ Math.ceil(chunkTotal / chunkSize) }}</span>
            <button
              :disabled="chunkPage >= Math.ceil(chunkTotal / chunkSize)"
              @click="chunkPage++; loadChunks()"
            >
              下一页
            </button>
          </div>
        </div>
        <!-- 结构树侧边栏 — 借鉴 RAGFlow 文档结构树 -->
        <div v-if="structureTree" class="kb-detail__structure-panel">
          <div class="kb-detail__chunks-header">
            <span>📑 文档结构</span>
          </div>
          <div class="kb-detail__structure-tree">
            <StructureTreeNode
              v-for="(node, i) in structureTree"
              :key="i"
              :node="node"
            />
          </div>
        </div>
        <div v-else-if="structureLoading" class="kb-detail__structure-panel kb-detail__structure-panel--loading">
          加载结构中...
        </div>
      </div>

      <!-- Tab: 批量上传 -->
      <div v-if="activeTab === 'batch-upload'" class="kb-detail__panel">
        <FileUploader
          accept=".txt,.md,.pdf,.html,.htm,.json,.csv,.docx,.pptx,.doc,.xlsx,.xls,.png,.jpg,.jpeg,.gif,.webp,.svg,.bmp"
          :max-size-mb="10"
          :on-upload="doUploadFiles"
          @complete="onUploadComplete"
        />
      </div>

      <!-- Tab: 网站导入 -->
      <div v-if="activeTab === 'site-import'" class="kb-detail__panel">
        <label class="kb-detail__label">Sitemap URL</label>
        <input
          v-model="sitemapUrl"
          class="kb-detail__input"
          placeholder="https://example.com/sitemap.xml"
        />
        <label class="kb-detail__label">或直接输入 URL 列表（每行一个）</label>
        <textarea
          v-model="urlList"
          class="kb-detail__textarea"
          rows="5"
          placeholder="https://example.com/page1&#10;https://example.com/page2"
        />
        <div class="kb-detail__form-row">
          <label class="kb-detail__label">最大页数</label>
          <input v-model.number="siteMaxPages" class="kb-detail__input kb-detail__input--small" type="number" min="1" max="500" />
        </div>
        <button
          class="kb-detail__btn kb-detail__btn--primary"
          :disabled="siteImporting"
          @click="doImportSite"
        >
          {{ siteImporting ? "正在导入..." : "开始导入" }}
        </button>
        <div v-if="siteResult" class="kb-detail__import-result">
          <h4>导入结果</h4>
          <p>站点: {{ siteResult.base_domain }}</p>
          <p>抓取成功: {{ siteResult.crawled_ok }} / 失败: {{ siteResult.crawled_fail }}</p>
          <p>导入: {{ siteResult.imported }}</p>
          <div v-if="siteResult.import_errors?.length">
            <p class="kb-detail__error-text">错误:</p>
            <ul>
              <li v-for="(e, i) in siteResult.import_errors" :key="i">{{ e }}</li>
            </ul>
          </div>
        </div>
      </div>
    </template>

    <!-- 错误 -->
    <div v-else class="kb-detail__error">知识库不存在或加载失败</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import {
  getKnowledgeBase,
  deleteKnowledgeBase,
  type KnowledgeBaseDetail,
} from "@/api/rag"
import {
  listDocuments,
  deleteDocument,
  type KBDocument,
} from "@/api/rag"
import {
  batchUploadDocuments,
} from "@/api/rag"
import FileUploader from "@/components/FileUploader.vue"
import {
  listChunks,
  deleteChunks,
  type ChunkItem,
} from "@/api/rag"
import {
  importFromSite,
  type SiteImportResponse,
} from "@/api/rag"
import {
  getDocumentStructure,
  type StructureNode,
} from "@/api/rag"
import { retrainKb } from "@/api/rag"
import { useTrainingProgress } from "@/composables/useTrainingProgress"

const route = useRoute()
const router = useRouter()
const kbId = route.params.id as string

/* ========== KB 信息 ========== */
const loading = ref(true)
const kb = ref<KnowledgeBaseDetail | null>(null)

async function loadKb() {
  loading.value = true
  try {
    kb.value = (await getKnowledgeBase(kbId)).data
  } catch {
    kb.value = null
  } finally {
    loading.value = false
  }
}

/* ========== 删除 KB ========== */
async function doDeleteKb() {
  if (!confirm("确定要删除这个知识库吗？此操作不可撤销。")) return
  try {
    await deleteKnowledgeBase(kbId)
    router.push("/knowledge")
  } catch {
    alert("删除失败")
  }
}

/* ========== Retrain ========== */
const retraining = ref(false)
const { progress: wsProgress, connect: wsConnect, disconnect: wsDisconnect } =
  useTrainingProgress(kbId)

async function doRetrain() {
  retraining.value = true
  try {
    await retrainKb(kbId)
    // 打开 WebSocket 监听进度
    wsConnect()
  } catch {
    alert("重新训练失败")
  } finally {
    retraining.value = false
  }
}

watch(wsProgress, (p) => {
  if (p?.finished) {
    wsDisconnect()
    loadDocuments()
  }
})

/* ========== Tab ========== */
const tabs = [
  { key: "documents", label: "文档列表" },
  { key: "batch-upload", label: "批量上传" },
  { key: "site-import", label: "网站导入" },
]
const activeTab = ref("documents")

/* ========== 文档列表 ========== */
const documents = ref<KBDocument[]>([])
const docTotal = ref(0)

async function loadDocuments() {
  try {
    const res = await listDocuments(kbId)
    documents.value = res.data.data
    docTotal.value = res.data.total
  } catch {
    // ignore
  }
}

async function doDeleteDoc(docId: string) {
  if (!confirm("确定删除此文档？")) return
  try {
    await deleteDocument(kbId, docId)
    if (expandedDoc.value === docId) expandedDoc.value = null
    loadDocuments()
    loadKb()
  } catch {
    alert("删除文档失败")
  }
}

/* ========== 单个文件上传 ========== */
async function doUploadFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    // 复用 batch upload API
    const res = await batchUploadDocuments(kbId, [file])
    alert("上传完成")
    loadDocuments()
    loadKb()
  } catch {
    alert("上传失败")
  }
  input.value = ""
}

/* ========== 分块面板 ========== */
const expandedDoc = ref<string | null>(null)
const chunks = ref<ChunkItem[]>([])
const chunkTotal = ref(0)
const chunkPage = ref(1)
const chunkSize = ref(50)
const selectedChunks = ref(new Set<string>())

function toggleDoc(docId: string) {
  if (expandedDoc.value === docId) {
    expandedDoc.value = null
    chunks.value = []
    selectedChunks.value = new Set()
    structureTree.value = null
  } else {
    expandedDoc.value = docId
    chunkPage.value = 1
    selectedChunks.value = new Set()
    loadChunks()
    loadStructureTree(docId)
  }
}

async function loadChunks() {
  if (!expandedDoc.value) return
  try {
    const res = await listChunks(
      kbId,
      expandedDoc.value,
      chunkPage.value,
      chunkSize.value,
    )
    chunks.value = res.data.data
    chunkTotal.value = res.data.total
  } catch {
    // ignore
  }
}

function toggleChunk(id: string) {
  const next = new Set(selectedChunks.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  selectedChunks.value = next
}

async function doDeleteSelectedChunks() {
  if (selectedChunks.value.size === 0) return
  if (!confirm(`确定删除 ${selectedChunks.value.size} 个分块？`)) return
  try {
    await deleteChunks(kbId, Array.from(selectedChunks.value))
    selectedChunks.value = new Set()
    loadChunks()
    loadKb()
  } catch {
    alert("删除分块失败")
  }
}

/* ========== 文档结构树 ========== */
const structureTree = ref<StructureNode[] | null>(null)
const structureLoading = ref(false)

async function loadStructureTree(docId: string) {
  structureLoading.value = true
  structureTree.value = null
  try {
    const res = await getDocumentStructure(kbId, docId)
    structureTree.value = res.data?.data ?? null
  } catch {
    // ignore
  } finally {
    structureLoading.value = false
  }
}

/* ========== 批量上传 (增强版 FileUploader) ========== */

async function doUploadFiles(files: File[]): Promise<{ ok: number; errors: { filename: string; error: string }[] }> {
  const res = await batchUploadDocuments(kbId, files)
  const ok = res.data.results.filter((r: { status: string }) => r.status === "ok").length
  const errors = res.data.results
    .filter((r: { status: string }) => r.status === "fail")
    .map((r: { filename: string; error?: string }) => ({ filename: r.filename, error: r.error ?? "未知错误" }))
  return { ok, errors }
}

function onUploadComplete(_result: { ok: number; errors: { filename: string; error: string }[] }) {
  loadDocuments()
  loadKb()
}

/* ========== 网站导入 ========== */
const sitemapUrl = ref("")
const urlList = ref("")
const siteMaxPages = ref(50)
const siteImporting = ref(false)
const siteResult = ref<SiteImportResponse | null>(null)

async function doImportSite() {
  if (!sitemapUrl.value && !urlList.value.trim()) {
    alert("请输入 sitemap URL 或 URL 列表")
    return
  }
  siteImporting.value = true
  siteResult.value = null
  try {
    const urls = urlList.value
      .split("\n")
      .map((u) => u.trim())
      .filter(Boolean)
    const res = await importFromSite(kbId, {
      sitemap_url: sitemapUrl.value || undefined,
      urls: urls.length > 0 ? urls : undefined,
      max_pages: siteMaxPages.value,
    })
    siteResult.value = res.data
    loadDocuments()
    loadKb()
  } catch {
    alert("网站导入失败")
  } finally {
    siteImporting.value = false
  }
}

/* ========== 工具函数 ========== */
const singleFile = ref(false)

function formatSize(bytes: number) {
  if (!bytes) return "0 B"
  const units = ["B", "KB", "MB", "GB"]
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024
    i++
  }
  return `${size.toFixed(1)} ${units[i]}`
}

function formatTime(ts: string | null) {
  if (!ts) return "-"
  return new Date(ts).toLocaleString("zh-CN")
}

/* ========== Init ========== */
onMounted(() => {
  loadKb()
  loadDocuments()
})
</script>

<style scoped>
/* ---- 复用 IDE 变量 ---- */
.kb-detail {
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
  color: var(--color-ide-fg);
}

.kb-detail__header {
  margin-bottom: 16px;
}

.kb-detail__back {
  background: none;
  border: 1px solid var(--color-ide-border);
  color: var(--color-ide-fg-secondary);
  padding: 6px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
}
.kb-detail__back:hover {
  background: var(--color-ide-bg-hover);
}

.kb-detail__loading,
.kb-detail__empty {
  text-align: center;
  padding: 48px;
  color: var(--color-ide-fg-secondary);
}
.kb-detail__error {
  text-align: center;
  padding: 48px;
  color: var(--color-ide-error);
}

/* ---- 信息卡片 ---- */
.kb-detail__card {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 24px;
  background: var(--color-ide-bg-secondary);
  border: 1px solid var(--color-ide-border);
  border-radius: 12px;
  margin-bottom: 16px;
}

.kb-detail__name {
  margin: 0 0 8px;
  font-size: 22px;
  color: var(--color-ide-fg);
}

.kb-detail__desc,
.kb-detail__summary {
  margin: 0 0 6px;
  color: var(--color-ide-fg-secondary);
  font-size: 14px;
}

.kb-detail__meta {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--color-ide-fg-secondary);
}

.kb-detail__actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
}

/* ---- 按钮 ---- */
.kb-detail__btn {
  padding: 8px 16px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  background: var(--color-ide-bg);
  color: var(--color-ide-fg);
  white-space: nowrap;
}
.kb-detail__btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.kb-detail__btn--primary {
  background: var(--color-ide-accent, #007acc);
  color: #fff;
  border-color: transparent;
}
.kb-detail__btn--danger {
  border-color: var(--color-ide-error);
  color: var(--color-ide-error);
}
.kb-detail__btn--outline {
  border-color: var(--color-ide-accent, #007acc);
  color: var(--color-ide-accent, #007acc);
}
.kb-detail__btn--outline:hover {
  background: var(--color-ide-accent, #007acc);
  color: #fff;
}
.kb-detail__btn--small {
  padding: 4px 10px;
  font-size: 12px;
}
.kb-detail__btn--small-text {
  background: none;
  border: 1px solid var(--color-ide-border);
  color: var(--color-ide-fg-secondary);
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
.kb-detail__btn--small-text:hover {
  background: var(--color-ide-bg-hover);
}
.kb-detail__btn--danger-text {
  color: var(--color-ide-error);
  border-color: var(--color-ide-error);
}
.kb-detail__file-btn {
  display: inline-block;
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid var(--color-ide-accent, #007acc);
  color: var(--color-ide-accent, #007acc);
  border-radius: 4px;
  cursor: pointer;
}
.kb-detail__file-btn:hover {
  background: var(--color-ide-bg-hover);
}

/* ---- 进度条 ---- */
.kb-detail__progress {
  margin-bottom: 16px;
  padding: 12px;
  background: var(--color-ide-bg-secondary);
  border-radius: 8px;
}
.kb-detail__progress-bar {
  height: 6px;
  background: var(--color-ide-border);
  border-radius: 3px;
  overflow: hidden;
}
.kb-detail__progress-fill {
  height: 100%;
  background: var(--color-ide-accent, #007acc);
  border-radius: 3px;
  transition: width 0.3s;
}
.kb-detail__progress-text {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-ide-fg-secondary);
}

/* ---- Tab ---- */
.kb-detail__tabs {
  display: flex;
  gap: 0;
  border-bottom: 2px solid var(--color-ide-border);
  margin-bottom: 16px;
}
.kb-detail__tab {
  padding: 10px 20px;
  border: none;
  background: none;
  color: var(--color-ide-fg-secondary);
  font-size: 14px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: color 0.15s, border-color 0.15s;
}
.kb-detail__tab--active {
  color: var(--color-ide-accent, #007acc);
  border-bottom-color: var(--color-ide-accent, #007acc);
}
.kb-detail__tab:hover {
  color: var(--color-ide-fg);
}

/* ---- Panel ---- */
.kb-detail__panel {
  background: var(--color-ide-bg-secondary);
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  padding: 16px;
}
.kb-detail__panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.kb-detail__panel-title {
  font-size: 16px;
  font-weight: 600;
}

/* ---- 表格 ---- */
.kb-detail__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.kb-detail__table th,
.kb-detail__table td {
  text-align: left;
  padding: 10px 8px;
  border-bottom: 1px solid var(--color-ide-border);
}
.kb-detail__table th {
  color: var(--color-ide-fg-secondary);
  font-weight: 600;
}
.kb-detail__doc-name {
  cursor: pointer;
  color: var(--color-ide-accent, #007acc);
}
.kb-detail__row--expanded td {
  background: var(--color-ide-bg-hover);
}
.kb-detail__doc-actions {
  display: flex;
  gap: 6px;
}

/* ---- 分块+结构树并排布局 ---- */
.kb-detail__chunks-layout {
  display: flex;
  gap: 12px;
}
.kb-detail__chunks-layout > .kb-detail__chunks-panel {
  flex: 1;
  min-width: 0;
}

/* ---- 结构树面板 ---- */
.kb-detail__structure-panel {
  width: 260px;
  flex-shrink: 0;
  padding: 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  background: var(--color-ide-bg);
  max-height: 480px;
  overflow-y: auto;
}
.kb-detail__structure-panel--loading {
  color: var(--color-ide-fg-secondary);
  font-size: 13px;
  text-align: center;
  padding-top: 24px;
}
.kb-detail__structure-tree {
  margin-top: 4px;
}

/* ---- 分块面板 ---- */
.kb-detail__chunks-panel {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  background: var(--color-ide-bg);
}
.kb-detail__chunks-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 600;
}
.kb-detail__chunks-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.kb-detail__chunks-list {
  max-height: 400px;
  overflow-y: auto;
}
.kb-detail__chunk-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  padding: 8px 0;
  border-bottom: 1px solid var(--color-ide-border);
  font-size: 12px;
}
.kb-detail__chunk-content {
  flex: 1;
  min-width: 0;
}
.kb-detail__chunk-text {
  display: block;
  white-space: pre-wrap;
  word-break: break-all;
  background: var(--color-ide-bg-secondary);
  padding: 6px 8px;
  border-radius: 4px;
  color: var(--color-ide-fg);
  max-height: 120px;
  overflow-y: auto;
}
.kb-detail__chunk-meta {
  margin-top: 4px;
  color: var(--color-ide-fg-secondary);
  font-size: 11px;
}
.kb-detail__chunks-pager {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  font-size: 13px;
}
.kb-detail__chunks-pager button {
  padding: 4px 12px;
  border: 1px solid var(--color-ide-border);
  background: var(--color-ide-bg);
  color: var(--color-ide-fg);
  border-radius: 4px;
  cursor: pointer;
}
.kb-detail__chunks-pager button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ---- 批量上传 ---- */
.kb-detail__upload-zone {
  text-align: center;
  padding: 32px;
  border: 2px dashed var(--color-ide-border);
  border-radius: 12px;
  color: var(--color-ide-fg-secondary);
}
.kb-detail__upload-zone input[type="file"] {
  margin: 12px 0;
}
.kb-detail__file-list {
  list-style: none;
  padding: 0;
  margin-top: 12px;
  text-align: left;
  font-size: 13px;
}
.kb-detail__file-list li {
  padding: 4px 0;
}
.kb-detail__batch-results {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  background: var(--color-ide-bg);
}
.kb-detail__result-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  font-size: 13px;
}
.kb-detail__result--ok {
  color: var(--color-ide-success, #4caf50);
}
.kb-detail__result--fail {
  color: var(--color-ide-error);
}
.kb-detail__error-text {
  color: var(--color-ide-error);
}

/* ---- 网站导入 ---- */
.kb-detail__label {
  display: block;
  margin-top: 12px;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 600;
}
.kb-detail__input {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  background: var(--color-ide-bg);
  color: var(--color-ide-fg);
  font-size: 13px;
  box-sizing: border-box;
}
.kb-detail__input--small {
  width: 120px;
}
.kb-detail__textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  background: var(--color-ide-bg);
  color: var(--color-ide-fg);
  font-size: 13px;
  resize: vertical;
  font-family: monospace;
  box-sizing: border-box;
}
.kb-detail__form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
}
.kb-detail__import-result {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  background: var(--color-ide-bg);
  font-size: 13px;
}
.kb-detail__import-result h4 {
  margin: 0 0 8px;
}
</style>
