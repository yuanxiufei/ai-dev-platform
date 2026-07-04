<script setup lang="ts">
/** CodeBuddy IDE — Right Panel (VSCode auxiliaryBarPart) — AI 助手专属面板 */
/**
 * VSCode 对标 — 不在 mounted 强制覆盖布局偏好
 * 布局状态从 localStorage 恢复，用户可自由关闭/重开 AI 面板
 *
 * Session 36: 顶部 tab 改为图标 + tooltip（与左侧 ActivityBar 风格一致）
 *   - 删除冗余文字标签 "AI 助手 记忆技能MCP"（左侧 ActivityBar 已有 AI 入口）
 *   - 每个 tab 只显示 16px SVG 图标，hover 显示 tooltip
 *   - 激活态：紫色 (var(--color-ide-accent)) 文字 + 底部 2px 指示线
 *   - 关闭按钮保留右上角
 */
import { ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import ChatPanel from './ChatPanel.vue'
import MemoryPanel from './MemoryPanel.vue'
import SkillsPanel from './SkillsPanel.vue'
import McpPanel from './McpPanel.vue'

const store = useIDEStore()
const dragging = ref(false)

function onResizeStart(e: MouseEvent): void {
  e.preventDefault(); dragging.value = true
  const sx = e.clientX, sw = store.layout.rightPanelWidth
  const move = (ev: MouseEvent) => { store.layout.rightPanelWidth = Math.max(260, Math.min(800, sw + (sx - ev.clientX))) }
  const up = () => { dragging.value = false; document.removeEventListener('mousemove',move); document.removeEventListener('mouseup',up) }
  document.addEventListener('mousemove',move); document.addEventListener('mouseup',up)
}

// ─── 4 个 AI 子视图定义 (图标 + tooltip) ───
const tabs = [
  {
    key: 'chat',
    title: 'AI 助手',
    svg: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>`,
  },
  {
    key: 'memory',
    title: '长期记忆',
    svg: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M12 5v13"/></svg>`,
  },
  {
    key: 'skills',
    title: '技能',
    svg: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M15.39 4.39a1 1 0 0 0 1.68-.474 2.5 2.5 0 1 1 3.014 3.015 1 1 0 0 0-.474 1.68l1.683 1.682a2.414 2.414 0 0 1 0 3.414L19.61 15.39a1 1 0 0 1-1.68-.474 2.5 2.5 0 1 0-3.014 3.015 1 1 0 0 1 .474 1.68l-1.683 1.682a2.414 2.414 0 0 1-3.414 0L8.61 19.61a1 1 0 0 0-1.68.474 2.5 2.5 0 1 1-3.014-3.015 1 1 0 0 0 .474-1.68l-1.683-1.682a2.414 2.414 0 0 1 0-3.414L4.39 8.61a1 1 0 0 1 1.68.474 2.5 2.5 0 1 0 3.014-3.015 1 1 0 0 1-.474-1.68l1.683-1.682a2.414 2.414 0 0 1 3.414 0z"/></svg>`,
  },
  {
    key: 'mcp',
    title: 'MCP 服务器',
    svg: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="8" x="2" y="2" rx="2"/><rect width="20" height="8" x="2" y="14" rx="2"/><path d="M6 6h.01"/><path d="M6 18h.01"/></svg>`,
  },
] as const
</script>

<template>
  <aside v-if="store.layout.rightPanelVisible"
    class="flex flex-col shrink-0 overflow-hidden relative"
    :style="{width:`${store.layout.rightPanelWidth}px`,background:'var(--color-ide-surface)',borderLeft:'1px solid var(--color-ide-border)'}">
    <!-- Resize Handle -->
    <div class="resize-handle resize-handle-h absolute left-0 top-0 bottom-0 -translate-x-1/2" :class="{active:dragging}" @mousedown.prevent="onResizeStart" />

    <!-- Title Bar (var(--panel-title-height)) — 图标式 Tab 切换 -->
    <div class="flex items-center shrink-0" style="height:var(--panel-title-height);border-bottom:1px solid var(--color-ide-border);padding:0 4px;">
      <div class="flex gap-0 h-full">
        <button v-for="tab in tabs" :key="tab.key"
          class="relative flex items-center justify-center w-9 h-full transition-colors"
          :class="store.rightPanelView===tab.key
            ? 'text-[var(--color-ide-accent)]'
            : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
          :title="tab.title"
          :aria-label="tab.title"
          :aria-pressed="store.rightPanelView===tab.key"
          @click="store.rightPanelView=tab.key as any">
          <span v-html="tab.svg" />
          <div v-if="store.rightPanelView===tab.key" class="absolute bottom-0 left-2 right-2"
            style="height:2px;background:var(--color-ide-accent);" />
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
      <ChatPanel v-if="store.rightPanelView==='chat'" />
      <MemoryPanel v-else-if="store.rightPanelView==='memory'" />
      <SkillsPanel v-else-if="store.rightPanelView==='skills'" />
      <McpPanel v-else-if="store.rightPanelView==='mcp'" />
    </div>
  </aside>
</template>
