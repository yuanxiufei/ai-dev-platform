# 全栈 AI 平台部署指南 —— Windows

> 在 Windows 上部署 9 容器全栈 AI 平台（PostgreSQL + Redis + Qdrant + Ollama + vLLM + Open WebUI + 监控栈），离线镜像一键导入。
>
> **📄 镜像来源与基础方案**：本文使用的所有 Docker 镜像及通用部署架构定义在 [`部署概览.md`](部署概览.md)（基础篇），请先阅读了解镜像清单和 Traefik/CI/CD/监控栈概览。

**适用人群**：Windows 10/11 用户，有 NVIDIA GPU（A5000 或同等），日常开发 + AI 推理。

**前置条件**：了解 Docker 基本用法，GPU 驱动已安装。

---

## 〇、Windows 部署二选一

| 方案 | 适用场景 | 性能 | GPU 支持 | 复杂度 |
|---|---|---|---|---|
| **WSL2** (本文主打) | 需要完整 Linux 环境 | 中等（9P 文件 IO 有损） | ✅ 手动安装 nvidia-toolkit | 中 |
| **Docker Desktop** | 图形化管理 | 中等（WSL2/Hyper-V 后端） | ✅ 内置 GPU | 低 |

> 💡 **已经装了 WSL2 + Ubuntu → 用方案 A**。不想碰命令行 → 用方案 B（跳到 [附录 A：Docker Desktop 快速部署](#附录-adocker-desktop-快速部署)）。

### 两方案差异速查

| 维度 | WSL2 | Docker Desktop |
|---|---|---|
| 安装 Docker | `apt install docker.io`（WSL 内） | 下载 exe 安装包 |
| 启动 Docker | 手动 `sudo dockerd &` | 自动（系统服务） |
| 命令行 | `wsl -d Ubuntu-24.04` | PowerShell / CMD |
| 路径前缀 | `/mnt/d/docker-images` | `D:\docker-images` |
| daemon.json | `/etc/docker/daemon.json` | `%USERPROFILE%\.docker\daemon.json` |
| GPU 配置 | 手动安装 nvidia-container-toolkit | GUI 勾选启用 |
| vLLM UVA | ❌ 需 patch（`vllm_entrypoint.sh`） | ❌ 同样需 patch |
| 文件性能 | ext4 内最快，NTFS 挂载较慢 | 良好 |

---

## 一、WSL2 环境准备

### 1.1 硬件与环境

| 项 | 典型值 |
|---|---|
| 操作系统 | Windows 10/11 + WSL2（Ubuntu-24.04） |
| GPU | NVIDIA RTX A5000 / 23GB VRAM / CUDA 13.2 |
| Docker | 29.1.3，data-root `/var/lib/docker`（WSL ext4） |
| nvidia-container-toolkit | 1.19+ |
| 默认 Runtime | `runc`，GPU 容器显式指定 `runtime: nvidia` |

### 1.2 安装 Docker（WSL 内执行）

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# 重新登录 WSL 生效
```

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
```

### 1.4 验证

```bash
nvidia-smi                  # 能显示 GPU
sudo nvidia-ctk --version   # 1.19.x
```

### 1.5 daemon.json

> ⚠️ **不要设 `"default-runtime": "nvidia"`** — postgres/redis 等非 GPU 容器会崩溃。

```json
{
  "data-root": "/var/lib/docker",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
```

保存到 `/etc/docker/daemon.json`，启动 dockerd：

```bash
sudo dockerd &> /tmp/dockerd.log &

# 报 exit code 1（旧 PID 残留）时：
sudo kill $(pgrep dockerd) 2>/dev/null
sudo rm -f /var/run/docker.pid
sudo dockerd &> /tmp/dockerd.log &
```

---

## 二、快速部署（WSL2）

```bash
# 1. 进入 WSL
wsl -d Ubuntu-24.04

# 2. 启动 Docker（每次重启 WSL 后执行一次）
sudo dockerd &> /tmp/dockerd.log &

# 3. 进入项目目录（假设镜像在 D 盘）
cd /mnt/d/docker-images

# 4. 加载离线镜像
docker load -i infra-images-latest.tar          # PG + Redis + Qdrant
docker load -i monitoring-images-latest.tar     # Prometheus + Alertmanager + Grafana
docker load -i ollama-latest.tar
docker load -i vllm-openai-latest.tar           # 可选
docker load -i open-webui-main.tar

# 5. 创建网络 + 启动
docker network create backend 2>/dev/null
docker network create llm-net 2>/dev/null
docker compose up -d

# 6. 验证
docker ps
```

---

## 三、架构概览

```
┌────────────────────────────────────────────────────────┐
│                     Windows 宿主机                       │
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
| vLLM | `vllm/vllm-openai:latest` | 3080 | ✅ | 可选：单模型高并发 |
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
FROM /mnt/d/app/LLM/models/huggingface/models/qwen2
EOF
docker cp /tmp/Modelfile ollama:/tmp/Modelfile
docker exec ollama ollama create qwen2-local:1.5b -f /tmp/Modelfile
```

### 7.2 vLLM（可选）

> 💡 仅高并发(100+ QPS)场景需要。WSL2 需 `vllm_entrypoint.sh` 补丁（见 [附录 B](#附录-bvllm-完整配置-wsl2)）。

```bash
# 验证
curl http://localhost:3080/health          # 200 OK
curl http://localhost:3080/v1/models
```

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

---

## 八、vLLM vs Ollama 选型

| 维度 | Ollama ⭐ | vLLM |
|---|---|---|
| 模型管理 | 多模型热切换 | 单模型，换即重启 |
| 上手 | 简单 | 需处理 UVA/网络/路径 |
| 性能 | 中等 | 高(PagedAttention) |
| 显存 | 按需加载 | 常驻 |
| 场景 | 日常开发/对外 API | 高并发单模型 |

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
sudo pkill dockerd                            # 停止 Docker
```

---

## 十一、踩坑索引（Windows 特有问题）

### Docker 通用

| 现象 | 原因 | 解决 |
|---|---|---|
| `executable file not found` | data-root 在 Windows 文件系统 | 用 `/var/lib/docker` |
| postgres/redis 启动崩溃 | `default-runtime: nvidia` | 去掉，只在 compose 指定 |
| dockerd exit code 1 | 旧 PID 残留 | `kill dockerd && rm /var/run/docker.pid` |
| 3090 无响应 | 容器名冲突 | `docker compose down --remove-orphans` |

### AI 服务

| 现象 | 原因 | 解决 |
|---|---|---|
| vLLM `is_uva_available() Check failed` | WSL2 不支持 UVA | `vllm_entrypoint.sh` patch |
| vLLM 无法下载模型 | 容器内 HTTPS 被墙 | `HF_HUB_OFFLINE=1` |
| vLLM 模型加载失败 | 9P 符号链接失效 | 用实体文件目录 |
| vLLM `Loading safetensors` 卡住 | 9P 读大文件慢 | 正常，约 20 秒 |
| Ollama 下载慢 | 国内网络 | 配代理或本地导入 |
| WebUI unhealthy | jq 脚本误判 | 不影响使用 |

### 基础设施

| 服务 | 现象 | 解决 |
|---|---|---|
| PostgreSQL | 密码忘记 | 进容器 `psql -U admin` 执行 ALTER |
| Redis | 外部连不上 | `bind 0.0.0.0` |
| Grafana | 登录失败 | 默认 admin/admin |

---

## 附录 A：Docker Desktop 快速部署

### A.1 安装 Docker Desktop

1. 下载 [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
2. 推荐选 **"Use WSL 2 instead of Hyper-V"**
3. 重启后确认右下角鲸鱼图标变绿

```powershell
docker --version
docker ps
```

### A.2 GPU 启用

1. Docker Desktop → Settings（⚙️）
2. → Resources → Advanced → **Enable GPU** ✅
3. Apply & Restart

```powershell
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

### A.3 daemon.json

在 Settings → Docker Engine 编辑：

```json
{
  "data-root": "D:\\docker-data",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "runtimeArgs": []
    }
  }
}
```

> ⚠️ Windows 路径用 `\\` 转义。

### A.4 PowerShell 部署

```powershell
cd D:\docker-images

docker load -i infra-images-latest.tar
docker load -i monitoring-images-latest.tar
docker load -i ollama-latest.tar
docker load -i vllm-openai-latest.tar
docker load -i open-webui-main.tar

docker network create backend 2>$null
docker network create llm-net 2>$null
docker compose up -d

docker ps
```

> 💡 `2>/dev/null` 在 PowerShell 中改为 `2>$null`。

### A.5 路径适配

```yaml
# ❌ WSL2 写法
volumes:
  - /mnt/d/app/LLM/models:/root/.cache/huggingface:ro

# ✅ Windows 写法
volumes:
  - D:\app\LLM\models\huggingface:/root/.cache/huggingface:ro
  # 或推荐：相对路径（跨平台兼容）
  - ./models/huggingface:/root/.cache/huggingface:ro
```

### A.6 Windows 特有注意事项

1. **换行符**：`.sh` 脚本必须 **LF** 换行，不可 CRLF。VS Code 右下角可切换。
2. **文件权限**：NTFS 无权限概念，容器内默认 `777`，敏感文件加 `:ro`。
3. **端口占用**：`netstat -ano | findstr :3090` 检查。
4. **防火墙**：首次启动可能弹窗，选"允许"。
5. **内存**：Settings → Resources → Advanced，建议 ≥16GB。

---

## 附录 B：vLLM 完整配置（WSL2）

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
  entrypoint: ["/vllm_entrypoint.sh"]
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
    - HF_HUB_OFFLINE=1
    - TRANSFORMERS_OFFLINE=1
  volumes:
    - /mnt/d/app/LLM/models/huggingface:/root/.cache/huggingface:ro
    - /mnt/d/docker-images/vllm_entrypoint.sh:/vllm_entrypoint.sh:ro
  command:
    - "--model"
    - "/root/.cache/huggingface/models/qwen2"
    - "--port"
    - "3080"
    - "--host"
    - "0.0.0.0"
```

**vllm_entrypoint.sh**：启动前 patch `is_uva_available()` 返回 True，绕过 WSL2 的 UVA 限制。

### 模型路径限制

```
D:\app\LLM\models\huggingface\models\
├── qwen2/              ✅ 实体文件目录
├── qwen/               ✅
├── Qwen3-0.6B/         ✅
├── models--...7B-Instruct/  ❌ 缺 shard
```

> ⚠️ WSL2 9P 文件系统不兼容 NTFS 符号链接，只认实体文件目录。

---

## 附录 C：Nginx 反向代理

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

---

## 附录 D：双系统共享数据（Windows + Linux）

把镜像/model/compose 放 **NTFS 分区**，Windows 直接访问，Linux 挂载后也能用：

```
D:\docker-images\          ← Windows
    ├── compose.yml
    ├── *.tar
    ├── models\
    └── docker-data\

/mnt/d/docker-images/      ← Linux 挂载后同一份
```

**关键注意事项**：

| 项目 | 说明 |
|---|---|
| docker load | 每个系统各执行一次（镜像在 docker 内部独立存储） |
| 模型文件 | 用 bind mount 共享，不 `docker cp` |
| Docker volumes | `pgdata` 等命名卷不互通，跨系统共享改用 bind mount |
| 换行符 | Git 在 Win 端可能改 CRLF → `git config --global core.autocrlf input` |
