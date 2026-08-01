<script setup lang="ts">
/**
 * 知识库检索命中测试页
 *
 * 借鉴 Dify hit-testing 模式：
 * - 左侧：查询输入 + 检索参数配置 (top_k, similarity_threshold)
 * - 右侧：命中结果面板（可展开/折叠的 chunk 卡片）
 * - 底部：历史查询记录表
 *
 * ...existing imports...
 */
import {
  computed, onMounted, ref, watch,
} from "vue"
import { useRoute, useRouter } from "vue-router"
import {
  type HitTestResponse,
  type HitTestResult,
  hitTestKnowledgeBase,
  type KnowledgeBaseDetail,
  getKnowledgeBase,
} from "@/api/rag"
import {
  ArrowLeft,
  Beaker,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Copy,
  FileText,
  History,
  Lightbulb,
  Loader2,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-vue-next"
import { useToast } from "@/composables/useToast"

/* ---------- 路由 & 状态 ---------- */

const route = useRoute()
const router = useRouter()
const kbId = route.params.id as string
const toast = useToast()

const kb = ref<KnowledgeBaseDetail | null>(null)
const loadingKb = ref(true)

/* ---------- 检索参数 ---------- */

const query = ref("")
const topK = ref(5)
const similarityThreshold = ref(0.0)
const searching = ref(false)
const hits = ref<HitTestResult[]>([])
const lastQuery = ref("")
const showAdvanced = ref(false)

/* ---------- 历史记录 (localStorage) ---------- */

interface HistoryItem {
  query: string
  kbId: string
  kbName: string
  topK: number
  threshold: number
  totalHits: number
  timestamp: string
}

const STORAGE_KEY = `hit-testing-history-${kbId}`

function loadHistory(): HistoryItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

const history = ref<HistoryItem[]>(loadHistory())

function saveHistory() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(history.value.slice(0, 50)))
}

function clearHistory() {
  history.value = []
  localStorage.removeItem(STORAGE_KEY)
}

/* ---------- 命中结果展开状态 ---------- */

const expandedHits = ref<Set<number>>(new Set())

function toggleHit(idx: number) {
  const s = new Set(expandedHits.value)
  if (s.has(idx)) s.delete(idx)
  else s.add(idx)
  expandedHits.value = s
}

/* ---------- KB 详情 ---------- */

onMounted(async () => {
  try {
    kb.value = (await getKnowledgeBase(kbId)).data
  } catch {
    toast.error("无法加载知识库信息")
  } finally {
    loadingKb.value = false
  }
})

/* ---------- 执行检索 ---------- */

async function doHitTest() {
  if (!query.value.trim() || searching.value) return
  searching.value = true

  try {
    const res = await hitTestKnowledgeBase(
      kbId,
      query.value.trim(),
      topK.value,
      similarityThreshold.value,
    )
    const data = res.data?.data ?? (res.data as unknown as HitTestResponse)
    hits.value = data?.hits ?? []
    lastQuery.value = query.value.trim()

    // 记录历史
    history.value.unshift({
      query: query.value.trim(),
      kbId,
      kbName: kb.value?.name ?? "",
      topK: topK.value,
      threshold: similarityThreshold.value,
      totalHits: hits.value.length,
      timestamp: new Date().toISOString(),
    })
    saveHistory()
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "检索请求失败"
    toast.error(msg)
    hits.value = []
  } finally {
    searching.value = false
  }
}

/* ---------- 恢复历史查询 ---------- */

function restoreHistory(item: HistoryItem) {
  query.value = item.query
  topK.value = item.topK
  similarityThreshold.value = item.threshold
}

/* ---------- 复制文本 ---------- */

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success("已复制到剪贴板")
  } catch {
    toast.error("复制失败")
  }
}

/* ---------- 工具函数 ---------- */

const formatScore = (score: number) => `${(score * 100).toFixed(1)}%`
const formatDate = (iso: string) => {
  const d = new Date(iso)
  return d.toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

const resultSummary = computed(() => {
  if (!lastQuery.value) return ""
  if (hits.value.length === 0) return "无命中结果"
  return `找到 ${hits.value.length} 个命中片段`
})

/* ---------- 快捷提示 ---------- */

const quickPrompts = [
  "请总结这个知识库的主要内容",
  "知识库中有哪些关键概念？",
  "最新添加的文档内容是什么？",
]
</script>

<template>
  <div class="h-full w-full flex flex-col overflow-hidden bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- 顶栏 -->
    <header
      class="flex items-center gap-3 px-5 py-3 border-b border-[var(--color-ide-border)] bg-[var(--color-ide-panel-bg)] shrink-0"
    >
      <button
        class="p-1.5 rounded-md hover:bg-[var(--color-ide-hover)] transition-colors"
        @click="router.push(`/knowledge/${kbId}`)"
      >
        <ArrowLeft :size="18" />
      </button>
      <Beaker :size="20" class="text-[var(--color-ide-accent)]" />
      <div class="flex-1 min-w-0">
        <h1 v-if="kb" class="text-base font-semibold truncate">
          {{ kb.name }} — 检索命中测试
        </h1>
        <h1 v-else class="text-base font-semibold">
          检索命中测试
        </h1>
      </div>
    </header>

    <!-- 主体：左右分栏 -->
    <div class="flex-1 flex overflow-hidden min-h-0">
      <!-- ===== 左面板：查询输入 ===== -->
      <aside
        class="w-[360px] shrink-0 flex flex-col border-r border-[var(--color-ide-border)] bg-[var(--color-ide-panel-bg)] overflow-y-auto"
      >
        <!-- 查询输入区 -->
        <div class="p-4 space-y-4">
          <!-- 搜索框 -->
          <div class="space-y-2">
            <label class="text-xs font-medium text-[var(--color-ide-text-secondary)]">
              检索查询
            </label>
            <textarea
              v-model="query"
              class="w-full min-h-[80px] max-h-[200px] px-3 py-2.5 text-sm rounded-lg border border-[var(--color-ide-border)] bg-[var(--color-ide-bg)] text-[var(--color-ide-text)] placeholder:text-[var(--color-ide-text-secondary)] resize-y focus:outline-none focus:ring-2 focus:ring-[var(--color-ide-accent)]/30 focus:border-[var(--color-ide-accent)]"
              placeholder="输入检索查询语句..."
              @keydown.ctrl.enter="doHitTest"
              @keydown.meta.enter="doHitTest"
            />
            <p class="text-[11px] text-[var(--color-ide-text-secondary)]">
              按 Ctrl+Enter 执行检索
            </p>
          </div>

          <!-- 快捷提示 -->
          <div v-if="!lastQuery && quickPrompts.length" class="space-y-1.5">
            <p class="text-xs text-[var(--color-ide-text-secondary)] flex items-center gap-1">
              <Lightbulb :size="12" /> 试试这些：
            </p>
            <button
              v-for="p in quickPrompts"
              :key="p"
              class="block w-full text-left text-xs px-2.5 py-1.5 rounded-md text-[var(--color-ide-text-secondary)] hover:bg-[var(--color-ide-hover)] hover:text-[var(--color-ide-text)] transition-colors truncate"
              @click="query = p"
            >
              {{ p }}
            </button>
          </div>

          <!-- 高级参数按钮 -->
          <button
            class="flex items-center gap-1.5 text-xs text-[var(--color-ide-text-secondary)] hover:text-[var(--color-ide-text)] transition-colors"
            @click="showAdvanced = !showAdvanced"
          >
            <SlidersHorizontal :size="14" />
            检索参数
            <ChevronDown v-if="!showAdvanced" :size="14" />
            <ChevronUp v-else :size="14" />
          </button>

          <!-- 高级参数面板 -->
          <div v-if="showAdvanced" class="space-y-3 p-3 rounded-lg bg-[var(--color-ide-bg)] border border-[var(--color-ide-border)]">
            <!-- Top-K -->
            <div class="space-y-1">
              <div class="flex items-center justify-between text-xs">
                <label class="text-[var(--color-ide-text-secondary)]">Top-K 结果数</label>
                <span class="font-mono text-[var(--color-ide-accent)]">{{ topK }}</span>
              </div>
              <input
                v-model.number="topK"
                type="range"
                min="1"
                max="20"
                step="1"
                class="w-full accent-[var(--color-ide-accent)]"
              />
              <div class="flex justify-between text-[10px] text-[var(--color-ide-text-secondary)]">
                <span>1</span><span>20</span>
              </div>
            </div>

            <!-- 相似度阈值 -->
            <div class="space-y-1">
              <div class="flex items-center justify-between text-xs">
                <label class="text-[var(--color-ide-text-secondary)]">相似度阈值</label>
                <span class="font-mono text-[var(--color-ide-accent)]">{{ similarityThreshold.toFixed(2) }}</span>
              </div>
              <input
                v-model.number="similarityThreshold"
                type="range"
                min="0"
                max="1"
                step="0.05"
                class="w-full accent-[var(--color-ide-accent)]"
              />
              <div class="flex justify-between text-[10px] text-[var(--color-ide-text-secondary)]">
                <span>0</span><span>1</span>
              </div>
            </div>
          </div>

          <!-- 检索按钮 -->
          <button
            class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all duration-200"
            :class="[
              searching || !query.trim()
                ? 'bg-[var(--color-ide-border)] text-[var(--color-ide-text-secondary)] cursor-not-allowed'
                : 'bg-[var(--color-ide-accent)] text-white hover:opacity-90 active:scale-[0.98]',
            ]"
            :disabled="searching || !query.trim()"
            @click="doHitTest"
          >
            <Loader2 v-if="searching" :size="16" class="animate-spin" />
            <Search v-else :size="16" />
            {{ searching ? '检索中...' : '执行检索' }}
          </button>
        </div>

        <!-- 历史记录 -->
        <div v-if="history.length" class="border-t border-[var(--color-ide-border)]">
          <div class="flex items-center justify-between px-4 py-2.5">
            <span class="text-xs font-medium text-[var(--color-ide-text-secondary)] flex items-center gap-1.5">
              <History :size="13" /> 历史记录
            </span>
            <button
              class="text-[10px] text-[var(--color-ide-text-secondary)] hover:text-red-400 transition-colors flex items-center gap-1"
              @click="clearHistory"
            >
              <Trash2 :size="11" /> 清空
            </button>
          </div>
          <div class="px-2 pb-3 space-y-1 max-h-[240px] overflow-y-auto">
            <button
              v-for="(item, i) in history"
              :key="i"
              class="w-full text-left px-2.5 py-2 rounded-md hover:bg-[var(--color-ide-hover)] transition-colors group"
              @click="restoreHistory(item)"
            >
              <div class="flex items-start gap-2">
                <div class="flex-1 min-w-0">
                  <p class="text-xs text-[var(--color-ide-text)] truncate">{{ item.query }}</p>
                  <p class="text-[10px] text-[var(--color-ide-text-secondary)] mt-0.5">
                    {{ formatDate(item.timestamp) }}
                    · {{ item.totalHits }} 命中 · Top-{{ item.topK }}
                  </p>
                </div>
              </div>
            </button>
          </div>
        </div>
      </aside>

      <!-- ===== 右面板：命中结果 ===== -->
      <main class="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <!-- 结果头部 -->
        <div class="flex items-center justify-between px-5 py-3 border-b border-[var(--color-ide-border)] shrink-0">
          <div class="flex items-center gap-2 text-sm">
            <FileText :size="16" class="text-[var(--color-ide-accent)]" />
            <span v-if="loadingKb" class="text-[var(--color-ide-text-secondary)]">加载中...</span>
            <template v-else-if="lastQuery">
              <span class="text-[var(--color-ide-text-secondary)]">查询：</span>
              <span class="font-medium truncate max-w-[300px]">{{ lastQuery }}</span>
              <span class="text-xs text-[var(--color-ide-accent)] font-mono ml-1">
                {{ resultSummary }}
              </span>
            </template>
            <span v-else class="text-[var(--color-ide-text-secondary)]">
              输入查询并执行检索以查看命中结果
            </span>
          </div>
          <div v-if="lastQuery" class="flex items-center gap-2">
            <span class="text-xs text-[var(--color-ide-text-secondary)]">
              相似度阈值: {{ similarityThreshold.toFixed(2) }} | Top-K: {{ topK }}
            </span>
          </div>
        </div>

        <!-- 结果列表 -->
        <div v-if="!lastQuery" class="flex-1 flex items-center justify-center">
          <div class="text-center space-y-3">
            <BookOpen :size="40" class="mx-auto text-[var(--color-ide-text-secondary)] opacity-30" />
            <p class="text-sm text-[var(--color-ide-text-secondary)]">
              <template v-if="loadingKb">正在加载知识库...</template>
              <template v-else>在左侧输入查询语句并执行检索</template>
            </p>
          </div>
        </div>

        <div v-else-if="hits.length === 0" class="flex-1 flex items-center justify-center">
          <div class="text-center space-y-3">
            <Search :size="40" class="mx-auto text-[var(--color-ide-text-secondary)] opacity-30" />
            <p class="text-sm text-[var(--color-ide-text-secondary)]">没有找到匹配的文档片段</p>
            <p class="text-xs text-[var(--color-ide-text-secondary)]">
              尝试调整查询语句或降低相似度阈值
            </p>
          </div>
        </div>

        <div v-else class="flex-1 overflow-y-auto p-4 space-y-3">
          <div
            v-for="(hit, idx) in hits"
            :key="idx"
            class="rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-panel-bg)] overflow-hidden transition-all"
          >
            <!-- 命中头部：排名、分数、文档来源 -->
            <button
              class="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-[var(--color-ide-hover)]/50 transition-colors"
              @click="toggleHit(idx)"
            >
              <!-- 排名徽章 -->
              <div
                class="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold shrink-0"
                :class="[
                  idx === 0
                    ? 'bg-[var(--color-ide-accent)]/15 text-[var(--color-ide-accent)]'
                    : 'bg-[var(--color-ide-border)] text-[var(--color-ide-text-secondary)]',
                ]"
              >
                #{{ hit.rank || idx + 1 }}
              </div>

              <!-- 分数条 -->
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1">
                  <div
                    class="h-1.5 rounded-full shrink-0"
                    :class="[
                      hit.score >= 0.7
                        ? 'bg-green-500'
                        : hit.score >= 0.4
                          ? 'bg-yellow-500'
                          : 'bg-orange-400',
                    ]"
                    :style="{ width: `${Math.max(hit.score * 100, 4)}px`, maxWidth: '120px' }"
                  />
                  <span
                    class="text-xs font-mono font-medium"
                    :class="[
                      hit.score >= 0.7
                        ? 'text-green-500'
                        : hit.score >= 0.4
                          ? 'text-yellow-500'
                          : 'text-orange-400',
                    ]"
                  >
                    {{ formatScore(hit.score) }}
                  </span>
                </div>
                <p class="text-[11px] text-[var(--color-ide-text-secondary)] truncate">
                  {{ hit.source || hit.doc_id || '(未知来源)' }}
                </p>
              </div>

              <!-- 展开/收起 -->
              <ChevronDown
                v-if="expandedHits.has(idx)"
                :size="16"
                class="text-[var(--color-ide-text-secondary)] shrink-0"
              />
              <ChevronUp
                v-else
                :size="16"
                class="text-[var(--color-ide-text-secondary)] shrink-0"
              />
            </button>

            <!-- 命中详情：内容展开区 -->
            <div
              v-if="expandedHits.has(idx)"
              class="px-4 pb-4 pt-0 border-t border-[var(--color-ide-border)]"
            >
              <!-- 文档片段 -->
              <div class="mt-3 p-3 rounded-lg bg-[var(--color-ide-bg)] text-sm leading-relaxed whitespace-pre-wrap break-words text-[var(--color-ide-text)]">
                {{ hit.content }}
              </div>

              <!-- 操作栏 -->
              <div class="flex items-center justify-between mt-3">
                <span class="text-[10px] text-[var(--color-ide-text-secondary)] font-mono">
                  doc_id: {{ hit.doc_id?.slice(0, 16) }}{{ hit.doc_id?.length && hit.doc_id.length > 16 ? '…' : '' }}
                </span>
                <button
                  class="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs text-[var(--color-ide-text-secondary)] hover:bg-[var(--color-ide-hover)] hover:text-[var(--color-ide-text)] transition-colors"
                  @click="copyText(hit.content)"
                >
                  <Copy :size="12" />
                  复制内容
                </button>
              </div>

              <!-- 元数据 -->
              <div v-if="hit.metadata && Object.keys(hit.metadata).length" class="mt-3 p-2.5 rounded-lg bg-[var(--color-ide-bg)]/50 border border-[var(--color-ide-border)] text-[10px] font-mono text-[var(--color-ide-text-secondary)] space-y-1 max-h-[200px] overflow-y-auto">
                <div v-for="(val, key) in hit.metadata" :key="key" class="flex items-start gap-2">
                  <span class="text-[var(--color-ide-accent)] shrink-0">{{ key }}:</span>
                  <span class="break-all">{{ typeof val === 'object' ? JSON.stringify(val) : val }}</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 底部间距 -->
          <div class="h-4" />
        </div>
      </main>
    </div>
  </div>
</template>
