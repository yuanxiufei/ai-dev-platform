# 开发进度记录

> 每次开发会话的详细记录，包括完成内容、技术决策、已知问题和后续待办。

---

## Session 01 — 2026-06-24（凌晨）模型选择功能完整实现

### 目标
修复 AgentChat 页面模型选择器：从「显示 0 模型 / UI 闪烁」到「完整展示 28 个模型并正确路由到选定模型」。

### 完成内容

#### Phase 1: 前端模型列表加载修复
- **问题**：`loadModels()` 函数 try 块为空 → API 调用缺失 → 显示 0 个模型
- **根因**：之前编辑意外删除了 API 调用体；且 token 为 `false`（未登录）时请求被跳过
- **修复**：
  - 恢复 `listAvailableModels()` 调用
  - 改用原生 `fetch()` 替代 axios（绕过 axios 401 拦截器导致的登录重定向循环）
  - 后端 `GET /api/v1/system/models` 移除 `CurrentUser` 认证依赖，改为公开接口
- **涉及文件**：
  - `studio-client/src/pages/AgentChat.vue` — loadModels() 重写
  - `backend/app/api/routes/system/models.py` — 移除 auth 要求
  - `studio-client/src/api/agent.ts` — 新增 listAvailableModels()
  - `studio-client/src/types/studio.ts` — 新增 ModelOption 接口

#### Phase 2: 模型选择后实际生效（核心难点）
- **问题**：用户选择了本地模型（如 qwen25-coder-7b），但后端仍然调用 DeepSeek
- **根因链路分析**：
  1. 本地 safetensors 模型未安装 transformers → 返回空结果（latency=0ms）
  2. 空结果触发 FallbackChain 回退到 Layer 4（第三方 API）
  3. 用户有 Ollama 本地服务运行了 12+ 个模型，但 registry 只注册了 1 个 Ollama 模型
- **架构决策**：创建 **ApiModelAdapter** 体系，让每个远程/Ollama 模型可被独立选择和路由
- **实现方案**：
  - `ai_models/registry.py` — 注册 12 个 Ollama 本地模型（标记 `extra={"is_local_api": True}`）
  - `backend/app/core/model_router.py` — 新增 `ApiModelAdapter(ICandidateModel)` 类 + `build_api_model_adapters()` 工厂函数
  - `_try_specific_model()` 重写为三层搜索：API models → local models → provider candidates
  - `backend/app/core/providers/base.py` — 新增 `_get_model_name()` 支持 `api_model_id` 覆盖
  - 所有 7 个 provider 文件统一使用 `self._get_model_name(request)`
  - `backend/app/main.py` — 初始化时构建 api_models 注入 ModelRouter

#### Phase 3: UI 分组正确性修复
- **问题**：Ollama 模型虽然运行在本地，但被归类到「远程 API」分组（蓝色 Globe 图标）
- **根因**：后端返回所有 remote_configs 时统一设置 `is_local=False`，没检查 `extra.is_local_api` 标记
- **修复**：`models.py` 两处返回逻辑增加 `config.extra.get("is_local_api")` 判断
- **效果**：12 个 Ollama 模型归入「本地模型」（绿色 Cpu 图标），真正的远程 API 保持蓝色 Globe

#### Phase 4: 前端 IDE 组件优化
- **ChatPanel.vue** 大重构：从 mock 生成改为调用 `agentChatSimple()` 真实 API
- IDE Store 布局调宽：sidebar 260px / rightPanel 420px / bottomPanel 240px
- 4 个页面统一背景色样式
- Vite proxy target 从 18000 改为 8000（匹配 standalone 开发端口）

#### Phase 5: 配置与环境修复
- `config.py` 改用 `load_dotenv()` + 绝对路径解决 Windows 下 pydantic-settings 相对路径不准的问题
- `.env` 中 DEEPSEEK_API_BASE_URL 修正为 `api.deepseek.com`（原 `.cn` 域名可能不稳定）
- 4 个 `pyproject.toml` 补充 `hatch.build.targets.wheel.packages` 配置

### 提交清单（5 commits）

| Commit | Hash | 内容 | 文件数 |
|--------|------|------|--------|
| 1 | `003712f` | feat: 完整模型选择功能 | 16, +828 |
| 2 | `17ebc3e` | fix: 配置环境修复 | 8, +80 |
| 3 | `dd8ef64` | feat: Agent 诊断日志+健康检查改进 | 2, +69 |
| 4 | `21f86f5` | feat: 前端 IDE 组件优化 | 19, +198 |
| 5 | `e522565` | chore: 开发工具+清理临时文件 | 4, +17 |

### 注册的 28 个模型一览

| 分组 | 数量 | 示例 |
|------|------|------|
| Ollama 本地 | 12 | qwen3-coder-30b(P50), deepseek-r1(P48), gemma4-31b(P44) |
| 远程 API | 13 | openai-o3(P38), claude-sonnet(P36), deepseek-v3(P34) |
| 本地文件(Safetensors/GGUF) | 4 | qwen25-coder-7b, gemma-31b, qwen25-vl-7b, cogvideox-5b |

### 已知问题与后续待办

#### 🔴 高优先级

1. **本地 Safetensors 模型不可用**
   - **现象**：qwen25-coder-7b、qwen25-vl-7b、cogvideox-5b 显示 `is_downloaded: false`
   - **原因**：需要安装 `transformers` 库并下载模型权重到 `models/` 目录
   - **待办**：
     ```bash
     # 安装依赖
     uv pip install transformers torch torchvision

     # 下载模型（通过 API 或 CLI）
     curl -X POST http://localhost:8000/api/v1/system/models/download \
       -H "Content-Type: application/json" \
       -d '{"model_name": "qwen25-coder-7b", "source": "huggingface"}'
     ```
   - **备注**：当前 Ollama 模型已可正常使用，Safetensors 为可选增强

2. **chat.py 诊断代码需清理**
   - **现象**：`agent/chat.py` 返回值包含 `_diag`、`_errors`、`_network` 字段
   - **原因**：调试阶段添加的诊断信息
   - **待办**：确认功能稳定后移除或改为 DEBUG 日志级别输出，不应返回给前端

3. **health.py 强制重初始化网关**
   - **现象**：detailed_health 每次调用都 `init_provider_registry()` 重新初始化
   - **影响**：频繁调用时性能开销
   - **待办**：改用缓存或定时刷新策略

#### 🟡 中优先级

4. **AgentChat.vue 未使用变量**
   - Lint 报告 ~20 个 unused variables/functions（selectModel 在模板中使用了不算）
   - **待办**：清理死代码或添加 `// @ts-ignore` / `// eslint-disable`

5. **models.py 的 lint 错误（已有，非本次引入）**
   - Line 285: `.value` 类型推断失败（DownloadStatus 枚举）
   - Line 556: `.desc` 类型推断失败（SQLModel order_by）
   - Line 560: `dict` 缺泛型参数
   - **待办**：升级 ty/sqlmy 类型存根或调整写法

6. **uv.lock 与 pyproject.toml 同步**
   - starlette 0.46→0.52 等大版本跳跃
   - **待办**：确认无 breaking change，必要时锁回兼容版本

#### 🟢 低优先级 / 建议

7. **`.gitignore` 补充**
   - 当前 `__pycache__/` 未在 gitignore 中（task_queue 的误入库说明这一点）
   - **建议**：添加 `__pycache__/`、`*.pyc`、`_test_result.txt` 等

8. **start-backend.bat 端口硬编码**
   - 当前固定 8000，与 development.md 中的 18000 不一致
   - **建议**：读取 .env 或支持参数传入

9. **前端 ChatPanel 与 AgentChat 功能重叠**
   - ChatPanel.vue 也接入了 agentChatSimple API
   - AgentChat.vue 有更完整的模型选择器
   - **建议**：明确两个组件的分工，避免重复维护

10. **SSE 流式对话未接入模型选择**
    - 当前 `POST /studio/chat/stream` 不传递 `preferred_model`
    - **待办**：流式对话也需要支持模型选择参数

11. **Ollama 模型在线状态检测**
    - 目前只检查 registry 是否注册，不验证 Ollama 服务是否真的在跑
    - **建议**：初始化时 ping `http://localhost:11434/api/tags` 确认可用

---

## Session 02 — 2026-06-30（晚上）P0 闭环补全 + P1.7 反思→Memory

### 目标
按 TASKS.md 完成 P0 核心闭环补全任务（3 项）+ P1.7 Agent 反思→Memory 闭环。

### 完成内容

#### P0.3: CodebaseMemory 工具注册到全局 ToolRegistry
- **问题**: `init_codebase_tools_to_global_registry()` 在 tools.py 中已定义（8 个 FunctionTool 包装），但 main.py 中未调用
- **修复**: 在 `main.py` 的 Codebase Memory 初始化块中新增调用：
  ```python
  from app.core.codebase_memory.tools import init_codebase_tools_to_global_registry
  global_count = init_codebase_tools_to_global_registry()
  ```
- **效果**: Agent 现在可通过 Function Calling 直接调用 `search_graph` / `trace_path` / `index_repository` 等 8 个工具（非 cbm_ 前缀，原始名称）

#### P0.1/0.2 验证（上一会话已完成）
- ✅ orchestrator.py: `_execute_subtask` 已通过 `AgentRunner.run()` 运行子任务
- ✅ agent_runner.py: before_run 注入 MemoryRetriever 上下文，after_run 调用 MemoryExtractor
- ✅ agent_config.py: `enable_memory: bool = True` 字段已添加

#### P1.7: Agent 反思→Memory 闭环
- **问题 1**: `ReflectionManager._save_to_memory()` 保存到向量层 key-value 存储，而非图存储的 LESSON 节点
- **问题 2**: `agent_runner.py` 的 `run()` 方法完全没有调用 `ReflectionManager.after_run()`
- **修复 1 (reflection.py)**:
  - 重写 `_save_to_memory()` — 改用 `MemoryExtractor.extract_from_reflection()` 提取 LESSON 类型节点，保存到图 `MemoryStore`
  - 新增 `_build_reflection_text()` 静态方法 — 将 issues/suggestions/scores 格式化为可解析文本
  - 兜底逻辑：如果未提取到结构化教训，则保存 `result.summary()` 作为 LESSON 摘要节点
- **修复 2 (agent_runner.py)**:
  - 在 Lakeview 摘要生成后、logger.info 前添加 ReflectionManager 调用：
    ```python
    rm = get_reflection_manager()
    if rm.config.enabled:
        auth_reflect = result.error == "" or rm.config.reflect_on_error
        if should_reflect:
            await rm.after_run(run_result=result, task_description=user_message, agent_actions=...)
    ```
- **效果**: 每次 Agent 运行结束后 → LLM 自省评估 → 提取 LESSON 教训 → 存入图记忆 → 下次运行前通过 MemoryRetriever 注入改进指导

### 数据流（完整闭环）
```
AgentRunner.run()
  ├─ before_run: MemoryRetriever.retrieve_as_context() → system prompt 增强
  ├─ 主循环: LLM ↔ ToolExecutor (含 Sandbox/Middleware/TrajectoryRecorder)
  └─ after_run:
       ├─ MemoryExtractor.extract_from_conversation() → DECISION/PATTERN/FACT
       └─ ReflectionManager.after_run()
            └─ AgentReflector.reflect() → LLM 自省评估
                 └─ MemoryExtractor.extract_from_reflection() → LESSON 节点
                      └─ MemoryStore.save(node) → SQLite 图存储
```

### 涉及文件（4 个修改）
| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/main.py` | 修改 | 新增 `init_codebase_tools_to_global_registry()` 调用 |
| `backend/app/core/agent/reflection.py` | 重写 | `_save_to_memory()` 改用图存储 + LESSON 提取；新增 `_build_reflection_text()` |
| `backend/app/core/agent/agent_runner.py` | 新增 | ReflectionManager.after_run() 调用（Lakeview 之后） |
| `backend/app/core/codebase_memory/tools.py` | 无需修改 | 上一会话已完成 |

### 待办
- P2.8/9/10 前端组件完善 (Memory 图谱渲染、Trajectory 时间线)

---

## Session 03 — 2026-06-30（晚上）P1 全部 + P2 全部

### 目标
按 TASKS.md 完成 P1.4~P1.6 功能增强 + P2.8~P2.10 平台体验。

### 完成内容

#### P1.4: Cypher 风格图查询
- **新文件**: `backend/app/core/codebase_memory/cypher.py` (~400行)
  - `Lexer` 类: 词法解析器 — 支持 MATCH/WHERE/RETURN/ORDER BY/LIMIT 等 18 种 TokenType
  - `Parser` 类: 递归下降语法解析器 — 生成 `CypherAST` (MatchClause/WhereCondition/ReturnItem/OrderByItem)
  - `QueryEngine` 类: AST → SQL 翻译 + 内存执行回退
    - SQLite 模式: 翻译为 graph_nodes/graph_edges 表 JOIN 查询
    - 内存模式: 遍历 CodeGraph._nodes/_edges 执行过滤
  - 便捷 API: `query_graph(query_text, db_path, graph)`
- **tools.py**: 新增 `tool_query_graph()` + 注册到 TOOL_REGISTRY (9→10 工具) 和全局 FunctionTool

#### P1.5: Git 变更自动增量索引
- **修改文件**: `backend/app/core/codebase_memory/indexer.py` (+~120行)
  - 新增 `GitIndexer` 类:
    - `get_changed_files()`: 通过 `git diff --name-only <base> HEAD` 检测变更
    - `incremental_index()`: 仅重新解析变更文件（删除旧节点→重新解析→更新哈希）
    - `_save_commit()`: 记录 HEAD commit hash + branch 到 git_status 表
    - 后台轮询: `start_watching()` / `stop_watching()` (间隔 60s)
    - 回调: `on_indexed(callback)`
- **main.py**: Codebase Memory 初始化后启动 GitIndexer watcher

#### P1.6: Skills 热加载
- **修改文件**: `backend/app/core/skills/skill_manager.py` (+~110行)
  - 新增 `SkillWatcher` 类:
    - 采用 mtime 轮询模式（借鉴 ConfigReloader）
    - `_snapshot()` / `_has_changes()`: 目录和文件变更检测
    - `reload_now()`: 触发异步 `SkillManager.discover()`
    - 后台线程: `start_watching()` / `stop_watching()` (间隔 5s)
  - 全局单例: `init_skill_watcher()` / `get_skill_watcher()`
- **skills API** (`agent/skills.py`): 新增 `POST /skills/reload` 端点
- **main.py**: Skills 初始化后启动 SkillWatcher

#### P2.8: Memory 可视化 API
- **新文件**: `backend/app/api/routes/system/memory_graph.py`
  - `GET /api/v1/memory/graph-data`: 查询 MemoryNode + MemoryEdge，返回 {nodes, edges, node_count, edge_count, type_counts}
  - `GET /api/v1/memory/graph-stats`: 记忆统计摘要
  - 支持按 type/min_importance 过滤
- 注册到 system 路由和 main.py

#### P2.9: AutoCLI 执行日志
- **修改文件**: `backend/app/core/tools/autocli.py` (+25行)
  - AutoCLI 类新增 `_log_to_tracedb()` 方法
  - `execute()` 所有执行路径（成功/超时/异常/安全拒绝）均写入 `data/cli_history.jsonl`
  - 日志字段: command, exit_code, latency_ms, security_level, workspace, timestamp
- **新文件**: `backend/app/api/routes/system/cli_history.py`
  - `GET /api/v1/system/cli-history`: 分页查询执行历史（最新在前）
  - 含 success/error 统计
- 注册到 system 路由和 main.py

#### P2.10: Agent 轨迹回放
- **修改文件**: `backend/app/api/routes/agent/trajectory.py` (+60行)
  - `GET /api/v1/agent/trajectory/{agent_id}/replay`: 轨迹回放 API
    - 自动解析多种轨迹格式 (steps/trajectory/events)
    - 构建 steps 时间线: {step, type, action, input, output, elapsed_ms, error}
    - 摘要: agent_id, session_id, total_steps, final_answer, success
    - 兼容 JSON 和 JSONL 轨迹文件

### 修改文件清单（全部零 lint 错误）

| 文件 | 变更 | 任务 |
|------|------|------|
| `backend/app/core/codebase_memory/cypher.py` | 新增 ~400行 | P1.4 |
| `backend/app/core/codebase_memory/tools.py` | +30行 | P1.4 |
| `backend/app/core/codebase_memory/indexer.py` | +120行 | P1.5 |
| `backend/app/core/skills/skill_manager.py` | +110行 | P1.6 |
| `backend/app/api/routes/agent/skills.py` | +12行 | P1.6 |
| `backend/app/main.py` | +20行 | P1.5/P1.6 |
| `backend/app/api/routes/system/memory_graph.py` | 新增 ~100行 | P2.8 |
| `backend/app/api/routes/system/cli_history.py` | 新增 ~50行 | P2.9 |
| `backend/app/api/routes/system/__init__.py` | +4行 | P2.8/P2.9 |
| `backend/app/api/routes/agent/trajectory.py` | +60行 | P2.10 |
| `backend/app/core/tools/autocli.py` | +25行 | P2.9 |
| `backend/app/api/main.py` | +4行 | P2.8/P2.9 |

### 剩余前端工作 (P2 前端)
- ~~Memory 可视化图谱组件~~ ✅ 已完成
- ~~Agent 轨迹回放时间线组件~~ ✅ 已完成

---

## Session 04 — 2026-06-30（晚上）P2 前端组件补全

### 目标
完成 TASKS.md 剩余的 P2.8（KnowledgeGraphPage）和 P2.10（TrajectoryPage）前端组件。

### 完成内容

#### KnowledgeGraphPage.vue 增强
- **Bug 修复**: 所有模板引用的变量去掉了 `_` 前缀（原 `_viewMode`/`_graphLayout`/`_svgViewBox`/`_nodeColor`/`_doParse` 导致模板无法绑定）
- **新增功能**:
  - 节点搜索过滤（按 id/label/domain）
  - 图谱缩放控制（放大/缩小/重置，zoom 0.3x~2.5x）
  - 节点点击选中 → 详情面板（显示 label/id/domain/importance）
  - 图表域色彩编码（10 色调色板）
  - SVG 节点阴影效果
  - 6 卡片统计栏（记忆总数/链接数/反向链接/孤立节点/热门节点/图密度）
  - 反向链接增加 hover 高亮
  - 解析器增加 Callout 渲染 + 颜色分类
  - 统计视图增加孤立节点列表
  - 加载状态指示器

#### TrajectoryPage.vue 新建
- **文件**: `studio-client/src/pages/TrajectoryPage.vue` (~170行)
- 双栏布局：左侧轨迹文件列表 + 右侧回放区域
- 左侧：按 Agent ID 筛选 / 文件大小+修改时间 / 选中高亮 / 删除
- 右侧回放：摘要卡片（成功/失败/总步骤/耗时/成功率）+ Agent/Session 元信息
- 步骤时间线：垂直时间线 + 类型色标（工具🟡/推理🟣/错误🔴/计划🔵/完成🟢）+ 错误红色高亮
- 空状态 + 加载指示器

#### 前端 API 层
- `model-features.ts` 新增 `trajectoryApi`（list/getAgent/replay/delete 4 个端点）
- 新增 `TrajectoryFile`/`TrajectorySummary`/`TrajectoryStep`/`TrajectoryReplay` 类型

#### 路由注册
- `router/index.ts` 新增 `/trajectory` → `TrajectoryPage.vue`

### 修改文件清单（全部零 lint 错误）

| 文件 | 变更 | 说明 |
|------|------|------|
| `studio-client/src/pages/KnowledgeGraphPage.vue` | 重写 ~230行 | Bug修复 + 可视化增强 |
| `studio-client/src/pages/TrajectoryPage.vue` | 新增 ~170行 | Agent 轨迹回放 |
| `studio-client/src/api/model-features.ts` | +50行 | trajectoryApi + 类型定义 |
| `studio-client/src/router/index.ts` | +5行 | /trajectory 路由 |
| `.codebuddy/TASKS.md` | 更新 | P2.8/P2.10 前端标记完成 |

### 状态：TASKS.md 全部 10 项任务已完成 🎉

---

## Session 05 — 2026-06-30（晚上）参考仓库深度借鉴

### 目标
基于 6 个参考仓库的深度分析，将精华设计模式融入 ai-fullstack-platform：
- **hermes-agent** → Agent 预算感知循环
- **anthropics-skills** → SKILL.md v2 规范对齐
- **Agent-Reach** → 模型健康检查机制

### 完成内容

#### 13. Agent 预算感知循环（借鉴 hermes-agent）
- **新文件**: `backend/app/core/agent/budget.py` (~280行)
  - `BudgetTracker`: token/cost/time 三层预算追踪器
  - `PricingTier`: 模型定价表（USD/百万tokens），覆盖 OpenAI/Anthropic/DeepSeek/Ollama
  - `BudgetStatus`: HEALTHY → WARNING → CRITICAL → EXHAUSTED 四级状态
  - 模糊定价匹配（按模型名关键字自动推断价格）
  - `create_default_budget()` / `create_dev_budget()` / `create_tight_budget()` 工厂函数
- **AgentConfig 集成**: 新增 4 个预算字段:
  - `enable_budget: bool` — 开关
  - `token_budget: int = 200000` — 最大 cumulative tokens
  - `cost_budget_usd: float = 5.0` — 最大累计成本
  - `time_budget_ms: float = 300000` — 最大运行时间
- **AgentRunner 集成**:
  - 每轮循环开始前检查预算（`should_continue()`）
  - 预算耗尽 → 优雅终止（提取最近 assistant 消息作为答案，非硬中断）
  - 预算 CRITICAL 时输出警告日志
  - 每轮 LLM 调用后记录消耗（`budget_tracker.record()`）
  - 结果注入预算摘要（`result.metadata["budget"]`）

#### 12. SKILL.md v2 规范对齐（借鉴 anthropics-skills + openai-skills）
- **SkillInfo v2**: 新增 9 个字段:
  - `license_info` / `version` / `author` / `tags` / `tier` / `requires_confirmation`
  - `scripts_dir` / `references_dir` / `assets_dir` (捆绑资源)
  - `_raw_content` / `_body_only` (内容缓存)
- **_parse_frontmatter_v2()**: 完整 YAML frontmatter 解析（9 字段），支持 tags JSON 列表/逗号分隔
- **渐进披露**:
  - `build_skills_prompt(level=1)`: Level 1 元数据摘要（始终在上下文中）
  - `build_skills_prompt(level=2)`: Level 2 完整 SKILL.md 内容
  - `build_skills_prompt(level=3)`: Level 3 捆绑资源引用
  - 按 tier 排序 (system > curated > experimental)
  - ⚠️ 标记需要确认的技能
- **格式验证**: `validate_skill()` / `validate_all()` — 检查必填字段 + tier 有效性 + 资源目录

#### 11. 模型健康检查（借鉴 Agent-Reach）
- **新文件**: `backend/app/core/agent/model_health.py` (~320行)
  - `HealthStatus`: healthy / degraded / unhealthy / unknown / disabled
  - `MonitoredModel`: 被监控模型条目（含失败/成功计数 + 适配器引用）
  - `ModelHealthChecker`:
    - `register()` / `register_from_adapters()` - 注册模型
    - `start(interval)` / `stop()` - 后台健康检查循环
    - `run_check_now()` - 手动触发全量检查
    - 3 种探测策略：`_ping_ollama()` (HTTP /api/tags) / `_ping_http()` (API key检查) / `_ping_local()` (文件存在性)
    - 连续失败 3 次才标记 unhealthy，连续成功 2 次恢复
    - 高延迟 (>5s) 标记 degraded
    - 同步更新 `model_adapter.is_available` 标志
- **API 端点**: `backend/app/api/routes/system/model_health.py`
  - `GET /system/model-health` — 查询所有模型健康状态
  - `POST /system/model-health/check` — 手动触发健康检查
- **main.py 集成**: ModelRouter 初始化后启动 ModelHealthChecker（每 2 分钟探测）

### 修改文件清单（全部零 lint 错误）

| 文件 | 变更 | 来源 |
|------|------|------|
| `backend/app/core/agent/budget.py` | **新增** ~280行 | hermes-agent |
| `backend/app/core/agent/model_health.py` | **新增** ~320行 | Agent-Reach |
| `backend/app/core/agent/agent_config.py` | +7行 | 预算字段 |
| `backend/app/core/agent/agent_runner.py` | +40行 | 预算集成 |
| `backend/app/core/skills/skill_manager.py` | +150行 | anthropics-skills |
| `backend/app/api/routes/system/model_health.py` | **新增** ~70行 | Agent-Reach |
| `backend/app/api/routes/system/__init__.py` | +2行 | 路由导出 |
| `backend/app/api/main.py` | +3行 | 路由注册 |
| `backend/app/main.py` | +20行 | HealthChecker 启动 |
| `.codebuddy/TASKS.md` | 更新 | Session 05 任务 11-13 |

### 架构演变

```
Session 01-04: 核心闭环 (P0.1~P2.10 全部完成)
  ├─ Agent流水线: AgentRunner + Sandbox + Middleware + TrajectoryRecorder
  ├─ Memory闭环: MemoryRetriever → MemoryExtractor → MemoryStore (图存储)
  ├─ Reflection: LLM自省 → LESSON教训 → 图记忆
  ├─ Codebase: Cypher查询 + Git增量索引
  └─ 前端: KnowledgeGraphPage + TrajectoryPage

Session 05: 参考仓库深度借鉴（预算+技能+健康检查）✨
  ├─ BudgetTracker (hermes-agent): 三层预算感知循环
  ├─ SKILL.md v2 (anthropics-skills): 渐进披露+资源目录+分层
  └─ ModelHealthChecker (Agent-Reach): 健康探测+动态可用性

Session 06: 管道正式化 + CLI 流水线 + Session 树 🔄
  ├─ Pipeline (cognee): @step 装饰器 + run_pipeline 延迟调用
  ├─ CLIPipeline (AutoCLI): YAML 步骤定义 + 串并行拓扑排序
  └─ SessionTree (hermes-agent): 分支/检查点/快照恢复
```

---

## Session 06 变更记录

### 新增文件

#### 14. Agent 管道正式化（借鉴 cognee）
- **新文件**: `backend/app/core/agent/pipeline.py` (~190行)
  - `@step` 装饰器：标记函数为管道步骤 → `StepSpec`
  - `StepSpec.__call__()` → `BoundStep`（不执行，只绑定参数）
  - `Pipeline` 类：`add`/`add_if` 流式 API，`run()` 编排
  - `run_pipeline()`：按序执行步骤链，output → next input
  - `define_pipeline()`：DSL 快捷构建（传 StepSpec 列表）
  - `PipelineContext`：上下文传递（step outputs 间引用）
  - 支持 async function / coroutine / generator / condition 跳过

#### 15. AutoCLI 流水线组合（借鉴 AutoCLI）
- **新文件**: `backend/app/core/tools/cli_pipeline.py` (~380行)
  - `PipelineStep`: 单个步骤定义（id/command/depends_on/parallel_with/condition/max_retries）
  - `CLIPipeline`: 多步骤执行器（拓扑排序 → 分组并行 → 逐步骤执行）
  - `CLIPipelineLoader`: YAML 文件/字符串加载器
  - `PipelineExecutionContext`: 变量作用域（`{{step.stdout}}` / `${ENV_VAR}` / `$VAR`）
  - `PipelineResult` / `PipelineStepResult`: 结构化结果
  - `load_pipeline()` / `build_pipeline()`: 工厂函数
  - 重试机制：`max_retries` + `retry_delay` + `on_failure=retry|continue|stop`

#### 16. Session 树 + 检查点恢复（借鉴 hermes-agent）
- **新文件**: `backend/app/core/agent/session_tree.py` (~360行)
  - `SessionNode`: 树节点（parent/children/branch/depth/forked_from/checkpoint_id）
  - `Checkpoint`: 状态快照（完整消息历史 + agent_config + tool_results）
  - `CheckpointManager`: 磁盘持久化（data/checkpoints/*.json + LRU 缓存）
  - `SessionTree`:
    - `create_session()` → `fork()` → `restore()` 完整生命周期
    - `get_subtree()` / `get_branch_chain()` 树遍历
    - `save_checkpoint()` / `restore()` 快照恢复
    - 自动淘汰最旧根节点（max_nodes 限制）
  - 树持久化：`data/session_tree.json`
  - 全局单例：`init_session_tree()` / `get_session_tree()` / `get_checkpoint_manager()`

### API 端点新增

| 端点 | 方法 | 说明 |
|------|------|------|
| `/system/session-tree` | GET | 树总览（所有分支链） |
| `/system/session-tree/{id}` | GET | 节点详情（含子树+分支链+检查点） |
| `/system/session-tree/{id}/subtree` | GET | 完整子树 |
| `/system/session-tree/fork` | POST | Fork 新分支 |
| `/system/session-tree/branches/all` | GET | 所有分支列表 |
| `/system/session-tree/checkpoints` | POST | 保存检查点 |
| `/system/session-tree/checkpoints` | GET | 检查点列表 |
| `/system/session-tree/checkpoints/{id}` | GET | 检查点详情 |
| `/system/session-tree/checkpoints/{id}` | DELETE | 删除检查点 |
| `/system/session-tree/restore` | POST | 从检查点恢复 |
| `/system/cli-pipeline/run-file` | POST | 从 YAML 文件运行 |
| `/system/cli-pipeline/run-inline` | POST | 内联 dict 运行 |
| `/system/cli-pipeline/run-yaml` | POST | YAML 字符串运行 |
| `/system/cli-pipeline/samples` | GET | 示例模板 |

### 修改文件清单（全部零 lint 错误）

| 文件 | 变更 | 来源 |
|------|------|------|
| `backend/app/core/agent/pipeline.py` | **新增** ~190行 | cognee |
| `backend/app/core/tools/cli_pipeline.py` | **新增** ~380行 | AutoCLI |
| `backend/app/core/agent/session_tree.py` | **新增** ~360行 | hermes-agent |
| `backend/app/core/agent/__init__.py` | +12行 | 导出新增 |
| `backend/app/api/routes/system/session_tree.py` | **新增** ~135行 | hermes-agent |
| `backend/app/api/routes/system/cli_pipeline.py` | **新增** ~105行 | AutoCLI |
| `backend/app/api/routes/system/__init__.py` | +4行 | 路由导出 |
| `backend/app/api/main.py` | +4行 | 路由注册 |
| `backend/app/main.py` | +16行 | SessionTree 启动（注入 MemoryStore） |
| `.codebuddy/TASKS.md` | 更新 | Session 06 任务 14-16 + 持久化重构 |
| `.codebuddy/PROGRESS.md` | 更新 | 本文件 |

### 🔄 Session 06 持久化重构说明

**重构前**（裸 JSON 文件）:
```
data/session_tree.json     — 单文件树结构（不含消息）
data/checkpoints/*.json    — 每个检查点一个文件
```

**重构后**（MemoryStore SQLite 图数据库）:
```
data/memory.db             — 统一存储所有 session/checkpoint 节点 + 边
  SELECT * FROM memory_nodes WHERE memory_type = 'session'   → 所有会话
  SELECT * FROM memory_nodes WHERE memory_type = 'checkpoint' → 所有检查点
  SELECT * FROM memory_edges WHERE relation_type = 'CONVERSATION_FLOW' → 树结构
data/checkpoints/*.json    — 仅大型检查点负载（>100KB），绝大多数情况不使用
```

**优势**:
- 统一存储：session/checkpoint 与其他记忆（代码记忆、决策、教训）同库
- 图查询：免费获得 BFS 遍历、关键词搜索、关联查询
- 自动衰减：旧 session 随 MemoryStore 的 decay_score 自然淘汰
- 单点备份：只需备份 `data/memory.db` 一个文件
- MemoryEdge 关系的幂等性（INSERT OR REPLACE）"""
```

---

## Session 07 — 2026-06-30（晚上）Zed/CodeEdit 前端 IDE 深度借鉴

### 目标
基于 `05-Zed.md` 和 `06-CodeEdit.md` 参考文档，增强前端 IDE 体验。

### 完成内容

#### z1. Command Palette 全局命令面板（Zed command_palette）
- **重写**: `studio-client/src/components/ide/CommandPalette.vue`
  - 最近使用命令：空查询时显示最近 10 条，带标记
  - 首字母缩写匹配：`jfp` → "Just File Picker"（Zed 风格）
- **增强**: `useShortcuts.ts` — `getRecent()`/`recordRecent()`/`calculateFuzzyScore()`/`matchAbbreviation()`

#### z2. Streaming Diff 流式渲染（Zed streaming_diff.rs）
- **新建**: `studio-client/src/components/StreamingDiffViewer.vue` (~250行)
  - 打字机效果（可配置速度）+ 黄色闪烁光标
  - unified/split 双模式 + 播放/暂停工具栏

#### z3. Panel/Dock 布局持久化（Zed Dock 系统）
- **增强**: `useLayoutStore.ts` — localStorage 自动保存（500ms debounce）+ 启动恢复 + `resetLayout()`

#### z4. FileTree 右键菜单（CodeEdit Project Navigator）
- **增强**: `studio-client/src/components/ide/FileTree.vue`
  - 新增：复制路径 / @-引用到对话 / 打开

### 修改文件清单（全部零 lint 错误，7 文件）

| 文件 | 变更 | 来源 |
|------|------|------|
| `CommandPalette.vue` | **重写** | Zed |
| `useShortcuts.ts` | +60行 | Zed |
| `StreamingDiffViewer.vue` | **新建** ~250行 | Zed |
| `useLayoutStore.ts` | +40行 | Zed |
| `FileTree.vue` | +50行 | CodeEdit |
| `useIDEStore.ts` | +1行 | — |
| `App.vue` | +3行 | — |

---

## Session 08 — 2026-06-30（晚上）VSCode/Aider/Cline 前端 IDE 增强

### 目标
基于 `07-VSCode.md`、`02-Aider.md`、`09-Cline.md` 参考文档，增强前端 IDE 体验。

### 完成内容

#### VSCode 风格 StatusBar 增强
- **重写**: `studio-client/src/components/ide/StatusBar.vue`
  - 模型健康指示器（绿色/黄色/红色 dot + 后台定期 health check）
  - 工作区名称显示（从 `workspaceRoot` 尾部提取）
  - 通知计数 badge（红色圆形角标）
  - 活跃模型名称（从 localStorage 恢复）

#### VSCode 风格 BreadcrumbsBar
- **新建**: `studio-client/src/components/ide/BreadcrumbsBar.vue` (~110行)
  - 文件路径分段显示，每段可点击
  - 点击某段弹出同级文件/文件夹列表（dropdown）
  - 根目录图标 + 文件名颜色编码
  - 集成到 `TabBar.vue`（替换原有内联面包屑）
- **Bug 修复**: `TabBar.vue` — 移除 `_` 前缀命名不一致（6 个函数）、修复 `$el` Vue2 语法、添加 `Circle` 导入

#### Aider 风格批量编辑确认
- **新建**: `studio-client/src/components/agent/BatchEditPanel.vue` (~230行)
  - 多文件 AI 修改建议审查面板（底部滑入）
  - unified/split 双模式 Diff 展示
  - 逐文件 Accept/Reject + Accept All/Reject All
  - 文件状态 dot（待审核🟡/已批准🟢/已拒绝🔴）
  - 操作类型 badge（修改/新建/删除）

#### Cline 风格 Always Allow 记忆
- **增强**: `studio-client/src/components/agent/SecurityApprovalPanel.vue`
  - Always Allow 工具列表（localStorage 持久化）
  - 每个工具独立"始终允许"开关
  - 头部显示始终允许数量

### 修改文件清单（全部零 lint 错误，7 文件）

| 文件 | 变更 | 来源 |
|------|------|------|
| `StatusBar.vue` | **重写** | VSCode |
| `BreadcrumbsBar.vue` | **新建** ~110行 | VSCode |
| `TabBar.vue` | Bug 修复 + 集成 | VSCode |
| `BatchEditPanel.vue` | **新建** ~230行 | Aider |
| `SecurityApprovalPanel.vue` | +50行 | Cline |
| `.codebuddy/TASKS.md` | 更新 | — |
| `PROGRESS.md` | 更新 | 本文件 |

---

## Session 09 — 2026-06-30（晚上）Sandbox资源限制 / MCP市场 / AutoCLI安全打通

### 目标
强化沙箱安全层（进程资源限制+K8s），统一AutoCLI↔Sandbox执行路径，MCP Market持久化+动态评分。

### 完成内容

#### 9a. Sandbox 进程资源限制 + K8s 支持
- **修改文件**: `backend/app/core/sandbox/base.py`
  - `SandboxConfig` 新增 5 个资源限制字段：
    - `resource_memory_limit_mb: int = 512` — Unix ulimit -v 内存限制
    - `resource_cpu_limit_seconds: int = 60` — Unix ulimit -t CPU 时间限制
    - `resource_max_processes: int = 50` — Unix ulimit -u 进程数限制
    - `resource_max_file_size_mb: int = 500` — Unix ulimit -f 文件大小限制
  - K8s 专用字段：`k8s_namespace` / `k8s_image` / `k8s_cpu_limit` / `k8s_memory_limit`
- **修改文件**: `backend/app/core/sandbox/local.py`
  - 新增 `_wrap_resource_limits()` 方法，在命令执行前包裹 `ulimit -v/-t/-u/-f`
  - 平台检测：仅 Unix 生效，Windows 跳过（无 ulimit）
- **修改文件**: `backend/app/core/sandbox/k8s.py`
  - K8sSandbox 继承 `Sandbox` ABC
  - Pod 创建/销毁生命周期管理
  - 文件操作通过 `kubectl exec` 代理（cat/ls/rm/mkdir/find/grep）
- **修改文件**: `backend/app/core/sandbox/__init__.py`
  - `init_sandbox()` 新增 `k8s` 类型分支
  - 导入导出 K8sSandbox

#### 9b. AutoCLI ↔ Sandbox 统一安全层
- **修改文件**: `backend/app/core/tools/autocli.py`
  - `AutoCLI.execute()` 新增 `delegate_to_sandbox: bool = True` 参数
  - 新增 `_execute_via_sandbox()` 方法，将命令执行委托给 Sandbox 统一层
  - 新增 `_sandbox_paths()` — 调用 `sandbox.validate_path()` 进行路径验证
  - `init_autocli()` 接受可选 `sandbox: Sandbox` 注入
- **架构升级**: 命令执行路径从 `subprocess.run()` 直调改为 Sandbox 代理
  ```
  Agent工具 → AutoCLI.security_check() → Sandbox.execute()
              ├─ ulimit 资源限制
              ├─ 路径白名单验证
              └─ 命令注入检测
  ```

#### 9c. MCP Marketplace 数据库持久化 + 动态评分
- **修改文件**: `backend/app/api/routes/agent/mcp_marketplace.py`
  - 动态评分系统 `_dynamic_score()`：基础星数 + 安装数 + 近30天安装数综合计算
  - 评分公式：`log₂(1+installs)×0.6 + log₂(1+recent)×0.3 + log₂(1+stars)×0.1`，上限 5.0
  - `_recalc_dynamic_stats()` — 从 `McpInstalledServer` 表实时计算
  - `_seed_marketplace()` — 幂等初始化种子数据（SQLModel 持久化）
  - 新增 API 端点：
    - `GET /stats` — 市场统计（安装排行+分类统计）
    - `POST /seed` — 种子数据初始化
    - `GET /installed` — 安装追踪记录

### 修改文件清单（全部零 lint 错误）

| 文件 | 变更 | 说明 |
|------|------|------|
| `backend/app/core/sandbox/base.py` | +10字段 | 资源限制 + K8s 配置 |
| `backend/app/core/sandbox/local.py` | +30行 | ulimit 资源包裹 |
| `backend/app/core/sandbox/k8s.py` | 重写 | Pod 隔离 + kubectl 代理 |
| `backend/app/core/sandbox/__init__.py` | +10行 | k8s 分支 + 导出 |
| `backend/app/core/tools/autocli.py` | +40行 | Sandbox 委托执行 |
| `backend/app/api/routes/agent/mcp_marketplace.py` | +80行 | 动态评分 + 种子+统计 API |

---

## Session 10 — 2026-06-30（晚上）前端IDE核心体验增强

### 目标
RooCode/Warp/VSCode 风格前端重构：多标签会话、ANSI终端、三主题、设置面板。

### 完成内容

#### 10a. 三主题系统（useThemeStore）
- **新建文件**: `studio-client/src/stores/useThemeStore.ts` (~80行)
  - 三套内置主题：**dark**（One Dark）、**light**（VSCode Light+）、**high-contrast**（黑底绿字）
  - 持久化到 `localStorage("codebuddy_theme")`
  - 操作：`setTheme()` / `cycleTheme()` / `isDark()`
  - 返回 `definition` 对象：`htmlClass`（设置 `<html>` class）+ `monacoTheme`（Monaco 编辑器主题名）
- **大幅增强**: `studio-client/src/index.css` (+~200行)
  - `html.theme-light` 覆盖块：80+ CSS 变量，蓝调 accent，VSCode 亮色风格
  - `html.theme-high-contrast` 覆盖块：90+ CSS 变量，黑底绿字高对比度
  - 完整的 `@theme` 块定义 IDE 核心色彩体系

#### 10b. Agent 多标签会话（RooCode 风格）
- **新建文件**: `studio-client/src/stores/useAgentTabsStore.ts` (~180行)
  - `createTab()` / `removeTab()` / `switchToTab()` / `renameTab()` / `togglePin()`
  - `saveMessages()` / `loadMessages()` — 消息序列化（上限50条/标签）
  - 最大 15 标签，超限自动移除最旧非固定标签
  - 自动从首条用户消息提取标题
  - 持久化到 `localStorage("agent_tabs_v1")`
- **新建文件**: `studio-client/src/components/agent/AgentTabBar.vue` (~120行)
  - 固定标签优先排列（Pin 图标）
  - hover 显示 Pin/Close 操作
  - 活跃标签蓝底高亮 + 左边框
  - 标题超 18 字符截断省略号
  - 新标签按钮（`+` 图标 + Ctrl+T 提示）
- **集成**: `studio-client/src/pages/AgentChat.vue`
  - `newChat()` 改用 `tabStore.createTab()`
  - `saveCurrentSession()` 同步到 `tabStore.saveMessages()` / `renameTab()` / `updateTabMode()`
  - `switchToSession()` 从 `tabStore.loadMessages()` 恢复消息
  - `@tab-switch` 同步 `sessionId` + `chatMode`

#### 10c. ANSI 终端颜色渲染
- **新建文件**: `studio-client/src/utils/ansi.ts` (~120行)
  - 完整 ANSI SGR 解析器（正则状态机）
  - 3/4-bit 颜色（16色 xterm）、256 色（6×6×6立方体）、True Color（`38;2;r;g;b`）
  - 样式解析：bold / dim / italic / underline / reset
  - 导出：`parseAnsi()` / `hasAnsi()` / `stripAnsi()` / `segmentStyle()`
- **类型扩展**: `studio-client/src/types/ide.ts`
  - `TerminalLine` 新增 `segments?: TerminalSegment[]`
  - 新增 `TerminalSegment` 接口（text/fg/bg/bold/dim/italic/underline）
- **集成**:
  - `useTerminalStore.ts`: `addTerminalLine()` 自动检测 ANSI 并预解析 segments
  - `Terminal.vue`: 输出改为 segment 级渲染，按 fg/bg/bold 逐段着色

#### 10d. 设置面板（SettingsPanel）
- **新建文件**: `studio-client/src/components/ide/SettingsPanel.vue` (~180行)
  - Teleported 全屏模态（5个标签页）
  - **通用**：主题切换（下拉+themeStore联动）、缩放级别、字体家族、字号、自动保存
  - **编辑器**：制表符宽度、自动换行、行号、小地图、光标样式
  - **终端**：默认 Shell、字号、光标闪烁、滚动缓冲区
  - **AI 助手**：提供商、模型、API Key、Temperature
  - **扩展**：已装插件列表 + ToggleSwitch 开关
- **新建文件**: `studio-client/src/components/ide/ui/Toggle.vue`
  - 通用 ToggleSwitch 组件，双向绑定 v-model

#### 10e. 代码编辑器主题同步
- **修改文件**: `studio-client/src/components/ide/CodeEditor.vue`
  - 集成 `useThemeStore`：监听 `themeStore.definition.monacoTheme` 变化
  - 调用 `monaco.editor.setTheme()` 实时切换
  - 初始化时使用 `themeStore.definition.monacoTheme`
  - 启用 `bracketPairColorization` / `stickyScroll`

#### 10f. StatusBar 主题快速切换
- **修改文件**: `studio-client/src/components/ide/StatusBar.vue`
  - 新增主题切换按钮，调用 `themeStore.cycleTheme()`
  - 亮色→Sun 图标（黄色）/ 暗色→Moon 图标（靛蓝色）/ 高对比度→"HC"文字（绿色）

### 修改文件清单（全部零 lint 错误）

| 文件 | 类型 | 说明 |
|------|------|------|
| `studio-client/src/stores/useThemeStore.ts` | **新建** ~80行 | 三主题系统 |
| `studio-client/src/stores/useAgentTabsStore.ts` | **新建** ~180行 | 多标签会话管理 |
| `studio-client/src/utils/ansi.ts` | **新建** ~120行 | ANSI 颜色解析器 |
| `studio-client/src/components/agent/AgentTabBar.vue` | **新建** ~120行 | 标签栏 UI |
| `studio-client/src/components/ide/SettingsPanel.vue` | **新建** ~180行 | 5标签设置面板 |
| `studio-client/src/components/ide/ui/Toggle.vue` | **新建** ~30行 | ToggleSwitch 组件 |
| `studio-client/src/index.css` | +~200行 | light/high-contrast 主题 |
| `studio-client/src/types/ide.ts` | +10行 | TerminalSegment 接口 |
| `studio-client/src/stores/useTerminalStore.ts` | +15行 | ANSI 预解析 |
| `studio-client/src/components/ide/Terminal.vue` | 修改 | Segment 级渲染 |
| `studio-client/src/components/ide/CodeEditor.vue` | +15行 | 主题同步 |
| `studio-client/src/components/ide/StatusBar.vue` | +10行 | 主题切换按钮 |
| `studio-client/src/pages/AgentChat.vue` | +30行 | 标签系统集成 |

---

## 附录：关键技术架构图

```
用户选模型 → AgentChat.vue(preferred_model)
                ↓
         POST /agent/chat/simple
                ↓
      ModelRouter.generate(request)
                ↓
    ┌─────────────────────────────┐
    │ _try_specific_model(name)   │
    │                             │
    │ ① api_models (ApiModelAdapter) ← Ollama/OpenAI 单模型
    │    ↓ 未找到                  │
    │ ② local_models (LocalModelAdapter) ← Safetensors/GGUF
    │    ↓ 未找到                  │
    │ ③ api_gateway.get_candidates() ← Provider 默认候选
    └─────────────────────────────┘
                ↓ 成功
          ModelResponse(content)
                ↓ 失败
    FallbackChain 五层回退
```

## 附录：环境配置速查

| 项目 | 值 | 备注 |
|------|-----|------|
| 后端端口 | 8000（dev）/ 18000（Docker/Standalone） | vite proxy 已改 8000 |
| Ollama 地址 | localhost:11434 | 需确保服务运行 |
| Python 版本 | 3.12 | `.python-version` |
| 包管理器 | uv (Python) / pnpm (前端) | |
| 数据库 | PostgreSQL 18 (Docker) | docker compose up -d db |

---

## 附录：前后端启动方式详解（Session 01 变更记录）

> 本次 Session 对启动配置做了多处调整，以下是完整对照。

### 后端启动（4 种方式）

| 方式 | 命令/操作 | 端口 | 说明 | 变更状态 |
|------|-----------|------|------|----------|
| **① Windows 一键脚本** | 双击 `start-backend.bat` | **8000** | 自动杀占用端口 + 启动 uvicorn | 🆕 **新增** |
| **② 开发模式（热重载）** | `cd backend && uv run fastapi dev app/main.py --port 8000` | 8000 | 修改代码即时生效，推荐日常开发 | ⚠️ 端口从 18000 改为 8000 |
| **③ Standalone 独立模式** | `python standalone.py` 或双击 `start-standalone.bat` | **18000** | 含守护进程+智能休眠+API鉴权，无需 Docker | 无变化 |
| **④ Docker Compose** | `docker compose up -d backend` | 8000 (容器内) / Traefik 路由 | 生产部署，含 Traefik 反向代理 + HTTPS | 无变化 |

### 前端启动

```bash
# 安装依赖（首次）
pnpm install

# Studio Client（C 端 AI 编辑器）— 主力开发前端
cd studio-client && pnpm dev        # → http://localhost:5173

# 其他前端（按需）
pnpm dev:studio-admin              # → http://localhost:5175（管理端）
pnpm dev:video-client              # → http://localhost:5174（视频 C 端）
pnpm dev:video-admin               # → http://localhost:5176（视频管理端）
```

#### 前端启动变更

| 项目 | 旧值 | 新值 | 影响 |
|------|------|------|------|
| Vite proxy target | （未确认，可能是 18000） | `http://localhost:8000` | 匹配 start-backend.bat 的 8000 端口 |
| Vite server port | 5173 | 5173（不变） | — |
| ChatPanel API | mock 数据 | `agentChatSimple()` 真实 API | 需后端先启动 |

### 推荐本地开发组合

```
终端 1: 双击 start-backend.bat          # 后端 :8000
终端 2: cd studio-client && pnpm dev     # 前端 :5173 → proxy → :8000
可选:    ollama serve                     # Ollama :11434（模型服务）
可选:    docker compose up -d db redis    # PostgreSQL + Redis（基础设施）
```

### 端口占用一览

| 端口 | 服务 | 必需 |
|------|------|:----:|
| 5173 | Studio Client (Vite) | ✅ 前端开发 |
| 5174 | Video Client (Vite) | 可选 |
| 5175 | Studio Admin (Vite) | 可选 |
| 5176 | Video Admin (Vite) | 可选 |
| **8000** | **Backend (uvicorn)** | ✅ **必需** |
| 11434 | Ollama | ✅ 模型服务 |
| 5432 | PostgreSQL (Docker) | ✅ 数据库 |
| 6379 | Redis (Docker) | 可选（缓存/限流/Celery） |
| 6333 | Qdrant (Docker) | 可选（向量数据库） |
| 18000 | Standalone 模式 | 备用（独立部署） |
| 18080 | Adminer (Docker) | 可选（数据库管理） |

### 已知启动注意事项

1. **端口冲突**：如果 8000 被占用，`start-backend.bat` 会自动 kill 占用进程再启动。手动模式需自行处理。
2. **Ollama 依赖**：12 个 Ollama 本地模型需要 Ollama 服务在 `localhost:11434` 运行，否则模型调用会失败并回退到远程 API。
3. **`.env` 路径**：`config.py` 已改用绝对路径 + `load_dotenv()`，从任何目录启动都能正确加载项目根目录的 `.env`。
4. **Standalone vs Dev 区别**：
   - Dev 模式（端口 8000）：轻量快速，热重载，适合开发调试
   - Standalone（端口 18000）：重量级，含进程守护/智能休眠/API鉴权/Web管理界面，适合长期运行
5. **Docker vs 本地**：同一个 `.env` 文件兼容两种模式，Docker 会覆盖 `POSTGRES_SERVER=db`、`REDIS_HOST=redis` 等变量。
