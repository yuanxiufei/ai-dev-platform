#!/bin/bash
# 检测 Windows 宿主机代理
WINDOWS_IP=$(grep nameserver /etc/resolv.conf | awk '{print $2}')
echo "Windows IP: $WINDOWS_IP"

for port in 7890 10809 7897 8080 3128; do
    if curl -s --connect-timeout 2 "http://$WINDOWS_IP:$port" > /dev/null 2>&1; then
        echo "代理端口 $port 可用"
    fi
done
