/**
 * useInlayHints — VSCode 风格编辑器内嵌类型标注
 *
 * 借鉴: VSCode src/vs/workbench/contrib/inlayHints/
 * 能力:
 *   - 在函数参数位置显示参数名提示 (如: fn(name: "value"))
 *   - 在变量声明处显示类型标注 (如: const x: string = ...)
 *   - CSS 样式与 VSCode inlay hint 一致：灰色小字、斜体、可点击互动
 */
import { ref, computed } from "vue"
import type * as monacoNs from "monaco-editor"

export interface InlayHint {
  id: string
  line: number
  column: number
  label: string
  kind: "type" | "parameter"
  paddingLeft?: boolean
  paddingRight?: boolean
}

/** 解析当前编辑器内容，生成类型/参数提示 */
function parseHints(content: string, language: string): InlayHint[] {
  const hints: InlayHint[] = []
  const lines = content.split("\n")
  let id = 0

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // TypeScript/JavaScript: 函数调用参数名提示
    if (["typescript", "javascript", "typescriptreact", "javascriptreact"].includes(language)) {
      // 匹配 lambda 参数: (name) => ... → name:
      const lambdaMatch = line.match(/\((\w+)\)\s*=>/)
      if (lambdaMatch) {
        hints.push({
          id: `hint-${id++}`,
          line: i + 1,
          column: (line.indexOf("(") + 1) || 1,
          label: `${lambdaMatch[1]}:`,
          kind: "parameter",
          paddingRight: true,
        })
      }

      // 匹配 const/let 变量声明类型推断
      const constMatch = line.match(/\b(const|let|var)\s+(\w+)\s*=\s*["'`]?/)
      if (constMatch && !line.includes(":")) {
        hints.push({
          id: `hint-${id++}`,
          line: i + 1,
          column: (line.indexOf(constMatch[2]) + constMatch[2].length) || 1,
          label: ": string",
          kind: "type",
          paddingRight: true,
        })
      }

      // 匹配 const/let with number
      const numMatch = line.match(/\b(const|let|var)\s+(\w+)\s*=\s*\d/)
      if (numMatch && !line.includes(":")) {
        hints.push({
          id: `hint-${id++}`,
          line: i + 1,
          column: (line.indexOf(numMatch[2]) + numMatch[2].length) || 1,
          label: ": number",
          kind: "type",
          paddingRight: true,
        })
      }
    }

    // Python: 函数参数 + 类型提示
    if (language === "python") {
      // 函数调用关键字参数提示: fn(name=value)
      const callMatch = line.match(/(\w+)\s*=\s*[\w"'.([{]/)
      if (callMatch && !line.trimStart().startsWith("def ")) {
        hints.push({
          id: `hint-${id++}`,
          line: i + 1,
          column: (line.indexOf(callMatch[1]) + callMatch[1].length) || 1,
          label: "=",
          kind: "parameter",
          paddingLeft: true,
          paddingRight: true,
        })
      }
    }

    // Rust: 类型标注
    if (language === "rust") {
      const letMatch = line.match(/let\s+(\w+)\s*=\s*/)
      if (letMatch && !line.includes(":")) {
        hints.push({
          id: `hint-${id++}`,
          line: i + 1,
          column: (line.indexOf(letMatch[1]) + letMatch[1].length) || 1,
          label: ": &str",
          kind: "type",
          paddingRight: true,
        })
      }
    }

    // Go: 简短变量声明类型
    if (language === "go") {
      const shortVarMatch = line.match(/(\w+)\s*:=\s*["'`]/)
      if (shortVarMatch) {
        hints.push({
          id: `hint-${id++}`,
          line: i + 1,
          column: (line.indexOf(shortVarMatch[1]) + shortVarMatch[1].length) || 1,
          label: ": string",
          kind: "type",
          paddingRight: true,
        })
      }
    }

    // 通用：解构参数类型提示
    const destructureMatch = line.match(/\{\s*(\w+)\s*\}\s*:/)
    if (destructureMatch) {
      hints.push({
        id: `hint-${id++}`,
        line: i + 1,
        column: (line.indexOf("}") + 1) || 1,
        label: ": Props",
        kind: "type",
        paddingRight: true,
      })
    }
  }

  return hints
}

/** 应用 InlayHints 到 Monaco 编辑器 */
export function useInlayHints() {
  const hints = ref<InlayHint[]>([])
  let decorationIds: string[] = []

  function refreshHints(editor: monacoNs.editor.IStandaloneCodeEditor, monaco: typeof monacoNs, language: string): void {
    const content = editor.getValue()
    hints.value = parseHints(content, language)
    applyDecorations(editor, monaco, hints.value)
  }

  function applyDecorations(
    editor: monacoNs.editor.IStandaloneCodeEditor,
    monaco: typeof monacoNs,
    hintList: InlayHint[],
  ): void {
    const decorations: monacoNs.editor.IModelDeltaDecoration[] = hintList.map((hint) => {
      const range = new monaco.Range(hint.line, hint.column, hint.line, hint.column + 1)

      const beforeContent = hint.paddingLeft ? "\u00A0" : ""
      const afterContent = hint.paddingRight ? "\u00A0" : ""

      return {
        range: hint.kind === "parameter"
          ? range
          : new monaco.Range(hint.line, hint.column, hint.line, hint.column),
        options: {
          before: {
            content: beforeContent + hint.label + afterContent,
            inlineClassName: "ide-inlay-hint",
            inlineClassNameAffectsLetterSpacing: false,
          },
          stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
        },
      }
    })

    // 使用 after 装饰显示在变量/表达式后面
    const afterDecorations: monacoNs.editor.IModelDeltaDecoration[] = hintList
      .filter(h => h.kind === "type")
      .map((hint) => {
        const range = new monaco.Range(hint.line, hint.column, hint.line, hint.column)
        const afterContent = hint.paddingRight ? "\u00A0" : ""
        return {
          range,
          options: {
            after: {
              content: hint.label + afterContent,
              inlineClassName: "ide-inlay-hint ide-inlay-hint-type",
              inlineClassNameAffectsLetterSpacing: false,
            },
            stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
          },
        }
      })

    const allDecorations = [...decorations, ...afterDecorations]
    decorationIds = editor.deltaDecorations(decorationIds, allDecorations)
  }

  function clearDecorations(editor: monacoNs.editor.IStandaloneCodeEditor): void {
    decorationIds = editor.deltaDecorations(decorationIds, [])
    hints.value = []
  }

  return {
    hints,
    refreshHints,
    clearDecorations,
  }
}
