# GPU 版 Docker 镜像构建指南

## 背景

后端 Docker 镜像需要同时支持 **RAG 语义搜索**（sentence-transformers）和 **GPU 模型推理**（torch/transformers/diffusers），依赖总量 ~3.5GB（185 个包，含 37 个 nvidia-* 包）。

本文档记录了从 CPU index → GPU版 torch 的最终方案及踩坑经验。

> 📄 **最终决策**：保留 GPU 版 torch（不用 CPU index）。镜像体积 ~3.5GB，首次构建 ~30 分钟（nvidia-* 大包下载慢），后续增量构建 ~30 秒（Docker 层缓存命中）。PyPI 镜像源使用腾讯云 `mirrors.cloud.tencent.com`。

---

## 架构设计

### 依赖分组策略

| 分组 | 位置 | 内容 | 说明 |
|------|------|------|------|
| `gpu` | `ai_models/pyproject.toml` `[dependency-groups]` | torch / transformers / diffusers / accelerate | GPU 模型推理依赖 |
| RAG | `backend/pyproject.toml` `[project] dependencies`（必装） | sentence-transformers / faiss-cpu / jieba / pypdf / markitdown | RAG 语义搜索，非可选组 |

### 两阶段 uv sync

```
Layer 1 (Step 14): uv sync --frozen --no-install-workspace --group gpu
  → 安装全部 185 个依赖包 (~30分钟，仅首次)
  → Docker 层缓存永久保留

Layer 2 (Step 18): uv sync --frozen --package app
  → 只安装 app 包本体（已编译好的 wheel）
  → 改代码重建时 ~30秒
```

---

## 踩坑记录

### 坑 1：BuildKit cache mount 不可用

**尝试**：使用 `RUN --mount=type=cache,target=/root/.cache/uv,id=uv-cache` 持久化 uv 下载缓存。

**现象**：
```
the --mount option requires BuildKit.
```

**原因**：WSL 中的 Docker 未安装 `buildx` 组件，`DOCKER_BUILDKIT=1` 环境变量也报同样错误。

**解决**：回退传统 Docker 层缓存。虽然无法跨构建持久化下载缓存，但 Docker 层缓存依然有效——只要 `pyproject.toml` / `uv.lock` 不变，依赖层命中缓存，不会重复下载。

### 坑 2：`--group gpu` + `--package app` 冲突

**错误信息**：
```
error: Group `gpu` is not defined in the project's `dependency-groups` table
```

**原因**：`gpu` 组定义在 `ai_models/pyproject.toml`（workspace 成员），不在 `backend/pyproject.toml`。`--package app` 限制了 uv 只在 backend 范围内查找。

**解决**：
```dockerfile
# ❌ 错误：--package app 限定了扫描范围
RUN uv sync --frozen --no-install-workspace --group gpu --package app

# ✅ 正确：不限定 range，uv 扫描全部 workspace 成员
RUN uv sync --frozen --no-install-workspace --group gpu
```

### 坑 3：第二次 uv sync 包依赖问题

**错误信息**：
```
Distribution not found at: file:///app/task_queue
```

**原因**：第二次 `uv sync` 使用 `--group gpu` 时，uv 试图解析 workspace 中所有成员，但 `task_queue` / `workers` 目录未 COPY 到镜像。

**解决**：第二次 `uv sync` 只需 `--package app`，因为依赖已在 Layer 1 装完：
```dockerfile
# Layer 2：只安装 app 包本身
RUN uv sync --frozen --package app
```

### 坑 4：国内镜像下载 nvidia-* 大包慢

**预期**：国内镜像 40MB/s，3.5GB 约 1.5 分钟。

**实际**：下载耗时 ~30 分钟。

**原因分析**：国内 PyPI 镜像（清华/阿里云/腾讯云 等）对大文件（torch 507MB、nvidia-cublas 403MB 等）通常没有本地缓存，实际在透传 NVIDIA 海外 CDN，受跨境带宽限制。小文件（普通 Python 包）走镜像缓存秒下，大文件走海外直连速度骤降。

**最终选择**：使用腾讯云镜像 `mirrors.cloud.tencent.com`（`ARG` 方式，可通过 `--build-arg` 切换）。清华镜像对 nvidia 大包同样没有本地缓存，且腾讯云网络链路更稳定。

**缓解措施**：
- `UV_HTTP_TIMEOUT=600` — 防止大包下载超时中断
- `UV_CONCURRENT_DOWNLOADS=8` — 8 路并行下载，网速差时能追回一些时间
- Docker 层缓存 — 只要下过一次，永久缓存

### 坑 5：DaoCloud 镜像站拉取 mailcatcher 403

**错误**：
```
unexpected status from HEAD request to https://docker.m.daocloud.io/v2/schickling/mailcatcher/manifests/latest: 403 Forbidden
```

**影响**：`mailcatcher`（开发邮件捕获）和依赖它的 `playwright`（E2E 测试）无法启动，连带阻塞了 4 个前端服务。

**解决**：跳过非核心服务启动：
```bash
docker compose -f compose.yml -f compose.override.yml up -d --scale mailcatcher=0 --scale playwright=0
```

---

## 最终 Dockerfile

```dockerfile
FROM python:3.12

ENV PYTHONUNBUFFERED=1

# ── 下载加速 ──
# PyPI 镜像源，可通过 --build-arg UV_INDEX_URL=... 切换
# 国内可选: https://mirrors.aliyun.com/pypi/simple/
# 清华（nvidia大包慢）: https://pypi.tuna.tsinghua.edu.cn/simple
# 官方（nvidia直连CDN）: https://pypi.org/simple/
ARG UV_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple/
ENV UV_INDEX_URL=${UV_INDEX_URL}
ENV UV_HTTP_TIMEOUT=600
ENV UV_CONCURRENT_DOWNLOADS=8
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN pip install uv -i ${UV_INDEX_URL}

WORKDIR /app/
ENV PATH="/app/.venv/bin:$PATH"

# Layer 1: 依赖（Docker 层缓存，仅 uv.lock/pyproject.toml 变更时重建）
COPY ./pyproject.toml /app/
COPY ./ai_models /app/ai_models
COPY ./backend/pyproject.toml ./backend/alembic.ini /app/backend/
COPY ./uv.lock /app/uv.lock
# gpu 组在 ai_models workspace 成员中定义，不要加 --package app
RUN uv sync --frozen --no-install-workspace --group gpu

# Layer 2: 源码（频繁变更，每次都重跑但秒级完成）
COPY ./backend/scripts /app/backend/scripts
COPY ./backend/app /app/backend/app
RUN uv sync --frozen --package app

WORKDIR /app/backend/

RUN addgroup --system app && adduser --system --group app
RUN chown -R app:app /app
USER app

CMD ["fastapi", "run", "--workers", "4", "app/main.py"]
```

---

## 构建命令

```bash
cd /mnt/d/code/ai-fullstack-platform

# 首次构建（~30分钟，下载 ~3.5GB 依赖）
docker build -t ai-platform-backend:latest -f backend/Dockerfile .

# 后续构建（~30秒，依赖层缓存命中）
docker build -t ai-platform-backend:latest -f backend/Dockerfile .
```

> 💡 **国内加速**：Docker daemon 已配置 3 个镜像源（DaoCloud + Timeweb + 腾讯云），但仅对拉取 Python 基础镜像生效。PyPI 包下载走 Dockerfile 中的 `UV_INDEX_URL`（默认**腾讯云镜像** `mirrors.cloud.tencent.com`），不经过 Docker registry mirrors。可通过 `--build-arg UV_INDEX_URL=...` 切换。

### 构建后部署

```bash
# 首次部署需手动执行数据库迁移
docker compose -f compose.yml -f compose.override.yml run --rm prestart

# 启动全部服务
docker compose -f compose.yml -f compose.override.yml up -d
```

> ⚠️ `compose.override.yml` 默认跳过 backend/celery 的 prestart 依赖，首次部署或重置 DB 后必须手动执行 `docker compose run --rm prestart`。

---

## 验证

```bash
# GPU 可用性
docker run --rm --gpus all ai-platform-backend:latest \
  python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
# 期望输出：CUDA available: True

# RAG 依赖可用性
docker run --rm --gpus all ai-platform-backend:latest \
  python -c "import sentence_transformers; print('sentence-transformers OK')"

# 模型推理依赖可用性
docker run --rm --gpus all ai-platform-backend:latest \
  python -c "import transformers, diffusers, accelerate; print('Model inference OK')"
```

---

## 最终镜像规格

| 指标 | 数值 |
|------|------|
| 总包数 | 185 |
| nvidia-* 包 | 37（cublas / cudnn / cufft / nccl 等） |
| torch 版本 | 2.12.1 (CUDA) |
| sentence-transformers | 5.6.0 |
| transformers | 5.13.0 |
| 镜像体积 | ~3.5GB |
| 首次构建 | ~30 分钟 |
| 增量构建（改代码） | ~30 秒 |

---

## 环境变量说明

| 变量 | 值 | 作用 |
|------|------|------|
| `UV_INDEX_URL` | `https://mirrors.cloud.tencent.com/pypi/simple/` | 腾讯云 PyPI 镜像加速（可通过 `--build-arg` 切换） |
| `UV_HTTP_TIMEOUT` | `600` | 防止大包下载超时 |
| `UV_CONCURRENT_DOWNLOADS` | `8` | 并行下载数 |
| `UV_COMPILE_BYTECODE` | `1` | 预编译 .pyc 加速启动 |
| `UV_LINK_MODE` | `copy` | 不使用硬链接（Docker 推荐） |

---

## 相关文件

| 文件 | 角色 |
|------|------|
| `backend/Dockerfile` | 镜像构建定义 |
| `pyproject.toml`（根） | workspace 声明 |
| `ai_models/pyproject.toml` | gpu 依赖组定义 |
| `backend/pyproject.toml` | app 包定义 + RAG 语义搜索依赖（必装） |
| `uv.lock` | 锁定 185 个包的精确版本 |
| `compose.override.yml` | mailcatcher / playwright 等开发服务 |
