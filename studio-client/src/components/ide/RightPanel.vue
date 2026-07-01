<script setup lang="ts">
/** CodeBuddy IDE — Right Panel (VSCode auxiliaryBarPart) */
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useIDEStore } from '@/stores/useIDEStore'
import Terminal from './Terminal.vue'
import OutputPanel from './OutputPanel.vue'
import ChatPanel from './ChatPanel.vue'
import MemoryPanel from './MemoryPanel.vue'
import SkillsPanel from './SkillsPanel.vue'
import McpPanel from './McpPanel.vue'

const store = useIDEStore()
const route = useRoute()
const dragging = ref(false)

function onResizeStart(e: MouseEvent): void {
  e.preventDefault(); dragging.value = true
  const sx = e.clientX, sw = store.layout.rightPanelWidth
  const move = (ev: MouseEvent) => { store.layout.rightPanelWidth = Math.max(260, Math.min(800, sw + (sx - ev.clientX))) }
  const up = () => { dragging.value = false; document.removeEventListener('mousemove',move); document.removeEventListener('mouseup',up) }
  document.addEventListener('mousemove',move); document.addEventListener('mouseup',up)
}

const isAgentChatRoute = computed(() => route.path === '/chat')
const allLabels: Record<string, string> = { output:'输出', terminal:'终端', debug:'运行和调试', chat:'AI 助手', memory:'记忆', skills:'技能', mcp:'MCP' }
const viewLabels = computed(() => isAgentChatRoute.value ? (()=>{const{chat:_,...r}=allLabels;return r})() : allLabels)

watch(isAgentChatRoute, (onChat) => { if (onChat && store.rightPanelView==='chat') store.rightPanelView='output' })
</script>

<template>
  <aside v-if="store.layout.rightPanelVisible"
    class="flex flex-col shrink-0 overflow-hidden relative"
    :style="{width:`${store.layout.rightPanelWidth}px`,background:'var(--color-ide-surface)',borderLeft:'1px solid var(--color-ide-border)'}">
    <!-- Resize Handle -->
    <div class="resize-handle resize-handle-h absolute left-0 top-0 bottom-0 -translate-x-1/2" :class="{active:dragging}" @mousedown.prevent="onResizeStart" />

    <!-- Title Bar (35px) -->
    <div class="flex items-center shrink-0" style="height:35px;border-bottom:1px solid var(--color-ide-border);padding:0 4px;">
      <div class="flex gap-0 h-full">
        <button v-for="(label,key) in viewLabels" :key="key"
          class="relative flex items-center px-3 text-[11px] font-semibold uppercase tracking-wider transition-colors"
          :class="store.rightPanelView===key
            ? 'text-[var(--color-ide-text)]'
            : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
          @click="store.rightPanelView=key as any">
          {{ label }}
          <div v-if="store.rightPanelView===key" class="absolute bottom-0 left-3 right-3"
            style="height:1px;background:var(--color-ide-accent);" />
        </button>
      </div>
      <div class="flex-1" />
      <button class="w-7 h-7 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]"
        title="关闭面板" @click="store.layout.rightPanelVisible=false">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-hidden">
      <OutputPanel v-if="store.rightPanelView==='output'" />
      <Terminal v-else-if="store.rightPanelView==='terminal'" />
      <div v-else-if="store.rightPanelView==='debug'" class="p-3 text-xs text-[var(--color-ide-text-dim)]">
        <p>运行和调试面板</p>
        <pre class="mt-2 text-[11px] font-mono p-2 rounded-[3px] border border-[var(--color-ide-border)]" style="background:var(--color-editor-bg);">等待调试会话...</pre>
      </div>
      <ChatPanel v-else-if="store.rightPanelView==='chat'" />
      <MemoryPanel v-else-if="store.rightPanelView==='memory'" />
      <SkillsPanel v-else-if="store.rightPanelView==='skills'" />
      <McpPanel v-else-if="store.rightPanelView==='mcp'" />
    </div>
  </aside>
</template>
