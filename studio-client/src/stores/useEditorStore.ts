// ============================================
// Editor Store — tabs, cursor, file open/save
// ============================================
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { CursorPosition, EditorGroup, EditorTab } from '@/types/ide'
import { generateDemoContent, getLanguageFromPath, isTauriEnv, uid } from './shared'
import { useFileTreeStore } from './useFileTreeStore'

export const useEditorStore = defineStore('editor', () => {
  const tabs = ref<EditorTab[]>([])
  const activeTabId = ref<string | null>(null)
  /** Session 23: VSCode 多编辑器组（分屏） */
  const groups = ref<EditorGroup[]>([])
  const activeGroupId = ref<string | null>(null)

  /**
   * 创建默认编辑器组（首次打开文件时自动创建）
   */
  function _ensureDefaultGroup(): void {
    if (groups.value.length === 0) {
      const g: EditorGroup = { id: uid(), tabs: [], activeTabId: null, widthRatio: 1 }
      groups.value.push(g)
      activeGroupId.value = g.id
    }
  }

  /**
   * 获取当前活跃的编辑器组
   */
  const activeGroup = computed(() => groups.value.find(g => g.id === activeGroupId.value) ?? null)

  /**
   * 获取某个组内的所有标签页
   */
  function getGroupTabs(groupId: string): EditorTab[] {
    const g = groups.value.find(gr => gr.id === groupId)
    if (!g) return []
    return g.tabs.map(tid => tabs.value.find(t => t.id === tid)).filter(Boolean) as EditorTab[]
  }

  /**
   * 将 tab 加入指定组
   */
  function _addTabToGroup(tabId: string, groupId: string): void {
    const g = groups.value.find(gr => gr.id === groupId)
    if (!g) return
    if (!g.tabs.includes(tabId)) {
      g.tabs.push(tabId)
    }
    g.activeTabId = tabId
    activeGroupId.value = groupId
  }

  /** Session 23: 分割编辑器（向右分屏） */
  function splitEditor(direction: "right" | "down" = "right"): void {
    const currentGroup = activeGroup.value
    if (!currentGroup) return

    // 如果当前组只有一个tab且没有打开文件，不分割
    if (currentGroup.tabs.length === 0) return

    const newGroup: EditorGroup = {
      id: uid(),
      tabs: [...currentGroup.tabs],
      activeTabId: currentGroup.activeTabId,
      widthRatio: direction === "right" ? 0.5 : undefined,
      heightRatio: direction === "down" ? 0.5 : undefined,
    }

    // 为原有的tab创建副本tab（每个组独立的tab实例）
    const origTabIds = [...currentGroup.tabs]
    const newTabIds: string[] = []
    for (const tid of origTabIds) {
      const orig = tabs.value.find(t => t.id === tid)
      if (!orig) continue
      const dup: EditorTab = {
        id: uid(),
        label: orig.label,
        filePath: orig.filePath,
        language: orig.language,
        content: orig.content,
        originalContent: orig.originalContent,
        modified: orig.modified,
        order: tabs.value.length,
        groupId: newGroup.id,
      }
      tabs.value.push(dup)
      newTabIds.push(dup.id)
      // 设置原tab的groupId
      orig.groupId = currentGroup.id
    }
    newGroup.tabs = newTabIds
    newGroup.activeTabId = newTabIds[0] ?? null

    // 调整宽度比例
    const n = groups.value.length + 1
    groups.value.forEach(g => { g.widthRatio = 1 / n })
    newGroup.widthRatio = 1 / n

    groups.value.push(newGroup)
    activeGroupId.value = newGroup.id
    activeTabId.value = newGroup.activeTabId
  }

  /** Session 23: 关闭编辑器组 */
  function closeGroup(groupId: string): void {
    if (groups.value.length <= 1) return  // 不能关闭最后一个组
    const g = groups.value.find(gr => gr.id === groupId)
    if (!g) return

    // 移除该组的所有tab
    for (const tid of g.tabs) {
      const idx = tabs.value.findIndex(t => t.id === tid)
      if (idx !== -1) tabs.value.splice(idx, 1)
    }
    // 移除组
    const gi = groups.value.findIndex(gr => gr.id === groupId)
    groups.value.splice(gi, 1)

    // 重新调整宽度
    const n = groups.value.length
    groups.value.forEach(gr => { gr.widthRatio = 1 / n })

    // 切换活跃组
    if (activeGroupId.value === groupId) {
      const nextGroup = groups.value[Math.min(gi, groups.value.length - 1)]
      activeGroupId.value = nextGroup?.id ?? null
      activeTabId.value = nextGroup?.activeTabId ?? null
    }
  }

  /** Session 23: 移动tab到指定组 */
  function moveTabToGroup(tabId: string, targetGroupId: string): void {
    const tab = tabs.value.find(t => t.id === tabId)
    if (!tab) return

    const targetGroup = groups.value.find(g => g.id === targetGroupId)
    if (!targetGroup) return
    if (targetGroup.tabs.includes(tabId)) return  // 已在目标组

    // 从原组移除
    for (const g of groups.value) {
      const idx = g.tabs.indexOf(tabId)
      if (idx !== -1) {
        g.tabs.splice(idx, 1)
        // 如果移除的是活跃tab，选下一个
        if (g.activeTabId === tabId) {
          g.activeTabId = g.tabs[0] ?? null
        }
        break
      }
    }

    // 加入目标组
    targetGroup.tabs.push(tabId)
    targetGroup.activeTabId = tabId
    activeGroupId.value = targetGroupId

    // 如果原组没有tab了，关闭该组
    for (const g of groups.value) {
      if (g.tabs.length === 0 && groups.value.length > 1) {
        closeGroup(g.id)
        break
      }
    }
  }

  const activeTab = computed(() => tabs.value.find((t) => t.id === activeTabId.value) ?? null)
  const sortedTabs = computed(() => [...tabs.value].sort((a, b) => a.order - b.order))

  async function openFile(filePath: string): Promise<void> {
    const existing = tabs.value.find((t) => t.filePath === filePath)
    if (existing) {
      activeTabId.value = existing.id
      // 找到并激活该tab所在的组
      for (const g of groups.value) {
        if (g.tabs.includes(existing.id)) {
          activeGroupId.value = g.id
          break
        }
      }
      return
    }

    _ensureDefaultGroup()

    const label = filePath.split(/[/\\]/).pop() ?? filePath
    const language = getLanguageFromPath(filePath)
    let content = generateDemoContent(label, language)

    if (isTauriEnv()) {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        content = await invoke<string>('read_file', { path: filePath })
      } catch (e) {
        console.warn(`[IDE] Failed to read file: ${filePath}`, e)
      }
    }

    const newTab: EditorTab = {
      id: uid(),
      label,
      filePath,
      language,
      content,
      originalContent: content,
      modified: false,
      order: tabs.value.length,
      groupId: activeGroupId.value ?? undefined,
    }

    tabs.value.push(newTab)
    activeTabId.value = newTab.id
    _addTabToGroup(newTab.id, activeGroupId.value!)
    useFileTreeStore().selectedFilePath = filePath
  }

  function createUntitledTab(): void {
    _ensureDefaultGroup()
    const newTab: EditorTab = {
      id: uid(),
      label: `未命名-${tabs.value.filter((t) => !t.filePath).length + 1}`,
      content: '',
      originalContent: '',
      modified: false,
      language: 'plaintext',
      order: tabs.value.length,
      groupId: activeGroupId.value ?? undefined,
    }
    tabs.value.push(newTab)
    activeTabId.value = newTab.id
    _addTabToGroup(newTab.id, activeGroupId.value!)
  }

  function closeTab(tabId: string): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId)
    if (idx === -1) return
    tabs.value.splice(idx, 1)

    // 从组中移除
    for (const g of groups.value) {
      const gi = g.tabs.indexOf(tabId)
      if (gi !== -1) {
        g.tabs.splice(gi, 1)
        if (g.activeTabId === tabId) {
          g.activeTabId = g.tabs[gi] ?? g.tabs[0] ?? null
        }
        // 如果该组没有tab了且不止一个组，关闭该组
        if (g.tabs.length === 0 && groups.value.length > 1) {
          closeGroup(g.id)
          break
        }
      }
    }

    if (activeTabId.value === tabId) {
      activeTabId.value = activeGroup.value?.activeTabId ?? tabs.value[0]?.id ?? null
    }
  }

  /** VSCode: Close all tabs to the right of the given tab */
  function closeToRight(tabId: string): void {
    const sortedIds = sortedTabs.value.map(t => t.id)
    const targetIdx = sortedIds.indexOf(tabId)
    if (targetIdx === -1) return
    const toClose = sortedIds.slice(targetIdx + 1).filter(id => !tabs.value.find(t => t.id === id)?.pinned)
    for (const id of toClose) closeTab(id)
  }

  /** VSCode: Close all other tabs, keeping pinned tabs */
  function closeOthers(tabId: string): void {
    const toClose = tabs.value.filter(t => t.id !== tabId && !t.pinned).map(t => t.id)
    for (const id of toClose) closeTab(id)
  }

  /** VSCode: Close all tabs (respecting pinned tabs) */
  function closeAll(): void {
    const toClose = tabs.value.filter(t => !t.pinned).map(t => t.id)
    for (const id of toClose) closeTab(id)
  }

  /** VSCode: Pin/unpin tab (stays left-aligned, won't close with bulk operations) */
  function pinTab(tabId: string): void {
    const tab = tabs.value.find(t => t.id === tabId)
    if (tab) tab.pinned = !tab.pinned
  }

  /** VSCode: Duplicate tab (split to new editor group if not already split) */
  function duplicateTab(tabId: string): void {
    const tab = tabs.value.find(t => t.id === tabId)
    if (!tab) return

    // 创建副本 tab
    const newTab: EditorTab = {
      id: uid(),
      label: `${tab.label} (副本)`,
      filePath: tab.filePath,
      language: tab.language,
      content: tab.content,
      originalContent: tab.originalContent,
      modified: tab.modified,
      pinned: false,
      order: tabs.value.length,
    }
    tabs.value.push(newTab)

    // Session 23: 如果还不存在第二个组，自动分屏
    if (groups.value.length === 1) {
      const targetGroup = groups.value[0]
      // 当前组已有多个tab时，把新tab放到新组
      const newGroup: EditorGroup = {
        id: uid(),
        tabs: [newTab.id],
        activeTabId: newTab.id,
        widthRatio: 0.5,
      }
      // 调整宽度
      groups.value.forEach(g => { g.widthRatio = 0.5 })
      newTab.groupId = newGroup.id
      groups.value.push(newGroup)
      activeGroupId.value = newGroup.id
    } else {
      // 否则添加到活跃组
      activeGroup.value?.tabs.push(newTab.id)
      newTab.groupId = activeGroupId.value ?? undefined
    }

    activeTabId.value = newTab.id
  }

  /** VSCode: Reveal file in file tree (select the file path) */
  function revealInTree(filePath: string): void {
    useFileTreeStore().selectedFilePath = filePath
    useFileTreeStore().expandToPath(filePath)
  }

  function updateActiveTabContent(content: string): void {
    const tab = activeTab.value
    if (!tab) return
    tab.content = content
    tab.modified = content !== tab.originalContent
  }

  async function saveActiveFile(): Promise<boolean> {
    const tab = activeTab.value
    if (!tab?.filePath) return false
    try {
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('write_file', { path: tab.filePath, content: tab.content })
      }
      tab.originalContent = tab.content
      tab.modified = false
      return true
    } catch (e) {
      console.warn(`[IDE] Failed to save: ${tab.filePath}`, e)
      return false
    }
  }

  async function saveAllFiles(): Promise<void> {
    for (const tab of tabs.value) {
      if (tab.modified && tab.filePath) {
        try {
          if (isTauriEnv()) {
            const { invoke } = await import('@tauri-apps/api/core')
            await invoke('write_file', {
              path: tab.filePath,
              content: tab.content,
            })
          }
          tab.originalContent = tab.content
          tab.modified = false
        } catch (e) {
          console.warn(`[IDE] Failed to save: ${tab.filePath}`, e)
        }
      }
    }
  }

  const cursorPosition = ref<CursorPosition>({
    line: 1,
    column: 1,
    totalLines: 1,
    selectedChars: 0,
    encoding: 'UTF-8',
    eol: '\n',
    languageId: 'plaintext',
    fileType: '',
    indentSize: 2,
    indentUsesTabs: false,
  })

  function updateCursorPosition(pos: Partial<CursorPosition>): void {
    Object.assign(cursorPosition.value, pos)
  }

  return {
    tabs,
    activeTabId,
    activeTab,
    sortedTabs,
    /** Session 23: 多编辑器组 */
    groups,
    activeGroupId,
    activeGroup,
    getGroupTabs,
    splitEditor,
    closeGroup,
    moveTabToGroup,
    openFile,
    createUntitledTab,
    closeTab,
    closeToRight,
    closeOthers,
    closeAll,
    pinTab,
    duplicateTab,
    revealInTree,
    updateActiveTabContent,
    saveActiveFile,
    saveAllFiles,
    cursorPosition,
    updateCursorPosition,
  }
})
