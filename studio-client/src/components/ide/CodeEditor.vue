<script setup lang="ts">
/**
 * CodeBuddy IDE — Code Editor (Monaco Editor Wrapper)
 *
 * 借鉴: Monaco Editor 08-MonacoEditor.md
 *
 * Session 10 新增:
 *   - 全局主题同步 (useThemeStore → Monaco theme)
 *   - 动态编辑器选项更新 (updateEditorOptions)
 *   - 增强编辑器特性 (sticky scroll, bracket colorization, semantic tokens)
 *
 * Session 16 新增:
 *   - FIM 代码补全 (Tabby 风格内联幽灵文本 + 防抖触发 + Tab/Esc 交互)
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

// ── FIM 代码补全 ──
const fim = useFIMCompletion(editorInstance, monacoInstance, {
  filePath: props.activeTab.filePath || "",
  language: props.activeTab.language || "plaintext",
  enabled: true,
  debounceMs: 300,
})
let fimKeydownDisposable: monacoNs.IDisposable | null = null

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
        "editorLineNumber.foreground": "#4B5563",
        "editorLineNumber.activeForeground": "#C0C1FF",
        "editor.selectionBackground": "#C0C1FF30",
        "editor.inactiveSelectionBackground": "#C0C1FF15",
        "editorCursor.foreground": "#C0C1FF",
        "editorIndentGuide.background": "#46455440",
        "editorIndentGuide.activeBackground": "#46455480",
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
      renderLineHighlight: "gutter",
      guides: { indentation: true, bracketPairs: true, bracketPairsHorizontal: true },
      wordWrap: "on",
      folding: true,
      foldingStrategy: "indentation",
      lineNumbers: "on",
      links: true,
      glyphMargin: true,
      // Session 10: enhanced editor features
      bracketPairColorization: { enabled: true },
      stickyScroll: { enabled: true },
      matchBrackets: "always",
      colorDecorators: true,
      parameterHints: { enabled: true },
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
    })
    editorInstance.value = editor
    editor.onDidChangeModelContent(() =>
      emit("update-content", editor.getValue()),
    )
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
  editorInstance.value?.dispose()
  editorInstance.value = null
})
</script>

<template><div ref="containerRef" class="absolute inset-0 w-full h-full" /></template>

<style>
/* 🆕 FIM 幽灵文本样式（借鉴 Tabby inline completion + Cursor ghost text）
 * 必须使用全局选择器，因为 Monaco 内部使用 shadow DOM 渲染 */
.fim-ghost-text {
  color: #6B7280 !important;
  font-style: italic;
  opacity: 0.6;
  pointer-events: none;
}
</style>
