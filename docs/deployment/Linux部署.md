# 全栈 AI 平台部署指南 —— Linux

> 在原生 Linux（Ubuntu/Debian/CentOS）上通过 `compose.yml` 一键部署全栈 AI 平台（PostgreSQL + Redis + Qdrant + Backend API + 3 前端 + Ollama + vLLM + Open WebUI + 监控栈）。
>
> **📄 通用架构与 compose 文件说明**：先阅读 [`Docker快速启动.md`](Docker快速启动.md) 了解 3 个 compose 文件的关系、全部服务清单和端口速查。
>
> **📄 部署概览**：CI/CD、Traefik 网关、监控栈等进阶配置见 [`部署概览.md`](部署概览.md)。

**适用人群**：Linux 服务器、双系统 Linux 用户、追求最佳性能的开发者。

**前置条件**：NVIDIA GPU 驱动已安装，Docker 基本熟悉。

---

## 〇、Linux 部署优势

与 Windows（WSL2/Docker Desktop）相比，原生 Linux 有显著优势：

| 对比维度 | Linux | WSL2 |
|---|---|---|
| 安装 Docker | `systemctl enable docker --now`（系统服务） | 手动 `sudo dockerd &` |
| 路径 | 直接 `/home/user/` 访问 | `/mnt/c/` `/mnt/d/` 前缀 |
| 文件 IO | 原生 ext4/xfs 速度 | 9P 跨文件系统有损耗 |
| daemon.json | `/etc/docker/daemon.json` | 同 |
| default-runtime: nvidia | ✅ 全部容器可安全使用 | ❌ 会崩 postgres/redis |
| vLLM UVA | ✅ 原生支持，无需 patch | ❌ 需 `vllm_entrypoint.sh` 补丁 |
| 模型加载速度 | ~5-10s（7B） | ~20-30s（7B） |
| 符号链接 | 完全支持 | NTFS 不支持 |

---

## 一、环境准备

### 1.1 硬件与环境

| 项 | 典型值 |
|---|---|
| 操作系统 | Ubuntu 24.04 / Debian 12 / CentOS 9 |
| GPU | NVIDIA RTX A5000 / 23GB VRAM / CUDA 13.2 |
| Docker | 29.1.3 |
| nvidia-container-toolkit | 1.19+ |

### 1.2 安装 Docker

```bash
# Ubuntu / Debian
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable docker --now    # 开机自启 + 立即启动

# CentOS / RHEL / Fedora
sudo dnf install -y docker docker-compose-plugin
sudo systemctl enable docker --now

# 免 sudo 使用（所有发行版）
sudo usermod -aG docker $USER
# 退出重新登录生效
```

> 💡 **Linux 最大优势**：`systemctl` 管理 dockerd，无需像 WSL2 那样每次手动 `sudo dockerd &`。

### 1.3 安装 NVIDIA Container Toolkit

```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
  sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

### 1.4 验证

```bash
nvidia-smi                  # 能显示 GPU
sudo nvidia-ctk --version   # 1.19.x
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

### 1.5 daemon.json（推荐默认 runtime）

原生 Linux 上 GPU 直通稳定，**可以安全设为默认 runtime**：

```json
{
  "data-root": "/var/lib/docker",
  "default-runtime": "nvidia",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
```

保存到 `/etc/docker/daemon.json` → `sudo systemctl restart docker`。

> 💡 Linux 上 `"default-runtime": "nvidia"` 是安全的，不会像 WSL2 那样导致 postgres/redis 崩溃。

---

## 二、快速部署

```bash
# 1. 进入项目目录
cd /path/to/ai-fullstack-platform

# 2. 首次构建所有镜像（~30 分钟，后续秒级）
docker compose build

# 3. 首次执行数据库迁移（仅一次）
docker compose run --rm prestart

# 4. 一键启动（compose.yml + compose.override.yml 自动合并）
docker compose up -d

# 5. 验证
docker ps
curl http://localhost:18000/api/v1/system/health
nvidia-smi
```

> 💡 **Linux 最大优势**：`systemctl` 管理 dockerd，无需像 WSL2 那样每次手动 `sudo dockerd &`。`compose.yml` 定义全部 10 个 service，`docker compose up -d` 一站式启动。

---

## 三、架构概览

```
┌──────────────────────────────────────────────────────────────────┐
│                         Linux 宿主机                               │
│  :18000(API) :5175(Studio Admin) :5174(Video C) :5176(Video Admin)│
│  :18080(Adminer) :18090(Traefik) :3090(WebUI) :11434(Ollama)     │
│  :3080(vLLM) :5432(PG) :6379(Redis) :6333(Qdrant) :9091(Grafana) │
│                                                                    │
│  ┌───────────────── 全部 compose.yml service ──────────────────┐  │
│  │  db(postgres)  redis  qdrant     ← 基础设施                  │  │
│  │  ollama  vllm  open-webui        ← AI 推理（GPU）            │  │
│  │  backend  celery-worker  prestart ← 核心 API + 任务队列       │  │
│  │  video-client  video-admin  studio-admin ← 前端 Nginx 静态     │  │
│  │  adminer  prometheus  grafana  alertmanager ← 辅助/监控       │  │
│  │  proxy(traefik)  mailcatcher  playwright ← 开发叠加层         │  │
│  └──────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

> 📦 `compose.yml` 定义全部 10 个 service，`compose.override.yml` 叠加开发配置（端口映射/热重载/Traefik）。`docker compose up -d` 自动合并两个文件。完整服务清单见 [`Docker快速启动.md`](Docker快速启动.md)。

---

## 四、全部容器清单

### 应用服务（compose.yml 需构建）

| 服务 | 镜像 | 端口 | 默认凭证 | 用途 |
|---|---|---|---|---|
| **Backend API** | `ai-platform-backend:latest` | 18000:8000 | admin@example.com/changethis | FastAPI 核心 API |
| **Celery Worker** | `ai-platform-backend:latest` | — | — | 异步任务队列 |
| **video-client** | `ai-platform-video-client:latest` | 5174:80 | — | Vue 3 视频浏览 C 端 |
| **video-admin** | `ai-platform-video-admin:latest` | 5176:80 | — | React 19 视频管理后台 |
| **studio-admin** | `ai-platform-studio-admin:latest` | 5175:80 | — | Vue 3 Studio 管理后台 |
| Adminer | `adminer` | 18080:8080 | — | 数据库可视化管理 |
| Traefik (proxy) | `traefik:3.6` | 80, 18090 | — | 反向代理（叠加层） |

### 基础设施（官方镜像）

| 服务 | 镜像 | 端口 | 默认凭证 |
|---|---|---|---|
| PostgreSQL 16 | `postgres:16-alpine` | 5432 | admin/admin123/studio |
| Redis 7 | `redis:7-alpine` | 6379 | 无密码 |
| Qdrant | `qdrant/qdrant:latest` | 6333/6334 | — |

### AI 服务（GPU，可选）

| 服务 | 镜像 | 端口 | GPU | 用途 |
|---|---|---|---|---|
| **Ollama** ⭐ | `ollama/ollama:latest` | 11434 | ✅ | 多模型管理，API 热切换 |
| vLLM | `vllm/vllm-openai:latest` | 3080 | ✅ | 单模型高并发 |
| Open WebUI | `ghcr.io/open-webui/open-webui:main` | 3090 | ❌ | AI 对话界面 |

### 监控

| 服务 | 镜像 | 端口 | 凭证 |
|---|---|---|---|
| Prometheus | `prom/prometheus:latest` | 9090 | — |
| Alertmanager | `prom/alertmanager:latest` | 9093 | — |
| Grafana | `grafana/grafana:latest` | 9091 | admin/admin |

### 地址速查

```
Backend API    → http://localhost:18000/api/v1/system/health
Studio Admin   → http://localhost:5175             (Vue 3 管理端)
Video Client   → http://localhost:5174             (Vue 3 C 端)
Video Admin    → http://localhost:5176             (React 19 管理端)
Open WebUI     → http://localhost:3090
Ollama API     → http://localhost:11434
vLLM API       → http://localhost:3080/v1
Grafana        → http://localhost:9091             (admin/admin)
Traefik        → http://localhost:18090            (Dashboard)
Adminer        → http://localhost:18080
PostgreSQL     → localhost:5432                    (admin/admin123/studio)
Redis          → localhost:6379
Qdrant HTTP    → http://localhost:6334
Prometheus     → http://localhost:9090
```

---

## 五、基础设施部署

> 📦 `compose.yml` 已配置全部基础设施（db/redis/qdrant），无需手动编写。以下是各服务手动部署参考（了解即可）。

### 5.1 PostgreSQL 16

compose.yml 中对应 service 名 `db`，环境变量来自 `.env` 文件。

**验证**：`docker exec ai-fullstack-platform-db-1 psql -U admin -d studio`

**备份恢复**：
```bash
docker exec ai-fullstack-platform-db-1 pg_dump -U admin studio > backup.sql       # 备份
docker exec -i ai-fullstack-platform-db-1 psql -U admin -d studio < backup.sql    # 恢复
```

> ⚠️ 生产必改 `.env` 中密码，数据在 Docker volume `app-db-data` 中。

### 5.2 Redis 7

**验证**：`docker exec ai-fullstack-platform-redis-1 redis-cli ping` → PONG

> ⚠️ 默认无密码，公网暴露前在 compose.yml 加 `command: redis-server --requirepass 密码`。

### 5.3 Qdrant 向量数据库

**验证**：`curl http://localhost:6334/collections`

---

## 六、监控部署

> 📦 `compose.yml` 已配置全部监控服务（prometheus/alertmanager/grafana），自动采集指标。以下是各服务手动部署参考。

### 6.1 Prometheus

**访问**：`http://localhost:9090`

### 6.2 Alertmanager

**访问**：`http://localhost:9093`

### 6.3 Grafana

**访问**：`http://localhost:9091`，默认 admin/admin。
**首次配置**：Data Sources → Prometheus → URL: `http://prometheus:9090`。

---

## 七、AI 服务部署

> 📦 `compose.yml` 已配置 Ollama/vLLM/Open WebUI。以下是手动部署和模型管理参考。

### 7.1 Ollama ⭐（主力后端）

多模型并存，API 按名称切模型无需重启，空闲 5 分钟自动释放显存。

**拉模型**：

```bash
docker exec ollama ollama pull qwen2.5-coder:7b   # 代码 ~4.7GB
docker exec ollama ollama pull qwen2.5:7b          # 中文 ~4.7GB
docker exec ollama ollama pull llama3.1:8b         # 通用 ~4.9GB
docker exec ollama ollama pull qwen2.5:3b          # 轻量 ~2.0GB
docker exec ollama ollama list                      # 查看已安装
```

**API 调用**：

```bash
# OpenAI 兼容格式
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen2.5-coder:7b","messages":[{"role":"user","content":"你好"}]}'
```

**本地模型导入**：

```bash
cat > /tmp/Modelfile << 'EOF'
FROM /home/user/models/huggingface/models/qwen2
EOF
docker cp /tmp/Modelfile ollama:/tmp/Modelfile
docker exec ollama ollama create qwen2-local:1.5b -f /tmp/Modelfile
```

### 7.2 vLLM（可选，高并发场景）

> 💡 Linux 上无需 UVA 补丁，直接用官方 `vllm/vllm-openai:latest` 镜像。日常用 Ollama 即可。

**验证**：

```bash
curl http://localhost:3080/health          # 200 OK
curl http://localhost:3080/v1/models       # 模型列表
```

**更换模型**：修改 `--model` 路径 → `docker compose up -d --force-recreate vllm`。

### 7.3 Open WebUI

> compose.yml 已配置，绑定 Ollama (`OLLAMA_BASE_URL: http://ollama:11434`)，访问 `http://localhost:3090`。

---

## 八、vLLM vs Ollama 选型

| 维度 | Ollama ⭐ | vLLM |
|---|---|---|
| 模型管理 | 多模型热切换 | 单模型，换即重启 |
| 上手 | 简单 | 中等 |
| 性能 | 中等 | 高(PagedAttention) |
| 显存 | 按需加载 | 常驻 |
| 场景 | 日常开发/对外 API | 高并发单模型 |

**策略**：日常用 Ollama(11434)，高并发开 vLLM(3080)，Open WebUI(3090) 统一界面。

---

## 九、对外映射

| 方案 | 适用 | 要点 |
|---|---|---|
| 路由器转发 | 有公网 IP | ⚠️ Ollama/WebUI 无认证 |
| Nginx 反向代理 | 有域名 | SSL + HTTP Basic Auth |
| Cloudflare Tunnel | 无公网 IP | 免费，需域名 |

**客户端调用示例**：

```python
from openai import OpenAI
client = OpenAI(base_url="https://你的地址/v1", api_key="not-needed")
response = client.chat.completions.create(
    model="qwen2.5-coder:7b",
    messages=[{"role": "user", "content": "写冒泡排序"}]
)
```

Nginx 配置详见 [附录 A](#附录-anginx-反向代理配置)。

---

## 十、常用操作

```bash
# 核心操作
docker compose up -d                          # 启动所有服务
docker compose down                           # 停止所有服务
docker compose build                          # 重新构建所有镜像
docker compose restart <service>              # 重启单个服务（如 backend）
docker compose logs -f backend                # 实时日志

# 数据库
docker compose exec db psql -U admin -d studio                  # 进 PostgreSQL
docker compose exec db pg_dump -U admin studio > backup.sql     # 备份

# AI 模型管理
docker compose exec ollama ollama list          # 已安装模型
docker compose exec ollama ollama pull qwen2.5-coder:7b  # 下载新模型

# 系统监控
docker ps                                       # 容器状态
nvidia-smi                                      # GPU 占用
docker stats                                    # 资源使用
sudo systemctl restart docker                   # 重启 Docker 引擎
```

---

## 十一、踩坑索引

### Docker 通用

| 现象 | 原因 | 解决 |
|---|---|---|
| `docker compose up -d` 报端口冲突 | 端口已被占用 | `lsof -i :端口号` 查占用进程 |
| prestart 失败 | 数据库未就绪 | 等 db 健康检查通过后重试 |
| backend 启动后立即退出 | 数据库连接失败 | 检查 `.env` 中 `POSTGRES_SERVER=db`（非 localhost） |

### AI 服务

| 现象 | 原因 | 解决 |
|---|---|---|
| vLLM 无法下载模型 | 容器内 HTTPS 被墙 | `HF_HUB_OFFLINE=1` |
| Ollama 下载慢 | 国内网络 | 配代理或本地导入 |
| Ollama 显存不足 | 同时加载太多 | 缩短 `keepalive` |
| WebUI 看不到新模型 | 未刷新 | `docker compose restart open-webui` |

### 基础设施

| 服务 | 现象 | 解决 |
|---|---|---|
| PostgreSQL | 密码忘记 | 进容器 `psql -U admin` 执行 ALTER |
| Redis | 外部连不上 | `bind 0.0.0.0` |
| Grafana | 登录失败 | 默认 admin/admin |

---

## 附录 A：Nginx 反向代理配置

```nginx
server {
    listen 443 ssl;
    server_name ai.yourdomain.com;
    ssl_certificate     /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    auth_basic "AI API";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location /ollama/  { proxy_pass http://127.0.0.1:11434/; proxy_read_timeout 300s; }
    location /vllm/    { proxy_pass http://127.0.0.1:3080/;  proxy_read_timeout 300s; }
    location /grafana/ { proxy_pass http://127.0.0.1:9091/; }
    location /         { proxy_pass http://127.0.0.1:3090; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade"; }
}
```

### Cloudflare Tunnel

```yaml
# ~/.cloudflared/config.yml
tunnel: <tunnel-id>
credentials-file: /root/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: ai.yourdomain.com
    service: http://localhost:3090
  - hostname: api.yourdomain.com
    service: http://localhost:11434
  - service: http_status:404
```

---

## 附录 B：双系统共享数据（Windows + Linux）

项目代码放 **NTFS 分区**，Docker 数据（镜像层+数据库+缓存）用 ext4 loopback 镜像共享：

```
D:\app\Docker\docker-volumes.img (70GB ext4)        ← WSL2: /mnt/d/app/Docker/
         ↕ 同一个文件，切换系统自动挂载 ↕
Linux: /run/media/用户名/Software/app/Docker/docker-volumes.img

挂载到 → /mnt/dockervol/
           ├── docker/         ← Docker data-root
           ├── postgres/       ← 数据库数据
           ├── redis/          ← 缓存
           ├── qdrant/         ← 向量库
           └── ...             ← 其他服务数据
```

### WSL2 启动
```bash
wsl -d Ubuntu-24.04
sudo mount -o loop /mnt/d/app/Docker/docker-volumes.img /mnt/dockervol
sudo dockerd &> /tmp/dockerd.log &
cd /mnt/d/code/ai-fullstack-platform
docker compose up -d
```

### 双系统 Linux 启动
```bash
sudo mount -o loop /run/media/用户名/Software/app/Docker/docker-volumes.img /mnt/dockervol
sudo systemctl start docker
cd /run/media/用户名/Software/code/ai-fullstack-platform
docker compose up -d
```

> 📖 完整双系统架构细节 → [`多系统共享Docker架构.md`](../development/多系统共享Docker架构.md)
