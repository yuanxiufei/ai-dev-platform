<script setup lang="ts">/** CodeBuddy IDE — Right Panel */
import { ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import Terminal from './Terminal.vue'
import OutputPanel from './OutputPanel.vue'
import ChatPanel from './ChatPanel.vue'

const store = useIDEStore()
const dragging = ref(false)

function onResizeStart(e: MouseEvent): void {
  e.preventDefault(); dragging.value = true; const sx = e.clientX, sw = store.layout.rightPanelWidth
  const move = (ev: MouseEvent) => { store.layout.rightPanelWidth = Math.max(260, Math.min(800, sw + (sx - ev.clientX))) }
  const up = () => { dragging.value = false; document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up) }
  document.addEventListener('mousemove', move); document.addEventListener('mouseup', up)
}

const viewLabels: Record<string, string> = { output: '输出', terminal: '终端', debug: '运行和调试', chat: 'AI 助手' }
</script>

<template>
  <aside v-if="store.layout.rightPanelVisible" class="bg-[var(--color-ide-surface)] flex flex-col shrink-0 border-l border-[var(--color-ide-border)] overflow-hidden relative" :style="{ width: `${store.layout.rightPanelWidth}px` }">
    <div class="resize-handle resize-handle-h absolute left-0 top-0 bottom-0 -translate-x-1/2" :class="{ active: dragging }" @mousedown.prevent="onResizeStart" />
    <div class="h-9 flex items-center border-b border-[var(--color-ide-border)] shrink-0 px-2">
      <div class="flex gap-0.5 text-[11px]">
        <button v-for="(label, key) in viewLabels" :key="key" class="px-2.5 py-1 rounded-t transition-colors"
          :class="store.rightPanelView === key ? 'bg-[var(--color-ide-bg)] text-[var(--color-ide-text)] border-t-2 border-t-[var(--color-ide-accent)] -mb-[1px]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-white/5'"
          @click="store.rightPanelView = key as any">{{ label }}</button>
      </div>
      <div class="flex-1" />
      <button class="p-1 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]" title="关闭面板" @click="store.layout.rightPanelVisible = false"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
    <div class="flex-1 overflow-hidden">
      <OutputPanel v-if="store.rightPanelView === 'output'" />
      <Terminal v-else-if="store.rightPanelView === 'terminal'" />
      <div v-else-if="store.rightPanelView === 'debug'" class="p-3 text-xs text-[var(--color-ide-text-dim)]"><p>运行和调试面板</p><pre class="mt-2 text-[11px] font-mono bg-[var(--color-ide-bg)] p-2 rounded border border-[var(--color-ide-border)]">等待调试会话...</pre></div>
      <ChatPanel v-else-if="store.rightPanelView === 'chat'" />
    </div>
  </aside>
</template>
