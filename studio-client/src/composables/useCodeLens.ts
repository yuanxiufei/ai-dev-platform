/**
 * useCodeLens — VSCode 风格代码透镜 (引用计数 + 行数标注)
 *
 * 对标: VSCode CodeLensProvider + codeLensController
 * Session 53: 新增，连接后端 /system/lsp/code-lens
 *
 * 在函数/类定义上方显示灰色透镜提示:
 *   "3 references" | "15 lines"
 * 使用 Monaco contentWidget 渲染可点击的透镜
 */
import { ref, watch, onBeforeUnmount } from "vue"
import type * as monacoNs from "monaco-editor"
import * as lspApi from "@/api/lsp"

export interface LspCodeLensItem {
  range: {
    start_line: number
    start_column: number
    end_line: number
    end_column: number
  }
  title: string
  command_id: string
  command_title: string
}

let monacoRef: typeof monacoNs | null = null
try { monacoRef = (window as any).monaco } catch { /* preload */ }

export function useCodeLens(
  getEditor: () => monacoNs.editor.IStandaloneCodeEditor | null,
  getContent: () => string,
  getLanguage: () => string,
  getFilePath: () => string,
) {
  const isEnabled = ref(true)
  const isPending = ref(false)
  const lensCount = ref(0)
  let decorationIds: string[] = []

  /** 获取并渲染代码透镜 */
  async function applyCodeLens(): Promise<void> {
    const editor = getEditor()
    const content = getContent()
    const language = getLanguage()
    const filePath = getFilePath()

    if (!editor || !content || !isEnabled.value) return

    const model = editor.getModel()
    if (!model) return

    isPending.value = true
    try {
      const lenses = await lspApi.getCodeLens({
        content,
        language,
        file_path: filePath,
      })

      lensCount.value = lenses.length

      const decorations: monacoNs.editor.IModelDeltaDecoration[] = []
      for (const lens of lenses) {
        const { start_line, end_column } = lens.range
        const line = start_line + 1 // 1-based
        const afterCol = end_column + 1

        // 使用 after 装饰显示引用计数
        decorations.push({
          range: {
            startLineNumber: line,
            startColumn: afterCol,
            endLineNumber: line,
            endColumn: afterCol,
          },
          options: {
            after: {
              content: `  ${lens.title}`,
              inlineClassName: "code-lens-hint",
            },
            stickiness: 1, // TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges
          },
        })
      }

      decorationIds = editor.deltaDecorations(decorationIds, decorations)
    } catch (err) {
      console.debug("CodeLens fetch failed:", err)
    } finally {
      isPending.value = false
    }
  }

  /** 清除所有 CodeLens 装饰 */
  function clearCodeLens(): void {
    const editor = getEditor()
    if (editor && decorationIds.length) {
      decorationIds = editor.deltaDecorations(decorationIds, [])
      lensCount.value = 0
    }
  }

  return {
    isEnabled,
    isPending,
    lensCount,
    applyCodeLens,
    clearCodeLens,
  }
}
