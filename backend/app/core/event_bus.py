"""
事件总线 — 异步队列驱动的消息分发系统

借鉴 AstrBot EventBus 设计：
- 维护一个 asyncio.Queue 接收各种消息事件
- dispatch() 无限循环从队列获取事件并创建异步任务处理
- strong reference 跟踪防止 pending task 被 GC 回收
- 支持多种事件类型的分发

数据流:
    消息平台 → event_queue.put(event) → EventBus.dispatch() → 对应 Scheduler 处理
"""

from __future__ import annotations

import asyncio
import logging
import time
from asyncio import Queue
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("platform.event_bus")


class EventPriority(int, Enum):
    """事件优先级"""
    LOW = 10
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class PlatformEvent:
    """统一的事件数据结构"""

    event_id: str
    """事件唯一 ID"""
    event_type: str
    """事件类型标签"""
    source: str
    """事件来源（平台/模块）"""
    session_id: str
    """关联会话 ID"""
    payload: dict[str, Any] = field(default_factory=dict)
    """事件负载数据"""
    priority: EventPriority = EventPriority.NORMAL
    timestamp: float = field(default_factory=time.time)
    """事件生成时间戳"""


# 事件处理器类型
EventHandler = Callable[[PlatformEvent], Awaitable[Any]]


class EventBus:
    """异步事件总线。

    - 维护事件队列 (asyncio.Queue)
    - dispatch() 无限循环从队列取事件
    - 根据事件类型路由到注册的处理器
    - 使用 asyncio.create_task 并发执行
    - strong reference 跟踪防止 task 被 GC 回收
    """

    def __init__(
        self,
        event_queue: Queue[PlatformEvent] | None = None,
        max_concurrent: int = 100,
    ) -> None:
        self.event_queue: Queue[PlatformEvent] = event_queue or Queue()
        self.max_concurrent = max_concurrent

        # 事件处理器注册表: event_type → list[EventHandler]
        self._handlers: dict[str, list[EventHandler]] = {}

        # 持有正在执行的 pipeline 任务的强引用，防止被 GC 回收
        self._pending_tasks: set[asyncio.Task] = set()

        # 控制标志
        self._running = False
        self._shutdown_event = asyncio.Event()

    # ── 处理器注册 ───────────────────────────────────

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """订阅事件类型"""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """取消订阅"""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        """订阅所有事件类型（通配符）"""
        self.subscribe("*", handler)

    # ── 事件发布 ────────────────────────────────────

    async def publish(self, event: PlatformEvent) -> None:
        """发布事件到队列"""
        await self.event_queue.put(event)
        logger.debug(
            "Event published: type=%s source=%s session=%s",
            event.event_type,
            event.source,
            event.session_id,
        )

    def publish_nowait(self, event: PlatformEvent) -> None:
        """同步发布事件（非阻塞）"""
        self.event_queue.put_nowait(event)

    # ── 事件分发 ────────────────────────────────────

    async def dispatch(self) -> None:
        """无限循环调度：从事件队列获取事件并分发给处理器。

        这是事件总线的主循环，通常作为独立的 asyncio.Task 运行。
        """
        self._running = True
        logger.info("EventBus dispatch loop started")

        while self._running:
            try:
                # 带超时的等待，以便检查 _running 标志
                event = await asyncio.wait_for(
                    self.event_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            # 创建任务处理事件
            task = asyncio.create_task(
                self._handle_event(event), name=f"event_{event.event_id}"
            )
            self._pending_tasks.add(task)
            task.add_done_callback(self._on_task_done)

            # 限制并发数
            while len(self._pending_tasks) >= self.max_concurrent:
                await asyncio.sleep(0.01)

    async def _handle_event(self, event: PlatformEvent) -> None:
        """处理单个事件：调用匹配的处理器"""
        handlers = self._find_handlers(event.event_type)
        if not handlers:
            logger.debug(
                "No handlers for event type '%s' (id=%s)",
                event.event_type, event.event_id,
            )
            return

        logger.info(
            "[%s] dispatching to %d handler(s)",
            event.event_type, len(handlers),
        )

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Handler failed for event type='%s' id='%s'",
                    event.event_type, event.event_id,
                )

    def _find_handlers(self, event_type: str) -> list[EventHandler]:
        """查找匹配的处理器（精确匹配 + 通配符）"""
        result: list[EventHandler] = []
        result.extend(self._handlers.get(event_type, []))
        result.extend(self._handlers.get("*", []))
        return result

    # ── 任务管理 ────────────────────────────────────

    def _on_task_done(self, task: asyncio.Task) -> None:
        """任务完成回调：移除强引用并暴露异常"""
        self._pending_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Event task failed", exc_info=exc)

    # ── 生命周期 ────────────────────────────────────

    async def shutdown(self, timeout: float = 10.0) -> None:
        """优雅关闭事件总线"""
        logger.info("EventBus shutting down...")
        self._running = False

        # 等待所有 pending 任务完成
        if self._pending_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        *self._pending_tasks, return_exceptions=True
                    ),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "EventBus shutdown: %d tasks still pending after %.1fs",
                    len(self._pending_tasks), timeout,
                )
                for t in list(self._pending_tasks):
                    t.cancel()

        self._pending_tasks.clear()
        logger.info("EventBus stopped")


# ── 全局单例 ─────────────────────────────────────────

_event_bus: EventBus | None = None


def init_event_bus(max_concurrent: int = 100) -> EventBus:
    """初始化全局事件总线单例"""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus(max_concurrent=max_concurrent)
    return _event_bus


def get_event_bus() -> EventBus:
    """获取全局事件总线单例"""
    if _event_bus is None:
        raise RuntimeError("EventBus not initialized. Call init_event_bus() first.")
    return _event_bus
