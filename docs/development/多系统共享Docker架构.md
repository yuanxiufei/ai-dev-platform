# 多系统共享 Docker 架构

> WSL2 (Windows) 和双系统 Linux 共享同一份 Docker 数据存储，通过 ext4 镜像文件实现。

---

## 架构图

```
Windows 宿主机 (D: 盘)
│
├── D:\code\ai-fullstack-platform\          ← 代码（NTFS），两系统共用
│   ├── compose.yml                         ← 生产服务定义（10 个 service）
│   ├── compose.override.yml                ← 本地开发覆盖（自动合并）
│   ├── compose.traefik.yml                 ← 生产 Traefik 网关
│   ├── .env                                ← 环境变量（两系统共用）
│   ├── backend/Dockerfile
│   ├── video-client/Dockerfile
│   ├── video-admin/Dockerfile
│   └── studio-admin/Dockerfile
│
├── D:\app\Docker\
│   ├── docker-volumes.img (70GB ext4)      ← 唯一数据盘，两系统共享
│   │   ├── docker/                         ← Docker data-root
│   │   │   ├── overlay2/                   ←   镜像层
│   │   │   ├── containers/                 ←   容器元数据
│   │   │   └── volumes/                    ←   compose 命名卷
│   │   │       ├── app-db-data/            → PostgreSQL
│   │   │       ├── redis-data/             → Redis
│   │   │       └── qdrant-data/            → Qdrant
│   │   ├── grafana/                        ← 监控面板
│   │   ├── open-webui/                     ← AI 对话
│   │   └── prometheus/                     ← 指标采集
│   └── Ubuntu-24.04\
│       └── ext4.vhdx                       ← WSL 发行版存储
│
└── D:\app\LLM\models\                      ← AI 模型权重实际存储
    ├── gguf/                                 ←   llama-cpp GGUF 模型
    ├── huggingface/                          ←   vLLM HuggingFace 缓存
    └── ollama/                               ←   Ollama 模型

└── D:\code\ai-fullstack-platform\models\    ← 项目内 models/（目录链接）
    ├── gguf → D:\app\LLM\models\gguf         ←   Windows: NTFS Junction (mklink /J)
    ├── huggingface → D:\app\LLM\models\huggingface
    └── ollama → D:\app\LLM\models\ollama
```

**核心原则**：两系统使用完全相同的 `compose.yml` + `compose.override.yml` + `.env`，零本地差异化配置。

---

## 系统一：WSL2 (Windows)

### 启动步骤

**每次进入 WSL 执行：**

```bash
# 1. 挂载共享数据镜像
sudo mount -o loop /mnt/d/app/Docker/docker-volumes.img /mnt/dockervol

# 2. 启动 Docker 守护进程
sudo dockerd &> /tmp/dockerd.log &

# 3. 进入项目，启动所有服务
cd /mnt/d/code/ai-fullstack-platform
docker compose up -d
```

**停止（退出 WSL 前执行）：**

```bash
cd /mnt/d/code/ai-fullstack-platform
docker compose down
# 镜像可选择性卸载：
# sudo umount /mnt/dockervol
```

### dockerd 启动失败处理

```bash
# 报 "exit code 1" → 旧 PID 残留
sudo kill $(pgrep dockerd) 2>/dev/null
sudo rm -f /var/run/docker.pid
sudo dockerd &> /tmp/dockerd.log &
```

---

## 系统二：双系统 Linux

### 启动步骤

```bash
# 1. 挂载共享数据镜像（路径按实际 NTFS 分区挂载点调整）
sudo mount -o loop /media/用户名/Data/app/Docker/docker-volumes.img /mnt/dockervol

# 2. 启动 Docker（通常已开机自启）
sudo systemctl start docker

# 3. 进入项目，启动所有服务
cd /media/用户名/Data/code/ai-fullstack-platform
docker compose up -d
```

**停止（切回 Windows 前执行）：**

```bash
cd /media/用户名/Data/code/ai-fullstack-platform
docker compose down
```

---

## 两系统路径对照

| 项目 | WSL2 | 双系统 Linux |
|---|---|---|
| **项目代码** | `/mnt/d/code/ai-fullstack-platform` | `/media/用户名/Data/code/ai-fullstack-platform` |
| **数据镜像** | `/mnt/d/app/Docker/docker-volumes.img` | `/media/用户名/Data/app/Docker/docker-volumes.img` |
| **挂载点** | `/mnt/dockervol` | `/mnt/dockervol` |
| **AI 模型实际存储** | `/mnt/d/app/LLM/models/`（含 gguf/huggingface/ollama） | `/media/用户名/Data/app/LLM/models/` |
| **项目内 models/ 链接** | `models/gguf → /mnt/d/app/LLM/models/gguf`（等 3 个） | `models/gguf → /media/.../app/LLM/models/gguf`（等 3 个） |

---

## 模型目录链接机制

### 为什么需要目录链接？

AI 模型权重文件体积巨大（数十 GB），不适合放在项目 Git 仓库中。模型文件实际存储在 `D:/app/LLM/models/`（Windows）或对应的 Linux 路径，但 Docker Compose 卷挂载使用项目相对路径 `${MODELS_DIR:-../models}`。

**解决方案**：在项目 `models/` 目录下创建指向实际存储的目录链接。

### .env 配置说明

`.env` **不再设置 `MODELS_DIR`**，Docker Compose 自行回退为 `../models`（即项目根目录的 `models/`）。`models/` 内的子目录通过平台原生的目录链接解析到实际存储位置：

```
项目 models/
├── gguf → /实际路径/LLM/models/gguf        (各系统自行创建)
├── huggingface → /实际路径/LLM/models/huggingface
└── ollama → /实际路径/LLM/models/ollama
```

Docker Compose 的卷挂载写法（`deploy/compose.shared.yml`）：

```yaml
volumes:
  - ${MODELS_DIR:-../models}/gguf:/models:ro
```

Compose 解析 `${MODELS_DIR:-../models}` → 取 `../models`（默认值）→ 通过 `models/gguf` 目录链接 → 最终读到实际模型文件。

### 各平台创建命令

#### Windows（NTFS Junction，在项目根目录执行）

```batch
cd D:\code\ai-fullstack-platform
mklink /J models\gguf D:\app\LLM\models\gguf
mklink /J models\huggingface D:\app\LLM\models\huggingface
mklink /J models\ollama D:\app\LLM\models\ollama
```

#### 双系统 Linux / WSL2（符号链接，在项目根目录执行）

```bash
cd /mnt/d/code/ai-fullstack-platform   # WSL2
# 或
cd /media/用户名/Data/code/ai-fullstack-platform  # 双系统

ln -s /mnt/d/app/LLM/models/gguf models/gguf
ln -s /mnt/d/app/LLM/models/huggingface models/huggingface
ln -s /mnt/d/app/LLM/models/ollama models/ollama
```

> **注意**：Linux 下 `ln -s` 的目标路径必须是该 Linux 环境内可访问的路径（WSL2 用 `/mnt/d/...`，双系统用 `/media/.../...`）。
> 如果实际存储路径不同，请根据各自系统的挂载点调整。

### 验证链接

```bash
# Windows
dir /AL models

# Linux
ls -la models/
```

---

## 全部 Docker 服务清单

### compose.yml 服务

| 服务 | 镜像/构建 | 本地端口 | 内部端口 | 网络 |
|---|---|---|---|---|
| **backend** | `backend/Dockerfile` | 18000 | 8000 | default |
| **celery-worker** | 复用 backend | — | — | default |
| **prestart** | 复用 backend | — | — | default |
| **db** | postgres:16-alpine | 5432 | 5432 | default |
| **redis** | redis:7-alpine | 6379 | 6379 | default |
| **qdrant** | qdrant/qdrant | 6333 | 6333/6334 | default |
| **adminer** | adminer | 18080 | 8080 | default |
| **video-client** | `video-client/Dockerfile` | 5174 | 80 | default |
| **video-admin** | `video-admin/Dockerfile` | 5176 | 80 | default |
| **studio-admin** | `studio-admin/Dockerfile` | 5175 | 80 | default |

### compose.override.yml 附加

| 服务 | 镜像 | 端口 | 说明 |
|---|---|---|---|
| **proxy** | traefik:3.6 | 80, 18090 | 本地反向代理 |
| **mailcatcher** | schickling/mailcatcher | 1080, 1025 | 开发邮件拦截 |
| **playwright** | `video-admin/Dockerfile.playwright` | 9323 | E2E 测试（按需） |

---

## 切换系统注意事项

| 规则 | 说明 |
|---|---|
| **退出前必须 `docker compose down`** | 否则另一系统启动时容器状态不一致 |
| **`.env` 两系统通用** | `POSTGRES_SERVER=db` / `REDIS_URL=redis://redis:6379/0` 用 Docker 服务名，不设 `MODELS_DIR` |
| **模型目录链接** | 每个系统需自行创建 `models/` 下的目录链接指向实际存储路径 |
| **镜像可能需重建** | overlay2 驱动版本差异时，`docker compose build --no-cache` |
| **ext4 镜像挂载失败** | `sudo fsck.ext4 -y /path/to/docker-volumes.img` 修复后重新挂载 |

---

## 服务验证

```bash
# 快速检查所有容器状态
docker ps --format 'table {{.Names}}\t{{.Status}}'

# Backend API 健康检查（WSL2/Linux 通用）
curl http://localhost:18000/api/v1/system/health
# 预期：{"status":"healthy"}

# PostgreSQL
docker exec $(docker compose ps -q db) pg_isready -U admin -d studio

# Redis
docker exec $(docker compose ps -q redis) redis-cli PING
# 预期：PONG

# 前端页面
curl -s -o /dev/null -w "%{http_code}" http://localhost:5175  # studio-admin
curl -s -o /dev/null -w "%{http_code}" http://localhost:5174  # video-client
curl -s -o /dev/null -w "%{http_code}" http://localhost:5176  # video-admin
# 预期：200
```

---

## 常见问题

### Q: 从 Linux 切回 WSL 后容器无法启动？

A: 在 Linux 上忘了 `docker compose down`。解决：
```bash
docker compose up -d --force-recreate
```

### Q: 镜像挂载失败 `mount: wrong fs type`？

A: ext4 镜像有脏日志，修复：
```bash
sudo fsck.ext4 -y /mnt/d/app/Docker/docker-volumes.img
sudo mount -o loop /mnt/d/app/Docker/docker-volumes.img /mnt/dockervol
```

### Q: 确认 Docker data-root 指向正确？

```bash
docker info --format 'DockerRootDir={{.DockerRootDir}}'
# 预期：DockerRootDir=/mnt/dockervol/docker
```

### Q: 两系统 compose 文件完全一样吗？

A: 是。`compose.yml` + `compose.override.yml` + `.env` 在两系统间零差异，Docker 自动合并两个 yml 文件。所有路径差异都通过 `/mnt/d/...` 和对应 Linux 的 NTFS 挂载点解决。

---

## 相关文件

| 文件 | 用途 |
|---|---|
| `compose.yml` | 生产环境主配置（10 个 service） |
| `compose.override.yml` | 本地开发覆盖（端口映射、热重载、mailcatcher） |
| `compose.traefik.yml` | 生产 Traefik 网关（独立部署） |
| `.env` | 环境变量（Docker 服务名，两系统通用） |
| `backend/Dockerfile` | Backend 镜像（python:3.12 + uv + GPU 依赖） |
| `video-client/Dockerfile` | Video C 端（Vue 3 + Vite → nginx:alpine） |
| `video-admin/Dockerfile` | Video 管理端（React 19 + Vite → nginx:alpine） |
| `studio-admin/Dockerfile` | Studio 管理端（Vue 3 + Vite → nginx:alpine） |
| `video-admin/Dockerfile.playwright` | Playwright E2E 测试镜像 |
| `D:\app\Docker\docker-volumes.img` | ext4 共享数据镜像（70GB） |
