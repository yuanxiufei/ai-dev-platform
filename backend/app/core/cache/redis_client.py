"""
分布式缓存层 — Redis 客户端 + 连接池 + 健康检查

支持:
- 异步连接池（redis.asyncio）
- 自动重连与超时控制
- 单例模式（全局共享连接）
- 可选启用（REDIS_URL 为空时回退到内存缓存）
"""

import logging
from typing import Any, Optional

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger("cache.redis")

# 全局单例
_redis_client: Optional[aioredis.Redis] = None


def _build_redis_url() -> str:
    """从多个环境变量组装 Redis URL"""
    redis_url = getattr(settings, "REDIS_URL", "") or ""
    if redis_url:
        return str(redis_url)

    host = getattr(settings, "REDIS_HOST", "localhost") or "localhost"
    port = int(getattr(settings, "REDIS_PORT", 6379) or 6379)
    password = getattr(settings, "REDIS_PASSWORD", "") or ""
    db = int(getattr(settings, "REDIS_DB", 0) or 0)

    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


async def init_redis_client() -> Optional[aioredis.Redis]:
    """初始化 Redis 客户端（全局单例），返回 None 表示不可用"""
    global _redis_client

    redis_enabled = getattr(settings, "REDIS_ENABLED", True)
    if not redis_enabled:
        logger.info("Redis disabled by config (REDIS_ENABLED=false)")
        return None

    redis_url = _build_redis_url()

    try:
        _redis_client = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=3,
            socket_keepalive=True,
            health_check_interval=30,
            max_connections=20,
        )
        await _redis_client.ping()
        logger.info("Redis client connected: %s", redis_url)
        return _redis_client
    except Exception as e:
        logger.warning("Redis unavailable (%s), fallback to in-memory: %s", redis_url, e)
        _redis_client = None
        return None


def get_redis_client() -> Optional[aioredis.Redis]:
    """获取全局 Redis 客户端（可能为 None）"""
    return _redis_client


async def close_redis_client() -> None:
    """关闭 Redis 连接"""
    global _redis_client
    if _redis_client:
        try:
            await _redis_client.close()
        except Exception:
            pass
        _redis_client = None
        logger.info("Redis client closed")


async def redis_health_check() -> dict[str, Any]:
    """Redis 健康检查"""
    client = get_redis_client()
    if not client:
        return {"available": False, "status": "not_configured"}

    try:
        await client.ping()
        info = await client.info("memory")
        return {
            "available": True,
            "status": "healthy",
            "used_memory_human": info.get("used_memory_human", "N/A"),
            "connected_clients": info.get("connected_clients", 0),
        }
    except Exception as e:
        return {"available": False, "status": "error", "error": str(e)}
