import apiClient from "./client"

/* ========== 类型定义 ========== */

export interface VideoAsset {
  id: string
  title: string
  description: string | null
  file_path: string
  thumbnail_path: string | null
  duration: number | null
  tags: string[] | null
  view_count: number
  is_public: boolean
  is_approved: boolean
  owner_id: number
  created_at: string
}

export interface VideoCreateRequest {
  title: string
  description?: string
  file_path: string
  thumbnail_path?: string
  duration?: number
  tags?: string[]
  is_public?: boolean
  is_approved?: boolean
  task_id?: string
}

export interface VideoUpdateRequest {
  title?: string
  description?: string
  tags?: string[]
  is_public?: boolean
  is_approved?: boolean
}

export interface GenerateRequest {
  prompt: string
  model_name?: string
  num_frames?: number  // 8-200, default 49
  fps?: number          // 4-30, default 8
  num_inference_steps?: number  // 10-100, default 50
  seed?: number
  style?: string  // cinematic | animation | product_demo | tutorial
}

export interface VideoTask {
  task_id: string
  prompt: string
  model_name: string
  status: "pending" | "generating" | "completed" | "failed"
  progress: number
  output_path: string | null
  thumbnail_path: string | null
  duration: number | null
  error_message: string | null
  created_at: string
}

export interface SubtitleCue {
  sequence: number
  start_time: string
  end_time: string
  text: string
}

export interface SubtitleInfo {
  language: string
  format: string
  source: string
}

export interface PageData<T> {
  data: T[]
  total: number
  page: number
  size: number
}

export interface AnalyticsOverview {
  videos: {
    total: number
    public: number
    total_views: number
    today_new: number
  }
  tasks: {
    total: number
    completed: number
    failed: number
    today_new: number
    success_rate: number
  }
}

export interface DailyTrend {
  date: string
  new_videos: number
  new_tasks: number
  views: number
}

/* ========== 客户端 API - 浏览/播放 ========== */

/** 浏览公开视频（C端） */
export function browseVideos(params: {
  page?: number; size?: number; tag?: string; sort?: "newest" | "popular"
} = {}) {
  return apiClient.get<PageData<VideoAsset>>("/videos/browse", { params })
}

/** 搜索视频 */
export function searchVideos(params: {
  q: string; page?: number; size?: number
}) {
  return apiClient.get<PageData<VideoAsset> & { query: string }>("/videos/search", { params })
}

/** 获取播放信息（自动+1播放数） */
export function getPlayInfo(videoId: string) {
  return apiClient.get<VideoAsset>(`/videos/${videoId}/play`)
}

/** 获取字幕 */
export function getSubtitles(videoId: string, lang = "zh", withCues = false) {
  return apiClient.get(`/videos/${videoId}/subtitles`, {
    params: { lang, with_cues: withCues },
  })
}

/** 列出字幕语言 */
export function listSubtitleLanguages(videoId: string) {
  return apiClient.get<{ video_id: string; languages: SubtitleInfo[] }>(
    `/videos/${videoId}/subtitles/languages`
  )
}

/** 上传字幕 */
export function uploadSubtitle(videoId: string, file: File, language = "zh") {
  const form = new FormData()
  form.append("file", file)
  return apiClient.post(`/videos/${videoId}/subtitles/upload`, form, {
    params: { language },
    headers: { "Content-Type": "multipart/form-data" },
  })
}

/** 删除字幕 */
export function deleteSubtitle(videoId: string, language: string) {
  return apiClient.delete(`/videos/${videoId}/subtitles/${language}`)
}

/* ========== 生成 API ========== */

/** 发起视频生成任务 */
export function generateVideo(req: GenerateRequest) {
  return apiClient.post<{ task_id: string; status: string; model_name: string }>(
    "/videos/generate", req
  )
}

/** 列出我的生成任务 */
export function listMyTasks(params: {
  page?: number; size?: number; status?: string
} = {}) {
  return apiClient.get<PageData<VideoTask>>("/videos/generate/my", { params })
}

/** 查询任务状态 */
export function getTaskStatus(taskId: string) {
  return apiClient.get<VideoTask>(`/videos/generate/${taskId}`)
}

/* ========== 管理端 API ========== */

/** 列出所有视频（管理端） */
export function listVideosAdmin(params: {
  page?: number; size?: number; is_approved?: boolean; is_public?: boolean
} = {}) {
  return apiClient.get<PageData<VideoAsset>>("/videos", { params })
}

/** 创建视频 */
export function createVideo(data: VideoCreateRequest) {
  return apiClient.post<VideoAsset>("/videos", data)
}

/** 获取视频详情（管理端） */
export function getVideoAdmin(videoId: string) {
  return apiClient.get<VideoAsset>(`/videos/${videoId}`)
}

/** 更新视频 */
export function updateVideo(videoId: string, data: VideoUpdateRequest) {
  return apiClient.put<VideoAsset>(`/videos/${videoId}`, data)
}

/** 删除视频 */
export function deleteVideo(videoId: string) {
  return apiClient.delete(`/videos/${videoId}`)
}

/* ========== 审核 API ========== */

/** 获取审核队列 */
export function getModerationQueue(params: { page?: number; size?: number } = {}) {
  return apiClient.get<PageData<VideoAsset>>("/videos/moderation/queue", { params })
}

/** 批准视频 */
export function approveVideo(videoId: string, reason?: string) {
  return apiClient.post(`/videos/moderation/${videoId}/approve`, { reason })
}

/** 驳回视频 */
export function rejectVideo(videoId: string, reason?: string) {
  return apiClient.post(`/videos/moderation/${videoId}/reject`, { reason })
}

/* ========== 分析 API ========== */

/** 数据概览 */
export function getAnalyticsOverview() {
  return apiClient.get<AnalyticsOverview>("/videos/analytics/overview")
}

/** 单视频分析 */
export function getVideoAnalytics(videoId: string) {
  return apiClient.get(`/videos/analytics/${videoId}`)
}

/** 每日趋势 */
export function getDailyTrends(days = 7) {
  return apiClient.get<{ trends: DailyTrend[]; days: number }>(
    "/videos/analytics/trends/daily", { params: { days } }
  )
}
