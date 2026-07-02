# AI Fullstack Platform — 生产部署指南

本项目支持通过 Docker Compose 部署到远程服务器，使用 Traefik 处理 HTTPS 反向代理。

也可以使用 GitHub Actions 实现 CI/CD 自动部署。

## 准备工作

* 准备一台远程服务器（Linux 推荐）。
* 将域名 DNS 解析到服务器 IP。
* 配置通配符子域名，例如 `*.ai-platform.example.com`，方便访问不同服务：
  `dashboard.ai-platform.example.com`、`api.ai-platform.example.com`、`traefik.ai-platform.example.com`、`adminer.ai-platform.example.com` 等。
* 在远程服务器上安装 [Docker Engine](https://docs.docker.com/engine/install/)（非 Docker Desktop）。

> **Windows 用户**: 生产部署推荐 Linux 服务器。本地开发可在 Windows 上通过
> [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/)
> （启用 WSL2 后端）运行大部分服务。部分服务限制见下方
> [Windows 兼容性说明](#windows-兼容性说明)。

## 公共 Traefik 代理

需要先部署一个 Traefik 反向代理来处理 HTTPS 证书。

以下步骤只需执行一次。

### Traefik Docker Compose

* 在远程服务器创建 Traefik 目录：

```bash
mkdir -p /root/code/traefik-public/
```

将本地的 Traefik Compose 文件上传到服务器：

```bash
rsync -a compose.traefik.yml root@你的服务器:/root/code/traefik-public/
```

### Traefik 公共网络

创建一个名为 `traefik-public` 的 Docker 公共网络，用于 Traefik 与各服务通信：

```bash
docker network create traefik-public
```

这样只需一个 Traefik 代理处理所有外部 HTTP/HTTPS 请求，后面可挂载多个不同域名的项目栈。

### Traefik 环境变量

在远程服务器设置以下环境变量：

```bash
# HTTP Basic Auth 用户名
export USERNAME=admin

# HTTP Basic Auth 密码
export PASSWORD=修改为你的密码

# 生成加密后的密码哈希
export HASHED_PASSWORD=$(openssl passwd -apr1 $PASSWORD)
# 验证：echo $HASHED_PASSWORD

# 你的域名
export DOMAIN=ai-platform.example.com

# Let's Encrypt 邮箱（不能用 example.com）
export EMAIL=admin@你的域名.com
```

### 启动 Traefik

```bash
cd /root/code/traefik-public/
docker compose -f compose.traefik.yml up -d
```

---

## 部署项目代码

### 上传代码

```bash
rsync -av --filter=":- .gitignore" ./ root@你的服务器:/root/code/app/
```

> `--filter=":- .gitignore"` 让 rsync 遵循 gitignore 规则，排除虚拟环境等文件。

### 生成密钥

`.env` 中默认值为 `changethis` 的变量都需要替换。用以下命令生成安全密钥：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

将输出粘贴到对应变量的位置，每个密钥分别生成。

### 必需环境变量

```bash
# 环境标识（生产环境用 production）
export ENVIRONMENT=production

# 域名
export DOMAIN=ai-platform.example.com

# 数据库密码（修改默认值）
export POSTGRES_PASSWORD="你生成的密钥"

# JWT 签名密钥
export SECRET_KEY="你生成的密钥"

# 初始管理员密码
export FIRST_SUPERUSER_PASSWORD="你生成的密钥"

# CORS 允许的域名
export BACKEND_CORS_ORIGINS="https://dashboard.${DOMAIN?变量未设置},https://api.${DOMAIN?变量未设置}"
```

### 其他可选环境变量

| 变量 | 说明 |
|------|------|
| `PROJECT_NAME` | 项目名称，用于 API 文档和邮件 |
| `STACK_NAME` | Docker Compose 栈名称，生产和预发布环境需区分 |
| `BACKEND_CORS_ORIGINS` | 逗号分隔的 CORS 允许域名列表 |
| `FIRST_SUPERUSER` | 初始管理员邮箱 |
| `SMTP_HOST` | SMTP 服务器地址 |
| `SMTP_USER` | SMTP 用户名 |
| `SMTP_PASSWORD` | SMTP 密码 |
| `EMAILS_FROM_EMAIL` | 发件人邮箱 |
| `POSTGRES_SERVER` | 数据库地址（Docker 内默认为 `db`） |
| `POSTGRES_PORT` | 数据库端口 |
| `POSTGRES_USER` | 数据库用户名 |
| `POSTGRES_DB` | 数据库名称（默认 `app`） |
| `SENTRY_DSN` | Sentry DSN（如使用） |

### AI 模型 API 密钥

设置以下环境变量以启用第三方 API 模型（本地模型不可用时自动回退）：

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export DEEPSEEK_API_KEY="sk-..."
export AZURE_OPENAI_API_KEY="..."
export REPLICATE_API_KEY="r8_..."
export ZHIPU_API_KEY="..."
export QWEN_API_KEY="..."
```

### AI 模型调度配置

```bash
# 模型存储目录（存放下载的模型权重）
export MODELS_DIR="/data/models"

# 优先本地模型（纯 API 部署可设为 false）
export MODEL_PREFER_LOCAL="true"

# 模型请求超时（秒）
export MODEL_REQUEST_TIMEOUT="30"

# 最大重试次数
export MODEL_MAX_RETRIES="2"

# 启用回退链
export MODEL_FALLBACK_ENABLED="true"

# 自动优化（每周自动评估模型性能）
export AUTO_OPTIMIZE_ENABLED="true"
export AUTO_OPTIMIZE_INTERVAL_HOURS="24"
```

---

## Standalone 独立部署模式

不依赖 Docker，适用于单机服务器场景：

```bash
# 1. 复制代码到服务器
rsync -av ./ root@你的服务器:/opt/ai-platform/

# 2. 安装 Python 依赖
cd /opt/ai-platform
uv sync

# 3. 配置环境
cp .env.standalone .env
# 编辑 .env 设置你的参数

# 4. 初始化并启动
python standalone.py --init
python standalone.py --start
```

Standalone 模式特性：
- **进程守护**：子进程崩溃自动重启
- **Web 管理面板**：内置仪表盘
- **远程唤醒 (WOL)**：局域网远程唤醒
- **DDNS 动态域名**：阿里云 DNS 自动更新
- **无需 Docker / PostgreSQL**：默认使用 SQLite

后端访问地址：`http://你的服务器IP:18000`

### 修改绑定端口

默认端口 `18000`，如需修改：

```bash
export STANDALONE_BIND_PORT="9000"
```

---

## Docker Compose 部署

配置好环境变量后：

```bash
cd /root/code/app/
docker compose -f compose.yml build
docker compose -f compose.yml up -d
```

> 生产环境不要使用 `compose.override.yml`，因此显式指定 `compose.yml`。

---

## 持续部署 (CD)

通过 GitHub Actions 实现自动部署，已内置 `staging` 和 `production` 两套环境。

### 安装 GitHub Actions Runner

在远程服务器上：

```bash
# 创建 github 用户
sudo adduser github

# 添加 Docker 权限
sudo usermod -aG docker github

# 切换到 github 用户
sudo su - github
cd
```

按照 [官方文档](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners#adding-a-self-hosted-runner-to-a-repository) 安装自托管 Runner，添加环境标签（如 `production`）。

安装为系统服务（切回 root 用户）：

```bash
exit
sudo su
cd /home/github/actions-runner

# 安装为服务
./svc.sh install github

# 启动
./svc.sh start

# 查看状态
./svc.sh status
```

详见：[配置自托管 Runner 为服务](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/configuring-the-self-hosted-runner-application-as-a-service)

### 配置 GitHub Environments

在仓库的 **Settings → Environments** 创建 `staging` 和 `production` 环境，可设置审批规则。

### 配置环境密钥

在对应 Environment 的 **Environment secrets** 中设置：

| 密钥 | 说明 |
|------|------|
| `DOMAIN_PRODUCTION` | 生产域名 |
| `DOMAIN_STAGING` | 预发布域名 |
| `STACK_NAME_PRODUCTION` | 生产栈名 |
| `STACK_NAME_STAGING` | 预发布栈名 |
| `EMAILS_FROM_EMAIL` | 发件人邮箱 |
| `FIRST_SUPERUSER` | 管理员邮箱 |
| `FIRST_SUPERUSER_PASSWORD` | 管理员密码 |
| `POSTGRES_PASSWORD` | 数据库密码 |
| `SECRET_KEY` | JWT 签名密钥 |
| `LATEST_CHANGES` | latest-changes 工具 Token |
| `SMOKESHOW_AUTH_KEY` | Smokeshow 代码覆盖率密钥 |

### 部署工作流

`.github/workflows` 目录内置了两个工作流：

- **staging**：推送到 `master` 分支后自动触发
- **production**：发布 Release 后自动触发

---

## GitHub Actions 专用环境变量

| 变量 | 说明 |
|------|------|
| `LATEST_CHANGES` | [latest-changes](https://github.com/tiangolo/latest-changes) 工具的个人访问令牌 |
| `SMOKESHOW_AUTH_KEY` | [Smokeshow](https://github.com/samuelcolvin/smokeshow) 代码覆盖率密钥（免费） |

---

---

## Docker 镜像说明

项目使用以下 Docker 镜像，导出文件位于 `docker-images/` 目录。

### 基础服务镜像 (`infra-images-latest.tar`)

| 镜像 | 大小 | 作用 |
|------|------|------|
| `postgres:16-alpine` | 420M | PostgreSQL 关系型数据库，存储项目/用户/会话/视频等核心数据 |
| `redis:7-alpine` | 58M | Redis 内存缓存，支持分布式限流、会话缓存、Celery 任务队列 |
| `qdrant/qdrant:latest` | 270M | Qdrant 向量数据库，存储知识库 embedding，支持语义搜索和 RAG |

### AI 模型服务镜像

| 镜像 | 大小 | 作用 |
|------|------|------|
| `ollama/ollama:latest` | 8G | Ollama 本地大模型推理引擎，提供 llama3.1/qwen2.5-coder/gemma2 等模型服务 |
| `vllm/vllm-openai:latest` | 30G | vLLM 高性能推理引擎，提供 OpenAI 兼容 API，支持 GPU 加速 |
| `ghcr.io/open-webui/open-webui:main` | 7G | Open WebUI 聊天界面，连接 Ollama/vLLM 提供 Web 对话和模型管理 |

### 监控服务镜像 (`monitoring-images-latest.tar`)

| 镜像 | 大小 | 作用 |
|------|------|------|
| `prom/prometheus:latest` | 359M | Prometheus 时序监控，采集 HTTP/模型/系统/容器健康指标 |
| `prom/alertmanager:latest` | 121M | Alertmanager 告警管理，支持企业微信/钉钉/邮件多渠道通知 |
| `grafana/grafana:latest` | 1.6G | Grafana 可视化仪表盘，预置 AI Platform 概览面板 |

### 镜像导入

```bash
# 导入基础服务
docker load -i docker-images/infra-images-latest.tar

# 导入 AI 模型
docker load -i docker-images/ollama-latest.tar
docker load -i docker-images/vllm-openai-latest.tar
docker load -i docker-images/open-webui-main.tar

# 导入监控栈
docker load -i docker-images/monitoring-images-latest.tar
```

---

## Windows 兼容性说明

### 可直接运行

| 服务 | 状态 | 说明 |
|------|------|------|
| 后端 (FastAPI) | ✅ 完全支持 | Python 跨平台，直接 `python -m uvicorn` 或通过 Docker |
| PostgreSQL | ✅ Docker | Docker Desktop + WSL2 完美支持 |
| Redis | ✅ Docker | Docker Desktop + WSL2 完美支持 |
| Qdrant | ✅ Docker | Docker Desktop + WSL2 完美支持 |
| Ollama | ✅ 原生 | [Windows 原生安装包](https://ollama.com/download/windows)，支持 GPU |
| Open WebUI | ✅ Docker | Docker Desktop + WSL2 支持 |
| Prometheus | ✅ Docker | Docker Desktop + WSL2 支持 |
| Grafana | ✅ Docker | Docker Desktop + WSL2 支持 |
| Alertmanager | ✅ Docker | Docker Desktop + WSL2 支持 |

### 需要 Linux 环境

| 服务 | 状态 | 说明 |
|------|------|------|
| vLLM | ❌ 仅 Linux | 依赖 CUDA 内核驱动和 Linux 内核特性，**不支持 Windows/Docker Desktop** |

> **替代方案**: vLLM 不可用时，Ollama 提供 OpenAI 兼容 API（`http://localhost:11434/v1`），可替代 vLLM 作为推理后端。

### Windows 本地开发最小配置

```bash
# 1. 安装 Docker Desktop (启用 WSL2)
# 2. 安装 Ollama for Windows
# 3. 启动基础服务
docker compose -f compose.yml up -d db redis qdrant

# 4. 启动后端 (无 vLLM)
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 18000

# 5. (可选) 启动 Open WebUI
docker compose -f /data/ai-platform/compose/docker-compose.yml up -d ollama open-webui

# 6. (可选) 启动监控栈
docker compose -f deploy/monitoring/docker-compose.monitoring.yml up -d
```

### 后端 Windows 适配说明

后端部分模块在非 Linux 环境下会自动降级：

| 模块 | Windows 行为 |
|------|-------------|
| `psutil` 系统指标 | ✅ 完全支持 |
| GPU 监控 | ❌ 跳过（无 nvidia-smi） |
| Docker 容器健康检测 | ❌ 跳过（Docker Desktop 需手动配置） |
| AutoCLI 命令行 | ⚠️ 部分命令不可用（bash shell 脚本） |
| vLLM 模型 | ❌ 不可用（需 Linux 环境） |

---

## 监控栈部署

项目内置 Prometheus + Alertmanager + Grafana 监控栈。

### 快速启动

```bash
cd deploy/monitoring

# 配置告警通知（可选）
cp .env .env.local
# 编辑 .env.local 填入 Webhook URL / SMTP

# 启动
docker compose -f docker-compose.monitoring.yml up -d
```

### 访问地址

| 服务 | 地址 | 默认账号 |
|------|------|----------|
| Prometheus | http://localhost:9090 | 无认证 |
| Grafana | http://localhost:3100 | admin / admin |
| Alertmanager | http://localhost:9093 | 无认证 |

### 告警规则

| 告警 | 级别 | 条件 |
|------|------|------|
| BackendDown | 🚨 critical | 后端不可达 > 1分钟 |
| BackendHigh5xx | ⚠️ warning | 5xx 错误率 > 10% (5分钟) |
| BackendHighLatency | ⚠️ warning | P95 延迟 > 2秒 |
| ContainerUnhealthy | 🚨 critical | 容器不健康 > 2分钟 |
| VllmStartupTimeout | ⚠️ warning | vLLM 启动超 5 分钟 |
| ModelCallErrorRate | ⚠️ warning | 模型调用错误率 > 20% (5分钟) |
| HighMemoryUsage | ⚠️ warning | 内存 > 16GB |

### 告警通知渠道

在 `.env` 中配置：

```bash
# 企业微信机器人
WECHAT_WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx

# 钉钉机器人
DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=xxx

# 邮件通知
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=alert@example.com
SMTP_PASSWORD=xxx
ALERT_EMAIL_TO=admin@example.com
```

---

## 访问地址

将 `ai-platform.example.com` 替换为你的域名。

### 主 Traefik 面板

`https://traefik.ai-platform.example.com`

### 生产环境

| 服务 | 地址 |
|------|------|
| 前端 | `https://dashboard.ai-platform.example.com` |
| API 文档 | `https://api.ai-platform.example.com/docs` |
| API 基础路径 | `https://api.ai-platform.example.com` |
| 数据库管理 | `https://adminer.ai-platform.example.com` |

### 预发布环境

| 服务 | 地址 |
|------|------|
| 前端 | `https://dashboard.staging.ai-platform.example.com` |
| API 文档 | `https://api.staging.ai-platform.example.com/docs` |
| API 基础路径 | `https://api.staging.ai-platform.example.com` |
| 数据库管理 | `https://adminer.staging.ai-platform.example.com` |
