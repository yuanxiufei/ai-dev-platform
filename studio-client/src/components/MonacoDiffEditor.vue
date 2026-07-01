<script setup lang="ts">
/**
 * MonacoDiffEditor.vue — Monaco 原生 DiffEditor 集成
 *
 * 借鉴: Monaco Editor 08-MonacoEditor.md + Zed streaming_diff
 * 
 * 能力:
 *   - Monaco createDiffEditor() 原生渲染 (200+语言语法高亮)
 *   - unified/split 双模式 (renderSideBySince)
 *   - 逐 hunk Accept/Reject (通过 decorations API)
 *   - AI 标注装饰 (deltaDecorations)
 *   - Minimap + IntelliSense
 *   - 键盘快捷键 (Alt+A Accept, Alt+R Reject, F3/Shift+F3 hunk导航)
 */
import type * as monacoNs from "monaco-editor"
import {
  AlignLeft,
  ArrowDown,
  ArrowUp,
  Check,
  ChevronDown,
  ChevronRight,
  Columns,
  Copy,
  Download,
  FileEdit,
  FileMinus,
  FilePlus,
  Minus,
  Plus,
  RotateCcw,
  X,
} from "lucide-vue-next"
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue"
import type { DiffData } from "@/types/studio"
import "monaco-editor/dev/vs/editor/editor.main.css"

const props = defineProps<{
  diff: DiffData | null
  collapsible?: boolean
  activeHunkIndex?: number
}>()

const emit = defineEmits<{
  (e: "close"): void
  (e: "apply"): void
  (e: "jumpToHunk", index: number): void
  (e: "acceptHunk", index: number): void
  (e: "rejectHunk", index: number): void
  (e: "acceptAll"): void
  (e: "rejectAll"): void
}>()

// ── 状态 ──
type ViewMode = "unified" | "split"
const viewMode = ref<ViewMode>("split")
const collapsed = ref(false)
const containerRef = ref<HTMLElement | null>(null)
const diffEditorInstance = shallowRef<monacoNs.editor.IStandaloneDiffEditor | null>(null)
let monacoInstance: typeof monacoNs | null = null

// Hunk 状态
const hunkStates = ref<("pending" | "accepted" | "rejected")[]>([])
const activeHunk = ref(props.activeHunkIndex ?? -1)
const totalHunks = ref(0)

// ── 语言映射 ──
const LANG_MAP: Record<string, string> = {
  py: "python", js: "javascript", ts: "typescript", tsx: "typescript",
  vue: "html", css: "css", scss: "scss", less: "less",
  html: "html", htm: "html", json: "json", yaml: "yaml", yml: "yaml",
  md: "markdown", mdx: "markdown", sql: "sql", sh: "shell", bash: "shell",
  go: "go", rs: "rust", java: "java", cpp: "cpp", c: "c", h: "c",
  kt: "kotlin", swift: "swift", rb: "ruby", php: "php",
  dart: "dart", gql: "graphql", graphql: "graphql",
  xml: "xml", toml: "toml", ini: "ini", cfg: "ini",
  dockerfile: "dockerfile", makefile: "makefile",
}
function resolveLanguage(): string {
  if (props.diff?.language) {
    return LANG_MAP[props.diff.language] || props.diff.language || "plaintext"
  }
  if (props.diff?.file_name) {
    const ext = props.diff.file_name.split(".").pop()?.toLowerCase() || ""
    return LANG_MAP[ext] || "plaintext"
  }
  return "plaintext"
}

// ── 变更统计 ──
const changeIcon = computed(() => {
  if (!props.diff) return FileEdit
  switch (props.diff.change_type) {
    case "CREATE": return FilePlus
    case "DELETE": return FileMinus
    default: return FileEdit
  }
})
const changeLabel = computed(() => {
  if (!props.diff) return "修改"
  switch (props.diff.change_type) {
    case "CREATE": return "新建"
    case "DELETE": return "删除"
    default: return "修改"
  }
})
const changeColor = computed(() => {
  if (!props.diff) return "text-blue-400"
  switch (props.diff.change_type) {
    case "CREATE": return "text-emerald-400"
    case "DELETE": return "text-red-400"
    default: return "text-amber-400"
  }
})
const changeBg = computed(() => {
  if (!props.diff) return "bg-blue-500/8 border-blue-500/15"
  switch (props.diff.change_type) {
    case "CREATE": return "bg-emerald-500/8 border-emerald-500/15"
    case "DELETE": return "bg-red-500/8 border-red-500/15"
    default: return "bg-amber-500/8 border-amber-500/15"
  }
})

// ── Diff 内容来源 ──
const originalText = computed(() => props.diff?.content_before ?? "")
const modifiedText = computed(() => props.diff?.content_after ?? "")

function copyDiff() {
  if (!props.diff) return
  navigator.clipboard.writeText(props.diff.diff_text)
}
function downloadDiff() {
  if (!props.diff) return
  const blob = new Blob([props.diff.diff_text], { type: "text/plain" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url; a.download = `${props.diff.file_name}.diff`; a.click()
  URL.revokeObjectURL(url)
}

// ── Hunk 状态管理 ──
function refreshHunkStates() {
  const de = diffEditorInstance.value
  if (!de) return
  const changes = de.getLineChanges()
  totalHunks.value = changes?.length || 0
  if (hunkStates.value.length !== totalHunks.value) {
    hunkStates.value = Array.from({ length: totalHunks.value }, () => "pending")
  }
}

function acceptHunk(index: number) {
  if (index < 0 || index >= hunkStates.value.length) return
  hunkStates.value[index] = "accepted"
  applyHunkDecoration(index, "accepted")
  emit("acceptHunk", index)
}
function rejectHunk(index: number) {
  if (index < 0 || index >= hunkStates.value.length) return
  hunkStates.value[index] = "rejected"
  applyHunkDecoration(index, "rejected")
  emit("rejectHunk", index)
}
function acceptAllHunks() {
  hunkStates.value = hunkStates.value.map(() => "accepted")
  refreshDecorations()
  emit("acceptAll")
}
function rejectAllHunks() {
  hunkStates.value = hunkStates.value.map(() => "rejected")
  refreshDecorations()
  emit("rejectAll")
}
function resetAllHunks() {
  hunkStates.value = hunkStates.value.map(() => "pending")
  refreshDecorations()
}

// Monaco decorations for hunk accept/reject
let hunkDecorationIds: string[] = []
function applyHunkDecoration(hunkIndex: number, state: "accepted" | "rejected") {
  const de = diffEditorInstance.value
  if (!de || !monacoInstance) return
  const changes = de.getLineChanges()
  if (!changes || hunkIndex >= changes.length) return
  
  const modified = de.getModifiedEditor()
  const change = changes[hunkIndex]
  const cls = state === "accepted" ? "ai-diff-accepted" : "ai-diff-rejected"
  
  const decos = modified.deltaDecorations(hunkDecorationIds, [{
    range: new monacoInstance.Range(
      change.modifiedStartLineNumber, 1,
      change.modifiedEndLineNumber, 1,
    ),
    options: {
      isWholeLine: true,
      className: cls,
      glyphMarginClassName: state === "accepted" ? "ai-glyph-accept" : "ai-glyph-reject",
    },
  }])
  if (state === "accepted" || state === "rejected") {
    hunkDecorationIds = decos
  }
}
function refreshDecorations() {
  const de = diffEditorInstance.value
  if (!de || !monacoInstance) return
  const modified = de.getModifiedEditor()
  modified.deltaDecorations(hunkDecorationIds, [])
  hunkDecorationIds = []
  
  const changes = de.getLineChanges()
  if (!changes) return
  const newDecos: monacoNs.editor.IModelDeltaDecoration[] = []
  hunkStates.value.forEach((state, i) => {
    if (i >= changes.length) return
    const c = changes[i]
    const cls = state === "accepted" ? "ai-diff-accepted" : state === "rejected" ? "ai-diff-rejected" : ""
    if (!cls) return
    newDecos.push({
      range: new monacoInstance!.Range(c.modifiedStartLineNumber, 1, c.modifiedEndLineNumber, 1),
      options: { isWholeLine: true, className: cls },
    })
  })
  hunkDecorationIds = modified.deltaDecorations([], newDecos)
}

function jumpToPrevHunk() {
  if (totalHunks.value === 0) return
  if (activeHunk.value <= 0) activeHunk.value = totalHunks.value - 1
  else activeHunk.value--
  emit("jumpToHunk", activeHunk.value)
}
function jumpToNextHunk() {
  if (totalHunks.value === 0) return
  if (activeHunk.value >= totalHunks.value - 1) activeHunk.value = 0
  else activeHunk.value++
  emit("jumpToHunk", activeHunk.value)
}

// ── Monaco DiffEditor 初始化 ──
async function initDiffEditor() {
  if (!containerRef.value) return
  try {
    const monaco = (await import("monaco-editor")).default
    monacoInstance = monaco
    
    // 注册主题（如果还没注册）
    try {
      monaco.editor.defineTheme("codebuddy-dark", {
        base: "vs-dark", inherit: true,
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
        ],
        colors: {
          "editor.background": "#0F131D", "editor.foreground": "#DFE2F1",
          "editor.lineHighlightBackground": "#1C1F2A20",
          "editorLineNumber.foreground": "#4B5563",
          "editorLineNumber.activeForeground": "#C0C1FF",
          "editor.selectionBackground": "#C0C1FF30",
          "editor.inactiveSelectionBackground": "#C0C1FF15",
          "editorCursor.foreground": "#C0C1FF",
          "editorIndentGuide.background": "#46455440",
          "editorIndentGuide.activeBackground": "#46455480",
          "diffEditor.insertedTextBackground": "#2ea04326",
          "diffEditor.removedTextBackground": "#f8514926",
          "diffEditor.insertedLineBackground": "#2ea04315",
          "diffEditor.removedLineBackground": "#f8514915",
        },
      })
    } catch (_) { /* theme already registered */ }
    
    const lang = resolveLanguage()
    const originalModel = monaco.editor.createModel(originalText.value, lang)
    const modifiedModel = monaco.editor.createModel(modifiedText.value, lang)
    
    const diffEditor = monaco.editor.createDiffEditor(containerRef.value, {
      automaticLayout: true,
      fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace",
      fontLigatures: true,
      lineHeight: 21,
      renderSideBySide: viewMode.value === "split",
      enableSplitViewResizing: true,
      ignoreTrimWhitespace: false,
      renderOverviewRuler: true,
      diffAlgorithm: "advanced",
      minimap: { enabled: true, maxColumn: 120, scale: 1 },
      scrollBeyondLastLine: false,
      smoothScrolling: true,
      readOnly: false,
      originalEditable: false,
      theme: "codebuddy-dark",
      padding: { top: 8, bottom: 8 },
      renderLineHighlight: "gutter",
      guides: { indentation: true, bracketPairs: true },
      wordWrap: "on",
      folding: true,
      lineNumbers: "on",
    })
    diffEditor.setModel({ original: originalModel, modified: modifiedModel })
    diffEditorInstance.value = diffEditor
    
    // 键盘快捷键
    diffEditor.getModifiedEditor().addAction({
      id: "accept-hunk", label: "Accept Hunk",
      keybindings: [monaco.KeyMod.Alt | monaco.KeyCode.KeyA],
      run: () => { if (activeHunk.value >= 0) acceptHunk(activeHunk.value) },
    })
    diffEditor.getModifiedEditor().addAction({
      id: "reject-hunk", label: "Reject Hunk",
      keybindings: [monaco.KeyMod.Alt | monaco.KeyCode.KeyR],
      run: () => { if (activeHunk.value >= 0) rejectHunk(activeHunk.value) },
    })
    
    refreshHunkStates()
  } catch (err) {
    console.warn("[MonacoDiffEditor] init error:", err)
  }
}

// ── View mode 切换 ──
watch(viewMode, (mode) => {
  const de = diffEditorInstance.value
  if (de) {
    de.updateOptions({ renderSideBySide: mode === "split" })
  }
})

// ── 外部内容变化 ──
watch([originalText, modifiedText], async ([orig, mod]) => {
  const de = diffEditorInstance.value
  if (!de || !monacoInstance) return
  const lang = resolveLanguage()
  de.setModel({
    original: monacoInstance.editor.createModel(orig, lang),
    modified: monacoInstance.editor.createModel(mod, lang),
  })
  await nextTick()
  refreshHunkStates()
})

// ── 生命周期 ──
onMounted(async () => {
  await nextTick()
  await initDiffEditor()
})
onBeforeUnmount(() => {
  diffEditorInstance.value?.dispose()
  diffEditorInstance.value = null
})
</script>

<template>
  <div
    v-if="diff"
    :class="['rounded-xl border overflow-hidden transition-all duration-200', changeBg]"
  >
    <!-- ── 头部 ── -->
    <div class="flex items-center justify-between px-4 py-2.5 bg-white/[0.03] border-b border-white/5">
      <div class="flex items-center gap-2.5 min-w-0">
        <button
          v-if="collapsible"
          @click="collapsed = !collapsed"
          class="p-1 rounded-md hover:bg-white/5 text-gray-500 hover:text-gray-300 shrink-0"
        >
          <ChevronDown v-if="!collapsed" class="w-3.5 h-3.5" />
          <ChevronRight v-else class="w-3.5 h-3.5" />
        </button>
        <component :is="changeIcon" :class="['w-4 h-4 shrink-0', changeColor]" />
        <span class="text-sm font-mono font-medium text-gray-200 truncate">
          {{ diff.file_name }}
        </span>
        <span :class="['text-[11px] font-semibold px-1.5 py-0.5 rounded', changeColor, changeBg]">
          {{ changeLabel }}
        </span>
        <span class="text-[11px] text-gray-500 font-mono ml-1 flex items-center gap-0.5">
          <img src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24'%3E%3Ccircle cx='12' cy='12' r='10' fill='%23f05138'/%3E%3Ctext x='12' y='17' text-anchor='middle' fill='white' font-size='12' font-weight='bold'%3EM%3C/text%3E%3C/svg%3E" class="w-3 h-3" alt="" />
          Monaco
        </span>
      </div>
      <div class="flex items-center gap-3 text-[11px] font-mono">
        <span v-if="diff.lines_added" class="text-emerald-400 flex items-center gap-0.5">
          <Plus class="w-3 h-3" /> {{ diff.lines_added }}
        </span>
        <span v-if="diff.lines_removed" class="text-red-400 flex items-center gap-0.5">
          <Minus class="w-3 h-3" /> {{ diff.lines_removed }}
        </span>
      </div>
    </div>

    <!-- ── 工具栏 ── -->
    <div v-if="!collapsed" class="flex items-center gap-1 px-4 py-1.5 bg-white/[0.02] border-b border-white/5">
      <button
        @click="viewMode = 'unified'"
        :class="['p-1.5 rounded-md text-[11px] transition-colors', viewMode === 'unified' ? 'bg-white/10 text-gray-200' : 'text-gray-500 hover:text-gray-300']"
        title="统一视图"
      >
        <AlignLeft class="w-3.5 h-3.5" />
      </button>
      <button
        @click="viewMode = 'split'"
        :class="['p-1.5 rounded-md text-[11px] transition-colors', viewMode === 'split' ? 'bg-white/10 text-gray-200' : 'text-gray-500 hover:text-gray-300']"
        title="双栏视图"
      >
        <Columns class="w-3.5 h-3.5" />
      </button>
      <div class="w-px h-4 bg-white/5 mx-1" />

      <button @click="jumpToPrevHunk" :disabled="totalHunks === 0"
        class="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="上一个变更 (Shift+F3)">
        <ArrowUp class="w-3.5 h-3.5" />
      </button>
      <span class="text-[10px] text-gray-500 font-mono min-w-[36px] text-center select-none">
        {{ activeHunk >= 0 ? `${activeHunk + 1}/${totalHunks}` : `${totalHunks}` }}
      </span>
      <button @click="jumpToNextHunk" :disabled="totalHunks === 0"
        class="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="下一个变更 (F3)">
        <ArrowDown class="w-3.5 h-3.5" />
      </button>

      <!-- Hunk 快速跳转圆点 -->
      <div v-if="totalHunks > 1" class="flex items-center gap-1 mx-1">
        <button v-for="h in totalHunks" :key="h"
          @click="activeHunk = h - 1; emit('jumpToHunk', h - 1)"
          :class="['w-3 h-3 rounded-full transition-all duration-200',
            hunkStates[h - 1] === 'accepted' ? 'bg-emerald-500' :
            hunkStates[h - 1] === 'rejected' ? 'bg-red-500' :
            activeHunk === h - 1 ? 'bg-brand-400 scale-110 shadow-sm shadow-brand-500/30'
            : 'bg-white/[0.06] hover:bg-white/[0.12]']"
          :title="`变更 ${h}`" />
      </div>

      <div class="w-px h-4 bg-white/5 mx-1" />

      <!-- Hunk Accept/Reject 按钮 -->
      <button @click="acceptHunk(activeHunk)" :disabled="activeHunk < 0"
        class="p-1 rounded-md text-emerald-500 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed ml-1"
        title="接受当前变更 (Alt+A)">
        <Check class="w-3.5 h-3.5" />
      </button>
      <button @click="rejectHunk(activeHunk)" :disabled="activeHunk < 0"
        class="p-1 rounded-md text-red-500 hover:text-red-400 hover:bg-red-500/10 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        title="拒绝当前变更 (Alt+R)">
        <X class="w-3.5 h-3.5" />
      </button>
      <div class="w-px h-4 bg-white/5 mx-1" />
      <button @click="acceptAllHunks"
        class="px-2 py-1 text-[10px] rounded text-emerald-500 hover:bg-emerald-500/10 transition-colors font-medium"
        title="接受全部">
        Accept All
      </button>
      <button @click="rejectAllHunks"
        class="px-2 py-1 text-[10px] rounded text-red-500 hover:bg-red-500/10 transition-colors font-medium"
        title="拒绝全部">
        Reject All
      </button>

      <div class="flex-1" />

      <button @click="copyDiff"
        class="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors" title="复制 diff">
        <Copy class="w-3.5 h-3.5" />
      </button>
      <button @click="downloadDiff"
        class="p-1.5 rounded-md text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors" title="下载 .diff">
        <Download class="w-3.5 h-3.5" />
      </button>
    </div>

    <!-- ── Monaco Diff Editor ── -->
    <div v-if="!collapsed" ref="containerRef" class="w-full" :style="{ minHeight: '320px', maxHeight: '600px' }" />

    <!-- ── 折叠时 ── -->
    <div v-if="collapsed" class="px-4 py-2 text-xs text-gray-500">
      +{{ diff.lines_added }} -{{ diff.lines_removed }} {{ diff.lines_added + diff.lines_removed }} 行变更
    </div>
  </div>
</template>

<style scoped>
/* AI diff accept/reject decorations */
:deep(.ai-diff-accepted) {
  background: linear-gradient(90deg, rgba(46, 160, 67, 0.12) 0%, transparent 100%) !important;
  border-left: 3px solid #2ea043 !important;
}
:deep(.ai-diff-rejected) {
  background: linear-gradient(90deg, rgba(248, 81, 73, 0.08) 0%, transparent 100%) !important;
  border-left: 3px solid #f85149 !important;
  opacity: 0.55;
}
:deep(.ai-glyph-accept) {
  background: #2ea043;
  width: 6px !important;
  margin-left: 3px;
}
:deep(.ai-glyph-reject) {
  background: #f85149;
  width: 6px !important;
  margin-left: 3px;
}
</style>
