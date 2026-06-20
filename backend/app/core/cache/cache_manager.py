"""
统一缓存管理器 — Redis 优先 + 内存回退

功能:
- 统一的缓存接口（get/set/delete/exists/ttl）
- Redis 优先，不可用时自动回退到内存 dict
- TTL 支持
- 装饰器 @cached 用于函数结果缓存

使用示例:
    cache = get_cache_manager()
    await cache.set("user:123", user_data, ttl=300)
    data = await cache.get("user:123")
"""

import asyncio
import functools
import hashlib
import json
import logging
import time
from typing import Any, Callable, Optional, TypeVar

from app.core.cache import get_redis_client

logger = logging.getLogger("cache.manager")

T = TypeVar("T")


class CacheBackend:
    """缓存后端抽象"""

    async def get(self, key: str) -> Optional[str]: ...

    async def set(self, key: str, value: str, ttl: int = 300) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def ttl(self, key: str) -> int: ...


class RedisCacheBackend(CacheBackend):
    """Redis 缓存后端"""

    async def get(self, key: str) -> Optional[str]:
        client = get_redis_client()
        if not client:
            raise ConnectionError("Redis not available")
        return await client.get(key)  # type: ignore[no-any-return]

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        client = get_redis_client()
        if not client:
            raise ConnectionError("Redis not available")
        await client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> None:
        client = get_redis_client()
        if client:
            await client.delete(key)

    async def exists(self, key: str) -> bool:
        client = get_redis_client()
        if not client:
            return False
        return bool(await client.exists(key))

    async def ttl(self, key: str) -> int:
        client = get_redis_client()
        if not client:
            return -1
        return await client.ttl(key)  # type: ignore[no-any-return]


class MemoryCacheBackend(CacheBackend):
    """内存回退后端（dict + TTL）"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at and time.time() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        async with self._lock:
            expires_at = time.time() + ttl if ttl > 0 else 0
            self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return await self.get(key) is not None

    async def ttl(self, key: str) -> int:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return -2
            _, expires_at = entry
            if not expires_at:
                return -1
            remaining = int(expires_at - time.time())
            return max(remaining, -2)


class CacheManager:
    """
    统一缓存管理器 — Redis 优先 → 内存回退

    JSON 序列化/反序列化自动处理，支持任意 Python 对象。
    """

    def __init__(self, prefix: str = "cache") -> None:
        self._prefix = prefix
        self._redis_backend = RedisCacheBackend()
        self._memory_backend = MemoryCacheBackend()

    @property
    def _backend(self) -> CacheBackend:
        """自动选择后端（Redis 优先）"""
        if get_redis_client():
            return self._redis_backend
        return self._memory_backend

    def _build_key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        """获取缓存值（自动 JSON 反序列化）"""
        try:
            raw = await self._backend.get(self._build_key(key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        """设置缓存值（自动 JSON 序列化），ttl 单位秒"""
        try:
            raw = json.dumps(value, ensure_ascii=False, default=str)
            await self._backend.set(self._build_key(key), raw, ttl=ttl)
        except Exception as e:
            logger.warning("Cache set failed for key=%s: %s", key, e)

    async def delete(self, key: str) -> None:
        """删除缓存"""
        try:
            await self._backend.delete(self._build_key(key))
        except Exception as e:
            logger.warning("Cache delete failed for key=%s: %s", key, e)

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            return await self._backend.exists(self._build_key(key))
        except Exception:
            return False

    async def get_or_set(
        self, key: str, factory: Callable[[], Any], ttl: int = 300,
    ) -> Any:
        """获取缓存，不存在则调用 factory 创建并缓存"""
        cached = await self.get(key)
        if cached is not None:
            return cached

        value = factory()
        if asyncio.iscoroutine(value):
            value = await value

        await self.set(key, value, ttl=ttl)
        return value

    async def clear_prefix(self, prefix: str) -> int:
        """清除匹配前缀的所有 key（仅 Redis 后端支持）"""
        client = get_redis_client()
        if not client:
            return 0

        pattern = f"{self._prefix}:{prefix}*"
        count = 0
        async for key in client.scan_iter(match=pattern):
            await client.delete(key)
            count += 1
        return count


# ── 全局单例 ────────────────────────────────────────

_cache_manager: Optional[CacheManager] = None


def init_cache_manager(prefix: str = "cache") -> CacheManager:
    """初始化全局缓存管理器"""
    global _cache_manager
    _cache_manager = CacheManager(prefix=prefix)
    backend_type = "redis" if get_redis_client() else "memory"
    logger.info("CacheManager initialized (backend=%s)", backend_type)
    return _cache_manager


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器（若未初始化则自动创建）"""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = init_cache_manager()
    return _cache_manager


def cached(ttl: int = 300, key_prefix: str = "fn"):
    """
    缓存装饰器 — 自动缓存异步函数结果

    使用示例:
        @cached(ttl=600, key_prefix="user_profile")
        async def get_user_profile(user_id: str) -> dict:
            ...
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 基于函数名 + 参数计算 key
            cache_key_parts = [
                key_prefix,
                func.__name__,
                hashlib.md5(
                    json.dumps(
                        {"args": args, "kwargs": kwargs}, sort_keys=True, default=str,
                    ).encode(),
                ).hexdigest()[:12],
            ]
            cache_key = ":".join(cache_key_parts)

            cache = get_cache_manager()
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug("Cache HIT: %s", cache_key)
                return cached_result

            logger.debug("Cache MISS: %s", cache_key)
            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl=ttl)
            return result

        return wrapper
    return decorator
