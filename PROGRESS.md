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

## Session 02 — 待续...

> （下次开发时在此处追加）

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
