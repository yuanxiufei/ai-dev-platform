<script setup lang="ts">
/**
 * CodeBuddy IDE — Left Sidebar (Explorer Panel)
 * Figma Design: studio-ai (node-id=9-195) — "资源管理器" 260px
 *
 * Layout:
 *   - Header: "资源管理器" + action buttons
 *   - Body: Scrollable file tree
 *   - Footer: 4 icon toolbar on #171B26 bg
 */
import { ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import {
  Files, Search, GitBranch, Bug, Blocks,
  Settings, ChevronRight, ChevronDown,
  FolderOpen, FolderClosed, FileCode, FileJson,
  FileText, Image as ImgIcon, Archive, File, FileSymlink,
} from 'lucide-vue-next'
import FileTree from './FileTree.vue'

const store = useIDEStore()
const isDragging = ref(false)

function onDragStart(e: MouseEvent): void {
  e.preventDefault()
  isDragging.value = true
  document.body.classList.add('cursor-col-resize', 'select-none')
  const startX = e.clientX
  const startW = store.layout.sidebarWidth
  const move = (ev: MouseEvent) => {
    store.layout.sidebarWidth = Math.max(180, Math.min(500, startW + (ev.clientX - startX)))
  }
  const up = () => {
    isDragging.value = false
    document.body.classList.remove('cursor-col-resize', 'select-none')
    document.removeEventListener('mousemove', move)
    document.removeEventListener('mouseup', up)
  }
  document.addEventListener('mousemove', move)
  document.addEventListener('mouseup', up)
}

/** Bottom toolbar items matching Figma design */
const bottomTools = [
  { id: 'explorer', icon: Files, label: '资源管理器' },
  { id: 'search', icon: Search, label: '搜索' },
  { id: 'git', icon: GitBranch, label: '源代码管理' },
  { id: 'debug', icon: Bug, label: '运行和调试' },
]
</script>

<template>
  <div v-if="store.layout.fileTreeVisible"
    class="shrink-0 flex flex-col h-full overflow-hidden border-r border-[var(--color-ide-border)]"
    :style="{ width: `${store.layout.sidebarWidth}px` }">
    <!-- Resize Handle -->
    <div class="resize-handle resize-handle-h" :class="{ active: isDragging }" @mousedown.prevent="onDragStart" />

    <!-- ── Header: 资源管理器 ──────────────────────── -->
    <div class="flex items-center justify-between px-3 py-2.5 shrink-0" style="border-bottom: 1px solid rgba(70,69,84,0.3);">
      <span class="text-[11px] font-bold uppercase tracking-wider" style="color:#908FA0;">资源管理器</span>
      <div class="flex items-center gap-1">
        <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="新建文件">
          <svg width="13.33" height="10.67" viewBox="0 0 16 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 1H3a1 1 0 00-1 1v8a1 1 0 001 1h10a1 1 0 001-1V5l-4-4z"/><path d="M10 1v4h4"/></svg>
        </button>
        <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="折叠全部">
          <svg width="10.67" height="10.67" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 6L8 12 2 6"/></svg>
        </button>
        <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="更多操作">
          <svg width="13.33" height="10.67" viewBox="0 0 16 12" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="3" cy="6" r="1" fill="currentColor"/><circle cx="8" cy="6" r="1" fill="currentColor"/><circle cx="13" cy="6" r="1" fill="currentColor"/></svg>
        </button>
      </div>
    </div>

    <!-- ── Body: File Tree (scrollable) ─────────────── -->
    <div class="flex-1 overflow-y-auto overflow-x-hidden py-2">
      <FileTree />
    </div>

    <!-- ── Footer: Bottom Toolbar (#171B26) ─────────── -->
    <div class="flex items-center justify-between px-6 py-2 shrink-0" style="background:#171B26; border-top:1px solid var(--color-ide-border);">
      <button
        v-for="tool in bottomTools" :key="tool.id"
        class="w-8 h-8 flex items-center justify-center rounded transition-colors"
        :class="store.activeActivityItem === tool.id ? 'text-[#C0C1FF] bg-[#C0C1FF10]' : 'text-[#908FA0] hover:text-[#DFE2F1]'"
        :title="tool.label"
        @click="store.activeActivityItem = tool.id; if(tool.id!=='explorer') store.layout.fileTreeVisible=true;"
      >
        <component :is="tool.icon" :size="16" />
      </button>
    </div>
  </div>

  <!-- Activity Bar (collapsed state when file tree hidden) -->
  <div v-else-if="store.layout.activityBarVisible"
    class="shrink-0 w-14 h-full flex flex-col items-center py-1.5 z-20"
    style="background: var(--color-activity-bg);">
    <!-- Logo -->
    <button
      class="w-10 h-10 my-1 rounded-md flex items-center justify-center hover:bg-white/5 transition-colors mb-3"
      title="CodeBuddy"
      @click="store.activeActivityItem = 'explorer'; store.layout.fileTreeVisible = true"
    >
      <div class="w-7 h-7 rounded flex items-center justify-center text-sm font-bold text-white" style="background: linear-gradient(135deg, #C0C1FF, #8B7BD6);">C</div>
    </button>

    <!-- Activity Items -->
    <div class="flex-1 flex flex-col gap-0.5 w-full">
      <button
        v-for="item in store.activityItems" :key="item.id"
        class="group relative w-full h-10 flex items-center justify-center transition-colors"
        :class="store.activeActivityItem === item.id ? 'text-white' : 'text-gray-500 hover:text-gray-300'"
        :title="item.label"
        @click="store.activeActivityItem = item.id; store.layout.fileTreeVisible = true"
      >
        <div v-if="store.activeActivityItem === item.id" class="absolute left-0 w-0.5 h-6 bg-white rounded-r" />
        <component :is="item.icon" ?? item.icon" :size="24" />
        <span class="absolute left-full ml-2 px-2.5 py-1.5 rounded text-sm whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50"
          style="background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);">
          {{ item.label }}
        </span>
        <span v-if="item.badge" class="absolute top-1 right-1 min-w-[16px] h-4 flex items-center justify-center bg-blue-500 text-[10px] font-medium text-white rounded-full px-1">
          {{ item.badge }}
        </span>
      </button>
    </div>

    <!-- Settings at bottom -->
    <div class="mt-auto pt-1 w-full" style="border-top: 1px solid rgba(51,51,74,0.2);">
      <button
        class="w-full h-10 flex items-center justify-center text-gray-500 hover:text-gray-300 transition-colors"
        title="管理" @click="store.activeActivityItem = 'settings'">
        <Settings :size="22" />
      </button>
    </div>
  </div>
</template>
