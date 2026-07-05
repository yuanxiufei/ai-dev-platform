/**
 * CodeBuddy IDE — Git Blame (GitLens 风格行归因)
 *
 * Session 40: 编辑器右侧装订线显示每行的 Git 提交信息
 * 借鉴: GitLens / VSCode blame annotations
 *
 * 功能:
 * - 通过 git blame 获取每行最后修改的提交者+时间
 * - 生成 Monaco editor contentWidget 显示悬浮 blame 信息
 * - 生成 Monaco glyphMargin decorations 显示简短 author
 */

import { computed, ref } from "vue"
import { isTauriEnv } from "@/stores/shared"

/** 单行 blame 信息 */
export interface BlameLine {
  lineNumber: number
  commitHash: string   // 7-char short hash
  author: string
  date: string         // ISO date
  summary: string      // commit message
  timeAgo: string      // "2 days ago" 格式
}

/** Blame 查询结果 */
export interface BlameResult {
  filePath: string
  lines: BlameLine[]
}

/** 计算相对时间 (e.g. "3 hours ago") */
function timeAgo(dateStr: string): string {
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const seconds = Math.floor((now - then) / 1000)

  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  const months = Math.floor(days / 30)
  if (months < 12) return `${months}mo ago`
  return `${Math.floor(months / 12)}y ago`
}

/** 解析 git blame 输出 */
function parseBlameOutput(raw: string): BlameLine[] {
  const lines: BlameLine[] = []
  // git blame --porcelain 输出格式:
  // <commit-hash> <orig-line> <final-line> <num-lines>
  // author <author>
  // author-time <unix-timestamp>
  // summary <message>
  // ...
  const blocks = raw.split("\n")

  let currentLine = 0
  for (let i = 0; i < blocks.length; i++) {
    const line = blocks[i]

    // Match: ^40hex-hash orig-line final-line num-lines
    const headerMatch = line.match(/^([0-9a-f]{40})\s+\d+\s+(\d+)/)
    if (headerMatch) {
      const hash = headerMatch[1].substring(0, 7)
      const lineNum = parseInt(headerMatch[2])
      let author = "unknown"
      let timestamp = ""
      let summary = ""

      // Read subsequent porcelain lines until next commit or EOF
      for (let j = i + 1; j < blocks.length; j++) {
        const pl = blocks[j]
        if (pl.startsWith("author ")) {
          author = pl.substring(7)
        } else if (pl.startsWith("author-time ")) {
          const ts = parseInt(pl.substring(12)) * 1000
          timestamp = new Date(ts).toISOString()
        } else if (pl.startsWith("summary ")) {
          summary = pl.substring(8)
        } else if (pl.startsWith("filename ") || pl.match(/^([0-9a-f]{40})\s+\d+\s+\d+/)) {
          // New entry or end of porcelain block
          break
        }
      }

      lines.push({
        lineNumber: lineNum,
        commitHash: hash,
        author,
        date: timestamp,
        summary,
        timeAgo: timestamp ? timeAgo(timestamp) : "",
      })
    }
  }

  return lines
}

/**
 * useGitBlame — Git 行归因状态
 *
 * 用法:
 *   const blame = useGitBlame()
 *   await blame.loadBlame(repoDir, filePath)
 *   blame.lines  // BlameLine[]
 */
export function useGitBlame() {
  const lines = ref<BlameLine[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const currentFilePath = ref("")

  /** 是否启用 blame (Tauri 或后端 API 均可) */
  const available = computed(() => isTauriEnv() || !!_wsRoot)
  let _wsRoot = ''

  /** 加载文件的 blame 信息 */
  async function loadBlame(workspaceRoot: string, filePath: string): Promise<void> {
    _wsRoot = workspaceRoot
    if (!workspaceRoot || !filePath || !available.value) {
      lines.value = []
      currentFilePath.value = filePath
      return
    }

    loading.value = true
    error.value = null
    currentFilePath.value = filePath

    try {
      if (isTauriEnv()) {
        const { invoke } = await import("@tauri-apps/api/core")
        const raw: string = await invoke("git_blame", {
          repoDir: workspaceRoot,
          filePath: filePath,
        })
        if (raw) {
          lines.value = parseBlameOutput(raw)
        } else {
          lines.value = []
        }
      } else {
        // Web 模式: 调用后端 REST API
        const { blame } = await import('@/api/git')
        const result = await blame(workspaceRoot, filePath)
        lines.value = result.map(l => ({
          lineNumber: l.line_number,
          commitHash: l.commit_hash,
          author: l.author,
          date: l.date,
          summary: l.summary,
          timeAgo: l.time_ago,
        }))
      }
    } catch (e: any) {
      console.warn("[GitBlame] Failed:", e.toString())
      error.value = e.toString()
      lines.value = []
    } finally {
      loading.value = false
    }
  }

  /** 清除 blame 数据 */
  function clear() {
    lines.value = []
    loading.value = false
    error.value = null
    currentFilePath.value = ""
  }

  /** 获取指定行的 blame 信息 */
  function getBlameForLine(lineNumber: number): BlameLine | null {
    return lines.value.find(l => l.lineNumber === lineNumber) ?? null
  }

  return {
    lines,
    loading,
    error,
    currentFilePath,
    available,
    loadBlame,
    clear,
    getBlameForLine,
  }
}
