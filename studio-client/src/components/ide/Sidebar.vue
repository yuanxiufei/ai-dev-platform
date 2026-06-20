<script setup lang="ts">
/** CodeBuddy IDE — Left Sidebar (Activity Bar + File Tree) */
import { ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { Files, Search, GitBranch, Bug, Blocks, Settings } from 'lucide-vue-next'
import FileTree from './FileTree.vue'

const store = useIDEStore()
const iconMap: Record<string, any> = { Files, Search, GitBranch, Bug, Blocks }
const isDragging = ref(false)

function onDragStart(e: MouseEvent): void {
  e.preventDefault(); isDragging.value = true; document.body.classList.add('cursor-col-resize','select-none')
  const startX = e.clientX, startW = store.layout.sidebarWidth
  const move = (ev: MouseEvent) => { store.layout.sidebarWidth = Math.max(180, Math.min(500, startW + (ev.clientX - startX))) }
  const up = () => { isDragging.value = false; document.body.classList.remove('cursor-col-resize','select-none'); document.removeEventListener('mousemove',move); document.removeEventListener('mouseup',up) }
  document.addEventListener('mousemove',move); document.addEventListener('mouseup',up)
}
</script>

<template>
  <div v-if="store.layout.activityBarVisible" class="shrink-0 flex h-full" style="width: var(--sidebar-width);">
    <aside class="w-12 bg-[var(--color-activity-bg)] flex flex-col items-center py-1 shrink-0 z-20">
      <button class="w-9 h-9 my-1 rounded-md flex items-center justify-center hover:bg-white/5 transition-colors mb-2">
        <div class="w-6 h-6 rounded bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-[11px] font-bold text-white">C</div>
      </button>
      <div class="flex-1 flex flex-col gap-0.5 w-full">
        <button v-for="item in store.activityItems" :key="item.id" class="group relative w-full h-9 flex items-center justify-center transition-colors"
          :class="store.activeActivityItem === item.id ? 'text-white' : 'text-gray-500 hover:text-gray-300'" :title="item.label"
          @click="store.activeActivityItem = item.id; store.layout.fileTreeVisible = true">
          <div v-if="store.activeActivityItem === item.id" class="absolute left-0 w-0.5 h-5 bg-white rounded-r" />
          <component :is="iconMap[item.icon] ?? item.icon" :size="20" />
          <span class="absolute left-full ml-2 px-2 py-1 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">{{ item.label }}</span>
          <span v-if="item.badge" class="absolute top-1 right-1 min-w-[16px] h-4 flex items-center justify-center bg-blue-500 text-[10px] font-medium text-white rounded-full px-1">{{ item.badge }}</span>
        </button>
      </div>
      <div class="mt-auto pt-1 border-t border-[#33334a33] w-full">
        <button class="w-full h-9 flex items-center justify-center text-gray-500 hover:text-gray-300 transition-colors" title="设置" @click="store.activeActivityItem = 'settings'"><Settings :size="19" /></button>
      </div>
    </aside>
    <div class="resize-handle resize-handle-h" :class="{ active: isDragging }" @mousedown.prevent="onDragStart" />
    <Transition name="slide-left">
      <aside v-show="store.layout.fileTreeVisible" class="bg-[var(--color-ide-surface)] flex flex-col overflow-hidden shrink-0" :style="{ width: `${store.layout.sidebarWidth}px` }">
        <div class="h-9 flex items-center justify-between px-3 text-xs font-semibold text-[var(--color-ide-text)] shrink-0 border-b border-transparent">
          <span>{{ store.activeActivityItem === 'explorer' ? '资源管理器' : store.activeActivityItem === 'search' ? '搜索' : store.activeActivityItem === 'git' ? '源代码管理' : store.activeActivityItem === 'debug' ? '运行和调试' : store.activeActivityItem === 'settings' ? '设置' : store.activeActivityItem }}</span>
          <div class="flex items-center gap-0.5">
            <button class="p-1 rounded hover:bg-white/5 opacity-60 hover:opacity-100"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg></button>
            <button class="p-1 rounded hover:bg-white/5 opacity-60 hover:opacity-100" title="关闭侧边栏" @click="store.layout.fileTreeVisible = false"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 18l-6-6 6-6"/></svg></button>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto overflow-x-hidden">
          <FileTree v-if="store.activeActivityItem === 'explorer'" />
          <div v-else-if="store.activeActivityItem === 'search'" class="p-3 text-xs text-[var(--color-ide-text-dim)]"><input type="text" placeholder="搜索" class="w-full bg-[var(--color-ide-bg)] border border-[var(--color-ide-border)] rounded px-2 py-1.5 text-xs focus:outline-none focus:border-[var(--color-ide-border-focus)]"/></div>
          <div v-else-if="store.activeActivityItem === 'git'" class="p-3 text-xs text-[var(--color-ide-text-dim)] space-y-2"><div class="text-[var(--color-ide-text)] font-semibold">源代码管理</div><div>main</div><div class="border-t border-[var(--color-ide-border)] pt-2"><div class="text-[10px] uppercase tracking-wider text-[var(--color-ide-text-dim)] mb-1">更改 (9)</div><div v-for="i in 9" :key="i" class="py-0.5 truncate hover:bg-white/5 rounded px-1 cursor-pointer">修改的文件_{{ i }}.ts</div></div></div>
          <div v-else-if="store.activeActivityItem === 'debug'" class="p-3 text-xs"><p>运行和调试</p><button class="mt-3 w-full py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs">启动调试</button></div>
          <div v-else-if="store.activeActivityItem === 'settings'" class="p-3 text-xs text-[var(--color-ide-text-dim)] space-y-1"><p>设置面板</p><button class="w-full text-left px-2 py-1.5 rounded hover:bg-white/5">用户设置</button><button class="w-full text-left px-2 py-1.5 rounded hover:bg-white/5">工作区设置</button><button class="w-full text-left px-2 py-1.5 rounded hover:bg-white/5">扩展</button></div>
        </div>
      </aside>
    </Transition>
  </div>
</template>
