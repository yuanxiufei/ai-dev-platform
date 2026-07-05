/**
 * useCommentsStore — VSCode 代码评审评论系统
 *
 * 借鉴: VSCode src/vs/workbench/contrib/comments/
 *
 * Session 54: 接入后端 REST API + localStorage 后备缓存
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// ── 类型定义 ──

export interface CommentAuthor {
  name: string
  avatar?: string
}

export interface CodeComment {
  id: string
  /** 文件路径 */
  filePath: string
  /** 行号 (1-based) */
  line: number
  /** 结束行号 */
  endLine?: number
  /** 评论正文 */
  body: string
  /** 作者信息 */
  author: CommentAuthor
  /** 创建时间 */
  createdAt: number
  /** 是否已解决 */
  resolved: boolean
  /** 回复评论 (thread) */
  replies: CodeComment[]
  /** 评论状态: "active" | "resolved" | "outdated" */
  state: 'active' | 'resolved' | 'outdated'
  /** 上下文代码片段（评论所在行的代码） */
  contextSnippet?: string
  /** 标签: "review" | "suggestion" | "question" | "issue" */
  label?: 'review' | 'suggestion' | 'question' | 'issue'
  /** Ghost 文本（建议代码） */
  suggestion?: string
}

const STORAGE_KEY = 'ide_comments_v2'

// ── 辅助: localStorage 桥接 ──

function loadFromCache(): CodeComment[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
  } catch {
    return []
  }
}

function saveToCache(comments: CodeComment[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(comments))
  } catch { /* ignore */ }
}

/** 将后端 API 返回的 snake_case 映射为 store 的 camelCase */
function mapApiComments(apiComments: any[]): CodeComment[] {
  return apiComments.map(c => ({
    id: c.id,
    filePath: c.file_path ?? c.filePath,
    line: c.line,
    endLine: c.end_line ?? c.endLine,
    body: c.body,
    author: c.author ?? { name: 'Unknown' },
    createdAt: c.created_at ?? c.createdAt ?? Date.now(),
    resolved: c.resolved ?? false,
    state: c.state ?? 'active',
    contextSnippet: c.context_snippet ?? c.contextSnippet,
    label: c.label,
    suggestion: c.suggestion,
    replies: c.replies ? mapApiComments(c.replies) : [],
  }))
}

// ── Store ──

export const useCommentsStore = defineStore('comments', () => {
  const comments = ref<CodeComment[]>(loadFromCache())
  const workspaceId = ref('default')
  const loading = ref(false)
  const apiAvailable = ref(false)

  /** 当前活动文件的评论 */
  function forFile(filePath: string): CodeComment[] {
    return comments.value.filter(c => c.filePath === filePath)
  }

  /** 某行的评论 */
  function forLine(filePath: string, line: number): CodeComment[] {
    return comments.value.filter(c => c.filePath === filePath && c.line === line)
  }

  /** 未解决的评论数 */
  const unresolvedCount = computed(() =>
    comments.value.filter(c => c.state !== 'resolved').length,
  )

  /** 文件未解决评论数 */
  function fileUnresolvedCount(filePath: string): number {
    return comments.value.filter(c => c.filePath === filePath && c.state !== 'resolved').length
  }

  // ── API 同步 ──

  /** 从后端拉取评论列表并合并到本地 */
  async function fetchFromApi(filePath?: string): Promise<void> {
    try {
      loading.value = true
      const { listComments } = await import('@/api/comments')
      const apiComments = await listComments(workspaceId.value, filePath, false)
      const mapped = mapApiComments(apiComments)
      // 合并: 后端优先，本地未同步的保留
      const apiIds = new Set(mapped.map(c => c.id))
      const localOnly = comments.value.filter(c => !apiIds.has(c.id) && (!filePath || c.filePath === filePath))
      comments.value = [...mapped, ...localOnly]
      saveToCache(comments.value)
      apiAvailable.value = true
    } catch (e) {
      console.warn('[Comments] Backend API unavailable, using local cache:', e)
      apiAvailable.value = false
    } finally {
      loading.value = false
    }
  }

  /** 推送本地评论到后端 (启动时调用) */
  async function syncToApi(): Promise<void> {
    if (!apiAvailable.value) return
    try {
      for (const c of comments.value) {
        try {
          const { addComment: apiAdd } = await import('@/api/comments')
          await apiAdd({
            file_path: c.filePath,
            line: c.line,
            body: c.body,
            workspace_id: workspaceId.value,
            author_name: c.author.name,
            author_avatar: c.author.avatar,
            label: c.label,
            suggestion: c.suggestion,
            end_line: c.endLine,
            context_snippet: c.contextSnippet,
          })
        } catch {
          // 评论可能已存在，跳过
        }
      }
    } catch (e) {
      console.warn('[Comments] Sync to API failed:', e)
    }
  }

  /** 初始化: 从 API 加载评论 */
  async function init(wsId = 'default'): Promise<void> {
    workspaceId.value = wsId
    await fetchFromApi()
    await syncToApi()
  }

  // ── CRUD 操作 ──

  /** 添加评论 */
  async function addComment(
    filePath: string,
    line: number,
    body: string,
    author: CommentAuthor = { name: 'User' },
    label?: CodeComment['label'],
    suggestion?: string,
    endLine?: number,
  ): Promise<CodeComment> {
    // 先尝试 API
    if (apiAvailable.value) {
      try {
        const { addComment: apiAdd } = await import('@/api/comments')
        const result = await apiAdd({
          file_path: filePath,
          line,
          body,
          workspace_id: workspaceId.value,
          author_name: author.name,
          author_avatar: author.avatar,
          label,
          suggestion,
          end_line: endLine,
        })
        const mapped = mapApiComments([result])[0]
        comments.value.push(mapped)
        saveToCache(comments.value)
        return mapped
      } catch (e) {
        console.warn('[Comments] API add failed, falling back to local:', e)
      }
    }

    // 本地后备
    const comment: CodeComment = {
      id: `comment-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      filePath,
      line,
      endLine,
      body,
      author,
      createdAt: Date.now(),
      resolved: false,
      replies: [],
      state: 'active',
      contextSnippet: '',
      label,
      suggestion,
    }
    comments.value.push(comment)
    saveToCache(comments.value)
    return comment
  }

  /** 添加回复 */
  async function addReply(
    parentId: string,
    body: string,
    author: CommentAuthor = { name: 'User' },
  ): Promise<CodeComment | null> {
    const parent = comments.value.find(c => c.id === parentId)
    if (!parent) return null

    // 尝试 API
    if (apiAvailable.value) {
      try {
        const { addReply: apiReply } = await import('@/api/comments')
        const result = await apiReply(parentId, body, author.name, author.avatar)
        const mapped = mapApiComments([result])[0]
        parent.replies.push(mapped)
        saveToCache(comments.value)
        return mapped
      } catch (e) {
        console.warn('[Comments] API reply failed, falling back to local:', e)
      }
    }

    // 本地后备
    const reply: CodeComment = {
      id: `reply-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      filePath: parent.filePath,
      line: parent.line,
      body,
      author,
      createdAt: Date.now(),
      resolved: false,
      replies: [],
      state: 'active',
    }
    parent.replies.push(reply)
    saveToCache(comments.value)
    return reply
  }

  /** 解决/取消解决评论 */
  async function toggleResolve(commentId: string): Promise<void> {
    // 尝试 API
    if (apiAvailable.value) {
      try {
        const { toggleResolve: apiToggle } = await import('@/api/comments')
        const result = await apiToggle(commentId)
        const comment = comments.value.find(c => c.id === commentId)
        if (comment) {
          comment.resolved = result.resolved
          comment.state = result.state as CodeComment['state']
          if (comment.resolved) {
            comment.replies.forEach(r => { r.resolved = true; r.state = 'resolved' })
          }
        }
        saveToCache(comments.value)
        return
      } catch (e) {
        console.warn('[Comments] API resolve failed, falling back to local:', e)
      }
    }

    // 本地后备
    const comment = comments.value.find(c => c.id === commentId)
    if (!comment) return
    comment.resolved = !comment.resolved
    comment.state = comment.resolved ? 'resolved' : 'active'
    if (comment.resolved) {
      comment.replies.forEach(r => { r.resolved = true; r.state = 'resolved' })
    }
    saveToCache(comments.value)
  }

  /** 删除评论 */
  async function deleteComment(commentId: string): Promise<void> {
    if (apiAvailable.value) {
      try {
        const { deleteComment: apiDelete } = await import('@/api/comments')
        await apiDelete(commentId)
      } catch (e) {
        console.warn('[Comments] API delete failed:', e)
      }
    }
    comments.value = comments.value.filter(c => c.id !== commentId)
    saveToCache(comments.value)
  }

  /** 编辑评论 */
  async function editComment(commentId: string, newBody: string): Promise<void> {
    if (apiAvailable.value) {
      try {
        const { editComment: apiEdit } = await import('@/api/comments')
        await apiEdit(commentId, newBody)
      } catch (e) {
        console.warn('[Comments] API edit failed:', e)
      }
    }
    const comment = comments.value.find(c => c.id === commentId)
    if (comment) {
      comment.body = newBody
      saveToCache(comments.value)
    }
  }

  /** 接受评论建议 (suggestion) */
  async function acceptSuggestion(commentId: string): Promise<string | null> {
    if (apiAvailable.value) {
      try {
        const { acceptSuggestion: apiAccept } = await import('@/api/comments')
        const result = await apiAccept(commentId)
        const comment = comments.value.find(c => c.id === commentId)
        if (comment) {
          comment.state = 'resolved'
          comment.resolved = true
        }
        saveToCache(comments.value)
        return result.suggestion
      } catch (e) {
        console.warn('[Comments] API accept failed:', e)
      }
    }

    // 本地后备
    const comment = comments.value.find(c => c.id === commentId)
    if (!comment || !comment.suggestion) return null
    comment.state = 'resolved'
    comment.resolved = true
    saveToCache(comments.value)
    return comment.suggestion
  }

  /** 清除文件的所有评论 */
  async function clearFileComments(filePath: string): Promise<void> {
    if (apiAvailable.value) {
      try {
        const { clearComments: apiClear } = await import('@/api/comments')
        await apiClear(workspaceId.value, filePath)
      } catch (e) {
        console.warn('[Comments] API clear failed:', e)
      }
    }
    comments.value = comments.value.filter(c => c.filePath !== filePath)
    saveToCache(comments.value)
  }

  /** 清除所有 */
  async function clearAll(): Promise<void> {
    if (apiAvailable.value) {
      try {
        const { clearComments: apiClear } = await import('@/api/comments')
        await apiClear(workspaceId.value)
      } catch (e) {
        console.warn('[Comments] API clear all failed:', e)
      }
    }
    comments.value = []
    saveToCache(comments.value)
  }

  return {
    comments,
    workspaceId,
    loading,
    apiAvailable,
    unresolvedCount,
    forFile,
    forLine,
    fileUnresolvedCount,
    init,
    fetchFromApi,
    addComment,
    addReply,
    toggleResolve,
    deleteComment,
    editComment,
    acceptSuggestion,
    clearFileComments,
    clearAll,
  }
})
