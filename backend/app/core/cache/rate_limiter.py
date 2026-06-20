"""
分布式限流器 — 基于 Redis 滑动窗口算法

功能:
- 支持 IP 级别 / 用户级别 / 端点级别的多维度限流
- 滑动窗口算法（Redis Sorted Set），精度高于 Fixed Window
- Redis 不可用时自动降级为内存限流
- 与 Pipeline RateLimitStage 互补：HTTP 层限流 + Agent 层限流

配置:
    REDIS_RATE_LIMIT_ENABLED=true
    REDIS_RATE_LIMIT_PER_IP=100      # 每 IP 每分钟
    REDIS_RATE_LIMIT_PER_USER=300    # 每用户每分钟
    REDIS_RATE_LIMIT_WINDOW=60       # 窗口秒数
"""

import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional

from app.core.cache import get_redis_client

logger = logging.getLogger("cache.rate_limiter")


class DistributedRateLimiter:
    """
    基于 Redis Sorted Set 的滑动窗口限流器

    算法: 每个 key 维护一个 sorted set，score 为纳秒时间戳。
         每次请求时清理窗口外的过期记录，计算窗口内计数。
         Redis 不可用时自动降级为进程内内存限流。
    """

    def __init__(
        self,
        window_seconds: int = 60,
        max_requests: int = 100,
        prefix: str = "ratelimit",
    ) -> None:
        self._window = window_seconds
        self._max_requests = max_requests
        self._prefix = prefix
        self._script_sha: Optional[str] = None

        # 内存降级存储
        self._fallback: defaultdict[str, list[float]] = defaultdict(list)
        self._fallback_locks: dict[str, asyncio.Lock] = {}
        self._using_redis: Optional[bool] = None

    async def _get_script(self) -> str:
        """Lua 脚本: 原子化滑动窗口检查"""
        return """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local max_requests = tonumber(ARGV[3])

        -- 清理过期记录
        redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)

        -- 计数
        local count = redis.call('ZCARD', key)

        if count < max_requests then
            redis.call('ZADD', key, now, now .. '-' .. count)
            redis.call('EXPIRE', key, math.ceil(window))
            return {1, count + 1}
        else
            -- 计算最早记录过期时间（用于 stall）
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local retry_after = 0
            if #oldest > 0 then
                retry_after = math.ceil(tonumber(oldest[2]) + window - now) + 0.3
            end
            return {0, retry_after}
        end
        """

    def _build_key(self, identifier: str) -> str:
        return f"{self._prefix}:{identifier}"

    async def _redis_check(self, key: str) -> tuple[bool, float]:
        """Redis 限流检查（原子 Lua 脚本）"""
        client = get_redis_client()
        if not client:
            raise ConnectionError("Redis not available")

        now_ns = time.time()
        window = self._window

        result = await client.eval(
            await self._get_script(),
            1,
            key,
            now_ns,
            window,
            self._max_requests,
        )

        allowed = bool(result[0])
        retry_after = float(result[1]) if not allowed else 0.0
        return allowed, retry_after

    async def _fallback_check(self, key: str) -> tuple[bool, float]:
        """内存降级限流检查"""
        if key not in self._fallback_locks:
            self._fallback_locks[key] = asyncio.Lock()

        async with self._fallback_locks[key]:
            now = time.time()
            window = self._window
            timestamps = self._fallback[key]

            # 清理过期
            cutoff = now - window
            while timestamps and timestamps[0] < cutoff:
                timestamps.pop(0)

            if len(timestamps) < self._max_requests:
                timestamps.append(now)
                return True, 0.0

            retry_after = timestamps[0] + window - now + 0.3
            return False, max(retry_after, 0)

    async def is_allowed(
        self,
        identifier: str,
        strategy: str = "reject",
    ) -> tuple[bool, float]:
        """
        检查是否允许请求

        参数:
            identifier: 限流标识（如 IP 地址、用户 ID）
            strategy: "reject" 直接拒绝 | "stall" 等待直到可放行

        返回:
            (allowed, retry_after_seconds)
        """
        key = self._build_key(identifier)

        # 检查 Redis 可用性
        if self._using_redis is None:
            self._using_redis = get_redis_client() is not None

        try:
            if self._using_redis:
                allowed, retry_after = await self._redis_check(key)
            else:
                allowed, retry_after = await self._fallback_check(key)
        except Exception:
            # Redis 故障，降级到内存
            logger.warning(
                "Redis rate limiter failed, falling back to in-memory for key=%s", key,
            )
            self._using_redis = False
            allowed, retry_after = await self._fallback_check(key)

        if not allowed and strategy == "stall" and retry_after > 0:
            logger.info(
                "Rate-limit stall: identifier=%s, wait=%.1fs", identifier, retry_after,
            )
            await asyncio.sleep(retry_after)
            # 等待后重试一次
            return await self.is_allowed(identifier, strategy="reject")

        if not allowed:
            logger.info(
                "Rate-limit reject: identifier=%s, retry_after=%.1fs",
                identifier, retry_after,
            )

        return allowed, retry_after


# ── 全局单例 ────────────────────────────────────────

_rate_limiter: Optional[DistributedRateLimiter] = None


def init_rate_limiter(
    window_seconds: int = 60,
    max_requests: int = 100,
) -> DistributedRateLimiter:
    """初始化全局分布式限流器"""
    global _rate_limiter
    _rate_limiter = DistributedRateLimiter(
        window_seconds=window_seconds,
        max_requests=max_requests,
    )
    return _rate_limiter


def get_rate_limiter() -> Optional[DistributedRateLimiter]:
    """获取全局限流器"""
    return _rate_limiter
