# 多系统共享 Docker 架构

## 架构概览

WSL (Windows) 和双系统 Linux 共享同一个 Docker 数据存储，通过 ext4 镜像文件实现。

```
D:\app\Docker\
├── docker-volumes.img        ← 唯一数据盘 (70GB ext4)，两系统共享
│   ├── docker/               ← Docker data-root（镜像层 + 容器 + volumes）
│   │   ├── overlay2/         ←   Docker 镜像层
│   │   ├── containers/       ←   容器运行元数据
│   │   └── volumes/          ←   compose 命名 volumes
│   │       ├── ai-fullstack-platform_app-db-data/   → PostgreSQL
│   │       ├── ai-fullstack-platform_redis-data/    → Redis
│   │       └── ai-fullstack-platform_qdrant-data/   → Qdrant
│   ├── grafana/              ← 监控面板（预留）
│   ├── open-webui/           ← AI 对话（预留）
│   └── prometheus/           ← 指标采集（预留）
│
├── overlay2/    ← 废弃（WSL data-root 已迁入 .img）
├── containers/  ← 废弃
└── volumes/     ← 废弃
```

**核心原则**：两系统使用完全相同的 `compose.yml` + `.env`，零本地覆盖文件。

---

## 系统一：WSL (Windows)

### 启动步骤

**每次进入 WSL：**

```bash
# 1. 挂载共享数据镜像
sudo mount -o loop /mnt/d/app/Docker/docker-volumes.img /mnt/dockervol

# 2. 启动 Docker
sudo service docker start

# 3. 启动所有服务
cd /mnt/d/code/ai-fullstack-platform
docker compose -f compose.yml -f compose.override.yml up -d
```

### 停止步骤

```bash
cd /mnt/d/code/ai-fullstack-platform
docker compose -f compose.yml -f compose.override.yml down
# 可选择性卸载镜像（下次还要用就不卸载）
# sudo umount /mnt/dockervol
```

---

## 系统二：双系统 Linux

### 启动步骤

```bash
# 1. 挂载共享数据镜像（路径按实际 NTFS 分区挂载点调整）
sudo mount -o loop /path/to/D/docker-volumes.img /mnt/dockervol

# 2. 启动 Docker（如果未自动启动）
sudo systemctl start docker

# 3. 启动服务
cd /path/to/project
docker compose -f compose.yml -f compose.override.yml up -d
```

---

## 切换系统注意事项

1. **退出前必须 `docker compose down`**，否则下次另一个系统启动时容器状态不一致
2. **两系统共用 `compose.override.yml`**（已包含 Qdrant 健康检查修复、端口映射等本地开发配置）
3. **`.env` 通用**——Docker Compose 会覆盖容器内 `POSTGRES_SERVER=db` 等变量，同一份 `.env` 兼容两种启动方式
4. **镜像切换后可能需要重新 `docker pull`**——如果镜像层在切换系统时不兼容（overlay2 驱动版本差异），重新拉取即可，数据不受影响

---

## 服务验证

三容器全部 healthy 即表示可正常使用。

### 快速验证（一命令）

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}'
```

预期输出：

```
NAMES                            STATUS
ai-fullstack-platform-db-1       Up X minutes (healthy)
ai-fullstack-platform-redis-1    Up X minutes (healthy)
ai-fullstack-platform-qdrant-1   Up X minutes (healthy)
```

### 逐服务深度验证

#### PostgreSQL

```bash
# 连接测试
docker exec ai-fullstack-platform-db-1 pg_isready -U admin -d studio

# 预期：/var/run/postgresql:5432 - accepting connections
```

```bash
# 查看表结构（有数据时可用）
docker exec ai-fullstack-platform-db-1 psql -U admin -d studio -c '\dt'
```

#### Redis

```bash
# PING 测试
docker exec ai-fullstack-platform-redis-1 redis-cli PING

# 预期：PONG
```

```bash
# Keyspace 信息
docker exec ai-fullstack-platform-redis-1 redis-cli INFO keyspace
```

#### Qdrant

```bash
# 健康检查 API（容器内）
docker exec ai-fullstack-platform-qdrant-1 bash -c 'timeout 3 bash -c "echo > /dev/tcp/127.0.0.1/6333" && echo OK'

# 预期：OK
```

> **已知问题**：Qdrant 镜像不含 `curl`，`compose.override.yml` 已将健康检查改为 bash TCP 重定向检测。

### 宿主机直连验证

确保 `.env` 中 `POSTGRES_SERVER=localhost`、`REDIS_URL=redis://localhost:6379/0`、`QDRANT_HOST=localhost`：

```bash
# PostgreSQL（需安装 psql 客户端）
psql -h localhost -p 5432 -U admin -d studio -c "SELECT 1 AS ok;"

# Redis（需安装 redis-cli）
redis-cli -h localhost -p 6379 PING

# Qdrant
curl http://localhost:6333/health
```

---

## 常见问题

### Q: Qdrant 一直 unhealthy？

A: 健康检查日志显示 `curl: executable file not found` 是正常的。已通过 `compose.override.yml` 修复为 bash TCP 检测。如仍有问题，手动验证：

```bash
docker exec ai-fullstack-platform-qdrant-1 bash -c 'timeout 3 bash -c "echo > /dev/tcp/127.0.0.1/6333" && echo OK || echo FAIL'
```

### Q: 从 Linux 切回 WSL 后容器无法启动？

A: 在 Linux 上忘记 `docker compose down`。解决：
```bash
# 在 WSL 中强制重建
docker compose -f compose.yml -f compose.override.yml up -d --force-recreate
```

### Q: 镜像挂载失败 `mount: wrong fs type`？

A: ext4 镜像可能未正常卸载留有脏日志。修复后重新挂载：
```bash
sudo fsck.ext4 -y /mnt/d/app/Docker/docker-volumes.img
sudo mount -o loop /mnt/d/app/Docker/docker-volumes.img /mnt/dockervol
```

### Q: 如何确认 Docker data-root 正确指向 ext4？

```bash
docker info --format 'DockerRootDir={{.DockerRootDir}}'
# 预期：DockerRootDir=/mnt/dockervol/docker
```

如果不是以上路径，检查 `/etc/docker/daemon.json` 中 `data-root` 配置。

---

## 相关文件

| 文件 | 用途 |
|------|------|
| `compose.yml` | 主配置（两系统通用，不动） |
| `compose.override.yml` | 本地开发覆盖（端口映射、健康检查修复） |
| `.env` | 环境变量（两系统通用） |
| `D:\app\Docker\docker-volumes.img` | ext4 共享数据镜像 |
