/**
 * useSemanticTokens — VSCode 风格语义高亮
 *
 * 对标: VSCode semanticTokensProvider + DocumentSemanticTokensProvider
 * Session 53: 新增，连接后端 /system/lsp/semantic-tokens
 *
 * 将后端返回的语义 Token 解码为 Monaco decorations，
 * 按 token 类型应用不同 CSS 样式 (namespace/type/function/variable/...)
 */
import { ref, watch, onBeforeUnmount } from "vue"
import type * as monacoNs from "monaco-editor"
import * as lspApi from "@/api/lsp"

/* ========== Token 类型 → CSS 类名映射 ========== */

const TOKEN_CLASS_MAP: Record<string, string> = {
  namespace: "semantic-namespace",
  type: "semantic-type",
  class: "semantic-class",
  enum: "semantic-enum",
  interface: "semantic-interface",
  struct: "semantic-struct",
  typeParameter: "semantic-type-param",
  parameter: "semantic-parameter",
  variable: "semantic-variable",
  property: "semantic-property",
  enumMember: "semantic-enum-member",
  event: "semantic-event",
  function: "semantic-function",
  method: "semantic-method",
  macro: "semantic-macro",
  keyword: "semantic-keyword",
  modifier: "semantic-modifier",
  comment: "semantic-comment",
  string: "semantic-string",
  number: "semantic-number",
  regexp: "semantic-regexp",
  operator: "semantic-operator",
  decorator: "semantic-decorator",
}

/* ========== 默认 Tokens Legend (后端 /semantic-tokens/legend 的备份) ========== */

const DEFAULT_TOKEN_TYPES = [
  "namespace", "type", "class", "enum", "interface", "struct", "typeParameter",
  "parameter", "variable", "property", "enumMember", "event",
  "function", "method", "macro", "keyword", "modifier", "comment",
  "string", "number", "regexp", "operator", "decorator"
]

export function useSemanticTokens(
  getEditor: () => monacoNs.editor.IStandaloneCodeEditor | null,
  getContent: () => string,
  getLanguage: () => string,
  getFilePath: () => string,
) {
  const isEnabled = ref(true)
  const isPending = ref(false)
  const tokenCount = ref(0)
  let legend: string[] = [...DEFAULT_TOKEN_TYPES]
  let decorationIds: string[] = []

  /** 获取 legend 映射表 */
  async function loadLegend(): Promise<void> {
    try {
      const result = await lspApi.getSemanticTokensLegend()
      if (result.token_types?.length) {
        legend = result.token_types
      }
    } catch {
      // 使用默认 legend
    }
  }

  /** 解码 LSP 语义 Token 数据 (delta 编码 → 绝对位置) */
  function decodeTokens(data: number[]): Array<{
    line: number; column: number; length: number; typeIdx: number; modifiers: number
  }> {
    const tokens: Array<{ line: number; column: number; length: number; typeIdx: number; modifiers: number }> = []
    let line = 0, column = 0
    for (let i = 0; i + 4 < data.length; i += 5) {
      line += data[i]
      column = data[i] === 0 ? column + data[i + 1] : data[i + 1]
      const length = data[i + 2]
      const typeIdx = data[i + 3]
      const modifiers = data[i + 4]
      tokens.push({ line, column, length, typeIdx, modifiers })
    }
    return tokens
  }

  /** 将 token 转换为 Monaco decorations */
  function tokensToDecorations(
    tokens: Array<{ line: number; column: number; length: number; typeIdx: number; modifiers: number }>,
    model: monacoNs.editor.ITextModel,
  ): monacoNs.editor.IModelDeltaDecoration[] {
    const decorations: monacoNs.editor.IModelDeltaDecoration[] = []
    for (const tok of tokens) {
      const tokenType = legend[tok.typeIdx] || "variable"
      const cssClass = TOKEN_CLASS_MAP[tokenType] || "semantic-variable"
      // 确保在有效范围内
      const lineCount = model.getLineCount()
      if (tok.line >= lineCount) continue
      const lineLen = model.getLineMaxColumn(tok.line + 1)
      const startCol = Math.min(tok.column + 1, lineLen)
      const endCol = Math.min(tok.column + tok.length + 1, lineLen)
      if (endCol <= startCol) continue

      decorations.push({
        range: (window as any).monaco
          ? new (window as any).monaco.Range(tok.line + 1, startCol, tok.line + 1, endCol)
          : { startLineNumber: tok.line + 1, startColumn: startCol, endLineNumber: tok.line + 1, endColumn: endCol },
        options: {
          inlineClassName: `semantic-token ${cssClass}`,
        },
      })
    }
    return decorations
  }

  /** 应用语义高亮到编辑器 */
  async function applySemanticTokens(): Promise<void> {
    const editor = getEditor()
    const content = getContent()
    const language = getLanguage()
    const filePath = getFilePath()

    if (!editor || !content || !isEnabled.value) return

    const model = editor.getModel()
    if (!model) return

    isPending.value = true
    try {
      const result = await lspApi.getSemanticTokens({
        content,
        language,
        file_path: filePath,
      })

      const tokens = decodeTokens(result.tokens.data)
      tokenCount.value = tokens.length
      const decorations = tokensToDecorations(tokens, model)
      // 清除旧装饰并应用新装饰
      decorationIds = editor.deltaDecorations(decorationIds, decorations)
    } catch (err) {
      // 静默失败 — 语义高亮是增强功能
      console.debug("Semantic tokens fetch failed:", err)
    } finally {
      isPending.value = false
    }
  }

  /** 清除所有语义高亮装饰 */
  function clearSemanticTokens(): void {
    const editor = getEditor()
    if (editor && decorationIds.length) {
      decorationIds = editor.deltaDecorations(decorationIds, [])
      tokenCount.value = 0
    }
  }

  // 在模块初始化时加载 legend
  loadLegend()

  return {
    isEnabled,
    isPending,
    tokenCount,
    applySemanticTokens,
    clearSemanticTokens,
  }
}
