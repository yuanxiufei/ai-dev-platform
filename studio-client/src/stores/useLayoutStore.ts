// ============================================
// Layout Store — UI layout dimensions & panels (Zed Dock 风格持久化)
// ============================================
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { ActivityItem, IDELayoutState, RightPanelView } from '@/types/ide'
import { useGitStore } from './useGitStore'

const LAYOUT_STORAGE_KEY = "ide_layout_v2"

/** 🆕 从 localStorage 恢复布局 (Zed Dock 风格持久化) */
function loadLayout(): Partial<IDELayoutState> {
  try {
    const raw = localStorage.getItem(LAYOUT_STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return {}
}

/** 🆕 保存布局到 localStorage */
function saveLayout(state: IDELayoutState) {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({
      sidebarWidth: state.sidebarWidth,
      rightPanelWidth: state.rightPanelWidth,
      bottomPanelHeight: state.bottomPanelHeight,
      fileTreeVisible: state.fileTreeVisible,
      rightPanelVisible: state.rightPanelVisible,
      bottomPanelVisible: state.bottomPanelVisible,
    }))
  } catch { /* ignore */ }
}

const defaultLayout: IDELayoutState = {
  sidebarWidth: 260,
  fileTreeVisible: true,
  rightPanelWidth: 320,
  rightPanelVisible: true,
  bottomPanelHeight: 180,
  bottomPanelVisible: true,
  activityBarVisible: true,
  statusBarVisible: true,
  menuBarVisible: true,
}

export const useLayoutStore = defineStore('layout', () => {
  const savedLayout = loadLayout()
  const layout = ref<IDELayoutState>({ ...defaultLayout, ...savedLayout })

  // 🆕 尺寸变化时自动持久化 (debounced)
  let saveTimeout: ReturnType<typeof setTimeout> | null = null
  watch(
    () => ({
      sw: layout.value.sidebarWidth,
      rw: layout.value.rightPanelWidth,
      bh: layout.value.bottomPanelHeight,
      ft: layout.value.fileTreeVisible,
      rp: layout.value.rightPanelVisible,
      bp: layout.value.bottomPanelVisible,
    }),
    () => {
      if (saveTimeout) clearTimeout(saveTimeout)
      saveTimeout = setTimeout(() => saveLayout(layout.value), 500)
    },
    { deep: true },
  )

  /** 🆕 重置布局到默认值 */
  function resetLayout() {
    Object.assign(layout.value, defaultLayout)
    try { localStorage.removeItem(LAYOUT_STORAGE_KEY) } catch { /* ignore */ }
  }

  const rightPanelView = ref<RightPanelView>('chat')
  const menuBarOpen = ref<string | null>(null)
  const activeActivityItem = ref('explorer')

  const activityItems = computed<ActivityItem[]>(() => {
    const gitStore = useGitStore()
    return [
      { id: 'explorer', icon: 'Files', label: '资源管理器', badge: undefined },
      { id: 'studio', icon: 'Sparkles', label: 'AI Studio', badge: undefined },
      { id: 'search', icon: 'Search', label: '搜索', badge: undefined },
      {
        id: 'git',
        icon: 'GitBranch',
        label: '源代码管理',
        badge: gitStore.gitChangedFiles > 0 ? String(gitStore.gitChangedFiles) : undefined,
      },
      { id: 'debug', icon: 'Bug', label: '运行和调试', badge: undefined },
      { id: 'extensions', icon: 'Blocks', label: '扩展', badge: undefined },
    ]
  })

  return {
    layout,
    rightPanelView,
    menuBarOpen,
    activityItems,
    activeActivityItem,
    resetLayout,
  }
})
