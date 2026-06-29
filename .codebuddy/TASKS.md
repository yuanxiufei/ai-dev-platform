# AI Fullstack Platform — 开发任务清单

> **日期**: 2026-06-29  
> **前置**: 四大闭环系统已实现，59 项测试通过  
> **原则**: 所有开发在闭环架构内进行，零外部依赖闭环

---

## P0 — 核心闭环补全

### 1. AgentOrchestrator 接入 AgentRunner 流水线
- **现状**: orchestrator.py 直接调用 ModelRouter，未复用 AgentRunner 的 Middleware/Sandbox/TrajectoryRecorder
- **目标**: 改造 orchestrator 以接入现有 AgentRunner 流水线
- **涉及文件**: `backend/app/core/agent/orchestrator.py`, `backend/app/core/agent/agent_runner.py`
- [ ] orchestrator 的 _execute_subtask 改用 AgentRunner.run()
- [ ] Planner/Coder/Reviewer 各用独立的 AgentConfig + Mode

### 2. Memory 闭环触达 AgentRunner
- **现状**: AgentRunner 未在运行前后加载/保存记忆
- **目标**: before_run 注入记忆上下文，after_run 保存提取的记忆
- **涉及文件**: `backend/app/core/agent/agent_runner.py`, `backend/app/core/memory/`
- [ ] AgentRunner.before_run → MemoryRetriever.retrieve_as_context()
- [ ] AgentRunner.after_run → MemoryExtractor.extract_and_save()

### 3. CodebaseMemory 工具注册到全局 ToolRegistry
- **现状**: TOOL_REGISTRY 仅在 codebase_memory 内部使用
- **目标**: 8 个工具注册到全局 ToolRegistry，Agent 可通过 Function Calling 调用
- **涉及文件**: `backend/app/core/codebase_memory/tools.py`, `backend/app/core/tools/registry.py`
- [ ] 将 8 个 Tool 注册到 ToolRegistry
- [ ] Agent 可通过 tool_calls 调用 search_graph/trace_path 等

---

## P1 — 功能增强

### 4. Cypher 风格图查询 (query_graph)
- **借鉴**: codebase-memory-mcp 的 openCypher 只读子集
- **目标**: 实现 MATCH→WHERE→RETURN 查询，支持聚合和路径遍历
- **涉及文件**: `backend/app/core/codebase_memory/tools.py` (新增 query_graph)
- [ ] 实现 Cypher 词法解析器 (Lexer)
- [ ] 实现 Cypher 语法解析器 (Parser) — MATCH/WHERE/RETURN/ORDER BY/LIMIT
- [ ] SQL 翻译层 → SQLite 执行
- [ ] 更新 TOOL_REGISTRY 添加 query_graph

### 5. Git 变更自动增量索引
- **现状**: FileIndexer 需手动触发 index()
- **目标**: 检测 git 变更后自动增量索引
- **涉及文件**: `backend/app/core/codebase_memory/indexer.py`
- [ ] 实现 GitWatcher (poll git diff 检测变更文件)
- [ ] 增量索引 (只重新解析变更的文件)
- [ ] 后台线程持续监听

### 6. Skills 热加载
- **现状**: SkillManager 仅在启动时 discover()
- **目标**: 运行时检测新 skill 文件，自动激活
- **涉及文件**: `backend/app/core/skills/skill_manager.py`
- [ ] 文件系统监听 (watchdog/inotify)
- [ ] 检测到新 SKILL.md → 自动解析注册
- [ ] API 端点触发重新发现

### 7. Agent 反思→Memory 闭环
- **现状**: reflection.py 的反思结果未保存到 MemoryStore
- **目标**: 反思结果自动调用 MemoryExtractor，保存为 LESSON 类型
- **涉及文件**: `backend/app/core/agent/reflection.py`, `backend/app/core/memory/`
- [ ] ReflectionManager 在 reflect() 后调用 MemoryExtractor
- [ ] 保存为 MemoryType.LESSON，关联原任务

---

## P2 — 平台体验

### 8. Memory 可视化 UI
- **现状**: 记忆仅存在 SQLite，无可视化
- **目标**: Studio 前端展示记忆节点和关系图
- [ ] 后端 API: GET /api/v1/memory/graph-data
- [ ] 前端: 知识图谱组件 (节点+边渲染)

### 9. AutoCLI 执行日志
- **现状**: CLI 执行无持久化记录
- **目标**: 记录每次执行到 TraceDB
- [ ] AutoCLI.execute() 写入 TraceDB
- [ ] API: GET /api/v1/system/cli-history

### 10. Agent 轨迹回放
- **现状**: TrajectoryRecorder 记录轨迹但无回放
- **目标**: 前端可视化回放 Agent 执行步骤
- [ ] API: GET /api/v1/agent/trajectories/{id}/replay
- [ ] 前端: 步骤时间线 + 详情面板

---

## 参考仓库待深入

| 仓库 | 学习重点 | 对应任务 |
|------|---------|---------|
| cognee | Pipeline 架构 + 自动本体生成 | 任务 2 (Memory 闭环) |
| Agent-Reach | Channel 抽象 + 多后端回退 | 任务 1 (Agent 流水线) |
| hermes-agent | 预算感知循环 + Session 树 | 任务 1/7 (Agent 循环) |
| AutoCLI | YAML 适配器 + 流水线组合 | 任务 9 (CLI 日志) |
| anthropics/skills | SKILL.md 规范 | 任务 6 (Skills 热加载) |
| openai/skills | Plugins 分层 (system/curated/experimental) | 任务 6 |

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
