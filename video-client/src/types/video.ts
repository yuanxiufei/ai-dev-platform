/**
 * Video 域类型定义 — 对齐后端 VideoTask / VideoAsset 模型
 */

export type TaskStatus = 'pending' | 'generating' | 'completed' | 'failed'

export interface GenerateRequest {
  prompt: string
  model_name?: string
  num_frames?: number
  fps?: number
  num_inference_steps?: number
  seed?: number
  style?: string
}

export interface GenerateResponse {
  task_id: string
  status: string
  model_name: string
  prompt: string
}

export interface TaskStatusResponse {
  task_id: string
  prompt: string
  model_name: string
  status: TaskStatus
  progress: number
  output_path: string | null
  thumbnail_path: string | null
  duration: number | null
  error_message: string | null
  created_at: string
}

export interface VideoAssetItem {
  id: string
  title: string
  description: string | null
  file_path: string
  thumbnail_path: string | null
  duration: number | null
  tags: string[] | null
  view_count: number
  created_at: string
}

export interface BrowseResponse {
  data: VideoAssetItem[]
  total: number
  page: number
  size: number
}

export interface MyTasksResponse {
  data: TaskStatusResponse[]
  total: number
  page: number
  size: number
}

export interface PlayInfoResponse {
  id: string
  title: string
  description: string | null
  file_path: string
  thumbnail_path: string | null
  duration: number | null
  tags: string[] | null
  view_count: number
  created_at: string
}

/** WebSocket 进度消息 */
export interface WsProgressMessage {
  task_id: string
  status: TaskStatus
  progress: number
  output_path?: string | null
  thumbnail_path?: string | null
  error_message?: string | null
  done?: boolean
}

/** 本地视频项 (Store 用, 合并 TaskStatusResponse 字段) */
export interface VideoItem {
  taskId: string
  title: string
  prompt: string
  status: TaskStatus
  progress: number
  thumbnailUrl?: string
  videoUrl?: string
  duration: number | null
  style: string
  modelName: string
  errorMessage?: string | null
  createdAt: string
}
