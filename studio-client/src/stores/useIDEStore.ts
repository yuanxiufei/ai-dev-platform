// ============================================
// IDE Store — Backward-compatible facade
// Composes: layout | fileTree | editor | terminal | search | git
// ============================================
import { defineStore } from 'pinia'
import { useEditorStore } from './useEditorStore'
import { useFileTreeStore } from './useFileTreeStore'
import { useGitStore } from './useGitStore'
import { useLayoutStore } from './useLayoutStore'
import { useSearchStore } from './useSearchStore'
import { useTerminalStore } from './useTerminalStore'

export const useIDEStore = defineStore('ide', () => {
  const layoutStore = useLayoutStore()
  const fileTreeStore = useFileTreeStore()
  const editorStore = useEditorStore()
  const terminalStore = useTerminalStore()
  const searchStore = useSearchStore()
  const gitStore = useGitStore()

  /** Refresh git status — cross-store: needs workspaceRoot from fileTree */
  async function refreshGitStatus(): Promise<void> {
    await gitStore.refreshGitStatus(fileTreeStore.workspaceRoot)
  }

  return {
    // Layout
    layout: layoutStore.layout,
    rightPanelView: layoutStore.rightPanelView,
    menuBarOpen: layoutStore.menuBarOpen,
    activityItems: layoutStore.activityItems,
    activeActivityItem: layoutStore.activeActivityItem,
    resetLayout: layoutStore.resetLayout,

    // File Tree
    workspaceRoot: fileTreeStore.workspaceRoot,
    fileTree: fileTreeStore.fileTree,
    selectedFilePath: fileTreeStore.selectedFilePath,
    initFileTree: fileTreeStore.initFileTree,
    toggleExpand: fileTreeStore.toggleExpand,
    findEntryByPath: fileTreeStore.findEntryByPath,
    findParentEntry: fileTreeStore.findParentEntry,
    refreshEntry: fileTreeStore.refreshEntry,
    createFileEntry: fileTreeStore.createFileEntry,
    createFolderEntry: fileTreeStore.createFolderEntry,
    deleteFileEntry: fileTreeStore.deleteFileEntry,
    renameFileEntry: fileTreeStore.renameFileEntry,

    // Editor
    tabs: editorStore.tabs,
    activeTabId: editorStore.activeTabId,
    activeTab: editorStore.activeTab,
    sortedTabs: editorStore.sortedTabs,
    openFile: editorStore.openFile,
    createUntitledTab: editorStore.createUntitledTab,
    closeTab: editorStore.closeTab,
    updateActiveTabContent: editorStore.updateActiveTabContent,
    saveActiveFile: editorStore.saveActiveFile,
    saveAllFiles: editorStore.saveAllFiles,
    cursorPosition: editorStore.cursorPosition,
    updateCursorPosition: editorStore.updateCursorPosition,

    // Terminal
    terminalSessions: terminalStore.terminalSessions,
    activeTerminalId: terminalStore.activeTerminalId,
    addTerminalLine: terminalStore.addTerminalLine,
    outputChannels: terminalStore.outputChannels,
    activeOutputChannel: terminalStore.activeOutputChannel,
    addOutputLine: terminalStore.addOutputLine,

    // Search
    searchState: searchStore.searchState,
    showGlobalSearch: searchStore.showGlobalSearch,
    toggleGlobalSearch: searchStore.toggleGlobalSearch,

    // Git
    gitBranch: gitStore.gitBranch,
    gitAhead: gitStore.gitAhead,
    gitBehind: gitStore.gitBehind,
    gitChangedFiles: gitStore.gitChangedFiles,
    refreshGitStatus,
  }
})
