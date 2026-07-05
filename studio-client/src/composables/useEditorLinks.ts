/**
 * useEditorLinks — VSCode 编辑器链接检测
 *
 * 借鉴: VSCode src/vs/editor/contrib/links/browser/links.ts
 *
 * 检测代码中的 URL 和文件路径链接，提供 Ctrl+Click 跳转能力。
 */

import { type Ref } from "vue"

export interface EditorLink {
  /** 链接 URL 或文件路径 */
  url: string
  /** 链接类型 */
  type: "url" | "file" | "npm" | "import"
  /** 在文本中的起始位置 (0-based) */
  start: number
  /** 在文本中的结束位置 (0-based) */
  end: number
  /** 所在的工具提示文本 */
  tooltip?: string
}

const URL_REGEX = /https?:\/\/[^\s"'`<>(){}[\]]+/g
const FILE_PATH_REGEX = /(?:\.\/|\.\.\/|\/)[^\s"'`<>(){}[\]]+/g
const NPM_REGEX = /"([@a-z][\w./-]*)"\s*from\s*['"]([^'"]+)['"]/g

/**
 * 检测文本中的链接
 */
export function detectLinks(text: string): EditorLink[] {
  const links: EditorLink[] = []

  // URL 链接
  let match: RegExpExecArray | null
  URL_REGEX.lastIndex = 0
  while ((match = URL_REGEX.exec(text)) !== null) {
    links.push({
      url: match[0],
      type: "url",
      start: match.index,
      end: match.index + match[0].length,
      tooltip: `打开 ${match[0]}`,
    })
  }

  // 文件路径链接
  FILE_PATH_REGEX.lastIndex = 0
  while ((match = FILE_PATH_REGEX.exec(text)) !== null) {
    // 避免和 URL 重叠
    const isUrl = links.some(l => l.type === "url" && match!.index >= l.start && match!.index < l.end)
    if (!isUrl) {
      links.push({
        url: match[0],
        type: "file",
        start: match.index,
        end: match.index + match[0].length,
        tooltip: `打开文件 ${match[0]}`,
      })
    }
  }

  // NPM 包导入链接
  NPM_REGEX.lastIndex = 0
  while ((match = NPM_REGEX.exec(text)) !== null) {
    const pkgName = match[2]
    links.push({
      url: `https://www.npmjs.com/package/${pkgName}`,
      type: "npm",
      start: match.index,
      end: match.index + match[0].length,
      tooltip: `查看 npm 包: ${pkgName}`,
    })
  }

  return links
}

/**
 * 打开链接
 * @param link 链接对象
 * @param options 可选配置: onOpenFile 文件打开回调
 */
export function openLink(
  link: EditorLink,
  options?: { onOpenFile?: (filePath: string) => void },
): void {
  switch (link.type) {
    case "url":
    case "npm":
      window.open(link.url, "_blank", "noopener,noreferrer")
      break
    case "file":
      options?.onOpenFile?.(link.url)
      break
    case "import":
      // 导入链接：提取模块路径
      const importMatch = link.url.match(/from\s+['"]([^'"]+)['"]/)
      if (importMatch) {
        const modulePath = importMatch[1]
        if (modulePath.startsWith("./") || modulePath.startsWith("../")) {
          options?.onOpenFile?.(modulePath)
        } else {
          window.open(`https://www.npmjs.com/package/${modulePath}`, "_blank", "noopener,noreferrer")
        }
      }
      break
  }
}

/**
 * Composable 用法
 * @param contentRef 文本内容的 ref
 * @param onOpenFile 文件打开回调
 */
export function useEditorLinks(
  contentRef?: Ref<string>,
  onOpenFile?: (filePath: string) => void,
) {
  /** 获取当前文本中的所有链接 */
  function scanLinks(text?: string): EditorLink[] {
    const content = text ?? contentRef?.value ?? ""
    return detectLinks(content)
  }

  /** 处理 Ctrl+Click 链接跳转 */
  function handleCtrlClick(
    event: MouseEvent,
    lineText: string,
    column: number,
  ): boolean {
    if (!event.ctrlKey && !event.metaKey) return false

    const links = detectLinks(lineText)
    for (const link of links) {
      if (column >= link.start && column <= link.end) {
        event.preventDefault()
        openLink(link, { onOpenFile })
        return true
      }
    }
    return false
  }

  return {
    scanLinks,
    handleCtrlClick,
    detectLinks,
    openLink,
  }
}
