<script setup lang="ts">
/**
 * CodeBuddy IDE — Root Application Component
 * 
 * IDE Layout Shell + Studio Router Views
 * The IDE structure (MenuBar/Sidebar/EditorArea/RightPanel/StatusBar) wraps everything,
 * while Studio pages render inside the editor area via Vue Router.
 */
import { computed, onMounted, ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import MenuBar from './components/ide/MenuBar.vue'
import StatusBar from './components/ide/StatusBar.vue'
import Sidebar from './components/ide/Sidebar.vue'
import EditorArea from './components/ide/EditorArea.vue'
import RightPanel from './components/ide/RightPanel.vue'
import GlobalSearch from './components/ide/GlobalSearch.vue'
import CommandPalette from './components/ide/CommandPalette.vue'
import SettingsPanel from './components/ide/SettingsPanel.vue'
import { useShortcuts } from '@/composables/useShortcuts'
import { usePlugins } from '@/composables/usePlugins'

const store = useIDEStore()
const { isCommandPaletteVisible, toggleCommandPalette, execute: executeShortcut } = useShortcuts()
const { activateAll: activatePlugins } = usePlugins()

// UI State
const showSettings = ref(false)

/** Keyboard shortcuts */
function onKeyDown(e: KeyboardEvent): void {
  const ctrl = e.ctrlKey || e.metaKey
  if (ctrl && e.key === 'b' && !e.shiftKey) { e.preventDefault(); store.layout.fileTreeVisible = !store.layout.fileTreeVisible }
  if (ctrl && e.shiftKey && e.key === 'F') { e.preventDefault(); store.showGlobalSearch = true }
  if (ctrl && !e.shiftKey && e.key === 'p') { e.preventDefault(); toggleCommandPalette(true); isCommandPaletteVisible.value = true }
  if (ctrl && e.key === 'w') { e.preventDefault(); if (store.activeTabId) store.closeTab(store.activeTabId) }
  if (ctrl && e.key === 'n' && !e.shiftKey) { e.preventDefault(); store.createUntitledTab() }
  if (ctrl && e.key === 's') { e.preventDefault(); const tab = store.activeTab; if (tab?.modified) { tab.modified = false; tab.originalContent = tab.content } }
  if (ctrl && e.key === '`') { e.preventDefault(); store.rightPanelView = 'terminal'; store.layout.rightPanelVisible = true }
  if (ctrl && e.key === ',') { e.preventDefault(); showSettings.value = true }
  if (e.key === 'Escape') { store.showGlobalSearch = false; showSettings.value = false }
}

if (typeof window !== 'undefined') window.addEventListener('keydown', onKeyDown)

function onCommandExecute(cmdId: string): void {
  executeShortcut(cmdId)
  switch (cmdId) {
    case 'file.new': store.createUntitledTab(); break
    case 'file.save': { const t = store.activeTab; if (t?.modified) t.modified = false }; break
    case 'view.toggleSidebar': store.layout.fileTreeVisible = !store.layout.fileTreeVisible; break
    case 'view.togglePanel': store.layout.rightPanelVisible = !store.layout.rightPanelVisible; break
    case 'settings.open': showSettings.value = true; break
    case 'terminal.toggle': store.rightPanelView = 'terminal'; store.layout.rightPanelVisible = !store.layout.rightPanelVisible; break
    case 'ai.chatPanel': store.rightPanelView = 'chat'; store.layout.rightPanelVisible = true; break
    default: console.log(`[Command] ${cmdId}`)
  }
}

onMounted(async () => {
  try { await activatePlugins() } catch (e) { console.warn('[IDE] Plugin activation:', e) }
  console.log('%c[CodeBuddy IDE] Ready', 'color:#0078D4;font-weight:bold;font-size:14px')
})
</script>

<template>
  <div class="ide-root h-full w-full flex flex-col bg-[var(--color-ide-bg)] overflow-hidden">
    <!-- Top Menu Bar -->
    <MenuBar v-if="store.layout.menuBarVisible" @open-settings="showSettings = true" />

    <!-- Main Content Area -->
    <div class="flex-1 flex overflow-hidden min-h-0">
      <!-- Left Sidebar -->
      <Sidebar />

      <!-- Center: Editor Area (contains code editor or Studio pages via router) -->
      <EditorArea class="flex-1 min-w-0" />

      <!-- Right Panel (Output / Terminal / AI Chat) -->
      <RightPanel />
    </div>

    <!-- Bottom Status Bar -->
    <StatusBar v-if="store.layout.statusBarVisible" />

    <!-- Global Search Overlay -->
    <GlobalSearch :visible="store.showGlobalSearch" @close="store.showGlobalSearch = false" />

    <!-- Command Palette (Ctrl+Shift+P) -->
    <CommandPalette :visible="isCommandPaletteVisible" @update:visible="(v)=>{isCommandPaletteVisible=v;if(!v)toggleCommandPalette(false)}" @execute="onCommandExecute" />

    <!-- Settings Panel (Ctrl+,) -->
    <SettingsPanel :visible="showSettings" @update:visible="showSettings = $event" />
  </div>
</template>
