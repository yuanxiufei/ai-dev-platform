<script setup lang="ts">
/** CodeBuddy IDE — Tab Bar (Figma design) */

import { FileCode, FileJson, FileText } from "lucide-vue-next"
import { computed, ref } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"
import type { EditorTab } from "@/types/ide"

const store = useIDEStore()
const draggedTabId = ref<string | null>(null)
const _visibleTabs = computed(() =>
  store.sortedTabs.filter((t) => t.id !== store.activeTabId),
)

function _onDragStart(e: DragEvent, id: string): void {
  draggedTabId.value = id
  e.dataTransfer?.setData("text/plain", id)
  e.dataTransfer!.effectAllowed = "move"
}
function _onDragOver(e: DragEvent): void {
  e.preventDefault()
  e.dataTransfer!.dropEffect = "move"
}
function _onDrop(e: DragEvent, targetId: string): void {
  e.preventDefault()
  const src = e.dataTransfer?.getData("text/plain")
  if (!src || src === targetId) return
  const tabs = [...store.tabs]
  const si = tabs.findIndex((t) => t.id === src)
  const ti = tabs.findIndex((t) => t.id === targetId)
  if (si === -1 || ti === -1) return
  const [moved] = tabs.splice(si, 1)
  tabs.splice(ti, 0, moved)
  tabs.forEach((t, i) => (t.order = i))
  draggedTabId.value = null
}
function _onMouseUp(e: MouseEvent, id: string): void {
  if (e.button === 1) store.closeTab(id)
}

/** Get file icon component based on file extension */
function _getFileIcon(tab: EditorTab): any {
  const ext = tab.filePath?.split(".").pop()?.toLowerCase() ?? ""
  if (["ts", "tsx", "js", "jsx", "py"].includes(ext)) return FileCode
  if (["json", "toml"].includes(ext)) return FileJson
  if (["md"].includes(ext)) return FileText
  return FileCode
}

/** Get file color matching Figma design */
function _getFileColor(label: string): string {
  if (label === "App.vue") return "#38BDF8"
  if (label === "main.ts") return "#60A5FA"
  const c: Record<string, string> = {
    ts: "#60A5FA",
    vue: "#38BDF8",
    json: "#FB923C",
    md: "#3B82F6",
  }
  return c[label.split(".").pop()?.toLowerCase() ?? ""] ?? "#908FA0"
}
</script>

<template>
  <div class="h-[var(--tabbar-height)] flex items-end bg-[var(--color-ide-bg)] border-b border-[var(--color-ide-border)] shrink-0 overflow-x-auto overflow-y-hidden" @dragover="onDragOver">
    <!-- Breadcrumb / Active file path (left side) -->
    <div class="shrink-0 h-full flex items-center px-3 text-xs border-r border-[var(--color-tab-border)] cursor-default select-none whitespace-nowrap"
      style="background: var(--color-editor-bg); color: var(--color-ide-text-dim);">
      <span v-if="store.activeTab?.filePath" class="flex items-center gap-1">
        <span v-for="(seg, i) in store.activeTab.filePath.split(/[/\\]/)" :key="i" class="flex items-center gap-1">
          <ChevronRight v-if="i > 0" :size="12" class="opacity-40" />
          <span :class="{ 'text-[var(--color-ide-text)]': i === store.activeTab.filePath.split(/[/\\]/).length - 1 }">{{ seg }}</span>
        </span>
      </span>
      <span v-else class="opacity-50">无打开的文件</span>
    </div>

    <!-- Tab items -->
    <div class="flex h-full items-stretch">
      <div
        v-for="tab in store.sortedTabs" :key="tab.id"
        draggable="true"
        class="group/tab relative flex items-center gap-2 pl-3 pr-8 h-full min-w-[100px] max-w-[200px] cursor-pointer border-r border-[var(--color-tab-border)] transition-colors select-none shrink-0"
        :class="{
          'bg-[var(--color-tab-active)]': tab.id === store.activeTabId,
          'bg-[var(--color-tab-inactive)] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-tab-hover)]': tab.id !== store.activeTabId,
          'opacity-50': draggedTabId === tab.id
        }"
        :title="`${tab.filePath || '(未命名)'}${tab.modified ? ' ●' : ''}`"
        @click="store.activeTabId = tab.id"
        @mousedown.middle="onMouseUp($event, tab.id)"
        @dragstart="onDragStart($event, tab.id)"
        @drop="onDrop($event, tab.id)"
      >
        <!-- File icon -->
        <component :is="getFileIcon(tab)" :size="14" :style="{ color: getFileColor(tab.label) }" />
        <!-- File name -->
        <span class="truncate flex-1 text-xs leading-none font-medium">{{ tab.label }}</span>

        <!-- Modified dot -->
        <Circle v-if="tab.modified" :size="9"
          :fill="tab.id === store.activeTabId ? '#FBBF24' : '#908FA0'"
          :stroke="tab.id === store.activeTabId ? '#FBBF24' : '#908FA0'"
          stroke-width="0.5" class="shrink-0 mt-0.5" />

        <!-- Close button -->
        <button class="absolute right-2 opacity-0 group-hover/tab:opacity-100 group-focus-within/tab:opacity-100 transition-opacity p-0.5 rounded hover:bg-white/10 shrink-0"
          :class="{ '!opacity-100': tab.id === store.activeTabId }"
          title="关闭"
          @click.stop="store.closeTab(tab.id)">
          <svg width="8" height="8" viewBox="0 0 24 24" fill="none" :stroke="tab.id === store.activeTabId ? '#DFE2F1' : 'currentColor'" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
        </button>

        <!-- Active bottom indicator (Figma: accent line) -->
        <div v-if="tab.id === store.activeTabId" class="absolute bottom-0 left-0 right-0 h-0.5 rounded-full" style="background:#C0C1FF;" />
      </div>
      <div v-if="store.sortedTabs.length > 0" class="flex items-center justify-center px-4 text-[11px] cursor-pointer transition-colors shrink-0" style="color:var(--color-ide-text-dim);" @mouseover="$el.style.color='var(--color-ide-text)'" @mouseout="$el.style.color=''">
        Review Next File →
      </div>
    </div>
  </div>
</template>
