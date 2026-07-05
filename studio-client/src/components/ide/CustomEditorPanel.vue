<script setup lang="ts">
/**
 * CustomEditorPanel — VSCode Custom Editors 支持
 * Session 42: 对标 VSCode customEditor API，支持 webview/binary 编辑器
 */
import { ref, computed } from "vue"
import { FileCode, Image, FileType, Play, ExternalLink, X } from "lucide-vue-next"

interface CustomEditor {
  id: string
  name: string
  selector: string
  type: "webview" | "binary" | "text"
  provider: string
  enabled: boolean
}
const editors = ref<CustomEditor[]>([
  { id: "image-preview", name: "图片预览", selector: "*.png,*.jpg,*.gif,*.svg,*.webp", type: "webview", provider: "builtin", enabled: true },
  { id: "pdf-preview", name: "PDF 预览", selector: "*.pdf", type: "webview", provider: "builtin", enabled: true },
  { id: "markdown-preview", name: "Markdown 预览", selector: "*.md", type: "webview", provider: "builtin", enabled: true },
  { id: "csv-preview", name: "CSV 数据表格", selector: "*.csv,*.tsv", type: "webview", provider: "builtin", enabled: true },
  { id: "svg-editor", name: "SVG 编辑器", selector: "*.svg", type: "binary", provider: "builtin", enabled: false },
  { id: "hex-editor", name: "Hex 编辑器", selector: "*.bin,*.dat", type: "binary", provider: "builtin", enabled: false },
])
const activePreview = ref<{ id: string; name: string; url?: string } | null>(null)

function toggleEditor(id: string): void {
  const editor = editors.value.find(e => e.id === id)
  if (editor) editor.enabled = !editor.enabled
}
function previewEditor(editor: CustomEditor): void {
  activePreview.value = { id: editor.id, name: editor.name, url: undefined }
}
</script>

<template>
  <div class="h-full flex flex-col" style="background: var(--color-ide-bg); color: var(--color-ide-text);">
    <div class="flex items-center gap-2 px-3 h-10 shrink-0" style="border-bottom: 1px solid var(--color-ide-border);">
      <FileType :size="16" style="color: var(--color-ide-accent);" />
      <span class="text-[13px] font-semibold">自定义编辑器</span>
      <span class="text-[10px] opacity-50">({{ editors.length }})</span>
    </div>
    <div class="flex-1 overflow-y-auto">
      <div class="p-2 text-[11px]" style="color: var(--color-ide-text-dim);">
        为特定文件类型配置自定义编辑器。支持 webview 预览和二进制编辑。
      </div>
      <div v-for="editor in editors" :key="editor.id" class="flex items-center gap-3 px-3 py-2.5 border-b"
        :style="{ borderColor: 'var(--color-ide-border)', opacity: editor.enabled ? 1 : 0.5 }">
        <div class="w-7 h-7 rounded-md flex items-center justify-center shrink-0"
          :style="{ background: 'var(--color-ide-surface-active)' }">
          <component :is="editor.type === 'webview' ? Image : FileCode" :size="13" style="color: var(--color-ide-accent);" />
        </div>
        <div class="flex-1 min-w-0">
          <div class="text-[12px] font-medium" style="color: var(--color-ide-text);">{{ editor.name }}</div>
          <div class="text-[10px] font-mono mt-0.5" style="color: var(--color-ide-text-dim);">{{ editor.selector }}</div>
        </div>
        <span class="text-[10px] px-1.5 py-0.5 rounded-[2px]"
          :style="{ background: 'var(--color-ide-surface-active)', color: 'var(--color-ide-text-dim)' }">
          {{ editor.type }}
        </span>
        <button class="px-2 py-1 rounded-[3px] text-[10px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
          style="color: var(--color-ide-text-dim);"
          @click="toggleEditor(editor.id)">
          {{ editor.enabled ? '禁用' : '启用' }}
        </button>
        <button class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)]"
          style="color: var(--color-ide-text-dim);" @click="previewEditor(editor)" title="预览">
          <Play :size="12" />
        </button>
      </div>
    </div>
    <!-- Preview Pane -->
    <div v-if="activePreview" class="h-48 shrink-0 border-t flex flex-col" style="border-color: var(--color-ide-border);">
      <div class="flex items-center justify-between px-3 py-1.5" style="background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border);">
        <span class="text-[11px] font-medium">{{ activePreview.name }} — 预览</span>
        <button @click="activePreview = null" class="text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]"><X :size="12" /></button>
      </div>
      <div class="flex-1 flex items-center justify-center text-[11px]" style="color: var(--color-ide-text-dim);">
        自定义编辑器预览区域。选择文件后在此显示。
      </div>
    </div>
  </div>
</template>
