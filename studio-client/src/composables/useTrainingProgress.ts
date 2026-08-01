import { ref, onUnmounted } from "vue"

export interface TrainingProgress {
  kb_id: string
  total: number
  current: number
  done: number
  failed: number
  phase: string
  message: string
  errors: string[]
  finished: boolean
}

export function useTrainingProgress(kbId: string) {
  const progress = ref<TrainingProgress | null>(null)
  const connected = ref(false)
  const error = ref<string | null>(null)
  let ws: WebSocket | null = null

  const connect = () => {
    try {
      const proto = location.protocol === "https:" ? "wss:" : "ws:"
      const host = location.host
      ws = new WebSocket(`${proto}//${host}/api/v1/rag/knowledge-bases/${kbId}/retrain/ws`)

      ws.onopen = () => {
        connected.value = true
        error.value = null
      }

      ws.onmessage = (evt) => {
        try {
          const data: TrainingProgress = JSON.parse(evt.data)
          progress.value = data
          if (data.finished && ws) {
            ws.close()
          }
        } catch {
          // ignore malformed messages
        }
      }

      ws.onerror = () => {
        error.value = "WebSocket 连接失败"
        connected.value = false
      }

      ws.onclose = () => {
        connected.value = false
      }
    } catch (e: unknown) {
      error.value = `WebSocket 创建失败: ${(e as Error).message}`
      connected.value = false
    }
  }

  const disconnect = () => {
    if (ws) {
      ws.close()
      ws = null
    }
  }

  onUnmounted(disconnect)

  return { progress, connected, error, connect, disconnect }
}
