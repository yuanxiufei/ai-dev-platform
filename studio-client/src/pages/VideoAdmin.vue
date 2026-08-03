<template>
  <div class="video-admin-page">
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">视频管理</h1>
        <span class="page-desc">管理所有视频、审核队列与数据统计</span>
      </div>
    </header>

    <!-- Tab 切换 -->
    <nav class="tabs-nav">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        class="tab-btn"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </nav>

    <!-- ═══ Tab 1: 视频列表 ═══ -->
    <div v-if="activeTab === 'videos'" class="tab-content">
      <div class="toolbar">
        <div class="search-box">
          <Search :size="16" class="search-icon" />
          <input
            v-model="videoSearch"
            placeholder="搜索视频..."
            class="search-input"
            @keyup.enter="fetchVideos"
          />
        </div>
        <button class="btn-ghost" @click="fetchVideos">
          <RefreshCw :size="14" /> 刷新
        </button>
        <button class="btn-primary" @click="openVideoCreate">
          <Plus :size="16" /> 新建
        </button>
      </div>

      <div v-if="videoLoading" class="loading-state"><Loader :size="20" class="spinner" /> 加载中...</div>

      <table v-else-if="videos.length" class="video-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>标题</th>
            <th>标签</th>
            <th>时长</th>
            <th>播放</th>
            <th>审核</th>
            <th>公开</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in videos" :key="v.id">
            <td class="cell-id" :title="v.id">{{ v.id.slice(0, 8) }}...</td>
            <td class="cell-title">
              <div class="title-text">{{ v.title }}</div>
              <div v-if="v.description" class="title-desc">{{ v.description.slice(0, 60) }}{{ v.description.length > 60 ? '...' : '' }}</div>
            </td>
            <td>
              <div class="chip-row">
                <span v-for="t in (v.tags || [])" :key="t" class="chip">{{ t }}</span>
              </div>
            </td>
            <td>{{ v.duration ? `${Math.floor(v.duration / 60)}:${String(v.duration % 60).padStart(2, '0')}` : '-' }}</td>
            <td>{{ v.view_count }}</td>
            <td>
              <span :class="['status-dot', v.is_approved ? 'status-approved' : 'status-pending']" />
              {{ v.is_approved ? '已通过' : '待审核' }}
            </td>
            <td>
              <span :class="['status-dot', v.is_public ? 'status-approved' : 'status-pending']" />
              {{ v.is_public ? '公开' : '私有' }}
            </td>
            <td>
              <div class="action-btns">
                <button class="btn-sm" @click="openVideoEdit(v)"><Pencil :size="13" /></button>
                <button class="btn-sm btn-sm-danger" @click="handleVideoDelete(v)"><Trash2 :size="13" /></button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-else class="empty-state">暂无视频数据</div>

      <div v-if="videoTotal > videoPageSize" class="pagination">
        <button :disabled="videoPage <= 1" @click="videoPage--; fetchVideos()">上一页</button>
        <span class="page-info">{{ videoPage }} / {{ Math.ceil(videoTotal / videoPageSize) }}</span>
        <button :disabled="videoPage * videoPageSize >= videoTotal" @click="videoPage++; fetchVideos()">下一页</button>
      </div>
    </div>

    <!-- ═══ Tab 2: 审核队列 ═══ -->
    <div v-if="activeTab === 'moderation'" class="tab-content">
      <div class="toolbar">
        <span class="queue-count">待审核: {{ moderationQueue.length }} 个视频</span>
        <button class="btn-ghost" @click="fetchModerationQueue">
          <RefreshCw :size="14" /> 刷新
        </button>
      </div>

      <div v-if="modLoading" class="loading-state"><Loader :size="20" class="spinner" /> 加载中...</div>

      <div v-else-if="moderationQueue.length === 0" class="empty-state">
        <CheckCircle :size="32" class="empty-icon" />
        审核队列为空，所有视频已处理
      </div>

      <div v-else class="moderation-list">
        <div v-for="v in moderationQueue" :key="v.id" class="mod-card">
          <div class="mod-info">
            <h4>{{ v.title }}</h4>
            <p v-if="v.description" class="mod-desc">{{ v.description }}</p>
            <div class="mod-meta">
              <span>ID: {{ v.id.slice(0, 8) }}...</span>
              <span v-if="v.duration">时长: {{ Math.floor(v.duration / 60) }}:{{ String(v.duration % 60).padStart(2, '0') }}</span>
              <span>标签: {{ (v.tags || []).join(', ') || '无' }}</span>
            </div>
          </div>
          <div class="mod-actions">
            <button class="btn-approve" @click="handleApprove(v)"><Check :size="14" /> 通过</button>
            <button class="btn-reject" @click="handleReject(v)"><X :size="14" /> 拒绝</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Tab 3: 数据分析 ═══ -->
    <div v-if="activeTab === 'analytics'" class="tab-content">
      <div class="toolbar">
        <h3 class="section-title">数据概览</h3>
        <button class="btn-ghost" @click="fetchAnalytics"><RefreshCw :size="14" /> 刷新</button>
      </div>

      <div v-if="analyticsLoading" class="loading-state"><Loader :size="20" class="spinner" /> 加载中...</div>

      <div v-else-if="analytics" class="analytics-grid">
        <div class="stat-card">
          <div class="stat-value">{{ analytics.total_videos ?? '-' }}</div>
          <div class="stat-label">总视频数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ analytics.total_views ?? '-' }}</div>
          <div class="stat-label">总播放量</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ analytics.avg_duration ? `${(analytics.avg_duration / 60).toFixed(1)}min` : '-' }}</div>
          <div class="stat-label">平均时长</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ analytics.public_videos ?? '-' }}</div>
          <div class="stat-label">公开视频</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ analytics.pending_review ?? '-' }}</div>
          <div class="stat-label">待审核</div>
        </div>
      </div>

      <!-- 每日趋势 -->
      <div v-if="trends.length" class="trends-section">
        <h3 class="section-title">每日播放趋势</h3>
        <table class="trend-table">
          <thead>
            <tr><th>日期</th><th>播放量</th><th>新增视频</th><th>总观看</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in trends" :key="t.date">
              <td>{{ t.date }}</td>
              <td>{{ t.views ?? 0 }}</td>
              <td>{{ t.new_videos ?? 0 }}</td>
              <td>{{ t.total_views ?? 0 }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ═══ 视频编辑弹窗 ═══ -->
    <div v-if="showVideoEditor" class="modal-overlay" @click.self="closeVideoEditor">
      <div class="modal-content modal-md">
        <div class="modal-header">
          <h2>{{ videoEditing ? '编辑视频' : '新建视频' }}</h2>
          <button class="btn-close" @click="closeVideoEditor">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-row">
            <label class="form-label">标题 <span class="required">*</span></label>
            <input v-model="videoForm.title" class="form-input" placeholder="视频标题" />
          </div>
          <div class="form-row">
            <label class="form-label">描述</label>
            <textarea v-model="videoForm.description" class="form-textarea" rows="2" placeholder="视频描述" />
          </div>
          <div class="form-row">
            <label class="form-label">文件路径 <span class="required">*</span></label>
            <input v-model="videoForm.file_path" class="form-input" placeholder="/data/videos/xxx.mp4" />
          </div>
          <div class="form-row">
            <label class="form-label">缩略图路径</label>
            <input v-model="videoForm.thumbnail_path" class="form-input" placeholder="/data/thumbnails/xxx.jpg" />
          </div>
          <div class="form-row form-row-2col">
            <div class="form-col">
              <label class="form-label">时长 (秒)</label>
              <input v-model.number="videoForm.duration" type="number" class="form-input" placeholder="120" />
            </div>
            <div class="form-col">
              <label class="form-label">标签 (逗号分隔)</label>
              <input v-model="videoTagsInput" class="form-input" placeholder="tutorial, demo" />
            </div>
          </div>
          <div class="form-row form-row-2col form-checks">
            <label class="form-check-label">
              <input v-model="videoForm.is_public" type="checkbox" /> 公开
            </label>
            <label class="form-check-label">
              <input v-model="videoForm.is_approved" type="checkbox" /> 已审核
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="closeVideoEditor">取消</button>
          <button class="btn-primary" :disabled="!videoForm.title || !videoForm.file_path" @click="handleVideoSave">
            {{ videoEditing ? '保存修改' : '创建视频' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Toast -->
    <div v-if="toast" class="toast" :class="toast.type">{{ toast.message }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from "vue"
import {
  Search, RefreshCw, Loader, Plus, Pencil, Trash2,
  CheckCircle, Check, X,
} from "lucide-vue-next"
import {
  listVideosAdmin, createVideo, getVideoAdmin, updateVideo, deleteVideo,
  getModerationQueue, approveVideo, rejectVideo,
  getAnalyticsOverview, getDailyTrends,
  type VideoAsset,
} from "@/api/video"

// ── Tabs ─────────────────────────────────────────────

const activeTab = ref<"videos" | "moderation" | "analytics">("videos")
const tabs = [
  { id: "videos" as const, label: "视频列表" },
  { id: "moderation" as const, label: "审核队列" },
  { id: "analytics" as const, label: "数据分析" },
]

// ── Video List ───────────────────────────────────────

const videos = ref<VideoAsset[]>([])
const videoLoading = ref(false)
const videoSearch = ref("")
const videoPage = ref(1)
const videoPageSize = 20
const videoTotal = ref(0)

async function fetchVideos() {
  videoLoading.value = true
  try {
    const res = await listVideosAdmin(videoPage.value, videoPageSize, videoSearch.value || undefined)
    videos.value = res.data.data
    videoTotal.value = res.data.total
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载视频列表失败", "error")
  } finally {
    videoLoading.value = false
  }
}

// ── Video CRUD ───────────────────────────────────────

const showVideoEditor = ref(false)
const videoEditing = ref(false)
const editingVideoId = ref<string | null>(null)

const videoForm = reactive({
  title: "",
  description: "",
  file_path: "",
  thumbnail_path: "",
  duration: undefined as number | undefined,
  is_public: false,
  is_approved: false,
  tags: [] as string[],
})
const videoTagsInput = ref("")

function openVideoCreate() {
  videoEditing.value = false
  editingVideoId.value = null
  resetVideoForm()
  showVideoEditor.value = true
}

async function openVideoEdit(v: VideoAsset) {
  videoEditing.value = true
  editingVideoId.value = v.id
  try {
    const res = await getVideoAdmin(v.id)
    const d = res.data
    videoForm.title = d.title
    videoForm.description = d.description || ""
    videoForm.file_path = d.file_path
    videoForm.thumbnail_path = d.thumbnail_path || ""
    videoForm.duration = d.duration ?? undefined
    videoForm.is_public = d.is_public
    videoForm.is_approved = d.is_approved
    videoForm.tags = d.tags || []
    videoTagsInput.value = (d.tags || []).join(", ")
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载视频详情失败", "error")
    return
  }
  showVideoEditor.value = true
}

function closeVideoEditor() {
  showVideoEditor.value = false
}

function resetVideoForm() {
  videoForm.title = ""
  videoForm.description = ""
  videoForm.file_path = ""
  videoForm.thumbnail_path = ""
  videoForm.duration = undefined
  videoForm.is_public = false
  videoForm.is_approved = false
  videoForm.tags = []
  videoTagsInput.value = ""
}

function syncVideoTagsArray() {
  videoForm.tags = videoTagsInput.value
    .split(",")
    .map(s => s.trim())
    .filter(Boolean)
}

async function handleVideoSave() {
  syncVideoTagsArray()
  try {
    if (videoEditing.value && editingVideoId.value) {
      await updateVideo(editingVideoId.value, {
        title: videoForm.title,
        description: videoForm.description || undefined,
        tags: videoForm.tags.length ? videoForm.tags : undefined,
        is_public: videoForm.is_public,
        is_approved: videoForm.is_approved,
      })
      showToast("视频已更新")
    } else {
      await createVideo({
        title: videoForm.title,
        description: videoForm.description || undefined,
        file_path: videoForm.file_path,
        thumbnail_path: videoForm.thumbnail_path || undefined,
        duration: videoForm.duration,
        tags: videoForm.tags.length ? videoForm.tags : undefined,
        is_public: videoForm.is_public,
        is_approved: videoForm.is_approved,
      })
      showToast("视频已创建")
    }
    closeVideoEditor()
    fetchVideos()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "保存失败", "error")
  }
}

async function handleVideoDelete(v: VideoAsset) {
  if (!confirm(`确定删除视频 "${v.title}"？此操作不可恢复。`)) return
  try {
    await deleteVideo(v.id)
    showToast(`视频 "${v.title}" 已删除`)
    fetchVideos()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "删除失败", "error")
  }
}

// ── Moderation ───────────────────────────────────────

const moderationQueue = ref<VideoAsset[]>([])
const modLoading = ref(false)

async function fetchModerationQueue() {
  modLoading.value = true
  try {
    const res = await getModerationQueue()
    moderationQueue.value = res.data
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载审核队列失败", "error")
  } finally {
    modLoading.value = false
  }
}

async function handleApprove(v: VideoAsset) {
  try {
    await approveVideo(v.id)
    showToast(`视频 "${v.title}" 已审核通过`)
    fetchModerationQueue()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "审核失败", "error")
  }
}

async function handleReject(v: VideoAsset) {
  const reason = prompt(`拒绝视频 "${v.title}"，请输入原因：`)
  if (reason === null) return
  try {
    await rejectVideo(v.id, reason || "不符合规范")
    showToast(`视频 "${v.title}" 已拒绝`)
    fetchModerationQueue()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "操作失败", "error")
  }
}

// ── Analytics ────────────────────────────────────────

const analytics = ref<any>(null)
const trends = ref<any[]>([])
const analyticsLoading = ref(false)

async function fetchAnalytics() {
  analyticsLoading.value = true
  try {
    const [overviewRes, trendsRes] = await Promise.all([
      getAnalyticsOverview(),
      getDailyTrends(),
    ])
    analytics.value = overviewRes.data
    trends.value = trendsRes.data
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载数据分析失败", "error")
  } finally {
    analyticsLoading.value = false
  }
}

// ── Tab Change ───────────────────────────────────────

import { watch } from "vue"
watch(activeTab, (tab) => {
  if (tab === "moderation") fetchModerationQueue()
  if (tab === "analytics") fetchAnalytics()
  if (tab === "videos") fetchVideos()
})

// ── Toast ────────────────────────────────────────────

const toast = ref<{ message: string; type: string } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(message: string, type = "success") {
  toast.value = { message, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 3000)
}

// ── Init ─────────────────────────────────────────────

onMounted(() => {
  fetchVideos()
})
</script>

<style scoped>
/* ── Layout ── */
.video-admin-page {
  padding: 24px 32px;
  height: 100%;
  overflow-y: auto;
  background: var(--color-ide-bg);
  color: var(--color-ide-fg);
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.header-left { display: flex; flex-direction: column; gap: 4px; }
.page-title { margin: 0; font-size: 22px; font-weight: 600; }
.page-desc { font-size: 13px; color: var(--color-ide-fg-muted); }
.section-title { margin: 0 0 12px 0; font-size: 14px; font-weight: 600; }

/* ── Tabs ── */
.tabs-nav {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-ide-border);
  margin-bottom: 20px;
}

.tab-btn {
  padding: 10px 20px;
  border: none;
  background: transparent;
  color: var(--color-ide-fg-muted);
  font-size: 14px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}
.tab-btn:hover { color: var(--color-ide-fg); }
.tab-btn.active {
  color: var(--color-ide-accent);
  border-bottom-color: var(--color-ide-accent);
}

/* ── Toolbar ── */
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.search-box { position: relative; flex: 1; max-width: 300px; }
.search-icon { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--color-ide-fg-muted); }
.search-input {
  width: 100%; padding: 8px 12px 8px 32px;
  border: 1px solid var(--color-ide-border); border-radius: 6px;
  background: var(--color-ide-bg-input); color: var(--color-ide-fg);
  font-size: 13px; outline: none;
}
.search-input:focus { border-color: var(--color-ide-accent); }

.queue-count { font-size: 13px; color: var(--color-ide-fg-muted); }

/* ── Buttons ── */
.btn-primary {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 16px; border: none; border-radius: 6px;
  background: var(--color-ide-accent); color: #fff;
  font-size: 13px; cursor: pointer;
}
.btn-primary:hover { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-ghost {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 6px 12px; border: 1px solid var(--color-ide-border); border-radius: 6px;
  background: transparent; color: var(--color-ide-fg); font-size: 13px; cursor: pointer;
}
.btn-ghost:hover { background: var(--color-ide-bg-hover); }

.btn-sm {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border: 1px solid var(--color-ide-border); border-radius: 5px;
  background: transparent; color: var(--color-ide-fg); cursor: pointer;
}
.btn-sm:hover { background: var(--color-ide-bg-hover); }
.btn-sm-danger:hover { border-color: #ef4444; color: #ef4444; }

.btn-approve {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 8px 16px; border: 1px solid #22c55e; border-radius: 6px;
  background: transparent; color: #22c55e; font-size: 13px; cursor: pointer;
}
.btn-approve:hover { background: #22c55e; color: #fff; }

.btn-reject {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 8px 16px; border: 1px solid #ef4444; border-radius: 6px;
  background: transparent; color: #ef4444; font-size: 13px; cursor: pointer;
}
.btn-reject:hover { background: #ef4444; color: #fff; }

/* ── States ── */
.loading-state, .empty-state {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 60px 0; color: var(--color-ide-fg-muted); font-size: 13px;
}
.spinner { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.empty-icon { opacity: 0.3; }

/* ── Video Table ── */
.video-table {
  width: 100%; border-collapse: collapse; font-size: 13px;
}
.video-table th {
  text-align: left; padding: 10px 12px;
  border-bottom: 2px solid var(--color-ide-border);
  color: var(--color-ide-fg-muted); font-weight: 600;
}
.video-table td {
  padding: 10px 12px; border-bottom: 1px solid var(--color-ide-border);
  vertical-align: top;
}
.video-table tbody tr:hover { background: var(--color-ide-bg-hover); }

.cell-id { font-family: monospace; font-size: 12px; color: var(--color-ide-fg-muted); }
.title-text { font-weight: 500; }
.title-desc { font-size: 11px; color: var(--color-ide-fg-muted); margin-top: 2px; }

.chip-row { display: flex; flex-wrap: wrap; gap: 3px; }
.chip {
  padding: 1px 7px; border-radius: 4px;
  background: var(--color-ide-bg-hover); font-size: 11px;
}

.status-dot {
  display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 4px;
}
.status-approved { background: #22c55e; }
.status-pending { background: #f59e0b; }

.action-btns { display: flex; gap: 4px; }

/* ── Pagination ── */
.pagination {
  display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 20px;
}
.pagination button {
  padding: 6px 14px; border: 1px solid var(--color-ide-border); border-radius: 6px;
  background: transparent; color: var(--color-ide-fg); font-size: 13px; cursor: pointer;
}
.pagination button:hover:not(:disabled) { background: var(--color-ide-bg-hover); }
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--color-ide-fg-muted); }

/* ── Moderation ── */
.moderation-list { display: flex; flex-direction: column; gap: 8px; }

.mod-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border: 1px solid var(--color-ide-border); border-radius: 8px;
  background: var(--color-ide-bg-panel); gap: 16px;
}
.mod-info { flex: 1; min-width: 0; }
.mod-info h4 { margin: 0 0 4px 0; font-size: 14px; }
.mod-desc { margin: 0 0 6px 0; font-size: 12px; color: var(--color-ide-fg-muted); }
.mod-meta { display: flex; gap: 16px; font-size: 11px; color: var(--color-ide-fg-muted); }
.mod-actions { display: flex; gap: 8px; flex-shrink: 0; }

/* ── Analytics ── */
.analytics-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px;
  margin-bottom: 24px;
}
.stat-card {
  padding: 16px; border: 1px solid var(--color-ide-border); border-radius: 8px;
  background: var(--color-ide-bg-panel); text-align: center;
}
.stat-value { font-size: 24px; font-weight: 700; }
.stat-label { font-size: 12px; color: var(--color-ide-fg-muted); margin-top: 4px; }

.trend-table {
  width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px;
}
.trend-table th {
  text-align: left; padding: 8px 12px;
  border-bottom: 2px solid var(--color-ide-border); color: var(--color-ide-fg-muted);
}
.trend-table td { padding: 8px 12px; border-bottom: 1px solid var(--color-ide-border); }

/* ── Modal ── */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center; z-index: 100;
}
.modal-content {
  background: var(--color-ide-bg-panel); border: 1px solid var(--color-ide-border);
  border-radius: 10px; max-height: 85vh; overflow-y: auto; width: 90%;
}
.modal-md { max-width: 500px; }
.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid var(--color-ide-border);
}
.modal-header h2 { margin: 0; font-size: 17px; }
.btn-close {
  border: none; background: transparent; color: var(--color-ide-fg-muted);
  font-size: 20px; cursor: pointer; line-height: 1;
}
.btn-close:hover { color: var(--color-ide-fg); }
.modal-body { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.modal-footer {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 14px 20px; border-top: 1px solid var(--color-ide-border);
}

/* ── Form ── */
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-label { font-size: 12px; color: var(--color-ide-fg-muted); }
.required { color: #ef4444; }
.form-input, .form-textarea {
  width: 100%; padding: 7px 10px; border: 1px solid var(--color-ide-border);
  border-radius: 5px; background: var(--color-ide-bg-input); color: var(--color-ide-fg);
  font-size: 13px; outline: none; box-sizing: border-box;
}
.form-input:focus, .form-textarea:focus { border-color: var(--color-ide-accent); }
.form-textarea { resize: vertical; }
.form-row-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.form-col { display: flex; flex-direction: column; gap: 4px; }
.form-checks { flex-direction: row; gap: 16px; }
.form-check-label {
  display: flex; align-items: center; gap: 6px; font-size: 13px; cursor: pointer;
}

/* ── Toast ── */
.toast {
  position: fixed; bottom: 24px; right: 24px;
  padding: 10px 20px; border-radius: 6px; font-size: 13px; z-index: 200;
  animation: slideUp 0.25s ease;
}
.toast.success { background: #16a34a; color: #fff; }
.toast.error { background: #dc2626; color: #fff; }
@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
