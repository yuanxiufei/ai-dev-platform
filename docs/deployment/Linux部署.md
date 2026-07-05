# 全栈 AI 平台部署指南 —— Linux

> 在原生 Linux（Ubuntu/Debian/CentOS）上部署 9 容器全栈 AI 平台（PostgreSQL + Redis + Qdrant + Ollama + vLLM + Open WebUI + 监控栈），离线镜像一键导入。
>
> **📄 镜像来源与基础方案**：本文使用的所有 Docker 镜像及通用部署架构定义在 [`部署概览.md`](部署概览.md)（基础篇），请先阅读了解镜像清单和 Traefik/CI/CD/监控栈概览。

**适用人群**：Linux 服务器、双系统 Linux 用户、追求最佳性能的开发者。

**前置条件**：NVIDIA GPU 驱动已安装，了解 Docker 基本用法。

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
# 1. 进入目录（直接本地路径，不需要 wsl 命令）
cd /home/user/docker-images
# 或 cd /data/docker-images

# 2. 加载离线镜像
docker load -i infra-images-latest.tar          # PG + Redis + Qdrant
docker load -i monitoring-images-latest.tar     # Prometheus + Alertmanager + Grafana
docker load -i ollama-latest.tar
docker load -i vllm-openai-latest.tar           # 可选
docker load -i open-webui-main.tar

# 3. 创建网络 + 启动
docker network create backend 2>/dev/null
docker network create llm-net 2>/dev/null
docker compose up -d

# 4. 验证
docker ps
nvidia-smi
```

---

## 三、架构概览

```
┌────────────────────────────────────────────────────────┐
│                     Linux 宿主机                         │
│  :3090(WebUI) :11434(Ollama) :3080(vLLM)               │
│  :5432(PG) :6379(Redis) :6333(Qdrant) :9091(Grafana)  │
│                                                        │
│  ┌─────── llm-net ───────┐  ┌─────── backend ────────┐ │
│  │ ollama :11434         │  │ postgres :5432         │ │
│  │ vllm   :3080          │  │ redis    :6379         │ │
│  │ open-webui :8080      │  │ qdrant   :6333/4       │ │
│  └───────────────────────┘  │ prometheus :9090       │ │
│                              │ alertmanager :9093     │ │
│                              │ grafana :3000          │ │
│                              └────────────────────────┘ │
└────────────────────────────────────────────────────────┘
```

**网络隔离**：`llm-net`（AI 推理互访）+ `backend`（基础设施 + 监控）。

---

## 四、全部容器清单

### 基础设施（`backend` 网络）

| 服务 | 镜像 | 端口 | 默认凭证 | 用途 |
|---|---|---|---|---|
| PostgreSQL 16 | `postgres:16-alpine` | 5432 | admin/admin123/studio | 关系数据库 |
| Redis 7 | `redis:7-alpine` | 6379 | 无密码 | 缓存/队列 |
| Qdrant | `qdrant/qdrant:latest` | 6333/6334 | — | 向量数据库(RAG) |

### AI 服务（`llm-net` 网络）

| 服务 | 镜像 | 端口 | GPU | 用途 |
|---|---|---|---|---|
| **Ollama** ⭐ | `ollama/ollama:latest` | 11434 | ✅ | **主力**：多模型管理，API 热切换 |
| vLLM | `vllm/vllm-openai:latest` | 3080 | ✅ | 可选：单模型高并发。**Linux 无需 UVA patch** |
| Open WebUI | `ghcr.io/open-webui/open-webui:main` | 3090 | ❌ | AI 对话界面 |

### 监控（`backend` 网络）

| 服务 | 镜像 | 端口 | 凭证 |
|---|---|---|---|
| Prometheus | `prom/prometheus:latest` | 9090 | — |
| Alertmanager | `prom/alertmanager:latest` | 9093 | — |
| Grafana | `grafana/grafana:latest` | 9091 | admin/admin |

### 地址速查

```
Open WebUI     → http://localhost:3090
Ollama API     → http://localhost:11434
vLLM API       → http://localhost:3080/v1
Grafana        → http://localhost:9091    (admin/admin)
PostgreSQL     → localhost:5432           (admin/admin123/studio)
Redis          → localhost:6379
Qdrant HTTP    → http://localhost:6334
Prometheus     → http://localhost:9090
```

---

## 五、基础设施部署

### 5.1 PostgreSQL 16

```yaml
postgres:
  image: postgres:16-alpine
  container_name: postgres
  restart: unless-stopped
  environment:
    POSTGRES_USER: admin
    POSTGRES_PASSWORD: admin123
    POSTGRES_DB: studio
  ports:
    - "5432:5432"
  volumes:
    - pgdata:/var/lib/postgresql/data
  networks:
    - backend
```

**验证**：`docker exec -it postgres psql -U admin -d studio`

**备份恢复**：
```bash
docker exec postgres pg_dump -U admin studio > backup.sql      # 备份
docker exec -i postgres psql -U admin -d studio < backup.sql   # 恢复
```

> ⚠️ 生产必改密码，数据在 volume `pgdata` 中，删容器不丢数据。

### 5.2 Redis 7

```yaml
redis:
  image: redis:7-alpine
  container_name: redis
  restart: unless-stopped
  ports:
    - "6379:6379"
  volumes:
    - redisdata:/data
  networks:
    - backend
```

**验证**：`docker exec redis redis-cli ping` → PONG

> ⚠️ 默认无密码，公网暴露前加 `command: redis-server --requirepass 密码`。

### 5.3 Qdrant 向量数据库

```yaml
qdrant:
  image: qdrant/qdrant:latest
  container_name: qdrant
  restart: unless-stopped
  ports:
    - "6333:6333"    # gRPC
    - "6334:6334"    # HTTP REST
  volumes:
    - qdrantdata:/qdrant/storage
  networks:
    - backend
```

**验证**：`curl http://localhost:6334/collections`

### 5.4 Volume 声明

```yaml
volumes:
  pgdata:
  redisdata:
  qdrantdata:
  ollamadata:
  webuidata:
  promdata:
  amdata:
  grafanadata:
```

---

## 六、监控部署

### 6.1 Prometheus

```yaml
prometheus:
  image: prom/prometheus:latest
  container_name: prometheus
  restart: unless-stopped
  ports:
    - "9090:9090"
  volumes:
    - promdata:/prometheus
  networks:
    - backend
```

### 6.2 Alertmanager

```yaml
alertmanager:
  image: prom/alertmanager:latest
  container_name: alertmanager
  restart: unless-stopped
  ports:
    - "9093:9093"
  volumes:
    - amdata:/alertmanager
  networks:
    - backend
```

### 6.3 Grafana

```yaml
grafana:
  image: grafana/grafana:latest
  container_name: grafana
  restart: unless-stopped
  depends_on:
    - prometheus
  ports:
    - "9091:3000"
  volumes:
    - grafanadata:/var/lib/grafana
  environment:
    GF_SECURITY_ADMIN_USER: admin
    GF_SECURITY_ADMIN_PASSWORD: admin
  networks:
    - backend
```

**首次配置**：打开 `http://localhost:9091`，admin/admin → Data Sources → Prometheus → URL: `http://prometheus:9090`。

---

## 七、AI 服务部署

### 7.1 Ollama ⭐（主力后端）

多模型并存，API 按名称切模型无需重启，空闲 5 分钟自动释放显存。

```yaml
ollama:
  image: ollama/ollama:latest
  container_name: ollama
  restart: unless-stopped
  ports:
    - "11434:11434"
  volumes:
    - ollamadata:/root/.ollama
  networks:
    - llm-net
  runtime: nvidia
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
```

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

### 7.2 vLLM（可选，Linux 专属优势）

> 💡 仅高并发(100+ QPS)场景需要。日常用 Ollama 即可。

**Linux 上无需 UVA 补丁**！`vllm_entrypoint.sh` 是 WSL2 特有的 workaround，原生 Linux 上直接用官方 vLLM 镜像：

```yaml
vllm:
  image: vllm/vllm-openai:latest
  container_name: vllm
  restart: unless-stopped
  runtime: nvidia
  ports:
    - "3080:3080"
  networks:
    - llm-net
  # entrypoint: ["/vllm_entrypoint.sh"]  ← Linux 不！需！要！
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
    - HF_HUB_OFFLINE=1
    - TRANSFORMERS_OFFLINE=1
  volumes:
    - /home/user/models:/root/.cache/huggingface:ro
  command:
    - "--model"
    - "/root/.cache/huggingface/models/qwen2"
    - "--port"
    - "3080"
    - "--host"
    - "0.0.0.0"
```

**验证**：

```bash
curl http://localhost:3080/health          # 200 OK
curl http://localhost:3080/v1/models       # 模型列表
```

**更换模型**：修改 `--model` 路径 → `docker compose up -d --force-recreate vllm`。

### 7.3 Open WebUI

```yaml
open-webui:
  image: ghcr.io/open-webui/open-webui:main
  container_name: open-webui
  restart: unless-stopped
  depends_on:
    - ollama
  ports:
    - "3090:8080"
  volumes:
    - webuidata:/app/backend/data
  environment:
    OLLAMA_BASE_URL: http://ollama:11434
    OPENAI_API_BASE_URLS: http://vllm:3080/v1
  networks:
    - llm-net
```

> Open WebUI 已配置 `RAG_EMBEDDING_ENGINE=ollama`，无需额外配置即可启动。

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
docker ps                                    # 查看状态
docker logs -f ollama                        # 实时日志
docker compose restart open-webui            # 重启单个
docker compose down && docker compose up -d  # 全部重建
docker exec -it postgres psql -U admin       # 进数据库
docker exec ollama ollama list               # 已安装模型
docker exec ollama ollama pull 模型名          # 下载新模型
nvidia-smi                                    # GPU 占用
sudo systemctl restart docker                 # 重启 Docker
```

---

## 十一、踩坑索引

### Docker 通用

| 现象 | 原因 | 解决 |
|---|---|---|
| postgres/redis 启动崩溃 | 非 nvidia 容器走 nvidia runtime | 去掉 `default-runtime: nvidia` 或不使用它 |
| `deploy.resources...devices` 不生效 | Swarm 语法 | 改用 `runtime: nvidia` |
| 3090 无响应 | 容器名冲突 | `docker compose down --remove-orphans` |

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

把镜像/model/compose 放 **NTFS 分区**，两个系统共用：

```
D:\docker-images\          ← Windows
    ├── compose.yml
    ├── *.tar
    ├── models\
    └── docker-data\

/mnt/d/docker-images/      ← Linux 挂载后
```

### 挂载 NTFS 分区

```bash
# 查看 NTFS 分区
sudo fdisk -l | grep NTFS

# 编辑 /etc/fstab 自动挂载
UUID=你的NTFS分区UUID  /mnt/d  ntfs-3g  defaults,uid=1000,gid=1000,umask=022  0  0

# 手动挂载
sudo mount -t ntfs-3g /dev/nvme0n1p4 /mnt/d
```

### 注意事项

| 项目 | 说明 |
|---|---|
| docker load | 每个系统各执行一次（镜像在 docker 内部独立存储） |
| 模型文件 | 用 bind mount 共享：`/mnt/d/docker-images/models:/root/.cache/huggingface:ro` |
| Docker volumes | `pgdata` 等命名卷不互通，跨系统共享改用 bind mount |
| 换行符 | `git config --global core.autocrlf input` 防 CRLF 污染 |
| 符号链接 | NTFS 不支持，模型目录只能用实体文件 |
