/**
 * Comments API 客户端 — 连接后端 /api/v1/system/comments/
 *
 * Session 53: 对标 VSCode Comments System
 * 覆盖: list/count/add/reply/edit/resolve/accept-suggestion/delete/clear
 */
import apiClient from "./client"

const COMMENTS_BASE = "/system/comments"

/* ========== 类型定义 ========== */

export interface CommentAuthor {
  name: string
  avatar?: string
}

export interface CodeComment {
  id: string
  file_path: string
  line: number
  end_line?: number
  body: string
  author: CommentAuthor
  created_at: number
  resolved: boolean
  state: "active" | "resolved" | "outdated"
  context_snippet?: string
  label?: "review" | "suggestion" | "question" | "issue"
  suggestion?: string
  replies: CodeComment[]
}

export interface UnresolvedCounts {
  total: number
  by_file: Record<string, number>
}

/* ========== API 方法 ========== */

/** 获取评论列表 */
export async function listComments(
  workspaceId = "default",
  filePath?: string,
  includeResolved = false,
): Promise<CodeComment[]> {
  const { data } = await apiClient.get(`${COMMENTS_BASE}/list`, {
    params: {
      workspace_id: workspaceId,
      file_path: filePath ?? undefined,
      include_resolved: includeResolved,
    },
  })
  return data
}

/** 获取未解决评论计数 */
export async function getCommentsCount(workspaceId = "default"): Promise<UnresolvedCounts> {
  const { data } = await apiClient.get(`${COMMENTS_BASE}/count`, {
    params: { workspace_id: workspaceId },
  })
  return data
}

/** 添加评论 */
export async function addComment(params: {
  file_path: string
  line: number
  body: string
  workspace_id?: string
  author_name?: string
  author_avatar?: string
  label?: string
  suggestion?: string
  end_line?: number
  context_snippet?: string
}): Promise<CodeComment> {
  const { data } = await apiClient.post(`${COMMENTS_BASE}`, params)
  return data
}

/** 回复评论 */
export async function addReply(
  commentId: string,
  body: string,
  authorName = "User",
  authorAvatar?: string,
): Promise<CodeComment> {
  const { data } = await apiClient.post(`${COMMENTS_BASE}/${commentId}/reply`, {
    body,
    author_name: authorName,
    author_avatar: authorAvatar ?? null,
  })
  return data
}

/** 编辑评论 */
export async function editComment(
  commentId: string,
  body: string,
  state?: string,
): Promise<void> {
  await apiClient.patch(`${COMMENTS_BASE}/${commentId}`, { body, state: state ?? null })
}

/** 切换解决状态 */
export async function toggleResolve(commentId: string): Promise<{ ok: boolean; resolved: boolean; state: string }> {
  const { data } = await apiClient.post(`${COMMENTS_BASE}/${commentId}/resolve`)
  return data
}

/** 接受建议 */
export async function acceptSuggestion(
  commentId: string,
): Promise<{ ok: boolean; suggestion: string; file_path: string; line: number }> {
  const { data } = await apiClient.post(`${COMMENTS_BASE}/${commentId}/suggestion/accept`)
  return data
}

/** 删除评论 */
export async function deleteComment(commentId: string): Promise<void> {
  await apiClient.delete(`${COMMENTS_BASE}/${commentId}`)
}

/** 清除评论 */
export async function clearComments(
  workspaceId = "default",
  filePath?: string,
): Promise<void> {
  await apiClient.delete(`${COMMENTS_BASE}`, {
    params: { workspace_id: workspaceId, file_path: filePath ?? undefined },
  })
}
