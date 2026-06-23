"""
SmartSleepManager — 智能休眠与唤醒

在长期无调用请求时，系统自动进入低功耗休眠状态；一旦接收到外部调用请求则自动唤醒。

休眠操作（应用级）：
- 卸载 GPU 模型（释放显存）
- 暂停非关键后台任务
- 降低 CPU 优先级
- 关闭 WebSocket 长连接空闲检测

唤醒操作（应用级）：
- 恢复 GPU 模型加载
- 恢复后台任务
- 恢复正常优先级
- 重建 WebSocket 连接

OS 级休眠（省电模式）：
- 在应用级休眠持续 N 秒后，触发操作系统睡眠/休眠
- 需配合 Wake-on-LAN 实现远程唤醒
- 支持 Windows（睡眠/休眠）、Linux（suspend）、macOS（sleep）

状态机：
    IDLE ──(timeout)──> SLEEPING ──(request)──> WAKING ──> IDLE
                            │
                            └──(os_sleep_timeout)──> OS_SLEEP (操作系统挂起)
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger("standalone.sleep")


class SystemState(Enum):
    """系统状态"""
    IDLE = "idle"            # 正常运行，等待请求
    ACTIVE = "active"        # 正在处理请求
    PRE_SLEEP = "pre_sleep"  # 准备进入休眠
    SLEEPING = "sleeping"    # 休眠中（低功耗）
    WAKING = "waking"        # 正在唤醒
    OS_SLEEPING = "os_sleeping"  # 操作系统已挂起（睡眠/休眠）


@dataclass
class SleepConfig:
    """休眠/唤醒配置"""

    # 进入休眠的空闲时间（秒）
    idle_timeout_seconds: float = 300.0  # 5分钟

    # 休眠前警告时间（秒），在真正休眠前发通知
    pre_sleep_warning_seconds: float = 60.0

    # 唤醒超时（秒），唤醒操作的最大等待时间
    wake_timeout_seconds: float = 30.0

    # 最低活跃请求数阈值 — 低于此值才允许休眠
    min_active_requests_to_prevent_sleep: int = 1

    # 是否在休眠时卸载模型
    unload_models_on_sleep: bool = True

    # 是否降低 CPU 优先级
    reduce_cpu_priority: bool = True

    # CPU 优先级降低目标（仅 Linux）
    cpu_nice_value: int = 10

    # 定期健康检查间隔（休眠时）
    sleep_poll_interval: float = 10.0

    # ── OS 级休眠 ──
    # 是否启用 OS 级休眠（应用休眠 N 秒后触发操作系统挂起）
    enable_os_sleep: bool = True
    # 进入应用级休眠后，再等待多久触发 OS 休眠（秒），默认 30 分钟
    os_sleep_timeout_seconds: float = 1800.0
    # OS 休眠模式: "sleep"（睡眠，内存供电）/ "hibernate"（休眠，写硬盘后断电）
    os_sleep_mode: str = "sleep"
    # 触发 OS 休眠前等待时间（秒，用于发送最后的通知）
    os_sleep_warning_seconds: float = 30.0

    # 事件回调
    on_state_change: Optional[Callable[[str, str], None]] = None   # (old, new)
    on_sleep: Optional[Callable[[], None]] = None
    on_wake: Optional[Callable[[], None]] = None


class SmartSleepManager:
    """智能休眠管理器。

    核心职责：
    1. 追踪最近的请求时间，判断是否需要休眠
    2. 执行休眠/唤醒操作
    3. 作为中间件钩子接入 FastAPI

    使用方式：
        ```python
        sleep_mgr = SmartSleepManager(SleepConfig(idle_timeout=300))

        # 通过中间件注入每次请求
        app.add_middleware(SleepAwareMiddleware, sleep_manager=sleep_mgr)

        # 后台启动状态机
        asyncio.create_task(sleep_mgr.run_state_machine())
        ```
    """

    def __init__(self, config: SleepConfig | None = None) -> None:
        self.config = config or SleepConfig()
        self._state: SystemState = SystemState.IDLE
        self._last_request_time: float = time.time()
        self._active_request_count: int = 0
        self._state_machine_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._wake_event = asyncio.Event()

        # 休眠前保存的状态
        self._sleep_start_time: float = 0.0
        self._models_were_loaded: list[str] = []
        self._original_nice: Optional[int] = None

        # 统计
        self._sleep_count: int = 0
        self._total_sleep_duration: float = 0.0

        # ── OS 级休眠 ──
        self._os_sleep_scheduled: bool = False
        self._os_sleep_at: float = 0.0          # 计划触发时间戳
        self._os_sleep_task: Optional[asyncio.Task] = None
        self._os_sleep_cancelled: bool = False    # 用于取消已进入的 OS 休眠任务

    # ── 公共 API ────────────────────────────────────

    @property
    def state(self) -> SystemState:
        return self._state

    @property
    def is_sleeping(self) -> bool:
        return self._state == SystemState.SLEEPING

    @property
    def stats(self) -> dict:
        base = {
            "state": self._state.value,
            "last_request_seconds_ago": time.time() - self._last_request_time,
            "active_requests": self._active_request_count,
            "sleep_count": self._sleep_count,
            "total_sleep_duration": self._total_sleep_duration,
            "current_sleep_duration": (
                time.time() - self._sleep_start_time if self.is_sleeping else 0
            ),
        }
        # OS 休眠信息
        base["os_sleep"] = {
            "enabled": self.config.enable_os_sleep,
            "scheduled": self._os_sleep_scheduled,
            "scheduled_at": self._os_sleep_at,
            "seconds_until_os_sleep": max(0, self._os_sleep_at - time.time()) if self._os_sleep_scheduled else 0,
            "mode": self.config.os_sleep_mode,
            "timeout_seconds": self.config.os_sleep_timeout_seconds,
        }
        return base

    def mark_request(self) -> None:
        """标记一次请求活动（由中间件调用）。

        每次 API 请求到达时调用此方法，更新最后活跃时间。
        如果当前在休眠状态，触发唤醒。
        同时取消任何已安排的 OS 休眠倒计时。
        """
        self._last_request_time = time.time()

        # 如果在 OS 休眠倒计时中，取消它
        if self._os_sleep_scheduled:
            self._os_sleep_cancelled = True
            self._os_sleep_scheduled = False
            self._os_sleep_at = 0.0
            if self._os_sleep_task and not self._os_sleep_task.done():
                self._os_sleep_task.cancel()
                self._os_sleep_task = None
            logger.info("OS sleep countdown cancelled due to incoming request")

        if self._state == SystemState.SLEEPING:
            logger.info("Request detected while sleeping, triggering wake...")
            self._wake_event.set()

    async def force_sleep(self) -> bool:
        """强制立即进入休眠（跳过空闲超时等待）"""
        if self._state in (SystemState.SLEEPING, SystemState.PRE_SLEEP):
            return True

        if self._active_request_count >= self.config.min_active_requests_to_prevent_sleep:
            logger.warning(
                "Cannot sleep: %d active requests (threshold=%d)",
                self._active_request_count, self.config.min_active_requests_to_prevent_sleep,
            )
            return False

        await self._enter_sleep()
        return True

    async def force_wake(self) -> bool:
        """强制立即唤醒"""
        if self._state != SystemState.SLEEPING:
            return True

        await self._exit_sleep()
        return True

    async def run_state_machine(self) -> None:
        """启动后台状态机循环"""
        logger.info(
            "Sleep state machine started (idle_timeout=%ds)",
            self.config.idle_timeout_seconds,
        )
        while not self._shutdown_event.is_set():
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Sleep state machine error: %s", traceback.format_exc())
                await asyncio.sleep(5)

    async def stop(self) -> None:
        """停止状态机"""
        self._shutdown_event.set()
        if self._state_machine_task:
            self._state_machine_task.cancel()
        # 如果在休眠中，强制唤醒
        if self._state == SystemState.SLEEPING:
            await self._exit_sleep()

    # ── 状态机核心 ──────────────────────────────────

    async def _tick(self) -> None:
        """状态机的一次 tick"""
        current_state = self._state
        idle_seconds = time.time() - self._last_request_time

        if current_state == SystemState.IDLE:
            # 检查是否应该进入预休眠
            if idle_seconds >= self.config.idle_timeout_seconds - self.config.pre_sleep_warning_seconds:
                if self._active_request_count < self.config.min_active_requests_to_prevent_sleep:
                    self._set_state(SystemState.PRE_SLEEP)
                    logger.info(
                        "Entering pre-sleep (idle for %.0fs, %d active requests)",
                        idle_seconds, self._active_request_count,
                    )

            await asyncio.sleep(min(idle_seconds + 1, self.config.sleep_poll_interval))

        elif current_state == SystemState.PRE_SLEEP:
            # 等待预休眠期结束
            if idle_seconds >= self.config.idle_timeout_seconds:
                if self._active_request_count < self.config.min_active_requests_to_prevent_sleep:
                    await self._enter_sleep()
                else:
                    # 有活跃请求，回到 IDLE
                    logger.debug("Pre-sleep aborted: %d active requests", self._active_request_count)
                    self._set_state(SystemState.IDLE)
            else:
                # 在预休眠期间有新请求，回到 IDLE
                self._set_state(SystemState.IDLE)

            await asyncio.sleep(self.config.sleep_poll_interval)

        elif current_state == SystemState.SLEEPING:
            # 等待唤醒事件或定期检查
            try:
                await asyncio.wait_for(
                    self._wake_event.wait(),
                    timeout=self.config.sleep_poll_interval,
                )
                self._wake_event.clear()
                await self._exit_sleep()
            except asyncio.TimeoutError:
                pass  # 继续等待

        elif current_state == SystemState.WAKING:
            # 唤醒中，等待完成
            await asyncio.sleep(1)

        elif current_state == SystemState.ACTIVE:
            # 活跃状态，短暂检查后回到决策循环
            await asyncio.sleep(1)
            if idle_seconds < self.config.idle_timeout_seconds:
                self._set_state(SystemState.IDLE)

    async def _enter_sleep(self) -> None:
        """执行休眠操作"""
        if self._state == SystemState.SLEEPING:
            return

        logger.info("=" * 50)
        logger.info("Entering SLEEP mode...")
        self._set_state(SystemState.SLEEPING)
        self._sleep_start_time = time.time()
        self._sleep_count += 1

        # 1. 卸载 GPU 模型
        if self.config.unload_models_on_sleep:
            await self._unload_models()

        # 2. 降低 CPU 优先级
        if self.config.reduce_cpu_priority:
            self._lower_cpu_priority()

        # 3. 暂停非关键后台任务
        await self._pause_background_tasks()

        logger.info("System is now SLEEPING (sleep #%d)", self._sleep_count)

        # 安排 OS 级休眠（如果启用）
        if self.config.enable_os_sleep:
            await self.schedule_os_sleep()

        if self.config.on_sleep:
            try:
                self.config.on_sleep()
            except Exception:
                pass

    async def _exit_sleep(self) -> None:
        """执行唤醒操作"""
        if self._state not in (SystemState.SLEEPING, SystemState.WAKING):
            return

        logger.info("=" * 50)
        logger.info("WAKING from sleep...")
        self._set_state(SystemState.WAKING)

        # 取消 OS 休眠计划（如果有）
        await self.cancel_os_sleep()

        # 1. 恢复 CPU 优先级
        if self.config.reduce_cpu_priority:
            self._restore_cpu_priority()

        # 2. 重新加载模型
        if self.config.unload_models_on_sleep and self._models_were_loaded:
            await self._reload_models()

        # 3. 恢复后台任务
        await self._resume_background_tasks()

        # 记录休眠时长
        sleep_duration = time.time() - self._sleep_start_time
        self._total_sleep_duration += sleep_duration
        logger.info("System WOKE UP (slept for %.0fs, total sleep: %.0fs)",
                     sleep_duration, self._total_sleep_duration)

        self._set_state(SystemState.IDLE)

        if self.config.on_wake:
            try:
                self.config.on_wake()
            except Exception:
                pass

    def _set_state(self, new_state: SystemState) -> None:
        old = self._state
        self._state = new_state
        if old != new_state:
            logger.debug("Sleep state: %s → %s", old.value, new_state.value)
            if self.config.on_state_change:
                try:
                    self.config.on_state_change(old.value, new_state.value)
                except Exception:
                    pass
            # 发布事件
            self._publish_state_change(old.value, new_state.value)

    def _publish_state_change(self, old_state: str, new_state: str) -> None:
        """发布状态变更事件到事件总线"""
        try:
            from app.core.event_bus import get_event_bus
            bus = get_event_bus()
            if bus:
                bus.emit("standalone.sleep.state_change", {
                    "old_state": old_state,
                    "new_state": new_state,
                    "timestamp": time.time(),
                })
        except Exception:
            pass

    # ── OS 级休眠 ────────────────────────────────────

    def _get_os_sleep_command(self) -> list[str]:
        """获取当前平台的 OS 休眠命令。

        Returns:
            命令列表 [可执行文件, 参数...]

        支持的平台：
        - Windows: rundll32 (睡眠) / shutdown /h (休眠)
        - Linux: systemctl suspend
        - macOS: pmset sleepnow
        """
        system = platform.system()
        mode = self.config.os_sleep_mode

        if system == "Windows":
            if mode == "hibernate":
                return ["shutdown", "/h"]
            else:
                # 睡眠模式（默认）
                return ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
        elif system == "Linux":
            return ["systemctl", "suspend"]
        elif system == "Darwin":
            return ["pmset", "sleepnow"]
        else:
            logger.warning("OS sleep not supported on platform: %s", system)
            return []

    async def trigger_os_sleep(self) -> bool:
        """立即触发操作系统睡眠/休眠。

        这是一个不可逆的操作——操作系统挂起后，进程将停止响应。
        需要配合 Wake-on-LAN 或定时唤醒才能恢复。

        Returns:
            True 如果命令成功发出，False 如果平台不支持
        """
        cmd = self._get_os_sleep_command()
        if not cmd:
            return False

        logger.warning("=" * 60)
        logger.warning("TRIGGERING OS SLEEP — system will become unresponsive")
        logger.warning("  Platform: %s  Mode: %s", platform.system(), self.config.os_sleep_mode)
        logger.warning("  Command: %s", " ".join(cmd))
        logger.warning("  Wake-on-LAN must be configured to resume remotely")
        logger.warning("=" * 60)

        # 状态迁移
        self._set_state(SystemState.OS_SLEEPING)
        self._os_sleep_scheduled = False

        # 发布 OS 休眠事件
        try:
            from app.core.event_bus import get_event_bus
            bus = get_event_bus()
            if bus:
                bus.emit("standalone.sleep.os_sleep_triggered", {
                    "timestamp": time.time(),
                    "platform": platform.system(),
                    "mode": self.config.os_sleep_mode,
                })
        except Exception:
            pass

        # 短暂延迟让日志和事件发出
        await asyncio.sleep(0.5)

        # 执行系统命令
        try:
            import subprocess
            subprocess.run(cmd, check=False, capture_output=True)
        except Exception as e:
            logger.error("OS sleep command failed: %s", e)
            return False

        return True

    async def schedule_os_sleep(self) -> dict:
        """安排在应用级休眠 N 秒后触发 OS 休眠。

        调用时机：进入应用级休眠 (_enter_sleep) 后。
        """
        if not self.config.enable_os_sleep:
            return {"scheduled": False, "reason": "OS sleep disabled in config"}

        if self._os_sleep_scheduled:
            # 已经安排了
            return {
                "scheduled": True,
                "scheduled_at": self._os_sleep_at,
                "seconds_remaining": max(0, self._os_sleep_at - time.time()),
            }

        self._os_sleep_at = time.time() + self.config.os_sleep_timeout_seconds
        self._os_sleep_scheduled = True
        self._os_sleep_cancelled = False

        logger.info(
            "OS sleep scheduled in %.0fs (at %s)",
            self.config.os_sleep_timeout_seconds,
            time.strftime("%H:%M:%S", time.localtime(self._os_sleep_at)),
        )

        # 启动后台倒计时任务
        self._os_sleep_task = asyncio.create_task(self._os_sleep_countdown())

        return {
            "scheduled": True,
            "scheduled_at": self._os_sleep_at,
            "timeout_seconds": self.config.os_sleep_timeout_seconds,
            "mode": self.config.os_sleep_mode,
        }

    async def cancel_os_sleep(self) -> dict:
        """取消已安排的 OS 休眠倒计时。"""
        if not self._os_sleep_scheduled:
            return {"cancelled": False, "reason": "No OS sleep scheduled"}

        self._os_sleep_cancelled = True
        self._os_sleep_scheduled = False
        self._os_sleep_at = 0.0

        if self._os_sleep_task and not self._os_sleep_task.done():
            self._os_sleep_task.cancel()
            try:
                await self._os_sleep_task
            except asyncio.CancelledError:
                pass
        self._os_sleep_task = None

        logger.info("OS sleep schedule cancelled")
        return {"cancelled": True}

    def get_os_sleep_status(self) -> dict:
        """获取 OS 休眠计划状态。"""
        return {
            "enabled": self.config.enable_os_sleep,
            "scheduled": self._os_sleep_scheduled,
            "scheduled_at": self._os_sleep_at,
            "seconds_remaining": max(0, self._os_sleep_at - time.time()) if self._os_sleep_scheduled else 0,
            "mode": self.config.os_sleep_mode,
            "timeout_seconds": self.config.os_sleep_timeout_seconds,
            "platform": platform.system(),
        }

    async def _os_sleep_countdown(self) -> None:
        """OS 休眠倒计时后台任务。

        等待 os_sleep_timeout_seconds，到期后触发 OS 休眠。
        如果在倒计时期间收到了请求（触发 mark_request），则取消。
        """
        timeout = self.config.os_sleep_timeout_seconds
        warning_secs = self.config.os_sleep_warning_seconds

        try:
            # 等待主超时（减去警告时间）
            if timeout > warning_secs:
                await asyncio.sleep(timeout - warning_secs)

                # 发送预警告
                if not self._os_sleep_cancelled and self._os_sleep_scheduled:
                    logger.warning(
                        "OS sleep imminent in %.0fs — cancel by sending any API request",
                        warning_secs,
                    )
                    try:
                        from app.core.event_bus import get_event_bus
                        bus = get_event_bus()
                        if bus:
                            bus.emit("standalone.sleep.os_sleep_warning", {
                                "seconds_remaining": warning_secs,
                                "timestamp": time.time(),
                            })
                    except Exception:
                        pass

                # 等待剩余时间
                await asyncio.sleep(warning_secs)
            else:
                await asyncio.sleep(timeout)

            # 倒计时结束，触发 OS 休眠
            if not self._os_sleep_cancelled and self._os_sleep_scheduled:
                logger.info("OS sleep timeout reached, triggering OS suspend...")
                await self.trigger_os_sleep()

        except asyncio.CancelledError:
            logger.info("OS sleep countdown task cancelled")
        except Exception as e:
            logger.error("OS sleep countdown error: %s", e)

    # ── 模型管理操作 ────────────────────────────────

    async def _unload_models(self) -> None:
        """卸载已加载的模型以释放显存/内存"""
        self._models_were_loaded = []
        try:
            from app.core.model_router import get_model_router
            router = get_model_router()
            if router and hasattr(router, "loaded_models"):
                self._models_were_loaded = list(router.loaded_models.keys())
                for model_name in self._models_were_loaded:
                    try:
                        router.loaded_models.pop(model_name, None)
                        logger.info("Unloaded model: %s", model_name)
                    except Exception:
                        pass

            # 触发垃圾回收
            import gc
            gc.collect()

            # GPU 显存清理
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("GPU cache cleared")
            except ImportError:
                pass

        except Exception as e:
            logger.warning("Model unload error: %s", e)

    async def _reload_models(self) -> None:
        """重新加载之前卸载的模型"""
        if not self._models_were_loaded:
            return

        try:
            from app.core.model_router import get_model_router
            router = get_model_router()
            if router:
                for model_name in self._models_were_loaded:
                    try:
                        if hasattr(router, "load_model"):
                            await router.load_model(model_name)
                        logger.info("Reloaded model: %s", model_name)
                    except Exception as e:
                        logger.warning("Failed to reload model %s: %s", model_name, e)
        except Exception as e:
            logger.warning("Model reload error: %s", e)

    # ── CPU 优先级 ──────────────────────────────────

    def _lower_cpu_priority(self) -> None:
        """降低当前进程的 CPU 优先级"""
        if platform.system() != "Linux":
            return
        try:
            nice_val = self.config.cpu_nice_value
            self._original_nice = os.nice(0)
            os.nice(nice_val - self._original_nice)
            logger.info("CPU priority lowered (nice=%d)", os.nice(0))
        except Exception as e:
            logger.debug("CPU priority adjustment not supported: %s", e)

    def _restore_cpu_priority(self) -> None:
        """恢复 CPU 优先级"""
        if self._original_nice is None:
            return
        try:
            current = os.nice(0)
            os.nice(self._original_nice - current)
            logger.info("CPU priority restored (nice=%d)", os.nice(0))
        except Exception:
            pass
        self._original_nice = None

    # ── 后台任务管理 ────────────────────────────────

    async def _pause_background_tasks(self) -> None:
        """暂停非关键后台任务"""
        tasks_paused = []

        # 暂停 GPU 监控
        try:
            from app.core.gpu import get_gpu_monitor
            monitor = get_gpu_monitor()
            if monitor and getattr(monitor, "_running", False):
                await monitor.stop()
                tasks_paused.append("gpu_monitor")
        except Exception:
            pass

        # 暂停资源采集
        try:
            from app.core.resources import get_resource_collector
            collector = get_resource_collector()
            if collector and getattr(collector, "_running", False):
                await collector.stop()
                tasks_paused.append("resource_collector")
        except Exception:
            pass

        if tasks_paused:
            logger.info("Paused background tasks: %s", ", ".join(tasks_paused))

    async def _resume_background_tasks(self) -> None:
        """恢复后台任务"""
        tasks_resumed = []

        # 恢复 GPU 监控
        try:
            from app.core.gpu import get_gpu_monitor
            monitor = get_gpu_monitor()
            if monitor and not getattr(monitor, "_running", False):
                await monitor.start()
                tasks_resumed.append("gpu_monitor")
        except Exception:
            pass

        # 恢复资源采集
        try:
            from app.core.resources import get_resource_collector
            collector = get_resource_collector()
            if collector and not getattr(collector, "_running", False):
                await collector.start()
                tasks_resumed.append("resource_collector")
        except Exception:
            pass

        if tasks_resumed:
            logger.info("Resumed background tasks: %s", ", ".join(tasks_resumed))


# ── FastAPI 中间件适配 ──────────────────────────────


class SleepAwareMiddleware:
    """FastAPI 中间件 — 将每个请求注册到 SleepManager。

    使用方式：
        ```python
        app.add_middleware(SleepAwareMiddleware, sleep_manager=None)
        # 传入 None 时会自动查找全局单例（懒加载）
        ```
    """

    def __init__(self, app, sleep_manager: Optional[SmartSleepManager] = None) -> None:
        self.app = app
        self._sleep_manager = sleep_manager

    @property
    def sleep_manager(self) -> Optional[SmartSleepManager]:
        if self._sleep_manager is None:
            self._sleep_manager = get_sleep_manager()
        return self._sleep_manager

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        mgr = self.sleep_manager
        if mgr is not None:
            # 标记请求
            mgr.mark_request()
            # 增加活跃请求计数
            mgr._active_request_count += 1
            try:
                await self.app(scope, receive, send)
            finally:
                mgr._active_request_count = max(
                    0, mgr._active_request_count - 1
                )
        else:
            await self.app(scope, receive, send)


# ── 全局单例 ────────────────────────────────────────

_sleep_manager: Optional[SmartSleepManager] = None


def init_sleep_manager(config: SleepConfig | None = None) -> SmartSleepManager:
    global _sleep_manager
    if _sleep_manager is None:
        _sleep_manager = SmartSleepManager(config)
    return _sleep_manager


def get_sleep_manager() -> Optional[SmartSleepManager]:
    return _sleep_manager
