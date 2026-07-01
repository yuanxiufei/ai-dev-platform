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
