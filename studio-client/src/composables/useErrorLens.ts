/**
 * CodeBuddy IDE — Error Lens (Session 45)
 *
 * 对标 VSCode Error Lens 扩展:
 *   - 在诊断行末尾内联显示 error/warning/info 消息
 *   - Monaco deltaDecorations API 实现
 *   - 从 ProblemsPanel 后端 API 获取诊断数据
 *   - 支持 show/hide 切换
 */

import type * as monacoNs from "monaco-editor"
import type { ShallowRef } from "vue"

/** 诊断条目 */
export interface DiagnosticItem {
  /** 文件名 */
  file: string
  /** 行号 (1-based) */
  line: number
  /** 列号 (1-based) */
  column: number
  /** 消息文本 */
  message: string
  /** 严重级别 */
  severity: "error" | "warning" | "info"
  /** 规则代码 */
  code?: string
}

/** 行内装饰显示每条诊断消息 */
export function useErrorLens(
  editorRef: ShallowRef<monacoNs.editor.IStandaloneCodeEditor | null>,
  monacoRef: ShallowRef<typeof monacoNs | null>,
) {
  let errorLensDecorations: string[] = []

  /** 严重级别 → CSS 类名 */
  const SEVERITY_CLASS: Record<string, string> = {
    error: "error-lens-error",
    warning: "error-lens-warning",
    info: "error-lens-info",
  }

  /** 严重级别 → 图标前缀 */
  const SEVERITY_PREFIX: Record<string, string> = {
    error: "✘",
    warning: "⚠",
    info: "ℹ",
  }

  /** 严重级别 → 前景色 */
  const SEVERITY_FG: Record<string, string> = {
    error: "#f85149",
    warning: "#d29922",
    info: "#61AFEF",
  }

  /** 严重级别 → 背景色（带透明度） */
  const SEVERITY_BG: Record<string, string> = {
    error: "rgba(248, 81, 73, 0.08)",
    warning: "rgba(210, 153, 34, 0.08)",
    info: "rgba(97, 174, 239, 0.08)",
  }

  /**
   * 应用诊断行内装饰
   *
   * @param diagnostics 诊断条目列表
   * @param currentFile 当前文件路径（只显示当前文件的诊断）
   */
  function apply(diagnostics: DiagnosticItem[], currentFile?: string): void {
    const editor = editorRef.value
    const monaco = monacoRef.value
    if (!editor || !monaco) return

    // 清除旧装饰
    clear(editor)

    // 筛选当前文件的诊断
    const filtered = currentFile
      ? diagnostics.filter(d => {
          // 模糊匹配文件名
          const dFile = d.file.replace(/\\/g, "/").toLowerCase()
          const cFile = (currentFile || "").replace(/\\/g, "/").toLowerCase()
          return dFile === cFile || dFile.endsWith("/" + cFile) || cFile.endsWith("/" + dFile)
        })
      : diagnostics

    if (filtered.length === 0) return

    // 按行合并：同一行多个诊断只显示第一个最严重的
    const lineMap = new Map<number, DiagnosticItem>()
    const severityOrder = { error: 0, warning: 1, info: 2 }
    for (const d of filtered) {
      const existing = lineMap.get(d.line)
      if (!existing || severityOrder[d.severity] < severityOrder[existing.severity]) {
        lineMap.set(d.line, d)
      }
    }

    const model = editor.getModel()
    if (!model) return

    const decorations: monacoNs.editor.IModelDeltaDecoration[] = []

    for (const [, diag] of lineMap) {
      if (diag.line < 1 || diag.line > model.getLineCount()) continue

      const lineMaxCol = model.getLineMaxColumn(diag.line)
      // 显示在行尾
      const endCol = lineMaxCol

      // 截断过长消息
      const msg = diag.message.length > 80
        ? diag.message.substring(0, 77) + "..."
        : diag.message

      const fullMessage = `${diag.message}${diag.code ? ` [${diag.code}]` : ""}`

      decorations.push({
        range: new monaco.Range(diag.line, endCol, diag.line, endCol),
        options: {
          isWholeLine: false,
          after: {
            content: `  ${SEVERITY_PREFIX[diag.severity]} ${msg}`,
            inlineClassName: SEVERITY_CLASS[diag.severity],
            cursorStops: monaco.editor.InjectedTextCursorStops.None,
          },
          hoverMessage: {
            value: `**${SEVERITY_PREFIX[diag.severity]} ${diag.severity.toUpperCase()}**  — ${fullMessage}`,
            isTrusted: true,
          },
          stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
          overviewRuler: {
            color: SEVERITY_FG[diag.severity],
            position: monaco.editor.OverviewRulerLane.Center,
          },
        },
      })
    }

    errorLensDecorations = editor.deltaDecorations(errorLensDecorations, decorations)
  }

  /** 清除所有 Error Lens 装饰 */
  function clear(editor?: monacoNs.editor.IStandaloneCodeEditor | null): void {
    const ed = editor || editorRef.value
    if (!ed || errorLensDecorations.length === 0) return
    ed.deltaDecorations(errorLensDecorations, [])
    errorLensDecorations = []
  }

  /**
   * 从 ProblemsPanel 扫描结果直接构建诊断列表并应用
   * 与 ProblemsPanel.vue 共享同一套扫描逻辑
   */
  function applyFromScan(content: string, language: string, filePath?: string): void {
    const editor = editorRef.value
    if (!editor) return

    const diagnostics: DiagnosticItem[] = []
    const lines = content.split("\n")

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      const lineNum = i + 1

      // TODO/FIXME/HACK/XXX → info
      if (/\b(TODO|FIXME|HACK|XXX)\b/.test(line)) {
        diagnostics.push({
          file: filePath || "untitled",
          line: lineNum,
          column: 1,
          message: line.trim().length > 60 ? line.trim().substring(0, 57) + "..." : line.trim(),
          severity: "info",
          code: "TODO",
        })
      }

      // console 语句 → warning
      if (/console\.(log|debug|warn)\(/.test(line) && /^(?!\s*\/\/)/.test(line)) {
        const m = line.match(/console\.(\w+)\(/)
        diagnostics.push({
          file: filePath || "untitled",
          line: lineNum,
          column: 1,
          message: `${m?.[1] ?? "log"} 调试语句`,
          severity: "warning",
          code: "no-console",
        })
      }

      // 空 catch → warning
      if (/catch\s*\([^)]*\)\s*\{\s*\}/.test(line)) {
        diagnostics.push({
          file: filePath || "untitled",
          line: lineNum,
          column: 1,
          message: "空的 catch 块",
          severity: "warning",
          code: "no-empty-catch",
        })
      }

      // var 声明 → warning (JS/TS)
      if (["javascript", "typescript", "javascriptreact", "typescriptreact"].includes(language)) {
        if (/\bvar\s+\w+\b/.test(line.replace(/['"`].*?['"`]/g, ""))) {
          diagnostics.push({
            file: filePath || "untitled",
            line: lineNum,
            column: 1,
            message: "使用 'var' 声明，建议改为 'let' 或 'const'",
            severity: "info",
            code: "no-var",
          })
        }
      }
    }

    apply(diagnostics, filePath)
  }

  return {
    apply,
    clear,
    applyFromScan,
    /** 获取当前装饰 ID（供外部判断是否有诊断） */
    hasDecorations: () => errorLensDecorations.length > 0,
  }
}
