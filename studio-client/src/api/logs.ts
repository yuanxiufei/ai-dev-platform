import apiClient from "./client"

// ── Types ────────────────────────────────────────────

export interface LogEntry {
  timestamp: string
  level: "trace" | "debug" | "info" | "warn" | "error" | "fatal"
  channel: string
  message: string
  source: string
  metadata?: Record<string, any>
}

export interface LogChannelInfo {
  name: string
  count: number
}

export interface LogChannelResponse {
  channel: string
  total: number
  entries: LogEntry[]
}

export interface LogSearchResponse {
  query: string
  total: number
  results: LogEntry[]
}

export interface LogWritePayload {
  message: string
  level?: string
  source?: string
}

// ── API ──────────────────────────────────────────────

export const logsApi = {
  /** 列出所有日志通道及其条目数 */
  listChannels: () =>
    apiClient.get<{ channels: LogChannelInfo[] }>("/system/logs/channels"),

  /** 获取指定通道的日志条目（支持 level/limit/offset） */
  getLogs: (channel: string, params?: { level?: string; limit?: number; offset?: number }) =>
    apiClient.get<LogChannelResponse>(`/system/logs/${channel}`, { params }),

  /** 写入日志到指定通道 */
  writeLog: (channel: string, payload: LogWritePayload) =>
    apiClient.post<LogEntry>(`/system/logs/${channel}`, payload),

  /** 清空指定通道的所有日志 */
  clearChannel: (channel: string) =>
    apiClient.delete(`/system/logs/${channel}`),

  /** 全文搜索日志（跨通道，按 message 匹配） */
  searchLogs: (query: string, params?: { channel?: string; level?: string; limit?: number }) =>
    apiClient.get<LogSearchResponse>("/system/logs/search", {
      params: { q: query, ...params },
    }),

  /** 创建 WebSocket 实时日志流 */
  streamLogs: (channel: string): WebSocket => {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:"
    const base = (apiClient.defaults.baseURL || "").replace(/^http/, "ws")
    return new WebSocket(`${base}/system/logs/${channel}/stream`)
  },
}
