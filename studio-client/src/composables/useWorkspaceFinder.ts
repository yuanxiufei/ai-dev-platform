/**
 * useWorkspaceFinder — 工作区自动发现
 *
 * 对标 VSCode workbench/contrib/workspaces: WorkspacesFinderContribution
 * 当用户以单文件夹模式打开 IDE 时，自动扫描根目录下是否有 .code-workspace 文件。
 *
 * 工作机制:
 *   1. 监听 workspaceRoot 变化
 *   2. 列出根目录，查找 *.code-workspace 文件
 *   3. 发现 .code-workspace 文件时提示用户打开
 *   4. 多个文件时提供选择器
 */
import { watch, type Ref } from "vue"

interface WorkspaceFile {
  name: string
  path: string
}

/** 工作区自动发现 */
export function useWorkspaceFinder(
  workspaceRoot: Ref<string>,
  apiBase: string = "/api/v1",
) {
  let dismissedRoots = new Set<string>()
  let checking = false

  /** 扫描目录中的 .code-workspace 文件 */
  async function scanForWorkspaceFiles(rootPath: string): Promise<WorkspaceFile[]> {
    try {
      const resp = await fetch(
        `${apiBase}/system/filesystem/list?path=${encodeURIComponent(rootPath)}&pattern=*.code-workspace`,
      )
      if (!resp.ok) return []
      const data = await resp.json()
      const files: WorkspaceFile[] = []
      // 兼容两种响应格式: { data: [...] } 或 { files: [...] }
      const items = data.data || data.files || data || []
      for (const item of Array.isArray(items) ? items : []) {
        if (typeof item === "string" && item.endsWith(".code-workspace")) {
          files.push({ name: item, path: `${rootPath}/${item}`.replace(/\\/g, "/") })
        } else if (item.name && item.name.endsWith(".code-workspace")) {
          files.push({ name: item.name, path: item.path || item.name })
        }
      }
      return files
    } catch {
      return []
    }
  }

  /** 显示检测到的 .code-workspace 通知 */
  function showWorkspaceNotification(files: WorkspaceFile[]): void {
    if (files.length === 0) return

    // 使用自定义事件通知系统（如果存在的话）
    // 回退：直接 window.confirm / 或 emit 事件
    const event = new CustomEvent("ide:workspace-files-found", {
      detail: { files, rootPath: workspaceRoot.value },
    })
    window.dispatchEvent(event)
  }

  /** 启动监听 */
  async function checkWorkspaceRoot(rootPath: string): Promise<void> {
    if (!rootPath || checking) return
    if (dismissedRoots.has(rootPath)) return

    // 仅对单文件夹模式检查（.code-workspace 文件本身是 workspace 模式）
    if (rootPath.endsWith(".code-workspace")) return

    checking = true
    try {
      const files = await scanForWorkspaceFiles(rootPath)
      if (files.length > 0) {
        showWorkspaceNotification(files)
      }
    } catch {
      // 静默处理
    } finally {
      checking = false
    }
  }

  /** 标记已忽略 */
  function dismissRoot(rootPath: string): void {
    dismissedRoots.add(rootPath)
  }

  /** 监听器 */
  let stopWatch: (() => void) | null = null

  function start(): void {
    if (stopWatch) return
    stopWatch = watch(
      () => workspaceRoot.value,
      (root) => {
        if (root) checkWorkspaceRoot(root)
      },
      { immediate: true },
    )
  }

  function stop(): void {
    if (stopWatch) {
      stopWatch()
      stopWatch = null
    }
  }

  return {
    start,
    stop,
    dismissRoot,
    scanForWorkspaceFiles,
  }
}
