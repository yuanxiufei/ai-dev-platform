<template>
  <div class="p-6">
    <div class="max-w-6xl mx-auto">
      <header class="mb-8 text-center">
        <h1 class="text-3xl font-bold text-white">🎬 视频工坊</h1>
        <p class="text-[var(--color-ide-text-dim)] mt-2">浏览、搜索、生成 AI 视频</p>
      </header>

      <!-- Tabs 切换 -->
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

      <!-- ==================== 浏览标签 ==================== -->
      <div v-if="activeTab === 'browse'">
        <!-- 搜索栏 -->
        <div class="flex flex-col sm:flex-row gap-3 mb-6">
          <div class="flex-1 relative">
            <input
              v-model="searchQuery"
              @keyup.enter="doSearch"
              class="w-full px-4 py-2.5 pl-10 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-[var(--color-ide-text-dim)] outline-none focus:border-brand-500/50"
              placeholder="搜索视频标题或描述..."
            />
            <span class="absolute left-3 top-2.5 text-[var(--color-ide-text-dim)] text-sm">🔍</span>
          </div>
          <select
            v-model="sortBy"
            @change="loadVideos"
            class="px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50"
          >
            <option value="newest">最新</option>
            <option value="popular">最热</option>
            <option value="longest">最长</option>
          </select>
          <select
            v-model="filterTag"
            @change="loadVideos"
            class="px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50"
          >
            <option value="">全部标签</option>
            <option v-for="tag in knownTags" :key="tag" :value="tag">{{ tag }}</option>
          </select>
        </div>

        <!-- 视频网格 -->
        <div v-if="loadingVideos" class="text-center py-12 text-[var(--color-ide-text-dim)]">
          <div class="animate-spin inline-block w-6 h-6 border-2 border-brand-500/30 border-t-brand-500 rounded-full mb-2"></div>
          <p class="text-sm">加载中...</p>
        </div>
        <div v-else-if="!videos.length" class="text-center py-12 text-[var(--color-ide-text-dim)]">
          <p class="text-4xl mb-3">📭</p>
          <p>暂无视频</p>
        </div>
        <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          <div
            v-for="video in videos"
            :key="video.id"
            @click="openPlayer(video)"
            class="group rounded-2xl bg-gray-900/50 border border-gray-800/50 overflow-hidden cursor-pointer hover:border-brand-500/30 hover:shadow-lg hover:shadow-brand-500/5 transition-all"
          >
            <!-- 缩略图 -->
            <div class="relative aspect-video bg-gray-800 flex items-center justify-center overflow-hidden">
              <img
                v-if="video.thumbnail"
                :src="video.thumbnail"
                :alt="video.title"
                class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
              />
              <span v-else class="text-3xl opacity-30">🎬</span>
              <div class="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center">
                <span class="w-12 h-12 rounded-full bg-white/80 text-black flex items-center justify-center text-lg opacity-0 group-hover:opacity-100 transition-opacity">▶</span>
              </div>
              <span v-if="video.duration" class="absolute bottom-2 right-2 px-2 py-0.5 rounded-md bg-black/70 text-xs text-white">{{ formatDuration(video.duration) }}</span>
            </div>
            <!-- 信息 -->
            <div class="p-4">
              <h3 class="text-sm font-medium text-white truncate">{{ video.title }}</h3>
              <p class="text-xs text-[var(--color-ide-text-dim)] mt-1 line-clamp-2">{{ video.description || '暂无描述' }}</p>
              <div class="flex items-center gap-3 mt-3 text-xs text-[var(--color-ide-text-dim)]">
                <span>👁 {{ video.views || 0 }}</span>
                <span v-if="video.status" class="px-2 py-0.5 rounded-full text-[10px] font-medium" :class="statusClass(video.status)">{{ video.status }}</span>
                <span v-if="video.tags?.length" class="flex gap-1">
                  <span v-for="tag in video.tags.slice(0, 2)" :key="tag" class="px-1.5 py-0.5 rounded-md bg-gray-800 text-[10px]">{{ tag }}</span>
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 分页 -->
        <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 mt-6">
          <button @click="goPage(page - 1)" :disabled="page <= 1" class="px-3 py-2 rounded-lg text-xs bg-gray-800 text-[var(--color-ide-text-dim)] hover:text-white disabled:opacity-30 transition-colors">上一页</button>
          <span v-for="p in visiblePages" :key="p" @click="goPage(p)" class="w-9 h-9 flex items-center justify-center rounded-lg text-xs cursor-pointer transition-colors" :class="p === page ? 'bg-brand-500/30 text-brand-300 font-medium' : 'bg-gray-800 text-[var(--color-ide-text-dim)] hover:text-white'">{{ p }}</span>
          <button @click="goPage(page + 1)" :disabled="page >= totalPages" class="px-3 py-2 rounded-lg text-xs bg-gray-800 text-[var(--color-ide-text-dim)] hover:text-white disabled:opacity-30 transition-colors">下一页</button>
        </div>
      </div>

      <!-- ==================== 生成标签 ==================== -->
      <div v-if="activeTab === 'generate'">
        <!-- 生成表单 -->
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-8">
          <h2 class="text-lg font-bold text-white mb-4">✨ 生成新视频</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">视频标题</label>
              <input v-model="genForm.title" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50" placeholder="输入视频标题" />
            </div>
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">风格 / 模式</label>
              <select v-model="genForm.style" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50">
                <option value="realistic">写实</option>
                <option value="anime">动漫</option>
                <option value="cinematic">电影感</option>
                <option value="abstract">抽象</option>
              </select>
            </div>
          </div>
          <div class="mb-4">
            <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">生成提示词</label>
            <textarea v-model="genForm.prompt" rows="4" class="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-[var(--color-ide-text-dim)] outline-none focus:border-brand-500/50 resize-none" placeholder="描述你想生成的视频内容..."></textarea>
          </div>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">时长 (秒)</label>
              <input v-model.number="genForm.duration" type="number" min="1" max="300" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50" />
            </div>
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">分辨率</label>
              <select v-model="genForm.resolution" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50">
                <option value="720p">720p</option>
                <option value="1080p">1080p</option>
                <option value="4k">4K</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">帧率</label>
              <select v-model="genForm.fps" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50">
                <option :value="24">24 fps</option>
                <option :value="30">30 fps</option>
                <option :value="60">60 fps</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-[var(--color-ide-text-dim)] mb-1 block">标签</label>
              <input v-model="genForm.tags" class="w-full px-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50" placeholder="用逗号分隔" />
            </div>
          </div>
          <button @click="submitGenerate" :disabled="generating || !genForm.prompt" class="w-full py-3 rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 text-white font-medium disabled:opacity-50 transition-all">
            {{ generating ? '⏳ 正在提交任务...' : '🚀 开始生成' }}
          </button>

          <!-- 生成任务状态 -->
          <div v-if="genTaskId" class="mt-4 p-4 rounded-xl bg-gray-800 border border-gray-700">
            <div class="flex items-center justify-between mb-2">
              <span class="text-sm text-white font-medium">任务 #{{ genTaskId }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full" :class="genTaskStatus === 'completed' ? 'bg-green-500/20 text-green-400' : genTaskStatus === 'failed' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'">{{ genTaskStatus === 'completed' ? '✅ 完成' : genTaskStatus === 'failed' ? '❌ 失败' : '⏳ 处理中' }}</span>
            </div>
            <div class="w-full bg-gray-700 rounded-full h-2 overflow-hidden">
              <div class="h-full rounded-full bg-gradient-to-r from-brand-500 to-purple-500 transition-all duration-500" :style="{ width: (genProgress * 100) + '%' }"></div>
            </div>
            <p class="text-xs text-[var(--color-ide-text-dim)] mt-2">{{ Math.round(genProgress * 100) }}%</p>
          </div>
        </div>

        <!-- 我的任务列表 -->
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-bold text-white">📋 我的任务</h2>
            <button @click="loadMyTasks" class="text-xs px-3 py-1.5 rounded-lg bg-gray-800 text-[var(--color-ide-text-dim)] hover:text-white transition-colors">刷新</button>
          </div>
          <div v-if="loadingTasks" class="text-center py-6 text-[var(--color-ide-text-dim)]">
            <div class="animate-spin inline-block w-5 h-5 border-2 border-brand-500/30 border-t-brand-500 rounded-full mb-1"></div>
            <p class="text-xs">加载任务列表...</p>
          </div>
          <div v-else-if="!myTasks.length" class="text-center py-8 text-[var(--color-ide-text-dim)]">
            <p class="text-3xl mb-2">📝</p>
            <p class="text-sm">还没有生成任务</p>
          </div>
          <div v-else class="space-y-2">
            <div v-for="task in myTasks" :key="task.task_id" class="flex items-center gap-3 px-4 py-3 rounded-xl bg-gray-800/50 border border-gray-700/30">
              <span class="flex-1 text-sm text-white truncate">{{ task.title || '未命名任务' }}</span>
              <span class="text-xs px-2 py-0.5 rounded-full" :class="task.status === 'completed' ? 'bg-green-500/20 text-green-400' : task.status === 'failed' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'">
                {{ task.status === 'completed' ? '完成' : task.status === 'failed' ? '失败' : task.status === 'running' ? '运行中' : '等待中' }}
              </span>
              <div class="w-20 bg-gray-700 rounded-full h-1.5 overflow-hidden">
                <div class="h-full rounded-full bg-brand-500" :style="{ width: ((task.progress || 0) * 100) + '%' }"></div>
              </div>
              <button @click="openTaskDetail(task.task_id)" class="text-xs px-2 py-1 rounded-lg bg-gray-700 text-[var(--color-ide-text-dim)] hover:text-white transition-colors">详情</button>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== 播放弹窗 ==================== -->
      <Teleport to="body">
        <div v-if="playingVideo" class="fixed inset-0 z-[9999] bg-black/80 flex items-center justify-center p-4" @click.self="closePlayer">
          <div class="w-full max-w-4xl bg-gray-950 rounded-2xl overflow-hidden shadow-2xl" @click.stop>
            <!-- 播放器头部 -->
            <div class="flex items-center justify-between px-6 py-4 border-b border-gray-800">
              <h2 class="text-lg font-bold text-white truncate">{{ playingVideo.title }}</h2>
              <button @click="closePlayer" class="w-8 h-8 flex items-center justify-center rounded-lg bg-gray-800 text-[var(--color-ide-text-dim)] hover:text-white transition-colors">✕</button>
            </div>
            <!-- 视频区域 -->
            <div class="aspect-video bg-black flex items-center justify-center relative">
              <div class="text-[var(--color-ide-text-dim)] text-center">
                <p class="text-5xl mb-3">🎬</p>
                <p class="text-sm">视频播放区域</p>
                <p v-if="playInfo?.url" class="text-xs mt-2">
                  <a :href="playInfo.url" target="_blank" class="text-brand-400 hover:underline">在外部浏览器打开</a>
                </p>
              </div>
            </div>
            <!-- 视频信息 -->
            <div class="p-6 space-y-3">
              <p class="text-sm text-[var(--color-ide-text)]">{{ playingVideo.description || '暂无描述' }}</p>
              <div class="flex items-center gap-4 text-xs text-[var(--color-ide-text-dim)]">
                <span>👁 {{ playingVideo.views }}</span>
                <span v-if="playingVideo.duration">⏱ {{ formatDuration(playingVideo.duration) }}</span>
                <span v-if="playingVideo.tags?.length">
                  <span v-for="tag in playingVideo.tags" :key="tag" class="ml-1 px-1.5 py-0.5 rounded-md bg-gray-800 text-[10px]">{{ tag }}</span>
                </span>
              </div>
              <!-- 字幕 -->
              <div v-if="subtitles.length" class="pt-3 border-t border-gray-800">
                <h3 class="text-xs font-medium text-[var(--color-ide-text-dim)] mb-2">📝 字幕</h3>
                <div v-for="sub in subtitles" :key="sub.id" class="flex items-center gap-2 text-xs py-1">
                  <span class="px-1.5 py-0.5 rounded bg-gray-800 text-[10px]">{{ sub.language }}</span>
                  <span class="text-[var(--color-ide-text-dim)] truncate">{{ sub.filename }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import {
  videoApi,
  type VideoItem,
} from '@/api/video'

// ==================== 通用状态 ====================
const tabs = [
  { id: 'browse', label: '📺 浏览视频' },
  { id: 'generate', label: '✨ 生成视频' },
]
const activeTab = ref<'browse' | 'generate'>('browse')
const knownTags = ['AI', '生成', '教育', '娱乐', '科技', '自然', '音乐', '动画', '教程']

// ==================== 浏览标签 ====================
const videos = ref<VideoItem[]>([])
const loadingVideos = ref(false)
const searchQuery = ref('')
const sortBy = ref('newest')
const filterTag = ref('')
const page = ref(1)
const pageSize = 12
const totalVideos = ref(0)
const totalPages = computed(() => Math.ceil(totalVideos.value / pageSize))
const visiblePages = computed(() => {
  const pages: number[] = []
  const t = totalPages.value
  if (t <= 7) {
    for (let i = 1; i <= t; i++) pages.push(i)
  } else {
    const start = Math.max(1, Math.min(page.value - 3, t - 6))
    for (let i = start; i < start + 7; i++) pages.push(i)
  }
  return pages
})

// ==================== 生成标签 ====================
const genForm = ref({
  title: '',
  prompt: '',
  style: 'realistic',
  duration: 10,
  resolution: '1080p',
  fps: 30,
  tags: '',
})
const generating = ref(false)
const genTaskId = ref('')
const genTaskStatus = ref('pending')
const genProgress = ref(0)
const myTasks = ref<any[]>([])
const loadingTasks = ref(false)

// ==================== 播放弹窗 ====================
const playingVideo = ref<VideoItem | null>(null)
const playInfo = ref<{ url?: string } | null>(null)
const subtitles = ref<any[]>([])

// ==================== 方法 ====================

// --- 浏览 ---
async function loadVideos() {
  loadingVideos.value = true
  try {
    const params: any = { page: page.value, size: pageSize, sort: sortBy.value }
    if (filterTag.value) params.tag = filterTag.value
    const res = await videoApi.browseVideos(params)
    videos.value = res.data.data || []
    totalVideos.value = res.data.total || 0
  } catch (e) {
    console.error('loadVideos failed:', e)
  } finally {
    loadingVideos.value = false
  }
}

async function doSearch() {
  page.value = 1
  if (!searchQuery.value.trim()) {
    return loadVideos()
  }
  loadingVideos.value = true
  try {
    const res = await videoApi.searchVideos(searchQuery.value.trim(), page.value, pageSize)
    videos.value = res.data.data || []
    totalVideos.value = res.data.total || 0
  } catch (e) {
    console.error('searchVideos failed:', e)
  } finally {
    loadingVideos.value = false
  }
}

function goPage(p: number) {
  if (p < 1 || p > totalPages.value) return
  page.value = p
  searchQuery.value ? doSearch() : loadVideos()
}

// --- 生成 ---
async function submitGenerate() {
  if (!genForm.prompt.value) return
  generating.value = true
  genTaskId.value = ''
  try {
    const res = await videoApi.generateVideo({
      title: genForm.value.title || '未命名视频',
      prompt: genForm.value.prompt,
      style: genForm.value.style,
      duration: genForm.value.duration,
      resolution: genForm.value.resolution,
      fps: genForm.value.fps,
      tags: genForm.value.tags ? genForm.value.tags.split(',').map(t => t.trim()).filter(Boolean) : [],
    })
    genTaskId.value = res.data.task_id
    // 轮询任务状态
    pollTaskStatus(genTaskId.value)
  } catch (e) {
    console.error('generateVideo failed:', e)
  } finally {
    generating.value = false
  }
}

function pollTaskStatus(taskId: string) {
  const interval = setInterval(async () => {
    try {
      const res = await videoApi.getTaskStatus(taskId)
      const d = res.data
      genTaskStatus.value = d.status
      genProgress.value = d.progress || 0
      if (d.status === 'completed' || d.status === 'failed') {
        clearInterval(interval)
        // 完成后刷新浏览列表
        if (d.status === 'completed') loadVideos()
      }
    } catch (e) {
      clearInterval(interval)
    }
  }, 2000)
}

async function loadMyTasks() {
  loadingTasks.value = true
  try {
    const res = await videoApi.listMyTasks()
    myTasks.value = res.data.data || res.data || []
  } catch (e) {
    console.error('loadMyTasks failed:', e)
  } finally {
    loadingTasks.value = false
  }
}

async function openTaskDetail(taskId: string) {
  try {
    const res = await videoApi.getTaskStatus(taskId)
    const d = res.data
    genTaskId.value = taskId
    genTaskStatus.value = d.status
    genProgress.value = d.progress || 0
    if (d.status !== 'completed' && d.status !== 'failed') {
      pollTaskStatus(taskId)
    }
    activeTab.value = 'generate'
  } catch (e) {
    console.error('openTaskDetail failed:', e)
  }
}

// --- 播放 ---
async function openPlayer(video: VideoItem) {
  playingVideo.value = video
  playInfo.value = null
  subtitles.value = []
  try {
    const res = await videoApi.getPlayInfo(video.id)
    playInfo.value = res.data
  } catch (e) { /* ignore */ }
  try {
    const res = await videoApi.getSubtitles(video.id)
    subtitles.value = res.data.subtitles || res.data.data || []
  } catch (e) { /* ignore */ }
}

function closePlayer() {
  playingVideo.value = null
  playInfo.value = null
  subtitles.value = []
}

// --- 工具 ---
function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

function statusClass(status: string): string {
  const map: Record<string, string> = {
    published: 'bg-green-500/20 text-green-400',
    processing: 'bg-yellow-500/20 text-yellow-400',
    draft: 'bg-gray-500/20 text-gray-400',
    rejected: 'bg-red-500/20 text-red-400',
  }
  return map[status] || 'bg-gray-500/20 text-gray-400'
}

// ==================== 生命周期 ====================
onMounted(() => {
  loadVideos()
  loadMyTasks()
})
</script>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
