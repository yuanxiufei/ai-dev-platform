#!/bin/bash
# 一键完成：nvidia-toolkit 安装 + dockerd 重启 + 全部服务启动
# 在 WSL2 终端中执行: sudo bash /mnt/d/code/ai-fullstack-platform/deploy/setup-nvidia.sh
set -e

echo "=== [1/4] 安装 nvidia-container-toolkit ==="
if command -v nvidia-ctk &>/dev/null; then
    echo "nvidia-ctk 已安装，跳过"
else
    apt-get install -y -o Acquire::http::Timeout=180 -o Acquire::Retries=10 nvidia-container-toolkit
fi

echo "=== [2/4] 配置 Docker runtime ==="
nvidia-ctk runtime configure --runtime=docker
nvidia-ctk --version

echo "=== [3/4] 确保 dockerd 运行 ==="
if ! pgrep dockerd &>/dev/null; then
    echo "启动 dockerd..."
    nohup dockerd &>/tmp/dockerd.log &
    sleep 3
fi
docker info 2>&1 | head -3

echo "=== [4/4] 启动全部服务 (含拉取 open-webui/vllm) ==="
cd /mnt/d/code/ai-fullstack-platform
MODELS_DIR=/mnt/d/app/LLM/models CELERY_POOL=solo \
  docker compose -f deploy/compose.shared.yml up -d --pull missing

echo ""
echo "=== 全部完成！==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
