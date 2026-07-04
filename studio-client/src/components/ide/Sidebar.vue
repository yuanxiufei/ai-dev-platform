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
 *     - 可拖拽分栏: 打开编辑器 / 项目文件 / 大纲 / 时间线
 *
 * 架构变更 (Session 31):
 *   - 4 个分栏 (打开编辑器 / 项目文件 / 大纲 / 时间线) 改为可拖拽调节高度
 *   - 每个分栏底部有一个 4px 拖拽手柄, 上下拖动改变上方分栏高度
 *   - 双击手柄 = 折叠/展开上方分栏
 *   - 高度持久化到 localStorage (sidebar_section_heights_v1)
 *   - 限制: 每个分栏最小 24px (只剩标题), 最大不超容器 80%
 */
import { Bug, Settings } from "lucide-vue-next"
import { computed, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { useIDEStore } from "@/stores/useIDEStore"
import FileTree from "./FileTree.vue"
import ProjectsPanel from "./ProjectsPanel.vue"
import StudioPanel from "./StudioPanel.vue"
import ScmPanel from "./ScmPanel.vue"
import OutlinePanel from "./OutlinePanel.vue"
import TimelinePanel from "./TimelinePanel.vue"
import SearchPanel from "./SearchPanel.vue"
import ExtensionsPanel from "./ExtensionsPanel.vue"
import TestingPanel from "./TestingPanel.vue"
import InputDialog from "@/components/InputDialog.vue"

const store = useIDEStore()
const route = useRoute()
const isDragging = ref(false)
const fileTreeReady = ref(false)

/**
 * Sidebar 顶部标题
 *  - 标准视图：直接显示活动项名
 *  - AI 工具视图：根据当前路由显示"AI 工具 / [工具名]"
 */
const sidebarTitle = computed<string>(() => {
  if (store.activeActivityItem === 'ai-studio' || store.activeActivityItem === 'ai-more' || store.activeActivityItem === 'studio') {
    return 'AI 工具'
  }
  if (store.activeActivityItem === 'projects') return '项目'
  if (store.activeActivityItem === 'explorer') return '资源管理器'
  if (store.activeActivityItem === 'git') return '源代码管理'
  if (store.activeActivityItem === 'search') return '搜索'
  if (store.activeActivityItem === 'debug') return '运行和调试'
  if (store.activeActivityItem === 'testing') return '测试'
  if (store.activeActivityItem === 'extensions') return '扩展'
  if (store.activeActivityItem === 'settings') return '管理'
  return '资源管理器'
})

// ─── 各分栏高度 (px) ───
interface SectionHeights {
  openEditors: number
  project: number
  outline: number
  // timeline 用 flex:1, 不存固定高度
}

const SECTION_STORAGE_KEY = "sidebar_section_heights_v1"
const DEFAULT_HEIGHTS: SectionHeights = {
  openEditors: 140,
  project: 280,
  outline: 160,
}

function loadHeights(): SectionHeights {
  try {
    const raw = localStorage.getItem(SECTION_STORAGE_KEY)
    if (raw) return { ...DEFAULT_HEIGHTS, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return { ...DEFAULT_HEIGHTS }
}

const sectionHeights = ref<SectionHeights>(loadHeights())

let saveTimeout: ReturnType<typeof setTimeout> | null = null
watch(
  () => ({ ...sectionHeights.value }),
  () => {
    if (saveTimeout) clearTimeout(saveTimeout)
    saveTimeout = setTimeout(() => {
      try { localStorage.setItem(SECTION_STORAGE_KEY, JSON.stringify(sectionHeights.value)) } catch { /* ignore */ }
    }, 500)
  },
  { deep: true },
)

// "打开编辑器" 区域 — 显示所有打开的标签页
const openEditors = computed(() => store.tabs)

// 🔥 输入对话框状态
const newFileDlgOpen = ref(false)
const newFolderDlgOpen = ref(false)

onMounted(async () => {
  console.log('[Sidebar] onMounted, calling initFileTree...')
  try {
    await store.initFileTree()
    console.log('[Sidebar] initFileTree done, fileTree length:', store.fileTree.length)
  } catch (e) {
    console.error('[Sidebar] initFileTree failed:', e)
  }
  fileTreeReady.value = true
})

// ─── 拖拽分栏高度 ───
const MIN_SECTION_HEIGHT = 24 // 只剩标题

function onSplitterDragStart(e: MouseEvent, key: keyof SectionHeights): void {
  e.preventDefault()
  isDragging.value = true
  document.body.classList.add("cursor-row-resize", "select-none")
  const startY = e.clientY
  const startH = sectionHeights.value[key]
  const containerEl = (e.currentTarget as HTMLElement).parentElement
  const containerH = containerEl ? containerEl.clientHeight : 800

  const move = (ev: MouseEvent) => {
    const dy = ev.clientY - startY
    const newH = Math.max(MIN_SECTION_HEIGHT, Math.min(containerH * 0.8, startH + dy))
    sectionHeights.value[key] = newH
  }
  const up = () => {
    isDragging.value = false
    document.body.classList.remove("cursor-row-resize", "select-none")
    document.removeEventListener("mousemove", move)
    document.removeEventListener("mouseup", up)
  }
  document.addEventListener("mousemove", move)
  document.addEventListener("mouseup", up)
}

// ─── 双击分栏: 折叠到最小高度 (只剩标题) ───
const collapsedSections = ref<Record<string, boolean>>({})

function onSplitterDoubleClick(key: keyof SectionHeights): void {
  collapsedSections.value[key] = !collapsedSections.value[key]
}

const effectiveHeight = (key: keyof SectionHeights): string => {
  if (collapsedSections.value[key]) return `${MIN_SECTION_HEIGHT}px`
  return `${sectionHeights.value[key]}px`
}

// ── 文件操作 ──
async function handleNewFile(): Promise<void> {
  newFileDlgOpen.value = true
}

async function onConfirmNewFile(name: string): Promise<void> {
  const parent = store.workspaceRoot // 空字符串在 demo 模式下合法
  const created = await store.createFileEntry(parent, name.trim())
  if (created) {
    store.fileTree.push(created)
    store.fileTree.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
    })
    // 🔥 新建后自动打开文件
    store.openFile(created.path)
  }
}

async function handleNewFolder(): Promise<void> {
  newFolderDlgOpen.value = true
}

async function onConfirmNewFolder(name: string): Promise<void> {
  const parent = store.workspaceRoot // 空字符串在 demo 模式下合法
  const created = await store.createFolderEntry(parent, name.trim())
  if (created) {
    store.fileTree.push(created)
    store.fileTree.sort((a, b) => {
      if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
    })
  }
}

// 🔥 校验: 文件/文件夹名不能包含非法字符, 且不能与已有项重名
function validateEntryName(parentDir: string, name: string): string | null {
  if (!name) return null // 空值由组件内 "名称不能为空" 处理
  if (/[\\/:*?"<>|]/.test(name)) return "名称不能包含以下字符: \\ / : * ? \" < > |"
  // 检查重名
  const sameParent =
    parentDir === store.workspaceRoot
      ? store.fileTree
      : (() => {
          const find = (entries: typeof store.fileTree): any => {
            for (const e of entries) {
              if (e.path === parentDir) return e.children ?? []
              if (e.children) {
                const r = find(e.children)
                if (r) return r
              }
            }
            return null
          }
          return find(store.fileTree) ?? []
        })()
  if (sameParent.some((e: any) => e.name === name)) return "同名文件/文件夹已存在"
  return null
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
      style="height: var(--panel-title-height); padding: 0 10px 0 20px; border-bottom: 1px solid var(--color-ide-border);"
    >
      <span class="text-[12px] font-semibold uppercase tracking-wider text-[var(--color-ide-text)]">
        {{ sidebarTitle }}
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
    <div class="flex-1 overflow-hidden min-h-0 flex flex-col">
      <!-- 🔥 Projects View (项目) — 列表 + 搜索 + 创建入口 -->
      <ProjectsPanel v-if="store.activeActivityItem === 'projects'" />

      <!-- 🔥 Explorer View (资源管理器) — 4 个可拖拽分栏 -->
      <div v-if="store.activeActivityItem === 'explorer'" class="flex-1 flex flex-col min-h-0">
        <!-- "打开编辑器" 区 -->
        <div v-if="openEditors.length > 0" class="shrink-0 flex flex-col" :style="{ height: effectiveHeight('openEditors') }">
          <button
            class="sidebar-section-header shrink-0"
            @click="collapsedSections['openEditors'] = !collapsedSections['openEditors']"
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"
              class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': !collapsedSections['openEditors'] }">
              <path d="M4 2l8 6-8 6V2z" />
            </svg>
            <span class="text-[12px] font-semibold uppercase tracking-wider">打开编辑器</span>
            <span class="text-[11px] text-[var(--color-ide-text-dim)] ml-1">({{ openEditors.length }})</span>
          </button>
          <div v-if="!collapsedSections['openEditors']" class="flex-1 overflow-y-auto overflow-x-hidden py-0.5 min-h-0">
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

        <!-- 🔥 分栏拖拽手柄 (打开编辑器 ↓ 项目文件) -->
        <div v-if="openEditors.length > 0"
          class="section-splitter shrink-0"
          @mousedown="onSplitterDragStart($event, 'openEditors')"
          @dblclick="onSplitterDoubleClick('openEditors')"
        />

        <!-- "项目文件" 区 -->
        <div class="shrink-0 flex flex-col" :style="{ height: effectiveHeight('project') }">
          <button
            class="sidebar-section-header shrink-0"
            @click="collapsedSections['project'] = !collapsedSections['project']"
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"
              class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': !collapsedSections['project'] }">
              <path d="M4 2l8 6-8 6V2z" />
            </svg>
            <span class="text-[12px] font-semibold uppercase tracking-wider">
              {{ store.workspaceRoot?.split(/[/\\]/).pop() || '项目文件' }}
            </span>
          </button>
          <div v-if="!collapsedSections['project']" class="flex-1 overflow-hidden min-h-0">
            <FileTree />
          </div>
        </div>

        <!-- 🔥 分栏拖拽手柄 (项目文件 ↓ 大纲) -->
        <div
          class="section-splitter shrink-0"
          @mousedown="onSplitterDragStart($event, 'project')"
          @dblclick="onSplitterDoubleClick('project')"
        />

        <!-- "大纲" 区 -->
        <div class="shrink-0 flex flex-col" :style="{ height: effectiveHeight('outline') }">
          <button
            class="sidebar-section-header shrink-0"
            @click="collapsedSections['outline'] = !collapsedSections['outline']"
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"
              class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': !collapsedSections['outline'] }">
              <path d="M4 2l8 6-8 6V2z" />
            </svg>
            <span class="text-[12px] font-semibold uppercase tracking-wider">大纲</span>
          </button>
          <div v-if="!collapsedSections['outline']" class="flex-1 overflow-hidden min-h-0">
            <OutlinePanel />
          </div>
        </div>

        <!-- 🔥 分栏拖拽手柄 (大纲 ↓ 时间线) -->
        <div
          class="section-splitter shrink-0"
          @mousedown="onSplitterDragStart($event, 'outline')"
          @dblclick="onSplitterDoubleClick('outline')"
        />

        <!-- 🔥 "时间线" 区 (VS Code Timeline) — flex: 1 自动占满剩余 -->
        <div class="flex-1 flex flex-col min-h-0">
          <button
            class="sidebar-section-header shrink-0"
            @click="collapsedSections['timeline'] = !collapsedSections['timeline']"
          >
            <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor"
              class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': !collapsedSections['timeline'] }">
              <path d="M4 2l8 6-8 6V2z" />
            </svg>
            <span class="text-[12px] font-semibold uppercase tracking-wider">时间线</span>
          </button>
          <div v-if="!collapsedSections['timeline']" class="flex-1 min-h-0 overflow-hidden">
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

      <!-- 🔥 AI 工具面板（点 ActivityBar "更多 AI 工具"时展示） -->
      <StudioPanel v-else-if="store.activeActivityItem === 'studio' || store.activeActivityItem === 'ai-more' || store.activeActivityItem === 'ai-studio'" />

      <!-- 🔥 防御：settings 使用模态框，不应走 Sidebar。这里作为兜底占位 -->
      <div v-else-if="store.activeActivityItem === 'settings'" class="h-full flex flex-col items-center justify-center text-[var(--color-ide-text-dim)]">
        <Settings :size="24" class="mb-2 opacity-30" />
        <p class="text-[12px]">管理</p>
        <button class="mt-2 px-3 py-1 text-[11px] rounded border border-[var(--color-ide-border)] hover:bg-[var(--color-ide-surface-hover)]"
          @click="store.showSettingsPanel = true">打开设置面板</button>
      </div>
    </div>
  </div>

  <!-- 🔥 新建文件对话框 -->
  <InputDialog
    v-model:open="newFileDlgOpen"
    title="新建文件"
    placeholder="请输入文件名 (含扩展名, 如 main.ts)"
    confirm-text="创建"
    :validator="(n) => validateEntryName(store.workspaceRoot ?? '', n)"
    @confirm="onConfirmNewFile"
  />

  <!-- 🔥 新建文件夹对话框 -->
  <InputDialog
    v-model:open="newFolderDlgOpen"
    title="新建文件夹"
    placeholder="请输入文件夹名"
    confirm-text="创建"
    :validator="(n) => validateEntryName(store.workspaceRoot ?? '', n)"
    @confirm="onConfirmNewFolder"
  />
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

/* 🔥 VSCode 风格: 分栏拖拽手柄 (4px 高的横向条) */
.section-splitter {
  height: 4px;
  cursor: row-resize;
  background: transparent;
  position: relative;
  flex-shrink: 0;
  transition: background 0.15s;
}
/* 默认显示细分割线 (1px) — 始终可见 */
.section-splitter::after {
  content: "";
  position: absolute;
  top: 1px;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--color-ide-border);
  opacity: 0.45;
  transition: opacity 0.15s;
}
/* hover 时手柄整条 4px 变 accent 色 */
.section-splitter:hover {
  background: var(--color-ide-accent);
}
.section-splitter:hover::after,
.section-splitter:active::after {
  opacity: 0.8;
  background: var(--color-ide-accent);
}
</style>
