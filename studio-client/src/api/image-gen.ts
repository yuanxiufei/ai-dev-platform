import apiClient from "./client"

/* ========== 图像生成 ========== */

export interface ImageGenResult {
  images: {
    url: string
    b64_json: string
    local_path: string
    revised_prompt: string
    seed: number
    width: number
    height: number
  }[]
  provider_used: string
  latency_ms: number
}

export interface BatchGenResult {
  results: {
    prompt: string
    success: boolean
    image?: { url: string; b64_json: string }
    error?: string
  }[]
  total: number
  successful: number
}

export interface GenerateImagePayload {
  prompt: string
  negative_prompt?: string
  size?: string
  style?: string
  n?: number
  quality?: string
  seed?: number
  steps?: number
  cfg_scale?: number
  engine?: string
  model?: string
}

export const imageGenApi = {
  /** 获取可用引擎列表 */
  providers: () =>
    apiClient.get<{ providers: string[] }>("/image-gen/providers"),

  /** 单张/批量生成图像 */
  generate: (data: GenerateImagePayload) =>
    apiClient.post<ImageGenResult>("/image-gen/generate", data),

  /** 批量 Prompt 生成 */
  batchGenerate: (data: {
    prompts: string[]
    size?: string
    engine?: string
  }) => apiClient.post<BatchGenResult>("/image-gen/batch-generate", data),
}
