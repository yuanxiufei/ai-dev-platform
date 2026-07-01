/**
 * FIM 代码补全 Composable — 智能触发 + 内联幽灵文本
 *
 * 借鉴 Tabby autocomplete + Continue ghost text 设计：
 * - 按键后防抖 300ms 自动触发
 * - "." / "import" 等特殊字符即时触发
 * - 内联幽灵文本展示（灰色 italic，可 Tab 接受）
 * - 接受/驳回反馈上报
 *
 * 使用方式:
 *   const fim = useFIMCompletion(editorInstance, monacoInstance, {
 *     filePath: "app.py",
 *     language: "python",
 *     enabled: true,
 *   })
 *   // 组件挂载时自动绑定按键监听，卸载时自动解绑
 */

import { ref, onBeforeUnmount, watch, type Ref } from "vue"
import {
  requestCompletion,
  sendFeedback,
  type CompletionItem,
  type CompletionTrigger,
} from "@/api/fim"

export interface FIMOptions {
  /** 文件路径（用于语言推断和缓存键） */
  filePath?: string
  /** 编程语言 */
  language?: string
  /** 是否启用自动补全 */
  enabled?: boolean
  /** 防抖延迟 (ms)，默认 300 */
  debounceMs?: number
  /** 最大返回条数，默认 5 */
  topK?: number
  /** 是否启用特殊字符即时触发 */
  instantTriggers?: boolean
}

export interface FIMState {
  /** 当前显示的补全文本 */
  suggestion: string | null
  /** 当前补全所在行号 */
  suggestionLine: number
  /** 当前补全评分 */
  suggestionScore: number
  /** 是否正在请求中 */
  loading: boolean
  /** 补全引擎是否已启用 */
  enabled: boolean
}

export function useFIMCompletion(
  editorRef: Ref<any>,        // IStandaloneCodeEditor | null
  monacoRef: Ref<any>,        // Monaco namespace | null
  options: FIMOptions = {},
) {
  // ── 状态 ──
  const state = ref<FIMState>({
    suggestion: null,
    suggestionLine: 0,
    suggestionScore: 0,
    loading: false,
    enabled: options.enabled ?? true,
  })

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let lastCompletionTime = 0
  const MIN_COMPLETION_INTERVAL = 500  // 两次补全最小间隔 ms
  let currentCompletionItem: CompletionItem | null = null

  // 幽灵文本装饰 ID
  let ghostDecorationIds: string[] = []

  // ── 触发判断 ──

  /** 判断按键是否应触发补全 */
  function shouldTrigger(char: string): boolean {
    if (!state.value.enabled) return false

    // 即时触发字符（借鉴 Tabby 即时触发设计）
    const instantChars = [".", "(", "[", "{", '"', "'", "`"]
    if (options.instantTriggers !== false && instantChars.includes(char)) {
      return true
    }

    // 字母/数字输入时也触发（防抖）
    if (/^[a-zA-Z0-9_]$/.test(char)) return true

    return false
  }

  /** 推断触发类型 */
  function inferTrigger(char: string): CompletionTrigger {
    if (char === ".") return "dot"
    if (char === "(") return "function_call"
    if (/^(import|from|require)$/i.test(char)) return "import"
    return "keystroke"
  }

  // ── 核心：发送补全请求 ──

  async function fetchCompletion(): Promise<void> {
    const editor = editorRef.value
    const monaco = monacoRef.value
    if (!editor || !monaco || !state.value.enabled) return

    // 频率限制
    const now = Date.now()
    if (now - lastCompletionTime < MIN_COMPLETION_INTERVAL) return
    lastCompletionTime = now

    const model = editor.getModel()
    const position = editor.getPosition()
    if (!model || !position) return

    const fileContent = model.getValue()
    const cursorLine = position.lineNumber - 1  // 0-based
    const cursorColumn = position.column - 1    // 0-based

    // 如果光标在空行或文件太短，跳过
    if (fileContent.length < 3) return

    state.value.loading = true

    try {
      const resp = await requestCompletion({
        file_content: fileContent,
        cursor_line: cursorLine,
        cursor_column: cursorColumn,
        file_path: options.filePath || "",
        language: options.language || model.getLanguageId(),
        trigger: "keystroke",
        top_k: options.topK ?? 5,
      })

      const items = resp.data.items || []
      if (items.length === 0) {
        clearGhostText()
        return
      }

      // 取最高分补全
      const best = items[0]
      currentCompletionItem = best

      // 显示幽灵文本
      showGhostText(position.lineNumber, best.text, best.score ?? 0)
    } catch {
      // 静默失败 — 补全不应该打断用户
      clearGhostText()
    } finally {
      state.value.loading = false
    }
  }

  // ── 幽灵文本渲染 ──

  /** 使用 Monaco after-content decoration 展示内联幽灵文本 */
  function showGhostText(line: number, suggestion: string, score: number): void {
    const editor = editorRef.value
    const monaco = monacoRef.value
    if (!editor || !monaco) return

    clearGhostText()

    const lineMaxColumn = editor.getModel()?.getLineMaxColumn(line) || 1
    const range = new monaco.Range(line, lineMaxColumn, line, lineMaxColumn)

    ghostDecorationIds = editor.deltaDecorations([], [
      {
        range,
        options: {
          after: {
            content: suggestion,
            inlineClassName: "fim-ghost-text",
          },
        },
      },
    ])

    state.value.suggestion = suggestion
    state.value.suggestionLine = line
    state.value.suggestionScore = score
  }

  function clearGhostText(): void {
    const editor = editorRef.value
    if (!editor || ghostDecorationIds.length === 0) return

    editor.deltaDecorations(ghostDecorationIds, [])
    ghostDecorationIds = []

    state.value.suggestion = null
    currentCompletionItem = null
  }

  // ── 接受/驳回 ──

  /** 接受当前补全建议 */
  function accept(): void {
    const editor = editorRef.value
    const monaco = monacoRef.value
    const suggestion = state.value.suggestion

    if (!editor || !monaco || !suggestion) return

    // 在光标处插入建议文本
    editor.executeEdits("fim-accept", [
      {
        range: new monaco.Range(
          state.value.suggestionLine,
          editor.getModel()?.getLineMaxColumn(state.value.suggestionLine) || 1,
          state.value.suggestionLine,
          editor.getModel()?.getLineMaxColumn(state.value.suggestionLine) || 1,
        ),
        text: suggestion,
      },
    ])

    // 上报反馈
    const item = currentCompletionItem
    if (item) {
      sendFeedback({
        accepted: true,
        completion_text: item.text,
        file_path: options.filePath,
        cursor_line: state.value.suggestionLine - 1,
        source: item.source,
      }).catch(() => {})
    }

    clearGhostText()
  }

  /** 驳回当前补全建议 */
  function dismiss(): void {
    const item = currentCompletionItem
    if (item) {
      sendFeedback({
        accepted: false,
        completion_text: item.text,
        file_path: options.filePath,
        source: item.source,
      }).catch(() => {})
    }
    clearGhostText()
  }

  // ── 防抖触发 ──

  /** 处理按键，决定是否触发补全 */
  function handleKeystroke(char: string): void {
    if (!shouldTrigger(char)) return

    // 清除旧定时器
    if (debounceTimer) {
      clearTimeout(debounceTimer)
    }

    // 即时触发字符 — 直接请求
    const instantChars = [".", "(", "[", "{", '"', "'", "`"]
    if (options.instantTriggers !== false && instantChars.includes(char)) {
      debounceTimer = setTimeout(fetchCompletion, 100)  // 微延迟防抖
      return
    }

    // 普通字符 — 标准防抖
    const delay = options.debounceMs ?? 300
    debounceTimer = setTimeout(fetchCompletion, delay)
  }

  /** 手动触发补全（Ctrl+Space） */
  function triggerManual(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
    }
    fetchCompletion()
  }

  /** 启用/禁用补全 */
  function setEnabled(enabled: boolean): void {
    state.value.enabled = enabled
    if (!enabled) clearGhostText()
  }

  // ── 键盘事件处理（Tab/Escape） ──

  /** 处理键盘事件，拦截 Tab 和 Escape */
  function handleKeydown(e: KeyboardEvent): boolean {
    if (!state.value.suggestion) return false

    if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault()
      e.stopPropagation()
      accept()
      return true
    }

    if (e.key === "Escape") {
      e.preventDefault()
      e.stopPropagation()
      dismiss()
      return true
    }

    return false
  }

  // ── 清理 ──

  function cleanup(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    clearGhostText()
  }

  onBeforeUnmount(cleanup)

  // ── 响应 enabled 变化 ──
  watch(
    () => options.enabled,
    (val) => {
      if (val !== undefined) setEnabled(val)
    },
  )

  return {
    state,
    handleKeystroke,
    handleKeydown,
    triggerManual,
    accept,
    dismiss,
    clearGhostText,
    setEnabled,
    cleanup,
  }
}
