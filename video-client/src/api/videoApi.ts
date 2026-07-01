/**
 * Video API Service — 对接后端视频生成/浏览/播放全部端点
 */
import apiClient from './client'
import type {
  GenerateRequest,
  GenerateResponse,
  TaskStatusResponse,
  BrowseResponse,
  MyTasksResponse,
  PlayInfoResponse,
} from '../types/video'

// ── 生成 ─────────────────────────────────────────

/** 发起视频生成任务 */
export async function generateVideo(payload: GenerateRequest): Promise<GenerateResponse> {
  const { data } = await apiClient.post<GenerateResponse>('/videos/generate', payload)
  return data
}

/** 查询任务状态 */
export async function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  const { data } = await apiClient.get<TaskStatusResponse>(`/videos/generate/${taskId}`)
  return data
}

/** 列出我的生成任务 */
export async function listMyTasks(
  page = 1,
  size = 20,
  status?: string,
): Promise<MyTasksResponse> {
  const params: Record<string, string | number> = { page, size }
  if (status) params.status = status
  const { data } = await apiClient.get<MyTasksResponse>('/videos/generate/my', { params })
  return data
}

// ── 浏览 ─────────────────────────────────────────

/** 浏览公开视频 */
export async function browseVideos(
  page = 1,
  size = 20,
  tag?: string,
  sort = 'newest',
): Promise<BrowseResponse> {
  const params: Record<string, string | number> = { page, size, sort }
  if (tag) params.tag = tag
  const { data } = await apiClient.get<BrowseResponse>('/videos/browse', { params })
  return data
}

/** 搜索视频 */
export async function searchVideos(
  q: string,
  page = 1,
  size = 20,
): Promise<BrowseResponse> {
  const { data } = await apiClient.get<BrowseResponse>('/videos/search', {
    params: { q, page, size },
  })
  return data
}

// ── 播放 ─────────────────────────────────────────

/** 获取播放信息 */
export async function getPlayInfo(videoId: string): Promise<PlayInfoResponse> {
  const { data } = await apiClient.get<PlayInfoResponse>(`/videos/${videoId}/play`)
  return data
}

/** 创建 WebSocket 连接 (用于实时进度) */
export function connectProgressWs(
  taskId: string,
  token: string,
): WebSocket {
  const baseUrl = import.meta.env.VITE_WS_URL || `ws://localhost:8000`
  const ws = new WebSocket(`${baseUrl}/api/v1/videos/generate/${taskId}/ws?token=${encodeURIComponent(token)}`)
  return ws
}
