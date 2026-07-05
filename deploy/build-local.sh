#!/bin/bash
# 只构建本地服务 + 启动（跳过 open-webui/vllm）
set -e

echo "====== 构建本地 Docker 镜像 ======"
cd /mnt/d/code/ai-fullstack-platform

# 构建 backend 镜像（backend/prestart/celery-worker 共享）
echo "[1/2] 构建 backend 镜像..."
MODELS_DIR=/mnt/d/app/LLM/models docker compose -f deploy/compose.shared.yml build backend

# 构建前端镜像
echo "[2/2] 构建前端镜像..."
docker compose -f deploy/compose.shared.yml build studio-admin video-client video-admin

echo ""
echo "====== 启动所有本地服务 ======"
MODELS_DIR=/mnt/d/app/LLM/models CELERY_POOL=solo \
  docker compose -f deploy/compose.shared.yml up -d backend prestart celery-worker studio-admin video-client video-admin

echo ""
echo "====== 服务状态 ======"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "访问: http://localhost:18000 (API) | http://localhost:5175 (Studio Admin)"
