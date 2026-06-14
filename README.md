# 🚀 AI Fullstack Platform

基于 FastAPI + Vue 3 / React 19 的 AI 全栈开发平台，集成代码生成、视频生成、异步任务处理等 AI 能力。

## 系统架构

```
  ┌──────────────────────────────────────────────┐
  │                  pnpm Monorepo               │
  │                                              │
  │  ┌──────────────┐  ┌──────────────┐         │
  │  │  video-client │  │  video-admin │         │
  │  │   (Vue 3)    │  │  (React 19)  │         │
  │  │   端口 5174   │  │   端口 5176   │         │
  │  └──────┬───────┘  └──────┬───────┘         │
  │  ┌──────┴───────┐  ┌──────┴───────┐         │
  │  │ studio-client│  │ studio-admin │         │
  │  │   (Vue 3)    │  │   (Vue 3)    │         │
  │  │   端口 5173   │  │   端口 5175   │         │
  │  └──────┬───────┘  └──────┬───────┘         │
  └─────────┼──────────────────┼─────────────────┘
            └────────┬─────────┘
                     ↓
       ┌──────────────────────────┐
       │   FastAPI API 网关       │  (REST + OpenAPI)
       └──────────┬───────────────┘
                  ↓
       ┌──────────────────┐
       │   Redis 消息队列  │
       └────────┬─────────┘
 ┌──────────────┴──────────────┐
 ↓                             ↓
代码生成 Worker              视频生成 Worker
(Qwen2.5-Coder)             (CogVideoX)
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
- 💻 **代码生成** — Qwen2.5-Coder（截图→代码、文本→API）
- 🎥 **视频生成** — CogVideoX（UI 演示、短视频）

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
| API 文档 | http://localhost:8000/docs |
| 数据库管理 | http://localhost:8080 |
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

# 3. 启动后端（终端 1）
uv run fastapi dev app/main.py

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
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── api/
│   │   │   ├── main.py         # 路由注册入口
│   │   │   └── routes/
│   │   │       ├── video/      # 视频业务 API
│   │   │       │   ├── admin/  # 管理端路由
│   │   │       │   └── client/ # C 端路由
│   │   │       └── studio/     # 代码业务 API
│   │   │           ├── admin/  # 管理端路由（项目/模板）
│   │   │           └── client/ # C 端路由（会话/模型/对话）
│   │   ├── core/              # 配置、JWT、数据库连接
│   │   ├── models.py          # SQLModel 数据模型
│   │   └── initial_data.py    # 初始化数据脚本
│   ├── scripts/prestart.sh    # 数据库迁移脚本
│   └── pyproject.toml
│
├── video-client/               # Vue 3 C 端 — 视频生成
│   ├── src/
│   ├── vite.config.ts          # 端口 5174
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
│
├── video-admin/                # React 19 管理端 — 视频管理
│   ├── src/
│   ├── vite.config.ts          # 端口 5176
│   ├── Dockerfile
│   ├── Dockerfile.playwright
│   ├── nginx.conf
│   └── package.json
│
├── studio-client/              # Vue 3 C 端 — AI 编辑器（含 Tauri）
│   ├── src/
│   ├── src-tauri/              # Tauri 桌面端
│   ├── vite.config.ts          # 端口 5173
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
│
├── studio-admin/               # Vue 3 管理端 — 项目管理 & 模板
│   ├── src/
│   ├── vite.config.ts          # 端口 5175
│   ├── Dockerfile
│   ├── nginx.conf
│   └── package.json
│
├── task_queue/                  # 任务队列
│   ├── celery_app.py          # Celery 配置
│   └── redis_config.py        # Redis 连接
│
├── models/                      # 🔥 模型权重文件存放目录
│   ├── Qwen2.5-VL-7B-Instruct/ # safetensors → Qwen2.5-VL
│   ├── Qwen2.5-Coder-7B-Instruct/ # safetensors → Qwen-Coder（回退）
│   ├── CogVideoX-5b/           # safetensors → CogVideoX
│   └── gemma-4-31B-it-qat-GGUF/ # GGUF → Gemma 31B（代码生成首选）
│
├── ai_models/                   # AI 模型层（按能力分类，自动适配格式）
│   ├── base.py                 # BaseModel 基类 + ModelConfig
│   ├── registry.py            # 模型注册中心（自动路径拼接）
│   ├── vl_model.py            # 视觉理解（截图→布局）
│   ├── coder_model.py         # 代码生成（safetensors / GGUF 统一接口）
│   ├── video_model.py         # 视频生成（文本→视频）
│   ├── prompts/               # Prompt 模板
│   │   ├── code_gen.py        # 代码生成提示词
│   │   └── video_gen.py       # 视频生成提示词
│   └── pyproject.toml
│
├── workers/                    # Celery 异步 Worker
│   ├── code_worker.py         # 代码生成任务
│   └── video_worker.py        # 视频生成任务
│
├── compose.yml                 # Docker Compose 编排
├── compose.override.yml        # 本地开发覆盖配置
├── .env                        # 环境变量
├── pnpm-workspace.yaml         # pnpm monorepo 配置
├── pyproject.toml              # Python 工作区配置
└── package.json                # 前端工作区根配置（dev/build 脚本）
```

---

## 核心 API

### 用户 / 认证
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/login/access-token` | 用户登录 |
| `POST` | `/api/v1/users/signup` | 用户注册 |
| `GET` | `/api/v1/users/me` | 获取当前用户 |
| `PATCH` | `/api/v1/users/me` | 更新当前用户 |
| `POST` | `/api/v1/password-recovery/{email}` | 密码找回 |

### 视频业务 (Video)
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/items/` | 获取项目列表 |
| `POST` | `/api/v1/items/` | 创建项目 |

### 代码 / AI 业务 (Studio)
| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/studio/projects` | 创建项目 |
| `GET` | `/studio/projects` | 项目列表 |
| `POST` | `/studio/templates` | 创建模板 |
| `GET` | `/studio/templates` | 模板列表 |
| `POST` | `/studio/sessions` | 创建会话 |
| `GET` | `/studio/sessions` | 会话列表 |
| `POST` | `/studio/models` | 模型管理 |
| `POST` | `/studio/chat` | AI 对话 |

### 运维
| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/utils/health-check/` | 健康检查 |

完整 API 见 Swagger 文档：http://localhost:8000/docs

---

## 配置说明

核心环境变量（`.env`）：

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

Docker Compose 在容器内会自动覆盖 `POSTGRES_SERVER=db`、`REDIS_HOST=redis`，所以同一个 `.env` 可同时兼容本地和 Docker 两种启动方式。

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
| [development.md](./development.md) | 本地开发指南 |
| [deployment.md](./deployment.md) | 生产部署指南 |
| [release-notes.md](./release-notes.md) | 版本更新记录 |

## License

MIT License — 详见 [LICENSE](./LICENSE) 文件。
