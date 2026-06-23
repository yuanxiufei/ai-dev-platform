"""
ProcessWatchdog — 自动崩溃修复守护进程

监控后端进程状态，当进程异常退出时自动重启恢复。
支持：
- 进程存活检测（PID + HTTP 健康检查）
- 指数退避重启策略
- 重启次数限制与冷却期
- 结构化日志与事件通知
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("standalone.watchdog")


class WatchdogState(Enum):
    """守护进程状态"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    RESTARTING = "restarting"
    COOLDOWN = "cooldown"
    FAILED = "failed"


@dataclass
class WatchdogConfig:
    """守护进程配置"""

    # 被监控的进程启动命令
    cmd: list[str] = field(default_factory=lambda: [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "0.0.0.0", "--port", "8000",
    ])
    # 工作目录
    cwd: str = ""
    # 环境变量
    env: dict[str, str] = field(default_factory=dict)

    # 健康检查 URL
    health_check_url: str = "http://127.0.0.1:8000/api/v1/utils/health-check/"
    # 健康检查间隔（秒）
    health_check_interval: float = 5.0
    # 健康检查超时（秒）
    health_check_timeout: float = 3.0
    # 启动后等待健康检查的最长时间（秒）
    startup_grace_period: float = 60.0

    # 最大重启次数（0 = 无限）
    max_restarts: int = 10
    # 冷却窗口：在 window_seconds 内达到 max_restarts 则冷却
    cooldown_window_seconds: float = 300.0
    # 冷却时间（秒）
    cooldown_seconds: float = 120.0

    # 重启间隔基础值（秒），实际使用指数退避
    restart_delay_base: float = 2.0
    # 最大重启间隔（秒）
    restart_delay_max: float = 60.0

    # 退出时是否清理子进程
    cleanup_children: bool = True

    # 事件回调
    on_state_change: Optional[Callable[[str, str], None]] = None  # (old_state, new_state)
    on_restart: Optional[Callable[[int], None]] = None             # (restart_count)


class ProcessWatchdog:
    """进程守护器 — 自动崩溃恢复。

    使用方式：
        ```python
        watchdog = ProcessWatchdog(WatchdogConfig(
            cmd=["python", "-m", "uvicorn", "app.main:app", "--port", "8000"],
            cwd="/path/to/backend",
        ))
        await watchdog.start()
        # ... 守护进程会在后台持续监控 ...
        await watchdog.stop()
        ```
    """

    def __init__(self, config: WatchdogConfig | None = None) -> None:
        self.config = config or WatchdogConfig()
        self._state: WatchdogState = WatchdogState.STOPPED
        self._process: Optional[subprocess.Popen] = None
        self._pid: Optional[int] = None
        self._restart_count: int = 0
        self._total_restarts: int = 0
        self._last_start_time: float = 0.0
        self._restart_times: list[float] = []  # 用于冷却窗口计算
        self._monitor_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._http_session = None

    # ── 公共 API ────────────────────────────────────

    @property
    def state(self) -> WatchdogState:
        return self._state

    @property
    def pid(self) -> Optional[int]:
        return self._pid

    @property
    def restart_count(self) -> int:
        return self._total_restarts

    @property
    def is_running(self) -> bool:
        return self._state == WatchdogState.RUNNING

    async def start(self) -> None:
        """启动守护进程（启动子进程 + 开始监控）"""
        if self._state != WatchdogState.STOPPED:
            logger.warning("Watchdog already %s, ignoring start()", self._state.value)
            return

        self._shutdown_event.clear()
        await self._start_process()

        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("ProcessWatchdog started (PID=%s)", self._pid)

    async def stop(self) -> None:
        """停止守护进程（终止子进程 + 停止监控）"""
        self._shutdown_event.set()
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None

        await self._kill_process()
        self._set_state(WatchdogState.STOPPED)
        logger.info("ProcessWatchdog stopped")

    async def restart(self) -> None:
        """手动重启被监控进程"""
        logger.info("Manual restart requested")
        await self._kill_process()
        await self._start_process()

    def get_status(self) -> dict:
        """获取当前状态摘要"""
        return {
            "state": self._state.value,
            "pid": self._pid,
            "restart_count": self._total_restarts,
            "uptime_seconds": time.time() - self._last_start_time if self._last_start_time else 0,
            "is_running": self.is_running,
        }

    # ── 内部实现 ────────────────────────────────────

    def _set_state(self, new_state: WatchdogState) -> None:
        old = self._state
        self._state = new_state
        if old != new_state and self.config.on_state_change:
            try:
                self.config.on_state_change(old.value, new_state.value)
            except Exception:
                pass

    async def _start_process(self) -> bool:
        """启动被监控进程"""
        self._set_state(WatchdogState.STARTING)

        cwd = self.config.cwd or os.getcwd()
        env = {**os.environ, **self.config.env}

        try:
            self._process = subprocess.Popen(
                self.config.cmd,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True if sys.platform != "win32" else False,
            )
            self._pid = self._process.pid
            self._last_start_time = time.time()
            logger.info("Process started: PID=%d, cmd=%s", self._pid, self.config.cmd)

            # 异步读取 stdout/stderr
            if self._process.stdout:
                asyncio.create_task(self._read_stdout(self._process.stdout))

            # 等待健康检查通过
            healthy = await self._wait_healthy()
            if healthy:
                self._set_state(WatchdogState.RUNNING)
                self._restart_count = 0
                logger.info("Process healthy (PID=%d)", self._pid)
                return True
            else:
                logger.warning("Process started but health check failed (PID=%d)", self._pid)
                self._set_state(WatchdogState.FAILED)
                return False

        except Exception as e:
            logger.error("Failed to start process: %s\n%s", e, traceback.format_exc())
            self._set_state(WatchdogState.FAILED)
            return False

    async def _wait_healthy(self) -> bool:
        """等待进程健康检查通过"""
        deadline = time.time() + self.config.startup_grace_period
        await asyncio.sleep(2.0)  # 初始等待

        while time.time() < deadline:
            if self._shutdown_event.is_set():
                return False
            if await self._check_health():
                return True
            await asyncio.sleep(self.config.health_check_interval)
        return False

    async def _check_health(self) -> bool:
        """执行一次 HTTP 健康检查"""
        try:
            import aiohttp
        except ImportError:
            # Fallback: 仅检查进程是否存活
            if self._process is None:
                return False
            return self._process.poll() is None

        if self._http_session is None:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self.config.health_check_timeout)
            self._http_session = aiohttp.ClientSession(timeout=timeout)

        try:
            async with self._http_session.get(self.config.health_check_url) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def _read_stdout(self, stdout) -> None:
        """异步读取子进程 stdout"""
        loop = asyncio.get_event_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, stdout.readline)
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").rstrip()
                if decoded:
                    logger.info("[app:%d] %s", self._pid or 0, decoded)
            except Exception:
                break

    async def _kill_process(self) -> None:
        """安全终止子进程"""
        if self._process is None:
            return

        pid = self._pid
        logger.info("Terminating process PID=%d...", pid)

        try:
            if sys.platform == "win32":
                self._process.terminate()
            else:
                os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass

        try:
            self._process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("Process PID=%d did not exit, force killing", pid)
            self._process.kill()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.error("Failed to kill process PID=%d", pid)

        self._process = None
        self._pid = None

    async def _restart_process(self) -> bool:
        """带策略的重启流程"""
        self._set_state(WatchdogState.RESTARTING)
        self._total_restarts += 1
        self._restart_count += 1
        now = time.time()

        # 记录重启时间戳用于冷却计算
        self._restart_times.append(now)
        self._restart_times = [t for t in self._restart_times
                               if now - t <= self.config.cooldown_window_seconds]

        # 检查是否需要冷却
        if self.config.max_restarts > 0 and len(self._restart_times) >= self.config.max_restarts:
            logger.warning(
                "Restart threshold reached (%d in %ds), entering cooldown",
                len(self._restart_times), self.config.cooldown_window_seconds,
            )
            self._set_state(WatchdogState.COOLDOWN)
            await asyncio.sleep(self.config.cooldown_seconds)
            self._restart_times.clear()
            self._restart_count = 0

        # 指数退避等待
        delay = min(
            self.config.restart_delay_base * (2 ** min(self._restart_count - 1, 5)),
            self.config.restart_delay_max,
        )
        logger.info(
            "Restarting in %.1fs (attempt #%d, total #%d)...",
            delay, self._restart_count, self._total_restarts,
        )
        await asyncio.sleep(delay)

        # 触发回调
        if self.config.on_restart:
            try:
                self.config.on_restart(self._restart_count)
            except Exception:
                pass

        return await self._start_process()

    async def _monitor_loop(self) -> None:
        """主监控循环"""
        while not self._shutdown_event.is_set():
            try:
                if self._state == WatchdogState.COOLDOWN:
                    await asyncio.sleep(1)
                    continue

                # 检查进程是否存活
                if self._process is not None:
                    returncode = self._process.poll()
                    if returncode is not None:
                        logger.warning(
                            "Process PID=%d exited with code %d",
                            self._pid, returncode,
                        )
                        self._process = None
                        self._pid = None

                        if not self._shutdown_event.is_set():
                            await self._restart_process()
                    elif self._state == WatchdogState.RUNNING:
                        # 周期性健康检查
                        if not await self._check_health():
                            logger.warning("Health check failed for PID=%d", self._pid)
                            await self._kill_process()
                            if not self._shutdown_event.is_set():
                                await self._restart_process()

                await asyncio.sleep(self.config.health_check_interval)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.error("Monitor loop error: %s", traceback.format_exc())
                await asyncio.sleep(5)

        # 清理 HTTP session
        if self._http_session:
            await self._http_session.close()
            self._http_session = None


# ── 便捷函数 ────────────────────────────────────────

def create_backend_watchdog(
    backend_dir: str = "",
    host: str = "0.0.0.0",
    port: int = 8000,
    env: dict[str, str] | None = None,
) -> ProcessWatchdog:
    """创建监控 FastAPI 后端的守护进程。

    Args:
        backend_dir: 后端代码目录（默认自动推断）
        host: 监听地址
        port: 监听端口
        env: 额外的环境变量
    """
    if not backend_dir:
        # 自动推断：从本文件位置推算 backend 目录
        backend_dir = str(Path(__file__).resolve().parent.parent.parent.parent)

    config = WatchdogConfig(
        cmd=[
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", host,
            "--port", str(port),
            "--log-level", "info",
        ],
        cwd=backend_dir,
        env=env or {},
        health_check_url=f"http://127.0.0.1:{port}/api/v1/utils/health-check/",
    )
    return ProcessWatchdog(config)
