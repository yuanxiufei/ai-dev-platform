#!/bin/bash
# 全栈 AI 平台一键启动脚本
# 包含：数据盘挂载检查 + 构建 + 启动

set -e

echo "=== 1. 检查数据盘挂载 ==="
if ! mountpoint -q /mnt/dockervol; then
    echo "挂载 /mnt/dockervol..."
    sudo mount -o loop /mnt/d/app/Docker/docker-volumes.img /mnt/dockervol
    echo "挂载完成"
else
    echo "已挂载"
fi

echo ""
echo "=== 2. 检查 dockerd ==="
if ! pgrep -x dockerd > /dev/null; then
    echo "启动 dockerd..."
    sudo dockerd &> /tmp/dockerd.log &
    sleep 3
else
    echo "dockerd 已运行"
fi

echo ""
echo "=== 3. 启动基础设施 ==="
cd /mnt/d/code/ai-fullstack-platform
MODELS_DIR=/mnt/d/app/LLM/models docker compose -f deploy/compose.shared.yml up -d \
    postgres redis qdrant ollama prometheus alertmanager grafana adminer

echo ""
echo "=== 4. 构建本地服务 (backend + 前端) ==="
MODELS_DIR=/mnt/d/app/LLM/models CELERY_POOL=solo \
    docker compose -f deploy/compose.shared.yml build \
    backend prestart celery-worker studio-admin video-client video-admin

echo ""
echo "=== 5. 拉取 AI 服务镜像 (需要网络) ==="
MODELS_DIR=/mnt/d/app/LLM/models CELERY_POOL=solo \
    docker compose -f deploy/compose.shared.yml pull open-webui vllm 2>/dev/null || \
    echo "拉取 Open WebUI/vLLM 失败（网络问题），跳过"

echo ""
echo "=== 6. 启动全部服务 ==="
MODELS_DIR=/mnt/d/app/LLM/models CELERY_POOL=solo \
    docker compose -f deploy/compose.shared.yml up -d

echo ""
echo "=== 完成！当前运行的服务： ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
