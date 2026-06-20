"""
分布式缓存层包入口 — 统一导出

模块:
- redis_client: 异步连接池管理
- rate_limiter: 分布式滑动窗口限流
- cache_manager: 统一缓存接口（Redis → 内存回退）
"""

from app.core.cache.redis_client import (
    init_redis_client,
    get_redis_client,
    close_redis_client,
    redis_health_check,
)
from app.core.cache.rate_limiter import (
    DistributedRateLimiter,
    init_rate_limiter,
    get_rate_limiter,
)
from app.core.cache.cache_manager import (
    CacheManager,
    init_cache_manager,
    get_cache_manager,
    cached,
)

__all__ = [
    "init_redis_client",
    "get_redis_client",
    "close_redis_client",
    "redis_health_check",
    "DistributedRateLimiter",
    "init_rate_limiter",
    "get_rate_limiter",
    "CacheManager",
    "init_cache_manager",
    "get_cache_manager",
    "cached",
]
