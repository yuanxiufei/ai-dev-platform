// ============================================
// CodeBuddy IDE — Type Definitions
// ============================================

/** File system entry (file or directory) */
export interface FileEntry {
  name: string
  path: string
  isDir: boolean
  children?: FileEntry[]
  language?: string
  icon?: string
  expanded?: boolean
  mtime?: number
  size?: number
}

/** Editor tab state */
export interface EditorTab {
  id: string
  label: string
  filePath?: string
  language?: string
  content: string
  modified: boolean
  originalContent: string
  order: number
}

/** Terminal session */
export interface TerminalSession {
  id: string
  title: string
  shellType: "powershell" | "cmd" | "bash" | "zsh"
  lines: TerminalLine[]
  active: boolean
  cwd: string
}

/** Single terminal output line */
export interface TerminalLine {
  id: string
  text: string
  type: "input" | "output" | "error" | "success" | "info"
  timestamp: number
  /** Session 10: optional pre-parsed ANSI segments */
  segments?: TerminalSegment[]
}

/** Session 10: ANSI-parsed segment for rich terminal rendering */
export interface TerminalSegment {
  text: string
  fg?: string
  bg?: string
  bold?: boolean
  dim?: boolean
  italic?: boolean
  underline?: boolean
}

/** Output panel channel */
export interface OutputChannel {
  id: string
  name: string
  lines: string[]
  visible: boolean
}

/** Search result match */
export interface SearchResult {
  file: string
  line: number
  column: number
  lineText: string
  matchLength: number
  matches: Array<{ start: number; end: number }>
}

/** Global search state */
export interface SearchState {
  query: string
  replaceQuery: string
  includePattern: string
  excludePattern: string
  results: SearchResult[]
  searching: boolean
  caseSensitive: boolean
  wholeWord: boolean
  useRegex: boolean
  currentResultIndex: number
}

/** Right panel view mode */
export type RightPanelView = "output" | "terminal" | "debug" | "chat"

/** Sidebar / Activity bar icon entry */
export interface ActivityItem {
  id: string
  icon: string
  label: string
  badge?: number | string
}

/** Menu bar structure */
export interface MenuItem {
  label: string
  shortcut?: string
  action?: () => void
  disabled?: boolean
  checked?: boolean
  separator?: boolean
  children?: MenuItem
}

/** Cursor position info */
export interface CursorPosition {
  line: number
  column: number
  totalLines: number
  selectedChars: number
  encoding: string
  eol: "\n" | "\r\n"
  languageId: string
  fileType: string
  indentSize: number
  indentUsesTabs: boolean
}

/** IDE layout dimensions (persisted) */
export interface IDELayoutState {
  sidebarWidth: number
  fileTreeVisible: boolean
  rightPanelWidth: number
  rightPanelVisible: boolean
  bottomPanelHeight: number
  bottomPanelVisible: boolean
  activityBarVisible: boolean
  statusBarVisible: boolean
  menuBarVisible: boolean
}
