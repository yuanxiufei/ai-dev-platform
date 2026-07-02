<script setup lang="ts">
/**
 * Sidebar — VS Code sidebarPart (右侧面板内容区, 不含 ActivityBar)
 *
 * 架构变更 (Session 27):
 *   ActivityBar 已分离为独立组件 (ActivityBar.vue)
 *   Sidebar 现在仅负责:
 *     - 可拖拽调整宽度 (170px ~ 600px)
 *     - 顶部标题栏 + 工具栏
 *     - 根据 activeActivityItem 切换面板内容
 *     - Explorer/SCM/Search/Debug/Extensions 视图
 *     - 折叠区: 打开编辑器 / 项目文件 / 大纲
 */
import { Search, Bug, Blocks, Sparkles, FlaskConical } from "lucide-vue-next"
import { computed, onMounted, ref } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"
import FileTree from "./FileTree.vue"
import ScmPanel from "./ScmPanel.vue"
import OutlinePanel from "./OutlinePanel.vue"
import TimelinePanel from "./TimelinePanel.vue"
import SearchPanel from "./SearchPanel.vue"
import ExtensionsPanel from "./ExtensionsPanel.vue"
import TestingPanel from "./TestingPanel.vue"

const store = useIDEStore()
const isDragging = ref(false)
const fileTreeReady = ref(false)

// 🔥 可折叠区域
const sectionsCollapsed = ref<Record<string, boolean>>({})

// 🔥 "打开编辑器" 区域 — 显示所有打开的标签页
const openEditors = computed(() => store.tabs)

onMounted(async () => {
  await store.initFileTree()
  fileTreeReady.value = true
})

// ── 文件操作 ──
async function handleNewFile(): Promise<void> {
  const name = prompt("文件名:")
  if (!name?.trim()) return
  const parent = store.workspaceRoot; if (!parent) return
  const created = await store.createFileEntry(parent, name.trim())
  if (created) {
    store.fileTree.push(created)
    store.fileTree.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
    })
  }
}

async function handleNewFolder(): Promise<void> {
  const name = prompt("文件夹名:")
  if (!name?.trim()) return
  const parent = store.workspaceRoot; if (!parent) return
  const created = await store.createFolderEntry(parent, name.trim())
  if (created) {
    store.fileTree.push(created)
    store.fileTree.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
    })
  }
}

// ── 拖拽调整宽度 ──
function onDragStart(e: MouseEvent): void {
  e.preventDefault(); isDragging.value = true
  document.body.classList.add("cursor-col-resize", "select-none")
  const startX = e.clientX, startW = store.layout.sidebarWidth
  const move = (ev: MouseEvent) => {
    store.layout.sidebarWidth = Math.max(170, Math.min(600, startW + (ev.clientX - startX)))
  }
  const up = () => {
    isDragging.value = false
    document.body.classList.remove("cursor-col-resize", "select-none")
    document.removeEventListener("mousemove", move)
    document.removeEventListener("mouseup", up)
  }
  document.addEventListener("mousemove", move)
  document.addEventListener("mouseup", up)
}

// ── 文件颜色标签 ──
function getFileColor(name: string): string {
  const c: Record<string, string> = { ts: '#60A5FA', tsx: '#60A5FA', js: '#f7df1e', jsx: '#61dafb', py: '#3776ab', rs: '#dea584', vue: '#38BDF8', json: '#FB923C', md: '#3B82F6', html: '#E06C75', css: '#264de4' }
  return c[name.split('.').pop()?.toLowerCase() ?? ''] ?? '#90a4ae'
}
</script>

<template>
  <!-- ═══ Sidebar Content Panel (VSCode sidebarPart) ═══ -->
  <div
    v-if="store.layout.fileTreeVisible"
    class="shrink-0 flex flex-col h-full overflow-hidden relative"
    :style="{
      width: `${store.layout.sidebarWidth}px`,
      background: 'var(--color-ide-surface)',
      borderRight: '1px solid var(--color-ide-border)',
    }"
  >
    <!-- 🔥 Resize Handle (右侧拖拽) -->
    <div class="resize-handle resize-handle-h" :class="{ active: isDragging }"
      style="right: 0; left: auto;"
      @mousedown.prevent="onDragStart" />

    <!-- ═══ Header Bar (38px) — 随活动视图变化 ═══ -->
    <div
      class="flex items-center justify-between shrink-0"
      style="height: 38px; padding: 0 10px 0 20px; border-bottom: 1px solid var(--color-ide-border);"
    >
      <span class="text-[12px] font-semibold uppercase tracking-wider text-[var(--color-ide-text)]">
        <template v-if="store.activeActivityItem === 'explorer'">资源管理器</template>
        <template v-else-if="store.activeActivityItem === 'git'">源代码管理</template>
        <template v-else-if="store.activeActivityItem === 'search'">搜索</template>
        <template v-else-if="store.activeActivityItem === 'debug'">运行和调试</template>
        <template v-else-if="store.activeActivityItem === 'testing'">测试</template>
        <template v-else-if="store.activeActivityItem === 'extensions'">扩展</template>
        <template v-else-if="store.activeActivityItem === 'studio'">AI Studio</template>
        <template v-else-if="store.activeActivityItem === 'settings'">管理</template>
        <template v-else>资源管理器</template>
      </span>

      <!-- 🔥 工具栏操作 -->
      <div class="flex items-center gap-0.5">
        <template v-if="store.activeActivityItem === 'explorer'">
          <button
            class="w-7 h-7 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]"
            title="新建文件" @click="handleNewFile"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M10 1H3a1 1 0 00-1 1v8a1 1 0 001 1h10a1 1 0 001-1V5l-4-4z" /><path d="M10 1v4h4" />
            </svg>
          </button>
          <button
            class="w-7 h-7 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]"
            title="新建文件夹" @click="handleNewFolder"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M2 3a1 1 0 011-1h3.5l1.5 2H13a1 1 0 011 1v6a1 1 0 01-1 1H3a1 1 0 01-1-1V3z" />
            </svg>
          </button>
          <button
            class="w-7 h-7 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]"
            title="更多操作"
          >
            <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
              <circle cx="3" cy="8" r="1.2" /><circle cx="8" cy="8" r="1.2" /><circle cx="13" cy="8" r="1.2" />
            </svg>
          </button>
        </template>
      </div>
    </div>

    <!-- ═══ Content Area — 根据 activeActivityItem 切换 ═══ -->
    <div class="flex-1 overflow-hidden min-h-0">
      <!-- 🔥 Explorer View (资源管理器) -->
      <div v-if="store.activeActivityItem === 'explorer'" class="h-full overflow-y-auto overflow-x-hidden">
        <!-- "打开编辑器" 区 -->
        <div v-if="openEditors.length > 0" class="sidebar-section">
          <button
            class="sidebar-section-header"
            @click="sectionsCollapsed['openEditors'] = !sectionsCollapsed['openEditors']"
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"
              class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': !sectionsCollapsed['openEditors'] }">
              <path d="M4 2l8 6-8 6V2z" />
            </svg>
            <span class="text-[12px] font-semibold uppercase tracking-wider">打开编辑器</span>
            <span class="text-[11px] text-[var(--color-ide-text-dim)] ml-1">({{ openEditors.length }})</span>
          </button>
          <div v-if="!sectionsCollapsed['openEditors']" class="py-0.5">
            <div
              v-for="tab in openEditors" :key="'oe-' + tab.id"
              class="flex items-center h-7 px-5 cursor-pointer text-[13px] transition-colors"
              :class="tab.id === store.activeTabId
                ? 'bg-[var(--color-ide-surface-active)] text-[var(--color-ide-text)]'
                : 'hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]'"
              @click="store.activeTabId = tab.id"
              @dblclick="store.openFile(tab.filePath || tab.label)"
            >
              <span class="w-1 h-1 rounded-full mr-2 shrink-0" :style="{ background: getFileColor(tab.label) }" />
              <span class="truncate flex-1">{{ tab.label }}</span>
              <span v-if="tab.modified" class="text-[10px] shrink-0 text-[#FBBF24] ml-1">●</span>
            </div>
          </div>
        </div>

        <!-- "项目文件" 区 -->
        <div class="sidebar-section">
          <button
            class="sidebar-section-header"
            @click="sectionsCollapsed['project'] = !sectionsCollapsed['project']"
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"
              class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': !sectionsCollapsed['project'] }">
              <path d="M4 2l8 6-8 6V2z" />
            </svg>
            <span class="text-[12px] font-semibold uppercase tracking-wider">
              {{ store.workspaceRoot?.split(/[/\\]/).pop() || '项目文件' }}
            </span>
          </button>
          <div v-if="!sectionsCollapsed['project']">
            <FileTree />
          </div>
        </div>

        <!-- "大纲" 区 -->
        <div class="sidebar-section">
          <button
            class="sidebar-section-header"
            @click="sectionsCollapsed['outline'] = !sectionsCollapsed['outline']"
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"
              class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': !sectionsCollapsed['outline'] }">
              <path d="M4 2l8 6-8 6V2z" />
            </svg>
            <span class="text-[12px] font-semibold uppercase tracking-wider">大纲</span>
          </button>
          <div v-if="!sectionsCollapsed['outline']" class="min-h-0 overflow-hidden" style="max-height: 200px;">
            <OutlinePanel />
          </div>
        </div>

        <!-- 🔥 "时间线" 区 (VS Code Timeline) -->
        <div class="sidebar-section" style="flex: 1; min-height: 0; display: flex; flex-direction: column;">
          <button
            class="sidebar-section-header"
            @click="sectionsCollapsed['timeline'] = !sectionsCollapsed['timeline']"
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"
              class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': !sectionsCollapsed['timeline'] }">
              <path d="M4 2l8 6-8 6V2z" />
            </svg>
            <span class="text-[12px] font-semibold uppercase tracking-wider">时间线</span>
          </button>
          <div v-if="!sectionsCollapsed['timeline']" class="flex-1 min-h-0 overflow-hidden">
            <TimelinePanel />
          </div>
        </div>
      </div>

      <!-- 🔥 SCM / Git View -->
      <ScmPanel v-else-if="store.activeActivityItem === 'git'" />

      <!-- 🔥 Search View — 使用完整 SearchPanel -->
      <SearchPanel v-else-if="store.activeActivityItem === 'search'" />

      <!-- 🔥 Debug View -->
      <div v-else-if="store.activeActivityItem === 'debug'" class="h-full flex flex-col items-center justify-center text-[var(--color-ide-text-dim)]">
        <Bug :size="24" class="mb-2 opacity-30" />
        <p class="text-[12px]">运行和调试</p>
        <p class="text-[10px] opacity-50 mt-1">连接调试器以使用</p>
      </div>

      <!-- 🔥 Testing View — 使用完整 TestingPanel -->
      <TestingPanel v-else-if="store.activeActivityItem === 'testing'" />

      <!-- 🔥 Extensions View — 使用完整 ExtensionsPanel -->
      <ExtensionsPanel v-else-if="store.activeActivityItem === 'extensions'" />

      <!-- 🔥 Studio View -->
      <div v-else-if="store.activeActivityItem === 'studio'" class="h-full flex flex-col items-center justify-center text-[var(--color-ide-text-dim)]">
        <Sparkles :size="24" class="mb-2 text-[var(--color-ide-accent)]/40" />
        <p class="text-[12px]">AI Studio</p>
        <p class="text-[10px] opacity-50 mt-1">智能编码助手</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 🔥 VS Code 分区标题 */
.sidebar-section-header {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-ide-text-dim);
  cursor: pointer;
  border: none;
  background: transparent;
  transition: color 0.1s;
}
.sidebar-section-header:hover {
  color: var(--color-ide-text);
}

.sidebar-section {
  border-bottom: 1px solid var(--color-ide-border);
}
.sidebar-section:last-child {
  border-bottom: none;
}
</style>
