<script setup lang="ts">
/** CodeBuddy IDE — Code Editor (Monaco Editor Wrapper) */

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
let monacoInstance: typeof monacoNs | null = null

async function initMonaco(): Promise<void> {
  if (!containerRef.value) return
  try {
    const monaco = (await import("monaco-editor")).default
    monacoInstance = monaco
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
      },
    })
    const editor = monaco.editor.create(containerRef.value, {
      value: props.activeTab.content,
      language: props.activeTab.language ?? "plaintext",
      theme: "codebuddy-dark",
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
      guides: { indentation: true, bracketPairs: true },
      wordWrap: "on",
      folding: true,
      lineNumbers: "on",
      links: true,
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
    editor.focus()
  } catch (err) {
    console.warn("[CodeBuddy] Monaco init error:", err)
  }
}

watch(
  () => [props.activeTab.id, props.activeTab.language],
  async ([newId], [oldId]) => {
    if (!monacoInstance) return
    if (newId !== oldId) {
      editorInstance.value?.dispose()
      editorInstance.value = null
      await nextTick()
      if (!editorInstance.value) {
        const m = editorInstance.value
        monacoInstance!.editor.setModelLanguage(
          m!.getModel()!,
          props.activeTab.language ?? "plaintext",
        )
        editorInstance.value?.setValue(props.activeTab.content)
      } else await initMonaco()
    } else if (editorInstance.value) {
      const _m = editorInstance.value.getValue()
      monacoInstance!.editor.setModelLanguage(
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
onBeforeUnmount(() => {
  editorInstance.value?.dispose()
  editorInstance.value = null
})
</script>

<template><div ref="containerRef" class="absolute inset-0 w-full h-full" /></template>
