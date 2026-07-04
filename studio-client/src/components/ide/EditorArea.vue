<script setup lang="ts">
/**
 * CodeBuddy IDE — Editor Area (VSCode editorPart)
 *
 * VSCode 对标设计：
 *   - 多编辑器组分屏 (VSCode Multi-Editor-Group)
 *   - 路由页面 (AI 工具/设置) 作为全屏 overlay 渲染在编辑器上层
 *   - 不关闭编辑标签页，切换工具时保持编辑器状态
 *   - 底部面板只在 App.vue 全局渲染（单一面板源）
 */
import { computed, nextTick, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useIDEStore } from "@/stores/useIDEStore"
import { ArrowLeft } from "lucide-vue-next"
import TabBar from "./TabBar.vue"
import CodeEditor from "./CodeEditor.vue"
import WelcomePage from "./WelcomePage.vue"
import PeekView from "./PeekView.vue"
import type { PeekItem } from "./PeekView.vue"

const store = useIDEStore()
const route = useRoute()
const router = useRouter()
const editorKey = ref(0)

watch(() => store.activeTabId, async () => { await nextTick(); editorKey.value++ })

const isEditingFile = computed(() => store.tabs.length > 0)

/**
 * VSCode 对标：AI 工具/设置页面作为全屏 overlay 渲染，不干扰编辑器
 *
 * Session 33 修复:
 *   - 旧版只对 5 个路径开 overlay，导致其他 Studio 工具（/memory, /kanban, /voice, ...）跳转后中央留白
 *   - 修复：只要不是"纯编辑器"路径（即不进入 /projects 列表本身），所有路由页面都 overlay
 *   - /projects 列表本身用 ProjectsPanel（左 Sidebar 显示），不需 overlay
 */
const showPageOverlay = computed(() => {
  const path = route.path
  // /projects 列表本身由 Sidebar ProjectsPanel + 空 EditorArea 处理
  if (path === '/projects') return false
  // 其他所有路由（AI 工具 / 设置 / 项目详情 / 新建项目 等）都用 overlay
  return true
})

function closePageOverlay(): void {
  router.push('/projects')
}

/** Session 23: 编辑器组宽度比（百分比） */
const groupWidths = ref<Record<string, number>>({})

/** 初始化组宽度 */
watch(() => store.groups, (gs) => {
  const w: Record<string, number> = {}
  gs.forEach(g => { w[g.id] = g.widthRatio ?? (1 / gs.length) })
  groupWidths.value = w
}, { immediate: true, deep: true })

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

/** Session 26: 暴露 Peek View 给全局使用 */
;(window as any).__openPeek = openPeek
;(window as any).__closePeek = closePeek

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

/** 当前应该显示在编辑器中的 tab */
const currentActiveTab = computed(() => {
  if (store.activeTab) return store.activeTab
  if (store.activeTabId) {
    const t = store.tabs.find(t => t.id === store.activeTabId)
    if (t) return t
  }
  if (store.tabs.length > 0) return store.tabs[0]
  return null
})
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden min-w-0" style="background:var(--color-editor-bg);">
    <!-- TabBar: 正常由子模式渲染（单组/多组），groups为空时兜底渲染避免TabBar缺失 -->
    <TabBar v-if="isEditingFile && store.groups.length === 0" />

    <div class="flex-1 relative overflow-hidden flex flex-col">
      <!-- Session 26: Peek View 悬浮预览 — 最顶层 overlay -->
      <PeekView
        :visible="peekVisible"
        :items="peekItems"
        :active-index="peekActiveIndex"
        @close="closePeek"
        @next="peekNext"
        @prev="peekPrev"
        @open-full="peekOpenFull"
      />

      <!-- VSCode 对标：AI 工具/设置页面作为全屏 overlay 渲染在编辑器上层 -->
      <!-- 不关闭编辑标签页，路由页面始终可覆盖显示 -->
      <div v-if="showPageOverlay" class="absolute inset-0 z-20 flex flex-col" style="background: var(--color-editor-bg);">
        <!-- Overlay 顶部工具栏：返回按钮 -->
        <div class="flex items-center px-2 shrink-0" style="height: var(--panel-title-height); background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border);">
          <button
            class="flex items-center gap-1 px-2 py-0.5 text-[12px] rounded-sm transition-colors cursor-pointer"
            style="color: var(--color-ide-text-dim);"
            @click="closePageOverlay"
            @mouseenter="(e: MouseEvent) => { (e.currentTarget as HTMLElement).style.color = 'var(--color-ide-text)'; (e.currentTarget as HTMLElement).style.background = 'var(--color-ide-surface-hover)'; }"
            @mouseleave="(e: MouseEvent) => { (e.currentTarget as HTMLElement).style.color = 'var(--color-ide-text-dim)'; (e.currentTarget as HTMLElement).style.background = 'transparent'; }"
          >
            <ArrowLeft :size="14" />
            <span>返回编辑器</span>
          </button>
        </div>
        <div class="flex-1 overflow-auto">
          <router-view v-slot="{ Component, route: currentRoute }">
            <transition enter-active-class="transition-all duration-150 ease-out"
              enter-from-class="opacity-0 translate-y-2" enter-to-class="opacity-100 translate-y-0"
              leave-active-class="transition-all duration-100 ease-in"
              leave-from-class="opacity-100 translate-y-0" leave-to-class="opacity-0 -translate-y-2" mode="out-in">
              <component :is="Component" :key="currentRoute.path" />
            </transition>
          </router-view>
        </div>
      </div>

      <!-- 无编辑文件时显示欢迎页 -->
      <WelcomePage v-if="!isEditingFile" />

      <template v-else>
        <div class="flex-1 flex overflow-hidden">
          <!-- 单组模式（快速路径） -->
          <template v-if="store.groups.length <= 1">
            <div class="flex flex-col flex-1 min-w-0" @mousedown="activateGroup(store.groups[0]?.id ?? '')">
              <TabBar v-if="store.groups[0]" :group-id="store.groups[0].id" />
              <CodeEditor v-if="currentActiveTab" :key="editorKey" :active-tab="currentActiveTab"
                @update-content="store.updateActiveTabContent($event)"
                @update-cursor="store.updateCursorPosition($event)" class="flex-1 min-w-0" />
              <div v-else class="flex-1 flex items-center justify-center text-[var(--color-ide-text-dim)] text-[12px]">
                正在准备编辑器…
              </div>
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
      </template>
    </div>
  </div>
</template>
