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
import { onMounted, onUnmounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { usePlugins } from "@/composables/usePlugins"
import { useShortcuts, shortcutManager } from "@/composables/useShortcuts"
import { useIDEStore } from "@/stores/useIDEStore"
import { useKeybindingStore } from "@/stores/useKeybindingStore"
import MenuBar from "@/components/ide/MenuBar.vue"
import ActivityBar from "@/components/ide/ActivityBar.vue"
import Sidebar from "@/components/ide/Sidebar.vue"
import EditorArea from "@/components/ide/EditorArea.vue"
import RightPanel from "@/components/ide/RightPanel.vue"
import Terminal from "@/components/ide/Terminal.vue"
import BottomOutputPanel from "@/components/ide/BottomOutputPanel.vue"
import ProblemsPanel from "@/components/ide/ProblemsPanel.vue"
import TasksPanel from "@/components/ide/TasksPanel.vue"
import StatusBar from "@/components/ide/StatusBar.vue"
import GlobalSearch from "@/components/ide/GlobalSearch.vue"
import QuickOpen from "@/components/ide/QuickOpen.vue"
import CommandPalette from "@/components/ide/CommandPalette.vue"
import SettingsPanel from "@/components/ide/SettingsPanel.vue"
import NotificationToast from "@/components/ide/NotificationToast.vue"
import InputDialogHost from "@/components/InputDialogHost.vue"
import { setupWidgetNavigationKeyboard, teardownWidgetNavigationKeyboard } from "@/composables/useWidgetNavigation"
import { toggleSyncScroll as _toggleSyncScroll } from "@/composables/useSyncScroll"
import { useWorkspaceFinder } from "@/composables/useWorkspaceFinder"
import { useNotificationStore } from "@/stores/useNotificationStore"
import { useImageCarouselStore, isMediaFile } from "@/stores/useImageCarouselStore"
import ImageCarousel from "@/components/ide/ImageCarousel.vue"
import ExternalUriOpenerDialog from "@/components/ide/ExternalUriOpenerDialog.vue"
import { openUrl } from "@/composables/useExternalUriOpener"

const store = useIDEStore()
const router = useRouter()

// Session 58: Workspace Finder state
let _workspaceFinder: ReturnType<typeof useWorkspaceFinder> | null = null
function _onWorkspaceFound(e: CustomEvent) {
  const { files } = e.detail
  if (!files || files.length === 0) return
  const notifStore = useNotificationStore()
  const names = files.map((f: any) => f.name).join("、")
  notifStore.info(
    `检测到工作区文件: ${names}`,
    {
      detail: "此文件夹包含 .code-workspace 文件，是否打开？",
      source: "工作区发现",
      actions: files.map((f: any) => ({
        label: `打开 ${f.name}`,
        action: () => {
          store.setWorkspaceRoot(f.path)
          _workspaceFinder?.dismissRoot(store.workspaceRoot.value)
        },
      })),
      autoDismiss: 0,
    },
  )
}
const {
  isCommandPaletteVisible,
  toggleCommandPalette,
  on: onCommand,
} = useShortcuts()
const { activateAll: activatePlugins } = usePlugins()

// ── VSCode 全局键盘快捷键注册表 (Session 23: useKeybindingStore) ──
const kb = useKeybindingStore()
const imageCarStore = useImageCarouselStore()
kb.registerCallbacks({
  toggleCommandPalette: () => toggleCommandPalette(true),
  toggleQuickOpen: () => { quickOpenSymbolMode.value = false; showQuickOpen.value = true },
  toggleSymbolSearch: () => { quickOpenSymbolMode.value = true; showQuickOpen.value = true },
  saveFile: async () => {
    /** Session 47: Format on Save — 保存前先格式化 */
    try {
      const raw = localStorage.getItem("ide_editor_settings_v2")
      const settings = raw ? JSON.parse(raw) : null
      if (settings?.formatOnSave !== false) {
        await (window as any).__formatActiveDocument?.()
        // 等待格式化完成 + content 同步
        await new Promise(r => setTimeout(r, 50))
      }
    } catch { /* 静默处理 - 格式化失败不影响保存 */ }
    await store.saveActiveFile()
  },
  closeActiveTab: () => { if (store.activeTabId) store.closeTab(store.activeTabId) },
  splitEditorRight: () => store.splitEditor("right"),
  focusFileExplorer: () => { store.layout.fileTreeVisible = true },
  toggleTerminal: () => {
    store.bottomPanelView = "terminal"
    store.layout.bottomPanelVisible = !store.layout.bottomPanelVisible
  },
  toggleSidebar: () => { store.layout.fileTreeVisible = !store.layout.fileTreeVisible },
  toggleBottomPanel: () => { store.layout.bottomPanelVisible = !store.layout.bottomPanelVisible },
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
  /** 🔥 Session 35: Markdown Preview (Ctrl+Shift+V) */
  markdownPreview: () => {
    store.markdownPreviewVisible = !store.markdownPreviewVisible
  },
  /** Session 58: 同步滚动切换 (Ctrl+Shift+Alt+L) */
  toggleSyncScroll: () => _toggleSyncScroll(),
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
onCommand("view.toggleLockedScrolling", () => _toggleSyncScroll())
onCommand("view.openImageViewer", () => {
  const activeTab = store.activeTab
  if (activeTab?.filePath && isMediaFile(activeTab.label)) {
    imageCarStore.open(activeTab.filePath)
  } else {
    // 如果没有打开图片文件，提示用户
    const notifStore2 = useNotificationStore()
    notifStore2.info("请先在文件资源管理器中点击一个图片文件", { source: "图片查看器" })
  }
})
onCommand("terminal.toggle", () => {
  store.bottomPanelView = "terminal"
  store.layout.bottomPanelVisible = !store.layout.bottomPanelVisible
})
onCommand("ai.chatPanel", () => {
  store.rightPanelView = "chat"
  store.layout.rightPanelVisible = true
})
onCommand("view.resetLayout", () => { store.resetLayout() })
onCommand("view.zenMode", () => { toggleZenMode() })
onCommand("preferences.openKeybindings", () => { router.push("/keybindings") })
onCommand("preferences.openSettings", () => { store.showSettingsPanel = true })
onCommand("preferences.openUriOpenerSettings", () => { store.showSettingsPanel = true })

// Zen Mode 快捷键: Ctrl+K Z
onCommand("view.exitZenMode", () => { exitZenMode() })

// ── Bottom Panel Resize (Sash drag) — VSCode: panelPart 可拖拽高度 ──
let bottomPanelDragging = false
function onBottomPanelResizeStart(e: MouseEvent): void {
  e.preventDefault()
  bottomPanelDragging = true
  const startY = e.clientY
  const startHeight = store.layout.bottomPanelHeight

  function onMove(ev: MouseEvent): void {
    if (!bottomPanelDragging) return
    const delta = startY - ev.clientY  // 向上拖=增大面板
    store.layout.bottomPanelHeight = Math.max(80, Math.min(600, startHeight + delta))
  }

  function onUp(): void {
    bottomPanelDragging = false
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

const showQuickOpen = ref(false)
/** Session 48: QuickOpen 符号搜索模式 */
const quickOpenSymbolMode = ref(false)
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

/** 命令面板点击/回车执行命令 — 将 cmdId 路由到对应的 IDE 操作 */
function onCommandExecute(cmdId: string): void {
  // 直接路由: 无需通过 shortcutManager 重触发
  if (cmdId === "settings.open") store.showSettingsPanel = true
  else if (cmdId === "view.zenMode") toggleZenMode()
  // 回退: 走 shortcutManager.execute → 触发 onCommand() 注册的 handler
  else shortcutManager.execute(cmdId)
}

onMounted(async () => {
  try { await activatePlugins() } catch (e) { console.warn("[CodeBuddy] Plugin activation:", e) }
  await store.refreshGitStatus()
  store.addOutputLine(`[信息] CodeBuddy IDE v0.1.0 已启动`)
  if (store.workspaceRoot) store.addOutputLine(`[信息] 工作区: ${store.workspaceRoot}`)
  // Session 57: Widget 导航 (F6/Shift+F6)
  setupWidgetNavigationKeyboard()
  // Session 58: 工作区自动发现 (.code-workspace 文件)
  const workspaceFinder = useWorkspaceFinder(store.workspaceRoot, import.meta.env.VITE_API_BASE)
  workspaceFinder.start()
  // 监听 .code-workspace 文件发现事件
  window.addEventListener("ide:workspace-files-found", _onWorkspaceFound as EventListener)
  // Session 58: 全局 URL 打开器 (供 HTML/markdown 中的链接使用)
  ;(window as any).__openUrl = (url: string) => openUrl(url, import.meta.env.VITE_API_BASE)
  _workspaceFinder = workspaceFinder

  console.log("%c[CodeBuddy IDE] Ready", "color:#007ACC;font-weight:bold;font-size:14px")
})

onUnmounted(() => {
  teardownWidgetNavigationKeyboard()
  if (_workspaceFinder) _workspaceFinder.stop()
  window.removeEventListener("ide:workspace-files-found", _onWorkspaceFound as EventListener)
})
</script>

<template>
  <RouterView v-if="['/login', '/group-chat'].includes($route.path)" />
  <!-- VSCode Workbench Shell -->
  <div v-else class="workbench h-full w-full flex flex-col overflow-hidden select-none"
    style="background: var(--color-ide-bg);">

    <!-- ═══ TitleBar (VSCode: titlebarPart, h=35px) ═══ -->
    <MenuBar v-if="store.layout.menuBarVisible && !zenMode" @open-settings="store.showSettingsPanel = true" />

    <!-- ═══ Middle: ActivityBar + Sidebar + Editor + AuxBar + BottomPanel (HORIZONTAL) ═══ -->
    <div class="flex-1 flex overflow-hidden min-h-0">
      <!-- 🔥 ActivityBar — VS Code activitybarPart (48px left, always visible) -->
      <ActivityBar v-if="!zenMode && store.layout.activityBarVisible" />
      <!-- 🔥 Sidebar — 内容面板 (资源管理器/搜索/SCM/扩展…) -->
      <Sidebar v-if="!zenMode" />

      <!-- ═══ Center Column: Editor + Bottom Panel (VERTICAL) ═══ -->
      <div class="flex-1 flex flex-col min-w-0 min-h-0">
        <!-- Editor Area -->
        <EditorArea class="flex-1 min-h-0" :class="{ 'zen-editor': zenMode }" />

        <!-- ═══ Bottom Panel (终端/输出/问题) — VSCode: panelPart, 可拖拽调整高度 ═══ -->
        <template v-if="!zenMode && store.layout.bottomPanelVisible">
          <!-- Drag handle / Sash (4px draggable strip) -->
          <div
            class="shrink-0 relative group"
            style="height: 4px; background: transparent; cursor: row-resize;"
            @mousedown.prevent="onBottomPanelResizeStart"
          >
            <!-- Hover indicator line -->
            <div class="absolute inset-x-0 top-1/2 -translate-y-1/2 h-[1px] opacity-0 group-hover:opacity-100 transition-opacity"
              style="background: var(--color-ide-accent);" />
          </div>
          <!-- Panel body -->
          <div
            class="flex flex-col overflow-hidden"
            :style="{ height: store.layout.bottomPanelHeight + 'px', background: 'var(--color-ide-bg)', borderTop: '1px solid var(--color-ide-border)' }"
          >
            <!-- Panel Tab Bar (var(--panel-title-height)) -->
            <div class="flex items-center px-2 gap-1 shrink-0"
              style="height: var(--panel-title-height); background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border);">
              <button
                v-for="tab in [
                  { id: 'terminal', label: '终端' },
                  { id: 'output', label: '输出' },
                  { id: 'problems', label: '问题' },
                  { id: 'tasks', label: '任务' },
                ]" :key="tab.id"
                :class="['px-2 py-0.5 text-[12px] rounded-sm transition-colors cursor-pointer']"
                :style="store.bottomPanelView === tab.id
                  ? { color: 'var(--color-ide-text)', fontWeight: 500, background: 'var(--color-ide-surface)' }
                  : { color: 'var(--color-ide-text-dim)', opacity: 0.7 }"
                @click="store.bottomPanelView = tab.id as any"
              >{{ tab.label }}</button>
              <div class="flex-1" />
              <!-- Close button (终端操作按钮统一由 Terminal.vue 内部工具栏管理) -->
              <button class="p-1 rounded hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors cursor-pointer ml-1"
                title="关闭面板"
                @click="store.layout.bottomPanelVisible = false">
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
            <!-- Panel Content -->
            <div class="flex-1 overflow-hidden min-h-0">
              <Terminal v-if="store.bottomPanelView === 'terminal'" :embedded="true" />
              <BottomOutputPanel v-else-if="store.bottomPanelView === 'output'" />
              <ProblemsPanel v-else-if="store.bottomPanelView === 'problems'" />
              <TasksPanel v-else-if="store.bottomPanelView === 'tasks'" />
            </div>
          </div>
        </template>
      </div>

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
    <QuickOpen :visible="showQuickOpen" :force-symbol-mode="quickOpenSymbolMode" @close="showQuickOpen = false; quickOpenSymbolMode = false" />
    <CommandPalette
      :visible="isCommandPaletteVisible"
      @update:visible="(v: boolean) => { isCommandPaletteVisible = v; if (!v) toggleCommandPalette(false) }"
      @execute="onCommandExecute"
    />
    <SettingsPanel :visible="store.showSettingsPanel" @update:visible="store.showSettingsPanel = $event" />

    <!-- Notifications -->
    <NotificationToast />

    <!-- Image Carousel (Session 58: 图片/视频轮播查看器) -->
    <ImageCarousel />

    <!-- External URI Opener Dialog (Session 58: URL 打开器选择) -->
    <ExternalUriOpenerDialog />

    <!-- 🔥 全局输入对话框 (命令式 API) -->
    <InputDialogHost />
  </div>
</template>

<style scoped>
/* workbench contain moved to global index.css */
</style>
