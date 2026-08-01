import apiClient from "./client"

// ============================================
// 终端管理 API — 会话 CRUD + WebSocket 通道
// ============================================

export interface TerminalSession {
  session_id: string
  shell: string
  cwd: string | null
  ws_url: string
}

export interface TerminalInfo {
  terminal_id: string
  session_id: string
  shell: string
  cwd: string | null
  pid: number
  cols: number
  rows: number
  created_at: string
}

/** 构建 WebSocket URL（自动拼接 baseURL 的 host + JWT token） */
function buildTerminalWsUrl(sessionId: string): string {
  // 由 apiClient 的 baseURL 提取 protocol/host，拼接 WS 路径
  const baseUrl = (apiClient.defaults.baseURL || "/api/v1") as string
  const isHttps = baseUrl.startsWith("https")
  const wsProto = isHttps ? "wss" : "ws"
  // 处理相对路径 /api/v1 → 用当前 window.location
  try {
    const url = new URL(baseUrl, window.location.origin)
    return `${wsProto}://${url.host}${baseUrl}/system/terminal/sessions/${sessionId}/ws`
  } catch {
    // fallback：绝对路径拼接
    return `${wsProto}://${window.location.host}${baseUrl}/system/terminal/sessions/${sessionId}/ws`
  }
}

/** 获取 JWT token（从 localStorage 读取） */
function getToken(): string {
  // 尝试多种常见存储键
  const token = localStorage.getItem("access_token") || localStorage.getItem("token") || ""
  return token
}

export const terminalApi = {
  /** 创建终端会话，返回 session_id + ws_url */
  createSession: (shell = "/bin/bash", cwd?: string) =>
    apiClient.post("/system/terminal/sessions", null, {
      params: { shell, cwd },
    }),

  /** 列出所有活跃终端会话 */
  listSessions: () =>
    apiClient.get("/system/terminal/sessions"),

  /** 关闭终端会话 */
  closeSession: (sessionId: string, force = false) =>
    apiClient.delete(`/system/terminal/sessions/${sessionId}`, { params: { force } }),

  /**
   * 创建 WebSocket 连接到终端会话
   * 返回原生 WebSocket 对象，调用方负责生命周期管理
   */
  connectWs: (sessionId: string): WebSocket => {
    const wsUrl = `${buildTerminalWsUrl(sessionId)}?token=${getToken()}`
    const ws = new WebSocket(wsUrl)
    return ws
  },
}
