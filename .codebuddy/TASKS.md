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

## 参考仓库待深入

| 仓库 | 学习重点 | 对应任务 |
|------|---------|---------|
| cognee | Pipeline 架构 + 自动本体生成 | 任务 2 (Memory 闭环) + Session 06 |
| Agent-Reach | Channel 抽象 + 多后端回退 | 任务 1 (Agent 流水线) + Session 05 |
| hermes-agent | 预算感知循环 + Session 树 | 任务 1/7 (Agent 循环) + Session 05/06 |
| AutoCLI | YAML 适配器 + 流水线组合 | 任务 9 (CLI 日志) + Session 06 |
| anthropics/skills | SKILL.md 规范 | 任务 6 (Skills 热加载) + Session 05 |
| openai/skills | Plugins 分层 | 任务 6 + Session 05 |

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
