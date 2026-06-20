<script setup lang="ts">
/** CodeBuddy IDE — Top Menu Bar */
import { ref, onMounted, onUnmounted } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import type { MenuItem } from '@/types/ide'

const store = useIDEStore()
const openMenu = ref<string | null>(null)
const menuRef = ref<HTMLElement | null>(null)

const menus = ref<{ id: string; label: string; items: MenuItem[] }[]>([
  {
    id: 'file', label: '文件', items: [
      { label: '新建文件', shortcut: 'Ctrl+N', action: () => store.createUntitledTab() },
      { label: '打开文件...', shortcut: 'Ctrl+O' },
      { separator: true },
      { label: '保存', shortcut: 'Ctrl+S' },
      { label: '另存为...', shortcut: 'Ctrl+Shift+S' },
      { label: '保存全部', shortcut: 'Ctrl+K S' },
      { separator: true },
      { label: '退出', shortcut: 'Alt+F4' },
    ],
  },
  {
    id: 'edit', label: '编辑', items: [
      { label: '撤销', shortcut: 'Ctrl+Z' }, { label: '重做', shortcut: 'Ctrl+Y' },
      { separator: true },
      { label: '剪切', shortcut: 'Ctrl+X' }, { label: '复制', shortcut: 'Ctrl+C' },
      { label: '粘贴', shortcut: 'Ctrl+V' }, { label: '全选', shortcut: 'Ctrl+A' },
      { separator: true },
      { label: '查找', shortcut: 'Ctrl+F', action: () => store.toggleGlobalSearch() },
      { label: '替换', shortcut: 'Ctrl+H', action: () => { store.showGlobalSearch = true; store.searchState.replaceQuery = '' } },
      { label: '在文件中查找', shortcut: 'Ctrl+Shift+F' },
    ],
  },
  {
    id: 'view', label: '查看', items: [
      { label: '命令面板...', shortcut: 'Ctrl+Shift+P' }, { separator: true },
      { label: '资源管理器', shortcut: 'Ctrl+Shift+E', checked: store.activeActivityItem === 'explorer', action: () => store.activeActivityItem = 'explorer' },
      { label: '搜索', shortcut: 'Ctrl+Shift+F', action: () => { store.activeActivityItem = 'search'; store.toggleGlobalSearch() } },
      { label: '源代码管理', shortcut: 'Ctrl+Shift+G', checked: store.activeActivityItem === 'git', action: () => store.activeActivityItem = 'git' },
      { label: '运行和调试', action: () => store.activeActivityItem = 'debug' },
      { label: '扩展', action: () => store.activeActivityItem = 'extensions' },
      { separator: true },
      { label: '终端', shortcut: 'Ctrl+`', action: () => { store.rightPanelView = 'terminal'; store.layout.rightPanelVisible = true } },
      { label: '侧边栏可见性', shortcut: 'Ctrl+B', action: () => store.layout.fileTreeVisible = !store.layout.fileTreeVisible },
    ],
  },
  {
    id: 'help', label: '帮助', items: [
      { label: '欢迎' }, { label: '文档' },
      { label: '键盘快捷方式', shortcut: 'Ctrl+K Ctrl+S' },
      { separator: true }, { label: '关于 CodeBuddy IDE' },
    ],
  },
])

function toggleMenu(id: string): void { openMenu.value = openMenu.value === id ? null : id }
function closeMenus(): void { openMenu.value = null }
function handleItemClick(item: MenuItem): void { if (item.action) item.action(); closeMenus() }

onClickOutside(menuRef, closeMenus)
function onClickOutside(el: HTMLElement | null, handler: () => void): void {
  onMounted(() => document.addEventListener('mousedown', fn))
  onUnmounted(() => document.removeEventListener('mousedown', fn))
  function fn(e: MouseEvent) { if (el && !el.contains(e.target as Node)) handler() }
}
</script>

<template>
  <div class="h-[var(--menubar-height)] bg-[var(--color-activity-bg)] border-b border-[var(--color-ide-border)] flex items-center px-1 shrink-0 select-none z-50" ref="menuRef">
    <div class="flex items-center gap-2 mr-3 px-2 text-xs text-[var(--color-ide-text-dim)]">
      <div class="w-4 h-4 rounded bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-[10px] font-bold text-white">C</div>
      <span class="font-medium">CodeBuddy</span>
    </div>
    <div v-for="menu in menus" :key="menu.id" class="relative">
      <button class="px-2 py-1 text-xs rounded hover:bg-white/5 transition-colors" :class="{ 'bg-white/10': openMenu === menu.id }" @click.stop="toggleMenu(menu.id)">{{ menu.label }}</button>
      <Transition name="fade">
        <div v-if="openMenu === menu.id" class="absolute top-full left-0 mt-0 min-w-[220px] bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded shadow-xl py-1 z-[100]" @click.stop>
          <template v-for="(item, idx) in menu.items" :key="idx">
            <hr v-if="item.separator" class="my-1 border-[var(--color-ide-border)]" />
            <button v-else class="context-menu-item w-full text-left text-xs flex justify-between gap-6"
              :class="{ 'text-[var(--color-ide-accent)]': !!item.checked && item.checked }" :disabled="item.disabled" @click="handleItemClick(item)">
              <span>{{ item.label }}</span><span class="text-[var(--color-ide-text-dim)]">{{ item.shortcut }}</span>
            </button>
          </template>
        </div>
      </Transition>
    </div>
    <div class="flex-1" />
    <div class="flex items-center gap-1 px-1">
      <button title="AI 助手" class="p-1 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors text-[11px]" @click="store.rightPanelView = 'chat'; store.layout.rightPanelView = true">AI 助手</button>
      <div class="w-px h-4 bg-[var(--color-ide-border)] mx-1" />
      <button class="w-7 h-7 flex items-center justify-center rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 9l6 6m0-6l-6 6"/></svg></button>
      <button class="w-7 h-7 flex items-center justify-center rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/></svg></button>
      <button class="w-7 h-7 flex items-center justify-center rounded hover:bg-red-500/20 hover:text-red-400 text-[var(--color-ide-text-dim)] transition-colors"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg></button>
    </div>
  </div>
</template>
