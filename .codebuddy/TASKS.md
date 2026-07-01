# AI Fullstack Platform — 开发任务清单

> **日期**: 2026-06-29  
> **前置**: 四大闭环系统已实现，59 项测试通过  
> **原则**: 所有开发在闭环架构内进行，零外部依赖闭环

---

## P0 — 核心闭环补全

### 1. AgentOrchestrator 接入 AgentRunner 流水线 ✅
- **现状**: orchestrator.py 直接调用 ModelRouter，未复用 AgentRunner 的 Middleware/Sandbox/TrajectoryRecorder
- **目标**: 改造 orchestrator 以接入现有 AgentRunner 流水线
- **涉及文件**: `backend/app/core/agent/orchestrator.py`, `backend/app/core/agent/agent_runner.py`
- [x] orchestrator 的 _execute_subtask 改用 AgentRunner.run()
- [x] Planner/Coder/Reviewer 各用独立的 AgentConfig + Mode

### 2. Memory 闭环触达 AgentRunner ✅
- **现状**: AgentRunner 未在运行前后加载/保存记忆
- **目标**: before_run 注入记忆上下文，after_run 保存提取的记忆
- **涉及文件**: `backend/app/core/agent/agent_runner.py`, `backend/app/core/memory/`
- [x] AgentRunner.before_run → MemoryRetriever.retrieve_as_context()
- [x] AgentRunner.after_run → MemoryExtractor.extract_and_save()

### 3. CodebaseMemory 工具注册到全局 ToolRegistry ✅
- **现状**: TOOL_REGISTRY 仅在 codebase_memory 内部使用
- **目标**: 8 个工具注册到全局 ToolRegistry，Agent 可通过 Function Calling 调用
- **涉及文件**: `backend/app/core/codebase_memory/tools.py`, `backend/app/core/tools/registry.py`
- [x] 将 8 个 Tool 注册到 ToolRegistry
- [x] Agent 可通过 tool_calls 调用 search_graph/trace_path 等
- [x] main.py 中集成 init_codebase_tools_to_global_registry() 调用

---

## P1 — 功能增强

### 4. Cypher 风格图查询 (query_graph) ✅
- **借鉴**: codebase-memory-mcp 的 openCypher 只读子集
- **目标**: 实现 MATCH→WHERE→RETURN 查询，支持聚合和路径遍历
- **涉及文件**: `backend/app/core/codebase_memory/tools.py` (新增 query_graph)
- [x] 实现 Cypher 词法解析器 (Lexer)
- [x] 实现 Cypher 语法解析器 (Parser) — MATCH/WHERE/RETURN/ORDER BY/LIMIT
- [x] SQL 翻译层 → SQLite 执行
- [x] 内存执行层 → CodeGraph 回退
- [x] 更新 TOOL_REGISTRY 添加 query_graph

### 5. Git 变更自动增量索引 ✅
- **现状**: FileIndexer 需手动触发 index()
- **目标**: 检测 git 变更后自动增量索引
- **涉及文件**: `backend/app/core/codebase_memory/indexer.py`
- [x] 实现 GitIndexer (git diff --name-only 检测变更文件)
- [x] 增量索引 (只重新解析变更的文件)
- [x] 后台线程持续监听 (poll=60s)
- [x] main.py 集成启动

### 6. Skills 热加载 ✅
- **现状**: SkillManager 仅在启动时 discover()
- **目标**: 运行时检测新 skill 文件，自动激活
- **涉及文件**: `backend/app/core/skills/skill_manager.py`
- [x] 文件系统监听 (mtime 轮询，借鉴 ConfigReloader)
- [x] 检测到新 SKILL.md → 自动解析注册
- [x] API 端点触发重新发现 (POST /skills/reload)
- [x] main.py 集成启动

### 7. Agent 反思→Memory 闭环 ✅
- **现状**: reflection.py 的反思结果未保存到 MemoryStore
- **目标**: 反思结果自动调用 MemoryExtractor，保存为 LESSON 类型
- **涉及文件**: `backend/app/core/agent/reflection.py`, `backend/app/core/memory/`
- [x] ReflectionManager 在 reflect() 后调用 MemoryExtractor
- [x] 保存为 MemoryType.LESSON，关联原任务
- [x] AgentRunner.run() 中接入 ReflectionManager.after_run() 调用

---

## P2 — 平台体验

### 8. Memory 可视化 UI ✅
- **现状**: 记忆仅存在 SQLite，无可视化
- **目标**: Studio 前端展示记忆节点和关系图
- [x] 后端 API: GET /api/v1/memory/graph-data (MemoryNode/MemoryEdge)
- [x] 后端 API: GET /api/v1/memory/graph-stats
- [x] 前端: KnowledgeGraphPage.vue 完整实现（SVG图谱/反链/解析/统计 + 节点搜索/缩放/选中详情面板）

### 9. AutoCLI 执行日志 ✅
- **现状**: CLI 执行无持久化记录
- **目标**: 记录每次执行到 JSONL 日志
- [x] AutoCLI.execute() 写入 data/cli_history.jsonl
- [x] API: GET /api/v1/system/cli-history

### 10. Agent 轨迹回放 ✅
- **现状**: TrajectoryRecorder 记录轨迹但无回放
- **目标**: 前端可视化回放 Agent 执行步骤
- [x] API: GET /api/v1/agent/trajectory/{agent_id}/replay
- [x] 前端: TrajectoryPage.vue 完整实现（文件列表 + 回放时间线 + 摘要卡片 + 步骤详情 + 错误高亮 + 删除）

---

## 参考仓库待深入

| 仓库 | 学习重点 | 对应任务 |
|------|---------|---------|
| cognee | Pipeline 架构 + 自动本体生成 | 任务 2 (Memory 闭环) + **Session 06 管道正式化** |
| Agent-Reach | Channel 抽象 + 多后端回退 | 任务 1 (Agent 流水线) + **Session 05 模型健康检查** |
| hermes-agent | 预算感知循环 + Session 树 | 任务 1/7 (Agent 循环) + **Session 05 预算追踪** + **Session 06 Session 树** |
| AutoCLI | YAML 适配器 + 流水线组合 | 任务 9 (CLI 日志) + **Session 06 CLI 流水线** |
| anthropics/skills | SKILL.md 规范 | 任务 6 (Skills 热加载) + **Session 05 SKILL.md v2** |
| openai/skills | Plugins 分层 (system/curated/experimental) | 任务 6 + **Session 05 技能分层** |

---

## Session 05 — 参考仓库深度借鉴

### 11. Agent 预算感知循环 ✅
- **来源**: hermes-agent 预算感知循环设计
- **目标**: 加入 token/成本/时间 三层预算，预算耗尽时优雅终止
- [x] `budget.py`: BudgetTracker 类（token/cost/time 三层预算 + PricingTier 定价表）
- [x] AgentConfig 新增 enable_budget/token_budget/cost_budget_usd/time_budget_ms 字段
- [x] AgentRunner.run() 每轮循环前检查预算 + 每轮后记录消耗
- [x] 预算耗尽时优雅终止（非硬中断，返回已有最佳答案）

### 12. SKILL.md v2 规范对齐 ✅
- **来源**: anthropics-skills SKILL.md 规范 + openai-skills 分层设计
- **目标**: 渐进披露（L1/L2/L3）+ 捆绑资源目录 + 格式验证 + tier 分层
- [x] SkillInfo 新增 license/version/author/tags/tier/scripts_dir/references_dir/assets_dir 字段
- [x] _parse_frontmatter_v2() 完整 frontmatter 解析（9 个字段）
- [x] build_skills_prompt() 渐进披露（Level 1/2/3 三级）
- [x] validate_skill() / validate_all() 格式验证

### 13. 模型健康检查 ✅
- **来源**: Agent-Reach Channel.check() 设计
- **目标**: 定期健康探测 + 动态标记 is_available + API 查询
- [x] `model_health.py`: ModelHealthChecker 类 + MonitoredModel + 3 种探测策略
- [x] main.py 集成启动（每 2 分钟探测）
- [x] API: GET /system/model-health + POST /system/model-health/check

---

## Session 06 — 管道正式化 + CLI 流水线 + Session 树

### 14. Agent 管道正式化 ✅
- **来源**: cognee TaskSpec → BoundTask → run_pipeline 延迟调用模式
- **目标**: @step 装饰器 + Pipeline 抽象 + 步骤编排器
- [x] `pipeline.py`: @step 装饰器 → StepSpec → BoundStep 三层延迟调用
- [x] Pipeline 类：add/add_if 流式 API + run() 编排
- [x] run_pipeline(): 按序执行 + 条件跳过 + async generator 支持
- [x] define_pipeline() DSL 快捷构建
- [x] PipelineContext 上下文传递（step outputs 间引用）
- [x] agent/__init__.py 导出 step/StepSpec/BoundStep/Pipeline/PipelineResult 等

### 15. AutoCLI 流水线组合 ✅
- **来源**: AutoCLI YAML 适配器 + 流水线组合设计
- **目标**: YAML 定义多步骤 CLI 工作流 + 串行/并行/条件执行 + 变量传递
- [x] `cli_pipeline.py`: CLIPipeline + CLIPipelineLoader + PipelineStep
- [x] YAML 文件加载 + YAML 字符串加载 + 内联 dict 构建
- [x] 拓扑排序 + 并行分组（depends_on/parallel_with）
- [x] 条件执行（`{{step.exit_code}} == 0` 风格表达式）
- [x] 重试机制（max_retries + retry_delay + on_failure）
- [x] 变量模板解析（{{step.stdout}} / ${ENV_VAR} / $VARIABLE）
- [x] API: POST /system/cli-pipeline/run-file + run-inline + run-yaml + samples

### 16. Session 树 + 检查点恢复 ✅
- **来源**: hermes-agent Session Tree / Checkpoint 设计
- **目标**: 会话树形组织 + 分支探索 + 状态快照 + 恢复运行
- **🔄 重构**: 持久化从裸 JSON 文件迁移到 MemoryStore (SQLite 图数据库) + StorageManager
- [x] `session_tree.py`: SessionTree + SessionNode + Checkpoint + CheckpointManager
- [x] Session 树：create/fork/get_subtree/get_branch_chain/get_all_branches
- [x] 分支：fork() 自动保存检查点 + 复制消息历史 + 同级分支
- [x] 检查点：MemoryStore(SQLite) 元数据 + StorageManager 文件存储(>100KB负载)
- [x] 边关系：CONVERSATION_FLOW(父→子) / BRANCHES_FROM(fork) / BELONGS_TO(检查点) / RESTORED_FROM
- [x] 恢复：restore() 从 MemoryStore 快照重建消息历史 + 创建恢复节点
- [x] 启动恢复：_init_from_memory_store() 从 data/memory.db 自动重建整棵树
- [x] main.py 集成：注入 get_memory_store() + get_storage_manager() 单例
- [x] API: /system/session-tree (树/节点/子树/fork) + /checkpoints (CRUD) + /restore

---
## Session 07 — Zed/CodeEdit 前端借鉴 ✅

### 17. Command Palette Zed 风格增强 ✅
- [x] 最近使用命令（localStorage + 最近 10 条）
- [x] 首字母缩写匹配（jfp → Just File Picker）
- [x] 模糊匹配评分（精确子串 > 前缀 > 首字母缩写）
- [x] 系统感知快捷键显示

### 18. Streaming Diff 流式渲染 ✅
- [x] StreamingDiffViewer.vue（打字机效果 + 闪烁光标）
- [x] unified/split 双模式
- [x] 播放/暂停工具栏

### 19. 布局持久化 + FileTree 右键菜单 ✅
- [x] LayoutStore localStorage 持久化 + resetLayout()
- [x] FileTree 右键菜单：复制路径 / @-引用到对话 / 打开

---

## Session 08 — VSCode/Aider/Cline 前端增强 ✅

### 20. VSCode 风格 StatusBar + Breadcrumbs ✅
- [x] StatusBar: 模型健康指示器 + 工作区名称 + 通知 badge
- [x] BreadcrumbsBar.vue: 路径分段点击 + 同级文件下拉导航
- [x] TabBar.vue: 修复 `_` 前缀 bug + 集成 BreadcrumbsBar

### 21. Aider 风格批量编辑确认 ✅
- [x] BatchEditPanel.vue: 多文件编辑审查面板
- [x] 搜索-替换 Diff 展示（unified/split）
- [x] 逐文件 Accept/Reject + Accept All/Reject All
- [x] 文件类型/状态色彩编码

### 22. Cline 风格 Always Allow 记忆 ✅
- [x] SecurityApprovalPanel: Always Allow 模式（localStorage 持久化）
- [x] 始终允许工具数量显示
- [x] 每工具独立 Always Allow 开关

---

## Session 11 — 视频系统前后端打通 ✅

### 23. 视频前后端 API 打通 ✅
- **现状**: video-client 和 video-admin 只用 mock 数据，不调用后端
- **目标**: 前后端完整打通，所有数据走真实 API
- **涉及**: video-client 3 页面 + video-admin 4 页面 + backend 2 端点

**后端改动 (1 文件)**
| 文件 | 改动 |
|------|------|
| `video/client/generate.py` | 修复缺少 `logger` 导入 Bug；新增 `GET /videos/generate/my` 用户任务分页列表（支持 status 过滤） |

**video-client 改动 (7 文件)**
| 文件 | 改动 |
|------|------|
| `api/videoApi.ts` (**新增**) | API 服务层：`generateVideo` / `getTaskStatus` / `listMyTasks` / `browseVideos` / `searchVideos` / `getPlayInfo` / `connectProgressWs` |
| `types/video.ts` (**新增**) | TS 类型：`GenerateRequest/Response`、`TaskStatusResponse`、`VideoItem`、`WsProgressMessage` 等 10+ 接口 |
| `stores/videoStore.ts` (**重写**) | Pinia Store：真实 API 调用 + WebSocket 实时进度 + 1.5s 轮询回退 + 本地视频列表管理 |
| `pages/home/HomeDesktop.vue` | 生成入口页：提示词输入 + 6 种风格/时长选择 → `store.startGeneration()` + 实时进度条 + 最近作品网格 |
| `pages/gallery/GalleryDesktop.vue` | 画廊页：`store.fetchMyTasks()` 加载 + 状态过滤 + 4列网格 + 进度/删除 |
| `pages/player/PlayerDesktop.vue` | 播放页：路由 id 查找视频 + 双列布局（预览/详情）+ 点赞/分享/下载 |
| `vite.config.ts` | 新增 `/api`、`/videos`、`/thumbnails` 代理到 `localhost:8000` |

**video-admin 改动 (6 文件)**
| 文件 | 改动 |
|------|------|
| `pages/Videos.vue` (**新增**) | 管理列表：分页表格 + 审核/公开状态筛选 + 编辑/删除操作 |
| `pages/Analytics.vue` (**新增**) | 数据分析：8 张统计卡片 + 任务成功率/公开率/平均时长摘要 |
| `pages/Moderation.vue` (**新增**) | 审核队列：待审核卡片列表 + 批准/驳回操作 + 15s 自动刷新 |
| `pages/Dashboard.vue` | 概览仪表板：4 张概览卡片 + 3 个快捷入口（视频管理/数据分析/内容审核） |
| `router/index.ts` | 新增 3 条路由：`/videos`、`/analytics`（superuser）、`/moderation`（superuser） |
| `components/Sidebar/AppSidebar.vue` | 新增 3 个导航项：视频管理(Film)、数据分析(BarChart3)、内容审核(ShieldCheck) |
| `vite.config.ts` | 新增 `/api` 代理到 `localhost:8000` |

---

## Session 12 — Agent封闭环增强 (参考 LangGraph/SWE-agent/CrewAI/OpenHands)

### 24. WorkflowGraph 声明式状态图 ✅
- **来源**: LangGraph StateGraph 声明式节点+边+条件路由
- **目标**: 将 hardcoded if/else 替换为声明式图引擎
- [x] `workflow_graph.py`: WorkflowState / WorkflowGraph / CompiledWorkflow
- [x] 条件路由 (add_conditional) + stream() 事件流
- [x] create_default_workflow(): Planner -> Coder -> Reviewer <-> Fixer
- [x] to_mermaid() Mermaid 图可视化导出

### 25. ContextWindow 智能上下文管理 ✅
- **来源**: SWE-agent ACP SmartContext 三级截断策略
- **目标**: 超长上下文时智能截断而非硬截断
- [x] `context_window.py`: ContextWindowManager + ContextBudget + SmartReadResult
- [x] TRIM_TOOL_OUTPUT -> TRIM_OLD_FILES -> SUMMARIZE_HISTORY 三级策略
- [x] AgentConfig.trim_context() 新增 smart 参数

### 26. CrewAI 风格上下文链 ✅
- **来源**: CrewAI Task Context Chain ({dep_id} 变量插值)
- **目标**: 依赖任务结果自动注入后续子任务上下文
- [x] orchestrator: task_context_map 依赖任务结果自动注入
- [x] _execute_subtask() description 参数支持插值后的描述

### 27. WorkflowGraph 引擎集成 ✅
- **目标**: orchestrator 支持双引擎 (直接/图引擎)
- [x] ENGINE_DIRECT / ENGINE_WORKFLOW 常量 + engine 参数
- [x] _orchestrate_workflow() 使用 CompiledWorkflow 编排

**文件变更** (5 文件, +1152/-23):
| 文件 | 改动 |
|------|------|
| `workflow_graph.py` (**新增**) | WorkflowGraph + CompiledWorkflow + stream + Mermaid |
| `context_window.py` (**新增**) | ContextWindowManager + 三级截断 + Budget |
| `orchestrator.py` | 双引擎 + CrewAI 上下文链 + 工作流图编排 |
| `agent_config.py` | trim_context() smart 参数 + 三级策略 |
| `__init__.py` | 新模块导出 |

---

## Session 13 — 客户端增强 (参考 Cline/RooCode/Continue/OpenInterpreter)

### 28. ToolCallCard — Cline 风格工具调用卡片 ✅
- **来源**: Cline ChatRow.tsx (工具调用内嵌消息流渲染)
- **目标**: 工具调用→执行→结果在聊天消息中行内展示
- [x] `ToolCallCard.vue`: 低风险紧凑折叠 + 高风险独立卡片
- [x] 状态机: pending→executing→success/error，带加载动画
- [x] 参数 JSON 展开 + 结果预览(15行截断) + 复制按钮
- [x] 安全级别标签 (FILE_MODIFY/SYSTEM/UNSAFE)

### 29. ChatMetricsBar — RooCode 风格实时指标 ✅
- **来源**: RooCode TaskHeader.tsx (stats table + ContextWindowProgress)
- **目标**: 对话页实时展示 Token/成本/耗时/成功率
- [x] `ChatMetricsBar.vue`: ContextWindow 进度条 + Token ↑↓ + $成本 + 耗时/轮次/工具成功率

### 30. useChatScroll — Continue 风格智能滚动 ✅
- **来源**: Cline useScrollBehavior (disableAutoScroll + 双重保险)
- **目标**: 用户上滚时不自动滚动，滚回底部时恢复
- [x] `useChatScroll.ts`: 向上滚→暂停；到底部→恢复；3s 超时自动恢复
- [x] 双重保险: smooth + 延迟 40ms/70ms instant snap

### 31. ChatSessionManager — 会话持久化 ✅
- **来源**: RooCode Task Persistence (localStorage + 后端 API)
- **目标**: 页面刷新不丢失聊天记录
- [x] `chatSessionManager.ts`: localStorage 即时恢复 + 30s 自动保存 + 导出/导入
- [x] 最大 200 条消息 / 50 个会话的限制 + 全局单例

### 32. 轨迹 API 增强 ✅
- **来源**: OpenHands 事件系统 + 审计追踪
- **目标**: 分页列表 + 聚合统计 + 多维筛选
- [x] `trajectory.py`: GET /list (分页+状态/模型/搜索筛选) + GET /stats (成功率/Top模型/均值)
- [x] `model-features.ts`: TrajectoryListItem / TrajectoryStats 类型 + API 方法

**文件变更** (6 文件, +1107/-2):
| 文件 | 改动 |
|------|------|
| `ToolCallCard.vue` (**新增**) | Cline 风格工具调用卡片 (308行) |
| `ChatMetricsBar.vue` (**新增**) | RooCode 风格实时指标栏 (146行) |
| `useChatScroll.ts` (**新增**) | Continue 风格智能滚动 (141行) |
| `chatSessionManager.ts` (**新增**) | RooCode 风格会话持久化 (297行) |
| `trajectory.py` | 新增 /list(分页+筛选) + /stats(聚合) (168行) |
| `model-features.ts` | 新增 TrajectoryListItem/Stats 类型 + API (49行) |

---

## Session 14 — Git-Native Agent + Human Input + Memory 图 (参考 Aider/AutoGen/HermesStudio/MCP)

### 33. FuzzyDiffer — Aider 风格模糊 Diff 引擎 ✅
- **来源**: Aider diffs.py (Search-Replace 编辑 + Fuzzy Match + 冲突检测)
- **目标**: AI 生成的代码 diff 容错匹配 + 自动冲突检测
- [x] `differ.py` (377行): FuzzyDiffer + EditBlock + DiffResult
- [x] 三层匹配: 精确→行级模糊→块级模糊 (阈值 0.8)
- [x] 冲突检测 (多编辑重叠区间) + 逆操作撤销
- [x] parse_edit_blocks() + multi_file_apply() + 全局单例

### 34. Git Auto-Commit — Aider 风格 Git-Native 编辑 ✅
- **来源**: Aider main_loop.py (每次修改 = 一个 git commit)
- **目标**: Agent 代码修改后自动 git add + commit
- [x] `agent_runner`: _git_auto_commit() 在 Memory 提取后自动提交
- [x] `orchestrator`: _git_auto_commit() 在 Pipeline 完成后自动提交

### 35. Human Input Mode — AutoGen 风格审批控制 ✅
- **来源**: AutoGen HumanInputMode (NEVER/TERMINATE/ALWAYS)
- **目标**: 高/中/低风险操作分级审批
- [x] `agent_modes`: HumanInputMode 枚举 + 字段
- [x] `agent_config`: human_input_mode + git_auto_commit
- [x] debug 模式默认 ALWAYS

### 36. MemoryGraphPanel — HermesStudio 风格记忆图可视化 ✅
- **来源**: HermesStudio Memory.vue + 图可视化
- [x] `MemoryGraphPanel.vue` (678行): SVG 力导向图 + 拖拽/缩放 + 筛选 + 详情

### 37. 前端 Memory Graph API ✅
- [x] memoryGraphApi.graphData/stats + 类型定义

**文件变更** (8 文件, +1324/-1):
| 文件 | 改动 |
|------|------|
| `differ.py` (**新增**) | FuzzyDiffer + 三层模糊匹配 + 冲突检测 (377行) |
| `MemoryGraphPanel.vue` (**新增**) | SVG 记忆图 (678行) |
| `agent_runner.py` | _git_auto_commit() (104行) |
| `orchestrator.py` | _git_auto_commit() + 新参数 (80行) |
| `agent_modes.py` | HumanInputMode 枚举 (24行) |
| `agent_config.py` | human_input_mode + git_auto_commit (8行) |
| `model-features.ts` | MemoryGraph API 类型 (45行) |
| `__init__.py` | FuzzyDiffer/HumanInputMode 导出 (9行) |

---

## 参考仓库待深入

| 仓库 | 学习重点 | 对应任务 |
|------|---------|---------|
| LangGraph | StateGraph + 条件路由 + Checkpoint | Session 12 (WorkflowGraph) |
| SWE-agent | SmartContext + ACP 协议 + 环境管理 | Session 12 (ContextWindow) |
| CrewAI | Task Context Chain + Process 编排 | Session 12 (上下文链) |
| OpenHands | AgentSkills + Sandbox Timeout + 审计追踪 | Session 12/15 |
| Continue | IDE 嵌入式 Agent + 上下文策略 | Session 16 |
| Tabby | 本地代码补全 + FIM + ghost text | Session 16 |
| Zed | GPUI Layout + Multi-buffer editing | Session 16 |
| Cline | 结构化 Prompt + Always Allow + ToolCallCard | Session 08/13/15 |
| RooCode | 检查点回滚 + TaskHeader 指标 + 会话持久化 | Session 13/15 |
| OpenInterpreter | Smart Auto-Approval + Sandbox 安全 | Session 15 |
| cognee | Pipeline 架构 + 自动本体生成 | Session 06 |
| Agent-Reach | Channel 抽象 + 多后端回退 | Session 05 |
| hermes-agent | 预算感知循环 + Session 树 | Session 05/06 |
| AutoCLI | YAML 适配器 + 流水线组合 | Session 06 |
| anthropics/skills | SKILL.md 规范 | Session 05 |
| openai/skills | Plugins 分层 | Session 05 |
| Aider | Fuzzy Diff + Git Auto-Commit | Session 14 |
| AutoGen | HumanInputMode 审批控制 | Session 14 |

---

## Session 15 — 智能审批+文件检查点+提示词模板 (RooCode/Cline/OpenHands借鉴)

### 38. FileCheckpoint/Rollback ✅
- **来源**: RooCode checkpoints/ 文件内容快照 + 多轮回滚
- **目标**: Agent 每轮修改后自动保存检查点，支持回滚到任意检查点
- **涉及文件**: `backend/app/core/agent/checkpoint.py`, `backend/app/api/routes/agent/checkpoint.py`
- [x] `FileCheckpoint` dataclass: id/agent_name/turn_number/files_modified/metadata
- [x] `FileSnapshot`: path/content_hash/prev_hash/size/encoding/file_mode/modified_at
- [x] `FileCheckpointManager`: save/rollback/list/get/cleanup
- [x] 内联存储 (<50KB) + 磁盘备份 (data/file_checkpoints/)
- [x] AgentRunner 每轮后自动保存 (enable_checkpoint 开关)
- [x] API: GET/POST checkpoints + rollback + cleanup

### 39. Smart Auto-Approval Engine ✅
- **来源**: RooCode auto-approval + OpenInterpreter confirm_mode
- **目标**: RiskLevel 分级审批 + Always Allow 记忆规则
- **涉及文件**: `backend/app/core/agent/auto_approval.py`, `backend/app/api/routes/agent/auto_approval.py`
- [x] `RiskLevel` 枚举: SAFE/MODERATE/DANGEROUS
- [x] `TOOL_RISK_MAP`: 30+ 工具风险映射
- [x] `ApprovalRule`: tool_name + allowed + path_pattern(glob) + param_conditions
- [x] `AutoApprovalEngine`: check/matches + 四种模式 (safe-tools/custom/never/always)
- [x] rules 持久化到 data/approval_rules.json
- [x] API: rules CRUD + check + risk-levels + set-mode

### 40. Structured Prompt Templates ✅
- **来源**: Cline system-prompt 结构化提示体系
- **目标**: 四角色专用提示词模板 + PromptBuilder 动态构建
- **涉及文件**: `backend/app/core/agent/prompt_templates.py`
- [x] `PLANNER_PROMPT`: Architect Agent 分析→设计→分解
- [x] `CODER_PROMPT`: Senior Software Engineer 实现→diff→检查
- [x] `REVIEWER_PROMPT`: Code Review Expert 8点检查表
- [x] `DEBUG_PROMPT`: Debugging Expert 复现→追踪→诊断→修复→验证
- [x] `PromptBuilder`: build() 动态注入 {context_block} (task/plan/code_changes)

### 41. AutoCLI Timeout ✅ (已有)
- **来源**: OpenHands Action Security + OpenInterpreter Sandbox
- **状态**: 已有 `asyncio.wait_for` + `default_timeout=30.0` + per-command 覆盖

**文件变更** (11 文件, +1630/-6):
| 文件 | 改动 |
|------|------|
| `checkpoint.py` (**新增**) | FileCheckpoint + FileCheckpointManager (407行) |
| `auto_approval.py` (**新增**) | AutoApprovalEngine + RiskLevel (437行) |
| `prompt_templates.py` (**新增**) | PromptBuilder + 四角色模板 (283行) |
| `routes/agent/checkpoint.py` (**新增**) | 检查点 CRUD + rollback API (147行) |
| `routes/agent/auto_approval.py` (**新增**) | 审批规则 CRUD + check API (182行) |
| `agent_runner.py` | 每轮后自动保存检查点 (+23行) |
| `agent_config.py` | enable_checkpoint 字段 (+4行) |
| `orchestrator.py` | 集成 PromptBuilder 结构化提示 (+28/-6行) |
| `agent/__init__.py` | 新模块导出 (+19行) |
| `routes/agent/__init__.py` | 新路由注册 (+2行) |
| `model-features.ts` | FileCheckpoint/ApprovalRule 前端类型 (+104行) |

---

## Session 16 — ContextProvider插件+FIM集成 (Continue/Tabby/Zed借鉴)

### 42. ContextProvider 插件系统 ✅
- **来源**: Continue core/context/ ContextProvider 分层管理设计
- **目标**: 替代 AgentRunner 硬编码上下文组装，实现插件化分层注入
- **涉及文件**: `backend/app/core/agent/context_provider.py`
- [x] `ContextProvider` ABC: name + priority + async provide()
- [x] `ContextProviderRegistry`: register/unregister/set_enabled/get_all (按 priority 排序)
- [x] 7 个内置 Provider: SystemInstruction(0)/Skill(10)/ToolDesc(20)/FileContext(30)/RelatedFiles(35)/Memory(40)/Project(50)/MCP(60)
- [x] AgentRunner._assemble_system_prompt() 替代硬编码，回退到 _build_system_prompt()
- [x] 全局单例: init/get_context_provider_registry()

### 43. Skills 接入 Agent 管道 ✅
- **来源**: Continue slash commands + 现有 SkillsManager
- **目标**: SkillContextProvider 自动匹配用户输入并注入技能指令
- [x] SkillContextProvider 桥接 SkillsManager.match() + build_skill_instructions()
- [x] 优先级 10（仅次于系统指令），运行时条件启用

### 44. FIM 代码补全前端集成 ✅
- **来源**: Tabby autocomplete + Continue ghost text
- **目标**: 打通已有 FIMCompletionEngine 后端到前端内联补全
- **涉及文件**: `studio-client/src/api/fim.ts`, `useFIMCompletion.ts`, `CodeEditor.vue`
- [x] `api/fim.ts` (109行): CompletionRequest/Response 类型 + API 方法
- [x] `useFIMCompletion.ts` (278行): 300ms 防抖 + 即时触发 + 幽灵文本 + Tab/Esc
- [x] `CodeEditor.vue`: onKeyDown 按键触发 + Tab/Esc 拦截 + .fim-ghost-text 样式
- [x] 频率限制 500ms + 反馈上报 (sendFeedback)

### 45. Multi-File Context (Zed multi-buffer) ✅
- **来源**: Zed multi-buffer editing + file dependency graph
- **目标**: 为 Agent 提供当前编辑文件的关系文件上下文
- **涉及文件**: `backend/app/core/agent/related_files.py`
- [x] `FileRelationshipTracker`: 最近访问 + import 关系图
- [x] 5 种语言 import 解析 (Python/TS/Vue/Go/Rust)
- [x] 4 级关系: imported-by-current → imports-current → same-dir → recent
- [x] `RelatedFilesProvider` 自动注入关联文件上下文

**文件变更** (7 文件, +1475/-42):
| 文件 | 改动 |
|------|------|
| `context_provider.py` (**新增**) | ContextProvider 插件系统 + 7 内置 Provider (480行) |
| `related_files.py` (**新增**) | 文件关系追踪器 + import 图 + Provider (320行) |
| `api/fim.ts` (**新增**) | FIM 补全 API 服务层 (109行) |
| `useFIMCompletion.ts` (**新增**) | FIM Vue Composable (278行) |
| `agent_runner.py` | _assemble_system_prompt() + ContextProvider 集成 (+53/-27) |
| `agent/__init__.py` | ContextProvider/RelatedFiles 导出 (+16) |
| `CodeEditor.vue` | FIM 集成 + monacoRaw 重构 (+23/-8) |

---

## Session 17 — 前端缺陷修复 + Tauri 功能补全

### 46. 修复 ProjectList 死链接 /projects/new ✅
- **问题**: `ProjectList.vue` 中 `router.push("/projects/new")` 指向不存在的路由，导致被 catch-all 重定向到 `/chat`
- **涉及文件**: `studio-client/src/router/index.ts`, `studio-client/src/pages/ProjectNew.vue`, `studio-client/src/api/studio.ts`
- [x] `router/index.ts`: 新增 `/projects/new` → `ProjectNew.vue` 路由（在 `/projects/:id` 之前）
- [x] `ProjectNew.vue` (**新增**): AI 全栈项目创建页面（手动/AI 双模式 + 模板选择 + 技术栈配置）
- [x] `studio.ts`: 新增 `createProject()` API + `CreateProjectParams` 接口

### 47. AtMentionPopup 假数据替换为真实 API ✅
- **问题**: `recentFiles` 硬编码假数据；`fakeFiles` 命名误导；选中文件后未保存到最近列表
- **涉及文件**: `studio-client/src/components/agent/AtMentionPopup.vue`
- [x] `fakeFiles` → `projectFiles` 重命名，语义清晰
- [x] `recentFiles` 改为从 `localStorage("at_mention_recent_files")` 加载/持久化
- [x] `selectFile()` 调用 `saveRecentFile()` 自动记录最近文件
- [x] 最多保留 10 条最近文件，去重 + LRU

### 48. GlobalSearch Web 回退实现真实搜索 ✅
- **问题**: 非 Tauri 环境下 `doSearch()` 返回空数组（仅 `setTimeout 300ms`），搜索功能完全不可用
- **涉及文件**: `studio-client/src/components/ide/GlobalSearch.vue`
- [x] Web 回退调用 `/api/v1/system/codebase/files?q=...` 真实 API 搜索
- [x] 搜索文件名匹配 → 转换为 SearchResult 格式
- [x] 静默错误处理（API 不可用时显示空结果）

### 49. Tauri 插件安装功能实现 ✅
- **问题**: `install_plugin()` 仅为 `Err("Plugin installation not yet implemented")`
- **涉及文件**: `studio-client/src-tauri/src/commands/plugins.rs` (+~180行)
- [x] `install_from_local()`: 本地路径 → 读取 plugin.json → 复制到 plugins 目录 → 注册
- [x] `install_from_url()`: URL 下载 (curl/PowerShell) → 解压 → 查找 manifest → 安装
- [x] `get_plugins_dir()`: 跨平台数据目录 (Windows: %APPDATA%, macOS: ~/Library, Linux: ~/.local/share)
- [x] `save_registry()` / `load_registry()`: registry.json 持久化
- [x] `find_manifest()`: 递归查找 plugin.json
- [x] `copy_dir_all()`: 递归目录复制
- [x] `uninstall_plugin()` 增强: 同步删除磁盘文件

### 50. Tauri Git Diff 解析完整实现 ✅
- **问题**: `parse_diff_output()` 返回硬编码的占位 `GitDiff`（path="unknown", hunks=[]）
- **涉及文件**: `studio-client/src-tauri/src/commands/git.rs` (+~120行)
- [x] 完整 unified diff 格式解析器
- [x] 解析 `diff --git a/path b/path` → 文件路径 + old_path
- [x] 解析 `--- /dev/null` → 新文件 (status="A")
- [x] 解析 `+++ /dev/null` → 删除文件 (status="D")
- [x] 解析 `@@ -a,b +c,d @@` → hunk 头部 + 行号追踪
- [x] 逐行解析 `+`/`-`/` `  → GitDiffLine + additions/deletions 统计
- [x] `parse_hunk_header()` 辅助函数

**文件变更** (8 文件, +784/-97):
| 文件 | 改动 |
|------|------|
| `router/index.ts` | 新增 `/projects/new` 路由 (+5行) |
| `ProjectNew.vue` (**新增**) | AI 项目创建页 — 双模式 + 模板 (198行) |
| `api/studio.ts` | 新增 createProject + CreateProjectParams (+18行) |
| `AtMentionPopup.vue` | 假数据→localStorage持久化 (+12/-18行) |
| `GlobalSearch.vue` | Web回退→真实API搜索 (+25/-4行) |
| `plugins.rs` | install_plugin完整实现 + 持久化 (+~250/-10行) |
| `git.rs` | parse_diff_output完整unified diff解析 (+~130/-12行) |
| `TASKS.md` | Session 17 记录 (+x行) |

---

## Session 18 — 代码质量与基础设施加固

### 51. Vite 配置修正 ✅
- **问题**: 端口 5177 与 PROGRESS.md 记录的 5173 不一致，代理目标 18000 与开发端口 8000 不一致
- **涉及文件**: `studio-client/vite.config.ts`
- [x] 开发端口: 5177 → 5173
- [x] 代理目标: `http://localhost:18000` → `http://localhost:8000`

### 52. 硬编码占位符密钥 + package.json 清理 ✅
- **问题**: `embedder.py` 硬编码 `"sk-placeholder"`；`@tailwindcss/vite` 和 `vite` 在 dependencies 中应为 devDependencies；根 package.json 重复引入 `@tauri-apps/api`
- **涉及文件**: `backend/app/core/rag/embedder.py`, `studio-client/package.json`, `package.json`
- [x] `embedder.py`: `api_key or "sk-placeholder"` → `api_key or os.getenv("OPENAI_API_KEY", "")`
- [x] `studio-client/package.json`: `@tailwindcss/vite` + `vite` 从 dependencies → devDependencies
- [x] 根 `package.json`: 移除重复的 `@tauri-apps/api` + `@tauri-apps/plugin-dialog`

### 53. models.py lint + MCP marketplace auth ✅
- **问题**: models.py 3 处类型推断/泛型问题；mcp_marketplace 安装时 `user_id=None` 无鉴权上下文
- **涉及文件**: `backend/app/api/routes/system/models.py`, `backend/app/api/routes/agent/mcp_marketplace.py`
- [x] `models.py`: `record.status.value` → `record.status`；`dict[str, dict]` → `dict[str, dict[str, int]]`；添加 `# type: ignore[arg-type]` 标记
- [x] `mcp_marketplace.py`: 新增 `user: CurrentUser` 参数；`user_id=None` → `user_id=user.id if user else None`

### 54. MessageHistoryStore / ConversationStore DB 后端 ✅
- **问题**: 仅有内存实现 (`Memory*Store`)，缺少持久化后端
- **涉及文件**: `backend/app/core/message_history.py`, `backend/app/core/conversation/manager.py`
- [x] `SqliteMessageHistoryStore`: SQLite 持久化（data/messages.db）
  - 6 个 CRUD 操作完整实现
  - message_id 为主键，session_id 索引，timestamp 索引
- [x] `SqliteConversationStore`: SQLite 持久化（data/conversations.db）
  - 5 个 CRUD 操作完整实现 + list_by_session 分页
  - conversation_id 为主键，session_id 索引，updated_at 索引

### 55. AgentChat.vue 死代码验证 ✅
- **问题**: PROGRESS.md Session 01 报告 ~20 未使用变量
- **状态**: 已验证 — 当前零 lint 错误，所有 27 个 icon 导入均在模板中使用
- 未使用变量在前续 Session 中已被逐步清理

**文件变更** (8 文件, +245/-25):
| 文件 | 改动 |
|------|------|
| `vite.config.ts` | 端口 5177→5173 + 代理 18000→8000 |
| `package.json` | 移除重复 Tauri 依赖 |
| `studio-client/package.json` | @tailwindcss/vite+vite→devDependencies |
| `embedder.py` | 移除硬编码 sk-placeholder |
| `models.py` | lint 修复 (3 处) |
| `mcp_marketplace.py` | user_id TODO→CurrentUser 注入 |
| `message_history.py` | 新增 SqliteMessageHistoryStore (~80行) |
| `manager.py` | 新增 SqliteConversationStore (~100行) |

---

## 测试规范

```bash
# 每次修改后运行闭环测试
cd /path/to/ai-fullstack-platform
PYTHONPATH="$PWD/backend:$PYTHONPATH" python3 tests/test_closed_loop.py

# 新增测试必须覆盖跨系统联动
# 使用临时目录，零副作用
```

## 禁止事项

1. ❌ 不可重新创建 `backend/app/core/ckg/` 目录
2. ❌ 不可在 Memory 中引入外部向量数据库
3. ❌ 不可绕过 AutoCLI 安全检测
4. ❌ 不可删除 Agent Mode 的 skills 绑定
5. ❌ 不可在 codebase_memory 中引入非标准库依赖
