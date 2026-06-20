"""
核心生命周期管理 — 统一启动/停止/重启流程

借鉴 AstrBot AstrBotCoreLifecycle 设计：
- initialize(): 按序初始化所有子系统
- start(): 启动事件总线 + 注册任务
- stop(): 优雅关闭所有子系统
- 提供统一的子系统声明式和初始化 API
"""

from __future__ import annotations

import asyncio
import logging
import time
import traceback
from typing import Any

logger = logging.getLogger("platform.lifecycle")

# ── 生命周期阶段枚举 ────────────────────────────────


class LifecyclePhase:
    """生命周期阶段常量"""

    PRE_INIT = "pre_init"
    INIT = "init"
    POST_INIT = "post_init"
    RUNNING = "running"
    SHUTDOWN = "shutdown"


# ── 可初始化的子系统接口 ─────────────────────────────


class Initializable:
    """可初始化/可终止的子系统抽象"""

    async def initialize(self) -> None:
        """初始化子系统"""

    async def shutdown(self) -> None:
        """终止子系统"""


# ── 核心生命周期管理器 ───────────────────────────────


class CoreLifecycle:
    """统一的核心生命周期管理器。

    负责按序初始化所有子系统，并在应用关闭时优雅终止。

    初始化顺序:
        1. 配置管理器
        2. 数据库连接
        3. Provider 管理器
        4. 插件管理器
        5. Pipeline 调度器
        6. 事件总线
        7. Cron 任务管理器

    Example:
        ```python
        lifecycle = CoreLifecycle()
        lifecycle.register("config", ConfigManager())
        lifecycle.register("plugins", PluginManager())
        lifecycle.register("event_bus", EventBus())
        await lifecycle.initialize()
        await lifecycle.start()
        ```
    """

    def __init__(self) -> None:
        # 子系统注册表: name → Initializable
        self._subsystems: dict[str, Initializable] = {}
        # 初始化顺序（按注册顺序）
        self._init_order: list[str] = []
        # 运行时任务
        self._tasks: list[asyncio.Task] = []
        # 状态
        self._phase: str = LifecyclePhase.PRE_INIT
        self._start_time: float = 0
        # 关闭事件
        self._shutdown_event = asyncio.Event()

    # ── 子系统注册 ─────────────────────────────────────

    def register(self, name: str, subsystem: Initializable) -> None:
        """注册一个子系统"""
        self._subsystems[name] = subsystem
        if name not in self._init_order:
            self._init_order.append(name)
        logger.debug("Subsystem registered: %s", name)

    def get(self, name: str) -> Initializable | None:
        """按名称获取子系统"""
        return self._subsystems.get(name)

    # ── 生命周期方法 ──────────────────────────────────

    async def initialize(self) -> None:
        """按序初始化所有子系统"""
        self._phase = LifecyclePhase.INIT
        logger.info("=== CoreLifecycle initializing ===")

        for name in self._init_order:
            subsystem = self._subsystems[name]
            try:
                await subsystem.initialize()
                logger.info("  [%s] initialized", name)
            except Exception as e:
                logger.error(
                    "  [%s] initialization FAILED: %s\n%s",
                    name, e, traceback.format_exc(),
                )
                # 初始化失败不阻止其他子系统
        self._phase = LifecyclePhase.POST_INIT

    async def start(self) -> None:
        """启动核心生命周期。

        此方法会启动事件总线调度循环和其他后台任务。
        """
        self._phase = LifecyclePhase.RUNNING
        self._start_time = time.time()
        logger.info("=== CoreLifecycle starting ===")

        # 触发 OnPlatformLoadedEvent — 通过 EventBus
        try:
            from app.core.event_bus import get_event_bus, PlatformEvent
            from app.core.plugins.handler import EventType, handler_registry

            # 发布平台加载事件
            event = PlatformEvent(
                event_id="lifecycle_start",
                event_type="platform.loaded",
                source="core_lifecycle",
                session_id="system",
            )
            get_event_bus().publish_nowait(event)

            # 执行事件钩子: OnPlatformLoadedEvent
            handlers = handler_registry.get_by_event_type(
                EventType.OnPlatformLoadedEvent,
                only_activated=True,
            )
            for handler in handlers:
                try:
                    logger.info(
                        "Executing lifecycle hook: %s",
                        handler.handler_name,
                    )
                    await handler.handler()
                except Exception:
                    logger.error(traceback.format_exc())

        except RuntimeError:
            # EventBus 未初始化时跳过
            pass

    async def shutdown(self) -> None:
        """优雅关闭所有子系统"""
        self._phase = LifecyclePhase.SHUTDOWN
        logger.info("=== CoreLifecycle shutting down ===")

        # 取消所有运行时任务
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()

        # 反向关闭子系统（后注册先关闭）
        for name in reversed(self._init_order):
            subsystem = self._subsystems[name]
            try:
                await subsystem.shutdown()
                logger.info("  [%s] shutdown", name)
            except Exception as e:
                logger.warning(
                    "  [%s] shutdown error: %s", name, e
                )

        self._shutdown_event.set()
        elapsed = time.time() - self._start_time
        logger.info(
            "=== CoreLifecycle shut down (uptime: %.0fs) ===", elapsed
        )

    # ── 任务管理 ─────────────────────────────────────

    def register_task(self, coro: Any) -> asyncio.Task:
        """注册一个后台协程任务，受生命周期管理"""
        task = asyncio.create_task(coro)
        self._tasks.append(task)
        return task

    # ── 状态查询 ─────────────────────────────────────

    @property
    def phase(self) -> str:
        return self._phase

    @property
    def uptime(self) -> float:
        if self._start_time == 0:
            return 0
        return time.time() - self._start_time

    def is_running(self) -> bool:
        return self._phase == LifecyclePhase.RUNNING
