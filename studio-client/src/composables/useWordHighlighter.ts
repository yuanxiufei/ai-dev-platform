/**
 * CodeBuddy IDE — Word Highlighter (单词出现位置高亮)
 *
 * 借鉴: VSCode editor/contrib/wordHighlighter — WordHighlighterContribution
 * Session 46: 选中单词时高亮文档中所有相同单词（装饰器实现）
 */
import type * as monacoNs from "monaco-editor"
import type { ShallowRef } from "vue"

/**
 * WordHighlighter 逻辑
 * 文档级装饰器高亮所有匹配单词
 */
export function useWordHighlighter(
  editorRef: ShallowRef<monacoNs.editor.IStandaloneCodeEditor | null>,
) {
  let decorationIds: string[] = []
  let lastWord: string | null = null
  let enabled = true
  /** 允许的最大高亮数，避免性能问题 */
  const MAX_HIGHLIGHTS = 500

  /** 高亮文档中所有匹配的单词 */
  function highlight(editor: monacoNs.editor.IStandaloneCodeEditor, monaco: typeof monacoNs): void {
    if (!enabled) return
    const model = editor.getModel()
    const sel = editor.getSelection()
    if (!model || !sel || sel.isEmpty()) {
      clear(editor)
      return
    }

    const word = model.getWordAtPosition({
      lineNumber: sel.startLineNumber,
      column: sel.startColumn,
    })

    if (!word || word.word === lastWord) return

    clear(editor)
    lastWord = word.word

    // 排除关键字和短单词（单字符、数字等）
    if (word.word.length < 2 || /^\d+$/.test(word.word)) return

    const excluded = new Set([
      "if", "else", "for", "while", "do", "switch", "case", "break", "continue",
      "return", "throw", "try", "catch", "finally", "new", "delete", "typeof",
      "void", "this", "super", "class", "extends", "import", "export", "default",
      "from", "as", "async", "await", "yield", "function", "var", "let", "const",
      "true", "false", "null", "undefined", "NaN", "Infinity",
      "int", "float", "double", "string", "boolean", "number", "void", "any",
      "never", "unknown", "object", "symbol", "bigint", "readonly", "static",
      "public", "private", "protected", "abstract", "enum", "interface", "type",
      "implements", "namespace", "module", "declare", "global", "keyof", "infer",
      "get", "set", "of", "in", "is", "not", "and", "or", "to",
    ])
    if (excluded.has(word.word)) return

    // 在全文搜索匹配
    const matches = model.findMatches(
      word.word, false, true, true, null, true, MAX_HIGHLIGHTS,
    )

    if (!matches || matches.length <= 1) return // 只有当前一个匹配，不高亮

    const decos: monacoNs.editor.IModelDeltaDecoration[] = matches
      .filter(m => !m.range.equalsRange(sel)) // 排除当前选中词
      .map(m => ({
        range: m.range,
        options: {
          className: "word-highlight-match",
          inlineClassName: "word-highlight-match-text",
        },
      }))

    decorationIds = editor.deltaDecorations([], decos)
  }

  /** 清除所有高亮 */
  function clear(editor: monacoNs.editor.IStandaloneCodeEditor | null): void {
    lastWord = null
    if (editor && decorationIds.length > 0) {
      editor.deltaDecorations(decorationIds, [])
      decorationIds = []
    }
  }

  function setEnabled(v: boolean): void {
    enabled = v
    if (!enabled && editorRef.value) clear(editorRef.value)
  }

  return { highlight, clear, setEnabled, isEnabled: () => enabled }
}
