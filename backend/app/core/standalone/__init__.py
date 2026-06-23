"""
Standalone Runtime Module — 无需 Docker 的独立运行方案

提供五大核心能力：
1. ProcessWatchdog  — 自动崩溃修复（守护进程）
2. ApiAuthMiddleware — API Key 远程鉴权
3. SmartSleepManager — 智能休眠与唤醒
4. WakeOnLANManager — 远程唤醒（WOL 魔术包）
5. StateSwitch       — 全局状态开关控制
"""

from app.core.standalone.watchdog import ProcessWatchdog, WatchdogConfig
from app.core.standalone.api_auth import (
    ApiAuthMiddleware,
    ApiAuthConfig,
    RemoteApiKeyManager,
    require_api_key,
)
from app.core.standalone.sleep_manager import (
    SmartSleepManager,
    SleepConfig,
    SystemState,
)
from app.core.standalone.state_switch import (
    StateSwitch,
    FeatureToggles,
    get_feature_state,
    set_feature_state,
    list_feature_states,
)
from app.core.standalone.wol_manager import (
    WakeOnLANManager,
    WOLConfig,
    send_magic_packet,
    build_magic_packet,
    init_wol_manager,
    get_wol_manager,
)
from app.core.standalone.manager import StandaloneManager, StandaloneConfig

__all__ = [
    # Watchdog
    "ProcessWatchdog",
    "WatchdogConfig",
    # API Auth
    "ApiAuthMiddleware",
    "ApiAuthConfig",
    "RemoteApiKeyManager",
    "require_api_key",
    # Sleep
    "SmartSleepManager",
    "SleepConfig",
    "SystemState",
    # Wake-on-LAN
    "WakeOnLANManager",
    "WOLConfig",
    "send_magic_packet",
    "build_magic_packet",
    "init_wol_manager",
    "get_wol_manager",
    # State Switch
    "StateSwitch",
    "FeatureToggles",
    "get_feature_state",
    "set_feature_state",
    "list_feature_states",
    # Manager
    "StandaloneManager",
    "StandaloneConfig",
]
