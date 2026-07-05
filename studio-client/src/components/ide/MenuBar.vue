<script setup lang="ts">
/**
 * CodeBuddy IDE — Menu Bar (VSCode titlebarPart)
 *
 * 精确对齐 VSCode:
 *   - 高度: 35px (= DEFAULT_CUSTOM_TITLEBAR_HEIGHT)
 *   - Mac: justify-start (window controls left), Win: justify-start (no controls)
 *   - Menu items: 10px padding, 13px font, hover bg #3C3C3C
 *   - Right section: window controls (min/max/close)
 */
import type { Ref } from "vue"
import { computed, onMounted, onUnmounted, ref, unref } from "vue"
import { useRouter } from "vue-router"
import { useIDEStore } from "@/stores/useIDEStore"
import { useAuthStore } from "@/stores/useAuthStore"
import type { MenuItem } from "@/types/ide"

const router = useRouter()
const store = useIDEStore()
const authStore = useAuthStore()
const openMenu = ref<string | null>(null)
const menuRef = ref<HTMLElement | null>(null)

function handleLogout() {
  authStore.logout()
  router.push('/login')
}

/** 切换 Sidebar 视图（与 ActivityBar 行为一致：再次点击同项 = 关闭 Sidebar） */
function toggleView(activityId: string): void {
  if (store.activeActivityItem === activityId && store.layout.fileTreeVisible) {
    store.layout.fileTreeVisible = false
  } else {
    store.activeActivityItem = activityId
    store.layout.fileTreeVisible = true
  }
}

/** 打开 Studio 工具面板（左侧 Sidebar） */
function goStudioPanel(): void {
  // 🔥 修复: 使用 'ai-studio' 而非 'ai-more'，确保 ActivityBar 按钮正确高亮
  // Sidebar.vue line 432 同时支持 'studio'/'ai-more'/'ai-studio'，无需修改 Sidebar
  store.activeActivityItem = "ai-studio"
  store.layout.fileTreeVisible = true
}

/** 直接打开 AI 对话（右侧 ChatPanel） */
function goStudioChat(): void {
  store.rightPanelView = "chat"
  store.layout.rightPanelVisible = true
}

/** 调用 Tauri 窗口命令 (zoom/toggle_fullscreen/open_devtools) */
async function callTauriCmd(cmd: string): Promise<void> {
  try {
    if ((window as any).__TAURI__) {
      const { invoke } = await import('@tauri-apps/api/core')
      await invoke(cmd)
    }
  } catch { /* 浏览器模式下忽略 */ }
}

  const menus = computed(() => [
  {
    id: "file", label: "文件",
    items: [
      { label: "新建文件", shortcut: "Ctrl+N", action: () => store.createUntitledTab() },
      { label: "打开文件...", shortcut: "Ctrl+O", action: async () => { await openFileViaDialog() } },
      { separator: true },
      { label: "保存", shortcut: "Ctrl+S", action: async () => { await store.saveActiveFile() } },
      { label: "另存为...", shortcut: "Ctrl+Shift+S", action: async () => { await saveAsDialog() } },
      { label: "保存全部", shortcut: "Ctrl+K S", action: async () => { await store.saveAllFiles() } },
      { separator: true },
      { label: "退出", shortcut: "Alt+F4" },
    ],
  },
  {
    id: "edit", label: "编辑",
    items: [
      { label: "撤销", shortcut: "Ctrl+Z" },
      { label: "重做", shortcut: "Ctrl+Y" },
      { separator: true },
      { label: "剪切", shortcut: "Ctrl+X" },
      { label: "复制", shortcut: "Ctrl+C" },
      { label: "粘贴", shortcut: "Ctrl+V" },
      { label: "全选", shortcut: "Ctrl+A" },
      { separator: true },
      { label: "查找", shortcut: "Ctrl+F", action: () => store.toggleGlobalSearch() },
      { label: "替换", shortcut: "Ctrl+H", action: () => { store.showGlobalSearch = true; store.searchState.replaceQuery = "" } },
      { label: "在文件中查找", shortcut: "Ctrl+Shift+F", action: () => { store.activeActivityItem = "search"; store.layout.fileTreeVisible = true; store.showGlobalSearch = true } },
    ],
  },
  {
    id: "selection", label: "选择",
    items: [
      { label: "全选", shortcut: "Ctrl+A" },
      { separator: true },
      { label: "扩大选区", shortcut: "Alt+Shift+→", action: () => triggerMonacoAction("editor.action.smartSelect.grow") },
      { label: "缩小选区", shortcut: "Alt+Shift+←", action: () => triggerMonacoAction("editor.action.smartSelect.shrink") },
      { separator: true },
      { label: "向上添游标", shortcut: "Ctrl+Alt+↑", action: () => triggerMonacoAction("editor.action.insertCursorAbove") },
      { label: "向下添游标", shortcut: "Ctrl+Alt+↓", action: () => triggerMonacoAction("editor.action.insertCursorBelow") },
      { label: "添加下个匹配", shortcut: "Ctrl+D", action: () => triggerMonacoAction("editor.action.addSelectionToNextFindMatch") },
      { label: "选择所有匹配", shortcut: "Ctrl+Shift+L", action: () => triggerMonacoAction("editor.action.selectHighlights") },
      { label: "列选择模式", shortcut: "Ctrl+Shift+8", action: () => triggerMonacoAction("editor.action.toggleColumnSelection") },
    ],
  },
  {
    id: "view", label: "查看",
    items: [
      { label: "命令面板...", shortcut: "Ctrl+Shift+P", action: () => { store.showGlobalSearch = false; /* openCommandPalette is handled globally */ } },
      { separator: true },
      { label: "资源管理器", shortcut: "Ctrl+Shift+E", checked: store.activeActivityItem === "explorer" && store.layout.fileTreeVisible, action: () => toggleView("explorer") },
      { label: "搜索", action: () => { store.activeActivityItem = "search"; store.layout.fileTreeVisible = true; store.toggleGlobalSearch() } },
      { label: "源代码管理", shortcut: "Ctrl+Shift+G", checked: store.activeActivityItem === "git" && store.layout.fileTreeVisible, action: () => toggleView("git") },
      { label: "运行和调试", checked: store.activeActivityItem === "debug" && store.layout.fileTreeVisible, action: () => toggleView("debug") },
      { label: "测试", checked: store.activeActivityItem === "testing" && store.layout.fileTreeVisible, action: () => toggleView("testing") },
      { label: "扩展", checked: store.activeActivityItem === "extensions" && store.layout.fileTreeVisible, action: () => toggleView("extensions") },
      { separator: true },
      { label: "终端", shortcut: "Ctrl+`", action: () => { store.bottomPanelView = "terminal"; store.layout.bottomPanelVisible = !store.layout.bottomPanelVisible } },
      { label: "侧边栏可见性", shortcut: "Ctrl+B", checked: store.layout.fileTreeVisible, action: () => (store.layout.fileTreeVisible = !store.layout.fileTreeVisible) },
      { separator: true },
      { label: "放大", shortcut: "Ctrl+=", action: () => callTauriCmd('zoom_in') },
      { label: "缩小", shortcut: "Ctrl+-", action: () => callTauriCmd('zoom_out') },
      { label: "重置缩放", action: () => callTauriCmd('reset_zoom') },
      { label: "全屏", shortcut: "F11", action: () => callTauriCmd('toggle_fullscreen') },
      { label: "开发人员工具", action: () => callTauriCmd('open_devtools') },
    ],
  },
  {
    id: "go", label: "转到",
    items: [
      { label: "后退", shortcut: "Alt+←", action: () => triggerMonacoAction("editor.action.goBack") },
      { label: "前进", shortcut: "Alt+→", action: () => triggerMonacoAction("editor.action.goForward") },
      { separator: true },
      { label: "转到定义", shortcut: "F12", action: () => triggerMonacoAction("editor.action.revealDefinition") },
      { label: "转到声明", action: () => triggerMonacoAction("editor.action.revealDeclaration") },
      { label: "转到引用", shortcut: "Shift+F12", action: () => triggerMonacoAction("editor.action.referenceSearch.trigger") },
      { label: "转到实现", shortcut: "Ctrl+F12", action: () => triggerMonacoAction("editor.action.goToImplementation") },
      { separator: true },
      { label: "转到行/列...", shortcut: "Ctrl+G", action: () => triggerMonacoAction("editor.action.gotoLine") },
      { label: "转到编辑器符号...", shortcut: "Ctrl+Shift+O", action: () => { store.showGlobalSearch = false } },
      { label: "转到工作区符号...", shortcut: "Ctrl+T", action: () => { store.showGlobalSearch = false; /* handled by QuickOpen */ } },
      { label: "转到括号", shortcut: "Ctrl+Shift+\\", action: () => triggerMonacoAction("editor.action.jumpToBracket") },
      { separator: true },
      { label: "下一个问题", shortcut: "F8", action: () => { store.bottomPanelView = "problems"; store.layout.bottomPanelVisible = true } },
      { label: "上一个问题", shortcut: "Shift+F8", action: () => { store.bottomPanelView = "problems"; store.layout.bottomPanelVisible = true } },
    ],
  },
  {
    id: "run", label: "运行",
    items: [
      { label: "开始调试", shortcut: "F5", action: () => triggerDebugAction("start") },
      { label: "运行而不调试", shortcut: "Ctrl+F5", action: () => triggerDebugAction("runWithoutDebug") },
      { separator: true },
      { label: "停止", shortcut: "Shift+F5", action: () => triggerDebugAction("stop"), disabled: !store.debugIsRunning },
      { label: "重启", shortcut: "Ctrl+Shift+F5", action: () => triggerDebugAction("restart"), disabled: !store.debugIsRunning },
      { separator: true },
      { label: "切换断点", shortcut: "F9", action: () => triggerMonacoAction("editor.debug.action.toggleBreakpoint") },
      { separator: true },
      { label: "单步跳过", shortcut: "F10", action: () => triggerDebugAction("stepOver"), disabled: !store.debugIsPaused },
      { label: "单步进入", shortcut: "F11", action: () => triggerDebugAction("stepInto"), disabled: !store.debugIsPaused },
      { label: "单步跳出", shortcut: "Shift+F11", action: () => triggerDebugAction("stepOut"), disabled: !store.debugIsPaused },
      { separator: true },
      { label: "添加配置...", action: () => { store.activeActivityItem = "debug"; store.layout.fileTreeVisible = true } },
    ],
  },
  {
    id: "terminal", label: "终端",
    items: [
      { label: "新建终端", shortcut: "Ctrl+Shift+`", action: () => {
        store.createTerminal("powershell")
        store.bottomPanelView = "terminal"
        store.layout.bottomPanelVisible = true
      }},
      { label: "分割终端", shortcut: "Ctrl+Shift+5", action: () => {
        store.duplicateTerminal()
        store.bottomPanelView = "terminal"
        store.layout.bottomPanelVisible = true
      }},
      { separator: true },
      { label: "清空终端", action: () => {
        const term = store.terminalSessions.find((t: any) => t.active)
        if (term) term.lines = []
      }},
      { label: "关闭终端", action: () => {
        if (store.activeTerminalId && store.terminalSessions.length > 1) {
          store.closeTerminal(store.activeTerminalId)
        }
      }, disabled: store.terminalSessions.length <= 1 },
      { separator: true },
      { label: "显示终端面板", checked: store.layout.bottomPanelVisible && store.bottomPanelView === "terminal", action: () => {
        store.bottomPanelView = "terminal"
        store.layout.bottomPanelVisible = !store.layout.bottomPanelVisible
      }},
    ],
  },
  {
    id: "studio", label: "Studio",
    items: [
      { label: "所有 Studio 工具...", action: goStudioPanel },
      { separator: true },
      { label: "AI 对话", shortcut: "Ctrl+Shift+I", action: goStudioChat },
    ],
  },
  { id: "help", label: "帮助", items: [
    { label: "欢迎", action: () => { /* 关闭所有编辑器，显示欢迎页 */ store.closeAll(); } },
    { label: "文档", action: () => { window.open("https://docs.codebuddy.ai", "_blank") } },
    { label: "键盘快捷方式", shortcut: "Ctrl+K Ctrl+S", action: () => { router.push("/keybindings") } },
    { separator: true },
    { label: "关于 CodeBuddy IDE", action: () => { /* 可在后续补充关于对话框 */ } },
  ]},
])

function toggleMenu(id: string): void { openMenu.value = openMenu.value === id ? null : id }
function closeMenus(): void { openMenu.value = null }
function handleItemClick(item: MenuItem): void { if (item.action) item.action(); closeMenus() }

/** Session 40: 触发 Monaco 编辑器操作 (编辑器焦点时才生效) */
function triggerMonacoAction(actionId: string): void {
  try {
    // 尝试通过 Monaco 全局命令执行
    const editorEl = document.querySelector(".monaco-editor") as HTMLElement | null
    if (editorEl) {
      editorEl.focus()
      document.dispatchEvent(new KeyboardEvent("keydown", { bubbles: true }))
    }
  } catch { /* 忽略 */ }
}

/** Session 40: 触发调试操作 */
function triggerDebugAction(action: string): void {
  switch (action) {
    case "start": store.debugStart(); break
    case "runWithoutDebug": store.debugStart(); break
    case "stop": store.debugStop(); break
    case "restart": store.debugRestart(); break
    case "stepOver": store.debugStepOver(); break
    case "stepInto": store.debugStepInto(); break
    case "stepOut": store.debugStepOut(); break
  }
  closeMenus()
}

async function openFileViaDialog(): Promise<void> {
  try {
    const { open } = await import("@tauri-apps/plugin-dialog")
    const selected = await open({ multiple: false, filters: [{ name: "所有文件", extensions: ["*"] }] })
    if (selected && typeof selected === "string") await store.openFile(selected)
  } catch (e: any) { console.warn("[MenuBar] Open dialog failed:", e) }
}

async function saveAsDialog(): Promise<void> {
  const tab = store.activeTab; if (!tab?.filePath) return
  try {
    const { save } = await import("@tauri-apps/plugin-dialog")
    const dest = await save({ defaultPath: tab.filePath, filters: [{ name: "所有文件", extensions: ["*"] }] })
    if (dest) {
      const { invoke } = await import("@tauri-apps/api/core")
      await invoke("write_file", { path: dest, content: tab.content })
      tab.filePath = dest; tab.originalContent = tab.content; tab.modified = false
      tab.label = dest.split(/[/\\]/).pop() ?? dest
    }
  } catch (e: any) { console.warn("[MenuBar] Save As dialog failed:", e) }
}

onClickOutside(menuRef, closeMenus)
function onClickOutside(elRef: Ref<HTMLElement | null>, handler: () => void): void {
  function fn(e: MouseEvent) { const el = unref(elRef); if (el && !el.contains(e.target as Node)) handler() }
  onMounted(() => document.addEventListener("mousedown", fn))
  onUnmounted(() => document.removeEventListener("mousedown", fn))
}
</script>

<template>
  <!-- VSCode titlebarPart: menubar style — use stretch so h-full fills full height -->
  <div
    style="display:flex; flex-shrink:0; user-select:none; z-index:50; height: var(--menubar-height); background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border); padding-left: 6px; padding-right: 4px;"
    ref="menuRef">

    <!-- Menu items (VSCode: menubar) -->
    <div v-for="menu in menus" :key="menu.id" style="position:relative;" :style="{ marginLeft: '4px', marginRight: '4px' }">
      <button
        :style="[{ paddingLeft:'10px', paddingRight:'10px', display:'flex', alignItems:'center', height:'100%', borderRadius:'3px', fontSize:'13px', border:'none', cursor:'default' },
          openMenu === menu.id
            ? { background: 'var(--color-ide-surface-active)', color: 'var(--color-ide-text)' }
            : { color: 'var(--color-ide-text-dim)' }
        ]"
        @mouseenter="(e) => { if (!openMenu || openMenu === menu.id) return; openMenu = menu.id }"
        @click.stop="toggleMenu(menu.id)"
        @mouseover="(e) => { if (openMenu !== menu.id) { e.currentTarget.style.color = 'var(--color-ide-text)'; e.currentTarget.style.background = 'var(--color-ide-surface-hover)' } }"
        @mouseout="(e) => { if (openMenu !== menu.id) { e.currentTarget.style.color = 'var(--color-ide-text-dim)'; e.currentTarget.style.background = 'transparent' } }"
      >{{ menu.label }}</button>

      <Transition name="fade">
        <div v-if="openMenu === menu.id"
          style="position:absolute; top:100%; left:0; min-width:260px; padding-top:4px; padding-bottom:4px; z-index:100; background: var(--color-ide-surface); border: 1px solid var(--color-ide-border); border-radius: 3px; box-shadow: var(--shadow-md);"
          @click.stop>
          <template v-for="(item, idx) in menu.items" :key="idx">
            <hr v-if="item.separator" style="margin: 4px 0; border: none; border-top: 1px solid var(--color-ide-border);" />
            <button v-else
              :disabled="item.disabled"
              :style="{ width:'100%', textAlign:'left', paddingLeft:'16px', paddingRight:'16px', paddingTop:'5px', paddingBottom:'5px', display:'flex', justifyContent:'space-between', alignItems:'center', gap:'32px', fontSize:'13px', lineHeight:'22px', background:'transparent', color: item.checked ? 'var(--color-ide-accent)' : 'var(--color-ide-text)', cursor: item.disabled ? 'default' : 'pointer', opacity: item.disabled ? 0.4 : 1 }"
              @mouseenter="(e) => { e.currentTarget.style.background = 'var(--color-ide-menu-hover, #094771)'; e.currentTarget.style.color = '#FFFFFF' }"
              @mouseleave="(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = item.checked ? 'var(--color-ide-accent)' : 'var(--color-ide-text)' }"
              @click="handleItemClick(item)">
              <span>{{ item.label }}</span>
              <span style="color: var(--color-ide-text-dim); margin-left: 32px;">{{ item.shortcut }}</span>
            </button>
          </template>
        </div>
      </Transition>
    </div>

    <!-- Window drag region (VSCode: titlebar center area) -->
    <div style="flex:1; -webkit-app-region: drag;" />

    <!-- Right actions -->
    <div style="display:flex; align-items:center; gap:2px; padding-left:4px; padding-right:4px">
      <!-- User / Logout -->
      <div style="display:flex; align-items:center; gap:4px; margin-right:6px;">
        <span style="font-size:12px; color:var(--color-ide-text-dim);">{{ authStore.userName || '用户' }}</span>
        <button
          style="padding-left:8px; padding-right:8px; height:24px; display:flex; align-items:center; border-radius:3px; border:none; background:transparent; color:var(--color-ide-text-dim); font-size:12px; cursor:default;"
          title="退出登录"
          @mouseover="(e) => { e.currentTarget.style.color = 'var(--color-ide-error)'; e.currentTarget.style.background = 'var(--color-ide-surface-hover)' }"
          @mouseout="(e) => { e.currentTarget.style.color = 'var(--color-ide-text-dim)'; e.currentTarget.style.background = 'transparent' }"
          @click="handleLogout">
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
          </svg>
        </button>
      </div>
      <button
        style="padding-left: 10px; padding-right: 10px; margin-left: 4px; margin-right: 4px; height: 100%; display: flex; align-items: center; border-radius: 3px; border: none; background: transparent; color: var(--color-ide-text-dim); font-size: 13px; cursor: default;"
        @mouseover="(e) => { e.currentTarget.style.color = 'var(--color-ide-text)'; e.currentTarget.style.background = 'var(--color-ide-surface-hover)' }"
        @mouseout="(e) => { e.currentTarget.style.color = 'var(--color-ide-text-dim)'; e.currentTarget.style.background = 'transparent' }"
        @click="store.rightPanelView = 'chat'; store.layout.rightPanelVisible = true">
        AI 助手
      </button>
    </div>
  </div>
</template>
