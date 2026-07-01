/**
 * Video Store — 对接后端真实 API + WebSocket 实时进度
 *
 * 数据流：
 *   用户点击生成 → POST /videos/generate → 获取 task_id
 *                → WS /videos/generate/{task_id}/ws → 实时推送进度
 *   画廊页面    → GET /videos/generate/my → 用户任务列表
 *   公开探索    → GET /videos/browse → 已发布视频
 *   播放页      → GET /videos/{id}/play → 视频播放信息
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { generateVideo, getTaskStatus, listMyTasks, connectProgressWs } from '../api/videoApi'
import type { VideoItem, TaskStatus, WsProgressMessage } from '../types/video'

export type { VideoItem, TaskStatus }

export const useVideoStore = defineStore('video', () => {
  // ── State ──────────────────────────────────────
  const videos = ref<VideoItem[]>([])
  const isGenerating = ref(false)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  /** 当前活跃的 WebSocket 连接 (taskId → WebSocket) */
  const wsConnections = ref<Map<string, WebSocket>>(new Map())

  // ── Computed ────────────────────────────────────
  const completedVideos = computed(() => videos.value.filter(v => v.status === 'completed'))
  const generatingVideos = computed(() => videos.value.filter(v => v.status === 'generating'))
  const failedVideos = computed(() => videos.value.filter(v => v.status === 'failed'))

  // ── Actions ─────────────────────────────────────

  /** 从后端加载用户的任务列表 */
  async function fetchMyTasks(page = 1, size = 50) {
    isLoading.value = true
    error.value = null
    try {
      const res = await listMyTasks(page, size)
      // 合并到本地列表 (保留 WebSocket 实时更新的进度)
      const existingIds = new Map(videos.value.map(v => [v.taskId, v]))
      const merged: VideoItem[] = res.data.map(t => {
        const existing = existingIds.get(t.task_id)
        return {
          taskId: t.task_id,
          title: t.prompt?.slice(0, 40) || '未命名',
          prompt: t.prompt,
          status: t.status,
          progress: existing && (existing.status === 'generating') ? existing.progress : t.progress,
          thumbnailUrl: t.thumbnail_path || undefined,
          videoUrl: t.output_path || undefined,
          duration: t.duration,
          style: '',
          modelName: t.model_name,
          errorMessage: t.error_message,
          createdAt: t.created_at,
        }
      })
      videos.value = merged
    } catch (e: any) {
      error.value = e?.message || '加载失败'
    } finally {
      isLoading.value = false
    }
  }

  /** 发起视频生成 */
  async function startGeneration(
    prompt: string,
    style: string,
    durationSec: number,
  ): Promise<string | null> {
    isGenerating.value = true
    error.value = null

    try {
      const res = await generateVideo({
        prompt,
        style,
        num_frames: Math.min(durationSec * 8, 200),
        fps: 8,
      })

      const taskId = res.task_id

      // 创建本地条目
      const item: VideoItem = {
        taskId,
        title: prompt.slice(0, 40),
        prompt,
        status: 'pending',
        progress: 0,
        duration: durationSec,
        style,
        modelName: res.model_name,
        createdAt: new Date().toISOString(),
      }
      videos.value = [item, ...videos.value]

      // 连接 WebSocket 实时进度
      const token = localStorage.getItem('token')
      if (token) {
        connectWs(taskId, token)
      } else {
        // 无 token 时回退到轮询
        startPolling(taskId)
      }

      return taskId
    } catch (e: any) {
      error.value = e?.message || '生成失败'
      isGenerating.value = false
      return null
    }
  }

  /** 连接 WebSocket 监听实时进度 */
  function connectWs(taskId: string, token: string) {
    const ws = connectProgressWs(taskId, token)

    ws.onopen = () => {
      wsConnections.value.set(taskId, ws)
      updateVideo(taskId, { status: 'generating', progress: 5 })
    }

    ws.onmessage = (event) => {
      try {
        const msg: WsProgressMessage = JSON.parse(event.data)
        if (msg.error) {
          updateVideo(taskId, { status: 'failed', errorMessage: msg.error })
          closeWs(taskId)
          return
        }

        updateVideo(taskId, {
          status: msg.status,
          progress: msg.progress,
          videoUrl: msg.output_path || undefined,
          thumbnailUrl: msg.thumbnail_path || undefined,
          errorMessage: msg.error_message,
        })

        if (msg.done) {
          closeWs(taskId)
          isGenerating.value = false
        }
      } catch {
        // 忽略解析错误
      }
    }

    ws.onerror = () => {
      // WebSocket 失败 → 回退到 HTTP 轮询
      closeWs(taskId)
      startPolling(taskId)
    }

    ws.onclose = () => {
      wsConnections.value.delete(taskId)
    }
  }

  /** HTTP 轮询 (WebSocket 不可用时的回退) */
  function startPolling(taskId: string) {
    const interval = setInterval(async () => {
      try {
        const status = await getTaskStatus(taskId)
        updateVideo(taskId, {
          status: status.status,
          progress: status.progress,
          videoUrl: status.output_path || undefined,
          thumbnailUrl: status.thumbnail_path || undefined,
          errorMessage: status.error_message,
        })

        if (status.status === 'completed' || status.status === 'failed') {
          clearInterval(interval)
          isGenerating.value = false
        }
      } catch {
        clearInterval(interval)
        updateVideo(taskId, { status: 'failed', errorMessage: '状态查询失败' })
        isGenerating.value = false
      }
    }, 1500)
  }

  /** 关闭 WebSocket 连接 */
  function closeWs(taskId: string) {
    const ws = wsConnections.value.get(taskId)
    if (ws && ws.readyState !== WebSocket.CLOSED) {
      ws.close()
    }
    wsConnections.value.delete(taskId)
  }

  // ── CRUD ────────────────────────────────────────

  function updateVideo(taskId: string, updates: Partial<VideoItem>) {
    const idx = videos.value.findIndex(v => v.taskId === taskId)
    if (idx !== -1) {
      videos.value[idx] = { ...videos.value[idx], ...updates }
    }
  }

  function removeVideo(taskId: string) {
    closeWs(taskId)
    videos.value = videos.value.filter(v => v.taskId !== taskId)
  }

  function getVideo(taskId: string): VideoItem | undefined {
    return videos.value.find(v => v.taskId === taskId)
  }

  /** 清除错误 */
  function clearError() {
    error.value = null
  }

  return {
    // state
    videos,
    isGenerating,
    isLoading,
    error,
    wsConnections,
    // computed
    completedVideos,
    generatingVideos,
    failedVideos,
    // actions
    fetchMyTasks,
    startGeneration,
    updateVideo,
    removeVideo,
    getVideo,
    clearError,
  }
})
