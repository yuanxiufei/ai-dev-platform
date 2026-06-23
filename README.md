# 🚀 AI Fullstack Platform

基于 FastAPI + Vue 3 / React 19 的全栈 AI 开发平台，集成代码生成（截图→代码 / 自然语言→全栈项目）、视频生成（文字→视频）、
智能模型调度（本地优先 + 五层回退链）、异步任务处理、系统管理和远程控制能力。

## 系统架构

```
  ┌──────────────────────────────────────────────────────┐
  │                    pnpm Monorepo                     │
  │                                                      │
  │  ┌──────────────┐  ┌──────────────┐                 │
  │  │  video-client │  │  video-admin │                 │
  │  │   (Vue 3)    │  │  (React 19)  │                 │
  │  │   端口 5174   │  │   端口 5176   │                 │
  │  └──────┬───────┘  └──────┬───────┘                 │
  │  ┌──────┴───────┐  ┌──────┴───────┐                 │
  │  │ studio-client│  │ studio-admin │                 │
  │  │   (Vue 3)    │  │   (Vue 3)    │                 │
  │  │   端口 5173   │  │   端口 5175   │                 │
  │  └──────┬───────┘  └──────┬───────┘                 │
  └─────────┼──────────────────┼─────────────────────────┘
            └────────┬─────────┘
                     ↓  :18000
       ┌─────────────────────────────────────┐
       │        FastAPI API 网关              │
       │  ┌───────────┬──────────┬─────────┐ │
       │  │  Studio   │  Video   │ System  │ │
       │  │ (代码/AI) │ (视频)   │ (运维)  │ │
       │  └───────────┴──────────┴─────────┘ │
       └──────────────┬──────────────────────┘
                      ↓
       ┌─────────────────────────────────────┐
       │         ModelRouter（模型路由）      │
       │  能力导向 → 五层回退 → 统一接口      │
       │  ┌─────────────────────────────────┐ │
       │  │ 1. 用户指定  → 2. 本地最优      │ │
       │  │ 3. 本地降级  → 4. 第三方API     │ │
       │  │ 5. 内置基础（永不中断）          │ │
       │  └─────────────────────────────────┘ │
       └──────────────┬──────────────────────┘
                      ↓
       ┌──────────────────┐
       │   Redis / Celery │
       └────────┬─────────┘
 ┌──────────────┴────────────────┐
 ↓                               ↓
代码生成 Worker                视频生成 Worker
(Qwen2.5-Coder/Gemma)         (CogVideoX/Replicate)
```

## 技术栈

### 后端
- ⚡ **FastAPI** — 高性能 Python API 框架
- 🧰 **SQLModel** — ORM + 数据校验
- 🔍 **Pydantic** — 配置管理与请求校验
- 💾 **PostgreSQL 18** — 关系型数据库
- 🔑 **JWT** — 用户认证与鉴权
- 📫 **邮件** — 密码重置等邮件功能

### 前端（pnpm Monorepo）
- 🌐 **4 个前端项目** — C 端 + 管理端 × 视频/代码两条业务线
- ⚡ **Vite 5 / 6 / 7** — 各项目独立版本
- 🎨 **Tailwind CSS 4** — 原子化样式
- 🖥️ **Vue 3** + **TypeScript** — video-client / studio-client / studio-admin
- ⚛️ **React 19** + **TypeScript** — video-admin
- 🧩 **Radix UI** / **shadcn/ui** 风格组件 — video-admin
- 🌗 **深色模式** 支持（各项目独立实现）
- 🧪 **Playwright** — E2E 测试（video-admin）

### 任务队列
- 🔴 **Redis 7** — 消息代理
- 📦 **Celery** — 分布式任务队列

### AI Worker
- 💻 **代码生成** — Qwen2.5-Coder / Gemma 31B（截图→代码、文本→API）
- 🎥 **视频生成** — CogVideoX / Stable Video Diffusion（UI 演示、短视频）
- 👁️ **视觉理解** — Qwen2.5-VL 7B（截图分析、布局识别）

### 模型调度层
- 🧠 **ModelRouter** — 统一模型调度入口，按能力分类
- 📊 **ModelScheduler** — 动态评分调度（base_priority × availability × performance）
- 🔗 **FallbackChain** — 五层回退链（本地→API→内置，永不中断）
- 🌐 **ApiGateway** — 多Provider适配器（OpenAI/Claude/DeepSeek/Replicate/智谱/通义千问）
- 📥 **ModelDownloader** — HuggingFace/ModelScope 双源下载

### 基础设施
- 🐋 **Docker Compose** — 一键部署
- 🔄 **Traefik** — 反向代理 + 自动 HTTPS
- 🔁 **GitHub Actions** — CI/CD 流水线

---

## 快速开始

### 前置条件

| 工具 | 用途 |
|------|------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 数据库 / Redis / 容器化 |
| [pnpm](https://pnpm.io/) | 前端包管理 |
| [uv](https://docs.astral.sh/uv/) | Python 包管理 |

### 方式一：Docker Compose（一键启动）

```bash
docker compose watch
```

启动后访问：

| 服务 | 地址 |
|------|------|
| Studio Client（C 端） | http://localhost:5173 |
| Video Client（C 端） | http://localhost:5174 |
| Studio Admin（管理端） | http://localhost:5175 |
| Video Admin（管理端） | http://localhost:5176 |
| API 文档 | http://localhost:18000/docs |
| 数据库管理 | http://localhost:18080 |
| Traefik 面板 | http://localhost:8090 |

### 方式二：本地开发（推荐）

Docker 只跑基础设施，前后端在本地跑，代码修改即时生效。

```bash
# 1. 启动基础设施
docker compose up -d db redis mailcatcher

# 2. 初始化数据库（仅首次）
# Git Bash / WSL:
cd backend && bash scripts/prestart.sh

# Windows PowerShell:
cd backend
uv run python app/backend_pre_start.py
uv run alembic upgrade head
uv run python app/initial_data.py

# 3. 启动后端（终端 1）— 端口 18000
uv run fastapi dev app/main.py --port 18000

# 4. 安装前端依赖（首次）
pnpm install

# 5. 启动前端（按需选择）
# 终端 2：Studio Client（C 端 AI 编辑器）
pnpm dev:studio-client

# 终端 3：Video Client（C 端视频生成）
pnpm dev:video-client

# 终端 4：Studio Admin（管理端）
pnpm dev:studio-admin

# 终端 5：Video Admin（管理端）
pnpm dev:video-admin
```

### 方式三：Standalone 独立部署（Windows）

不依赖 Docker，一键启动所有服务：

```powershell
# 初始化（仅首次）
python standalone.py --init

# 启动服务
start-standalone.bat
```

访问：http://localhost:18000 （API + Web 管理界面）

> Standalone 模式内置进程守护、健康监控、DDNS 远程唤醒等功能。详见 [standalone-tools/README.md](./standalone-tools/README.md)

### 默认账户

| 字段 | 值 |
|------|-----|
| 邮箱 | `admin@example.com` |
| 密码 | `changethis` |

> ⚠️ 生产环境请修改 `.env` 中的 `SECRET_KEY`、`POSTGRES_PASSWORD`、`FIRST_SUPERUSER_PASSWORD`。

---

## 项目结构

```
ai-fullstack-platform/
├── backend/                        # FastAPI 后端
│   ├── app/
│   │   ├── api/
│   │   │   ├── main.py             # 路由注册入口
│   │   │   └── routes/
│   │   │       ├── studio/         # Studio 业务 API
│   │   │       │   ├── admin/      #   管理端（项目/模板 CRUD + 生成）
│   │   │       │   └── client/     #   C端（对话/会话/模型）
│   │   │       ├── video/          # Video 业务 API
│   │   │       │   ├── admin/      #   管理端（视频CRUD/分析/审核）
│   │   │       │   └── client/     #   C端（浏览/搜索/生成/播放）
│   │   │       └── system/         # 系统运维 API
│   │   │           ├── health.py   #   健康检查（基本/详细/统计）
│   │   │           ├── models.py   #   模型管理（列表/下载/加载/卸载）
│   │   │           ├── gpu.py      #   GPU 状态监控
│   │   │           ├── resources.py #  系统资源监控
│   │   │           ├── config.py   #   配置热加载
│   │   │           ├── benchmarks.py # 性能基准测试
│   │   │           ├── terminal.py #   WebSocket 终端
│   │   │           ├── remote.py   #   远程代理/端口转发
│   │   │           ├── storage.py  #   存储管理
│   │   │           ├── checkpoints.py # 代码快照
│   │   │           ├── guardrails.py  # 安全护栏
│   │   │           └── task_queue.py  # 任务队列监控
│   │   ├── core/                   # 核心基础设施
│   │   │   ├── model_router.py     #   ModelRouter 调度入口
│   │   │   ├── api_gateway.py      #   ApiGateway 多Provider适配
│   │   │   ├── fallback_chain.py   #   FallbackChain 五层回退
│   │   │   ├── model_downloader.py #   模型下载管理器
│   │   │   ├── config.py           #   全局配置
│   │   │   ├── db.py               #   数据库连接
│   │   │   ├── metrics.py          #   指标收集
│   │   │   ├── security/           #   认证与鉴权
│   │   │   ├── standalone/         #   独立部署管理
│   │   │   ├── terminal/           #   终端管理
│   │   │   ├── mcp/                #   MCP 协议支持
│   │   │   └── remote/             #   远程代理控制
│   │   └── models/                 # 数据模型（SQLModel）
│   │       ├── studio_models.py    #   StudioProject/ChatSession
│   │       ├── video_models.py     #   VideoTask/VideoAsset
│   │       └── system_models.py    #   ModelDownload/UsageStat
│   ├── scripts/prestart.sh         # 数据库迁移脚本
│   └── pyproject.toml
│
├── ai_models/                       # AI 模型层（按能力分类）
│   ├── registry.py                  #   注册中心（本地+远程）
│   ├── scheduler.py                 #   动态评分调度器（DynamicScore）
│   ├── api_proxy.py                 #   第三方API统一代理
│   ├── optimizer.py                 #   自动优化引擎
│   ├── downloader.py                #   模型下载器
│   └── base.py                      #   BaseModel + ModelConfig
│
├── models/                          # 🔥 模型权重文件存放目录
│   ├── Qwen2.5-VL-7B-Instruct/      # safetensors → 视觉理解
│   ├── Qwen2.5-Coder-7B-Instruct/   # safetensors → 代码生成
│   ├── CogVideoX-5b/               # safetensors → 视频生成
│   └── gemma-4-31B-it-qat-GGUF/    # GGUF → 代码生成（大参数量）
│
├── task_queue/                      # 任务队列
│   ├── celery_app.py                #   Celery 配置
│   └── redis_config.py              #   Redis 连接
│
├── workers/                         # Celery 异步 Worker
│   ├── code_worker.py               #   代码生成任务
│   └── video_worker.py              #   视频生成任务
│
├── standalone-tools/                # 独立部署工具
│   ├── ddns.py                      #   阿里云 DDNS 动态域名
│   ├── wol.py                       #   远程唤醒 WOL
│   ├── start-*.bat                  #   Windows 快速启动脚本
│   └── README.md                    #   WOL / DDNS 教程
│
├── video-client/                    # Vue 3 C 端 — 视频生成
├── video-admin/                     # React 19 管理端 — 视频管理
├── studio-client/                   # Vue 3 C 端 — AI 编辑器（含 Tauri）
├── studio-admin/                    # Vue 3 管理端 — 项目管理 & 模板
│
├── compose.yml                      # Docker Compose 编排
├── compose.override.yml             # 本地开发覆盖配置
├── compose.traefik.yml              # Traefik 反向代理
├── .env                             # 环境变量
├── .env.standalone                  # Standalone 模式配置
├── standalone.py                    # Standalone 入口
├── start-standalone.bat             # Windows 一键启动
├── pnpm-workspace.yaml              # pnpm monorepo 配置
├── pyproject.toml                   # Python 工作区配置
└── package.json                     # 前端工作区根配置
```

---

## 核心 API

> 所有 API 挂载在 `/api/v1/` 下，共 **108 个端点**，分组为 Studio / Video / System 三大模块。

### 认证与用户

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/login/access-token` | 用户登录，返回 JWT |
| `POST` | `/api/v1/users/signup` | 用户注册 |
| `GET` | `/api/v1/users/me` | 获取当前用户信息 |
| `PATCH` | `/api/v1/users/me` | 更新当前用户 |
| `POST` | `/api/v1/password-recovery/{email}` | 密码找回 |

### Studio — AI 编程工具

**项目管理（管理端 + C 端）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/studio/projects` | 项目列表（分页 + 筛选） |
| `POST` | `/studio/projects` | 创建项目 |
| `GET` | `/studio/projects/{id}` | 项目详情 |
| `PUT` | `/studio/projects/{id}` | 更新项目 |
| `DELETE` | `/studio/projects/{id}` | 删除项目 |
| `POST` | `/studio/projects/generate` | AI 生成全栈项目（同步） |
| `POST` | `/studio/projects/generate/async` | AI 生成全栈项目（Celery 异步） |
| `GET` | `/studio/projects/generate/async/{task_id}` | 查询异步任务状态 |
| `POST` | `/studio/projects/{id}/build` | 构建项目 |
| `POST` | `/studio/projects/{id}/deploy` | 部署项目 |
| `POST` | `/studio/projects/screenshot` | 截图→代码 |

**模板市场（管理端 + C 端）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/studio/templates` | 模板列表 |
| `POST` | `/studio/templates` | 创建模板 |
| `GET` | `/studio/templates/{id}` | 模板详情 |
| `PUT` | `/studio/templates/{id}` | 更新模板 |
| `DELETE` | `/studio/templates/{id}` | 删除模板 |
| `POST` | `/studio/templates/{id}/use` | 基于模板创建项目 |

**AI 对话（C 端）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/studio/chat` | 发送消息（非流式） |
| `POST` | `/studio/chat/stream` | SSE 流式对话 |
| `GET` | `/studio/chat/{session_id}/messages` | 对话历史 |

**会话管理（C 端）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/studio/sessions` | 会话列表 |
| `POST` | `/studio/sessions` | 创建新会话 |
| `GET` | `/studio/sessions/{id}` | 会话详情 |
| `PUT` | `/studio/sessions/{id}` | 重命名会话 |
| `DELETE` | `/studio/sessions/{id}` | 删除会话（级联消息） |

**模型管理（C 端）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/studio/models` | 可用模型列表 |
| `GET` | `/studio/models/providers` | API 提供商列表 |
| `POST` | `/studio/models/download` | 触发模型下载 |
| `GET` | `/studio/models/download/{task_id}` | 下载进度查询 |
| `GET` | `/studio/models/usage-stats` | 模型使用统计 |
| `POST` | `/studio/models/optimize` | 触发自动优化 |

### Video — 视频生成工具

**视频 CRUD（管理端）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/videos` | 视频列表（管理端所有） |
| `POST` | `/videos` | 创建视频记录 |
| `GET` | `/videos/{id}` | 视频详情 |
| `PUT` | `/videos/{id}` | 更新视频 |
| `DELETE` | `/videos/{id}` | 删除视频 |

**数据分析（管理端）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/videos/analytics/overview` | 整体数据概览 |
| `GET` | `/videos/analytics/{id}` | 单个视频分析 |
| `GET` | `/videos/analytics/trends/daily` | 每日趋势 |

**内容审核（管理端）**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/videos/moderation/queue` | 待审核队列 |
| `POST` | `/videos/moderation/{id}/approve` | 批准视频 |
| `POST` | `/videos/moderation/{id}/reject` | 驳回视频 |

**C 端**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/videos/browse` | 浏览公开视频（分页 + 标签） |
| `GET` | `/videos/search` | 搜索视频 |
| `POST` | `/videos/generate` | 发起视频生成任务 |
| `GET` | `/videos/generate/{task_id}` | 查询任务状态 |
| `WS` | `/videos/generate/{task_id}/ws` | WebSocket 实时进度 |
| `GET` | `/videos/{id}/play` | 视频播放（+ 观看计数） |
| `GET` | `/videos/{id}/subtitles` | 视频字幕 |

### System — 系统运维

**健康检查**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/system/health` | 基本健康检查 |
| `GET` | `/system/health/detailed` | 详细检查（DB + 模型 + 网关 + 路由） |
| `GET` | `/system/health/stats` | 系统统计（数据计数 + 存储） |

**全局模型管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/system/models` | 所有模型列表（本地 + 远程） |
| `GET` | `/system/models/{name}` | 模型详情 |
| `POST` | `/system/models/download` | 下载模型（异步） |
| `GET` | `/system/models/download/{task_id}` | 下载进度 |
| `DELETE` | `/system/models/{name}` | 删除本地模型 |
| `POST` | `/system/models/{name}/load` | 加载模型到内存 |
| `POST` | `/system/models/{name}/unload` | 卸载模型释放资源 |
| `GET` | `/system/models/loaded` | 当前已加载模型列表 |
| `GET` | `/system/models/providers` | API 提供商列表 |
| `POST` | `/system/models/providers` | 配置 API 密钥 |
| `GET` | `/system/models/usage-stats` | 使用统计 |
| `POST` | `/system/models/optimize` | 触发自动优化 |

**GPU 与资源监控**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/system/gpu/devices` | GPU 设备列表 |
| `GET` | `/system/gpu/status` | GPU 总体状态 |
| `GET` | `/system/resources/current` | 当前资源快照（CPU/内存/磁盘/GPU） |
| `GET` | `/system/resources/hardware` | 硬件详情 |
| `GET` | `/system/resources/history` | 资源快照历史 |

**模型目录 (Catalog)**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/system/catalog/models` | 模型目录（分页） |
| `GET` | `/system/catalog/models/{id}` | 模型集详情 |
| `GET` | `/system/catalog/drafts` | 草稿/即将上线模型 |
| `GET` | `/system/catalog/categories` | 模型分类 |
| `GET` | `/system/catalog/info` | 目录元数据 |

**基准测试 (Benchmarks)**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/system/benchmarks` | 基准测试列表 |
| `POST` | `/system/benchmarks` | 创建测试任务 |
| `GET` | `/system/benchmarks/{id}` | 任务详情 |
| `POST` | `/system/benchmarks/{id}/submit` | 提交执行 |
| `POST` | `/system/benchmarks/{id}/stop` | 停止测试 |
| `WS` | `/system/benchmarks/{id}/ws` | WebSocket 实时日志 |

**终端 (WebSocket)**

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/system/terminal/sessions` | 创建终端会话 |
| `GET` | `/system/terminal/sessions` | 活跃终端列表 |
| `DELETE` | `/system/terminal/sessions/{id}` | 关闭终端 |
| `WS` | `/system/terminal/sessions/{id}/ws` | WebSocket 终端通道 |

**存储管理**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/system/storage/stats` | 各类存储统计 |
| `GET` | `/system/storage/config` | 存储配置 |
| `POST` | `/system/storage/config` | 更新存储配置 |
| `POST` | `/system/storage/migrate` | 迁移存储目录 |
| `POST` | `/system/storage/cleanup` | 清理临时文件 |
| `GET` | `/system/storage/quota` | 存储配额检查 |

**任务队列**

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/tasks/queue/stats` | 队列统计概览 |
| `GET` | `/tasks/queue/active` | 活跃任务列表 |
| `GET` | `/tasks/queue/{task_id}` | 任务状态 |
| `POST` | `/tasks/queue/{task_id}/revoke` | 撤销任务 |

**远程代理与配置**

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/system/remote/sessions` | 创建远程代理连接 |
| `GET` | `/system/remote/sessions` | 活跃远程会话列表 |
| `DELETE` | `/system/remote/sessions/{id}` | 结束远程会话 |
| `GET` | `/system/config` | 当前配置 |
| `POST` | `/system/config/reload` | 热加载配置 |
| `GET` | `/system/guardrails/config` | 安全护栏配置 |
| `POST` | `/system/guardrails/check` | 检查调用安全性 |
| `POST` | `/system/checkpoints` | 创建代码快照 |
| `POST` | `/system/checkpoints/{id}/restore` | 回滚到快照 |

> 完整 API 见 Swagger 文档：http://localhost:18000/docs

---

## 模型调度

### 五层回退链

```
Layer 1: 用户指定模型（preferred_model）
    ↓ 不可用
Layer 2: 本地最优模型（DynamicScore 排行前3）
    ↓ 不可用
Layer 3: 本地次优模型（降级尝试）
    ↓ 不可用
Layer 4: 第三方 API（OpenAI → Claude → DeepSeek → Replicate → 智谱 → 通义千问）
    ↓ 不可用
Layer 5: 内置基础模型（永远可用，确保系统不中断）
```

### DynamicScore 评分

```
DynamicScore = base_priority × availability_factor × performance_factor
- availability_factor: 0=不可用, 0.5=降级, 1.0=完全可用
- performance_factor: 成功率(60%) × 速度因子(40%)
```

### 支持的第三方 API 提供商

| 提供商 | 模型 | 能力 | 优先级 |
|--------|------|------|--------|
| OpenAI | GPT-4o, o1, o3, GPT-4-turbo | 代码生成/视觉 | 35-38 |
| Anthropic | Claude Sonnet 4, Claude 3 Opus | 代码生成 | 36 |
| DeepSeek | DeepSeek-V3, DeepSeek-Coder | 代码生成 | 34 |
| Azure | Azure OpenAI Service | 代码生成 | — |
| Replicate | CogVideoX, Stable Video Diffusion | 视频生成 | 30 |
| 智谱 (Zhipu) | GLM-4 Plus, GLM-4V | 代码生成/视觉 | 32 |
| 通义千问 (Qwen) | Qwen-Max, Qwen-Plus | 代码生成 | — |

## 配置说明

### 基础环境变量（`.env`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PROJECT_NAME` | 项目名称 | `AI Fullstack Platform` |
| `SECRET_KEY` | JWT 签名密钥 | `changethis` |
| `POSTGRES_SERVER` | 数据库地址 | `localhost` |
| `POSTGRES_DB` | 数据库名 | `app` |
| `REDIS_HOST` | Redis 地址 | `localhost` |
| `REDIS_URL` | Redis 连接串 | `redis://localhost:6379/0` |
| `FIRST_SUPERUSER` | 初始管理员邮箱 | `admin@example.com` |
| `FIRST_SUPERUSER_PASSWORD` | 初始管理员密码 | `changethis` |

### AI 模型配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | — |
| `ANTHROPIC_API_KEY` | Claude API 密钥 | — |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | — |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI 密钥 | — |
| `REPLICATE_API_KEY` | Replicate API 密钥 | — |
| `ZHIPU_API_KEY` | 智谱 API 密钥 | — |
| `QWEN_API_KEY` | 通义千问 API 密钥 | — |

### 模型与存储配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MODELS_DIR` | 模型权重存放目录 | `models/` |
| `MODEL_PREFER_LOCAL` | 优先使用本地模型 | `true` |
| `MODEL_REQUEST_TIMEOUT` | 模型请求超时（秒） | `30` |
| `MODEL_MAX_RETRIES` | 最大重试次数 | `2` |
| `MODEL_FALLBACK_ENABLED` | 启用回退链 | `true` |
| `AUTO_OPTIMIZE_ENABLED` | 启用自动优化 | `true` |
| `AUTO_OPTIMIZE_INTERVAL_HOURS` | 自动优化间隔（小时） | `24` |

### Standalone 独立部署配置（`.env.standalone`）

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `STANDALONE_BIND_PORT` | 绑定端口 | `18000` |
| `STANDALONE_AUTO_START` | 自动启动服务 | `true` |
| `STANDALONE_WEB_UI` | 启用 Web 管理界面 | `true` |

Docker Compose 在容器内会自动覆盖 `POSTGRES_SERVER=db`、`REDIS_HOST=redis`，所以同一个 `.env` 可同时兼容本地和 Docker 两种启动方式。生产环境请修改所有 `changethis` 值。

---

## 生成密钥

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

用输出替换 `.env` 中的所有 `changethis`。

---

## 更多文档

| 文档 | 说明 |
|------|------|
| [PROGRESS.md](./PROGRESS.md) | **开发进度记录** — 每次会话详情、技术决策、已知问题与待办 |
| [development.md](./development.md) | 本地开发指南 |
| [deployment.md](./deployment.md) | 生产部署指南 |
| [release-notes.md](./release-notes.md) | 版本更新记录 |
| [standalone-tools/README.md](./standalone-tools/README.md) | 远程唤醒 (WOL) + DDNS 配置教程 |
| [CONTRIBUTING.md](./CONTRIBUTING.md) | 贡献指南 |

## 许可证

MIT License — 详见 [LICENSE](./LICENSE) 文件。
