# 部署指南

## 架构总览

```
┌──────────────────────────────────────────────────┐
│              NTFS 共享分区 (Software/D:)           │
│                                                  │
│  app/Docker/docker-volumes.img (70GB ext4)       │
│    └─→ mount /data/docker-volumes                │
│        ├── docker/         ← Docker data-root    │
│        ├── postgres/       ← 数据库 (47MB)        │
│        ├── redis/          ← 缓存                │
│        ├── qdrant/         ← 向量库              │
│        ├── open-webui/     ← AI 界面配置          │
│        ├── prometheus/     ← 监控指标             │
│        ├── grafana/        ← 仪表盘              │
│        └── alertmanager/   ← 告警                │
│                                                  │
│  app/LLM/models/                                  │
│    ├── ollama/             ← LLM 模型 (bind)      │
│    └── huggingface/        ← vLLM 模型 (bind)     │
└──────────────────────────────────────────────────┘
```

**Linux 和 WSL2 共享同一个 ext4 文件，镜像层 + 数据库 + 所有服务数据都是同一份。**

---

## 快速启动

```bash
cd ai-fullstack-platform
bash setup.sh
```

脚本自动识别 Linux / WSL2，挂载 ext4、配置 Docker、启动全部服务。

---

## 系统配置详情

### 1. ext4 卷挂载

**Linux** (`/etc/fstab`):
```
/run/media/reginyuan/Software/app/Docker/docker-volumes.img /data/docker-volumes ext4 loop,defaults 0 0
```

**WSL2** (启动时手动挂载，`setup.sh` 执行):
```bash
sudo mount -o loop /mnt/d/app/Docker/docker-volumes.img /data/docker-volumes
```

### 2. Docker daemon.json

**Linux** (`/etc/docker/daemon.json`):
```json
{
    "data-root": "/data/docker-volumes/docker",
    "default-runtime": "nvidia",
    "registry-mirrors": [
        "https://docker.m.daocloud.io"
    ],
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    }
}
```

**WSL2** (`/etc/docker/daemon.json`):
```json
{
    "data-root": "/data/docker-volumes/docker",
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    }
}
```
> WSL2 不能设 `default-runtime: nvidia`，否则 postgres/redis 等非 GPU 容器会崩溃。GPU 容器需在 compose 中显式 `runtime: nvidia`。

### 3. Docker 启动

| 系统 | 方式 |
|------|------|
| Linux | `sudo systemctl start docker` |
| WSL2 | `sudo dockerd &> /tmp/dockerd.log &` |

### 4. NTFS 分区路径对照

| 内容 | Linux | WSL2 |
|------|-------|------|
| 项目代码 | `/run/media/reginyuan/Software/code/ai-fullstack-platform` | `/mnt/d/code/ai-fullstack-platform` |
| ext4 镜像 | `/run/media/reginyuan/Software/app/Docker/docker-volumes.img` | `/mnt/d/app/Docker/docker-volumes.img` |
| Ollama 模型 | `/run/media/reginyuan/Software/app/LLM/models/ollama` | `/mnt/d/app/LLM/models/ollama` |
| HuggingFace 模型 | `/run/media/reginyuan/Software/app/LLM/models/huggingface` | `/mnt/d/app/LLM/models/huggingface` |

---

## 服务参数

### 镜像（13 个）

#### 公共镜像（9 个，从 Docker Hub 拉取）

| 镜像 | 大小 | 用途 | 提供方 |
|------|------|------|--------|
| `postgres:16-alpine` | 420MB | 关系数据库 | PostgreSQL 官方 |
| `redis:7-alpine` | 58MB | 缓存 / 消息队列 | Redis 官方 |
| `qdrant/qdrant:latest` | 270MB | 向量数据库 (RAG) | Qdrant 官方 |
| `ollama/ollama:latest` | 8.0GB | LLM 推理 (GPU) | Ollama 官方 |
| `vllm/vllm-openai:latest` | 29.8GB | 高性能推理 (GPU) | vLLM 官方 |
| `ghcr.io/open-webui/open-webui:main` | 6.7GB | AI 对话面板 | Open WebUI 社区 |
| `prom/prometheus:latest` | 359MB | 指标采集 | Prometheus 官方 |
| `prom/alertmanager:latest` | 121MB | 告警路由 | Prometheus 官方 |
| `grafana/grafana:latest` | 1.6GB | 可视化仪表盘 | Grafana 官方 |
| **公共镜像小计** | **47.4GB** | | |

#### 项目构建镜像（4 个，本地 `docker compose build`）

| 镜像 | 大小 | 用途 | Dockerfile |
|------|------|------|------------|
| `ai-platform-backend:latest` | 19.7GB | FastAPI 后端 (模型路由+Agent+闭环) | `backend/Dockerfile` |
| `ai-platform-studio-admin:latest` | 93MB | AI 编程项目管理端 (Nginx SPA) | `studio-admin/Dockerfile` |
| `ai-platform-video-client:latest` | 93MB | 视频生成 C 端 (Nginx SPA) | `video-client/Dockerfile` |
| `ai-platform-video-admin:latest` | 93MB | 视频生成管理端 (Nginx SPA) | `video-admin/Dockerfile` |
| **项目镜像小计** | **~20GB** | | |

> studio-client 为桌面端跨端应用，不在此处构建镜像。

#### 补充镜像

| 镜像 | 大小 | 用途 | 提供方 |
|------|------|------|--------|
| `adminer:latest` | 170MB | 数据库 Web 管理面板 | Adminer 官方 |

> 以上全部镜像通过 `docker compose` 从 Docker Hub 拉取或 `docker compose build` 本地构建，存储在 ext4 卷内。
> **Linux 和 WSL2 共享同一份文件**，包含镜像层、数据库、缓存、监控等全部数据。

### 服务端口与凭证

| 服务 | 端口 | 用户 | 密码 | 数据库 |
|------|------|------|------|--------|
| PostgreSQL | 5432 | `admin` | `admin123` | `studio` |
| Redis | 6379 | — | — | — |
| Qdrant HTTP | 6334 | — | — | — |
| Qdrant gRPC | 6333 | — | — | — |
| Ollama API | 11434 | — | — | — |
| vLLM API | 3080 | — | — | — |
| Open WebUI | 3090 | — | — | — |
| Prometheus | 9090 | — | — | — |
| Alertmanager | 9093 | — | — | — |
| Grafana | 9091 | `admin` | `admin` | — |

### 数据存储量

| 数据 | 大小 | 位置 |
|------|------|------|
| PostgreSQL | 47MB | `/data/docker-volumes/postgres/` |
| Redis | 8KB | `/data/docker-volumes/redis/` |
| Qdrant | 20KB | `/data/docker-volumes/qdrant/` |
| Open WebUI | 844KB | `/data/docker-volumes/open-webui/` |
| Grafana | 50MB | `/data/docker-volumes/grafana/` |
| Prometheus | 400KB | `/data/docker-volumes/prometheus/` |

---

## 环境变量

```bash
# PostgreSQL
POSTGRES_USER=admin          # 默认
POSTGRES_PASSWORD=admin123   # 默认
POSTGRES_DB=studio           # 默认

# Grafana
GRAFANA_USER=admin           # 默认
GRAFANA_PASSWORD=admin       # 默认

# WSL2 额外需要
CELERY_POOL=solo             # 仅 WSL2
```

---

## compose.shared.yml 结构

共 **16 个服务**（10 基础服务 + 6 应用层服务），studio-client 为桌面端跨端应用，不在 Docker 中部署。

```yaml
services:
  postgres:        # PostgreSQL 16, 端口 5432
  redis:           # Redis 7, 端口 6379
  qdrant:          # Qdrant 向量库, 端口 6333/6334
  ollama:          # Ollama LLM, 端口 11434 (GPU)
  vllm:            # vLLM 推理, 端口 3080 (GPU)
  open-webui:      # AI 对话面板, 端口 3090
  prometheus:      # 监控采集, 端口 9090
  alertmanager:    # 告警路由, 端口 9093
  grafana:         # 仪表盘, 端口 9091
  prestart:        # 数据库迁移 (需构建)
  backend:         # FastAPI 后端 (需构建)
  celery-worker:   # 异步任务 (WSL2 需 --pool=solo)
  adminer:         # 数据库管理, 端口 18080
  studio-admin:    # 项目管理前端 (需构建)
  video-client:    # 视频 C 端 (需构建)
  video-admin:     # 视频管理端 (需构建)
  (studio-client 为桌面端跨端应用，不在 Docker 中部署)

volumes: (全部使用 bind mount 到 /data/docker-volumes/)
networks: ai-platform-net (bridge)
```

---

## compose.shared.yml 各服务详细配置

### PostgreSQL
- **镜像**: `postgres:16-alpine`
- **端口**: `5432:5432`
- **环境变量**:
  - `POSTGRES_USER=admin`
  - `POSTGRES_PASSWORD=admin123`
  - `POSTGRES_DB=studio`
  - `PGDATA=/var/lib/postgresql/data/pgdata`
- **数据卷**: `/data/docker-volumes/postgres:/var/lib/postgresql/data`
- **健康检查**: `pg_isready -U admin -d studio`

### Redis
- **镜像**: `redis:7-alpine`
- **端口**: `6379:6379`
- **数据卷**: `/data/docker-volumes/redis:/data`
- **健康检查**: `redis-cli ping`
- **认证**: 无密码

### Qdrant
- **镜像**: `qdrant/qdrant:latest`
- **端口**: `6333:6333` (gRPC), `6334:6334` (HTTP)
- **数据卷**: `/data/docker-volumes/qdrant:/qdrant/storage`
- **健康检查**: `bash -c 'echo >/dev/tcp/localhost/6333'` (容器无 curl，用 bash 内置 TCP 检测)

### Ollama
- **镜像**: `ollama/ollama:latest`
- **端口**: `11434:11434`
- **运行时**: `nvidia` (GPU)
- **环境**: `OLLAMA_KEEP_ALIVE=24h`, `OLLAMA_HOST=0.0.0.0`
- **数据卷**: `$MODELS_DIR/ollama:/root/.ollama` (NTFS bind mount)

### vLLM
- **镜像**: `vllm/vllm-openai:latest`
- **端口**: `3080:3080`
- **运行时**: `nvidia` (GPU)
- **环境**: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`
- **数据卷**: `$MODELS_DIR/huggingface:/root/.cache/huggingface:ro` (NTFS, 只读)
- **命令**: `--model /root/.cache/huggingface/models/qwen2 --port 3080 --host 0.0.0.0`

### Open WebUI
- **镜像**: `ghcr.io/open-webui/open-webui:main`
- **端口**: `3090:8080`
- **依赖**: ollama
- **环境**: `OLLAMA_BASE_URL=http://ollama:11434`, `OPENAI_API_BASE_URLS=http://vllm:3080/v1`, `RAG_EMBEDDING_ENGINE=ollama`
- **数据卷**: `/data/docker-volumes/open-webui:/app/backend/data`

### Prometheus
- **镜像**: `prom/prometheus:latest`
- **端口**: `9090:9090`
- **数据卷**: `/data/docker-volumes/prometheus:/prometheus`

### Alertmanager
- **镜像**: `prom/alertmanager:latest`
- **端口**: `9093:9093`
- **数据卷**: `/data/docker-volumes/alertmanager:/alertmanager`

### Grafana
- **镜像**: `grafana/grafana:latest`
- **端口**: `9091:3000`
- **凭据**: `admin / admin`
- **依赖**: prometheus
- **数据卷**: `/data/docker-volumes/grafana:/var/lib/grafana`

---

## 系统差异对照表

| 配置项 | Linux | WSL2 |
|--------|-------|------|
| `daemon.json`: default-runtime | `nvidia` | 不设 (仅 runc) |
| GPU 访问 | 原生直通 | nvidia-container-toolkit 桥接 |
| Docker 启动 | `systemctl start docker` | `sudo dockerd &` |
| NTFS 路径前缀 | `/run/media/reginyuan/Software` | `/mnt/d` |
| ext4 镜像路径 | `/run/media/reginyuan/Software/app/Docker/docker-volumes.img` | `/mnt/d/app/Docker/docker-volumes.img` |
| celery pool | `prefork` | `--pool=solo` |
| Ollama/vLLM GPU | 默认可用 | 需要 nvidia-container-toolkit |

> 以上差异由 `setup.sh` 自动检测并处理。

---

## 日常使用：切换系统

两个系统共享同一份 ext4 数据，切换时只需启动 Docker 和执行 `setup.sh`：

```bash
# 任意系统重启后
cd ai-fullstack-platform
bash setup.sh
```

`setup.sh` 会自动：
1. 检测 Linux / WSL2 环境
2. 挂载 ext4 卷（如未挂载）
3. 配置 Docker daemon.json（适配当前系统）
4. 启动所有基础服务

> 切换系统后数据无感知 — 数据库、缓存、模型、监控历史完全一致。

---

## 从零部署（首次）

### Linux
```bash
# 1. Docker 已安装 (systemd)
# 2. 创建 ext4 卷 (首次)
sudo dd if=/dev/zero of=/run/media/reginyuan/Software/app/Docker/docker-volumes.img bs=1M count=71680
sudo mkfs.ext4 -F /run/media/reginyuan/Software/app/Docker/docker-volumes.img
sudo mkdir -p /data/docker-volumes
sudo echo "/run/media/reginyuan/Software/app/Docker/docker-volumes.img /data/docker-volumes ext4 loop,defaults 0 0" | sudo tee -a /etc/fstab
sudo mount /data/docker-volumes

# 3. 启动
cd /run/media/reginyuan/Software/code/ai-fullstack-platform
bash setup.sh
```

### Windows WSL2

前提：ext4 卷已在 Linux 端创建（仅需创建一次，两个系统共享同一个 .img 文件）。

```bash
# 1. 安装 WSL2 + Docker + nvidia-container-toolkit
# 2. 启动 WSL2
wsl -d Ubuntu-24.04

# 3. 挂载 ext4 卷并启动全部服务（setup.sh 自动处理）
cd /mnt/d/code/ai-fullstack-platform
bash setup.sh
```

> WSL2 启动后所有 Docker 数据（镜像层、数据库、缓存）与 Linux 共享同一份 ext4 卷，切换系统无需重新拉取镜像或导入数据。

---

## 验证部署

```bash
# 查看所有容器状态
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# 逐一验证服务可达
docker exec postgres pg_isready -U admin -d studio  # PostgreSQL
docker exec redis redis-cli ping                     # Redis
curl -s http://localhost:6333/telemetry              # Qdrant
curl -s http://localhost:11434/api/tags              # Ollama
curl -s http://localhost:3080/v1/models              # vLLM
curl -s http://localhost:3090/                       # Open WebUI
curl -s http://localhost:9090/-/healthy              # Prometheus
curl -s http://localhost:9091/api/health             # Grafana
curl -s http://localhost:9093/-/healthy              # Alertmanager
curl -s http://localhost:18080/                      # Adminer
```

> 无论 Linux 还是 WSL2 启动，以上验证结果应完全一致。
