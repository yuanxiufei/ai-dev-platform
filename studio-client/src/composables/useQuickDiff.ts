/**
 * CodeBuddy IDE — QuickDiff (VSCode 行内差异装饰)
 *
 * Session 26: 编辑器 gutter 显示修改/新增/删除行标记
 * 借鉴: VSCode QuickDiff / DirtyDiffDecorator
 *
 * 功能:
 * - 对比 currentContent 和 originalContent，识别修改/新增/删除行
 * - 生成 Monaco deltaDecorations 配置，显示在 glyphMargin + overviewRuler
 * - 返回三种状态: modified(黄), added(绿), deleted(红)
 */

export interface DiffLine {
  lineNumber: number
  type: "modified" | "added" | "deleted"
  /** 原始行号（modified 类型） */
  oldLineNumber?: number
}

/** 简单行级别差异对比（Myers启发式，仅识别变更行） */
export function computeLineDiff(
  original: string,
  current: string,
): DiffLine[] {
  const origLines = original.split("\n")
  const currLines = current.split("\n")
  const result: DiffLine[] = []

  // 最长公共子序列 (LCS) 快速逼近
  const lcs: number[] = []
  let oi = 0, ci = 0

  while (oi < origLines.length || ci < currLines.length) {
    if (oi < origLines.length && ci < currLines.length) {
      const oLine = origLines[oi].trim()
      const cLine = currLines[ci].trim()
      if (oLine === cLine) {
        // Match — skip
        oi++; ci++
        continue
      }
    }

    // 尝试向前看 3 行找匹配
    let matched = false
    for (let look = 1; look <= 5 && !matched; look++) {
      if (ci + look < currLines.length && oi < origLines.length
        && origLines[oi].trim() === currLines[ci + look].trim()) {
        // 当前行是新增的 (in current but not in original)
        for (let k = 0; k < look; k++) {
          result.push({ lineNumber: ci + k + 1, type: "added" })
        }
        ci += look
        matched = true
      } else if (oi + look < origLines.length && ci < currLines.length
        && origLines[oi + look].trim() === currLines[ci].trim()) {
        // 原始行在当前中被删除
        for (let k = 0; k < look; k++) {
          result.push({ lineNumber: ci + 1, type: "deleted", oldLineNumber: oi + k + 1 })
        }
        oi += look
        matched = true
      } else if (oi + look < origLines.length && ci + look < currLines.length
        && origLines[oi + look].trim() === currLines[ci + look].trim()) {
        // 这两行是修改的
        for (let k = 0; k < look; k++) {
          result.push({
            lineNumber: ci + k + 1,
            type: "modified",
            oldLineNumber: oi + k + 1,
          })
        }
        oi += look; ci += look
        matched = true
      }
    }

    if (!matched) {
      // 无匹配，按单行修改处理
      if (oi < origLines.length && ci < currLines.length) {
        result.push({ lineNumber: ci + 1, type: "modified", oldLineNumber: oi + 1 })
        oi++; ci++
      } else if (ci < currLines.length) {
        while (ci < currLines.length) {
          result.push({ lineNumber: ci + 1, type: "added" })
          ci++
        }
      } else if (oi < origLines.length) {
        // 全部删除 → 标记在当前行之后
        const lastLine = currLines.length > 0 ? currLines.length : 1
        while (oi < origLines.length) {
          result.push({ lineNumber: lastLine, type: "deleted", oldLineNumber: oi + 1 })
          oi++
        }
      }
    }
  }

  return result
}

/** 将 DiffLine 转换为 Monaco IModelDeltaDecoration[] */
export function diffLinesToDecorations(
  diffLines: DiffLine[],
): Array<{
  range: { startLineNumber: number; startColumn: number; endLineNumber: number; endColumn: number }
  options: any
}> {
  const GLYPH_COLORS: Record<string, string> = {
    modified: "#d29922", // 黄色
    added: "#2ea043",    // 绿色
    deleted: "#f85149",  // 红色
  }

  return diffLines.map(d => ({
    range: { startLineNumber: d.lineNumber, startColumn: 1, endLineNumber: d.lineNumber, endColumn: 1 },
    options: {
      isWholeLine: true,
      className: `qd-${d.type}-line`,
      glyphMarginClassName: `qd-glyph-${d.type}`,
      overviewRuler: {
        color: GLYPH_COLORS[d.type],
        position: 3, // OverviewRulerLane.Left
      },
      glyphMarginHoverMessage: d.type === "deleted"
        ? { value: `**删除** — 原始第 ${d.oldLineNumber} 行已被删除` }
        : d.type === "added"
        ? { value: `**新增** — 新增 ${d.lineNumber} 行` }
        : { value: `**已修改** — 原始第 ${d.oldLineNumber} 行 → 第 ${d.lineNumber} 行` },
    },
  }))
}
