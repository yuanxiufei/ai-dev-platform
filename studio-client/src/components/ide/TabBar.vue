<script setup lang="ts">
/** CodeBuddy IDE — Tab Bar */
import { computed, ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { X, Circle, ChevronRight } from 'lucide-vue-next'

const store = useIDEStore()
const draggedTabId = ref<string | null>(null)
const visibleTabs = computed(() => store.sortedTabs.filter(t => t.id !== store.activeTabId))

function onDragStart(e: DragEvent, id: string): void { draggedTabId.value = id; e.dataTransfer?.setData('text/plain', id); e.dataTransfer!.effectAllowed = 'move' }
function onDragOver(e: DragEvent): void { e.preventDefault(); e.dataTransfer!.dropEffect = 'move' }
function onDrop(e: DragEvent, targetId: string): void {
  e.preventDefault(); const src = e.dataTransfer?.getData('text/plain')
  if (!src || src === targetId) return
  const tabs = [...store.tabs]; const si = tabs.findIndex(t => t.id === src); const ti = tabs.findIndex(t => t.id === targetId)
  if (si === -1 || ti === -1) return
  const [moved] = tabs.splice(si, 1); tabs.splice(ti, 0, moved); tabs.forEach((t, i) => t.order = i); draggedTabId.value = null
}
function onMouseUp(e: MouseEvent, id: string): void { if (e.button === 1) store.closeTab(id) }
</script>

<template>
  <div class="h-[var(--tabbar-height)] flex items-end bg-[var(--color-tab-inactive)] border-b border-[var(--color-tab-border)] shrink-0 overflow-x-auto overflow-y-hidden" @dragover="onDragOver">
    <div class="shrink-0 h-full flex items-center px-3 text-xs text-[var(--color-ide-text-dim)] border-r border-[var(--color-tab-border)] bg-[var(--color-ide-bg)] cursor-default select-none whitespace-nowrap">
      <span v-if="store.activeTab?.filePath" class="flex items-center gap-1">
        <span v-for="(seg, i) in store.activeTab.filePath.split(/[/\\]/)" :key="i" class="flex items-center gap-1">
          <ChevronRight v-if="i > 0" :size="12" class="opacity-40" /><span :class="{ 'text-[var(--color-ide-text)]': i === store.activeTab.filePath.split(/[/\\]/).length - 1 }">{{ seg }}</span>
        </span>
      </span>
      <span v-else class="opacity-50">无打开的文件</span>
    </div>
    <div class="flex h-full items-stretch">
      <div v-for="tab in store.sortedTabs" :key="tab.id" draggable="true"
        class="group/tab relative flex items-center gap-1.5 pl-3 pr-2 h-full min-w-[100px] max-w-[200px] cursor-pointer border-r border-[var(--color-tab-border)] transition-colors select-none shrink-0"
        :class="{ 'bg-[var(--color-tab-active)] text-[var(--color-ide-text-bright)]': tab.id === store.activeTabId, 'bg-[var(--color-tab-inactive)] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-tab-hover)]': tab.id !== store.activeTabId, 'opacity-50': draggedTabId === tab.id }"
        :title="`${tab.filePath || '(未命名)'}${tab.modified ? ' ●' : ''}`"
        @click="store.activeTabId = tab.id" @mousedown.middle="onMouseUp($event, tab.id)" @dragstart="onDragStart($event, tab.id)" @drop="onDrop($event, tab.id)">
        <Circle v-if="tab.modified" :size="9" :fill="tab.id === store.activeTabId ? '#f5e0dc' : '#939ab7'" class="shrink-0 mt-0.5" :stroke="tab.id === store.activeTabId ? '#f5e0dc' : '#939ab7'" stroke-width="0.5" />
        <span class="truncate flex-1 text-xs leading-none">{{ tab.label }}</span>
        <button class="opacity-0 group-hover/tab:opacity-100 group-focus-within/tab:opacity-100 transition-opacity p-0.5 rounded hover:bg-white/10 shrink-0" :class="{ '!opacity-100': tab.id === store.activeTabId }" title="关闭" @click.stop="store.closeTab(tab.id)"><X :size="16" /></button>
        <div v-if="tab.id === store.activeTabId" class="absolute bottom-0 left-0 right-0 h-0.5 bg-[var(--color-ide-accent)]" />
      </div>
      <div v-if="store.sortedTabs.length > 0" class="flex items-center justify-center px-4 text-[11px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] cursor-pointer transition-colors shrink-0">Review Next File →</div>
    </div>
  </div>
</template>
