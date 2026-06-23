<script setup lang="ts">
/** CodeBuddy IDE — Code Editor (Monaco Editor Wrapper) */
import { ref, watch, onMounted, onBeforeUnmount, nextTick, shallowRef } from 'vue'
import type * as monacoNs from 'monaco-editor'
import type { EditorTab } from '@/types/ide'
import 'monaco-editor/dev/vs/editor/editor.main.css'

const props = defineProps<{ activeTab: EditorTab }>()
const emit = defineEmits<{ (e: 'update-content', v: string): void; (e: 'update-cursor', v: any): void }>()

const containerRef = ref<HTMLElement | null>(null)
const editorInstance = shallowRef<monacoNs.editor.IStandaloneCodeEditor | null>(null)
let monacoInstance: typeof monacoNs | null = null

async function initMonaco(): Promise<void> {
  if (!containerRef.value) return
  try {
    const monaco = (await import('monaco-editor')).default; monacoInstance = monaco
    monaco.editor.defineTheme('codebuddy-dark', {
      base: 'vs-dark', inherit: true,
      rules: [
        { token: 'comment', foreground: '6c7086', fontStyle: 'italic' }, { token: 'keyword', foreground: 'cba6f7' },
        { token: 'string', foreground: 'a6e3a1' }, { token: 'number', foreground: 'fab387' },
        { token: 'type', foreground: '89b4fa' }, { token: 'function', foreground: 'f38ba8' },
        { token: 'variable', foreground: 'cdd6f4' }, { token: 'operator', foreground: '89dceb' },
      ],
      colors: {
        'editor.background': '#1e1e2e', 'editor.foreground': '#cdd6f4',
        'editor.lineHighlightBackground': '#2d2d4200', 'editorLineNumber.foreground': '#6c7086',
        'editorLineNumber.activeForeground': '#cdd6f4', 'editor.selectionBackground': '#45475a66',
        'editor.inactiveSelectionBackground': '#45475a33', 'editorCursor.foreground': '#f5e0dc',
        'editorIndentGuide.background': '#33334a', 'editorIndentGuide.activeBackground': '#45475a',
        'scrollbarSlider.background': '#45475a66', 'scrollbarSlider.hoverBackground': '#585b7066',
        'scrollbarSlider.activeBackground': '#6c708666',
      },
    })
    const editor = monaco.editor.create(containerRef.value, {
      value: props.activeTab.content, language: props.activeTab.language ?? 'plaintext', theme: 'codebuddy-dark',
      automaticLayout: true, fontSize: 13,
      fontFamily: "'JetBrains Mono', 'Cascadia Code', 'Fira Code', Consolas, monospace",
      fontLigatures: true, lineHeight: 21, padding: { top: 8, bottom: 8 },
      minimap: { enabled: true, maxColumn: 120, scale: 1 },
      scrollBeyondLastLine: false, smoothScrolling: true, cursorBlinking: 'smooth',
      cursorSmoothCaretAnimation: 'on', renderLineHighlight: 'gutter',
      guides: { indentation: true, bracketPairs: true },
      wordWrap: 'on', folding: true, lineNumbers: 'on', links: true,
    })
    editorInstance.value = editor
    editor.onDidChangeModelContent(() => emit('update-content', editor.getValue()))
    editor.onCursorPositionChanged(() => {
      const pos = editor.getPosition(), model = editor.getModel()
      emit('update-cursor', { line: pos?.lineNumber ?? 1, column: pos?.column ?? 1, totalLines: model?.getLineCount() ?? 1, selectedChars: editor.getSelection()?.toString().length ?? 0, languageId: model?.getLanguageId() ?? 'plaintext' })
    })
    editor.focus()
  } catch (err) { console.warn('[CodeBuddy] Monaco init error:', err) }
}

watch(() => [props.activeTab.id, props.activeTab.language], async ([newId], [oldId]) => {
  if (!monacoInstance) return
  if (newId !== oldId) {
    editorInstance.value?.dispose(); editorInstance.value = null
    await nextTick()
    if (!editorInstance.value) { const m = editorInstance.value; monacoInstance!.editor.setModelLanguage(m!.getModel()!, props.activeTab.language ?? 'plaintext'); editorInstance.value?.setValue(props.activeTab.content) }
    else await initMonaco()
  } else if (editorInstance.value) {
    const m = editorInstance.value.getValue(); monacoInstance!.editor.setModelLanguage(editorInstance.value.getModel()!, props.activeTab.language ?? 'plaintext')
  }
})
watch(() => props.activeTab.content, (nc) => { if (editorInstance.value && editorInstance.value.getValue() !== nc) { const s = editorInstance.value.getSelection(); editorInstance.value.setValue(nc); if (s) editorInstance.value.setSelection(s); } })

onMounted(async () => { await initMonaco() })
onBeforeUnmount(() => { editorInstance.value?.dispose(); editorInstance.value = null })
</script>

<template><div ref="containerRef" class="absolute inset-0 w-full h-full" /></template>
