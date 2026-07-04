# AI Fullstack Platform — 长期记忆

## 项目偏好
- 所有代码使用中文注释和文档
- 遵循闭环系统开发规范（不可破坏四层联动）
- Python 后端使用 FastAPI + SQLite 原生持久化，零外部向量数据库
- 代码风格：类型标注 + 全局单例 + 回退链设计

## 技术决策
- 2026-06-29: 完成四大闭环系统自主实现（CodebaseMemory / LongTermMemory / Agent / AutoCLI），59 项测试通过
- Session 05-08: 参考 6 个开源项目深度借鉴，实现预算追踪/SKILL.md v2/模型健康检查/Pipeline/Session树/前端UX增强
- Session 11: 视频系统前后端打通（video-client + video-admin，共 14 文件）
- Session 12: Agent封闭环增强（WorkflowGraph + ContextWindow + CrewAI上下文链），参考 LangGraph/SWE-agent/CrewAI/OpenHands
- Session 13: 客户端增强（ToolCallCard + ChatMetricsBar + useChatScroll + ChatSessionManager + 轨迹API），参考 Cline/RooCode/Continue/OpenInterpreter
- Session 14: Git-Native Agent + Human Input + Memory 图（FuzzyDiffer + Git Auto-Commit + HumanInputMode + MemoryGraphPanel），参考 Aider/AutoGen/HermesStudio
- Session 15: 智能审批+文件检查点+提示词模板（FileCheckpoint + AutoApprovalEngine + PromptBuilder），参考 RooCode/Cline/OpenInterpreter/OpenHands
- Session 16: ContextProvider插件+FIM前端集成（ContextProvider 插件系统 + FIM 幽灵文本 + Multi-File 上下文），参考 Continue/Tabby/Zed
- Session 17: 前端缺陷修复+Tauri功能补全（ProjectNew路由修复 + AtMention真实API + GlobalSearch Web搜索 + 插件安装 + Git Diff完整解析）
- Session 18: 代码质量与基础设施加固（Vite端口修正 + 硬编码密钥移除 + package.json清理 + lint修复 + MCP auth + SQLite持久化后端）
- Session 19: 持久化缺口补全+配置修复+测试扩展（SQLite store集成/前端模型自动选择/model_health Ollama配置化/后端175项测试/前端ANSI测试）
- Session 20: 客户端完善（Studio导航菜单/ProjectDetail工作区/TemplatesBrowse模板流/AgentChat欢迎页重做+Tauri启动修复）
- Session 21: VSCode+Hermes全量抄写（SCM Git面板/通知系统/ChatPanel增强-Session置顶归档批量删除NewChatDrawer/终端14主题/Diff工作台集成/i18n国际化/12主题系统），14文件，零lint错误
- Session 22: 12主题CSS变量补全+视觉增强（index.css补全9个缺失主题块~450行CSS变量/修复useThemeStore applyHtmlClass+cycleTheme/notransitions防闪烁/组件硬编码颜色→CSS变量），零lint错误
- Session 23: VSCode Multi-Editor-Group 分屏编辑器（EditorGroup类型/useEditorStore splitEditor/groups/TabBar groupId过滤/EditorArea组间sash拖拽/面包屑Bar/Monaco配置find+breadcrumbs+右键菜单+useKeybindingStore），零lint错误
- Session 24: 键盘快捷键集成+DebugPanel+ZenMode（useKeybindingStore注册回调到App.vue/补充IDEStore facade/DebugPanel.vue断点调用栈变量监视/Zen Mode Ctrl+K Z全屏编辑），零lint错误
- Session 25: VSCode/hermes功能对标继续（OutlinePanel.vue文档符号树~300行/Sidebar集成大纲区域/WelcomePage.vue欢迎页6快捷操作/useMarkdown.ts自研MD渲染引擎Mermaid+KaTeX+代码高亮/ChatPanel集成Markdown/Monaco增强rulers+行高亮+whitespace/7文件），零lint错误
- Session 26: VSCode/hermes功能对标（PeekView.vue悬浮预览~140行/useQuickDiff.ts行内差异~110行/ChatOutlinePanel.vue对话大纲~150行/GlobalSearch文件分组树形搜索/useMarkdown headingPrefix增强/8文件），零lint错误
- Session 27: 修复新建文件打不开编辑器问题（useFileTreeStore.ts browser fallback + Sidebar/FileTree auto-openFile/3文件），零lint错误
- Session 28: 替换浏览器原生 prompt() 为 VS Code 风格 InputDialog (InputDialog/InputDialogHost 双组件 + 全局命令式 API inputDialog() + 字符校验 + App.vue 全局挂载/5文件), 全部 0 lint 错误
- Session 27: VS Code ActivityBar分离+面板全量补齐（ActivityBar.vue独立48px活动栏~220行/SearchPanel.vue搜索替换面板~440行/ExtensionsPanel.vue扩展管理器~680行含12个模拟扩展/TestingPanel.vue测试资源管理器~420行/Sidebar.vue重构纯内容区/Terminal.vue增强多终端新建分割重命名Shell类型14主题/App.vue布局适配ActivityBar+测试快捷键/useLayoutStore添加testing活动项/useTerminalStore新增createTerminal/closeTerminal/switchToTerminal/duplicateTerminal/renameTerminal/useIDEStore facade暴露），10文件，零lint错误
- Session 28: 快捷键管理+SCM增强+时间线+任务系统（KeybindingsPage.vue快捷键管理页~430行64条默认快捷键搜索编辑录制冲突检测/ScmPanel.vue分支切换5个分支创建+Stash暂存弹出丢弃/TimelinePanel.vue文件历史时间线8条目按时间分组恢复对比/TasksPanel.vue任务系统11个任务自动检测npm/shell运行状态/TasksPanel集成RightPanel/CodeEditor启用CodeLens语义高亮/ProblemsPanel搜索折叠分组/路由添加/keybindings/App.vue命令入口/ide.ts类型扩展），10文件，零lint错误
- Session 29: 修复 IDE 关键bug — (1) `useIDEStore` facade 反应性丢失,改用 `storeToRefs` (6 个子 store 统一) — Pinia setup store 中直接 `subStore.ref` 拿的是 unwrap 快照值, 不会响应后续更新; (2) Monaco 0.52 ESM 兼容 `(mod.default ?? mod)`; (3) `onCursorPositionChanged` 0.50+ 重命名为 `onDidChangeCursorPosition`; (4) group 模式 CodeEditor 重渲染竞态, initMonaco 加 `nextTick` 等待 DOM. 验证: 文件树正常渲染 + 点击文件能开 Monaco 编辑器, 零 lint 错误
- Session 30: ActivityBar 新增"项目"入口 (Briefcase SVG 图标) + 新建 `ProjectsPanel.vue` (~230行) — 顶部搜索/刷新/新建 + 列表/状态徽章(草稿/构建中/部署中/运行中/失败) + hover 打开/删除操作 + 底部"新建项目"按钮. `useLayoutStore.ts` activityItems 第1位插入 projects, `Sidebar.vue` 标题和内容区加 projects 分支. 验证: 点击后 Sidebar 切换到"项目"面板, 后端 500 时优雅显示"重试", 零 lint 错误
- Session 31: 修复 FileTree 选中态黑色方块 + ProjectsPanel 渐变背景 — **Tauri WebView2 不支持 `color-mix()`** 和 Tailwind v4 `from-{color}/{alpha}` JIT 渐变, 都 fallback 成纯黑. 改用 `rgba(0,122,204,0.18)` 替代 `color-mix(in srgb, var(--color-ide-accent) 18%, transparent)`, 用 inline `style="background: linear-gradient(...)"` 替代 `bg-gradient-to-br from-brand-500/15`. **关键经验**: IDE 桌面端 UI 关键样式优先用原生 CSS 变量 + rgba + inline style, 不依赖 Tailwind JIT. 同时 FileTree 缩进 8→12px 加深层级. 验证: 选中行半透明蓝色高亮 + ProjectsPanel 渐变图标正常, 零 lint 错误
- Session 32: FileTree 缩进深度对齐 + MenuBar 终端顶级菜单 + 合并 ChatPanel 重复 terminal — (1) FileTree paddingLeft `*12+8` → `*14+18`, 引导线 left `(i-1)*12+18` → `(i-1)*14+25` (中线对齐), 引导线颜色 `rgba(60,60,60,0.55)` → `rgba(120,120,120,0.35)` 更柔和. (2) MenuBar 顶部新增 `终端` 顶级菜单 (新建/分割/清空/关闭/显示), 菜单 min-width 220→260px 防 `Ctrl+Shift+`` 换行. (3) ChatPanel 顶部"工具面板"删除 Terminal tab 只保留 Files, 移除 `Terminal` icon import + `toolPanelTab` ref. **关键经验**: VSCode 风格 FileTree 引导线公式 `left = (depth - 1) * step + (paddingBase + step/2)`, 其中 step=缩进步长, paddingBase=根级 paddingLeft. 验证: 文件树 `my-ai-app > src > {package.json...}` 父子缩进明显 + 顶部菜单 `终端` 菜单完整渲染 + 点击新建终端后 RightPanel 自动切到终端 tab, 零 lint 错误
    37|- Session 33: VSCode对标修复6项 — (1) P0 底部面板重复渲染: 删除 EditorArea 内嵌面板(~80行), 只保留 App.vue 全局面板; (2) P0 router-view被isEditingFile隐藏: 路由页面改为 overlay 全屏渲染在编辑器上层, 删除 closeAll() 破坏性调用, ActivityBar/MenuBar 不再关闭编辑标签页; (3) P1 RightPanel onMounted 强制覆盖布局偏好已移除, 改为 localStorage 恢复; (4) P1 FileTree Git 状态从 mock 改为 useIDEStore.gitChanges 真实数据; (5) P2 WelcomePage "打开文件夹"实现 Tauri dialog.open + Browser showDirectoryPicker; (6) P2 Settings 按钮 hover 样式移除 + 重复 ::-moz-focus-inner 删除. 全部零 lint 错误.
- Session 34: VSCode 像素级视觉对齐 (2026-07-04) — (1) 4 个 CSS 高度变量归位: --menubar-height 38→35, --statusbar-height 28→22, --tabbar-height 38→35, --panel-title-height 38→35; (2) StatusBar font-size 14→12, 图标 :size 14→12, item 高度 28→22; (3) CodeEditor fontSize 13→14, wordWrap on→off, scrollBeyondLastLine false→true, padding {8,8}→{0,0}, 背景 #0F131D→#1E1E1E, Cascadia Code 字体置顶, lineNumbersMinChars 4→5; (4) RightPanel 活动指示器 1→2px; (5) 6 处硬编码 35/38px 高度统一为 var(--panel-title-height); (6) MenuBar 菜单项字体 14→13px. 9 文件 26 处改动, 零 lint 错误.

## 顶部菜单 (Session 32 6 个)
`文件 / 编辑 / 查看 / 终端 / Studio / 帮助`
- "终端" 是 Session 32 新增的顶级菜单 (VSCode 风格), 包含: 新建/分割/清空/关闭/显示

## 终端入口汇总 (避免重复)
- **顶部菜单** → `终端` → `新建终端 Ctrl+Shift+`` (Session 32 新增, VSCode 主入口)
- **顶部菜单** → `查看` → `终端 Ctrl+`` (兼容入口)
- **RightPanel** 标题栏 → `终端` tab (原有, 切换视图)
- **ChatPanel** 顶部 → ❌ Session 32 移除 (避免重复)

## 跨平台兼容经验 (重要)
- **Tauri WebView2 / 老 WebView 不支持 `color-mix()`** → fallback 纯黑. 替代: `rgba()` / `color-mix` 检测
- **Tailwind v4 `from-{color}/{alpha}` JIT 渐变** 在 .vue 单文件组件中可能未扫描到 → 编译为空 class → 元素无背景. 替代: inline `style="background: linear-gradient(135deg, rgba(R,G,B,A), rgba(R,G,B,A))"`
- **IDE 关键 UI 样式 (选中态/品牌渐变/激活边框)** 优先用 CSS 变量 + rgba + inline style, 不依赖 Tailwind JIT 编译产物
- 通用回退: `text-{color}` 自定义色 → `style="color: #XXX"`; `border-{color}/{alpha}` → `style="border: 1px solid rgba(...)"`

## 前端视觉规范
- 所有UI颜色必须通过CSS变量引用(`var(--color-ide-*)`)，禁止硬编码色值
- 主题切换流程: `useThemeStore.applyHtmlClass()` → 清除所有`theme-*`类 → 添加新主题类 → dark-category非dark主题额外添加`theme-dark`回退
- 首页加载: `<html>`添加`no-transitions`类，2个`requestAnimationFrame`后移除，防止主题闪烁
- StatusBar右侧主题切换按钮: 图标+主题名称标签，点击`cycleTheme()`循环12主题
- 组件级颜色: ActivityBar indicator用`--color-ide-text-bright`，NotificationToast用`--color-ide-error/warning/success/info`，badge用`--color-ide-accent`

## 架构约定
- `backend/app/core/` 为核心基础设施，不可引入外部依赖闭环
- API 前缀 `/api/v1/`，分页格式 `{data, total, page, size}`
- Agent 流水线顺序不可变: Planner → Coder → Reviewer → Memory
- 模型回退链: 本地最优 → 本地次优 → 第三方 API → 内置基础
