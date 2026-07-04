// ============================================
// IDE Store — Backward-compatible facade
// Composes: layout | fileTree | editor | terminal | search | git
//
// IMPORTANT: Uses storeToRefs to preserve reactive links to sub-stores.
// Direct property access like `fileTreeStore.fileTree` captures the
// unwrapped initial value in Pinia setup stores, breaking reactivity.
// ============================================
import { defineStore, storeToRefs } from 'pinia'
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

  // storeToRefs preserves reactive links to source stores
  // (skips methods, returns Ref<X> for state + getters)
  const ly = storeToRefs(layoutStore)
  const ft = storeToRefs(fileTreeStore)
  const ed = storeToRefs(editorStore)
  const tm = storeToRefs(terminalStore)
  const sr = storeToRefs(searchStore)
  const gi = storeToRefs(gitStore)

  /** Refresh git status — cross-store: needs workspaceRoot from fileTree */
  async function refreshGitStatus(): Promise<void> {
    await gitStore.refreshGitStatus(fileTreeStore.workspaceRoot)
  }

  return {
    // Layout (state + getters via storeToRefs, methods directly)
    layout: ly.layout,
    rightPanelView: ly.rightPanelView,
    bottomPanelView: ly.bottomPanelView,
    menuBarOpen: ly.menuBarOpen,
    activityItems: ly.activityItems,
    activeActivityItem: ly.activeActivityItem,
    showSettingsPanel: ly.showSettingsPanel,
    resetLayout: layoutStore.resetLayout,

    // File Tree
    workspaceRoot: ft.workspaceRoot,
    fileTree: ft.fileTree,
    selectedFilePath: ft.selectedFilePath,
    initFileTree: fileTreeStore.initFileTree,
    toggleExpand: fileTreeStore.toggleExpand,
    findEntryByPath: fileTreeStore.findEntryByPath,
    findParentEntry: fileTreeStore.findParentEntry,
    refreshEntry: fileTreeStore.refreshEntry,
    expandToPath: fileTreeStore.expandToPath,
    createFileEntry: fileTreeStore.createFileEntry,
    createFolderEntry: fileTreeStore.createFolderEntry,
    deleteFileEntry: fileTreeStore.deleteFileEntry,
    renameFileEntry: fileTreeStore.renameFileEntry,

    // Editor
    tabs: ed.tabs,
    activeTabId: ed.activeTabId,
    activeTab: ed.activeTab,
    sortedTabs: ed.sortedTabs,
    groups: ed.groups,
    activeGroupId: ed.activeGroupId,
    activeGroup: ed.activeGroup,
    openFile: editorStore.openFile,
    createUntitledTab: editorStore.createUntitledTab,
    closeTab: editorStore.closeTab,
    closeToRight: editorStore.closeToRight,
    closeOthers: editorStore.closeOthers,
    closeAll: editorStore.closeAll,
    pinTab: editorStore.pinTab,
    duplicateTab: editorStore.duplicateTab,
    splitEditor: editorStore.splitEditor,
    revealInTree: editorStore.revealInTree,
    updateActiveTabContent: editorStore.updateActiveTabContent,
    saveActiveFile: editorStore.saveActiveFile,
    saveAllFiles: editorStore.saveAllFiles,
    cursorPosition: ed.cursorPosition,
    updateCursorPosition: editorStore.updateCursorPosition,

    // Terminal
    terminalSessions: tm.terminalSessions,
    activeTerminalId: tm.activeTerminalId,
    createTerminal: terminalStore.createTerminal,
    closeTerminal: terminalStore.closeTerminal,
    switchToTerminal: terminalStore.switchToTerminal,
    duplicateTerminal: terminalStore.duplicateTerminal,
    renameTerminal: terminalStore.renameTerminal,
    addTerminalLine: terminalStore.addTerminalLine,
    outputChannels: tm.outputChannels,
    activeOutputChannel: tm.activeOutputChannel,
    addOutputLine: terminalStore.addOutputLine,
    executeCommandInTerminal: terminalStore.executeCommandInTerminal,

    // Search
    searchState: sr.searchState,
    showGlobalSearch: sr.showGlobalSearch,
    toggleGlobalSearch: searchStore.toggleGlobalSearch,

    // Git
    gitBranch: gi.gitBranch,
    gitAhead: gi.gitAhead,
    gitBehind: gi.gitBehind,
    gitChangedFiles: gi.gitChangedFiles,
    gitChanges: gi.gitChanges,
    gitStagedCount: gi.stagedCount,
    gitUnstagedCount: gi.unstagedCount,
    refreshGitStatus,
    gitStageFile: gitStore.stageFile,
    gitUnstageFile: gitStore.unstageFile,
    gitCommit: gitStore.commit,
    gitPush: gitStore.push,
    gitPull: gitStore.pull,
  }
})
