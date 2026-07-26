/**
 * WebSocket 训练进度 Composable
 * 用法: connect(kbId, filepath) → 自动接收实时进度更新
 */
import { ref, type Ref } from 'vue'

export interface ProgressUpdate {
  stage: string
  pct: number
  message: string
  chunk_count?: number
}

export function useTrainingProgress() {
  const ws = ref<WebSocket | null>(null)
  const stage = ref('')
  const pct = ref(0)
  const message = ref('')
  const chunkCount = ref(0)
  const connected = ref(false)
  const error = ref('')
  const done = ref(false)

  /** 获取 WebSocket 基地址 */
  function wsBaseUrl(): string {
    const loc = window.location
    const protocol = loc.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${protocol}//${loc.host}`
  }

  /** 连接 WebSocket 并发送训练指令 */
  function connect(kbId: string, filepath: string, repair: boolean = true): void {
    disconnect()
    error.value = ''
    done.value = false
    stage.value = ''
    pct.value = 0
    message.value = '正在连接...'
    chunkCount.value = 0

    const url = `${wsBaseUrl()}/api/v1/rag/knowledge-bases/${kbId}/train-ws`
    const socket = new WebSocket(url)
    ws.value = socket

    socket.onopen = () => {
      connected.value = true
      message.value = '已连接，开始训练...'
      socket.send(JSON.stringify({ filepath, repair }))
    }

    socket.onmessage = (event) => {
      try {
        const data: ProgressUpdate = JSON.parse(event.data)
        stage.value = data.stage
        pct.value = data.pct
        message.value = data.message

        if (data.stage === 'done') {
          done.value = true
          if (data.chunk_count != null) {
            chunkCount.value = data.chunk_count
          }
          disconnect()
        }

        if (data.stage === 'error') {
          error.value = data.message
          disconnect()
        }
      } catch {
        error.value = '进度解析失败'
      }
    }

    socket.onerror = () => {
      error.value = 'WebSocket 连接失败'
      disconnect()
    }

    socket.onclose = () => {
      connected.value = false
    }
  }

  function disconnect(): void {
    if (ws.value) {
      try {
        ws.value.close()
      } catch { /* ignore */ }
      ws.value = null
    }
    connected.value = false
  }

  /** 连接 retrain-ws（无需发送数据，连上即开始） */
  function connectRetrain(kbId: string): void {
    disconnect()
    error.value = ''
    done.value = false
    stage.value = ''
    pct.value = 0
    message.value = '正在连接...'
    chunkCount.value = 0

    const url = `${wsBaseUrl()}/api/v1/rag/knowledge-bases/${kbId}/retrain-ws`
    const socket = new WebSocket(url)
    ws.value = socket

    socket.onopen = () => {
      connected.value = true
      message.value = '已连接，开始重新训练...'
    }

    socket.onmessage = (event) => {
      try {
        const data: ProgressUpdate = JSON.parse(event.data)
        stage.value = data.stage
        pct.value = data.pct
        message.value = data.message

        if (data.stage === 'done') {
          done.value = true
          if ((data as any).summary) {
            // retrain 完成时会带 summary: { total, success, failed, errors }
            chunkCount.value = (data as any).summary.success ?? 0
          }
          disconnect()
        }

        if (data.stage === 'error') {
          error.value = data.message
          disconnect()
        }
      } catch {
        error.value = '进度解析失败'
      }
    }

    socket.onerror = () => {
      error.value = 'WebSocket 连接失败'
      disconnect()
    }

    socket.onclose = () => {
      connected.value = false
    }
  }

  return {
    ws,
    stage,
    pct,
    message,
    chunkCount,
    connected,
    error,
    done,
    connect,
    connectRetrain,
    disconnect,
  }
}
