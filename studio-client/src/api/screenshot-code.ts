import apiClient from "./client"

/* ========== 截图转代码 ========== */

export interface ScreenshotCodeResult {
  message_id: string
  session_id: string
  content: string
  role: string
  model_used: string | null
  provider: string | null
  is_fallback: boolean
  latency_ms: number
}

export const screenshotToCode = (imagesBase64: string[], message: string) =>
  apiClient.post<ScreenshotCodeResult>("/studio/chat", {
    message,
    images_base64: imagesBase64,
  })
