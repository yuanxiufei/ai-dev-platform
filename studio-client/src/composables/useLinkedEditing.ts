/**
 * useLinkedEditing.ts — 链接编辑 (成对标签/变量同步编辑)
 *
 * 对标 VSCode editor/contrib/linkedEditing/
 * 支持: HTML/JSX 标签对、同名变量引用、函数/类定义与引用
 * Session 55: 对接后端 /system/lsp/linked-editing API
 */
import { ref, readonly } from "vue"
import { apiClient } from "@/api/client"

export interface LinkedRange {
  start_line: number
  start_column: number
  end_line: number
  end_column: number
}

export interface LinkedEditingResult {
  ranges: LinkedRange[]
  word_pattern: string
}

export function useLinkedEditing() {
  const ranges = ref<LinkedRange[]>([])
  const wordPattern = ref("")
  const loading = ref(false)
  const error = ref<string | null>(null)
  const sourcePosition = ref<{ line: number; column: number } | null>(null)

  /** 从后端获取链接编辑范围 */
  async function fetchLinkedRanges(
    content: string,
    language: string,
    line: number,
    column: number,
  ): Promise<LinkedEditingResult | null> {
    loading.value = true
    error.value = null
    sourcePosition.value = { line, column }
    try {
      const res = await apiClient.post("/system/lsp/linked-editing", {
        content,
        language,
        position_line: line,
        position_column: column,
      })
      ranges.value = res.data?.ranges ?? []
      wordPattern.value = res.data?.word_pattern ?? ""
      return res.data
    } catch (e: any) {
      error.value = e?.message ?? "Failed to fetch linked ranges"
      return null
    } finally {
      loading.value = false
    }
  }

  /** 前端 fallback — 全文本匹配同名标识符 */
  function computeLocal(
    content: string,
    line: number,
    column: number,
  ): LinkedEditingResult {
    const lines = content.split("\n")
    if (line >= lines.length) return { ranges: [], word_pattern: "" }

    const ln = lines[line]
    let start = column, end = column
    if (column < ln.length && (ln[column]?.match(/[\w-]/) ?? false)) {
      while (start > 0 && (ln[start - 1]?.match(/[\w-]/) ?? false)) start--
      while (end < ln.length && (ln[end]?.match(/[\w-]/) ?? false)) end++
    } else {
      return { ranges: [], word_pattern: "" }
    }

    const word = ln.slice(start, end)
    if (!word || word.length === 0) return { ranges: [], word_pattern: "" }
    sourcePosition.value = { line, column }

    const pattern = word.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    const allRanges: LinkedRange[] = []

    for (let i = 0; i < lines.length; i++) {
      const re = new RegExp(`\\b${pattern}\\b`, "g")
      let m: RegExpExecArray | null
      while ((m = re.exec(lines[i])) !== null) {
        allRanges.push({
          start_line: i, start_column: m.index,
          end_line: i, end_column: m.index + word.length,
        })
      }
    }

    ranges.value = allRanges
    wordPattern.value = pattern

    return { ranges: allRanges, word_pattern: pattern }
  }

  /** 检测光标是否在 HTML/JSX 标签名上 */
  function detectTagPair(
    content: string,
    line: number,
    column: number,
  ): LinkedEditingResult | null {
    const lines = content.split("\n")
    if (line >= lines.length) return null

    const ln = lines[line]
    // 匹配 <tagname 或 </tagname
    const tagRe = /<\/?([\w-]+)/g
    let m: RegExpExecArray | null
    while ((m = tagRe.exec(ln)) !== null) {
      if (m.index + 1 <= column && column <= m.index + m[0].length) {
        const tagName = m[1]
        sourcePosition.value = { line, column }

        const ranges: LinkedRange[] = []
        // 当前标签
        ranges.push({
          start_line: line, start_column: m.index + (m[0].startsWith("</") ? 2 : 1),
          end_line: line, end_column: m.index + (m[0].startsWith("</") ? 2 : 1) + tagName.length,
        })

        const isOpenTag = !m[0].startsWith("</")
        // 查找配对标签
        const openRe = new RegExp(`<(?:${tagName})\\b`, "g")
        const closeRe = new RegExp(`</${tagName}>`, "g")
        for (let i = 0; i < lines.length; i++) {
          if (i === line) continue
          if (isOpenTag) {
            let cm: RegExpExecArray | null
            while ((cm = closeRe.exec(lines[i])) !== null) {
              ranges.push({
                start_line: i, start_column: cm.index + 2,
                end_line: i, end_column: cm.index + 2 + tagName.length,
              })
              break
            }
          } else {
            let om: RegExpExecArray | null
            while ((om = openRe.exec(lines[i])) !== null) {
              ranges.push({
                start_line: i, start_column: om.index + 1,
                end_line: i, end_column: om.index + 1 + tagName.length,
              })
              break
            }
          }
        }

        ranges.value = ranges
        wordPattern.value = tagName.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
        return { ranges, word_pattern: wordPattern.value }
      }
    }

    return null
  }

  /** 生成装饰器位置 (Monaco decoration options) */
  function getDecorations(): Array<{
    range: { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number }
    options: { className: string; inlineClassName?: string }
  }> {
    return ranges.value.map(r => ({
      range: {
        startLineNumber: r.start_line + 1,
        startColumn: r.start_column + 1,
        endLineNumber: r.end_line + 1,
        endColumn: r.end_column + 1,
      },
      options: {
        className: "linked-editing-range",
        inlineClassName: "linked-editing-inline",
      },
    }))
  }

  function reset() {
    ranges.value = []
    wordPattern.value = ""
    sourcePosition.value = null
    error.value = null
  }

  return {
    ranges: readonly(ranges),
    wordPattern: readonly(wordPattern),
    sourcePosition: readonly(sourcePosition),
    loading: readonly(loading),
    error: readonly(error),
    fetchLinkedRanges,
    computeLocal,
    detectTagPair,
    getDecorations,
    reset,
  }
}
