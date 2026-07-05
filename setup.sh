#!/bin/bash
# ============================================================
# setup.sh — AI Fullstack Platform 双系统 Docker 部署
# 自动识别 Linux / WSL2，使用共享 ext4 存储
# ============================================================
set -e

# 检测环境
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo ">>> 检测到 WSL2 环境"
    NTFS_BASE="/mnt/d"
    POSTGRES_USER="${POSTGRES_USER:-admin}"
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-admin123}"
    POSTGRES_DB="${POSTGRES_DB:-studio}"
    CELERY_POOL="solo"
else
    echo ">>> 检测到 Linux 环境"
    NTFS_BASE="/run/media/reginyuan/Software"
    POSTGRES_USER="${POSTGRES_USER:-admin}"
    POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-admin123}"
    POSTGRES_DB="${POSTGRES_DB:-studio}"
    CELERY_POOL=""
fi

MODELS_DIR="${NTFS_BASE}/app/LLM/models"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "=== 1/3 挂载共享 ext4 数据卷 ==="
EXT4_IMG="${NTFS_BASE}/app/Docker/docker-volumes.img"
if mount | grep -q /data/docker-volumes; then
    echo "  ✓ 已挂载"
else
    sudo mkdir -p /data/docker-volumes
    sudo mount -o loop "$EXT4_IMG" /data/docker-volumes
    echo "  ✓ 挂载成功 ($EXT4_IMG → /data/docker-volumes)"
fi

echo ""
echo "=== 2/3 配置 Docker ==="
if [ -n "$CELERY_POOL" ]; then
    # WSL2: 不设 default-runtime=nvidia
    sudo tee /etc/docker/daemon.json << EOF
{
    "data-root": "/data/docker-volumes/docker",
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    }
}
EOF
    sudo dockerd &> /tmp/dockerd.log &
    sleep 3
else
    # Linux: 可以用 default-runtime=nvidia
    sudo tee /etc/docker/daemon.json << EOF
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
EOF
fi
echo "  ✓ Docker data-root: /data/docker-volumes/docker"

echo ""
echo "=== 3/3 启动服务 ==="
cd "$PROJECT_DIR/deploy"
export MODELS_DIR POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB CELERY_POOL

docker network create ai-platform-net 2>/dev/null || true
sudo docker compose -f compose.shared.yml up -d postgres redis qdrant ollama vllm open-webui prometheus alertmanager grafana

echo ""
echo "=== 完成 ==="
sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo "地址速查:"
echo "  PostgreSQL   → localhost:5432  (admin/admin123/studio)"
echo "  Redis        → localhost:6379"
echo "  Ollama API   → http://localhost:11434"
echo "  vLLM API     → http://localhost:3080/v1"
echo "  Open WebUI   → http://localhost:3090"
echo "  Grafana      → http://localhost:9091  (admin/admin)"
