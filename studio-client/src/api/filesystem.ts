import apiClient from "./client"

// ============================================
// 文件系统 CRUD API — 安全限制在 PROJECT_ROOT 内
// ============================================

export interface FileEntry {
  name: string
  path: string
  type: "file" | "directory"
  size_bytes: number
  modified_at: number
  extension: string
  is_hidden: boolean
}

export interface FileInfo {
  name: string
  path: string
  type: "file" | "directory"
  size_bytes: number
  modified_at: number
  created_at: number
  extension: string
  is_hidden: boolean
  is_readable: boolean
  is_writable: boolean
}

export const filesystemApi = {
  /** 列出目录内容 */
  listDir: (path = ".", showHidden = false) =>
    apiClient.get("/system/filesystem/list", { params: { path, show_hidden: showHidden } }),

  /** 读取文件内容（文本或 base64 编码） */
  readFile: (path: string, encoding = "utf-8") =>
    apiClient.get("/system/filesystem/read", { params: { path, encoding } }),

  /** 写入文件（自动创建父目录） */
  writeFile: (path: string, content: string, encoding = "utf-8") =>
    apiClient.post("/system/filesystem/write", { path, content, encoding }),

  /** 创建目录 */
  mkdir: (path: string, parents = true) =>
    apiClient.post("/system/filesystem/mkdir", { path, parents }),

  /** 移动文件/目录 */
  move: (source: string, destination: string) =>
    apiClient.post("/system/filesystem/move", { source, destination }),

  /** 复制文件/目录 */
  copy: (source: string, destination: string, overwrite = false) =>
    apiClient.post("/system/filesystem/copy", { source, destination, overwrite }),

  /** 删除文件/目录 */
  delete: (path: string, recursive = false) =>
    apiClient.post("/system/filesystem/delete", { path, recursive }),

  /** 获取文件/目录详细信息 */
  getInfo: (path: string) =>
    apiClient.get("/system/filesystem/info", { params: { path } }),
}
