<script setup lang="ts">
/**
 * ActivityBar — VS Code activitybarPart
 *
 * 设计原则:
 *   1. 单一职责 — 只负责切换 Sidebar / AI 工具栏
 *   2. 分组清晰 — 标准视图 (Top) / AI 工具 (Middle) / 系统 (Bottom)
 *   3. 状态独立 — AI 工具不污染 fileTreeVisible 状态
 *   4. 容错强健 — 点击不存在的路由不会 500，所有错误本地处理
 *   5. 拖拽 — 仅在标准视图间支持，AI 工具固定顺序
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { Settings } from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"
import { useToast } from "@/composables/useToast"

const store = useIDEStore()
const router = useRouter()
const route = useRoute()
const toast = useToast()

// ─── 当前激活项 ID ───
// 🔥 修复"状态卡住" bug: activeActivityItem 是唯一真相来源。
// 路由变化时通过 watch 同步 activeActivityItem（处理用户直接 URL 跳转）。
// 点击时 onActivityClick 直接更新 activeActivityItem。
// 路由匹配仅作 fallback（初始加载 / 页面刷新后恢复选中状态）。
const activeItemId = computed<string | null>(() => {
  const currentPath = route.path

  // 优先级 1: 用户手动选中的标准视图（包括不在 activityItems 中的固定项 explorer/settings）
  const priorityIds = [
    ...store.activityItems.filter(it => !it.route).map(it => it.id),
    'explorer', 'settings',
  ]
  if (priorityIds.includes(store.activeActivityItem)) {
    return store.activeActivityItem
  }

  // 优先级 2: 用户手动选中的 AI 工具（直接匹配 activeActivityItem）
  const aiMatch = store.activityItems.find(it => it.route && it.id === store.activeActivityItem)
  if (aiMatch) return aiMatch.id

  // 优先级 3: 回退到路由匹配（用户直接 URL 跳转 / 初始页面 / 浏览器后退）
  for (const item of store.activityItems) {
    if (item.route && currentPath.startsWith(item.route)) return item.id
  }

  // 不回退到别的值，保持上一个确认的状态
  return store.activeActivityItem
})

// 🔥 路由变化 → 同步 activeActivityItem（处理浏览器后退/直接 URL 修改）
watch(
  () => route.path,
  (newPath) => {
    for (const item of store.activityItems) {
      if (item.route && newPath.startsWith(item.route)) {
        store.activeActivityItem = item.id
        return
      }
    }
    // 回到主页 → 默认 explorer + 恢复 Sidebar
    if (newPath === '/' || newPath === '/projects') {
      store.activeActivityItem = 'explorer'
      store.layout.fileTreeVisible = true
    }
  },
  { immediate: true },
)

// ─── 拖拽状态 (仅标准视图支持) ───
const dragOverItemId = ref<string | null>(null)
const dragItemId = ref<string | null>(null)

// ─── 图标库 ───
const iconSvgs: Record<string, string> = {
  Briefcase: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="14" x="2" y="7" rx="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg>`,
  Files: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>`,
  Search: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`,
  GitBranch: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="6" cy="18" r="3"/><path d="M18 9a3 3 0 100-6 3 3 0 000 6z"/><path d="M6 15a9 9 0 009 9"/></svg>`,
  Bug: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m8 2 1.88 1.88"/><path d="M14.12 3.88 16 2"/><path d="M9 7.13v-1a3.003 3.003 0 016 0v1M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 014-4h4a4 4 0 014 4v3c0 3.3-2.7 6-6 6z"/><path d="M3 13h4M17 13h4M20 17.5l-1.5-1.5M13.5 6l-3 3M10.5 6l3 3"/></svg>`,
  Blocks: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>`,
  Sparkles: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 01-1.275 1.275L3 12l5.813 1.912a2 2 0 011.275 1.275L12 21l1.912-5.813a2 2 0 011.275-1.275L21 12l-5.813-1.912a2 2 0 01-1.275-1.275L12 3z"/></svg>`,
  FlaskConical: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6"/><path d="M10 3v7.6L4.8 17.5a1.5 1.5 0 00.9 2.5h12.6a1.5 1.5 0 00.9-2.5L14 10.6V3"/></svg>`,
  Settings: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z"/><circle cx="12" cy="12" r="3"/></svg>`,
  Brain: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 007 4.5v15a2.5 2.5 0 005 0v-1.5h.5a2.5 2.5 0 000-5h-.5V8h.5a2.5 2.5 0 000-5H12V2.5A2.5 2.5 0 009.5 2z"/><path d="M14.5 2A2.5 2.5 0 0012 4.5v15a2.5 2.5 0 005 0V2.5A2.5 2.5 0 0014.5 2z"/><circle cx="9.5" cy="12" r="1.5"/><circle cx="14.5" cy="12" r="1.5"/></svg>`,
  Camera: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 4h-5L7 7H4a2 2 0 00-2 2v9a2 2 0 002 2h16a2 2 0 002-2V9a2 2 0 00-2-2h-3l-2.5-3z"/><circle cx="12" cy="13" r="3"/></svg>`,
  Image: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="m21 15-5-5L5 21"/></svg>`,
  Bot: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="10" x="3" y="11" rx="2"/><circle cx="12" cy="5" r="2"/><path d="M8 5a2 2 0 014 0"/><path d="M12 5v6M8 16h.01M12 16h.01M16 16h.01"/></svg>`,
  Cpu: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="16" x="4" y="4" rx="2"/><rect width="6" height="6" x="9" y="9" rx="1"/><path d="M15 2v2"/><path d="M15 20v2"/><path d="M2 15h2"/><path d="M2 9h2"/><path d="M20 15h2"/><path d="M20 9h2"/><path d="M9 2v2"/><path d="M9 20v2"/></svg>`,
  Puzzle: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M15.39 4.39a1 1 0 0 0 1.68-.474 2.5 2.5 0 1 1 3.014 3.015 1 1 0 0 0-.474 1.68l1.683 1.682a2.414 2.414 0 0 1 0 3.414L19.61 15.39a1 1 0 0 1-1.68-.474 2.5 2.5 0 1 0-3.014 3.015 1 1 0 0 1 .474 1.68l-1.683 1.682a2.414 2.414 0 0 1-3.414 0L8.61 19.61a1 1 0 0 0-1.68.474 2.5 2.5 0 1 1-3.014-3.015 1 1 0 0 0 .474-1.68l-1.683-1.682a2.414 2.414 0 0 1 0-3.414L4.39 8.61a1 1 0 0 1 1.68.474 2.5 2.5 0 1 0 3.014-3.015 1 1 0 0 1-.474-1.68l1.683-1.682a2.414 2.414 0 0 1 3.414 0z"/></svg>`,
  Plug2: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 2v6"/><path d="M15 2v6"/><path d="M12 17v5"/><path d="M5 8h14"/><path d="M6 11V8h12v3a6 6 0 1 1-12 0Z"/></svg>`,
  MessageSquare: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>`,
  LayoutDashboard: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/></svg>`,
  FolderKanban: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20h16a2 2 0 002-2V8a2 2 0 00-2-2h-7.93a2 2 0 01-1.66-.9l-.82-1.2A2 2 0 007.93 3H4a2 2 0 00-2 2v13c0 1.1.9 2 2 2Z"/><path d="M8 10v4"/><path d="M12 10v2"/><path d="M16 10v6"/></svg>`,
  LayoutTemplate: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="7" x="3" y="3" rx="1"/><rect width="9" height="7" x="3" y="14" rx="1"/><rect width="5" height="7" x="16" y="14" rx="1"/></svg>`,
  /** Session 41: 端口转发 */
  Globe: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>`,
  /** Session 42: 多文件差异 */
  FileDiff: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/><line x1="8" y1="9" x2="10" y2="9"/></svg>`,
  /** Session 42: 进程管理 */
  CpuProcess: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="2" x2="9" y2="4"/><line x1="15" y1="2" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="22"/><line x1="15" y1="20" x2="15" y2="22"/><line x1="20" y1="9" x2="22" y2="9"/><line x1="20" y1="14" x2="22" y2="14"/><line x1="2" y1="9" x2="4" y2="9"/><line x1="2" y1="14" x2="4" y2="14"/></svg>`,
  /** Session 42: 自定义编辑器 */
  FileType: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>`,
  /** Session 42: 编辑会话 */
  History: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 119 9"/><polyline points="3 3 3 12 12 12"/></svg>`,
  /** Session 42: 代码片段 */
  Code2: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>`,
  /** Session 43: 任务列表 */
  ListTodo: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="4" height="4" rx="1"/><line x1="10" y1="7" x2="21" y2="7"/><rect x="3" y="12" width="4" height="4" rx="1"/><line x1="10" y1="14" x2="21" y2="14"/><rect x="3" y="19" width="4" height="4" rx="1"/><line x1="10" y1="21" x2="21" y2="21"/></svg>`,
  /** Session 43: 交互窗口 (Terminal 图标已存在，复用) */
}

// ─── 拖拽 ───
function onDragStart(e: DragEvent, itemId: string): void {
  dragItemId.value = itemId
  if (e.dataTransfer) e.dataTransfer.effectAllowed = "move"
}

function onDragOver(e: DragEvent, itemId: string): void {
  e.preventDefault()
  if (dragItemId.value && dragItemId.value !== itemId) {
    dragOverItemId.value = itemId
  }
}

function onDragLeave(): void {
  dragOverItemId.value = null
}

function onDrop(e: DragEvent, _targetId: string): void {
  e.preventDefault()
  dragOverItemId.value = null
  dragItemId.value = null
}

// ─── 核心: 点击处理 (重构) ───
// 🔥 修复"状态卡住": 所有项（包括 explorer/settings）都通过 activeActivityItem 作为唯一真相来源
async function onActivityClick(itemId: string): Promise<void> {
  const item = store.activityItems.find((it) => it.id === itemId)
  if (!item) {
    // 固定项 (explorer / settings) — 不在 activityItems 里，直接处理状态
    // 🔥 settings 使用模态框，不在 Sidebar 内渲染内容
    if (itemId === 'settings') {
      store.activeActivityItem = itemId
      store.layout.fileTreeVisible = false  // 关闭 Sidebar，settings 是独立模态框
      store.showSettingsPanel = !store.showSettingsPanel
      return
    }
    if (itemId === 'explorer') {
      if (store.activeActivityItem === 'explorer' && store.layout.fileTreeVisible) {
        store.layout.fileTreeVisible = false
      } else {
        store.activeActivityItem = 'explorer'
        store.layout.fileTreeVisible = true
      }
    } else {
      console.warn(`[ActivityBar] Unknown item: ${itemId}`)
    }
    return
  }

  try {
    // ── 情况 1: AI 工具 (有 route) → 路由导航, 关闭 Sidebar ──
    if (item.route) {
      // AI 工具是全屏独立页面，不需要 Sidebar
      store.activeActivityItem = itemId
      store.layout.fileTreeVisible = false
      if (route.path !== item.route) {
        await router.push(item.route)
      }
      return
    }

    // ── 情况 1.2: AI 对话 (ai-chat) → 打开右侧 ChatPanel ──
    // 🔥 修复: 右侧面板已开但显示其他内容(如 memory/skills)时，应切换到 chat，而非误关面板
    if (itemId === 'ai-chat') {
      store.activeActivityItem = itemId
      store.layout.fileTreeVisible = false
      if (store.layout.rightPanelVisible && store.rightPanelView === 'chat') {
        // Chat 已打开 → 关闭面板
        store.layout.rightPanelVisible = false
      } else {
        // 打开或切换到 ChatPanel
        store.rightPanelView = 'chat'
        store.layout.rightPanelVisible = true
      }
      return
    }

    // ── 情况 1.3: AI Studio 面板 (ai-studio) → 打开 Sidebar 显示 StudioPanel ──
    if (itemId === 'ai-studio') {
      if (store.activeActivityItem === 'ai-studio' && store.layout.fileTreeVisible) {
        store.layout.fileTreeVisible = false
      } else {
        store.activeActivityItem = 'ai-studio'
        store.layout.fileTreeVisible = true
      }
      return
    }

    // ── 情况 1.5: AI 工具入口 (ai-more) → 打开 Sidebar 显示 StudioPanel ──
    if (itemId === 'ai-more') {
      if (store.activeActivityItem === 'ai-more' && store.layout.fileTreeVisible) {
        store.layout.fileTreeVisible = false
      } else {
        store.activeActivityItem = 'ai-more'
        store.layout.fileTreeVisible = true
      }
      return
    }

    // ── 情况 2: 标准视图 (Explorer / Search / Git / Debug / Test / Extensions) ──
    if (store.activeActivityItem === itemId && store.layout.fileTreeVisible) {
      // 再次点击同一项 → 隐藏 Sidebar (VSCode 行为)
      store.layout.fileTreeVisible = false
    } else {
      // 切换到新项 → 显示 Sidebar
      // 🔥 关键修复: activeActivityItem 统一在此设置，activeItemId 直接读取它
      store.activeActivityItem = itemId
      store.layout.fileTreeVisible = true
    }
  } catch (e) {
    // 路由失败等异常 → 本地提示, 不再让 500 污染 UI
    console.error(`[ActivityBar] click failed for ${itemId}:`, e)
    toast?.error?.(`无法打开: ${item.label}`)
  }
}

// ─── 全局错误监听: 防止任何未捕获错误让 ActivityBar 失能 ───
function handleGlobalError(e: ErrorEvent) {
  if (e.filename?.includes("ActivityBar") || e.message?.includes("ActivityBar")) {
    console.error("[ActivityBar] global error:", e.message)
  }
}

onMounted(() => {
  window.addEventListener("error", handleGlobalError)
})

onUnmounted(() => {
  window.removeEventListener("error", handleGlobalError)
})

// ─── 派生: 按 group 分类 ───
const standardItems = computed(() => store.activityItems.filter((it) => !it.route && !['ai-more', 'ai-chat', 'ai-studio'].includes(it.id)))
const aiItems = computed(() => store.activityItems.filter((it) => !!it.route))
</script>

<template>
  <!-- ═══ ActivityBar — VSCode activitybarPart (48px fixed) ═══ -->
  <aside
    class="activity-bar shrink-0 w-12 h-full flex flex-col items-center z-20"
    :style="{
      background: 'var(--color-activity-bg)',
      borderRight: '1px solid var(--color-ide-border)',
    }"
    role="toolbar"
    aria-label="活动栏"
  >
    <!-- ─── 顶部 Logo / 资源管理器 (固定第一项) ─── -->
    <button
      class="activity-item group relative w-full h-10 flex items-center justify-center transition-colors"
      :class="activeItemId === 'explorer' ? 'text-white' : 'text-[var(--color-ide-text-dim)]/40'"
      title="资源管理器 (Ctrl+Shift+E)"
      aria-label="资源管理器"
      @click="onActivityClick('explorer')"
    >
      <div v-if="activeItemId === 'explorer'" class="activity-indicator absolute left-0" />
      <span class="w-5 h-5 inline-flex items-center justify-center" v-html="iconSvgs['Files'] || ''" />
      <span class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
            :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }">
        资源管理器
      </span>
    </button>

    <!-- 分隔线 -->
    <div class="separator" />

    <!-- ─── 中部: 标准视图 (可拖拽重排, 可滚动) ─── -->
    <div class="flex flex-col w-full overflow-y-auto activity-scroll" style="max-height: calc(100vh - 260px)">
      <button
        v-for="item in standardItems"
        :key="item.id"
        class="activity-item group relative w-full h-10 flex items-center justify-center transition-colors"
        :class="item.id === activeItemId ? 'text-white' : 'text-[var(--color-ide-text-dim)]/40'"
        :title="item.label"
        :aria-label="item.label"
        :aria-pressed="item.id === activeItemId"
        draggable="true"
        @click="onActivityClick(item.id)"
        @dragstart="onDragStart($event, item.id)"
        @dragover="onDragOver($event, item.id)"
        @dragleave="onDragLeave"
        @drop="onDrop($event, item.id)"
      >
        <div v-if="item.id === activeItemId" class="activity-indicator absolute left-0" />

        <!-- 拖拽指示器 -->
        <div
          v-if="dragOverItemId === item.id && dragItemId !== item.id"
          class="absolute top-0 left-1 right-1 z-10"
          style="height: 2px; background: var(--color-ide-accent); border-radius: 1px"
        />

        <span class="w-5 h-5 inline-flex items-center justify-center" v-html="iconSvgs[item.icon] || ''" />

        <span class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
              :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }">
          {{ item.label }}
        </span>

        <span
          v-if="item.badge"
          class="activity-badge absolute top-1.5 right-1 min-w-[16px] h-[18px] flex items-center justify-center text-[10px] font-bold text-white rounded-full px-1"
          :style="{ background: 'var(--color-ide-accent)' }"
        >
          {{ item.badge }}
        </span>
      </button>
    </div>

    <!-- 分隔线 -->
    <div class="separator" />

    <!-- ─── AI 快捷工具 (ai-chat → ChatPanel, ai-studio → StudioPanel) ─── -->
    <div class="flex flex-col w-full">
      <button
        class="activity-item group relative w-full h-10 flex items-center justify-center transition-colors"
        :class="activeItemId === 'ai-chat' ? 'text-white ai-active' : 'text-[var(--color-ide-text-dim)]/40'"
        title="AI 对话"
        aria-label="AI 对话"
        @click="onActivityClick('ai-chat')"
      >
        <div v-if="activeItemId === 'ai-chat'" class="activity-indicator absolute left-0 ai-indicator" />
        <span class="w-5 h-5 inline-flex items-center justify-center" v-html="iconSvgs['MessageSquare'] || ''" />
        <span class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
              :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }">
          AI 对话
        </span>
      </button>
      <button
        class="activity-item group relative w-full h-10 flex items-center justify-center transition-colors"
        :class="activeItemId === 'ai-studio' ? 'text-white ai-active' : 'text-[var(--color-ide-text-dim)]/40'"
        title="AI Studio 面板"
        aria-label="AI Studio 面板"
        @click="onActivityClick('ai-studio')"
      >
        <div v-if="activeItemId === 'ai-studio'" class="activity-indicator absolute left-0 ai-indicator" />
        <span class="w-5 h-5 inline-flex items-center justify-center" v-html="iconSvgs['LayoutDashboard'] || ''" />
        <span class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
              :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }">
          AI Studio 面板
        </span>
      </button>
    </div>

    <!-- 分隔线 -->
    <div class="separator" />

    <!-- ─── AI 工具分组 (固定顺序, 不可拖拽, 可滚动) ─── -->
    <div class="flex flex-col w-full overflow-y-auto activity-scroll" style="max-height: calc(100vh - 360px)">
      <button
        v-for="item in aiItems"
        :key="item.id"
        class="activity-item group relative w-full h-10 flex items-center justify-center transition-colors"
        :class="item.id === activeItemId ? 'text-white ai-active' : 'text-[var(--color-ide-text-dim)]/40'"
        :title="item.label"
        :aria-label="item.label"
        :aria-pressed="item.id === activeItemId"
        @click="onActivityClick(item.id)"
      >
        <div v-if="item.id === activeItemId" class="activity-indicator absolute left-0 ai-indicator" />
        <span class="w-5 h-5 inline-flex items-center justify-center" v-html="iconSvgs[item.icon] || ''" />
        <span class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
              :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }">
          {{ item.label }}
        </span>
      </button>
    </div>

    <!-- 弹性空间 -->
    <div class="flex-1" />

    <!-- ─── 底部管理 ─── -->
    <div class="w-full" style="border-top: 1px solid var(--color-ide-border)">
      <button
        class="activity-item group relative w-full h-10 flex items-center justify-center transition-colors"
        :class="activeItemId === 'settings' ? 'text-white' : 'text-[var(--color-ide-text-dim)]/40'"
        title="管理 (Ctrl+,)"
        aria-label="管理设置"
        @click="onActivityClick('settings')"
      >
        <div v-if="activeItemId === 'settings'" class="activity-indicator absolute left-0" />
        <Settings :size="20" />
        <span class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
              :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }">
          管理
        </span>
      </button>
    </div>
  </aside>
</template>

<style scoped>
/* ═══ ActivityBar ═══ */
.activity-bar {
  contain: layout style;
  user-select: none;
  -webkit-user-select: none;
  --ai-accent: rgba(139, 92, 246, 1);
  --ai-accent-bg: rgba(139, 92, 246, 0.1);
  --ai-accent-glow: rgba(139, 92, 246, 0.5);
}

/* ── Item 基础 ── */
.activity-item {
  outline: none !important;
  appearance: none;
  -webkit-appearance: none;
  -moz-appearance: none;
  border: 0;
  background: transparent;
  padding: 0;
  margin: 0;
  cursor: pointer;
  position: relative;
}
.activity-item:focus,
.activity-item:focus-visible,
.activity-item:active,
.activity-item:hover:active {
  outline: none !important;
  background: transparent;
  box-shadow: none;
}
.activity-item::-moz-focus-inner { border: 0; }

/* ── Hover 态 ── */
.activity-item:hover {
  color: var(--color-ide-text) !important;
}

/* ── Active 指示器 ── */
.activity-indicator {
  width: 2px;
  height: 24px;
  border-radius: 0 2px 2px 0;
  background: var(--color-ide-text-bright);
  transition: all 0.15s cubic-bezier(0.16, 1, 0.3, 1);
  z-index: 1;
  pointer-events: none;
}

/* ── AI 工具激活指示器: 紫色高亮 (与 AI 主题一致) ── */
.activity-indicator.ai-indicator,
.activity-indicator.absolute.left-0.ai-indicator {
  background: var(--ai-accent);
  box-shadow: 0 0 8px var(--ai-accent-glow);
}
.ai-active {
  background: linear-gradient(90deg, var(--ai-accent-bg), transparent 50%) !important;
}

/* ── Tooltip ── */
.activity-tooltip {
  transition: opacity 0.12s ease;
}

/* ── Badge ── */
.activity-badge {
  line-height: 1;
  pointer-events: none;
}

/* ── 分隔线 ── */
.separator {
  width: 24px;
  height: 1px;
  background: var(--color-ide-border);
  margin: 4px 0;
}

/* ── 滚动条（隐藏原生滚动条但保留滚动能力） ── */
.activity-scroll {
  scrollbar-width: none;          /* Firefox */
  -ms-overflow-style: none;       /* IE/Edge */
  scroll-behavior: smooth;
}
.activity-scroll::-webkit-scrollbar {
  display: none;                  /* Chrome/Safari */
}
</style>
