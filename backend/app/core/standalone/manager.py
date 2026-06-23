"""
StandaloneManager — 统一独立运行协调器

协调四大子系统：
1. ProcessWatchdog  — 进程崩溃自动恢复
2. ApiAuthMiddleware — API Key 远程鉴权
3. SmartSleepManager — 智能休眠/唤醒
4. StateSwitch      — 全局功能开关

作为 FastAPI lifespan 的一环，在 startup/shutdown 统一管理。
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.core.standalone.watchdog import (
    ProcessWatchdog, WatchdogConfig, WatchdogState,
)
from app.core.standalone.api_auth import (
    ApiAuthConfig, RemoteApiKeyManager,
    init_remote_key_manager, get_remote_key_manager,
)
from app.core.standalone.sleep_manager import (
    SmartSleepManager, SleepConfig, SleepAwareMiddleware, SystemState,
    init_sleep_manager, get_sleep_manager,
)
from app.core.standalone.state_switch import (
    StateSwitch, FeatureToggles, FeatureKey,
    init_state_switch, get_state_switch,
)
from app.core.standalone.wol_manager import (
    WakeOnLANManager, WOLConfig,
    init_wol_manager, get_wol_manager,
)

logger = logging.getLogger("standalone.manager")


@dataclass
class StandaloneConfig:
    """独立运行总体配置"""

    # ── 守护进程 ──
    watchdog_enabled: bool = True
    watchdog_config: Optional[WatchdogConfig] = None

    # ── API 鉴权 ──
    api_auth_enabled: bool = True
    api_auth_config: Optional[ApiAuthConfig] = None

    # ── 智能休眠 ──
    smart_sleep_enabled: bool = True
    sleep_config: Optional[SleepConfig] = None

    # ── 状态开关 ──
    state_switch_enabled: bool = True
    state_persist_path: str = "data/standalone_state.json"

    # ── 启动选项 ──
    auto_start_watchdog: bool = True
    auto_start_sleep_manager: bool = True
    bind_host: str = "0.0.0.0"
    bind_port: int = 8000


class StandaloneManager:
    """独立运行统一管理器。

    使用方式 — 在 FastAPI lifespan 中：
        ```python
        manager = StandaloneManager()
        await manager.setup(app)

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            await manager.startup()
            yield
            await manager.shutdown()
        ```
    """

    def __init__(self, config: StandaloneConfig | None = None) -> None:
        self.config = config or StandaloneConfig()
        self._watchdog: Optional[ProcessWatchdog] = None
        self._api_auth_middleware: Optional[ApiAuthMiddleware] = None
        self._sleep_manager: Optional[SmartSleepManager] = None
        self._wol_manager: Optional[WakeOnLANManager] = None
        self._state_switch: Optional[StateSwitch] = None
        self._key_manager: Optional[RemoteApiKeyManager] = None
        self._sleep_state_task: Optional[asyncio.Task] = None
        self._started = False

    # ── 生命周期 ────────────────────────────────────

    async def setup(self, app) -> None:
        """在创建 FastAPI app 后调用，注入中间件和状态开关。

        Args:
            app: FastAPI application instance
        """
        logger.info("=" * 60)
        logger.info("StandaloneManager: setting up...")
        logger.info("=" * 60)

        # 1. 初始化状态开关（最先，因为其他模块依赖它）
        if self.config.state_switch_enabled:
            self._state_switch = init_state_switch(
                persist_path=self.config.state_persist_path,
            )
            logger.info("  [state-switch] initialized (%d features)",
                        len(self._state_switch._features))

        # 2. 初始化 API Key 管理器
        if self.config.api_auth_enabled:
            self._key_manager = init_remote_key_manager()
            logger.info("  [api-auth] key manager initialized (%s)",
                        "enabled" if self.config.api_auth_enabled else "disabled")

        # 3. 初始化智能休眠管理器
        if self.config.smart_sleep_enabled:
            sleep_cfg = self.config.sleep_config or SleepConfig()
            self._sleep_manager = init_sleep_manager(sleep_cfg)
            logger.info("  [sleep] manager initialized (idle_timeout=%ds)",
                        sleep_cfg.idle_timeout_seconds)

            # 将状态开关回调绑定到休眠管理器
            if self._state_switch:
                sleep_feature = FeatureToggles.SMART_SLEEP
                sleep_feature.on_change = self._on_sleep_toggle
                logger.info("  [sleep] bound to StateSwitch")

        # 4. 初始化 Wake-on-LAN 管理器
        if self.config.smart_sleep_enabled:
            self._wol_manager = await init_wol_manager()
            logger.info("  [wol] manager initialized — MAC=%s", self._wol_manager.config.target_mac)

        # 5. 初始化守护进程
        if self.config.watchdog_enabled:
            wd_config = self.config.watchdog_config or WatchdogConfig(
                cmd=[
                    os.sys.executable, "-m", "uvicorn", "app.main:app",
                    "--host", self.config.bind_host,
                    "--port", str(self.config.bind_port),
                    "--log-level", "info",
                ],
                cwd=os.getcwd(),
            )
            self._watchdog = ProcessWatchdog(wd_config)

            # 绑定状态变更回调
            self._watchdog.config.on_state_change = self._on_watchdog_state_change
            self._watchdog.config.on_restart = self._on_watchdog_restart

            logger.info("  [watchdog] configured (cmd=%s)", wd_config.cmd)

        logger.info("StandaloneManager setup complete")

    async def startup(self) -> None:
        """启动所有子系统（在 FastAPI lifespan startup）"""
        if self._started:
            logger.warning("StandaloneManager already started")
            return

        logger.info("=" * 60)
        logger.info("StandaloneManager: starting...")
        logger.info("=" * 60)

        # 检查状态开关来决定哪些子系统启动
        sleep_enabled = self._is_feature_enabled(FeatureKey.SMART_SLEEP)
        watchdog_enabled = self._is_feature_enabled(FeatureKey.WATCHDOG)

        # 启动智能休眠
        if self._sleep_manager and sleep_enabled and self.config.auto_start_sleep_manager:
            self._sleep_state_task = asyncio.create_task(
                self._sleep_manager.run_state_machine()
            )
            logger.info("  [sleep] state machine started")

        # 启动守护进程（注意：守护进程会在子进程中启动应用，此处仅记录）
        if self._watchdog and watchdog_enabled and self.config.auto_start_watchdog:
            logger.info(
                "  [watchdog] ready — call manager.activate_watchdog() in standalone mode "
                "or start via the standalone launcher script"
            )
            # 守护进程需要从外部脚本启动，这里不启动它
            # 因为 FastAPI 在他自己的进程里运行，守护进程作为父进程管理

        # 注册事件总线监听
        try:
            from app.core.event_bus import get_event_bus
            bus = get_event_bus()
            if bus:
                bus.subscribe("standalone.*", self._on_event_bus_message)
                logger.info("  [events] subscribed to standalone.*")
        except Exception:
            pass

        self._started = True
        logger.info("StandaloneManager startup complete. System ready.")

    async def shutdown(self) -> None:
        """停止所有子系统"""
        logger.info("=" * 60)
        logger.info("StandaloneManager: shutting down...")
        logger.info("=" * 60)

        if self._sleep_manager:
            await self._sleep_manager.stop()
            logger.info("  [sleep] stopped")

        if self._sleep_state_task:
            self._sleep_state_task.cancel()
            try:
                await self._sleep_state_task
            except asyncio.CancelledError:
                pass

        if self._watchdog:
            await self._watchdog.stop()
            logger.info("  [watchdog] stopped")

        self._started = False
        logger.info("StandaloneManager shutdown complete")

    # ── 状态查询 ────────────────────────────────────

    def get_status(self) -> dict:
        """获取完整系统状态"""
        status = {
            "version": "1.0.0",
            "started": self._started,
            "timestamp": time.time(),
            "subsystems": {},
        }

        if self._state_switch:
            status["features"] = self._state_switch.list_all()

        if self._watchdog:
            status["subsystems"]["watchdog"] = self._watchdog.get_status()

        if self._sleep_manager:
            status["subsystems"]["sleep"] = self._sleep_manager.stats

        if self._key_manager:
            status["subsystems"]["api_auth"] = {
                "active_keys": self._key_manager.count(),
            }

        if self._wol_manager:
            status["subsystems"]["wol"] = self._wol_manager.get_info()

        return status

    # ── 回调 ────────────────────────────────────────

    def _on_watchdog_state_change(self, old_state: str, new_state: str) -> None:
        logger.info("[watchdog] state: %s → %s", old_state, new_state)

    def _on_watchdog_restart(self, restart_count: int) -> None:
        logger.warning("[watchdog] restart #%d triggered", restart_count)
        # 可通过事件总线通知
        try:
            from app.core.event_bus import get_event_bus
            bus = get_event_bus()
            if bus:
                bus.emit("standalone.watchdog.restart", {
                    "restart_count": restart_count,
                    "timestamp": time.time(),
                })
        except Exception:
            pass

    async def _on_sleep_toggle(self, enabled: bool) -> None:
        """状态开关控制休眠的回调"""
        if self._sleep_manager:
            if not enabled and self._sleep_manager.is_sleeping:
                logger.info("Sleep disabled via switch, forcing wake")
                await self._sleep_manager.force_wake()
            elif enabled:
                logger.info("Sleep re-enabled via switch")

    def _on_event_bus_message(self, message: dict) -> None:
        """处理事件总线消息"""
        event_type = message.get("type", "")
        logger.debug("[events] %s: %s", event_type, message)

    def _is_feature_enabled(self, key: FeatureKey) -> bool:
        if self._state_switch:
            return self._state_switch.is_enabled(key)
        return True  # 没有开关则默认启用

    # ── 手动控制 ────────────────────────────────────

    async def activate_watchdog(self) -> None:
        """手动激活守护进程（从外部脚本调用）"""
        if self._watchdog:
            await self._watchdog.start()

    async def force_sleep(self) -> bool:
        """强制进入休眠"""
        if self._sleep_manager:
            return await self._sleep_manager.force_sleep()
        return False

    async def force_wake(self) -> bool:
        """强制唤醒"""
        if self._sleep_manager:
            return await self._sleep_manager.force_wake()
        return False

    def create_api_key(self, tenant: str = "default", name: str = "",
                       roles: list[str] | None = None) -> dict:
        """创建远程 API Key"""
        if self._key_manager:
            return self._key_manager.create_remote_key(
                tenant=tenant, name=name, roles=roles,
            )
        raise RuntimeError("API key manager not initialized")

    def list_api_keys(self) -> list[dict]:
        """列出所有 API Key"""
        if self._key_manager:
            return self._key_manager.list_keys()
        return []

    async def revoke_api_key(self, hashed_key: str) -> bool:
        """撤销 API Key"""
        if self._key_manager:
            return self._key_manager.revoke_key(hashed_key)
        return False

    async def toggle_feature(self, key: str) -> Optional[bool]:
        """切换特征状态"""
        if self._state_switch:
            return await self._state_switch.toggle(key)
        return None

    async def set_feature(self, key: str, enabled: bool) -> bool:
        """设置特征状态"""
        if self._state_switch:
            return await self._state_switch.set(key, enabled)
        return False

    # ── OS 休眠控制 ─────────────────────────────────

    async def trigger_os_sleep(self) -> bool:
        """立即触发操作系统睡眠/休眠"""
        if self._sleep_manager:
            return await self._sleep_manager.trigger_os_sleep()
        return False

    async def cancel_os_sleep(self) -> dict:
        """取消已安排的 OS 休眠"""
        if self._sleep_manager:
            return await self._sleep_manager.cancel_os_sleep()
        return {"cancelled": False, "reason": "Sleep manager not initialized"}

    def get_os_sleep_status(self) -> dict:
        """获取 OS 休眠计划状态"""
        if self._sleep_manager:
            return self._sleep_manager.get_os_sleep_status()
        return {"enabled": False, "scheduled": False, "reason": "Sleep manager not initialized"}

    # ── Wake-on-LAN 控制 ──────────────────────────

    async def get_wol_info(self) -> dict:
        """获取 WOL 配置信息"""
        if self._wol_manager:
            return self._wol_manager.get_info()
        return {"error": "WOL manager not initialized"}

    async def send_wol(self, mac_address: str = "", broadcast: str = "", port: int = 0) -> dict:
        """发送 WOL 魔术包。

        Args:
            mac_address: 目标 MAC（为空则使用本机检测到的 MAC）
            broadcast: 广播地址（为空则使用配置的地址）
            port: UDP 端口（为 0 则使用配置的端口）
        """
        if not self._wol_manager:
            return {"success": False, "message": "WOL manager not initialized"}

        # 如果指定了目标 MAC，发送到指定地址
        if mac_address:
            bc = broadcast or self._wol_manager.config.broadcast_address
            p = port or self._wol_manager.config.port
            return await self._wol_manager.send_to(mac_address, bc, p)

        # 否则发送到本机
        return await self._wol_manager.send()

    async def configure_wol(self, target_mac: str = "", broadcast_address: str = "", port: int = 0) -> dict:
        """配置 WOL 参数"""
        if self._wol_manager:
            return await self._wol_manager.configure(target_mac, broadcast_address, port)
        return {"error": "WOL manager not initialized"}

    async def redetect_wol(self) -> dict:
        """重新检测网络接口"""
        if self._wol_manager:
            return await self._wol_manager.detect()
        return {"error": "WOL manager not initialized"}


# ── 全局单例 ────────────────────────────────────────

_standalone_manager: Optional[StandaloneManager] = None


def init_standalone_manager(
    config: StandaloneConfig | None = None,
    app=None,
) -> StandaloneManager:
    """初始化 StandaloneManager 单例。

    Args:
        config: 配置对象
        app: FastAPI 应用实例（如果传入，同时注入中间件）

    Returns:
        StandaloneManager 实例
    """
    global _standalone_manager
    if _standalone_manager is None:
        _standalone_manager = StandaloneManager(config)
        logger.info("StandaloneManager singleton created")
    return _standalone_manager


def get_standalone_manager() -> Optional[StandaloneManager]:
    return _standalone_manager
