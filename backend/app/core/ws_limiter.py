"""
WebSocket 连接限制器 — 全局 + 每用户并发连接数控制

用法:
    limiter = WSConnectionLimiter(max_global=100, max_per_user=5)

    @router.websocket("/ws")
    async def my_ws(websocket: WebSocket):
        async with limiter.enforce(websocket, user_id):
            await websocket.accept()
            # ... WebSocket loop ...
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger("ws_limiter")

# ── 默认限制 ─────────────────────────────────────────────────
# 环境变量可覆盖
import os
_DEFAULT_MAX_GLOBAL = int(os.getenv("WS_MAX_CONNECTIONS_GLOBAL", "100"))
_DEFAULT_MAX_PER_USER = int(os.getenv("WS_MAX_CONNECTIONS_PER_USER", "5"))


class WSConnectionLimiter:
    """全局 + 每用户 WebSocket 并发连接数限制"""

    def __init__(
        self,
        max_global: int = _DEFAULT_MAX_GLOBAL,
        max_per_user: int = _DEFAULT_MAX_PER_USER,
    ):
        self._max_global = max_global
        self._max_per_user = max_per_user
        self._global_count = 0
        self._per_user: dict[str, int] = {}
        self._lock = asyncio.Lock()

    @property
    def global_count(self) -> int:
        return self._global_count

    @property
    def max_global(self) -> int:
        return self._max_global

    async def _acquire(self, user_id: Optional[str] = None) -> bool:
        """尝试获取连接槽位。返回 True 表示成功。"""
        async with self._lock:
            if self._global_count >= self._max_global:
                logger.warning(
                    "WebSocket connection rejected: global limit %d reached",
                    self._max_global,
                )
                return False

            if user_id:
                user_count = self._per_user.get(user_id, 0)
                if user_count >= self._max_per_user:
                    logger.warning(
                        "WebSocket connection rejected: per-user limit %d reached for %s",
                        self._max_per_user, user_id,
                    )
                    return False
                self._per_user[user_id] = user_count + 1

            self._global_count += 1
            logger.debug(
                "WS connection acquired (global=%d/%d) user=%s",
                self._global_count, self._max_global, user_id,
            )
            return True

    async def _release(self, user_id: Optional[str] = None) -> None:
        """释放连接槽位"""
        async with self._lock:
            self._global_count = max(0, self._global_count - 1)
            if user_id and user_id in self._per_user:
                self._per_user[user_id] = max(0, self._per_user[user_id] - 1)
                if self._per_user[user_id] == 0:
                    del self._per_user[user_id]
            logger.debug(
                "WS connection released (global=%d/%d) user=%s",
                self._global_count, self._max_global, user_id,
            )

    async def enforce(
        self, websocket: WebSocket, user_id: Optional[str] = None
    ):
        """异步上下文管理器 — 获取槽位，离开时自动释放。

        若槽位满则关闭 WebSocket 连接并抛出 ConnectionRefusedError。
        """
        if not await self._acquire(user_id):
            await websocket.close(code=1013, reason="Too many connections")
            raise ConnectionRefusedError("WebSocket connection limit reached")

        class _Guard:
            def __init__(self, limiter: WSConnectionLimiter, uid: Optional[str]):
                self._limiter = limiter
                self._uid = uid

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                await self._limiter._release(self._uid)

        return _Guard(self, user_id)


# ── 全局单例 ─────────────────────────────────────────────────

_global_ws_limiter: Optional[WSConnectionLimiter] = None


def get_ws_limiter() -> WSConnectionLimiter:
    """获取全局 WebSocket 连接限制器单例"""
    global _global_ws_limiter
    if _global_ws_limiter is None:
        _global_ws_limiter = WSConnectionLimiter()
    return _global_ws_limiter
