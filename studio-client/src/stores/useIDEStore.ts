// ============================================
// IDE Store — Backward-compatible facade
// Composes: layout | fileTree | editor | terminal | search | git
//
// IMPORTANT: Uses storeToRefs to preserve reactive links to sub-stores.
// Direct property access like `fileTreeStore.fileTree` captures the
// unwrapped initial value in Pinia setup stores, breaking reactivity.
// ============================================
import { defineStore, storeToRefs } from 'pinia'
import { useDebugStore } from './useDebugStore'
import { useEditorStore } from './useEditorStore'
import { useFileTreeStore } from './useFileTreeStore'
import { useGitStore } from './useGitStore'
import { useLayoutStore } from './useLayoutStore'
import { useSearchStore } from './useSearchStore'
import { useTerminalStore } from './useTerminalStore'
import { useCommentsStore } from './useCommentsStore'

export const useIDEStore = defineStore('ide', () => {
  const debugStore = useDebugStore()
  const layoutStore = useLayoutStore()
  const fileTreeStore = useFileTreeStore()
  const editorStore = useEditorStore()
  const terminalStore = useTerminalStore()
  const searchStore = useSearchStore()
  const gitStore = useGitStore()
  const commentsStore = useCommentsStore()

  // storeToRefs preserves reactive links to source stores
  // (skips methods, returns Ref<X> for state + getters)
  const db = storeToRefs(debugStore)
  const ly = storeToRefs(layoutStore)
  const ft = storeToRefs(fileTreeStore)
  const ed = storeToRefs(editorStore)
  const tm = storeToRefs(terminalStore)
  const sr = storeToRefs(searchStore)
  const gi = storeToRefs(gitStore)
  const cm = storeToRefs(commentsStore)

  /** Refresh git status — cross-store: needs workspaceRoot from fileTree */
  async function refreshGitStatus(): Promise<void> {
    await gitStore.refreshGitStatus(fileTreeStore.workspaceRoot)
  }

  return {
    // Debug (Session 36: 共享调试状态供 FloatingDebugToolbar + DebugPanel 使用)
    debugIsRunning: db.isRunning,
    debugIsPaused: db.isPaused,
    debugBreakpoints: db.breakpoints,
    debugStackFrames: db.stackFrames,
    debugVariables: db.variables,
    debugActiveStackFrame: db.activeStackFrame,
    debugStart: debugStore.startDebug,
    debugStop: debugStore.stopDebug,
    debugRestart: debugStore.restartDebug,
    debugPause: debugStore.pauseDebug,
    debugResume: debugStore.resumeDebug,
    debugStepOver: debugStore.stepOver,
    debugStepInto: debugStore.stepInto,
    debugStepOut: debugStore.stepOut,
    debugAddBreakpoint: debugStore.addBreakpointAtLine,

    // Layout (state + getters via storeToRefs, methods directly)
    layout: ly.layout,
    rightPanelView: ly.rightPanelView,
    bottomPanelView: ly.bottomPanelView,
    menuBarOpen: ly.menuBarOpen,
    activityItems: ly.activityItems,
    activeActivityItem: ly.activeActivityItem,
    showSettingsPanel: ly.showSettingsPanel,
    /** Session 35: Markdown 预览 */
    markdownPreviewVisible: ly.markdownPreviewVisible,
    resetLayout: layoutStore.resetLayout,
    focusWindow: layoutStore.focusWindow,
    toggleFullscreen: layoutStore.toggleFullscreen,
    zoomIn: layoutStore.zoomIn,
    zoomOut: layoutStore.zoomOut,
    resetZoom: layoutStore.resetZoom,
    openDevtools: layoutStore.openDevtools,
    // Session 57: Panel + View
    setPanelPosition: layoutStore.setPanelPosition,
    setPanelAlignment: layoutStore.setPanelAlignment,
    viewDescriptors: layoutStore.viewDescriptors,
    moveView: layoutStore.moveView,
    resetView: layoutStore.resetView,
    resetAllViews: layoutStore.resetAllViews,

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
    copyFileEntry: fileTreeStore.copyFileEntry,
    moveFileEntry: fileTreeStore.moveFileEntry,
    getFileInfo: fileTreeStore.getFileInfo,
    getRecentFiles: fileTreeStore.getRecentFiles,

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
    searchAvailable: sr.searchAvailable,
    toggleGlobalSearch: searchStore.toggleGlobalSearch,
    executeSearch: searchStore.executeSearch,
    executeReplace: searchStore.executeReplace,
    replaceInFile: searchStore.replaceInFile,

    // Git
    gitBranch: gi.gitBranch,
    gitAhead: gi.gitAhead,
    gitBehind: gi.gitBehind,
    gitChangedFiles: gi.gitChangedFiles,
    gitChanges: gi.gitChanges,
    gitStagedCount: gi.stagedCount,
    gitUnstagedCount: gi.unstagedCount,
    gitAvailable: gi.gitAvailable,
    commitLog: gi.commitLog,
    branches: gi.branches,
    diffData: gi.diffData,
    stagedFiles: gi.stagedFiles,
    unstagedFiles: gi.unstagedFiles,
    refreshGitStatus,
    gitStageFile: gitStore.stageFile,
    gitUnstageFile: gitStore.unstageFile,
    gitStageAll: gitStore.stageAll,
    gitUnstageAll: gitStore.unstageAll,
    gitCommit: gitStore.commit,
    gitPush: gitStore.push,
    gitPull: gitStore.pull,
    gitDiscard: gitStore.discardChanges,
    gitGetDiff: gitStore.getDiff,
    gitGetLog: gitStore.getLog,
    gitListBranches: gitStore.listBranches,
    gitCheckoutBranch: gitStore.checkoutBranch,
    gitStash: gitStore.stash,
    gitReset: gitStore.reset,

    // Comments (Session 39: 代码评审)
    commentThreads: cm.comments,
    commentUnresolvedCount: cm.unresolvedCount,
    commentAddThread: commentsStore.addComment,
    commentAddReply: commentsStore.addReply,
    commentToggleResolve: commentsStore.toggleResolve,
    commentDeleteThread: commentsStore.deleteComment,
    commentEditThread: commentsStore.editComment,
    commentAcceptSuggestion: commentsStore.acceptSuggestion,
    commentFileThreads: commentsStore.forFile,
    commentLineThreads: commentsStore.forLine,
    commentFileUnresolved: commentsStore.fileUnresolvedCount,
  }
})
