// ============================================
// Layout Store — UI layout dimensions & panels
// ============================================
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { ActivityItem, IDELayoutState, RightPanelView } from '@/types/ide'
import { useGitStore } from './useGitStore'

export const useLayoutStore = defineStore('layout', () => {
  const layout = ref<IDELayoutState>({
    sidebarWidth: 260,
    fileTreeVisible: true,
    rightPanelWidth: 320,
    rightPanelVisible: true,
    bottomPanelHeight: 180,
    bottomPanelVisible: true,
    activityBarVisible: true,
    statusBarVisible: true,
    menuBarVisible: false,
  })

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
  }
})
