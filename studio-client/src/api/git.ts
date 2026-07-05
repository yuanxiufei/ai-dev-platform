/**
 * Git API 客户端 — 连接后端 /api/v1/system/git/ 
 *
 * Session 53: 对标 VSCode Git Extension API
 * 覆盖: status, stage, unstage, commit, push, pull, diff, branches, checkout, log, stash, blame, remotes, clone
 */
import apiClient from "./client"

const GIT_BASE = "/system/git"

/* ========== 类型定义 ========== */

export interface GitFileChange {
  path: string
  status: "staged" | "modified" | "added" | "deleted" | "untracked" | "renamed"
  old_path?: string
}

export interface GitStatus {
  branch: string
  ahead: number
  behind: number
  changes: GitFileChange[]
}

export interface DiffLine {
  type: "added" | "removed" | "context"
  content: string
  line_number?: number
}

export interface DiffHunk {
  header: string
  lines: DiffLine[]
}

export interface DiffEntry {
  path: string
  old_path?: string
  status: string
  additions: number
  deletions: number
  hunks: DiffHunk[]
}

export interface BranchEntry {
  name: string
  is_current: boolean
  is_remote: boolean
}

export interface CommitEntry {
  hash: string
  short_hash: string
  message: string
  author: string
  email: string
  date: string
}

export interface BlameLine {
  line_number: number
  commit_hash: string
  author: string
  date: string
  summary: string
  time_ago: string
}

export interface RemoteEntry {
  name: string
  url: string
  fetch: boolean
  push: boolean
}

/* ========== API 方法 ========== */

/** 获取仓库状态 */
export async function getStatus(repoPath = "."): Promise<GitStatus> {
  const { data } = await apiClient.get(`${GIT_BASE}/status`, { params: { repo_path: repoPath } })
  return data
}

/** 暂存文件 */
export async function stageFile(repoPath: string, filePath: string): Promise<void> {
  await apiClient.post(`${GIT_BASE}/stage`, { repo_path: repoPath, file_path: filePath })
}

/** 取消暂存 */
export async function unstageFile(repoPath: string, filePath: string): Promise<void> {
  await apiClient.post(`${GIT_BASE}/unstage`, { repo_path: repoPath, file_path: filePath })
}

/** 暂存全部 */
export async function stageAll(repoPath = "."): Promise<void> {
  await apiClient.post(`${GIT_BASE}/stage-all`, null, { params: { repo_path: repoPath } })
}

/** 取消全部暂存 */
export async function unstageAll(repoPath = "."): Promise<void> {
  await apiClient.post(`${GIT_BASE}/unstage-all`, null, { params: { repo_path: repoPath } })
}

/** 提交 */
export async function commit(repoPath: string, message: string): Promise<void> {
  await apiClient.post(`${GIT_BASE}/commit`, { repo_path: repoPath, message })
}

/** 推送 */
export async function push(repoPath: string, remote = "origin", branch?: string): Promise<void> {
  await apiClient.post(`${GIT_BASE}/push`, { repo_path: repoPath, remote, branch })
}

/** 拉取 */
export async function pull(repoPath: string, remote = "origin", branch?: string): Promise<void> {
  await apiClient.post(`${GIT_BASE}/pull`, { repo_path: repoPath, remote, branch })
}

/** 丢弃文件更改 */
export async function discardChanges(repoPath: string, filePath: string): Promise<void> {
  await apiClient.post(`${GIT_BASE}/discard`, { repo_path: repoPath, file_path: filePath })
}

/** 获取差异 */
export async function getDiff(
  repoPath: string,
  file?: string,
  staged?: boolean,
): Promise<DiffEntry[]> {
  const { data } = await apiClient.post(`${GIT_BASE}/diff`, {
    repo_path: repoPath,
    file: file ?? null,
    staged: staged ?? false,
  })
  return data
}

/** 列出分支 */
export async function listBranches(repoPath = "."): Promise<BranchEntry[]> {
  const { data } = await apiClient.get(`${GIT_BASE}/branches`, { params: { repo_path: repoPath } })
  return data
}

/** 切换/创建分支 */
export async function checkoutBranch(
  repoPath: string,
  branch: string,
  createNew = false,
): Promise<void> {
  await apiClient.post(`${GIT_BASE}/checkout`, { repo_path: repoPath, branch, create_new: createNew })
}

/** 提交日志 */
export async function getLog(
  repoPath: string,
  limit = 20,
  branch?: string,
  file?: string,
): Promise<CommitEntry[]> {
  const { data } = await apiClient.get(`${GIT_BASE}/log`, {
    params: { repo_path: repoPath, limit, branch: branch ?? undefined, file: file ?? undefined },
  })
  return data
}

/** Stash (push 或 pop) */
export async function stash(
  repoPath: string,
  message?: string,
  pop = false,
): Promise<void> {
  await apiClient.post(`${GIT_BASE}/stash`, { repo_path: repoPath, message: message ?? null, pop })
}

/** Blame */
export async function blame(repoPath: string, filePath: string): Promise<BlameLine[]> {
  const { data } = await apiClient.post(`${GIT_BASE}/blame`, {
    repo_path: repoPath,
    file_path: filePath,
  })
  return data
}

/** 远程仓库列表 */
export async function listRemotes(repoPath = "."): Promise<RemoteEntry[]> {
  const { data } = await apiClient.get(`${GIT_BASE}/remotes`, { params: { repo_path: repoPath } })
  return data
}

/** 克隆仓库 */
export async function cloneRepo(
  url: string,
  target: string,
  branch?: string,
): Promise<{ ok: boolean; path: string }> {
  const { data } = await apiClient.post(`${GIT_BASE}/clone`, null, {
    params: { url, target, branch: branch ?? undefined },
  })
  return data
}
