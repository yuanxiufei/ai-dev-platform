<script setup lang="ts">
/**
 * CodeBuddy IDE — Editor Area (VSCode editorPart)
 *
 * Session 23: 多编辑器组分屏 (VSCode Multi-Editor-Group)
 *   - 水平分割: groups 渲染多个 editor pane
 *   - 每个 pane: TabBar 35px + CodeEditor flex-1
 *   - 组间 sash: 4px 可拖拽分隔线
 *   - 底部面板: 终端 | 问题 | 差异 | 调试控制台
 */
import { computed, nextTick, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { useIDEStore } from "@/stores/useIDEStore"
import { Diff, FileCode, GitCompare, SplitSquareVertical, Bug } from "lucide-vue-next"
import TabBar from "./TabBar.vue"
import CodeEditor from "./CodeEditor.vue"
import Terminal from "./Terminal.vue"
import ProblemsPanel from "./ProblemsPanel.vue"
import DebugPanel from "./DebugPanel.vue"
import WelcomePage from "./WelcomePage.vue"
import PeekView from "./PeekView.vue"
import DiffViewer from "@/components/DiffViewer.vue"
import type { PeekItem } from "./PeekView.vue"
import type { DiffData } from "@/types/studio"
import type { EditorGroup } from "@/types/ide"

const store = useIDEStore()
const route = useRoute()
const editorKey = ref(0)

watch(() => store.activeTabId, async () => { await nextTick(); editorKey.value++ })

const isEditingFile = computed(() => !!store.activeTab)
const showBottomPanel = computed(() => store.layout.bottomPanelVisible && isEditingFile.value)

/** Session 23: 编辑器组宽度比（百分比） */
const groupWidths = ref<Record<string, number>>({})

/** 初始化组宽度 */
watch(() => store.groups, (gs) => {
  const w: Record<string, number> = {}
  gs.forEach(g => { w[g.id] = g.widthRatio ?? (1 / gs.length) })
  groupWidths.value = w
}, { immediate: true, deep: true })

/** 获取某个组的 tabs */
function getGroupTabs(group: EditorGroup) {
  return store.tabs.filter(t => group.tabs.includes(t.id))
}

/** 拖拽分隔线调整组宽度 */
function onGroupSashStart(e: MouseEvent, leftGroupId: string, rightGroupId: string): void {
  e.preventDefault()
  const container = (e.currentTarget as HTMLElement).parentElement
  if (!container) return
  const startX = e.clientX
  const startWidths = { ...groupWidths.value }

  const move = (ev: MouseEvent) => {
    const dx = ev.clientX - startX
    const totalW = container.clientWidth
    const dxRatio = dx / totalW

    let leftW = startWidths[leftGroupId] + dxRatio
    let rightW = startWidths[rightGroupId] - dxRatio

    // 最小宽度 15%
    if (leftW < 0.15) { leftW = 0.15; rightW = startWidths[leftGroupId] + startWidths[rightGroupId] - 0.15 }
    if (rightW < 0.15) { rightW = 0.15; leftW = startWidths[leftGroupId] + startWidths[rightGroupId] - 0.15 }

    groupWidths.value = { ...groupWidths.value, [leftGroupId]: leftW, [rightGroupId]: rightW }
  }
  const up = () => {
    document.removeEventListener("mousemove", move)
    document.removeEventListener("mouseup", up)
  }
  document.addEventListener("mousemove", move)
  document.addEventListener("mouseup", up)
}

/** 点击组内区域，激活该组 */
function activateGroup(groupId: string): void {
  store.activeGroupId = groupId
  const g = store.groups.find(gr => gr.id === groupId)
  if (g?.activeTabId) {
    store.activeTabId = g.activeTabId
  }
}

const terminalTabs = [
  { id: "terminal", label: "终端" },
  { id: "problems", label: "问题" },
  { id: "diff", label: "差异" },
  { id: "debug", label: "调试控制台" },
]
const activeTerminalTab = ref("terminal")

/** Active diff state */
const activeDiff = ref<DiffData | null>(null)
const diffTabBadge = computed(() => activeDiff.value ? 1 : 0)
const debugPanelRef = ref<InstanceType<typeof DebugPanel> | null>(null)

/** Listen for diff events from AI chat or multi-file diff panel */
function showDiff(diff: DiffData) {
  activeDiff.value = diff
  activeTerminalTab.value = "diff"
  // Auto-open bottom panel if closed
  if (!store.layout.bottomPanelVisible) {
    store.layout.bottomPanelVisible = true
  }
}

function clearDiff() {
  activeDiff.value = null
  activeTerminalTab.value = "terminal"
}

// Expose showDiff globally for cross-component access
;(window as any).__showWorkbenchDiff = showDiff

/** Session 26: 暴露 Peek View 给全局使用 */
;(window as any).__openPeek = openPeek
;(window as any).__closePeek = closePeek

// Panel resize drag
const panelHeight = ref(180); const isDraggingPanel = ref(false)
function onPanelResizeStart(e: MouseEvent): void {
  e.preventDefault(); isDraggingPanel.value = true
  const sy = e.clientY, sh = panelHeight.value
  const move = (ev: MouseEvent) => { panelHeight.value = Math.max(77, Math.min(600, sh + (sy - ev.clientY))) }
  const up = () => { isDraggingPanel.value = false; document.removeEventListener('mousemove',move); document.removeEventListener('mouseup',up) }
  document.addEventListener('mousemove',move); document.addEventListener('mouseup',up)
}

/** Session 26: Peek View — 悬浮定义/引用预览 */
const peekVisible = ref(false)
const peekItems = ref<PeekItem[]>([])
const peekActiveIndex = ref(0)

/** 打开 Peek View（通常由 CodeEditor 右键菜单或快捷键触发） */
function openPeek(items: PeekItem[], startIndex = 0): void {
  peekItems.value = items
  peekActiveIndex.value = startIndex
  peekVisible.value = true
}

function closePeek(): void {
  peekVisible.value = false
  peekItems.value = []
}

function peekNext(): void {
  if (peekItems.value.length > 0) {
    peekActiveIndex.value = (peekActiveIndex.value + 1) % peekItems.value.length
  }
}

function peekPrev(): void {
  if (peekItems.value.length > 0) {
    peekActiveIndex.value = (peekActiveIndex.value - 1 + peekItems.value.length) % peekItems.value.length
  }
}

function peekOpenFull(item: PeekItem): void {
  store.openFile(item.file)
  closePeek()
}
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden min-w-0" style="background:var(--color-editor-bg);">
    <TabBar v-if="isEditingFile" />

    <div class="flex-1 relative overflow-hidden flex flex-col">
      <!-- Session 26: Peek View 悬浮预览 — 最顶层 overlay，不参与 v-if 链 -->
      <PeekView
        :visible="peekVisible"
        :items="peekItems"
        :active-index="peekActiveIndex"
        @close="closePeek"
        @next="peekNext"
        @prev="peekPrev"
        @open-full="peekOpenFull"
      />

      <!-- Studio Pages -->
      <template v-if="!isEditingFile">
        <router-view v-slot="{ Component, route: currentRoute }">
          <transition enter-active-class="transition-all duration-150 ease-out"
            enter-from-class="opacity-0 translate-y-2" enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition-all duration-100 ease-in"
            leave-from-class="opacity-100 translate-y-0" leave-to-class="opacity-0 -translate-y-2" mode="out-in">
            <component :is="Component" :key="currentRoute.path" />
          </transition>
        </router-view>
      </template>

      <!-- Code Editor Mode — Session 23: 多编辑器组 -->
      <!-- 🔥 无选项卡时显示欢迎页 -->
      <WelcomePage v-else-if="store.tabs.length === 0" />

      <template v-else>
        <div class="flex-1 flex overflow-hidden">
          <!-- 单组模式（快速路径） -->
          <template v-if="store.groups.length <= 1">
            <div class="flex flex-col flex-1 min-w-0" @mousedown="activateGroup(store.groups[0]?.id ?? '')">
              <TabBar v-if="store.groups[0]" :group-id="store.groups[0].id" />
              <CodeEditor :key="editorKey" :active-tab="store.activeTab!"
                @update-content="store.updateActiveTabContent($event)"
                @update-cursor="store.updateCursorPosition($event)" class="flex-1 min-w-0" />
            </div>
          </template>
          <!-- 多组分屏模式 -->
          <template v-else>
            <template v-for="(group, gi) in store.groups" :key="group.id">
              <div class="flex flex-col overflow-hidden min-w-0"
                :style="{ width: `${(groupWidths[group.id] ?? (1 / store.groups.length)) * 100}%`, flex: 'none' }"
                @mousedown="activateGroup(group.id)">
                <TabBar :group-id="group.id" />
                <div class="flex-1 relative overflow-hidden">
                  <CodeEditor v-if="group.activeTabId"
                    :key="`g-${group.id}-${group.activeTabId}`"
                    :active-tab="store.tabs.find(t => t.id === group.activeTabId)!"
                    @update-content="store.updateActiveTabContent($event)"
                    @update-cursor="store.updateCursorPosition($event)"
                    class="absolute inset-0 w-full h-full" />
                  <div v-else class="flex items-center justify-center h-full text-[var(--color-ide-text-dim)] text-[12px]">
                    打开文件以开始编辑
                  </div>
                </div>
              </div>
              <!-- 组间分隔线 (Sash) -->
              <div v-if="gi < store.groups.length - 1"
                class="shrink-0 cursor-col-resize group/sash relative z-10"
                style="width: 4px; margin-left: -2px; margin-right: -2px;"
                @mousedown.prevent="onGroupSashStart($event, group.id, store.groups[gi + 1].id)">
                <div class="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-[var(--color-ide-border)] group-hover/sash:w-0.5 group-hover/sash:bg-[var(--color-ide-accent)] transition-all" />
              </div>
            </template>
          </template>
        </div>

        <!-- Bottom Panel (VSCode PanelPart) -->
        <div v-if="showBottomPanel" class="shrink-0 flex flex-col"
          :style="{height:panelHeight+'px',background:'var(--color-terminal-bg)',borderTop:'1px solid var(--color-ide-border)'}">
          <!-- Sash resize handle (4px) -->
          <div class="shrink-0 cursor-row-resize group/handle"
            style="height:4px;margin-top:-2px;z-index:15;"
            :class="isDraggingPanel?'bg-[var(--color-ide-accent)]':''"
            @mousedown.prevent="onPanelResizeStart">
            <div class="mx-auto h-px group-hover/handle:h-0.5 group-hover/handle:bg-[var(--color-ide-accent)] transition-all"
              style="background:var(--color-ide-border);width:calc(100%-4px);" />
          </div>

          <!-- Panel Title Bar (35px) -->
          <div class="flex items-center justify-between shrink-0"
            style="height:35px;background:var(--color-ide-bg-secondary);border-bottom:1px solid var(--color-ide-border);padding:0 8px;">
            <div class="flex items-center h-full gap-0">
              <button v-for="tab in terminalTabs" :key="tab.id"
                class="relative flex items-center h-full text-[11px] font-semibold uppercase tracking-wider transition-colors px-2.5"
                :class="activeTerminalTab===tab.id?'text-[var(--color-ide-text)]':'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
                @click="activeTerminalTab=tab.id">
                {{ tab.label }}
                <div v-if="activeTerminalTab===tab.id" class="absolute bottom-0 left-2.5 right-2.5"
                  style="height:1px;background:var(--color-ide-accent);" />
              </button>
            </div>
            <div class="flex items-center gap-0.5">
              <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]" title="清除终端">
                <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3L3 11M3 3l8 8"/></svg>
              </button>
              <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]" title="拆分终端">
                <svg width="11" height="12" viewBox="0 0 16 18" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="2" y="2" width="12" height="14" rx="1"/><path d="M8 2v14"/></svg>
              </button>
              <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]" title="关闭面板" @click="store.layout.bottomPanelVisible=false">
                <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3L3 11M3 3l8 8"/></svg>
              </button>
            </div>
          </div>

          <!-- Panel Content -->
          <div class="flex-1 overflow-auto">
            <Terminal v-if="activeTerminalTab === 'terminal'" />
            <ProblemsPanel v-else-if="activeTerminalTab === 'problems'" />
            <DebugPanel v-else-if="activeTerminalTab === 'debug'" ref="debugPanelRef" />
            <!-- Diff panel -->
            <div v-else-if="activeTerminalTab === 'diff'" class="h-full flex flex-col">
              <template v-if="activeDiff">
                <!-- Diff header -->
                <div class="flex items-center justify-between px-3 py-1.5 border-b border-[var(--color-ide-border)] shrink-0" style="background:var(--color-ide-bg-secondary);">
                  <div class="flex items-center gap-2 text-[11px]">
                    <GitCompare :size="13" class="text-[var(--color-ide-accent)]" />
                    <span class="font-medium text-[var(--color-ide-text)]">{{ activeDiff.file_name }}</span>
                    <span class="px-1.5 py-0 rounded text-[9px] font-semibold uppercase"
                      :class="activeDiff.change_type === 'CREATE' ? 'bg-green-500/10 text-green-400' : activeDiff.change_type === 'DELETE' ? 'bg-red-500/10 text-red-400' : 'bg-yellow-500/10 text-yellow-400'">
                      {{ activeDiff.change_type === 'CREATE' ? '新建' : activeDiff.change_type === 'DELETE' ? '删除' : '修改' }}
                    </span>
                    <span class="text-[var(--color-ide-text-dim)]">
                      <span class="text-green-400">+{{ activeDiff.lines_added }}</span>
                      <span class="mx-1">/</span>
                      <span class="text-red-400">-{{ activeDiff.lines_removed }}</span>
                    </span>
                  </div>
                  <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" title="关闭差异" @click="clearDiff">
                    <svg width="11" height="11" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3L3 11M3 3l8 8"/></svg>
                  </button>
                </div>
                <!-- Diff content -->
                <div class="flex-1 overflow-auto">
                  <DiffViewer :diff="activeDiff" />
                </div>
              </template>
              <div v-else class="flex flex-col items-center justify-center h-full gap-2 text-[var(--color-ide-text-dim)]">
                <Diff :size="24" class="opacity-30" />
                <p class="text-[11px]">暂无差异比对</p>
                <p class="text-[10px] opacity-60">AI 生成代码或修改文件后，差异将在此显示</p>
              </div>
            </div>
            <div v-else class="flex items-center justify-center h-full text-[var(--color-ide-text-dim)] text-[11px]">
              {{ activeTerminalTab === 'debug' ? '调试控制台 (连接调试器以使用)' : '' }}
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
