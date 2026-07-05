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
import { useInlineDebugValues } from "@/composables/useInlineDebug"
import { useEditorIntelligence } from "@/composables/useEditorIntelligence"
import { useGitBlame, type BlameLine } from "@/composables/useGitBlame"
import { useInlayHints } from "@/composables/useInlayHints"
import { useEmmet } from "@/composables/useEmmet"
import { useErrorLens } from "@/composables/useErrorLens"
import { useSmartSelect } from "@/composables/useSmartSelect"
import { useLinkedEditing } from "@/composables/useLinkedEditing"
import { useWordHighlighter } from "@/composables/useWordHighlighter"
import { registerSyncScrollEditor, unregisterSyncScrollEditor } from "@/composables/useSyncScroll"
import ContextMenu, { type ContextMenuItem } from "./ui/ContextMenu.vue"
import GoToSymbol from "./GoToSymbol.vue"
import CodeActionsMenu, { type CodeAction } from "./CodeActionsMenu.vue"
import RenameInput from "./RenameInput.vue"
import FindWidget from "./FindWidget.vue"
import InlineChatWidget from "./InlineChatWidget.vue"
import "monaco-editor/dev/vs/editor/editor.main.css"
import { useSemanticTokens } from "@/composables/useSemanticTokens"
import { useCodeLens } from "@/composables/useCodeLens"
import { useFolding } from "@/composables/useFolding"
import * as lspApi from "@/api/lsp"

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

// ── Session 40: Git Blame 装饰状态（gutter 行归因标记） ──
const gitBlame = useGitBlame()
const showBlame = ref(false)
let blameDecorationIds: string[] = []
let blameContentWidgets: { id: string; dispose: () => void }[] = []

// ── Session 43: InlayHints 内嵌类型标注 ──
const inlayHints = useInlayHints()
let inlayHintsTimer: ReturnType<typeof setTimeout> | null = null
const showInlayHints = ref(true) // 可通过 settings 切换

// ── Session 45: Emmet 引擎 ──
const emmet = useEmmet()
let emmetDisposables: monacoNs.IDisposable[] = []

// ── Session 45: Error Lens 行内诊断 ──
const errorLens = useErrorLens(editorInstance, monacoInstance)
let errorLensTimer: ReturnType<typeof setTimeout> | null = null
const showErrorLens = ref(true) // 可通过 settings 切换

// ── Session 46: Smart Select 语义选区 ──
const smartSelect = useSmartSelect()

// ── Session 46: Linked Editing 链接编辑（HTML/XML 标签对）──
const linkedEditing = useLinkedEditing(editorInstance, monacoInstance)
let linkedEditingEnabled = ref(true)

// ── Session 46: Word Highlighter 单词出现位置高亮 ──
const wordHighlighter = useWordHighlighter(editorInstance)
let wordHighlightEnabled = ref(true)

// ── Session 53: Semantic Tokens 语义高亮 ──
const semanticTokens = useSemanticTokens(
  () => editorInstance.value,
  () => editorInstance.value?.getValue() || "",
  () => props.activeTab.language || "plaintext",
  () => props.activeTab.filePath || props.activeTab.label || "",
)

// ── Session 53: Code Lens 代码透镜 ──
const codeLens = useCodeLens(
  () => editorInstance.value,
  () => editorInstance.value?.getValue() || "",
  () => props.activeTab.language || "plaintext",
  () => props.activeTab.filePath || props.activeTab.label || "",
)

// ── Session 53: Folding 代码折叠 ──
const folding = useFolding(
  () => editorInstance.value?.getValue() || "",
  () => props.activeTab.language || "plaintext",
  () => props.activeTab.filePath || props.activeTab.label || "",
)

// ── Session 46: 光标撤销栈 (CursorUndo) ──
let cursorUndoStack: monacoNs.IPosition[] = []
let cursorUndoIndex = -1

// ── Session 46: Font Zoom 级别 ──
let fontSizeLevel = 14 // 初始字号
const MIN_FONT_SIZE = 8
const MAX_FONT_SIZE = 36

// ── Session 47: 异常行终止符检测 ──
/** 检测文本中的异常行终止符 (LS/PS 字符) */
function detectUnusualLineTerminators(content: string): { hasUnusual: boolean; details: string } {
  const lsCount = (content.match(/\u2028/g) || []).length // Line Separator
  const psCount = (content.match(/\u2029/g) || []).length // Paragraph Separator
  const hasUnusual = lsCount > 0 || psCount > 0
  const parts: string[] = []
  if (lsCount > 0) parts.push(`${lsCount} 个行分隔符(LS)`)
  if (psCount > 0) parts.push(`${psCount} 个段落分隔符(PS)`)
  return { hasUnusual, details: parts.join("、") }
}
/** 自动移除异常行终止符 */
function autoRemoveUnusualTerminators(content: string): string {
  return content.replace(/\u2028/g, "\n").replace(/\u2029/g, "\n\n")
}

// ── Session 46: Unicode Highlighter ──
let unicodeHighlightEnabled = ref(true)
let unicodeHighlightIds: string[] = []

// ── Session 46: 功能开关 ──
let longLinesEnabled = ref(true)
let tabFocusMode = ref(false) // false = 正常Tab行为（缩进）

// ── Session 47: 格式化开关 + API 格式化 ──
let formatOnSaveEnabled = ref(true)
let formatOnPasteEnabled = ref(false)
const formatApiBase = import.meta.env.VITE_API_BASE || "/api/v1"

/** Session 53: 通过 LSP 后端 API 格式化代码（多语言，多Provider） */
async function formatWithAPI(content: string, language: string): Promise<string | null> {
  try {
    const result = await lspApi.formatDocument({
      content,
      language,
      file_path: props.activeTab.filePath || "",
      tab_size: 4,
      insert_spaces: true,
    })
    return result.formatted_content || null
  } catch { /* API 不可用时静默回退到 Monaco */ }
  return null
}

/** Session 47: 格式化当前编辑器内容 */
async function formatDocument(formatter?: string): Promise<void> {
  const editor = editorInstance.value
  if (!editor) return
  const content = editor.getValue()
  const lang = props.activeTab.language || "plaintext"
  // 优先用后端 API 格式化
  const formatted = await formatWithAPI(content, lang)
  if (formatted && formatted !== content) {
    const pos = editor.getPosition()
    editor.setValue(formatted)
    if (pos) editor.setPosition(pos)
  } else {
    // 回退到 Monaco 内置
    editor.getAction("editor.action.formatDocument")?.run()
  }
}

/** Session 47: 格式化选区 */
async function formatSelection(): Promise<void> {
  const editor = editorInstance.value
  if (!editor) return
  const sel = editor.getSelection()
  if (!sel || sel.isEmpty()) return
  const model = editor.getModel()
  if (!model) return
  const content = model.getValueInRange(sel)
  const lang = props.activeTab.language || "plaintext"
  const formatted = await formatWithAPI(content, lang)
  if (formatted && formatted !== content) {
    editor.executeEdits("format-selection", [{ range: sel, text: formatted }])
  } else {
    editor.getAction("editor.action.formatSelection")?.run()
  }
}

/** Session 48: 自动检测未知文件的语言 */
const detectLangTimer = ref<ReturnType<typeof setTimeout> | null>(null)
async function autoDetectLanguage(): Promise<void> {
  const editor = editorInstance.value
  if (!editor) return
  const content = editor.getValue()
  if (!content || content.trim().length < 5) return
  const fileName = props.activeTab.filePath || props.activeTab.label

  if (detectLangTimer.value) clearTimeout(detectLangTimer.value)
  detectLangTimer.value = setTimeout(async () => {
    try {
      const baseUrl = formatApiBase
      const res = await fetch(`${baseUrl}/system/language/detect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: content.slice(0, 10000), file_name: fileName }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.primary && data.primary.confidence > 0.5 && data.primary.language_id !== "plaintext") {
          const langId = data.primary.language_id
          // 更新 Monaco 模型语言
          if (monacoRaw && editor.getModel()) {
            monacoRaw.editor.setModelLanguage(editor.getModel()!, langId)
          }
        }
      }
    } catch { /* 静默处理 */ }
  }, 1000)
}

/** Session 48: 获取代码操作建议 (灯泡菜单) */
const codeActionsCache = ref<any[]>([])
const codeActionsPosition = ref<{ line: number; column: number } | null>(null)
let codeActionsTimer: ReturnType<typeof setTimeout> | null = null

async function fetchCodeActions(): Promise<void> {
  const editor = editorInstance.value
  if (!editor) return
  const content = editor.getValue()
  const lang = props.activeTab.language || "plaintext"
  const pos = editor.getPosition()
  if (!pos) return

  try {
    const actions = await lspApi.getCodeActions({
      content,
      language: lang,
      file_path: props.activeTab.filePath || "",
      diagnostics: [],
      range: {
        start_line: pos.lineNumber - 1,
        start_column: pos.column - 1,
        end_line: pos.lineNumber - 1,
        end_column: pos.column,
      },
    })
    if (actions && actions.length > 0) {
      codeActionsCache.value = actions.map(a => ({
        id: a.kind + a.title,
        title: a.title,
        kind: (a.kind === "quickfix" ? "quickfix" : a.kind === "source.fixAll" ? "source" : "other") as any,
        isPreferred: a.is_preferred,
      }))
      codeActionsPosition.value = { line: pos.lineNumber, column: pos.column }
      showLightbulb(pos.lineNumber)
    }
  } catch { /* 静默 */ }
}

function applyCodeAction(action: any): void {
  const editor = editorInstance.value
  if (!editor) return
  hideLightbulb()

  if (action.command?.startsWith("fix:")) {
    const content = editor.getValue()
    const strategy = action.command.slice(4)
    if (strategy === "trim_trailing") {
      const lines = content.split("\n")
      editor.setValue(lines.map(l => l.replace(/\s+$/, "")).join("\n"))
    } else if (strategy === "append_newline") {
      if (!content.endsWith("\n")) editor.setValue(content + "\n")
    } else if (strategy === "collapse_empty_lines") {
      editor.setValue(content.replace(/\n{3,}/g, "\n\n"))
    } else {
      fetch(`${formatApiBase}/system/code-actions/apply?content=${encodeURIComponent(content)}&diagnostic_message=${encodeURIComponent(action.diagnostics?.[0] || "")}&diagnostic_line=${codeActionsPosition.value?.line || 1}`)
        .then(r => r.json()).then(d => { if (d.changed) editor.setValue(d.content) }).catch(() => {})
    }
    return
  }
  if (action.kind === "source.organizeImports") {
    formatDocument()
  } else if (action.kind === "source.fixAll") {
    formatDocument()
  }
}

function hideCodeActions(): void {
  codeActionsCache.value = []
}

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

/** Session 40: 应用 Git Blame 装饰（GitLens 风格行归因） */
function applyBlameDecorations(): void {
  const editor = editorInstance.value
  if (!editor || !monacoRaw) return
  const monaco = monacoRaw

  // 清除旧装饰
  if (blameDecorationIds.length > 0) {
    editor.deltaDecorations(blameDecorationIds, [])
    blameDecorationIds = []
  }
  // 清除 content widgets
  for (const w of blameContentWidgets) {
    w.dispose()
  }
  blameContentWidgets = []

  if (!showBlame.value || gitBlame.lines.value.length === 0) return

  const blameLines = gitBlame.lines.value
  const lineCount = editor.getModel()?.getLineCount() ?? 0

  // 为每一行创建 blame 装订线显示
  const decorations = blameLines.map((bl: BlameLine) => {
    // 用 hash 生成颜色 (确定性，同 author 同色)
    const hue = (bl.author.split("").reduce((a, c) => a + c.charCodeAt(0), 0) * 7) % 360
    const color = `hsl(${hue}, 55%, 68%)`

    return {
      range: new monaco.Range(bl.lineNumber, 1, bl.lineNumber, 1),
      options: {
        isWholeLine: true,
        glyphMarginClassName: `blame-glyph-${bl.lineNumber}`,
        glyphMarginHoverMessage: {
          value: `**${bl.commitHash}** — ${bl.author}, ${bl.timeAgo}\n\n${bl.summary || "(无提交说明)"}`,
          isTrusted: true,
        },
        // 在行前显示作者名缩写
        before: {
          content: `${bl.author.replace(/\s.*/, "").substring(0, 7)}`,
          inlineClassName: "blame-author-label",
        },
        overviewRuler: {
          color: color,
          position: monaco.editor.OverviewRulerLane.Center,
        },
      },
    }
  })

  blameDecorationIds = editor.deltaDecorations(blameDecorationIds, decorations)

  // 为未覆盖的行添加空占位，保持对齐（Monaco 不支持 per-line 前内容）
  // 解决方案：给所有没有 blame 的行也加空字符占位
  const coveredLines = new Set(blameLines.map(l => l.lineNumber))
  const placeholderDecorations: Array<{
    range: monacoNs.Range
    options: monacoNs.editor.IModelDeltaDecoration
  }> = []

  for (let line = 1; line <= lineCount; line++) {
    if (!coveredLines.has(line)) {
      placeholderDecorations.push({
        range: new monaco.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          before: {
            content: "        ",
            inlineClassName: "blame-placeholder",
          },
        },
      })
    }
  }

  if (placeholderDecorations.length > 0) {
    blameDecorationIds = [
      ...blameDecorationIds,
      ...editor.deltaDecorations([], placeholderDecorations),
    ]
  }
}

/** Session 40: 切换 Blame 标注 */
async function toggleBlame(): Promise<void> {
  showBlame.value = !showBlame.value
  if (showBlame.value) {
    // 加载 blame 数据
    if (props.activeTab.filePath) {
      // 从 store 获取 workspaceRoot
      const { useIDEStore } = await import("@/stores/useIDEStore")
      const ideStore = useIDEStore()
      const root = ideStore.workspaceRoot
      if (root) {
        await gitBlame.loadBlame(root, props.activeTab.filePath)
      }
    }
    applyBlameDecorations()
  } else {
    const editor = editorInstance.value
    if (editor && monacoRaw && blameDecorationIds.length > 0) {
      editor.deltaDecorations(blameDecorationIds, [])
      blameDecorationIds = []
    }
  }
}

// ── FIM 代码补全 ──
const fim = useFIMCompletion(editorInstance, monacoInstance, {
  filePath: props.activeTab.filePath || "",
  language: props.activeTab.language || "plaintext",
  enabled: true,
  debounceMs: 300,
})
let fimKeydownDisposable: monacoNs.IDisposable | null = null

// ── Session 37: Inline 调试变量显示 ──
const inlineDebug = useInlineDebugValues(editorInstance, monacoInstance)

// ── Session 38: 编辑器智能（Hover + SignatureHelp）──
const editorIntel = useEditorIntelligence(monacoInstance)

// ── Session 42: Inline Chat (Ctrl+I) ──
const showInlineChat = ref(false)
const inlineChatLine = ref(1)
const inlineChatContext = ref("")
function toggleInlineChat(): void {
  const editor = editorInstance.value
  if (!editor) return
  const pos = editor.getPosition()
  if (!pos) return
  const model = editor.getModel()
  if (!model) return
  // 获取当前行上下文（当前行 + 前后各 2 行）
  const startLine = Math.max(1, pos.lineNumber - 2)
  const endLine = Math.min(model.getLineCount(), pos.lineNumber + 2)
  let ctx = ""
  for (let i = startLine; i <= endLine; i++) {
    ctx += model.getLineContent(i) + "\n"
  }
  inlineChatLine.value = pos.lineNumber
  inlineChatContext.value = ctx.trim()
  showInlineChat.value = !showInlineChat.value
}
// 暴露到全局供 keybinding 调用
if (typeof window !== "undefined") (window as any).__toggleInlineChat = toggleInlineChat

// ── Session 38: F2 重命名符号 ──
const showRenameInput = ref(false)
const renameX = ref(0)
const renameY = ref(0)
const renameSymbolName = ref("")
const renameOccurrencesCount = ref(0)
/** 重命名所有匹配位置 (line, col, length) */
let renameLocations: { line: number; col: number; endCol: number }[] = []
/** 重命名装饰 IDs (高亮所有匹配项) */
let renameHighlightIds: string[] = []
/** 是否正在重命名中 */
let isRenaming = false

/**
 * 在当前模型中找到符号的所有匹配位置（简单文本匹配）
 * 借鉴 VSCode renameProvider.resolveRenameLocation
 */
function findRenameLocations(symbol: string): { line: number; col: number; endCol: number }[] {
  const editor = editorInstance.value
  if (!editor) return []
  const model = editor.getModel()
  if (!model) return []

  // 排除的标识符：关键字、内置类型
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
  ])

  // 不允许重命名关键字
  if (excluded.has(symbol)) return []

  const locations: { line: number; col: number; endCol: number }[] = []
  const regex = new RegExp(`\\b${symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g")
  const fullContent = model.getValue()
  const lines = fullContent.split("\n")

  for (let i = 0; i < lines.length; i++) {
    let match: RegExpExecArray | null
    const lineRegex = new RegExp(`\\b${symbol.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "g")
    while ((match = lineRegex.exec(lines[i])) !== null) {
      // 排除注释中的匹配
      const beforeMatch = lines[i].substring(0, match.index)
      const isInLineComment = /\/\/.*$/.test(beforeMatch)
      const isInBlockComment = /\/\*[^*]*$/.test(beforeMatch) || /^[^*]*\*\//.test(lines[i].substring(match.index))
      if (!isInLineComment && !isInBlockComment && !/^["'`]/.test(lines[i].substring(match.index + symbol.length).trimStart())) {
        locations.push({
          line: i + 1,
          col: match.index + 2, // Monaco column is 1-based, +1 for the match start +1 for Monaco convention? Actually Monaco column starts at 1, and index starts at 0, so col = index + 1
          endCol: match.index + symbol.length + 1,
        })
      }
    }
  }

  return locations
}

/** 高亮所有重命名匹配项 */
function highlightRenameLocations(locations: typeof renameLocations): void {
  const editor = editorInstance.value
  if (!editor || !monacoRaw) return
  const monaco = monacoRaw

  // 清除旧高亮
  if (renameHighlightIds.length > 0) {
    editor.deltaDecorations(renameHighlightIds, [])
    renameHighlightIds = []
  }

  const decos = locations.map(loc => ({
    range: new monaco.Range(loc.line, loc.col, loc.line, loc.endCol),
    options: {
      className: "rename-highlight",
      inlineClassName: "rename-highlight-text",
    },
  }))

  renameHighlightIds = editor.deltaDecorations([], decos)
}

/** 清除重命名高亮 */
function clearRenameHighlights(): void {
  const editor = editorInstance.value
  if (!editor) return
  if (renameHighlightIds.length > 0) {
    editor.deltaDecorations(renameHighlightIds, [])
    renameHighlightIds = []
  }
}

/** 执行重命名：先尝试后端 LSP 语义重命名，回退到本地匹配 (Session 53) */
async function executeRename(oldName: string, newName: string): Promise<void> {
  const editor = editorInstance.value
  if (!editor || !monacoRaw) return
  const monaco = monacoRaw

  // 尝试后端 LSP rename API
  const pos = editor.getPosition()
  if (pos) {
    try {
      const result = await lspApi.rename({
        content: editor.getValue(),
        language: props.activeTab.language || "plaintext",
        file_path: props.activeTab.filePath || "",
        position_line: pos.lineNumber - 1,
        position_column: pos.column - 1,
        new_name: newName,
      })
      if (result.edits && result.edits.length > 0 && !result.reject_reason) {
        const edits = result.edits.map(e => ({
          range: new monaco.Range(
            e.range.start_line + 1, e.range.start_column + 1,
            e.range.end_line + 1, e.range.end_column + 1),
          text: e.new_text,
        }))
        editor.executeEdits("rename-symbol-lsp", edits)
        clearRenameHighlights()
        showRenameInput.value = false
        isRenaming = false
        renameLocations = []
        editor.focus()
        return
      }
    } catch { /* 回退到本地 */ }
  }

  // 本地回退
  const edits = renameLocations.map(loc => ({
    range: new monaco.Range(loc.line, loc.col, loc.line, loc.endCol),
    text: newName,
  }))

  editor.executeEdits("rename-symbol", edits)
  clearRenameHighlights()
  showRenameInput.value = false
  isRenaming = false
  renameLocations = []

  // 光标回到重命名后位置
  editor.focus()
}

/** 启动重命名流程 (F2) — Session 53: 集成后端 LSP 语义重命名 */
async function startRename(): Promise<void> {
  const editor = editorInstance.value
  if (!editor) return

  const model = editor.getModel()
  if (!model) return

  const pos = editor.getPosition()
  if (!pos) return

  // 获取光标处的标识符
  const lineContent = model.getLineContent(pos.lineNumber)
  const col = pos.column - 1 // 0-based

  // 向左右扩展找到完整的标识符
  let start = col
  let end = col
  while (start > 0 && /[\w$]/.test(lineContent[start - 1])) start--
  while (end < lineContent.length && /[\w$]/.test(lineContent[end])) end++

  const symbol = lineContent.substring(start, end)

  if (!symbol || symbol.length === 0) return

  // 排除空选择和非标识符
  if (!/^[a-zA-Z_$][\w$]*$/.test(symbol)) return

  // 尝试后端 LSP prepareRename (Session 53)
  let resolvedSymbol = symbol
  try {
    const prepare = await lspApi.prepareRename({
      content: editor.getValue(),
      language: props.activeTab.language || "plaintext",
      file_path: props.activeTab.filePath || "",
      position_line: pos.lineNumber - 1,
      position_column: pos.column - 1,
    })
    if (prepare.can_rename && prepare.text) {
      resolvedSymbol = prepare.text
    }
  } catch { /* 回退到本地 */ }

  // 找到所有匹配位置
  const locations = findRenameLocations(resolvedSymbol)
  if (locations.length === 0) return

  renameLocations = locations
  renameSymbolName.value = resolvedSymbol
  renameOccurrencesCount.value = locations.length

  // 高亮所有匹配项
  highlightRenameLocations(locations)

  // 计算 RenameInput 显示位置
  const coords = editor.getScrolledVisiblePosition(pos)
  const container = containerRef.value
  const rect = container?.getBoundingClientRect()

  if (rect && coords) {
    renameX.value = rect.left + coords.left
    renameY.value = rect.top + coords.top - 30
  } else {
    renameX.value = window.innerWidth / 2 - 160
    renameY.value = window.innerHeight / 2 - 40
  }

  showRenameInput.value = true
  isRenaming = true
}

/** 重命名预览更新（实时高亮更新） */
function onRenameUpdatePreview(newName: string): void {
  // 清除旧高亮并在新名称位置重新高亮
  // 这里简化处理，保持原高亮
}

/** 重命名确认 */
function onRenameConfirm(newName: string): void {
  executeRename(renameSymbolName.value, newName)
}

/** 重命名取消 */
function onRenameCancel(): void {
  clearRenameHighlights()
  showRenameInput.value = false
  isRenaming = false
  renameLocations = []
  editorInstance.value?.focus()
}

// ── Find Widget 状态 ──
const showFindWidget = ref(false)
const findWidgetMode = ref<"find" | "replace">("find")
/** 在整篇文档中找到匹配数 */
function findMatchesInDoc(query: string, caseSensitive: boolean, wholeWord: boolean, regex: boolean): number {
  const editor = editorInstance.value
  if (!editor || !query) return 0
  const model = editor.getModel()
  if (!model) return 0
  const text = model.getValue()
  let pattern: RegExp
  try {
    if (regex) {
      pattern = new RegExp(query, caseSensitive ? "g" : "gi")
    } else {
      const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
      pattern = new RegExp(wholeWord ? `\\b${escaped}\\b` : escaped, caseSensitive ? "g" : "gi")
    }
  } catch {
    return 0
  }
  return (text.match(pattern) || []).length
}

/** 触发查找(Ctrl+F) */
function toggleFindWidget(): void {
  if (showFindWidget.value && findWidgetMode.value === "find") {
    showFindWidget.value = false
  } else {
    showFindWidget.value = true
    findWidgetMode.value = "find"
  }
}
/** 触发替换(Ctrl+H) */
function toggleReplaceWidget(): void {
  if (showFindWidget.value && findWidgetMode.value === "replace") {
    showFindWidget.value = false
  } else {
    showFindWidget.value = true
    findWidgetMode.value = "replace"
  }
}
/** FindWidget 导航到某个匹配 */
function onFindNavigateTo(line: number, col: number, endCol: number): void {
  const editor = editorInstance.value
  if (!editor) return
  editor.revealLineInCenter(line)
  editor.setPosition({ lineNumber: line, column: endCol || col })
  editor.setSelection({ startLineNumber: line, startColumn: col, endLineNumber: line, endColumn: endCol || col + 1 })
}
/** FindWidget 关闭 */
function onFindClose(): void {
  showFindWidget.value = false
  editorInstance.value?.focus()
}

// ── VSCode 右键上下文菜单 ──
const contextMenuVisible = ref(false)
const contextMenuX = ref(0)
const contextMenuY = ref(0)
const contextMenuItems = ref<ContextMenuItem[]>([])

// ── Go To Symbol 弹窗 ──
const showGoToSymbol = ref(false)

/** GoToSymbol 跳转回调：滚动到指定行/列并聚焦编辑器 */
function onGoToSymbol(line: number, column: number): void {
  const editor = editorInstance.value
  if (!editor) return
  editor.revealLineInCenter(line)
  editor.setPosition({ lineNumber: line, column })
  editor.focus()
}

// ── Session 37: Code Actions 灯泡菜单 ──

const showCodeActions = ref(false)
const codeActionsX = ref(0)
const codeActionsY = ref(0)
const codeActions = ref<CodeAction[]>([])
const codeActionsMsg = ref("")
/** 灯泡装饰 ID */
let lightbulbDecoId: string | null = null
/** 当前灯泡所在行 */
let lightbulbLine = -1

/**
 * 扫描当前行的问题并生成对应的 Code Actions
 * 借鉴 VSCode lightBulbWidget + codeActionWidget
 */
function scanLineProblems(lineNumber: number): CodeAction[] {
  const editor = editorInstance.value
  if (!editor) return []
  const model = editor.getModel()
  if (!model) return []

  const lineContent = model.getLineContent(lineNumber)
  if (!lineContent.trim()) return []

  const actions: CodeAction[] = []

  // ── console 语句 ──
  if (/\bconsole\.(log|debug|warn|info)\s*\(/.test(lineContent) && !/^\s*\/\//.test(lineContent)) {
    const m = lineContent.match(/\bconsole\.(\w+)\s*\(/)
    const method = m?.[1] ?? 'log'
    actions.push({
      id: "remove-console",
      title: `移除 console.${method}() 语句`,
      kind: "quickfix",
      isPreferred: true,
    })
    actions.push({
      id: "comment-console",
      title: `注释 console.${method}() 语句`,
      kind: "quickfix",
    })
  }

  // ── TODO / FIXME / HACK ──
  if (/\b(TODO|FIXME|HACK|XXX)\b/.test(lineContent)) {
    const tag = (lineContent.match(/\b(TODO|FIXME|HACK|XXX)\b/) ?? [])[1] ?? 'TODO'
    actions.push({
      id: "resolve-todo",
      title: `标记 ${tag} 为已处理`,
      kind: "quickfix",
      isPreferred: actions.length === 0,
    })
  }

  // ── 空 catch 块 ──
  if (/catch\s*\([^)]*\)\s*\{\s*\}/.test(lineContent)) {
    actions.push({
      id: "add-catch-log",
      title: "添加 console.error(err) 日志",
      kind: "quickfix",
      isPreferred: actions.length === 0,
    })
    actions.push({
      id: "add-catch-rethrow",
      title: "添加 err 信息后重新抛出",
      kind: "quickfix",
    })
  }

  // ── var 声明 (建议改用 let/const) ──
  if (/\bvar\s+\w+\b/.test(lineContent.replace(/['"`].*?['"`]/g, ''))) {
    actions.push({
      id: "var-to-const",
      title: "将 'var' 改为 'const'",
      kind: "refactor",
    })
    actions.push({
      id: "var-to-let",
      title: "将 'var' 改为 'let'",
      kind: "refactor",
    })
  }

  // ── 硬编码颜色 hex 值 ──
  if (/#[0-9a-fA-F]{3,8}\b/.test(lineContent) && /['"`]/.test(lineContent)) {
    actions.push({
      id: "extract-color-var",
      title: "提取颜色值为 CSS 变量",
      kind: "refactor",
    })
  }

  // ── 长函数体 (超过 30 行的函数/方法) ──
  if (/^(export\s+)?(async\s+)?function\s+\w+|^\s*(public\s+)?(async\s+)?\w+\s*\(/.test(lineContent)) {
    let braceCount = 0
    let endLine = lineNumber
    for (let i = lineNumber; i <= model.getLineCount(); i++) {
      const l = model.getLineContent(i)
      braceCount += (l.match(/\{/g) || []).length
      braceCount -= (l.match(/\}/g) || []).length
      if (braceCount > 0 && braceCount <= 0 && i > lineNumber + 5) { endLine = i; break }
      if (i > lineNumber + 50) { endLine = i; break }
    }
    if (endLine - lineNumber > 30) {
      actions.push({
        id: "extract-method",
        title: "提取到独立函数",
        kind: "refactor",
      })
    }
  }

  // ── 缺少分号的行（JS/TS 模式） ──
  const lang = model.getLanguageId()
  if (['javascript', 'typescript', 'javascriptreact', 'typescriptreact'].includes(lang)) {
    const trimmed = lineContent.trim()
    if (trimmed.length > 0 &&
        !trimmed.endsWith(';') &&
        !trimmed.endsWith('{') &&
        !trimmed.endsWith('}') &&
        !trimmed.endsWith(':') &&
        !trimmed.endsWith(',') &&
        !/^\s*(\/\/|\/\*|\*|\#|import|export\s+(type|interface)|if\s*\(|for\s*\(|while\s*\(|switch\s*\(|else|try|catch|finally|class\s+|function\s+|return\s*$)/.test(trimmed)) {
      actions.push({
        id: "add-semicolon",
        title: "添加缺少的分号",
        kind: "source",
      })
    }
  }

  // ── 未使用的 import (简单检测：导入但未在文件中使用) ──
  if (/^import\s+/.test(lineContent) && !/^\s*\/\//.test(lineContent)) {
    const importMatch = lineContent.match(/import\s+\{?\s*(\w+)/)
    const name = importMatch?.[1]
    if (name) {
      const fullContent = model.getValue()
      // 如果导入的名字在文件中只出现这一次，标记为可能未使用
      const re = new RegExp(`\\b${name}\\b`, 'g')
      const matches = fullContent.match(re)
      if (!matches || matches.length <= 1) {
        actions.push({
          id: "remove-unused-import",
          title: `移除未使用的导入 "${name}"`,
          kind: "source",
        })
      }
    }
  }

  return actions
}

/** 显示灯泡装饰（在问题行的 glyph margin 处） */
function showLightbulb(lineNumber: number): void {
  const editor = editorInstance.value
  if (!editor || !monacoRaw) return
  const monaco = monacoRaw

  // 同位置已有灯泡，不重复创建
  if (lightbulbLine === lineNumber && lightbulbDecoId) return
  hideLightbulb()

  lightbulbLine = lineNumber
  const ids = editor.deltaDecorations([], [{
    range: new monaco.Range(lineNumber, 1, lineNumber, 1),
    options: {
      isWholeLine: false,
      glyphMarginClassName: "code-actions-lightbulb",
      glyphMarginHoverMessage: { value: "💡 代码操作 (Ctrl+.)" },
      stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
      zIndex: 10,
    },
  }])
  if (ids.length > 0) lightbulbDecoId = ids[0]
}

/** 隐藏灯泡装饰 */
function hideLightbulb(): void {
  const editor = editorInstance.value
  if (!editor || !lightbulbDecoId) return
  editor.deltaDecorations([lightbulbDecoId], [])
  lightbulbDecoId = null
  lightbulbLine = -1
}

/** 展示 Code Actions 菜单（在灯泡点击或 Ctrl+. 时调用） */
async function showCodeActionsMenu(x: number, y: number, lineNumber: number): Promise<void> {
  const editor = editorInstance.value
  if (!editor) return

  const localActions = scanLineProblems(lineNumber)

  // Session 48: 并发获取后端 Code Actions
  const backendActions: any[] = []
  try {
    const content = editor.getValue()
    const lang = props.activeTab.language || "plaintext"
    const res = await fetch(`${formatApiBase}/system/code-actions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        content,
        language: lang,
        diagnostics: [],
        range_start_line: lineNumber,
        range_start_col: 1,
      }),
    })
    if (res.ok) {
      const data = await res.json()
      backendActions.push(...(data.actions || []))
    }
  } catch { /* 静默 */ }

  // 合并：后端 API 返回的 code actions 转成本地 CodeAction 格式
  const mergedActions = [...localActions]
  for (const ba of backendActions) {
    mergedActions.push({
      id: `backend-${ba.kind}-${mergedActions.length}`,
      label: ba.title,
      priority: ba.is_preferred ? "HIGH" : "MEDIUM",
      source: "backend-api",
      _rawAction: ba,
    } as any)
  }

  if (mergedActions.length === 0) return

  const model = editor.getModel()
  const msg = model?.getLineContent(lineNumber)?.trim()?.slice(0, 60) ?? ""

  codeActions.value = mergedActions as CodeAction[]
  codeActionsMsg.value = msg
  codeActionsX.value = x
  codeActionsY.value = y
  showCodeActions.value = true
}

/** 执行 Code Action */
function onCodeAction(action: CodeAction): void {
  const editor = editorInstance.value
  if (!editor) return

  // Session 48: 处理后端 API 返回的 Code Action
  if ((action as any)._rawAction) {
    applyCodeAction((action as any)._rawAction)
    showCodeActions.value = false
    return
  }

  const model = editor.getModel()
  if (!model) return

  const line = lightbulbLine > 0 ? lightbulbLine : editor.getPosition()?.lineNumber ?? 1
  const content = model.getLineContent(line)

  switch (action.id) {
    case "remove-console":
      // 删除整行
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line + 1, 1),
        text: "",
      }])
      break

    case "comment-console":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line, 1),
        text: "// ",
      }])
      break

    case "resolve-todo": {
      const tag = (content.match(/\b(TODO|FIXME|HACK|XXX)\b/) ?? [])[1] ?? 'TODO'
      const resolved = content.replace(new RegExp(`\\b${tag}\\b`), `${tag}(已处理)`)
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line, content.length + 1),
        text: resolved,
      }])
      break
    }

    case "add-catch-log":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line, content.length + 1),
        text: content.replace(/\{\s*\}/, `{ console.error(err); }`),
      }])
      break

    case "add-catch-rethrow":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line, content.length + 1),
        text: content.replace(/\{\s*\}/, `{ console.error(err); throw err; }`),
      }])
      break

    case "var-to-const":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line, content.length + 1),
        text: content.replace(/\bvar\b/, "const"),
      }])
      break

    case "var-to-let":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line, content.length + 1),
        text: content.replace(/\bvar\b/, "let"),
      }])
      break

    case "extract-color-var":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line, 1),
        text: "// TODO: 提取为 CSS 变量\n",
      }])
      break

    case "extract-method":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line, 1),
        text: "// TODO: 考虑提取为独立函数以减少复杂度\n",
      }])
      break

    case "add-semicolon":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, content.length + 1, line, content.length + 1),
        text: ";",
      }])
      break

    case "remove-unused-import":
      editor.executeEdits("code-action", [{
        range: new monacoRaw!.Range(line, 1, line + 1, 1),
        text: "",
      }])
      break

    default:
      console.warn("[CodeBuddy] Unknown code action:", action.id)
  }

  hideLightbulb()
  showCodeActions.value = false

  // 重新扫描当前行更新灯泡
  setTimeout(() => updateLightbulbForCursor(), 100)
}

/** 光标移动时更新灯泡 */
function updateLightbulbForCursor(): void {
  const editor = editorInstance.value
  if (!editor) return

  const pos = editor.getPosition()
  if (!pos) { hideLightbulb(); return }

  // 显示灯泡
  const model = editor.getModel()
  if (!model) return

  const lineContent = model.getLineContent(pos.lineNumber)
  // 只在非空行且有问题时显示灯泡
  const hasPotentialIssue =
    /\bconsole\.(log|debug|warn|info)\s*\(/.test(lineContent) ||
    /\b(TODO|FIXME|HACK|XXX)\b/.test(lineContent) ||
    /catch\s*\([^)]*\)\s*\{\s*\}/.test(lineContent) ||
    (/\bvar\s+\w+\b/.test(lineContent.replace(/['"`].*?['"`]/g, ''))) ||
    (/#[0-9a-fA-F]{3,8}\b/.test(lineContent) && /['"`]/.test(lineContent)) ||
    (lineContent.trim() && !lineContent.trim().endsWith(';') &&
     !lineContent.trim().endsWith('{') && !lineContent.trim().endsWith('}') &&
     ['javascript', 'typescript', 'javascriptreact', 'typescriptreact'].includes(model.getLanguageId()) &&
     !/^\s*(\/\/|\/\*|\*|\#|import)/.test(lineContent.trim())) ||
    (/^import\s+/.test(lineContent) && !/^\s*\/\//.test(lineContent))

  if (hasPotentialIssue) {
    showLightbulb(pos.lineNumber)
  } else {
    hideLightbulb()
  }
}

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
    { id: "goto-symbol", label: "转到符号...", shortcut: "Ctrl+Shift+O", action: () => { showGoToSymbol.value = true } },
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

// ── Session 46: Unicode 高亮辅助 ──
/** 可疑 Unicode 字符模式（零宽字符、同形异义字符等） */
const SUSPICIOUS_UNICODE = /[\u200B\u200C\u200D\u200E\u200F\u202A-\u202E\u2060-\u2064\uFEFF\u00AD\u034F\u17B4\u17B5]/g
/** 混淆字符（与 ASCII 外观相似的 Unicode） */
const CONFUSABLE_UNICODE = /[\u0430\u0441\u0443\u0435\u043E\u0440\u0445\u0391\u0392\u0395\u0396\u0397\u0399\u039A\u039C\u039D\u039F\u03A1\u03A4\u03A5\u03A7]/

/** 扫描并高亮文档中的可疑 Unicode 字符 */
function applyUnicodeHighlights(editor: monacoNs.editor.IStandaloneCodeEditor, monaco: typeof monacoNs): void {
  if (!unicodeHighlightEnabled.value) {
    if (unicodeHighlightIds.length > 0) {
      editor.deltaDecorations(unicodeHighlightIds, [])
      unicodeHighlightIds = []
    }
    return
  }
  const model = editor.getModel()
  if (!model) return

  const decos: monacoNs.editor.IModelDeltaDecoration[] = []
  const text = model.getValue()
  const lines = text.split("\n")

  for (let i = 0; i < lines.length; i++) {
    let match: RegExpExecArray | null
    SUSPICIOUS_UNICODE.lastIndex = 0
    while ((match = SUSPICIOUS_UNICODE.exec(lines[i])) !== null) {
      decos.push({
        range: new monaco.Range(i + 1, match.index + 1, i + 1, match.index + match[0].length + 1),
        options: {
          className: "unicode-highlight-suspicious",
          inlineClassName: "unicode-highlight-suspicious-text",
          hoverMessage: { value: `⚠️ 可疑 Unicode 字符 \`U+${match[0].codePointAt(0)?.toString(16).toUpperCase().padStart(4, "0")}\` — 可能是混淆攻击` },
          overviewRuler: { color: "#d29922", position: monaco.editor.OverviewRulerLane.Center },
        },
      })
    }
    CONFUSABLE_UNICODE.lastIndex = 0
    while ((match = CONFUSABLE_UNICODE.exec(lines[i])) !== null) {
      decos.push({
        range: new monaco.Range(i + 1, match.index + 1, i + 1, match.index + match[0].length + 1),
        options: {
          className: "unicode-highlight-confusable",
          inlineClassName: "unicode-highlight-confusable-text",
          hoverMessage: { value: `🔍 易混淆字符 \`U+${match[0].codePointAt(0)?.toString(16).toUpperCase().padStart(4, "0")}\` — 与 ASCII 字符外观相似` },
          overviewRuler: { color: "#61AFEF", position: monaco.editor.OverviewRulerLane.Center },
        },
      })
    }
  }

  unicodeHighlightIds = editor.deltaDecorations(unicodeHighlightIds, decos)
}

/** 长行指示器 — 在超过 120 字符的行后显示视觉标识 */
function applyLongLinesIndicator(editor: monacoNs.editor.IStandaloneCodeEditor, monaco: typeof monacoNs): void {
  const model = editor.getModel()
  if (!model) return

  // Monaco 自带 rulers 即可标注 80/120 列
  const enabled = longLinesEnabled.value
  editor.updateOptions({
    rulers: enabled ? [80, 120] : [],
  })
}

/** 光标撤销：保存当前光标位置到栈 */
function pushCursorUndo(editor: monacoNs.editor.IStandaloneCodeEditor): void {
  const pos = editor.getPosition()
  if (!pos) return
  // 限制栈大小
  if (cursorUndoStack.length > 50) cursorUndoStack.shift()
  cursorUndoStack.push({ lineNumber: pos.lineNumber, column: pos.column })
  cursorUndoIndex = cursorUndoStack.length - 1
}

/** 光标撤销：Ctrl+U 恢复到上一个光标位置 */
function cursorUndo(editor: monacoNs.editor.IStandaloneCodeEditor): void {
  if (cursorUndoStack.length < 2 || cursorUndoIndex <= 0) return
  cursorUndoIndex--
  const prev = cursorUndoStack[cursorUndoIndex]
  const model = editor.getModel()
  if (!model) return
  const lineCount = model.getLineCount()
  const safeLine = Math.min(prev.lineNumber, lineCount)
  const lineContent = model.getLineContent(safeLine)
  const safeCol = Math.min(prev.column, lineContent.length + 1)
  editor.setPosition({ lineNumber: safeLine, column: safeCol })
  editor.revealPositionInCenter({ lineNumber: safeLine, column: safeCol })
}

/** 字体缩放 */
function zoomFontIn(): void {
  fontSizeLevel = Math.min(MAX_FONT_SIZE, fontSizeLevel + 2)
  editorInstance.value?.updateOptions({ fontSize: fontSizeLevel })
}
function zoomFontOut(): void {
  fontSizeLevel = Math.max(MIN_FONT_SIZE, fontSizeLevel - 2)
  editorInstance.value?.updateOptions({ fontSize: fontSizeLevel })
}
function resetFontZoom(): void {
  fontSizeLevel = 14
  editorInstance.value?.updateOptions({ fontSize: fontSizeLevel })
}

/** Tab 聚焦模式切换 */
function toggleTabFocusMode(editor: monacoNs.editor.IStandaloneCodeEditor): void {
  tabFocusMode.value = !tabFocusMode.value
  editor.updateOptions({ tabFocusMode: tabFocusMode.value })
}

/** 中键滚动切换 */
function toggleMiddleScroll(editor: monacoNs.editor.IStandaloneCodeEditor): void {
  const current = editor.getOption(monacoRaw!.editor.EditorOption.scrollbar)
  editor.updateOptions({
    scrollbar: {
      ...current,
      useShadows: !current.useShadows, // 简单切换
    },
  })
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
  // Wait for DOM to be mounted, especially in group mode where
  // CodeEditor instances may be created/destroyed rapidly
  if (!containerRef.value) {
    await nextTick()
    if (!containerRef.value) {
      console.warn("[CodeBuddy] initMonaco: container not ready")
      return
    }
  }
  try {
    // Monaco 0.52+ uses named exports, not default
    // The import returns the namespace directly
    const monacoModule: any = await import("monaco-editor")
    const monaco: typeof monacoNs = (monacoModule.default ?? monacoModule) as typeof monacoNs
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
        "editor.background": "#1E1E1E",
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
      fontSize: 14,
      fontFamily:
        "'Cascadia Code', 'JetBrains Mono', 'Fira Code', Consolas, 'Courier New', monospace",
      fontLigatures: true,
      lineHeight: 22,
      padding: { top: 0, bottom: 0 },
      minimap: { enabled: true, maxColumn: 120, scale: 1, showRegionSectionHeaders: true },
      scrollBeyondLastLine: true,
      smoothScrolling: true,
      cursorBlinking: "smooth",
      cursorSmoothCaretAnimation: "on",
      /** Session 42: Emmet 支持 (Monaco 内置) */
      tabCompletion: "on",
      /** Session 25: VSCode 整行高亮 + 缩进参考线增强 */
      renderLineHighlight: "all",
      guides: { indentation: true, bracketPairs: true, bracketPairsHorizontal: true, highlightActiveIndentation: true },
      /** Session 25: 垂直标尺线 (80 char 灰线, 120 char 红线) */
      rulers: [80, 120],
      /** Session 25: 选择时显示空白字符 */
      renderWhitespace: "selection",
      /** Session 45: VSCode Selection Highlight + 选中词高亮 */
      occurrencesHighlight: true,
      selectionHighlight: true,
      renderLineHighlightOnlyWhenFocus: false,
      /** Session 25: 3 条 overview ruler */
      overviewRulerLanes: 3,
      /** Session 25: 鼠标悬停时显示折叠控件 */
      showFoldingControls: "mouseover",
      wordWrap: "off",
      folding: true,
      foldingStrategy: "indentation",
      lineNumbers: "on",
      lineNumbersMinChars: 5,
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
      /** Session 27: VSCode CodeLens + 语义高亮 */
      codeLens: true,
      "semanticHighlighting.enabled": true,
      tabCompletion: "on",
      autoClosingBrackets: "always",
      autoClosingQuotes: "always",
      /** Session 23: 禁用 Monaco 内置右键菜单，使用自定义 VSCode 风格菜单 */
      contextmenu: false,
    })
    editorInstance.value = editor

    /** Session 47: 注册 formatDocument 到全局，供 Ctrl+S (formatOnSave) 使用 */
    ;(window as any).__formatActiveDocument = formatDocument

    /** Session 47: 检测异常行终止符 (LS/PS) */
    const termCheck = detectUnusualLineTerminators(props.activeTab.content)
    if (termCheck.hasUnusual) {
      console.warn(`[CodeEditor] ⚠️ 检测到异常行终止符: ${termCheck.details}`)
      // 自动移除异常终止符并更新编辑器
      const cleaned = autoRemoveUnusualTerminators(props.activeTab.content)
      editor.setValue(cleaned)
      emit("update-content", cleaned)
    }

    /** Session 23: 自定义右键上下文菜单（VSCode 风格） */
    editor.onContextMenu((e) => {
      e.event.preventDefault()
      contextMenuItems.value = buildEditorContextMenu(editor)
      contextMenuX.value = e.event.posx
      contextMenuY.value = e.event.posy
      contextMenuVisible.value = true
    })

    /** Session 37: 灯泡 glyph margin 点击 → 打开 Code Actions 菜单 */
    editor.onMouseDown((e) => {
      if (e.target.type === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN && e.target.detail) {
        // 检测是否点击了灯泡装饰
        const decoId = e.target.detail as unknown as string
        if (decoId === lightbulbDecoId) {
          e.event.preventDefault()
          const lineNum = e.target.position?.lineNumber ?? 1
          showCodeActionsMenu(e.event.posx, e.event.posy, lineNum)
        }
      }
    })

    /** Session 38: F2 重命名符号 */
    editor.addAction({
      id: "codebuddy.renameSymbol",
      label: "重命名符号",
      keybindings: [monaco.KeyCode.F2],
      contextMenuGroupId: "modification",
      contextMenuOrder: 1,
      run: () => {
        startRename()
      },
    })

    /** Session 37: Ctrl+. 快捷键 → 打开 Code Actions */
    editor.addAction({
      id: "codebuddy.showCodeActions",
      label: "代码操作...",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Period],
      contextMenuGroupId: "navigation",
      contextMenuOrder: 1.5,
      run: (ed) => {
        const pos = ed.getPosition()
        if (!pos) return
        const coords = ed.getScrolledVisiblePosition(pos)
        if (!coords) return
        // 获取编辑器容器在页面中的位置
        const container = containerRef.value
        const rect = container?.getBoundingClientRect()
        if (rect) {
          showCodeActionsMenu(
            rect.left + coords.left + 30,
            rect.top + coords.top + 20,
            pos.lineNumber,
          )
        }
      },
    })
    /** Session 39: Ctrl+F 打开查找控件 */
    editor.addAction({
      id: "codebuddy.find",
      label: "查找",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyF],
      run: () => { toggleFindWidget() },
    })
    /** Session 39: Ctrl+H 打开替换控件 */
    editor.addAction({
      id: "codebuddy.replace",
      label: "替换",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyH],
      run: () => { toggleReplaceWidget() },
    })

    // ── Session 45: VSCode Editor Actions (joinLines / sortLines / transformCase) ──
    /** Join Lines (Ctrl+J) — 将下一行合并到当前行 */
    editor.addAction({
      id: "codebuddy.joinLines",
      label: "Join Lines",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyJ],
      run: (ed) => {
        const pos = ed.getPosition()
        const model = ed.getModel()
        if (!pos || !model) return
        if (pos.lineNumber >= model.getLineCount()) return
        const line1 = model.getLineContent(pos.lineNumber)
        const line2 = model.getLineContent(pos.lineNumber + 1)
        // 智能合并：如果 line1 以逗号/运算符结尾则不添加空格
        const needsSpace = !/[,([{+\-*/=<>]$/.test(line1.trimEnd()) && line2.trimStart().length > 0
        const spacer = needsSpace ? " " : ""
        const joined = line1.replace(/\s+$/, "") + spacer + line2.trimStart()
        ed.executeEdits("joinLines", [{
          range: new monaco.Range(pos.lineNumber, 1, pos.lineNumber + 2, 1),
          text: joined + "\n",
        }])
        ed.setPosition({ lineNumber: pos.lineNumber, column: line1.length + spacer.length + 1 })
      },
    })

    /** Sort Lines Ascending / Descending */
    editor.addAction({
      id: "codebuddy.sortLinesAsc",
      label: "Sort Lines Ascending",
      contextMenuGroupId: "9_cutcopypaste",
      contextMenuOrder: 4,
      run: (ed) => {
        const sel = ed.getSelection()
        const model = ed.getModel()
        if (!sel || !model) return
        const startLine = sel.startLineNumber
        const endLine = sel.endLineNumber
        if (startLine === endLine && sel.isEmpty()) return
        const lines: string[] = []
        for (let i = startLine; i <= endLine; i++) lines.push(model.getLineContent(i))
        lines.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }))
        const text = lines.join("\n")
        ed.executeEdits("sortLinesAsc", [{
          range: new monaco.Range(startLine, 1, endLine, model.getLineMaxColumn(endLine)),
          text,
        }])
      },
    })

    editor.addAction({
      id: "codebuddy.sortLinesDesc",
      label: "Sort Lines Descending",
      contextMenuGroupId: "9_cutcopypaste",
      contextMenuOrder: 4.1,
      run: (ed) => {
        const sel = ed.getSelection()
        const model = ed.getModel()
        if (!sel || !model) return
        const startLine = sel.startLineNumber
        const endLine = sel.endLineNumber
        if (startLine === endLine && sel.isEmpty()) return
        const lines: string[] = []
        for (let i = startLine; i <= endLine; i++) lines.push(model.getLineContent(i))
        lines.sort((a, b) => b.localeCompare(a, undefined, { sensitivity: "base" }))
        const text = lines.join("\n")
        ed.executeEdits("sortLinesDesc", [{
          range: new monaco.Range(startLine, 1, endLine, model.getLineMaxColumn(endLine)),
          text,
        }])
      },
    })

    /** Transform Case (Uppercase / Lowercase / Titlecase) */
    editor.addAction({
      id: "codebuddy.transformToUppercase",
      label: "Transform to Uppercase",
      contextMenuGroupId: "9_cutcopypaste",
      contextMenuOrder: 5,
      run: (ed) => {
        const sel = ed.getSelection()
        const model = ed.getModel()
        if (!sel || !model || sel.isEmpty()) return
        const text = model.getValueInRange(sel)
        ed.executeEdits("toUppercase", [{
          range: sel,
          text: text.toUpperCase(),
        }])
      },
    })

    editor.addAction({
      id: "codebuddy.transformToLowercase",
      label: "Transform to Lowercase",
      contextMenuGroupId: "9_cutcopypaste",
      contextMenuOrder: 5.1,
      run: (ed) => {
        const sel = ed.getSelection()
        const model = ed.getModel()
        if (!sel || !model || sel.isEmpty()) return
        const text = model.getValueInRange(sel)
        ed.executeEdits("toLowercase", [{
          range: sel,
          text: text.toLowerCase(),
        }])
      },
    })

    editor.addAction({
      id: "codebuddy.transformToTitlecase",
      label: "Transform to Title Case",
      contextMenuGroupId: "9_cutcopypaste",
      contextMenuOrder: 5.2,
      run: (ed) => {
        const sel = ed.getSelection()
        const model = ed.getModel()
        if (!sel || !model || sel.isEmpty()) return
        const text = model.getValueInRange(sel)
        const titleCased = text.replace(/\b\w/g, c => c.toUpperCase())
        ed.executeEdits("toTitlecase", [{
          range: sel,
          text: titleCased,
        }])
      },
    })

    // ── Session 45: Emmet 补全注册 ──
    emmetDisposables = emmet.registerCompletionProvider(monaco)

    // ═══ Session 46: Smart Select (Shift+Alt+→/←) ═══
    editor.addAction({
      id: "codebuddy.expandSelection",
      label: "扩大选区",
      keybindings: [monaco.KeyMod.Shift | monaco.KeyMod.Alt | monaco.KeyCode.RightArrow],
      run: (ed) => {
        smartSelect.expand(ed, monaco)
      },
    })
    editor.addAction({
      id: "codebuddy.shrinkSelection",
      label: "缩小选区",
      keybindings: [monaco.KeyMod.Shift | monaco.KeyMod.Alt | monaco.KeyCode.LeftArrow],
      run: (ed) => {
        smartSelect.shrink(ed, monaco)
      },
    })

    // ═══ Session 46: Anchor Select (Ctrl+K Ctrl+B 设置锚点) ═══
    let anchorPos: monacoNs.IPosition | null = null
    editor.addAction({
      id: "codebuddy.setSelectionAnchor",
      label: "设置选区锚点",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK, monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyB],
      run: (ed) => {
        const pos = ed.getPosition()
        if (pos) anchorPos = { lineNumber: pos.lineNumber, column: pos.column }
      },
    })
    editor.addAction({
      id: "codebuddy.selectFromAnchor",
      label: "从锚点选择到光标",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK, monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK],
      run: (ed) => {
        if (!anchorPos) return
        const cur = ed.getPosition()
        if (!cur) return
        const startLine = Math.min(anchorPos.lineNumber, cur.lineNumber)
        const startCol = anchorPos.lineNumber <= cur.lineNumber ? anchorPos.column : cur.column
        const endLine = Math.max(anchorPos.lineNumber, cur.lineNumber)
        const endCol = anchorPos.lineNumber <= cur.lineNumber ? cur.column : anchorPos.column
        ed.setSelection(new monaco.Range(startLine, startCol, endLine, endCol))
      },
    })
    editor.addAction({
      id: "codebuddy.goToAnchor",
      label: "跳转到锚点",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK, monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK],
      run: (ed) => {
        // 如果已有选区，优先 selectFromAnchor；否则 goToAnchor
        if (anchorPos) ed.setPosition(anchorPos)
      },
    })

    // ═══ Session 46: Cursor Undo (Ctrl+U) ═══
    editor.addAction({
      id: "codebuddy.cursorUndo",
      label: "光标撤销",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyU],
      run: (ed) => cursorUndo(ed),
    })

    // ═══ Session 46: Font Zoom (Ctrl+/-) ═══
    editor.addAction({
      id: "codebuddy.fontZoomIn",
      label: "放大字体",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Equal],
      run: () => zoomFontIn(),
    })
    editor.addAction({
      id: "codebuddy.fontZoomOut",
      label: "缩小字体",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Minus],
      run: () => zoomFontOut(),
    })
    editor.addAction({
      id: "codebuddy.fontZoomReset",
      label: "重置字体缩放",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Digit0],
      run: () => resetFontZoom(),
    })

    // ═══ Session 46: Unicode Highlighter 切换 ═══
    editor.addAction({
      id: "codebuddy.toggleUnicodeHighlight",
      label: "切换 Unicode 高亮",
      run: (ed) => {
        unicodeHighlightEnabled.value = !unicodeHighlightEnabled.value
        applyUnicodeHighlights(ed, monaco)
      },
    })

    // ═══ Session 46: Toggle Tab Focus Mode ═══
    editor.addAction({
      id: "codebuddy.toggleTabFocusMode",
      label: "切换 Tab 键模式",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyM],
      run: (ed) => toggleTabFocusMode(ed),
    })

    // ═══ Session 47: VSCode Word Part Operations (子词导航) ═══
    // 在 camelCase / snake_case / kebab-case 内部按子词移动光标
    editor.addAction({
      id: "codebuddy.cursorWordPartLeft",
      label: "光标移动到上一个子词",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.LeftArrow],
      run: (ed) => ed.trigger("keyboard", "cursorWordPartLeft", null),
    })
    editor.addAction({
      id: "codebuddy.cursorWordPartRight",
      label: "光标移动到下一个子词",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.RightArrow],
      run: (ed) => ed.trigger("keyboard", "cursorWordPartRight", null),
    })
    editor.addAction({
      id: "codebuddy.deleteWordPartLeft",
      label: "删除左侧子词",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.Backspace],
      run: (ed) => ed.trigger("keyboard", "deleteWordPartLeft", null),
    })
    editor.addAction({
      id: "codebuddy.deleteWordPartRight",
      label: "删除右侧子词",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.Delete],
      run: (ed) => ed.trigger("keyboard", "deleteWordPartRight", null),
    })

    // ── Session 46: Linked Editing: 光标移动时激活 ──
    let linkedEditingTimer: ReturnType<typeof setTimeout> | null = null
    editor.onDidChangeCursorPosition((_e) => {
      pushCursorUndo(editor) // 光标撤销栈

      if (linkedEditingEnabled.value && !isRenaming) {
        if (linkedEditingTimer) clearTimeout(linkedEditingTimer)
        linkedEditingTimer = setTimeout(() => {
          linkedEditing.deactivate(editor)
          linkedEditing.activate(editor)
        }, 200)
      }
    })

    // ── 内容变更监听（原有逻辑）──
    editor.onDidChangeModelContent((e) => {
      emit("update-content", editor.getValue())
      /** Session 26: 延迟应用 QuickDiff (防抖 300ms) */
      if (quickDiffWatcher) clearTimeout(quickDiffWatcher)
      quickDiffWatcher = setTimeout(() => applyQuickDiff(), 300)
      /** Session 43: 延迟刷新 InlayHints (防抖 500ms) */
      if (inlayHintsTimer) clearTimeout(inlayHintsTimer)
      inlayHintsTimer = setTimeout(() => {
        if (showInlayHints.value && monacoRaw) {
          inlayHints.refreshHints(editor, monacoRaw, props.activeTab.language ?? "plaintext")
        }
      }, 500)
      /** Session 45: Error Lens — 延迟刷新行内诊断 (防抖 800ms) */
      if (showErrorLens.value) {
        if (errorLensTimer) clearTimeout(errorLensTimer)
        errorLensTimer = setTimeout(() => {
          const model = editor.getModel()
          if (model) {
            errorLens.applyFromScan(
              model.getValue(),
              props.activeTab.language ?? "plaintext",
              props.activeTab.filePath,
            )
          }
        }, 800)
      }
      /** Session 46: Word Highlighter + Linked Editing + Unicode (debounce 600ms) */
      setTimeout(() => {
        if (wordHighlightEnabled.value) {
          wordHighlighter.highlight(editor, monaco)
        }
        linkedEditing.onDidChangeContent(editor, e)
        applyUnicodeHighlights(editor, monaco)
      }, 600)
      /** Session 53: Semantic Tokens + Code Lens — LSP 后端刷新 (防抖 1200ms) */
      setTimeout(() => {
        semanticTokens.applySemanticTokens()
        codeLens.applyCodeLens()
      }, 1200)
    })

    // ── Session 47: Read-Only Editor 编辑拦截 ═══
    // 在只读编辑器中尝试编辑时，弹出提示消息
    editor.onDidAttemptReadOnlyEdit(() => {
      const msg = editor.getModel()?.getValueLength() === 0
        ? "无法在空只读编辑器中编辑"
        : "无法编辑只读编辑器中的内容"
      // 使用 Monaco message controller 在编辑器内显示浮动提示
      ;(editor as any).showMessage?.(msg) ?? console.warn("[CodeEditor]", msg)
    })

    // ── Session 47: Format on Paste 粘贴后自动格式化 ──
    editor.onDidPaste((e) => {
      if (!formatOnPasteEnabled.value) return
      const edits = e.range.map(r => ({
        range: r.range,
        text: model.getValueInRange(r.range),
      }))
      // 延迟格式化（等粘贴内容完成）
      setTimeout(() => formatDocument(), 100)
    })

    // Monaco 0.50+ renamed onCursorPositionChanged -> onDidChangeCursorPosition
    const cursorHandler = () => {
      const pos = editor.getPosition(),
        model = editor.getModel()
      const selections = editor.getSelections()
      emit("update-cursor", {
        line: pos?.lineNumber ?? 1,
        column: pos?.column ?? 1,
        totalLines: model?.getLineCount() ?? 1,
        selectedChars: editor.getSelection()?.toString().length ?? 0,
        languageId: model?.getLanguageId() ?? "plaintext",
        /** VSCode 风格: 多光标计数 (Ctrl+Alt+Down 或 Ctrl+D 添加光标) */
        multiCursorCount: selections ? selections.length : 1,
      })
      // Session 37: 更新灯泡装饰
      updateLightbulbForCursor()
    }
    if (typeof (editor as any).onDidChangeCursorPosition === "function") {
      (editor as any).onDidChangeCursorPosition(cursorHandler)
    } else if (typeof (editor as any).onCursorPositionChanged === "function") {
      (editor as any).onCursorPositionChanged(cursorHandler)
    }

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
    /** Session 53: 初始 LSP 特性 (语义高亮 + 代码透镜 + 代码折叠) */
    setTimeout(() => {
      semanticTokens.applySemanticTokens()
      codeLens.applyCodeLens()
    }, 800)
    // 注册折叠 Provider
    folding.registerFoldingProvider()
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
  /** Session 37: 内联调试变量控制 */
  showInlineDebug: inlineDebug.show,
  hideInlineDebug: inlineDebug.hide,
  /** Session 40: Git Blame 控制 */
  toggleBlame,
  showBlame,
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
      /** Session 40: 标签页切换后刷新 blame */
      if (showBlame.value) {
        setTimeout(() => applyBlameDecorations(), 800)
      }
    } else if (editorInstance.value) {
      monacoRaw.editor.setModelLanguage(
        editorInstance.value.getModel()!,
        props.activeTab.language ?? "plaintext",
      )
      /** Session 48: 语言未知时自动检测 */
      if (!props.activeTab.language || props.activeTab.language === "plaintext") {
        autoDetectLanguage()
      }
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

// ── Session 38: 从 localStorage 读取编辑器设置动态应用 ──
const EDITOR_SETTINGS_KEY = "ide_editor_settings_v2"
function getEditorSettings(): Record<string, unknown> {
  try {
    const raw = localStorage.getItem(EDITOR_SETTINGS_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return {}
}

/** 应用编辑器设置到 Monaco */
function applyEditorSettings(): void {
  const editor = editorInstance.value
  if (!editor) return
  const s = getEditorSettings()
  editor.updateOptions({
    minimap: { enabled: s.minimap !== false, showRegionSectionHeaders: s.minimap !== false },
    bracketPairColorization: { enabled: s.bracketColorization !== false },
    stickyScroll: { enabled: s.stickyScroll !== false },
    /** Session 47: InlayHints Monaco 选项同步 */
    inlayHints: { enabled: s.inlayHints !== false },
    guides: {
      indentation: s.indentGuides !== false,
      bracketPairs: s.indentGuides !== false,
      bracketPairsHorizontal: s.indentGuides !== false,
      highlightActiveIndentation: true,
    },
    parameterHints: { enabled: s.parameterHints !== false },
    renderWhitespace: (s.renderWhitespace as string) ?? "selection",
    /** Session 45: Selection Highlight + Overview Ruler */
    occurrencesHighlight: s.selectionHighlight !== false,
    selectionHighlight: s.selectionHighlight !== false,
    overviewRulerLanes: (s.overviewRuler !== false) ? ((s.overviewRulerLanes as number) ?? 3) : 0,
    /** Session 46: 新增设置 */
    codeLens: s.codeLens !== false,
    folding: s.folding !== false,
    matchBrackets: s.matchBrackets !== false ? "always" : "never",
    colorDecorators: s.colorDecorators !== false,
    renderControlCharacters: s.renderControlCharacters !== false,
    fontSize: (s.fontSize as number) ?? fontSizeLevel,
    /** placeholder text */
    ...(s.placeholderText ? { placeholder: s.placeholderText as string } : {}),
  })
  // Error Lens toggle
  if (typeof s.errorLens === "boolean") {
    showErrorLens.value = s.errorLens
    if (!s.errorLens) errorLens.clear(editor)
  }
  // Word Highlighter toggle
  if (typeof s.wordHighlight === "boolean") {
    wordHighlightEnabled.value = s.wordHighlight
    if (!s.wordHighlight) wordHighlighter.clear(editor)
  }
  // Unicode Highlighter toggle
  if (typeof s.unicodeHighlight === "boolean") {
    unicodeHighlightEnabled.value = s.unicodeHighlight
    if (!s.unicodeHighlight && monacoRaw) applyUnicodeHighlights(editor, monacoRaw)
  }
  // Long Lines toggle
  if (typeof s.longLines === "boolean") {
    longLinesEnabled.value = s.longLines
    if (monacoRaw) applyLongLinesIndicator(editor, monacoRaw)
  }
  // Linked Editing toggle
  if (typeof s.linkedEditing === "boolean") {
    linkedEditingEnabled.value = s.linkedEditing
    if (!s.linkedEditing) linkedEditing.deactivate(editor)
  }
  // InlayHints toggle (Session 47: Monaco 选项 + composable 同步)
  if (typeof s.inlayHints === "boolean") {
    showInlayHints.value = s.inlayHints
    if (!s.inlayHints) inlayHints.clearDecorations(editor)
  }
  // Format on Save toggle (Session 47)
  if (typeof s.formatOnSave === "boolean") {
    formatOnSaveEnabled.value = s.formatOnSave
  }
  // Format on Paste toggle (Session 47)
  if (typeof s.formatOnPaste === "boolean") {
    formatOnPasteEnabled.value = s.formatOnPaste
  }
  // Font size
  if (typeof s.fontSize === "number") {
    fontSizeLevel = s.fontSize
  }
  // Smooth Scrolling
  if (typeof s.smoothScrolling === "boolean") {
    editor.updateOptions({ smoothScrolling: s.smoothScrolling })
  }
  // Middle Scroll (中键粘贴切换)
  if (typeof s.middleScroll === "boolean") {
    // 保存到 localStorage 供 mousedown 处理读取
  }
}

onMounted(async () => {
  await initMonaco()
    // 初始化后应用持久化设置 + 编辑器智能
    nextTick(() => {
      applyEditorSettings()
      editorIntel.init(monacoRaw)
      // Session 58: 注册到同步滚动管理器
      if (editorInstance.value) {
        const ed = editorInstance.value
        registerSyncScrollEditor({
          id: props.activeTab.id,
          getScrollTop: () => ed.getScrollTop(),
          setScrollTop: (top: number) => ed.setScrollTop(top),
          onScroll: (cb: () => void) => ed.onDidScrollChange(cb).dispose,
        })
      }
      // Session 43: 初始 InlayHints
      if (showInlayHints.value && editorInstance.value && monacoRaw) {
        setTimeout(() => {
          if (editorInstance.value && monacoRaw) {
            inlayHints.refreshHints(editorInstance.value, monacoRaw, props.activeTab.language ?? "plaintext")
          }
        }, 600)
      }
      // Session 45: 初始 Error Lens 扫描
      if (showErrorLens.value && editorInstance.value) {
        setTimeout(() => {
          const editor = editorInstance.value
          if (editor) {
            errorLens.applyFromScan(
              editor.getValue(),
              props.activeTab.language ?? "plaintext",
              props.activeTab.filePath,
            )
          }
        }, 700)
      }
    })
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
  hideLightbulb()
  inlineDebug.hide()
  clearRenameHighlights()
  editorIntel.dispose()
  if (quickDiffWatcher) clearTimeout(quickDiffWatcher)
  if (inlayHintsTimer) clearTimeout(inlayHintsTimer)
  if (errorLensTimer) clearTimeout(errorLensTimer)
  if (quickDiffIds.length > 0 && editorInstance.value) {
    editorInstance.value.deltaDecorations(quickDiffIds, [])
    quickDiffIds = []
  }
  if (editorInstance.value) {
    inlayHints.clearDecorations(editorInstance.value)
  }
  // Session 45: 清理 Emmet providers
  for (const d of emmetDisposables) { try { d.dispose() } catch { /* ignore */ } }
  emmetDisposables = []
  // Session 45: 清理 Error Lens
  errorLens.clear(editorInstance.value)
  // Session 46: 清理新系统
  linkedEditing.deactivate(editorInstance.value!)
  wordHighlighter.clear(editorInstance.value)
  smartSelect.resetStack()
  if (unicodeHighlightIds.length > 0 && editorInstance.value) {
    editorInstance.value.deltaDecorations(unicodeHighlightIds, [])
    unicodeHighlightIds = []
  }
  cursorUndoStack = []
  cursorUndoIndex = -1
  /** Session 53: 清理 LSP 特性 */
  semanticTokens.clearSemanticTokens()
  codeLens.clearCodeLens()
  folding.unregisterFoldingProvider()
  /** Session 58: 取消注册同步滚动 */
  unregisterSyncScrollEditor(props.activeTab.id)
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
  <!-- Session 36: Go To Symbol 符号导航弹窗 (Ctrl+Shift+O) -->
  <GoToSymbol
    :visible="showGoToSymbol"
    @close="showGoToSymbol = false"
    @go-to="onGoToSymbol"
  />
  <!-- Session 37: Code Actions 灯泡菜单 (Ctrl+.) -->
  <CodeActionsMenu
    :visible="showCodeActions"
    :x="codeActionsX"
    :y="codeActionsY"
    :actions="codeActions"
    :diagnostic-message="codeActionsMsg"
    @close="showCodeActions = false"
    @action="onCodeAction"
  />
  <!-- Session 38: F2 重命名符号内联输入 -->
  <RenameInput
    :visible="showRenameInput"
    :x="renameX"
    :y="renameY"
    :symbol-name="renameSymbolName"
    :occurrences-count="renameOccurrencesCount"
    @confirm="onRenameConfirm"
    @cancel="onRenameCancel"
    @update-preview="onRenameUpdatePreview"
  />
  <!-- VSCode 风格内联查找/替换 Widget (Ctrl+F/Ctrl+H) -->
  <FindWidget
    :visible="showFindWidget"
    :mode="findWidgetMode"
    :editor-content="editorInstance?.getValue() ?? ''"
    @close="onFindClose"
    @navigate="onFindNavigateTo"
  />

  <!-- Session 42: Inline Chat (Ctrl+I 编辑器内嵌 AI 对话) -->
  <InlineChatWidget
    :visible="showInlineChat"
    :editor-container="containerRef"
    :line-number="inlineChatLine"
    :language="activeTab.language ?? 'plaintext'"
    :context-code="inlineChatContext"
    @close="showInlineChat = false"
    @submit="showInlineChat = false"
  />
</template>

<style>
/* ═══ 编辑器 Git 行标记 + Gutter 颜色（全局 CSS 变量，穿透 Shadow DOM） ═══ */
:root {
  --editor-glyph-deleted: #f85149;
  --editor-modified-line-bg: rgba(210, 153, 34, 0.08);
  --editor-modified-line-border: rgba(210, 153, 34, 0.4);
  --editor-added-line-bg: rgba(46, 160, 67, 0.08);
  --editor-added-line-border: rgba(46, 160, 67, 0.4);
  --editor-deleted-line-bg: rgba(248, 81, 73, 0.08);
  --editor-deleted-line-border: rgba(248, 81, 73, 0.4);
}
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
  background: var(--editor-glyph-deleted) !important;
  width: 3px !important;
  margin-left: 3px;
  border-radius: 1px;
}
/* 行背景标记 */
.qd-modified-line { background: var(--editor-modified-line-bg) !important; border-left: 2px solid var(--editor-modified-line-border) !important; }
.qd-added-line { background: var(--editor-added-line-bg) !important; border-left: 2px solid var(--editor-added-line-border) !important; }
.qd-deleted-line { background: var(--editor-deleted-line-bg) !important; border-left: 2px solid var(--editor-deleted-line-border) !important; text-decoration: line-through; opacity: 0.5; }

/* ═══ Session 37: Code Actions 灯泡 glyph margin 图标 ═══ */
.code-actions-lightbulb {
  background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%23ffcc00' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5'/%3E%3Cpath d='M9 18h6'/%3E%3Cpath d='M10 22h4'/%3E%3C/svg%3E") center center / 14px 14px no-repeat !important;
  width: 16px !important;
  height: 16px !important;
  margin-left: 2px;
  cursor: pointer;
  opacity: 0.85;
  transition: opacity 0.1s;
}
.code-actions-lightbulb:hover {
  opacity: 1;
  filter: drop-shadow(0 0 3px rgba(255, 204, 0, 0.6));
}

/* ═══ Session 37: Inline 调试变量显示 ═══ */
.inline-debug-value {
  font-size: 11px;
  font-style: italic;
  color: var(--color-ide-text-dim, #858585);
  background: rgba(117, 190, 255, 0.08);
  border-radius: 3px;
  padding: 1px 4px;
  margin-left: 4px;
  white-space: nowrap;
  pointer-events: none;
  user-select: none;
}

/* ═══ Session 38: F2 重命名高亮 ═══ */
.rename-highlight {
  background: var(--editor-rename-highlight-bg, rgba(255, 140, 0, 0.15)) !important;
  border-bottom: 2px solid var(--editor-rename-highlight-border, rgba(255, 140, 0, 0.6)) !important;
}
.rename-highlight-text {
  color: var(--color-ide-text, #cccccc) !important;
}

/* ═══ Session 43: InlayHints 内嵌类型标注样式 ═══ */
.ide-inlay-hint {
  color: var(--color-ide-text-dim, #858585) !important;
  font-size: 11px;
  font-style: italic;
  opacity: 0.7;
  pointer-events: auto;
  cursor: default;
  user-select: none;
}
.ide-inlay-hint-type {
  color: var(--color-ide-text-dim, #6e7681) !important;
  font-size: 10px;
  font-style: italic;
  opacity: 0.6;
}

/* ═══ Session 45: Error Lens 行内诊断样式 ═══ */
.error-lens-error {
  color: #f85149 !important;
  font-size: 11px;
  font-style: italic;
  opacity: 0.85;
  background: rgba(248, 81, 73, 0.08);
  border-radius: 3px;
  padding: 1px 4px;
  margin-left: 6px;
  user-select: none;
  white-space: nowrap;
}
.error-lens-warning {
  color: #d29922 !important;
  font-size: 11px;
  font-style: italic;
  opacity: 0.85;
  background: rgba(210, 153, 34, 0.08);
  border-radius: 3px;
  padding: 1px 4px;
  margin-left: 6px;
  user-select: none;
  white-space: nowrap;
}
.error-lens-info {
  color: #61AFEF !important;
  font-size: 11px;
  font-style: italic;
  opacity: 0.75;
  background: rgba(97, 174, 239, 0.08);
  border-radius: 3px;
  padding: 1px 4px;
  margin-left: 6px;
  user-select: none;
  white-space: nowrap;
}

/* ═══ Session 46: Word Highlighter 单词出现位置高亮 ═══ */
.word-highlight-match {
  background: rgba(192, 193, 255, 0.12) !important;
  border-bottom: 1px solid rgba(192, 193, 255, 0.3) !important;
}
.word-highlight-match-text {
  color: var(--color-ide-text, #cccccc) !important;
}

/* ═══ Session 46: Linked Editing 标签对高亮 ═══ */
.linked-editing-highlight {
  background: rgba(97, 174, 239, 0.12) !important;
  border: 1px dashed rgba(97, 174, 239, 0.5) !important;
  border-radius: 2px;
}
.linked-editing-text {
  color: #61AFEF !important;
  font-weight: 600;
}

/* ═══ Session 46: Unicode Highlighter 可疑字符标注 ═══ */
.unicode-highlight-suspicious {
  background: rgba(210, 153, 34, 0.2) !important;
  border-bottom: 2px wavy #d29922 !important;
}
.unicode-highlight-suspicious-text {
  color: #d29922 !important;
  font-weight: bold;
}
.unicode-highlight-confusable {
  background: rgba(97, 174, 239, 0.15) !important;
  border-bottom: 1px dotted #61AFEF !important;
}
.unicode-highlight-confusable-text {
  color: #61AFEF !important;
  font-weight: bold;
}

/* ═══ Session 46: Smart Select 扩展选区动画 ═══ */
.monaco-editor .smart-select-flash {
  animation: smart-select-flash 300ms ease-out;
}
@keyframes smart-select-flash {
  0% { background: rgba(192, 193, 255, 0.2); }
  100% { background: transparent; }
}

/* ═══ Session 53: Semantic Tokens 语义高亮样式 ═══ */
.semantic-token { }
.semantic-namespace { color: var(--semantic-namespace, #b0b0b0) !important; }
.semantic-type { color: var(--semantic-type, #4EC9B0) !important; }
.semantic-class { color: var(--semantic-class, #4EC9B0) !important; }
.semantic-enum { color: var(--semantic-enum, #4EC9B0) !important; }
.semantic-interface { color: var(--semantic-interface, #4EC9B0) !important; }
.semantic-struct { color: var(--semantic-struct, #4EC9B0) !important; }
.semantic-type-param { color: var(--semantic-type-param, #4EC9B0) !important; }
.semantic-parameter { color: var(--semantic-parameter, #9CDCFE) !important; }
.semantic-variable { color: var(--semantic-variable, #9CDCFE) !important; }
.semantic-property { color: var(--semantic-property, #9CDCFE) !important; }
.semantic-enum-member { color: var(--semantic-enum-member, #4FC1FF) !important; }
.semantic-event { color: var(--semantic-event, #4FC1FF) !important; }
.semantic-function { color: var(--semantic-function, #DCDCAA) !important; }
.semantic-method { color: var(--semantic-method, #DCDCAA) !important; }
.semantic-macro { color: var(--semantic-macro, #DCDCAA) !important; }
.semantic-keyword { color: var(--semantic-keyword, #C586C0) !important; }
.semantic-modifier { color: var(--semantic-modifier, #C586C0) !important; }
.semantic-comment { color: var(--semantic-comment, #6A9955) !important; }
.semantic-string { color: var(--semantic-string, #CE9178) !important; }
.semantic-number { color: var(--semantic-number, #B5CEA8) !important; }
.semantic-regexp { color: var(--semantic-regexp, #D16969) !important; }
.semantic-operator { color: var(--semantic-operator, #D4D4D4) !important; }
.semantic-decorator { color: var(--semantic-decorator, #DCDCAA) !important; }

/* ═══ Session 53: CodeLens 代码透镜样式 ═══ */
.code-lens-hint {
  color: var(--code-lens, #999999) !important;
  font-size: 0.88em !important;
  font-style: italic !important;
  opacity: 0.75 !important;
}
</style>
