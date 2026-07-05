# Docker 快速启动指南

> 适用：Windows (WSL2) / 双系统 Linux。项目 `studio-client` 为桌面端（Tauri），不在 Docker 中部署。

---

## 一、三个 Compose 文件的角色

| 文件 | 用途 | 何时生效 |
|---|---|---|
| `compose.yml` | **生产环境**全部服务（10 个 service） | 始终生效 |
| `compose.override.yml` | **本地开发**覆盖层（开端口、热重载、mailcatcher） | 本地开发时**自动合并**到 compose.yml |
| `compose.traefik.yml` | **独立 Traefik 网关**（HTTPS 证书 + Dashboard） | 生产环境先部署此文件，再部署 compose.yml |

> 💡 Docker Compose 会自动合并 `compose.yml` + `compose.override.yml`，你只需要执行 `docker compose up -d` 即可。

---

## 二、全部服务一览

### 2.1 compose.yml 定义的服务

```
                    ┌── Traefik 网关（域名路由 + HTTPS）──┐
                    │       │          │          │        │
                  api.xxx  video.xxx  video-    studio-   adminer.xxx
                 (Backend) (用户端)  admin.xxx  admin.xxx  (DB面板)
                                       (管理端)   (管理端)
                    │
         ┌──────────┼──────────┐
         │          │          │
    PostgreSQL 16  Redis 7   Qdrant       Celery Worker
    (业务数据库)   (缓存队列) (向量搜索)   (异步任务)
```

| 服务 | 镜像/构建 | 本地端口 | 内部端口 | 说明 |
|---|---|---|---|---|
| **backend** | `backend/Dockerfile` | 18000 | 8000 | FastAPI 核心 API |
| **celery-worker** | 复用 backend 镜像 | — | — | 异步任务队列 |
| **prestart** | 复用 backend 镜像 | — | — | 数据库迁移（一次性） |
| **db** | `postgres:16-alpine` | 5432 | 5432 | 关系数据库 |
| **redis** | `redis:7-alpine` | 6379 | 6379 | 缓存 / 消息队列 |
| **qdrant** | `qdrant/qdrant:latest` | 6333 | 6333/6334 | 向量数据库 |
| **adminer** | `adminer` | 18080 | 8080 | 数据库管理面板 |
| **video-client** | `video-client/Dockerfile` | 5174 | 80 | Vue 3 C 端 — 视频浏览 |
| **video-admin** | `video-admin/Dockerfile` | 5176 | 80 | React 19 管理端 — 视频管理 |
| **studio-admin** | `studio-admin/Dockerfile` | 5175 | 80 | Vue 3 管理端 — 项目管理 |

### 2.2 compose.override.yml 额外服务

| 服务 | 镜像 | 本地端口 | 说明 |
|---|---|---|---|
| **proxy** (Traefik) | `traefik:3.6` | 80, 18090 | 本地反向代理 + Dashboard |
| **mailcatcher** | `schickling/mailcatcher` | 1080 | 本地邮件拦截（开发用） |
| **playwright** | `Dockerfile.playwright` | 9323 | E2E 测试（按需启动） |

---

## 三、快速启动（WSL2 / Linux 通用）

### 3.1 首次启动

```bash
# 1. 进入项目目录
cd /mnt/d/code/ai-fullstack-platform      # WSL2
# cd /path/to/ai-fullstack-platform        # 双系统 Linux

# 2. 构建所有镜像（首次 5~30 分钟，后续秒级）
docker compose build

# 3. 数据库迁移（仅首次，创建表结构）
docker compose run --rm prestart

# 4. 启动全部服务
docker compose up -d

# 5. 验证
docker ps
curl http://localhost:18000/api/v1/system/health
```

### 3.2 日常启动

```bash
cd /mnt/d/code/ai-fullstack-platform
docker compose up -d
```

### 3.3 停止

```bash
docker compose down
# 需要彻底清理（含 volumes）：docker compose down -v
```

### 3.4 更新代码后重建

```bash
# 重新构建有变更的镜像 + 重启
docker compose up -d --build
```

### 3.5 查看日志

```bash
docker compose logs -f backend          # 跟踪后端日志
docker compose logs -f --tail=50        # 最近 50 行所有服务日志
```

---

## 四、WSL2 专属：启动 Docker 守护进程

WSL2 中 Docker 不会开机自启，每次进 WSL 需要手动启动：

```bash
# 启动 Docker 守护进程
sudo dockerd &> /tmp/dockerd.log &

# 如果报 "exit code 1"（旧进程残留）
sudo kill $(pgrep dockerd) 2>/dev/null
sudo rm -f /var/run/docker.pid
sudo dockerd &> /tmp/dockerd.log &
```

> 💡 双系统 Linux 通常已自动启动 Docker（`systemctl start docker`）。

---

## 五、双系统 Linux 专属：路径差异

WSL2 和双系统 Linux 共用同一份**代码**（在 NTFS 分区，如 D 盘）和**Docker 数据盘**。

| 项目 | WSL2 路径 | 双系统 Linux 路径 |
|---|---|---|
| 项目代码 | `/mnt/d/code/ai-fullstack-platform` | `/media/用户/D盘/code/ai-fullstack-platform` |
| Docker 数据镜像 | `/mnt/d/app/Docker/docker-volumes.img` | 同上（NTFS 挂载点各异） |
| 挂载点 | `/mnt/dockervol` | `/mnt/dockervol` |

双系统 Linux 首次需挂载 Docker 数据盘：

```bash
# 挂载共享数据镜像（路径按实际 NTFS 挂载点调整）
sudo mount -o loop /media/用户名/D盘/app/Docker/docker-volumes.img /mnt/dockervol

# 确认 Docker data-root 正确
docker info --format '{{.DockerRootDir}}'
# 预期：/mnt/dockervol/docker
```

---

## 六、端口速查

| 服务 | 本地地址 |
|---|---|
| Backend API (Swagger) | http://localhost:18000/docs |
| Backend Health | http://localhost:18000/api/v1/system/health |
| Studio Admin | http://localhost:5175 |
| Video Client (C 端) | http://localhost:5174 |
| Video Admin (管理端) | http://localhost:5176 |
| Adminer (DB 面板) | http://localhost:18080 |
| Traefik Dashboard | http://localhost:18090 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |
| Qdrant | localhost:6333 (gRPC) / 6334 (HTTP) |

---

## 七、常用命令速查

```bash
docker compose up -d              # 启动所有服务
docker compose down               # 停止所有服务
docker compose restart backend    # 重启单个服务
docker compose build              # 构建所有镜像
docker compose build backend      # 只构建后端
docker compose ps                 # 查看服务状态
docker compose logs -f video-client  # 跟踪某个服务日志
docker compose run --rm prestart  # 手动执行数据库迁移

# 进入容器
docker exec -it $(docker compose ps -q db) psql -U admin -d studio
docker exec -it $(docker compose ps -q redis) redis-cli
```

---

## 八、常见问题

### Q: `docker compose up -d` 和 `docker compose -f compose.yml -f compose.override.yml up -d` 有什么区别？

A: 完全一样。Docker 在当前目录有 `compose.yml` 和 `compose.override.yml` 时会自动合并，不需要显式指定。

### Q: prestart 容器一直在 restart？

A: prestart 是一次性任务，跑完就退出。compose.override.yml 中跳过了 prestart 依赖（本地已做过迁移），所以看到 prestart 退出是正常的。

### Q: 切换系统后容器无法启动？

A: 可能是另一个系统没执行 `docker compose down`。解决办法：
```bash
docker compose -f compose.yml -f compose.override.yml up -d --force-recreate
```

### Q: backend 构建太慢？

A: Dockerfile 已做分层缓存（依赖层 vs 代码层）。代码没变时第二层秒过，只有 `pyproject.toml` 变更才重新装依赖。首次构建 `--group gpu` 需要下载 torch，约 10~30 分钟，此后增量构建秒级。

### Q: 端口被占用？

```bash
# Windows
netstat -ano | findstr :18000

# WSL2 / Linux
sudo lsof -i :18000
```
