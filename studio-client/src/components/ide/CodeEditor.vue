<script setup lang="ts">
/**
 * CodeBuddy IDE — Code Editor (Monaco Editor Wrapper)
 *
 * 借鉴: Monaco Editor + VSCode editorPart
 *
 * Session 10: 全局主题同步、动态编辑器选项、增强编辑器特性
 * Session 16: FIM 代码补全 (Tabby 风格)
 * Session 23: Find/Replace Widget + Breadcrumbs + Go To Line + 右键上下文菜单
 */

import type * as monacoNs from "monaco-editor"
import {
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  shallowRef,
  watch,
} from "vue"
import type { EditorTab } from "@/types/ide"
import { useThemeStore } from "@/stores/useThemeStore"
import { useFIMCompletion } from "@/composables/useFIMCompletion"
import { computeLineDiff, diffLinesToDecorations } from "@/composables/useQuickDiff"
import ContextMenu, { type ContextMenuItem } from "./ui/ContextMenu.vue"
import "monaco-editor/dev/vs/editor/editor.main.css"

const props = defineProps<{ activeTab: EditorTab }>()
const emit = defineEmits<{
  (e: "update-content", v: string): void
  (e: "update-cursor", v: any): void
}>()

const containerRef = ref<HTMLElement | null>(null)
const editorInstance = shallowRef<monacoNs.editor.IStandaloneCodeEditor | null>(
  null,
)
let monacoRaw: typeof monacoNs | null = null  // 非响应式快照（兼容原有代码）
const monacoInstance = shallowRef<typeof monacoNs | null>(null)  // 响应式给 composable 用
const themeStore = useThemeStore()

// ── AI 装饰状态 ──
let aiDecorationIds: string[] = []
let aiSuggestionIds: string[] = []

// ── Session 26: QuickDiff 装饰状态（gutter 修改标记） ──
let quickDiffIds: string[] = []
let quickDiffWatcher: ReturnType<typeof setTimeout> | null = null

/** 应用 QuickDiff gutter 装饰（比较原始内容 vs 当前内容） */
function applyQuickDiff(): void {
  const editor = editorInstance.value
  if (!editor || !monacoRaw) return
  const monaco = monacoRaw

  const currentContent = editor.getValue()
  const originalContent = props.activeTab.originalContent
  if (!originalContent || originalContent === currentContent) {
    // 无变更，清除装饰
    if (quickDiffIds.length > 0) {
      editor.deltaDecorations(quickDiffIds, [])
      quickDiffIds = []
    }
    return
  }

  const diffLines = computeLineDiff(originalContent, currentContent)
  if (diffLines.length === 0) {
    if (quickDiffIds.length > 0) {
      editor.deltaDecorations(quickDiffIds, [])
      quickDiffIds = []
    }
    return
  }

  const decoConfigs = diffLinesToDecorations(diffLines)
  const models = decoConfigs.map(d => ({
    range: new monaco.Range(
      d.range.startLineNumber, d.range.startColumn,
      d.range.endLineNumber, d.range.endColumn,
    ),
    options: d.options,
  }))

  quickDiffIds = editor.deltaDecorations(quickDiffIds, models)
}

// ── FIM 代码补全 ──
const fim = useFIMCompletion(editorInstance, monacoInstance, {
  filePath: props.activeTab.filePath || "",
  language: props.activeTab.language || "plaintext",
  enabled: true,
  debounceMs: 300,
})
let fimKeydownDisposable: monacoNs.IDisposable | null = null

// ── VSCode 右键上下文菜单 ──
const contextMenuVisible = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const contextMenuItems = ref<ContextMenuItem[]>([])

/** 构建编辑器右键菜单项（根据当前选区/语言动态生成） */
function buildEditorContextMenu(editor: monacoNs.editor.IStandaloneCodeEditor): ContextMenuItem[] {
  const hasSelection = !editor.getSelection()?.isEmpty()
  return [
    { id: "cut", label: "剪切", shortcut: "Ctrl+X", disabled: !hasSelection, action: () => editor.getAction("editor.action.clipboardCutAction")?.run() },
    { id: "copy", label: "复制", shortcut: "Ctrl+C", disabled: !hasSelection, action: () => editor.getAction("editor.action.clipboardCopyAction")?.run() },
    { id: "paste", label: "粘贴", shortcut: "Ctrl+V", action: () => editor.getAction("editor.action.clipboardPasteAction")?.run() },
    { id: "sep1", label: "", separator: true },
    { id: "find", label: "查找", shortcut: "Ctrl+F", action: () => editor.getAction("actions.find")?.run() },
    { id: "replace", label: "替换", shortcut: "Ctrl+H", action: () => editor.getAction("editor.action.startFindReplaceAction")?.run() },
    { id: "goto-line", label: "转到行...", shortcut: "Ctrl+G", action: () => editor.getAction("editor.action.gotoLine")?.run() },
    { id: "goto-symbol", label: "转到符号...", shortcut: "Ctrl+Shift+O", action: () => editor.getAction("editor.action.gotoSymbol")?.run() },
    { id: "sep2", label: "", separator: true },
    { id: "select-all", label: "全选", shortcut: "Ctrl+A", action: () => editor.getAction("editor.action.selectAll")?.run() },
    { id: "format", label: "格式化文档", shortcut: "Shift+Alt+F", action: () => editor.getAction("editor.action.formatDocument")?.run() },
    { id: "format-sel", label: "格式化选定内容", shortcut: "Ctrl+K Ctrl+F", disabled: !hasSelection, action: () => editor.getAction("editor.action.formatSelection")?.run() },
    { id: "toggle-comment", label: "切换注释", shortcut: "Ctrl+/", action: () => editor.getAction("editor.action.commentLine")?.run() },
    { id: "sep3", label: "", separator: true },
    { id: "go-def", label: "转到定义", shortcut: "F12", action: () => editor.getAction("editor.action.revealDefinition")?.run() },
    { id: "go-refs", label: "查找所有引用", shortcut: "Shift+F12", action: () => {
      // 尝试查找引用并显示在 Peek View 中
      const pos = editor.getPosition()
      if (pos) {
        const word = editor.getModel()?.getWordAtPosition(pos)
        const filePath = props.activeTab.filePath || ""
        if (word && filePath) {
          const items = [{
            file: filePath, label: word.word,
            startLine: pos.lineNumber, startColumn: word.startColumn,
            endLine: pos.lineNumber, endColumn: word.endColumn,
            content: editor.getValue(), language: props.activeTab.language,
          }]
          // 尝试全局 Peek View
          const openPeek = (window as any).__openPeek
          if (typeof openPeek === "function") {
            openPeek(items, 0)
            return
          }
        }
      }
      editor.getAction("editor.action.referenceSearch.trigger")?.run()
    }},
    { id: "peek-def", label: "速览定义", shortcut: "Alt+F12", action: () => {
      // 优先 Monaco 内置 peek，无 language server 时用自定义 PeekView
      editor.getAction("editor.action.peekDefinition")?.run()
      // 延迟检测是否成功弹出
      setTimeout(() => {
        const peekWidget = document.querySelector(".monaco-editor .peekview-widget")
        if (!peekWidget) {
          // 用自定义 PeekView 做回退
          const pos = editor.getPosition()
          if (pos) {
            const word = editor.getModel()?.getWordAtPosition(pos)
            const filePath = props.activeTab.filePath || ""
            if (word && filePath) {
              const openPeek = (window as any).__openPeek
              if (typeof openPeek === "function") {
                openPeek([{
                  file: filePath, label: `${word.word} (定义)`,
                  startLine: editor.getModel()?.findMatches(word.word, false, false, false, null, true)?.[0]
                    ?.range?.startLineNumber ?? pos.lineNumber,
                  content: editor.getValue(), language: props.activeTab.language,
                }], 0)
              }
            }
          }
        }
      }, 200)
    }},
    { id: "rename", label: "重命名符号", shortcut: "F2", action: () => editor.getAction("editor.action.rename")?.run() },
    { id: "sep4", label: "", separator: true },
    { id: "fold-all", label: "折叠所有", shortcut: "Ctrl+K Ctrl+0", action: () => editor.getAction("editor.foldAll")?.run() },
    { id: "unfold-all", label: "展开所有", shortcut: "Ctrl+K Ctrl+J", action: () => editor.getAction("editor.unfoldAll")?.run() },
    { id: "sep5", label: "", separator: true },
    { id: "word-wrap", label: "切换自动换行", shortcut: "Alt+Z", action: () => editor.updateOptions({ wordWrap: editor.getOption(monacoRaw!.editor.EditorOption.wordWrap) === "off" ? "on" : "off" }) },
    { id: "toggle-minimap", label: "切换小地图", action: () => editor.updateOptions({ minimap: { enabled: !editor.getOption(monacoRaw!.editor.EditorOption.minimap).enabled } }) },
    { id: "toggle-whitespace", label: "显示空白字符", shortcut: "Ctrl+R Ctrl+W", action: () => {
      const current = editor.getOption(monacoRaw!.editor.EditorOption.renderWhitespace)
      editor.updateOptions({ renderWhitespace: current === "selection" ? "all" : current === "all" ? "none" : "selection" })
    }},
    { id: "toggle-highlight-line", label: "切换行高亮", action: () => {
      const current = editor.getOption(monacoRaw!.editor.EditorOption.renderLineHighlight)
      editor.updateOptions({ renderLineHighlight: current === "all" ? "none" : current === "none" ? "line" : "all" })
    }},
  ]
}

/** AI 装饰选项 */
export interface AIDecoration {
  /** 起始行（1-based） */
  startLine: number
  /** 结束行（1-based） */
  endLine: number
  /** 起始列（1-based, 默认 1） */
  startColumn?: number
  /** 结束列（1-based, 默认 1） */
  endColumn?: number
  /** 装饰类型 */
  type: "insert" | "modify" | "delete" | "info"
  /** 悬浮提示文字 */
  hoverMessage?: string
  /** 是否整行装饰 */
  isWholeLine?: boolean
}

async function initMonaco(): Promise<void> {
  if (!containerRef.value) return
  try {
    const monaco = (await import("monaco-editor")).default
    monacoRaw = monaco
    monacoInstance.value = monaco
    monaco.editor.defineTheme("codebuddy-dark", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "comment", foreground: "5C6370", fontStyle: "italic" },
        { token: "keyword", foreground: "C678DD" },
        { token: "string", foreground: "98C379" },
        { token: "number", foreground: "D19A66" },
        { token: "type", foreground: "61AFEF" },
        { token: "function", foreground: "61AFEF" },
        { token: "variable", foreground: "DFE2F1" },
        { token: "operator", foreground: "DFE2F1" },
        { token: "tag", foreground: "E06C75" },
        { token: "attribute.name", foreground: "E06C75" },
        { token: "attribute.value", foreground: "98C379" },
        { token: "delimiter.html", foreground: "908FA0" },
        // AI 标注 token 色（借鉴 Monaco "my-ai-theme"）
        { token: "ai-inserted", background: "2ea04333", foreground: "3fb950" },
        { token: "ai-deleted", background: "f8514933", foreground: "f85149" },
        { token: "ai-modified", background: "d2992233", foreground: "e3b341" },
      ],
      colors: {
        "editor.background": "#0F131D",
        "editor.foreground": "#DFE2F1",
        "editor.lineHighlightBackground": "#1C1F2A20",
        "editor.lineHighlightBorder": "#2A2D3A10",
        "editorLineNumber.foreground": "#4B5563",
        "editorLineNumber.activeForeground": "#C0C1FF",
        "editor.selectionBackground": "#C0C1FF30",
        "editor.inactiveSelectionBackground": "#C0C1FF15",
        "editorCursor.foreground": "#C0C1FF",
        "editorIndentGuide.background": "#46455440",
        "editorIndentGuide.activeBackground": "#46455480",
        "editorRuler.foreground": "#2A2D3A80",
        "scrollbarSlider.background": "#46455450",
        "scrollbarSlider.hoverBackground": "#5a596b60",
        "scrollbarSlider.activeBackground": "#70708870",
        // Diff overview ruler 颜色
        "editorOverviewRuler.addedForeground": "#2ea04380",
        "editorOverviewRuler.modifiedForeground": "#d2992280",
        "editorOverviewRuler.deletedForeground": "#f8514980",
        "editorOverviewRuler.infoForeground": "#61AFEF80",
      },
    })
    const editor = monaco.editor.create(containerRef.value, {
      value: props.activeTab.content,
      language: props.activeTab.language ?? "plaintext",
      // Session 10: sync with global theme
      theme: themeStore.definition.monacoTheme,
      automaticLayout: true,
      fontSize: 13,
      fontFamily:
        "'JetBrains Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace",
      fontLigatures: true,
      lineHeight: 21,
      padding: { top: 8, bottom: 8 },
      minimap: { enabled: true, maxColumn: 120, scale: 1 },
      scrollBeyondLastLine: false,
      smoothScrolling: true,
      cursorBlinking: "smooth",
      cursorSmoothCaretAnimation: "on",
      /** Session 25: VSCode 整行高亮 + 缩进参考线增强 */
      renderLineHighlight: "all",
      guides: { indentation: true, bracketPairs: true, bracketPairsHorizontal: true, highlightActiveIndentation: true },
      /** Session 25: 垂直标尺线 (80 char 灰线, 120 char 红线) */
      rulers: [80, 120],
      /** Session 25: 选择时显示空白字符 */
      renderWhitespace: "selection",
      /** Session 25: 3 条 overview ruler */
      overviewRulerLanes: 3,
      /** Session 25: 鼠标悬停时显示折叠控件 */
      showFoldingControls: "mouseover",
      wordWrap: "on",
      folding: true,
      foldingStrategy: "indentation",
      lineNumbers: "on",
      lineNumbersMinChars: 4,
      links: true,
      glyphMargin: true,
      // Session 10: enhanced editor features
      bracketPairColorization: { enabled: true },
      stickyScroll: { enabled: true },
      matchBrackets: "always",
      colorDecorators: true,
      parameterHints: { enabled: true },
      /** Session 23: VSCode 编辑器内查找/替换 */
      find: {
        addExtraSpaceOnTop: false,
        autoFindInSelection: "never",
        seedSearchStringFromSelection: "always",
      },
      /** Session 23: VSCode 风格面包屑导航 */
      breadcrumbs: { enabled: true },
      suggest: {
        showWords: true,
        showSnippets: true,
        showClasses: true,
        showFunctions: true,
        showModules: true,
        showProperties: true,
      },
      tabCompletion: "on",
      autoClosingBrackets: "always",
      autoClosingQuotes: "always",
      /** Session 23: 禁用 Monaco 内置右键菜单，使用自定义 VSCode 风格菜单 */
      contextmenu: false,
    })
    editorInstance.value = editor

    /** Session 23: 自定义右键上下文菜单（VSCode 风格） */
    editor.onContextMenu((e) => {
      e.event.preventDefault()
      contextMenuItems.value = buildEditorContextMenu(editor)
      contextMenuX.value = e.event.posx
      contextMenuY.value = e.event.posy
      contextMenuVisible.value = true
    })
    editor.onDidChangeModelContent(() => {
      emit("update-content", editor.getValue())
      /** Session 26: 延迟应用 QuickDiff (防抖 300ms) */
      if (quickDiffWatcher) clearTimeout(quickDiffWatcher)
      quickDiffWatcher = setTimeout(() => applyQuickDiff(), 300)
    })
    editor.onCursorPositionChanged(() => {
      const pos = editor.getPosition(),
        model = editor.getModel()
      emit("update-cursor", {
        line: pos?.lineNumber ?? 1,
        column: pos?.column ?? 1,
        totalLines: model?.getLineCount() ?? 1,
        selectedChars: editor.getSelection()?.toString().length ?? 0,
        languageId: model?.getLanguageId() ?? "plaintext",
      })
    })

    // 🆕 FIM 补全: 按键触发 + Tab/Esc 拦截
    editor.onKeyDown((e) => {
      // 先让 FIM 处理（Tab/Esc 接受/驳回幽灵文本）
      if (fim.handleKeydown(e as unknown as KeyboardEvent)) return

      // 按键触发补全
      const key = e as unknown as KeyboardEvent
      if (key.key && key.key.length === 1) {
        fim.handleKeystroke(key.key)
      }
    })

    editor.focus()

    /** Session 26: 初始 QuickDiff */
    setTimeout(() => applyQuickDiff(), 500)
  } catch (err) {
    console.warn("[CodeBuddy] Monaco init error:", err)
  }
}

// ── AI 装饰 API ──

/** 颜色映射 */
const AI_DECO_CLASS: Record<string, string> = {
  insert: "ai-inserted-line",
  modify: "ai-modified-line",
  delete: "ai-deleted-line",
  info: "ai-info-line",
}
const AI_OVERVIEW_COLOR: Record<string, string> = {
  insert: "#2ea043", modify: "#d29922", delete: "#f85149", info: "#61AFEF",
}

/**
 * 应用 AI 建议的内联装饰（借鉴 Monaco deltaDecorations API）
 * 在编辑器行上显示颜色标记 + 悬浮信息 + overview ruler 标记
 */
function applyAIDecorations(decorations: AIDecoration[]) {
  const editor = editorInstance.value
  if (!editor || !monacoRaw) return
  const monaco = monacoRaw

  clearAIDecorations()

  const models = decorations.map((d) => ({
    range: new monaco.Range(
      d.startLine,
      d.startColumn ?? 1,
      d.endLine,
      d.endColumn ?? 1,
    ),
    options: {
      isWholeLine: d.isWholeLine ?? true,
      className: AI_DECO_CLASS[d.type] || "",
      hoverMessage: d.hoverMessage
        ? { value: `🤖 AI: ${d.hoverMessage}` }
        : undefined,
      glyphMarginClassName: `ai-glyph-${d.type}`,
      overviewRuler: {
        color: AI_OVERVIEW_COLOR[d.type],
        position: monaco.editor.OverviewRulerLane.Right,
      },
    },
  }))

  aiDecorationIds = editor.deltaDecorations([], models)
}

/** 清除所有 AI 装饰 */
function clearAIDecorations() {
  const editor = editorInstance.value
  if (!editor) return
  if (aiDecorationIds.length > 0) {
    editor.deltaDecorations(aiDecorationIds, [])
    aiDecorationIds = []
  }
  if (aiSuggestionIds.length > 0) {
    editor.deltaDecorations(aiSuggestionIds, [])
    aiSuggestionIds = []
  }
}

/**
 * 显示行内 AI 建议代码（临时 ghost text 风格，借鉴 inline edit）
 */
function showAISuggestion(line: number, suggestedCode: string, description?: string) {
  const editor = editorInstance.value
  if (!editor || !monacoRaw) return
  const monaco = monacoRaw

  clearAIDecorations()
  const contentAtLine = editor.getModel()?.getLineContent(line) || ""
  
  aiSuggestionIds = editor.deltaDecorations([], [{
    range: new monaco.Range(line, 1, line, 1),
    options: {
      isWholeLine: true,
      className: "ai-suggestion-ghost",
      after: {
        content: `  // 🤖 [AI建议] ${suggestedCode}${description ? ` (${description})` : ""}`,
      },
      hoverMessage: { value: `**AI 建议修改**\n\n\`\`\`\n${suggestedCode}\n\`\`\`\n\n${description || ""}\n\n按 Alt+A 接受, Alt+R 拒绝` },
      overviewRuler: {
        color: "#3fb950",
        position: monaco.editor.OverviewRulerLane.Right,
      },
    },
  }])
}

/** 接受 AI 内联建议（将建议代码替换到编辑器） */
function acceptAISuggestion(line: number, suggestedCode: string) {
  clearAIDecorations()
  const editor = editorInstance.value
  if (!editor || !monacoRaw) return
  editor.executeEdits("ai-accept", [{
    range: new monacoRaw.Range(line, 1, line, Number.MAX_SAFE_INTEGER),
    text: suggestedCode,
  }])
}

function rejectAISuggestion() {
  clearAIDecorations()
}

/** 获取 Monaco 实例（供父组件使用） */
function getMonaco() {
  return monacoRaw
}

/** 获取编辑器实例 */
function getEditor() {
  return editorInstance.value
}

// ── 暴露给父组件 ──
defineExpose({
  applyAIDecorations,
  clearAIDecorations,
  showAISuggestion,
  acceptAISuggestion,
  rejectAISuggestion,
  getMonaco,
  getEditor,
})

// ── 原有 Watcher ──
watch(
  () => [props.activeTab.id, props.activeTab.language],
  async ([newId], [oldId]) => {
    if (!monacoRaw) return
    if (newId !== oldId) {
      clearAIDecorations()
      editorInstance.value?.dispose()
      editorInstance.value = null
      await nextTick()
      await initMonaco()
    } else if (editorInstance.value) {
      monacoRaw.editor.setModelLanguage(
        editorInstance.value.getModel()!,
        props.activeTab.language ?? "plaintext",
      )
    }
  },
)
watch(
  () => props.activeTab.content,
  (nc) => {
    if (editorInstance.value && editorInstance.value.getValue() !== nc) {
      const s = editorInstance.value.getSelection()
      editorInstance.value.setValue(nc)
      if (s) editorInstance.value.setSelection(s)
    }
  },
)

onMounted(async () => {
  await initMonaco()
})

// Session 10: watch theme changes → update Monaco theme
watch(
  () => themeStore.definition.monacoTheme,
  (newTheme) => {
    if (monacoRaw && editorInstance.value) {
      monacoRaw.editor.setTheme(newTheme)
    }
  },
)

// Session 10: update editor options dynamically
watch(
  () => [
    themeStore.active,
  ],
  () => {
    // Theme already handled above; placeholder for future dynamic settings
    // e.g. fontSize, minimap toggle from useEditorStore
  },
)

onBeforeUnmount(() => {
  clearAIDecorations()
  if (quickDiffWatcher) clearTimeout(quickDiffWatcher)
  if (quickDiffIds.length > 0 && editorInstance.value) {
    editorInstance.value.deltaDecorations(quickDiffIds, [])
    quickDiffIds = []
  }
  editorInstance.value?.dispose()
  editorInstance.value = null
})
</script>

<template>
  <div ref="containerRef" class="absolute inset-0 w-full h-full" />
  <!-- Session 23: VSCode 风格编辑器右键上下文菜单 -->
  <ContextMenu
    :items="contextMenuItems"
    :x="contextMenuX"
    :y="contextMenuY"
    :visible="contextMenuVisible"
    @close="contextMenuVisible = false"
  />
</template>

<style>
/* 🆕 FIM 幽灵文本样式（借鉴 Tabby inline completion + Cursor ghost text）
 * 必须使用全局选择器，因为 Monaco 内部使用 shadow DOM 渲染 */
.fim-ghost-text {
  color: #6B7280 !important;
  font-style: italic;
  opacity: 0.6;
  pointer-events: none;
}

/* Session 26: QuickDiff gutter / line 样式 */
/* Gutter 标记: 修改(黄色条) */
.qd-glyph-modified {
  background: #d29922 !important;
  width: 3px !important;
  margin-left: 3px;
  border-radius: 1px;
}
/* Gutter 标记: 新增(绿色条) */
.qd-glyph-added {
  background: #2ea043 !important;
  width: 3px !important;
  margin-left: 3px;
  border-radius: 1px;
}
/* Gutter 标记: 删除(红色三角) — 简化版显示为色条 */
.qd-glyph-deleted {
  background: #f85149 !important;
  width: 3px !important;
  margin-left: 3px;
  border-radius: 1px;
}
/* 行背景标记 */
.qd-modified-line { background: rgba(210, 153, 34, 0.08) !important; border-left: 2px solid rgba(210, 153, 34, 0.4) !important; }
.qd-added-line { background: rgba(46, 160, 67, 0.08) !important; border-left: 2px solid rgba(46, 160, 67, 0.4) !important; }
.qd-deleted-line { background: rgba(248, 81, 73, 0.08) !important; border-left: 2px solid rgba(248, 81, 73, 0.4) !important; text-decoration: line-through; opacity: 0.5; }
</style>
