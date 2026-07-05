#!/bin/bash
# 通过国内镜像快速拉取 Open WebUI + vLLM
set -e

# 获取 Windows 宿主机 IP (用于代理检测)
WINDOWS_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}')

echo "=== 1. 检测代理 ==="
PROXY_FOUND=""
for port in 7890 10809 7897 8080; do
    if curl -s --connect-timeout 2 "http://$WINDOWS_IP:$port" > /dev/null 2>&1; then
        PROXY_FOUND="http://$WINDOWS_IP:$port"
        echo "找到代理: $PROXY_FOUND"
        break
    fi
done

if [ -z "$PROXY_FOUND" ]; then
    echo "未发现本地代理，使用镜像加速方式拉取"
fi

echo ""
echo "=== 2. 拉取 Open WebUI (ghcr.io) ==="
# 尝试多个镜像源
for MIRROR in "ghcr.dockerproxy.com" "ghcr.nju.edu.cn" "ghcr.io"; do
    echo "尝试: $MIRROR ..."
    if timeout 60 docker pull "$MIRROR/open-webui/open-webui:main" 2>/dev/null; then
        if [ "$MIRROR" != "ghcr.io" ]; then
            echo "重命名镜像..."
            docker tag "$MIRROR/open-webui/open-webui:main" "ghcr.io/open-webui/open-webui:main"
        fi
        echo "✅ Open WebUI 拉取成功!"
        break
    fi
    echo "× $MIRROR 不可用或超时"
done

echo ""
echo "=== 3. 拉取 vLLM (docker.io, 已有镜像加速) ==="
if docker pull vllm/vllm-openai:latest 2>&1; then
    echo "✅ vLLM 拉取成功!"
else
    echo "× vLLM 拉取失败"
fi

echo ""
echo "=== 4. 启动 AI 服务 ==="
cd /mnt/d/code/ai-fullstack-platform
MODELS_DIR=/mnt/d/app/LLM/models CELERY_POOL=solo \
    docker compose -f deploy/compose.shared.yml up -d open-webui vllm

echo ""
echo "=== 当前运行容器 ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
