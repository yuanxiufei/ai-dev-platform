/**
 * ChatSessionManager.ts — 会话持久化管理器 (参考 Roo Code Task Persistence)
 *
 * 功能:
 *   1. localStorage 本地持久化（即时恢复，离线可用）
 *   2. 后端 API 远程持久化（跨设备同步）
 *   3. 会话列表管理（创建/切换/删除/搜索）
 *   4. 自动保存（每 N 条消息或每 M 秒）
 *
 * 数据结构参考 RooCode PersistedTask:
 *   { sessionId, title, messages[], metadata{}, savedAt, version }
 */
import type { ChatMessage } from "@/types/studio"

// ── 类型定义 ──
export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  createdAt: string
  updatedAt: string
  /** 消息数 (快速预览) */
  messageCount: number
  /** 使用的模型 */
  modelUsed?: string
  /** 会话元数据 */
  metadata?: {
    mode?: string
    projectId?: string
    totalTokens?: number
    tags?: string[]
  }
  /** localStorage 版本号 */
  version: number
}

export interface SessionListItem {
  id: string
  title: string
  preview: string
  messageCount: number
  updatedAt: string
  modelUsed?: string
  mode?: string
}

// ── 存储配置 ──
const STORAGE_KEY = "codebuddy_chat_sessions"
const CURRENT_SESSION_KEY = "codebuddy_current_session"
const MAX_LOCAL_SESSIONS = 50
const VERSION = 1

// ── 序列化 / 反序列化 ──
const serializeSession = (session: ChatSession): string => {
  return JSON.stringify({
    ...session,
    // 只保留最近 200 条消息以减少存储空间
    messages: session.messages.slice(-200),
  })
}

const deserializeSession = (raw: string): ChatSession | null => {
  try {
    const parsed = JSON.parse(raw) as ChatSession
    // 版本迁移
    if (parsed.version !== VERSION) {
      parsed.version = VERSION
    }
    return parsed
  } catch {
    return null
  }
}

// ── localStorage 操作 ──
const loadAllSessions = (): Map<string, ChatSession> => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return new Map()
    const entries: [string, string][] = JSON.parse(raw)
    const map = new Map<string, ChatSession>()
    for (const [id, data] of entries) {
      const session = deserializeSession(data)
      if (session) map.set(id, session)
    }
    return map
  } catch {
    return new Map()
  }
}

const saveAllSessions = (sessions: Map<string, ChatSession>) => {
  try {
    // 限制最大会话数，删除最旧的
    const entries = Array.from(sessions.entries())
    if (entries.length > MAX_LOCAL_SESSIONS) {
      entries.sort((a, b) => new Date(b[1].updatedAt).getTime() - new Date(a[1].updatedAt).getTime())
      entries.length = MAX_LOCAL_SESSIONS
    }
    const serialized: [string, string][] = entries.map(([id, s]) => [id, serializeSession(s)])
    localStorage.setItem(STORAGE_KEY, JSON.stringify(serialized))
  } catch (e) {
    console.warn("[ChatSessionManager] localStorage 写入失败:", e)
  }
}

// ── ChatSessionManager 类 ──
export class ChatSessionManager {
  private sessions: Map<string, ChatSession>
  private currentId: string | null
  private autoSaveTimer: ReturnType<typeof setInterval> | null = null

  constructor() {
    this.sessions = loadAllSessions()
    this.currentId = localStorage.getItem(CURRENT_SESSION_KEY)
  }

  // ── CRUD 操作 ──

  /** 获取当前会话 */
  getCurrentSession(): ChatSession | null {
    if (!this.currentId) return null
    return this.sessions.get(this.currentId) || null
  }

  /** 获取当前会话 ID */
  getCurrentId(): string | null {
    return this.currentId
  }

  /** 创建新会话 */
  createSession(title?: string, metadata?: ChatSession["metadata"]): ChatSession {
    const id = crypto.randomUUID()
    const session: ChatSession = {
      id,
      title: title || "新对话",
      messages: [],
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      messageCount: 0,
      metadata,
      version: VERSION,
    }
    this.sessions.set(id, session)
    this.currentId = id
    localStorage.setItem(CURRENT_SESSION_KEY, id)
    this.persist()
    return session
  }

  /** 切换到指定会话 */
  switchSession(id: string): ChatSession | null {
    const session = this.sessions.get(id)
    if (!session) return null
    this.currentId = id
    localStorage.setItem(CURRENT_SESSION_KEY, id)
    return session
  }

  /** 删除会话 */
  deleteSession(id: string): boolean {
    const deleted = this.sessions.delete(id)
    if (this.currentId === id) {
      this.currentId = null
      localStorage.removeItem(CURRENT_SESSION_KEY)
    }
    if (deleted) this.persist()
    return deleted
  }

  /** 重命名会话 */
  renameSession(id: string, title: string): boolean {
    const session = this.sessions.get(id)
    if (!session) return false
    session.title = title
    session.updatedAt = new Date().toISOString()
    this.persist()
    return true
  }

  /** 保存当前会话 */
  saveCurrentSession(messages: ChatMessage[], title?: string): void {
    if (!this.currentId) {
      this.createSession(title)
    }
    const session = this.sessions.get(this.currentId!)
    if (!session) return

    session.messages = messages.slice(-200)
    session.messageCount = messages.length
    session.updatedAt = new Date().toISOString()
    if (title) session.title = title

    // 自动提取最后一条 assistant 消息作为标题
    if (!title && messages.length > 0) {
      const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant")
      if (lastAssistant) {
        session.title = lastAssistant.content.substring(0, 50).replace(/\n/g, " ") || "新对话"
      }
    }

    this.persist()
  }

  /** 获取会话列表 (摘要) */
  getSessionList(): SessionListItem[] {
    const list: SessionListItem[] = []
    this.sessions.forEach((s) => {
      const lastMsg = s.messages[s.messages.length - 1]
      list.push({
        id: s.id,
        title: s.title,
        preview: lastMsg?.content?.substring(0, 100).replace(/\n/g, " ") || "空对话",
        messageCount: s.messageCount,
        updatedAt: s.updatedAt,
        modelUsed: s.modelUsed,
        mode: s.metadata?.mode,
      })
    })
    return list.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime())
  }

  /** 清空所有会话 */
  clearAll(): void {
    this.sessions.clear()
    this.currentId = null
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem(CURRENT_SESSION_KEY)
  }

  // ── 自动保存 ──

  /** 启动自动保存 (每 30 秒) */
  startAutoSave(messagesRef: { value: ChatMessage[] }, getTitle?: () => string) {
    this.stopAutoSave()
    this.autoSaveTimer = setInterval(() => {
      if (messagesRef.value.length > 0) {
        this.saveCurrentSession(messagesRef.value, getTitle?.())
      }
    }, 30_000)
  }

  /** 停止自动保存 */
  stopAutoSave() {
    if (this.autoSaveTimer) {
      clearInterval(this.autoSaveTimer)
      this.autoSaveTimer = null
    }
  }

  // ── 导出 / 导入 ──

  /** 导出会话为 JSON */
  exportSession(id: string): string | null {
    const session = this.sessions.get(id)
    if (!session) return null
    return serializeSession(session)
  }

  /** 从 JSON 导入会话 */
  importSession(json: string): ChatSession | null {
    const session = deserializeSession(json)
    if (!session) return null
    session.id = crypto.randomUUID() // 避免 ID 冲突
    session.updatedAt = new Date().toISOString()
    this.sessions.set(session.id, session)
    this.persist()
    return session
  }

  /** 获取存储使用情况 */
  getStorageStats(): { sessionCount: number; totalMessages: number; estimatedSizeKB: number } {
    let totalMessages = 0
    this.sessions.forEach((s) => { totalMessages += s.messageCount })
    const raw = localStorage.getItem(STORAGE_KEY) || ""
    return {
      sessionCount: this.sessions.size,
      totalMessages,
      estimatedSizeKB: Math.round(raw.length / 1024),
    }
  }

  // ── 持久化 ──
  private persist() {
    saveAllSessions(this.sessions)
  }
}

// ── 全局单例 ──
let _manager: ChatSessionManager | null = null

export const getChatSessionManager = (): ChatSessionManager => {
  if (!_manager) {
    _manager = new ChatSessionManager()
  }
  return _manager
}
