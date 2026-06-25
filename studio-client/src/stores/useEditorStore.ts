// ============================================
// Editor Store — tabs, cursor, file open/save
// ============================================
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { CursorPosition, EditorTab } from '@/types/ide'
import { generateDemoContent, getLanguageFromPath, isTauriEnv, uid } from './shared'
import { useFileTreeStore } from './useFileTreeStore'

export const useEditorStore = defineStore('editor', () => {
  const tabs = ref<EditorTab[]>([])
  const activeTabId = ref<string | null>(null)

  const activeTab = computed(() => tabs.value.find((t) => t.id === activeTabId.value) ?? null)
  const sortedTabs = computed(() => [...tabs.value].sort((a, b) => a.order - b.order))

  async function openFile(filePath: string): Promise<void> {
    const existing = tabs.value.find((t) => t.filePath === filePath)
    if (existing) {
      activeTabId.value = existing.id
      return
    }

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
    }

    tabs.value.push(newTab)
    activeTabId.value = newTab.id
    useFileTreeStore().selectedFilePath = filePath
  }

  function createUntitledTab(): void {
    const newTab: EditorTab = {
      id: uid(),
      label: `未命名-${tabs.value.filter((t) => !t.filePath).length + 1}`,
      content: '',
      originalContent: '',
      modified: false,
      language: 'plaintext',
      order: tabs.value.length,
    }
    tabs.value.push(newTab)
    activeTabId.value = newTab.id
  }

  function closeTab(tabId: string): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId)
    if (idx === -1) return
    tabs.value.splice(idx, 1)
    if (activeTabId.value === tabId) {
      if (tabs.value.length > 0) {
        const nextIdx = Math.min(idx, tabs.value.length - 1)
        activeTabId.value = sortedTabs.value[nextIdx]?.id ?? null
      } else {
        activeTabId.value = null
      }
    }
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
    openFile,
    createUntitledTab,
    closeTab,
    updateActiveTabContent,
    saveActiveFile,
    saveAllFiles,
    cursorPosition,
    updateCursorPosition,
  }
})
