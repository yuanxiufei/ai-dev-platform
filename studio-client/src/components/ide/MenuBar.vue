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
import { onMounted, onUnmounted, ref, unref } from "vue"
import { useRouter } from "vue-router"
import { useIDEStore } from "@/stores/useIDEStore"
import type { MenuItem } from "@/types/ide"

const router = useRouter()
const store = useIDEStore()
const openMenu = ref<string | null>(null)
const menuRef = ref<HTMLElement | null>(null)

const menus = ref<{ id: string; label: string; items: MenuItem[] }[]>([
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
      { label: "在文件中查找", shortcut: "Ctrl+Shift+F" },
    ],
  },
  {
    id: "view", label: "查看",
    items: [
      { label: "命令面板...", shortcut: "Ctrl+Shift+P" },
      { separator: true },
      { label: "资源管理器", shortcut: "Ctrl+Shift+E", checked: store.activeActivityItem === "explorer", action: () => (store.activeActivityItem = "explorer") },
      { label: "搜索", shortcut: "Ctrl+Shift+F", action: () => { store.activeActivityItem = "search"; store.toggleGlobalSearch() } },
      { label: "源代码管理", shortcut: "Ctrl+Shift+G", checked: store.activeActivityItem === "git", action: () => (store.activeActivityItem = "git") },
      { label: "运行和调试", action: () => (store.activeActivityItem = "debug") },
      { label: "扩展", action: () => (store.activeActivityItem = "extensions") },
      { separator: true },
      { label: "终端", shortcut: "Ctrl+`", action: () => { store.rightPanelView = "terminal"; store.layout.rightPanelVisible = true } },
      { label: "侧边栏可见性", shortcut: "Ctrl+B", action: () => (store.layout.fileTreeVisible = !store.layout.fileTreeVisible) },
    ],
  },
  {
    id: "studio", label: "Studio",
    items: [
      { label: "AI 对话", shortcut: "\u21E7\u2318C", action: () => router.push("/chat") },
      { separator: true },
      { label: "项目管理", action: () => router.push("/projects") },
      { label: "模板市场", action: () => router.push("/templates") },
      { label: "Standalone 面板", action: () => router.push("/standalone") },
      { separator: true },
      { label: "知识库", action: () => router.push("/knowledge") },
      { label: "知识图谱", action: () => router.push("/knowledge-graph") },
      { label: "长期记忆", action: () => router.push("/memory") },
      { separator: true },
      { label: "工具浏览器", action: () => router.push("/tools") },
      { label: "MCP 设置", action: () => router.push("/mcp") },
      { label: "技能管理", action: () => router.push("/skills") },
      { label: "插件市场", action: () => router.push("/plugins") },
      { separator: true },
      { label: "AI 图片生成", action: () => router.push("/image-gen") },
      { label: "语音合成", action: () => router.push("/voice") },
      { label: "截图转代码", action: () => router.push("/screenshot-to-code") },
      { separator: true },
      { label: "模型竞技场", action: () => router.push("/arena") },
      { label: "Agent 管理", action: () => router.push("/agents") },
      { label: "Rules 配置", action: () => router.push("/rules") },
      { separator: true },
      { label: "数据分析", action: () => router.push("/analytics") },
      { label: "存储管理", action: () => router.push("/storage") },
      { label: "链路追踪", action: () => router.push("/trajectory") },
      { label: "OpenAPI 发现", action: () => router.push("/openapi") },
      { label: "Webhooks", action: () => router.push("/webhooks") },
      { label: "集成管理", action: () => router.push("/integrations") },
    ],
  },
  { id: "help", label: "帮助", items: [
    { label: "欢迎" }, { label: "文档" },
    { label: "键盘快捷方式", shortcut: "Ctrl+K Ctrl+S" },
    { separator: true }, { label: "关于 CodeBuddy IDE" },
  ]},
])

function toggleMenu(id: string): void { openMenu.value = openMenu.value === id ? null : id }
function closeMenus(): void { openMenu.value = null }
function handleItemClick(item: MenuItem): void { if (item.action) item.action(); closeMenus() }

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
        :style="[{ paddingLeft:'10px', paddingRight:'10px', display:'flex', alignItems:'center', height:'100%', borderRadius:'3px', fontSize:'14px', border:'none', cursor:'default' },
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
          style="position:absolute; top:100%; left:0; min-width:220px; padding-top:4px; padding-bottom:4px; z-index:100; background: var(--color-ide-surface); border: 1px solid var(--color-ide-border); border-radius: 3px; box-shadow: var(--shadow-md);"
          @click.stop>
          <template v-for="(item, idx) in menu.items" :key="idx">
            <hr v-if="item.separator" style="margin: 4px 0; border: none; border-top: 1px solid var(--color-ide-border);" />
            <button v-else
              :disabled="item.disabled"
              :style="{ width:'100%', textAlign:'left', paddingLeft:'16px', paddingRight:'16px', paddingTop:'6px', paddingBottom:'6px', display:'flex', justifyContent:'space-between', alignItems:'center', gap:'32px', fontSize:'14px', lineHeight:'28px', background:'transparent', color: item.checked ? 'var(--color-ide-accent)' : 'var(--color-ide-text)', cursor: item.disabled ? 'default' : 'pointer', opacity: item.disabled ? 0.4 : 1 }"
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
      <button
        style="padding-left: 10px; padding-right: 10px; margin-left: 4px; margin-right: 4px; height: 100%; display: flex; align-items: center; border-radius: 3px; border: none; background: transparent; color: var(--color-ide-text-dim); font-size: 14px; cursor: default;"
        @mouseover="(e) => { e.currentTarget.style.color = 'var(--color-ide-text)'; e.currentTarget.style.background = 'var(--color-ide-surface-hover)' }"
        @mouseout="(e) => { e.currentTarget.style.color = 'var(--color-ide-text-dim)'; e.currentTarget.style.background = 'transparent' }"
        @click="store.rightPanelView = 'chat'; store.layout.rightPanelVisible = true">
        AI 助手
      </button>
    </div>
  </div>
</template>
