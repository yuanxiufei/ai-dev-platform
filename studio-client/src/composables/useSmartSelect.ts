/**
 * useSmartSelect.ts — 智能选择 (语义范围扩展)
 *
 * 对标 VSCode editor/contrib/smartSelect/
 * 支持: word → line → block → function → class → file 逐层扩展
 * Session 55: 对接后端 /system/lsp/selection-ranges API
 */
import { ref, readonly } from "vue"
import { apiClient } from "@/api/client"

export interface Range {
  start_line: number
  start_column: number
  end_line: number
  end_column: number
}

export interface SelectionRangeNode {
  range: Range
  parent: SelectionRangeNode | null
}

export function useSmartSelect() {
  const currentLevel = ref(0)
  const maxLevel = ref(0)
  const ranges = ref<SelectionRangeNode | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  /** 从后端获取语义选择范围 */
  async function fetchRanges(
    content: string,
    language: string,
    line: number,
    column: number,
  ): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const res = await apiClient.post("/system/lsp/selection-ranges", {
        content,
        language,
        positions: [{ line, column }],
      })
      if (res.data && res.data.length > 0) {
        ranges.value = res.data[0]
        // 计算层级深度
        let depth = 0
        let node: SelectionRangeNode | null = res.data[0]
        while (node) { depth++; node = node.parent }
        maxLevel.value = depth
        currentLevel.value = 0
      }
    } catch (e: any) {
      error.value = e?.message ?? "Failed to fetch selection ranges"
    } finally {
      loading.value = false
    }
  }

  /** 向前端 fallback 计算范围 (离线模式) */
  function computeLocal(
    content: string,
    line: number,
    column: number,
  ): SelectionRangeNode {
    const lines = content.split("\n")
    if (line >= lines.length) {
      return { range: { start_line: line, start_column: column, end_line: line, end_column: column }, parent: null }
    }

    const ln = lines[line]
    const levels: Range[] = []

    // Level 1: token
    let start = column, end = column
    if (column < ln.length && (ln[column].match(/\w/) || ln[column] === "_")) {
      while (start > 0 && (ln[start - 1].match(/\w/) || ln[start - 1] === "_")) start--
      while (end < ln.length && (ln[end].match(/\w/) || ln[end] === "_")) end++
    }
    levels.push({ start_line: line, start_column: start, end_line: line, end_column: end || column + 1 })

    // Level 2: line
    levels.push({ start_line: line, start_column: 0, end_line: line, end_column: ln.length })

    // Level 3: indentation block
    const currentIndent = ln.length - ln.trimStart().length
    let blockStart = line, blockEnd = line
    for (let i = line - 1; i >= 0; i--) {
      const indent = lines[i].length - lines[i].trimStart().length
      if (indent < currentIndent) break
      blockStart = i
    }
    for (let i = line + 1; i < lines.length; i++) {
      if (!lines[i].trim()) { blockEnd = i; continue }
      const indent = lines[i].length - lines[i].trimStart().length
      if (indent < currentIndent) break
      blockEnd = i
    }
    levels.push({ start_line: blockStart, start_column: 0, end_line: blockEnd, end_column: lines[blockEnd]?.length ?? 0 })

    // Level 4: full document
    levels.push({ start_line: 0, start_column: 0, end_line: lines.length - 1, end_column: lines[lines.length - 1]?.length ?? 0 })

    // Build chain
    let result: SelectionRangeNode | null = null
    for (const r of levels.reverse()) {
      result = { range: r, parent: result }
    }

    ranges.value = result ?? levels[levels.length - 1]
    maxLevel.value = levels.length
    currentLevel.value = 0
    return result!
  }

  /** 扩展到下一个更大范围 */
  function expand(): Range | null {
    if (!ranges.value) return null
    if (ranges.value.parent) {
      ranges.value = ranges.value.parent
      currentLevel.value = Math.min(currentLevel.value + 1, maxLevel.value)
    }
    return ranges.value.range
  }

  /** 收缩到上一个更小范围 */
  function shrink(): Range | null {
    // 需要通过 rebuild 回溯 — 这里只支持 expand 方向
    // shrink 需要重新 fetch 或本地重建
    if (currentLevel.value > 0) {
      currentLevel.value--
    }
    return ranges.value?.range ?? null
  }

  /** 获取当前范围 */
  function currentRange(): Range | null {
    return ranges.value?.range ?? null
  }

  /** 重置 */
  function reset() {
    ranges.value = null
    currentLevel.value = 0
    maxLevel.value = 0
    error.value = null
  }

  return {
    ranges: readonly(ranges),
    currentLevel: readonly(currentLevel),
    maxLevel: readonly(maxLevel),
    loading: readonly(loading),
    error: readonly(error),
    fetchRanges,
    computeLocal,
    expand,
    shrink,
    currentRange,
    reset,
  }
}
