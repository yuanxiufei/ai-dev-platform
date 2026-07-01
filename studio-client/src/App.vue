<script setup lang="ts">
/**
 * CodeBuddy IDE — Root Application Component
 *
 * IDE Layout Shell:
 *   MenuBar → [ Sidebar | EditorArea(RouterView/CodeEditor) | RightPanel ] → StatusBar
 *
 * Studio pages render inside EditorArea via Vue Router.
 * Keyboard shortcuts are managed by useShortcuts composable.
 */
import { onMounted, ref } from "vue"
import { usePlugins } from "@/composables/usePlugins"
import { useShortcuts } from "@/composables/useShortcuts"
import { useIDEStore } from "@/stores/useIDEStore"
import MenuBar from "@/components/ide/MenuBar.vue"
import Sidebar from "@/components/ide/Sidebar.vue"
import EditorArea from "@/components/ide/EditorArea.vue"
import RightPanel from "@/components/ide/RightPanel.vue"
import StatusBar from "@/components/ide/StatusBar.vue"
import GlobalSearch from "@/components/ide/GlobalSearch.vue"
import CommandPalette from "@/components/ide/CommandPalette.vue"
import SettingsPanel from "@/components/ide/SettingsPanel.vue"

const store = useIDEStore()
const {
  isCommandPaletteVisible,
  toggleCommandPalette,
  on: onCommand,
} = useShortcuts()
const { activateAll: activatePlugins } = usePlugins()

// ── Wire IDE commands to store actions ──────────────────
onCommand("file.new", () => store.createUntitledTab())
onCommand("file.save", async () => {
  await store.saveActiveFile()
})
onCommand("file.saveAll", async () => {
  await store.saveAllFiles()
})
onCommand("file.closeEditor", () => {
  if (store.activeTabId) store.closeTab(store.activeTabId)
})
onCommand("edit.findInFiles", () => {
  store.showGlobalSearch = true
})
onCommand("view.toggleSidebar", () => {
  store.layout.fileTreeVisible = !store.layout.fileTreeVisible
})
onCommand("view.togglePanel", () => {
  store.layout.rightPanelVisible = !store.layout.rightPanelVisible
})
onCommand("terminal.toggle", () => {
  store.rightPanelView = "terminal"
  store.layout.rightPanelVisible = !store.layout.rightPanelVisible
})
onCommand("ai.chatPanel", () => {
  store.rightPanelView = "chat"
  store.layout.rightPanelVisible = true
})
onCommand("view.resetLayout", () => {
  store.resetLayout()
})

// ── UI overlay state ───────────────────────────────────
const showSettings = ref(false)

function onCommandExecute(cmdId: string): void {
  switch (cmdId) {
    case "settings.open":
      showSettings.value = true
      break
  }
}

// ── Lifecycle ──────────────────────────────────────────
onMounted(async () => {
  try {
    await activatePlugins()
  } catch (e) {
    console.warn("[CodeBuddy] Plugin activation:", e)
  }

  await store.refreshGitStatus()
  store.addOutputLine(`[信息] CodeBuddy IDE v0.1.0 已启动`)
  if (store.workspaceRoot) {
    store.addOutputLine(`[信息] 工作区: ${store.workspaceRoot}`)
  }

  console.log(
    "%c[CodeBuddy IDE] Ready",
    "color:#0078D4;font-weight:bold;font-size:14px",
  )
})
</script>

<template>
  <RouterView v-if="$route.path === '/login'" />
  <div v-else class="ide-root h-full w-full flex flex-col bg-[var(--color-ide-bg)] overflow-hidden">
    <!-- Top Menu Bar -->
    <MenuBar v-if="store.layout.menuBarVisible" @open-settings="showSettings = true" />

    <!-- Main Content: Sidebar | Editor(Studio Pages / Code) | Right Panel -->
    <div class="flex-1 flex overflow-hidden min-h-0">
      <Sidebar />
      <EditorArea class="flex-1 min-w-0" />
      <RightPanel />
    </div>

    <!-- Bottom Status Bar -->
    <StatusBar v-if="store.layout.statusBarVisible" />

    <!-- Overlays -->
    <GlobalSearch
      :visible="store.showGlobalSearch"
      @close="store.showGlobalSearch = false"
    />

    <CommandPalette
      :visible="isCommandPaletteVisible"
      @update:visible="(v: boolean) => { isCommandPaletteVisible = v; if (!v) toggleCommandPalette(false) }"
      @execute="onCommandExecute"
    />

    <SettingsPanel
      :visible="showSettings"
      @update:visible="showSettings = $event"
    />
  </div>
</template>
