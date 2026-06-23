# AI Fullstack Platform — Development Guide

## Docker Compose（一键启动所有服务）

```bash
docker compose watch
```

启动后访问：

| 服务 | URL |
|------|-----|
| Studio Client（C 端） | http://localhost:5173 |
| Video Client（C 端） | http://localhost:5174 |
| Studio Admin（管理端） | http://localhost:5175 |
| Video Admin（管理端） | http://localhost:5176 |
| 后端 API | http://localhost:8000 |
| API 文档 (Swagger) | http://localhost:8000/docs |
| 数据库管理 (Adminer) | http://localhost:18080 |
| 邮件查看 (Mailcatcher) | http://localhost:1080 |
| Traefik 面板 | http://localhost:8090 |

> 首次启动可能需要等待数据库就绪，可以通过 `docker compose logs backend` 查看日志。

---

## 本地开发（推荐方式）

**核心思路**：数据库 / Redis 用 Docker 跑，前端 / 后端在本地跑，代码修改即时生效。

### 前置条件

| 工具 | 用途 |
|------|------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | 数据库 / Redis / 邮件 |
| [pnpm](https://pnpm.io/) | 前端包管理 |
| [uv](https://docs.astral.sh/uv/) | Python 包管理 |

### 第一步：启动基础设施

只启动数据库、Redis、邮件服务：

```bash
# Windows PowerShell
docker compose up -d db redis mailcatcher
```

验证：

```bash
docker compose ps
# 确认 db、redis、mailcatcher 都是 Up/healthy 状态
```

### 第二步：初始化数据库（仅首次）

**Git Bash / WSL：**

```bash
cd backend && bash scripts/prestart.sh
```

**Windows PowerShell（手动执行）：**

```powershell
cd backend
uv run python app/backend_pre_start.py
uv run alembic upgrade head
uv run python app/initial_data.py
```

### 第三步：启动后端

**方式 A — Windows 一键启动（推荐）：**

```powershell
# 双击 start-backend.bat
# 或在终端运行：
start-backend.bat
```

> 自动杀掉 8000 端口占用进程，然后启动 uvicorn。

**方式 B — 开发模式（热重载）：**

```bash
cd backend
uv run fastapi dev app/main.py --port 8000
```

> 后端自动读取根目录 `.env`，修改代码 → 保存 → 自动热重载。

### 第四步：启动前端（新终端）

```bash
# 安装依赖（首次）
pnpm install

# Studio Client（C 端 AI 编辑器）
pnpm dev:studio-client

# Studio Admin（管理端）
pnpm dev:studio-admin

# Video Client（C 端视频生成）
pnpm dev:video-client

# Video Admin（管理端）
pnpm dev:video-admin
```

### 访问地址

| 服务 | URL |
|------|-----|
| Studio Client | http://localhost:5173 |
| Video Client | http://localhost:5174 |
| Studio Admin | http://localhost:5175 |
| Video Admin | http://localhost:5176 |
| API 文档 | http://localhost:8000/docs |
| 数据库管理 | http://localhost:18080 |
| 邮件查看 | http://localhost:1080 |

---

## Standalone 独立部署模式（Windows）

不依赖 Docker，一键启动。适用于单机/个人服务器场景。

### 启动

```powershell
# 初始化（仅首次，创建数据目录 + 默认配置）
python standalone.py --init

# 启动服务
start-standalone.bat
```

启动后访问：http://localhost:18000

### Standalone 特性

- **进程守护**：监控子进程健康，崩溃自动重启
- **Web 管理界面**：内置仪表盘，查看服务状态
- **远程唤醒 (WOL)**：通过 API 远程唤醒同一局域网的电脑
- **DDNS 动态域名**：自动更新阿里云 DNS 解析到当前公网 IP
- **终端代理**：WebSocket 远程终端访问

### Standalone API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/utils/health-check/` | 健康检查 |
| `POST` | `/api/v1/standalone/wol/send` | 发送 WOL 魔术包 |
| `POST` | `/api/v1/standalone/ddns/update` | 更新 DDNS 解析 |

> 详细配置见 [standalone-tools/README.md](./standalone-tools/README.md)

---

## 只改前端 → 停 Docker 前端，跑本地

```bash
docker compose stop studio-client video-client studio-admin video-admin
# 然后在本地启动需要的前端
cd studio-client && pnpm dev
```

## 只改后端 → 停 Docker 后端，跑本地

```bash
docker compose stop backend
# 方式 A: 双击 start-backend.bat（推荐）
# 方式 B:
cd backend && uv run fastapi dev app/main.py --port 8000
```

---

## Celery Worker（可选，需要异步任务时）

```bash
cd backend
uv run celery -A task_queue.celery_app worker --loglevel=info --pool=solo
```

> Windows 上必须加 `--pool=solo`（Celery 限制）。

---

## 模型管理

### 下载模型

系统支持从 HuggingFace 和 ModelScope 双源下载模型：

```bash
# 通过 CLI
cd backend
uv run python -m app.cli.main models download --name Qwen2.5-Coder-7B-Instruct

# 或通过 API
curl -X POST http://localhost:8000/api/v1/system/models/download \
  -H "Content-Type: application/json" \
  -d '{"model_name": "Qwen2.5-Coder-7B-Instruct", "source": "huggingface"}'
```

### 查看模型列表

```bash
# CLI
uv run python -m app.cli.main models list

# API
curl http://localhost:8000/api/v1/system/models
```

### 加载 / 卸载模型

```bash
# 加载模型到显存
curl -X POST http://localhost:8000/api/v1/system/models/qwen25-coder-7b/load

# 卸载模型释放显存
curl -X POST http://localhost:8000/api/v1/system/models/qwen25-coder-7b/unload

# 查看当前已加载
curl http://localhost:8000/api/v1/system/models/loaded
```

### 模型格式支持

| 格式 | 说明 | 示例 |
|------|------|------|
| Safetensors | HuggingFace 标准格式，支持 CUDA 加速 | Qwen2.5-Coder 7B |
| GGUF | 量化格式，CPU 友好，内存占用低 | Gemma 31B GGUF |
| ONNX | 跨平台推理，兼容性好 | — |

---

## 系统运维 API

### 健康检查

```bash
# 基本检查
curl http://localhost:8000/api/v1/system/health

# 详细检查（DB + 模型 + 网关 + 路由）
curl http://localhost:8000/api/v1/system/health/detailed

# 系统统计
curl http://localhost:8000/api/v1/system/health/stats
```

### 配置热加载

```bash
curl -X POST http://localhost:8000/api/v1/system/config/reload
```

### 触发自动优化

```bash
curl -X POST http://localhost:8000/api/v1/system/models/optimize
```

### GPU 状态监控

```bash
curl http://localhost:8000/api/v1/system/gpu/status
curl http://localhost:8000/api/v1/system/gpu/devices
```

### 资源使用

```bash
curl http://localhost:8000/api/v1/system/resources/current
curl http://localhost:8000/api/v1/system/resources/hardware
```

---

## 环境变量完整清单

### API 密钥

| 变量 | 说明 |
|------|------|
| `OPENAI_API_KEY` | OpenAI GPT-4o / o1 / o3 |
| `ANTHROPIC_API_KEY` | Claude Sonnet / Opus |
| `DEEPSEEK_API_KEY` | DeepSeek-V3 / Coder |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI Service |
| `REPLICATE_API_KEY` | CogVideoX / SVD |
| `ZHIPU_API_KEY` | GLM-4 Plus / GLM-4V |
| `QWEN_API_KEY` | 通义千问 Max / Plus |

### 模型与调度

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MODELS_DIR` | `models/` | 模型权重目录 |
| `MODEL_PREFER_LOCAL` | `true` | 优先本地模型 |
| `MODEL_REQUEST_TIMEOUT` | `30` | 请求超时秒 |
| `MODEL_MAX_RETRIES` | `2` | 最大重试 |
| `MODEL_FALLBACK_ENABLED` | `true` | 启用回退链 |
| `AUTO_OPTIMIZE_ENABLED` | `true` | 自动优化 |
| `AUTO_OPTIMIZE_INTERVAL_HOURS` | `24` | 优化间隔 |

### Standalone

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `STANDALONE_BIND_PORT` | `18000` | 绑定端口 |
| `STANDALONE_AUTO_START` | `true` | 自动启动 |
| `STANDALONE_WEB_UI` | `true` | Web 管理界面 |

---

## .env 配置说明

`.env` 默认值适合本地开发。Docker Compose 会在容器内覆盖 `POSTGRES_SERVER=db`、`REDIS_HOST=redis` 等变量，所以同一个 `.env` 文件能兼容两种启动方式，不需要来回修改。
