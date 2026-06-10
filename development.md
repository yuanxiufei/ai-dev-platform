# FastAPI Project - Development

## Docker Compose

* Start the local stack with Docker Compose:

```bash
docker compose watch
```

* Now you can open your browser and interact with these URLs:

Frontend, built with Docker, with routes handled based on the path: <http://localhost:5173>

Backend, JSON based web API based on OpenAPI: <http://localhost:8000>

Automatic interactive documentation with Swagger UI (from the OpenAPI backend): <http://localhost:8000/docs>

Adminer, database web administration: <http://localhost:8080>

Traefik UI, to see how the routes are being handled by the proxy: <http://localhost:8090>

**Note**: The first time you start your stack, it might take a minute for it to be ready. While the backend waits for the database to be ready and configures everything. You can check the logs to monitor it.

To check the logs, run (in another terminal):

```bash
docker compose logs
```

To check the logs of a specific service, add the name of the service, e.g.:

```bash
docker compose logs backend
```

## Mailcatcher

Mailcatcher is a simple SMTP server that catches all emails sent by the backend during local development. Instead of sending real emails, they are captured and displayed in a web interface.

This is useful for:

* Testing email functionality during development
* Verifying email content and formatting
* Debugging email-related functionality without sending real emails

The backend is automatically configured to use Mailcatcher when running with Docker Compose locally (SMTP on port 1025). All captured emails can be viewed at <http://localhost:1080>.

## 本地开发（推荐方式）

**核心思路**：数据库/Redis 用 Docker 跑，前端/后端在本地跑，代码修改即时生效。

### 前置条件

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（Win/Mac）
- [Bun](https://bun.sh/)（前端运行时和包管理）
- [uv](https://docs.astral.sh/uv/)（Python 包管理）

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

```bash
cd backend
uv run fastapi dev app/main.py
```

后端自动读取根目录 `.env`（已预设 `POSTGRES_SERVER=localhost`、`REDIS_HOST=localhost`）。

修改代码 → 保存 → 自动热重载。

### 第四步：启动前端（新终端）

```bash
cd frontend
bun run dev
```

修改代码 → 自动热更新。

### 访问地址

| 服务 | URL |
|------|-----|
| 前端 | http://localhost:5173 |
| API 文档 | http://localhost:8000/docs |
| 数据库管理 | http://localhost:8080 |
| 邮件查看 | http://localhost:1080 |

### 启动 Celery Worker（可选，需要异步任务时）

```bash
cd backend
uv run celery -A queue.celery_app worker --loglevel=info --pool=solo
```

> Windows 上必须加 `--pool=solo`（Celery 限制）。

---

## Docker Compose 方式（不需本地安装运行时）

如果不想在本地装 Bun/uv，全部用 Docker 跑：

```bash
docker compose watch
```

`compose.override.yml` 已配置代码目录挂载和 `--reload` 热重载，修改代码后 Docker 内的服务会自动同步。

访问地址：
- 前端：http://localhost:5173
- 后端：http://localhost:8000
- 管理端：http://localhost:8080

---

## 只改前端 → 停 Docker 前端，跑本地

```bash
docker compose stop frontend
cd frontend && bun run dev
```

## 只改后端 → 停 Docker 后端，跑本地

```bash
docker compose stop backend
cd backend && uv run fastapi dev app/main.py
```

---

## 纯本地（不用 Docker）

需要本机安装 PostgreSQL 18 + Redis 7，然后把 `.env` 中的连接信息改成你的实例地址。

默认 `.env` 已经针对 `localhost` 配置：
- `POSTGRES_SERVER=localhost`
- `REDIS_HOST=localhost`
- `REDIS_URL=redis://localhost:6379/0`

然后直接执行第三步、第四步。

---

## .env 配置说明

`.env` 默认值适合本地开发。Docker Compose 会在容器内覆盖 `POSTGRES_SERVER=db`、`REDIS_HOST=redis` 等变量，所以同一个 `.env` 文件能兼容两种启动方式，不需要来回修改。
