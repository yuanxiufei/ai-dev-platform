<script setup lang="ts">
/**
 * CodeBuddy IDE — Root Application
 *
 * ══════════════════════════════════════════════════════════
 *  VSCode Workbench Layout (pixel-accurate SerializableGrid)
 * ══════════════════════════════════════════════════════════
 *
 *  ┌──────────────────────────────────────────────────┐
 *  │  TitleBar (menuBar)          h=35px              │  ← TITLEBAR_PART
 *  ├──────┬───────────────────────────────┬───────────┤
 *  │ActBar│                               │           │
 *  │ 48px │  Editor Area                  │ AuxBar    │  ← HORIZONTAL
 *  │      │  (RouterView/CodeEditor)      │           │
 *  │      │  ┌─────────────────────────┐  │           │
 *  │Side  │  │ Bottom Panel (h=300px)  │  │           │
 *  │Bar   │  └─────────────────────────┘  │           │
 *  ├──────┴───────────────────────────────┴───────────┤
 *  │  StatusBar                       h=22px          │  ← STATUSBAR_PART
 *  └──────────────────────────────────────────────────┘
 *
 *  精确尺寸:
 *    ACTIVITYBAR_WIDTH = 48px
 *    TITLEBAR_HEIGHT   = 35px
 *    STATUSBAR_HEIGHT  = 22px
 *    PANEL_TITLE       = 35px
 *    TAB_HEIGHT        = 35px
 *    SASH_SIZE         = 4px
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { usePlugins } from "@/composables/usePlugins"
import { useShortcuts } from "@/composables/useShortcuts"
import { useIDEStore } from "@/stores/useIDEStore"
import { useKeybindingStore } from "@/stores/useKeybindingStore"
import MenuBar from "@/components/ide/MenuBar.vue"
import ActivityBar from "@/components/ide/ActivityBar.vue"
import Sidebar from "@/components/ide/Sidebar.vue"
import EditorArea from "@/components/ide/EditorArea.vue"
import RightPanel from "@/components/ide/RightPanel.vue"
import StatusBar from "@/components/ide/StatusBar.vue"
import GlobalSearch from "@/components/ide/GlobalSearch.vue"
import QuickOpen from "@/components/ide/QuickOpen.vue"
import CommandPalette from "@/components/ide/CommandPalette.vue"
import SettingsPanel from "@/components/ide/SettingsPanel.vue"
import NotificationToast from "@/components/ide/NotificationToast.vue"

const store = useIDEStore()
const router = useRouter()
const {
  isCommandPaletteVisible,
  toggleCommandPalette,
  on: onCommand,
} = useShortcuts()
const { activateAll: activatePlugins } = usePlugins()

// ── VSCode 全局键盘快捷键注册表 (Session 23: useKeybindingStore) ──
const kb = useKeybindingStore()
kb.registerCallbacks({
  toggleCommandPalette: () => toggleCommandPalette(true),
  toggleQuickOpen: () => { showQuickOpen.value = true },
  saveFile: async () => { await store.saveActiveFile() },
  closeActiveTab: () => { if (store.activeTabId) store.closeTab(store.activeTabId) },
  splitEditorRight: () => store.splitEditor("right"),
  focusFileExplorer: () => { store.layout.fileTreeVisible = true },
  toggleTerminal: () => {
    store.rightPanelView = "terminal"
    store.layout.rightPanelVisible = !store.layout.rightPanelVisible
  },
  toggleSidebar: () => { store.layout.fileTreeVisible = !store.layout.fileTreeVisible },
  toggleBottomPanel: () => { store.layout.rightPanelVisible = !store.layout.rightPanelVisible },
  toggleGlobalSearch: () => { store.showGlobalSearch = !store.showGlobalSearch },
  newUntitledFile: () => store.createUntitledTab(),
  /** 🔥 Testing Panel shortcut (Ctrl+Shift+T) */
  focusTesting: () => {
    store.activeActivityItem = "testing"
    store.layout.fileTreeVisible = true
  },
  /** 🔥 Extensions shortcut (Ctrl+Shift+X) */
  focusExtensions: () => {
    store.activeActivityItem = "extensions"
    store.layout.fileTreeVisible = true
  },
})

// Zen Mode: Ctrl+K Z
kb.register("Ctrl+K Z", toggleZenMode, "global", 10)

// ── IDE commands (CommandPalette) ──
onCommand("file.new", () => store.createUntitledTab())
onCommand("file.save", async () => { await store.saveActiveFile() })
onCommand("file.saveAll", async () => { await store.saveAllFiles() })
onCommand("file.closeEditor", () => { if (store.activeTabId) store.closeTab(store.activeTabId) })
onCommand("edit.findInFiles", () => { store.showGlobalSearch = true })
onCommand("nav.quickOpen", () => { showQuickOpen.value = true })
onCommand("view.toggleSidebar", () => { store.layout.fileTreeVisible = !store.layout.fileTreeVisible })
onCommand("view.togglePanel", () => { store.layout.rightPanelVisible = !store.layout.rightPanelVisible })
onCommand("terminal.toggle", () => {
  store.rightPanelView = "terminal"
  store.layout.rightPanelVisible = !store.layout.rightPanelVisible
})
onCommand("ai.chatPanel", () => {
  store.rightPanelView = "chat"
  store.layout.rightPanelVisible = true
})
onCommand("view.resetLayout", () => { store.resetLayout() })
onCommand("view.zenMode", () => { toggleZenMode() })
onCommand("preferences.openKeybindings", () => { router.push("/keybindings") })
onCommand("preferences.openSettings", () => { showSettings.value = true })

// Zen Mode 快捷键: Ctrl+K Z
onCommand("view.exitZenMode", () => { exitZenMode() })

const showSettings = ref(false)
const showQuickOpen = ref(false)
const zenMode = ref(false)

/** VSCode Zen Mode: 隐藏所有面板，只留编辑器 */
function toggleZenMode(): void {
  zenMode.value = !zenMode.value
}
function exitZenMode(): void {
  zenMode.value = false
}

// Zen Mode 时 Esc 退出
function onZenKeydown(e: KeyboardEvent): void {
  if (e.key === "Escape" && zenMode.value) {
    e.preventDefault()
    exitZenMode()
  }
}
watch(zenMode, (v) => {
  if (v) window.addEventListener("keydown", onZenKeydown)
  else window.removeEventListener("keydown", onZenKeydown)
})

function onCommandExecute(cmdId: string): void {
  if (cmdId === "settings.open") showSettings.value = true
  if (cmdId === "view.zenMode") toggleZenMode()
}

onMounted(async () => {
  try { await activatePlugins() } catch (e) { console.warn("[CodeBuddy] Plugin activation:", e) }
  await store.refreshGitStatus()
  store.addOutputLine(`[信息] CodeBuddy IDE v0.1.0 已启动`)
  if (store.workspaceRoot) store.addOutputLine(`[信息] 工作区: ${store.workspaceRoot}`)
  console.log("%c[CodeBuddy IDE] Ready", "color:#007ACC;font-weight:bold;font-size:14px")
})
</script>

<template>
  <RouterView v-if="$route.path === '/login'" />
  <!-- VSCode Workbench Shell -->
  <div v-else class="workbench h-full w-full flex flex-col overflow-hidden select-none"
    style="background: var(--color-ide-bg);">

    <!-- ═══ TitleBar (VSCode: titlebarPart, h=35px) ═══ -->
    <MenuBar v-if="store.layout.menuBarVisible && !zenMode" @open-settings="showSettings = true" />

    <!-- ═══ Middle: ActivityBar + Sidebar + Editor + AuxBar (HORIZONTAL) ═══ -->
    <div class="flex-1 flex overflow-hidden min-h-0">
      <!-- 🔥 ActivityBar — VS Code activitybarPart (48px left, always visible) -->
      <ActivityBar v-if="!zenMode && store.layout.activityBarVisible" />
      <!-- 🔥 Sidebar — 内容面板 (资源管理器/搜索/SCM/扩展…) -->
      <Sidebar v-if="!zenMode" />
      <!-- Editor Area (flex-1) — Zen Mode 全屏 -->
      <EditorArea class="flex-1 min-w-0" :class="{ 'zen-editor': zenMode }" />
      <!-- Right Panel (AuxBar) — Zen Mode 隐藏 -->
      <RightPanel v-if="!zenMode" />
    </div>

    <!-- ═══ StatusBar (VSCode: statusbarPart, h=22px) — Zen Mode 隐藏 ═══ -->
    <StatusBar v-if="store.layout.statusBarVisible && !zenMode" />

    <!-- ═══ Overlays ═══ -->
    <!-- Zen Mode indicator -->
    <div v-if="zenMode" class="fixed bottom-4 right-4 z-[999] px-3 py-1.5 rounded-md text-[12px] pointer-events-none transition-all duration-500"
      style="background: rgba(0,0,0,0.6); color: #CCCCCC; backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.05);">
      Zen 模式 · <kbd class="px-1 py-0.5 rounded text-[10px]" style="background: rgba(255,255,255,0.1);">Esc</kbd> 退出
    </div>
    <GlobalSearch :visible="store.showGlobalSearch" @close="store.showGlobalSearch = false" />
    <QuickOpen :visible="showQuickOpen" @close="showQuickOpen = false" />
    <CommandPalette
      :visible="isCommandPaletteVisible"
      @update:visible="(v: boolean) => { isCommandPaletteVisible = v; if (!v) toggleCommandPalette(false) }"
      @execute="onCommandExecute"
    />
    <SettingsPanel :visible="showSettings" @update:visible="showSettings = $event" />

    <!-- Notifications -->
    <NotificationToast />
  </div>
</template>

<style scoped>
/* workbench contain moved to global index.css */
</style>
