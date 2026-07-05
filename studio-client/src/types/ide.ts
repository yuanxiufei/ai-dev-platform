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
  /** VSCode: pinned tab (stays left-aligned, won't close with closeOthers) */
  pinned?: boolean
  /** Editor group id this tab belongs to */
  groupId?: string
}

/** VSCode style editor group (split panes) */
export interface EditorGroup {
  id: string
  tabs: string[]         // tab IDs
  activeTabId: string | null
  /** Ratio in horizontal split (0-1) */
  widthRatio?: number
  /** Ratio in vertical split (0-1) */
  heightRatio?: number
}

/** Terminal session */
export interface TerminalSession {
  id: string
  title: string
  shellType: "powershell" | "cmd" | "bash" | "zsh"
  lines: TerminalLine[]
  active: boolean
  cwd: string
  /** 待发送的命令（任务面板注入，WS 连接后就发送） */
  pendingCommand?: string
  /** Tauri process ID (0 = mock/仿真) */
  processId?: number
  /** Shell config used for spawn (only used internally) */
  _shellConfig?: { shell: string; cwd: string }
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

/** Right panel view mode — 侧边辅助面板（AI助手/聊天/记忆等） */
export type RightPanelView = "chat" | "memory" | "skills" | "mcp"

/** Bottom panel view mode — 底部面板（终端/输出/问题/调试控制台）*/
export type BottomPanelView = "terminal" | "output" | "problems" | "tasks" | "debug-console"

/** Sidebar / Activity bar icon entry */
export interface ActivityItem {
  id: string
  icon: string
  label: string
  badge?: number | string
  /** 点击后导航到的路由（设为路由路径时自动切 activeActivityItem='projects'） */
  route?: string
  /** 点击行为: 'sidebar'=展示 Sidebar 面板, 'route'=路由导航, 'chat'=打开右侧 AI 对话 */
  action?: 'sidebar' | 'route' | 'chat'
}

/** Menu bar structure */
export interface MenuItem {
  label: string
  shortcut?: string
  action?: () => void
  disabled?: boolean
  checked?: boolean
  separator?: boolean
  children?: MenuItem[]
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
  /** VSCode 风格: 多光标计数 (>1 时显示，如 "3 个游标") */
  multiCursorCount?: number
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
  /** Session 57: Panel 位置配置 — 'bottom' | 'left' | 'right' */
  panelPosition: 'bottom' | 'left' | 'right'
  /** Session 57: Panel 对齐 — 'left' | 'center' | 'right' | 'justify' */
  panelAlignment: 'left' | 'center' | 'right' | 'justify'
}

/** Session 57: 可注册的视图位置 (对标 VSCode ViewContainerLocation) */
export type ViewLocation = 'sidebar' | 'panel' | 'auxiliarybar'

/** Session 57: 视图描述符 — 可移动/可重置的视图注册 */
export interface ViewDescriptor {
  id: string
  label: string
  defaultLocation: ViewLocation
  currentLocation: ViewLocation
  icon: string
}

/** Session 39: 代码评审评论 */
export interface CommentThread {
  id: string
  filePath: string
  line: number
  body: string
  author: string
  createdAt: number
  resolved: boolean
  replies: CommentReply[]
  label?: string
  suggestion?: string
  state?: 'active' | 'resolved'
}

export interface CommentReply {
  id: string
  body: string
  author: string
  createdAt: number
}

/** Session 39: 调用层次结构项 */
export interface CallHierarchyItem {
  name: string
  kind: string
  file: string
  line: number
  children?: CallHierarchyItem[]
}

/** Session 39: 本地历史条目 */
export interface LocalHistoryEntry {
  id: string
  filePath: string
  content: string
  timestamp: number
  label: string
  isAutoSave: boolean
}

/** Session 39: 笔记本单元格 */
export interface NotebookCell {
  id: string
  type: 'code' | 'markdown'
  content: string
  output?: string
  language?: string
}

/** Session 39: 类型层次结构项 */
export interface TypeHierarchyItem {
  name: string
  kind: string
  file: string
  line: number
  children?: TypeHierarchyItem[]
}

/** Session 40: Git Blame 行归因信息 */
export interface BlameAnnotation {
  lineNumber: number
  commitHash: string
  author: string
  date: string
  summary: string
  timeAgo: string
}

/** Session 40: 文件对比状态 */
export interface FileCompareState {
  fileA: string
  fileB: string
  contentA: string
  contentB: string
  visible: boolean
}

/** Session 41: 端口条目 */
export interface PortEntry {
  id: string
  port: number
  localAddress: string
  processId?: number
  processName?: string
  source: "terminal" | "debug" | "user"
  label?: string
  isForwarded: boolean
}

/** Session 41: 搜索替换操作结果 */
export interface ReplaceResult {
  file: string
  line: number
  replaced: boolean
  before: string
  after: string
}

/** Session 42: 编辑会话 */
export interface EditSession {
  id: string
  name: string
  description: string
  createdAt: number
  fileCount: number
  synced: boolean
  tags: string[]
}

/** Session 42: 自定义编辑器 */
export interface CustomEditor {
  id: string
  name: string
  selector: string
  type: "webview" | "binary" | "text"
  provider: string
  enabled: boolean
}

/** Session 42: 拖放/粘贴载荷 */
export interface DropPastePayload {
  type: "file" | "text" | "image"
  files?: File[]
  text?: string
  position: { line: number; column: number }
}

/** Session 42: 搜索编辑器结果 */
export interface SearchEditorResult {
  file: string
  line: number
  column: number
  lineText: string
  matchLength: number
  excluded: boolean
}

/** Session 42: 内联聊天消息 */
export interface InlineChatMessage {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: number
}

/** Session 42: 多文件差异条目 */
export interface MultiDiffEntry {
  filePath: string
  fileName: string
  status: "modified" | "added" | "deleted" | "untracked" | "renamed"
  staged: boolean
  diffContent: string
}

/** Session 43: 任务定义 (VSCode Tasks 对等) */
export interface TaskDefinition {
  id: string
  name: string
  type: "shell" | "process" | "npm" | "gulp" | "tsc" | "custom"
  command: string
  args?: string[]
  cwd?: string
  env?: Record<string, string>
  /** 任务分组: build / test / none */
  group?: "build" | "test" | "none"
  /** 是否为默认构建任务 */
  isDefaultBuildTask?: boolean
  /** 是否为默认测试任务 */
  isDefaultTestTask?: boolean
  /** 问题匹配器 */
  problemMatcher?: string
  /** 展示配置 */
  presentation?: {
    reveal: "always" | "silent" | "never"
    focus: boolean
    panel: "shared" | "dedicated" | "new"
    showReuseMessage: boolean
    clear: boolean
  }
  /** 依赖任务 ID 列表 */
  dependsOn?: string[]
}

/** Session 43: 任务执行记录 */
export interface TaskRun {
  id: string
  taskId: string
  taskName: string
  status: "running" | "success" | "failed" | "terminated"
  startedAt: number
  endedAt?: number
  exitCode?: number
  output: string
  terminalId?: string
}

/** Session 43: 交互窗口单元格 (Jupyter/REPL 风格) */
export interface InteractiveCell {
  id: string
  type: "code" | "markdown"
  content: string
  output?: string
  outputType?: "text" | "html" | "error" | "image"
  language?: string
  running?: boolean
  collapsed?: boolean
  timestamp?: number
}

/** Session 43: InlayHint 类型标注 */
export interface InlayHint {
  id: string
  line: number
  column: number
  label: string
  kind: "type" | "parameter"
  paddingLeft?: boolean
  paddingRight?: boolean
}

/** Session 43: 批量编辑预览条目 */
export interface BulkEditPreview {
  id: string
  filePath: string
  fileName: string
  originalContent: string
  modifiedContent: string
  diffLines: { line: number; original: string; modified: string }[]
  accepted: boolean
  status: "pending" | "accepted" | "rejected"
}
