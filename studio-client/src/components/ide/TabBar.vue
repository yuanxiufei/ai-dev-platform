<script setup lang="ts">
/**
 * CodeBuddy IDE — Tab Bar (VSCode multiEditorTabsControl)
 *
 * VSCode 完整交互:
 *   - Tab height: 35px, active bg #1E1E1E, inactive bg #2D2D2D
 *   - Active indicator: top 1px #007ACC, pinned: italic label
 *   - Drag to reorder, middle-click close
 *   - 🔥 Right-click context menu: Close/Close Others/Close to Right/Close All/Pin/Duplicate/Split/Reveal
 *
 * Session 23: 支持 groupId prop 按编辑器组过滤 tabs
 */
import { FileCode, FileJson, FileText, FileImage, Pin, SplitSquareVertical } from "lucide-vue-next"
import { computed, ref, onMounted, onUnmounted } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"
import type { EditorTab } from "@/types/ide"
import BreadcrumbsBar from "./BreadcrumbsBar.vue"

const props = defineProps<{ groupId?: string }>()
const store = useIDEStore()

/** Session 23: 按组过滤标签页 */
const groupTabs = computed(() => {
  if (!props.groupId) return store.sortedTabs
  return store.sortedTabs.filter(t => store.groups.find(g => g.id === props.groupId)?.tabs.includes(t.id))
})
const draggedTabId = ref<string | null>(null)
const dropTarget = ref<string | null>(null)
const contextMenu = ref<{ x: number; y: number; tab: EditorTab } | null>(null)
const cmRef = ref<HTMLElement | null>(null)

function onDragStart(e: DragEvent, id: string): void {
  draggedTabId.value = id; e.dataTransfer?.setData("text/plain", id); e.dataTransfer!.effectAllowed = "move"
}
function onDragOver(e: DragEvent): void { e.preventDefault(); e.dataTransfer!.dropEffect = "move" }
function onDragEnter(_e: DragEvent, id: string): void { dropTarget.value = id }
function onDragLeave(): void { dropTarget.value = null }
function onDrop(e: DragEvent, targetId: string): void {
  e.preventDefault(); dropTarget.value = null
  const src = e.dataTransfer?.getData("text/plain")
  if (!src || src === targetId) return
  const tabs = [...store.tabs]
  const si = tabs.findIndex(t => t.id === src), ti = tabs.findIndex(t => t.id === targetId)
  if (si === -1 || ti === -1) return
  const [moved] = tabs.splice(si, 1); tabs.splice(ti, 0, moved)
  tabs.forEach((t, i) => (t.order = i)); draggedTabId.value = null
}
function onMiddleClick(e: MouseEvent, id: string): void { if (e.button === 1) store.closeTab(id) }
function onCloseTab(e: Event, id: string): void { e.stopPropagation(); store.closeTab(id) }

// 🔥 Context menu
function onContextMenu(e: MouseEvent, tab: EditorTab): void {
  e.preventDefault(); e.stopPropagation()
  contextMenu.value = { x: e.clientX, y: e.clientY, tab }
}
function closeContextMenu(): void { contextMenu.value = null }
function cmAction(fn: () => void): void { fn(); closeContextMenu() }

onMounted(() => document.addEventListener("click", closeContextMenu))
onUnmounted(() => document.removeEventListener("click", closeContextMenu))

function getFileIcon(tab: EditorTab) {
  const ext = tab.filePath?.split(".").pop()?.toLowerCase() ?? ""
  if (["ts","tsx","js","jsx","py","rs","go"].includes(ext)) return FileCode
  if (["json","toml","yaml","yml"].includes(ext)) return FileJson
  if (["md","txt"].includes(ext)) return FileText
  if (["png","jpg","jpeg","svg","gif","webp"].includes(ext)) return FileImage
  return FileCode
}
const iconColors: Record<string, string> = { vue:"#41B883", ts:"#519aba", tsx:"#519aba", js:"#F0DB4F", jsx:"#61DAFB", json:"#F5A623", md:"#519aba", py:"#3776AB", css:"#42A5F5", html:"#E44D26" }
function getColor(l: string): string { return iconColors[l.split(".").pop()?.toLowerCase() ?? ""] ?? "#CCCCCC" }
</script>

<template>
  <div class="flex items-stretch shrink-0 overflow-hidden select-none"
    style="height: var(--tabbar-height); background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border);"
    @dragover="onDragOver">
    <div class="shrink-0 h-full flex items-center border-r border-[var(--color-tab-border)]" style="background: var(--color-editor-bg);">
      <BreadcrumbsBar />
    </div>
    <div class="flex-1 overflow-x-auto overflow-y-hidden h-full" style="scrollbar-width:none;">
      <div class="flex h-full items-stretch min-w-0" role="tablist">
        <div v-for="tab in groupTabs" :key="tab.id"
          class="group/tab relative flex items-center gap-1 h-full cursor-pointer shrink-0"
          :class="tab.id === store.activeTabId
            ? 'text-[var(--color-ide-text)]'
            : 'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-tab-hover)]'"
          :style="{
            background: tab.id === store.activeTabId ? 'var(--color-tab-active)' : 'var(--color-tab-inactive)',
            borderRight: '1px solid var(--color-tab-border)',
            paddingRight: '6px',
          }"
          :title="`${tab.filePath || '(未命名)'}${tab.modified ? ' ●' : ''}${tab.pinned ? ' 📌' : ''}`"
          draggable="true" role="tab" :aria-selected="tab.id === store.activeTabId"
          @click="store.activeTabId = tab.id"
          @mousedown.middle="onMiddleClick($event, tab.id)"
          @contextmenu="onContextMenu($event, tab)"
          @dragstart="onDragStart($event, tab.id)"
          @dragenter="onDragEnter($event, tab.id)"
          @dragleave="onDragLeave" @drop="onDrop($event, tab.id)">
          <!-- Active top border -->
          <div v-if="tab.id === store.activeTabId"
            class="absolute top-0 left-0 right-0 z-10" style="height:1px; background: var(--color-ide-accent);" />
          <!-- Label -->
          <div class="flex items-center gap-1.5 min-w-0 pl-2.5">
            <component :is="getFileIcon(tab)" :size="14" :style="{color: getColor(tab.label)}" class="shrink-0" />
            <span class="truncate text-[13px] leading-none" :class="{ 'italic text-[12px]': tab.pinned }">{{ tab.label }}</span>
            <!-- Pin indicator -->
            <span v-if="tab.pinned" class="shrink-0 opacity-50">
              <Pin :size="10" />
            </span>
            <!-- Modified dot -->
            <span v-if="tab.modified" class="dirty-dot shrink-0 rounded-full"
              :style="{width:'8px', height:'8px', background: tab.id===store.activeTabId?'#FBBF24':'rgba(204,204,204,0.4)'}" />
          </div>
          <!-- Close btn -->
          <button class="shrink-0 flex items-center justify-center rounded-sm transition-opacity"
            :class="tab.id===store.activeTabId ? 'opacity-70 hover:opacity-100' : 'opacity-0 group-hover/tab:opacity-70'"
            style="width:28px; height:28px;" @click="onCloseTab($event, tab.id)">
            <svg width="8" height="8" viewBox="0 0 24 24" fill="none"
              :stroke="tab.id===store.activeTabId ? '#CCCCCC' : '#858585'"
              stroke-width="2" stroke-linecap="round">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          </button>
          <!-- Drop indicator -->
          <div v-if="dropTarget===tab.id" class="absolute top-0 bottom-0 right-0 z-20"
            style="width:2px;background:var(--color-ide-accent);pointer-events:none;" />
        </div>
      </div>
    </div>
    <!-- Editor actions -->
    <div v-if="groupTabs.length>0" class="shrink-0 flex items-center gap-0.5 px-1.5 h-full border-l border-[var(--color-tab-border)]">
      <!-- Session 23: Split Right button (VSCode split editor) -->
      <button class="w-7 h-7 rounded-[3px] flex items-center justify-center text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]"
        title="拆分编辑器向右" @click.stop="store.splitEditor('right')">
        <SplitSquareVertical :size="13" />
      </button>
      <button class="w-7 h-7 rounded-[3px] flex items-center justify-center text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]"
        title="更多操作" @click.stop>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><circle cx="3" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="13" cy="8" r="1.2"/></svg>
      </button>
    </div>
  </div>

  <!-- 🔥 VSCode Tab Context Menu -->
  <Teleport to="body">
    <div v-if="contextMenu" ref="cmRef" class="fixed z-[500] min-w-[200px] py-1 text-[13px]"
      :style="{left:contextMenu.x+'px',top:contextMenu.y+'px',background:'var(--color-ide-surface)',border:'1px solid var(--color-ide-border)',borderRadius:'3px',boxShadow:'0 2px 8px rgba(0,0,0,0.36)'}" @click.stop>
      <!-- Close -->
      <button class="context-menu-item w-full text-left flex justify-between gap-6" @click="cmAction(() => store.closeTab(contextMenu!.tab.id))">
        <span>关闭</span><kbd>Ctrl+W</kbd>
      </button>
      <!-- Close Others -->
      <button class="context-menu-item w-full text-left" @click="cmAction(() => store.closeOthers(contextMenu!.tab.id))">
        关闭其他
      </button>
      <!-- Close to Right -->
      <button class="context-menu-item w-full text-left" @click="cmAction(() => store.closeToRight(contextMenu!.tab.id))">
        关闭右侧
      </button>
      <!-- Close All -->
      <button class="context-menu-item w-full text-left" @click="cmAction(() => store.closeAll())">
        关闭所有
      </button>
      <!-- Close Unmodified (Close Saved) -->
      <button class="context-menu-item w-full text-left" @click="cmAction(() => { store.tabs.filter(t => !t.modified).forEach(t => store.closeTab(t.id)) })">
        关闭已保存
      </button>
      <hr class="my-1 border-[var(--color-ide-border)]" />
      <!-- Pin -->
      <button class="context-menu-item w-full text-left" @click="cmAction(() => store.pinTab(contextMenu!.tab.id))">
        {{ contextMenu!.tab.pinned ? '📌 取消固定' : '📌 固定' }}
      </button>
      <!-- Duplicate -->
      <button class="context-menu-item w-full text-left flex justify-between gap-6" @click="cmAction(() => store.duplicateTab(contextMenu!.tab.id))">
        <span>复制</span><kbd>Ctrl+K Ctrl+D</kbd>
      </button>
      <hr class="my-1 border-[var(--color-ide-border)]" />
      <!-- Split -->
      <button class="context-menu-item w-full text-left flex justify-between gap-6" @click="cmAction(() => store.duplicateTab(contextMenu!.tab.id))">
        <span>拆分到右侧</span><kbd>Ctrl+\</kbd>
      </button>
      <button class="context-menu-item w-full text-left" @click="cmAction(() => store.duplicateTab(contextMenu!.tab.id))">
        拆分到下方
      </button>
      <hr v-if="contextMenu.tab.filePath" class="my-1 border-[var(--color-ide-border)]" />
      <!-- Reveal in Explorer -->
      <button v-if="contextMenu.tab.filePath" class="context-menu-item w-full text-left flex justify-between gap-6" @click="cmAction(() => store.revealInTree(contextMenu!.tab.filePath!))">
        <span>在资源管理器中显示</span><kbd>Ctrl+K R</kbd>
      </button>
      <!-- Copy Path -->
      <button v-if="contextMenu.tab.filePath" class="context-menu-item w-full text-left flex justify-between gap-6"
        @click="cmAction(() => navigator.clipboard.writeText(contextMenu!.tab.filePath!))">
        <span>复制路径</span><kbd>Ctrl+K C</kbd>
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.dirty-dot { margin-top: 2px; }
</style>
