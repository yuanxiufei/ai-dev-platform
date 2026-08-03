// ============================================
// Layout Store — UI layout dimensions & panels (Zed Dock 风格持久化)
// ============================================
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { ActivityItem, BottomPanelView, IDELayoutState, RightPanelView, ViewLocation, ViewDescriptor } from '@/types/ide'
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
  panelPosition: 'bottom',
  panelAlignment: 'center',
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

  // ── Session 57: Panel 位置/对齐 ──
  function setPanelPosition(pos: 'bottom' | 'left' | 'right') {
    layout.value.panelPosition = pos
    saveLayout(layout.value)
  }
  function setPanelAlignment(align: 'left' | 'center' | 'right' | 'justify') {
    layout.value.panelAlignment = align
    saveLayout(layout.value)
  }

  // ── Session 57: View 移动/重置 ──
  /** 注册的视图 (可移动位置) */
  const viewDescriptors: ViewDescriptor[] = [
    { id:'terminal', label:'终端', defaultLocation:'panel', currentLocation:'panel', icon:'Terminal' },
    { id:'problems', label:'问题', defaultLocation:'panel', currentLocation:'panel', icon:'AlertCircle' },
    { id:'tasks', label:'任务', defaultLocation:'panel', currentLocation:'panel', icon:'ListTodo' },
    { id:'output', label:'输出', defaultLocation:'panel', currentLocation:'panel', icon:'Terminal' },
    { id:'debug-console', label:'调试控制台', defaultLocation:'panel', currentLocation:'panel', icon:'Bug' },
    { id:'testing', label:'测试', defaultLocation:'sidebar', currentLocation:'sidebar', icon:'FlaskConical' },
    { id:'callhierarchy', label:'调用层次结构', defaultLocation:'sidebar', currentLocation:'sidebar', icon:'GitBranch' },
    { id:'localhistory', label:'本地历史', defaultLocation:'sidebar', currentLocation:'sidebar', icon:'Briefcase' },
    { id:'typehierarchy', label:'类型层次结构', defaultLocation:'sidebar', currentLocation:'sidebar', icon:'Puzzle' },
    { id:'timeline', label:'时间线', defaultLocation:'sidebar', currentLocation:'sidebar', icon:'Hourglass' },
    { id:'ports', label:'端口', defaultLocation:'panel', currentLocation:'panel', icon:'Globe' },
    { id:'comments', label:'代码评审', defaultLocation:'sidebar', currentLocation:'sidebar', icon:'MessageSquare' },
  ]

  function moveView(viewId: string, to: ViewLocation): void {
    const desc = viewDescriptors.find(v => v.id === viewId)
    if (desc) desc.currentLocation = to
  }

  function resetView(viewId: string): void {
    const desc = viewDescriptors.find(v => v.id === viewId)
    if (desc) desc.currentLocation = desc.defaultLocation
  }

  function resetAllViews(): void {
    for (const desc of viewDescriptors) {
      desc.currentLocation = desc.defaultLocation
    }
  }

  const rightPanelView = ref<RightPanelView>('chat')
  const bottomPanelView = ref<BottomPanelView>('terminal')
  const menuBarOpen = ref<string | null>(null)
  const activeActivityItem = ref('explorer')
  /** 🔥 设置面板显示状态（修复 P2: ActivityBar settings 按钮打开设置面板） */
  const showSettingsPanel = ref(false)
  /** 🔥 Session 35: Markdown 预览分屏显示 */
  const markdownPreviewVisible = ref(false)

  /** Focus the IDE window (Tauri-only) */
  async function focusWindow(): Promise<void> {
    try {
      if (!(window as any).__TAURI__) return
      const { invoke } = await import('@tauri-apps/api/core')
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      const w = getCurrentWindow()
      await invoke('focus_window', { window: w })
    } catch (e) {
      console.warn('[Layout] focus_window failed:', e)
    }
  }

  /** 切换全屏 (Tauri-only) */
  async function toggleFullscreen(): Promise<void> {
    try {
      if (!(window as any).__TAURI__) return
      const { invoke } = await import('@tauri-apps/api/core')
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      const w = getCurrentWindow()
      await invoke('toggle_fullscreen', { window: w })
    } catch (e) {
      console.warn('[Layout] toggle_fullscreen failed:', e)
    }
  }

  /** 放大界面 (Tauri-only) */
  async function zoomIn(): Promise<void> {
    try {
      if (!(window as any).__TAURI__) return
      const { invoke } = await import('@tauri-apps/api/core')
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      const w = getCurrentWindow()
      await invoke('zoom_in', { window: w })
    } catch (e) {
      console.warn('[Layout] zoom_in failed:', e)
    }
  }

  /** 缩小界面 (Tauri-only) */
  async function zoomOut(): Promise<void> {
    try {
      if (!(window as any).__TAURI__) return
      const { invoke } = await import('@tauri-apps/api/core')
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      const w = getCurrentWindow()
      await invoke('zoom_out', { window: w })
    } catch (e) {
      console.warn('[Layout] zoom_out failed:', e)
    }
  }

  /** 重置缩放至 100% (Tauri-only) */
  async function resetZoom(): Promise<void> {
    try {
      if (!(window as any).__TAURI__) return
      const { invoke } = await import('@tauri-apps/api/core')
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      const w = getCurrentWindow()
      await invoke('reset_zoom', { window: w })
    } catch (e) {
      console.warn('[Layout] reset_zoom failed:', e)
    }
  }

  /** 打开开发者工具 (Tauri-only) */
  async function openDevtools(): Promise<void> {
    try {
      if (!(window as any).__TAURI__) return
      const { invoke } = await import('@tauri-apps/api/core')
      const { getCurrentWindow } = await import('@tauri-apps/api/window')
      const w = getCurrentWindow()
      await invoke('open_devtools', { window: w })
    } catch (e) {
      console.warn('[Layout] open_devtools failed:', e)
    }
  }

  const activityItems = computed<ActivityItem[]>(() => {
    const gitStore = useGitStore()
    return [
      // ── 标准视图 (Standard views, 切换 Sidebar) ──
      { id: 'search', icon: 'Search', label: '搜索', badge: undefined },
      {
        id: 'git',
        icon: 'GitBranch',
        label: '源代码管理',
        badge: gitStore.gitChangedFiles > 0 ? String(gitStore.gitChangedFiles) : undefined,
      },
      { id: 'debug', icon: 'Bug', label: '运行和调试', badge: undefined },
      { id: 'testing', icon: 'FlaskConical', label: '测试', badge: undefined },
      { id: 'extensions', icon: 'Blocks', label: '扩展', badge: undefined },
      // ── AI 工具 (AI tools, 路由导航) ──
      { id: 'ai-chat', icon: 'MessageSquare', label: 'AI 对话' },
      { id: 'ai-studio', icon: 'LayoutDashboard', label: 'AI Studio 面板' },
      { id: 'ai-projects', icon: 'FolderKanban', label: '项目管理', route: '/projects' },
      { id: 'ai-templates', icon: 'LayoutTemplate', label: '模板市场', route: '/templates' },
      { id: 'ai-knowledge', icon: 'Brain', label: '知识库', route: '/knowledge' },
      { id: 'ai-screenshot', icon: 'Camera', label: '截图转代码', route: '/screenshot-to-code' },
      { id: 'ai-video', icon: 'Film', label: '视频工坊', route: '/videos' },
      { id: 'ai-compound', icon: 'Database', label: '复合存储库', route: '/compound-vault' },
      { id: 'ai-filters', icon: 'Funnel', label: '文本过滤器', route: '/rag-filters' },
      { id: 'ai-presets', icon: 'Sliders', label: '模型预设', route: '/model-presets' },
      { id: 'ai-video-admin', icon: 'Shield', label: '视频管理', route: '/video-admin' },
      { id: 'ai-skills', icon: 'Cpu', label: '技能管理', route: '/skills' },\n      { id: 'ai-logs', icon: 'FileText', label: '日志查看器', route: '/logs' },
      { id: 'ai-extensions', icon: 'Puzzle', label: '扩展管理', route: '/extensions' },
      { id: 'ai-notebook', icon: 'Zap', label: '笔记执行器', route: '/notebook' },
      { id: 'ai-guardrails', icon: 'Shield', label: '安全护栏', route: '/guardrails' },
      { id: 'ai-agent-modes', icon: 'Bot', label: 'Agent 模式', route: '/agent-modes' },
      { id: 'ai-session-tree', icon: 'GitBranch', label: '会话树', route: '/session-tree' },
      { id: 'ai-system-config', icon: 'Settings', label: '系统配置', route: '/system-config' },
      /* P5: Chat / Arena / Structured Output / OpenAPI / Integrations / Diagnostics / GPU / Language Detection */
      { id: 'ai-arena', icon: 'Swords', label: '模型竞技场', route: '/arena' },
      { id: 'ai-structured-output', icon: 'Braces', label: '结构化输出', route: '/structured-output' },
      { id: 'ai-openapi', icon: 'Globe', label: 'OpenAPI 发现', route: '/openapi' },
      { id: 'ai-integrations', icon: 'Blocks', label: '集成管理', route: '/integrations' },
      { id: 'ai-diagnostics', icon: 'Stethoscope', label: '代码诊断', route: '/diagnostics' },
      { id: 'ai-gpu', icon: 'Cpu', label: 'GPU 监控', route: '/gpu' },
      { id: 'ai-language-detection', icon: 'Languages', label: '语言检测', route: '/language-detection' },
      /* P6: Tasks / Diff / Code Actions */
      { id: 'ai-tasks', icon: 'ListTodo', label: '任务管理', route: '/tasks' },
      { id: 'ai-diff', icon: 'Diff', label: 'Diff 对比', route: '/diff' },
      { id: 'ai-code-actions', icon: 'Wand', label: '代码操作', route: '/code-actions' },
      /* P7: 补齐侧边栏入口 — 工具/记忆/Webhook/分析/媒体/AI工具 */
      { id: 'ai-tools', icon: 'Wrench', label: '工具浏览器', route: '/tools' },
      { id: 'ai-memory', icon: 'Database', label: '记忆管理', route: '/memory' },
      { id: 'ai-webhooks', icon: 'Webhook', label: 'Webhook 管理', route: '/webhooks' },
      { id: 'ai-analytics', icon: 'BarChart3', label: '分析仪表盘', route: '/analytics' },
      { id: 'ai-image-gen', icon: 'Image', label: '图片生成', route: '/image-gen' },
      { id: 'ai-voice', icon: 'Mic', label: '语音功能', route: '/voice' },
      { id: 'ai-prompt-templates', icon: 'NotebookPen', label: '提示词模板', route: '/prompt-templates' },
      { id: 'ai-jobs', icon: 'Clock', label: '定时任务', route: '/jobs' },
      { id: 'ai-knowledge-graph', icon: 'Share2', label: '知识图谱', route: '/knowledge-graph' },
      { id: 'ai-traces', icon: 'Route', label: 'Agent 追踪', route: '/traces' },
      { id: 'ai-benchmarks', icon: 'Gauge', label: '基准测试', route: '/benchmarks' },
      { id: 'ai-models', icon: 'Boxes', label: '模型管理', route: '/models' },
      { id: 'ai-catalog', icon: 'Library', label: '模型目录', route: '/catalog' },
      { id: 'ai-trajectory', icon: 'Activity', label: '轨迹追踪', route: '/trajectory' },
      { id: 'ai-global-search', icon: 'Search', label: '全局搜索', route: '/global-search' },
      { id: 'ai-terminal', icon: 'Terminal', label: '终端', route: '/terminal' },
      { id: 'ai-standalone', icon: 'Monitor', label: '独立模式', route: '/standalone' },
      { id: 'ai-sessions', icon: 'History', label: '会话摘要', route: '/sessions' },
      { id: 'ai-testing', icon: 'FlaskConical', label: '测试面板', route: '/testing' },
      { id: 'ai-storage', icon: 'HardDrive', label: '存储设置', route: '/storage' },
      { id: 'ai-mcp', icon: 'PlugZap', label: 'MCP 设置', route: '/mcp' },
      { id: 'ai-plugins', icon: 'Plug2', label: '插件市场', route: '/plugins' },
      { id: 'ai-agents', icon: 'Bot', label: 'Agent 管理', route: '/agents' },
      { id: 'ai-snippets', icon: 'Code2', label: '代码片段', route: '/snippets' },
      { id: 'ai-more', icon: 'Sparkles', label: '更多 AI 工具' },
      // ── VSCode 高级面板 (Sidebar 切换) ──
      { id: 'callhierarchy', icon: 'GitBranch', label: '调用层次结构' },
      { id: 'localhistory', icon: 'Briefcase', label: '本地历史' },
      { id: 'typehierarchy', icon: 'Puzzle', label: '类型层次结构' },
      { id: 'comments', icon: 'MessageSquare', label: '代码评审' },
      { id: 'notebook', icon: 'LayoutTemplate', label: '笔记本' },
      { id: 'ports', icon: 'Globe', label: '端口' },
      { id: 'multidiff', icon: 'FileDiff', label: '多文件差异' },
      { id: 'browser', icon: 'Globe', label: '浏览器预览' },
      { id: 'processes', icon: 'Cpu', label: '进程管理' },
      { id: 'customeditors', icon: 'FileType', label: '自定义编辑器' },
      { id: 'editsessions', icon: 'History', label: '编辑会话' },
      // ── Session 43: 任务 + 交互窗口 ──
      { id: 'tasks', icon: 'ListTodo', label: '任务' },
      { id: 'interactive', icon: 'Terminal', label: '交互窗口' },
    ]
  })

  return {
    layout,
    rightPanelView,
    bottomPanelView,
    menuBarOpen,
    activityItems,
    activeActivityItem,
    showSettingsPanel,
    /** Session 35: Markdown 预览 */
    markdownPreviewVisible,
    focusWindow,
    toggleFullscreen,
    zoomIn,
    zoomOut,
    resetZoom,
    openDevtools,
    resetLayout,
    // Session 57: Panel + View 管理
    setPanelPosition,
    setPanelAlignment,
    viewDescriptors,
    moveView,
    resetView,
    resetAllViews,
  }
})
