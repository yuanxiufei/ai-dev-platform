"""
StateSwitch — 全局状态开关控制

提供全局开关来启用或禁用智能休眠等机制，防止在本机正在使用时因自动休眠
或后台唤醒抢占资源而引发冲突或问题。

特性：
- 多特征开关（休眠、鉴权、守护等）
- 运行时热切换（无需重启）
- 持久化到文件（JSON）
- 环境变量覆盖
- API 接口管理
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger("standalone.state_switch")


class FeatureKey(str, Enum):
    """可切换的功能特征"""
    # 智能休眠
    SMART_SLEEP = "smart_sleep"
    # API 鉴权
    API_AUTH = "api_auth"
    # 守护进程
    WATCHDOG = "watchdog"
    # GPU 加速
    GPU_ENABLED = "gpu_enabled"
    # 远程访问
    REMOTE_ACCESS = "remote_access"
    # 自动优化
    AUTO_OPTIMIZE = "auto_optimize"
    # 后台任务
    BACKGROUND_TASKS = "background_tasks"
    # 模型自动下载
    AUTO_DOWNLOAD_MODELS = "auto_download_models"
    # OS 级休眠（在应用休眠后触发操作系统睡眠/休眠）
    OS_SLEEP = "os_sleep"


@dataclass
class FeatureDefinition:
    """特征定义"""
    key: str
    name: str
    description: str
    enabled: bool = True
    # 是否可以通过 API 切换
    dynamic: bool = True
    # 环境变量覆盖（如果设置，则不可动态切换）
    env_override: str = ""
    # 变更回调
    on_change: Optional[Callable[[bool], None]] = None


class StateSwitch:
    """全局状态开关管理器。

    核心逻辑：
    - 维护一组 FeatureDefinition
    - 运行时热切换，无需重启
    - 变更持久化到本地 JSON 文件
    - 支持环境变量强制覆盖

    使用方式：
        ```python
        switch = StateSwitch()

        # 注册特征
        switch.register(FeatureDefinition(
            key="smart_sleep",
            name="智能休眠",
            description="空闲时自动进入低功耗休眠",
            enabled=True,
        ))

        # 查询状态
        if switch.is_enabled("smart_sleep"):
            sleep_mgr.force_sleep()

        # 切换状态
        switch.toggle("smart_sleep")  # 翻转
        switch.set("smart_sleep", False)  # 显式设置
        ```
    """

    def __init__(self, persist_path: str = "data/standalone_state.json") -> None:
        self._features: dict[str, FeatureDefinition] = {}
        self._persist_path = persist_path
        self._lock = None  # asyncio lock, 懒加载

    def _get_lock(self):
        import asyncio
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def register(self, feature: FeatureDefinition) -> None:
        """注册一个可切换特征"""
        # 检查环境变量覆盖
        if feature.env_override:
            env_val = os.getenv(feature.env_override)
            if env_val is not None:
                feature.enabled = env_val.lower() in ("1", "true", "yes", "on")
                feature.dynamic = False
                logger.info(
                    "Feature '%s' overridden by env %s=%s (locked)",
                    feature.key, feature.env_override, feature.enabled,
                )

        self._features[feature.key] = feature

    def is_enabled(self, key: str) -> bool:
        """查询特征是否启用"""
        feature = self._features.get(key)
        if feature is None:
            logger.warning("Feature '%s' not registered, assuming disabled", key)
            return False
        return feature.enabled

    def get(self, key: str) -> Optional[FeatureDefinition]:
        """获取特征定义"""
        return self._features.get(key)

    async def set(self, key: str, enabled: bool) -> bool:
        """设置特征状态"""
        feature = self._features.get(key)
        if feature is None:
            return False
        if not feature.dynamic:
            logger.warning("Feature '%s' is not dynamic, cannot change", key)
            return False

        old = feature.enabled
        if old == enabled:
            return True

        async with self._get_lock():
            feature.enabled = enabled
            logger.info("Feature '%s': %s → %s", key, old, enabled)

            # 触发回调
            if feature.on_change:
                try:
                    if callable(feature.on_change):
                        result = feature.on_change(enabled)
                        import inspect
                        if inspect.iscoroutine(result):
                            await result
                except Exception as e:
                    logger.error("Feature '%s' onChange error: %s", key, e)

            # 持久化
            self._persist()

        return True

    async def toggle(self, key: str) -> Optional[bool]:
        """翻转特征状态，返回新状态"""
        feature = self._features.get(key)
        if feature is None:
            return None
        new_state = not feature.enabled
        if await self.set(key, new_state):
            return new_state
        return None

    def list_all(self) -> list[dict]:
        """列出所有特征及其状态"""
        return [
            {
                "key": f.key,
                "name": f.name,
                "description": f.description,
                "enabled": f.enabled,
                "dynamic": f.dynamic,
                "env_override": f.env_override or None,
            }
            for f in self._features.values()
        ]

    def export(self) -> dict[str, bool]:
        """导出所有特征状态"""
        return {k: f.enabled for k, f in self._features.items()}

    def _persist(self) -> None:
        """持久化到文件"""
        try:
            path = Path(self._persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "features": {k: f.enabled for k, f in self._features.items()},
                "updated_at": time.time(),
            }
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to persist state: %s", e)

    def load_persisted(self) -> None:
        """从持久化文件恢复状态"""
        try:
            path = Path(self._persist_path)
            if not path.exists():
                return

            data = json.loads(path.read_text(encoding="utf-8"))
            features = data.get("features", {})
            for key, enabled in features.items():
                feature = self._features.get(key)
                if feature and feature.dynamic:
                    feature.enabled = enabled
                    logger.debug("Restored feature '%s' = %s from %s", key, enabled, path)
        except Exception as e:
            logger.warning("Failed to load persisted state: %s", e)


# ── 预定义特征集 ────────────────────────────────────


class FeatureToggles:
    """预定义的可切换特征集合"""

    SMART_SLEEP = FeatureDefinition(
        key=FeatureKey.SMART_SLEEP,
        name="智能休眠",
        description="空闲时自动进入低功耗休眠状态，收到请求时自动唤醒",
        enabled=True,
        dynamic=True,
        env_override="STANDALONE_SMART_SLEEP_ENABLED",
    )

    API_AUTH = FeatureDefinition(
        key=FeatureKey.API_AUTH,
        name="API 鉴权",
        description="启用 API Key 鉴权中间件，要求外部调用提供有效密钥",
        enabled=True,
        dynamic=True,
        env_override="STANDALONE_API_AUTH_ENABLED",
    )

    WATCHDOG = FeatureDefinition(
        key=FeatureKey.WATCHDOG,
        name="守护进程",
        description="监控后端进程，崩溃时自动重启恢复",
        enabled=True,
        dynamic=True,
        env_override="STANDALONE_WATCHDOG_ENABLED",
    )

    GPU_ENABLED = FeatureDefinition(
        key=FeatureKey.GPU_ENABLED,
        name="GPU 加速",
        description="启用 GPU 加速进行模型推理",
        enabled=True,
        dynamic=True,
    )

    REMOTE_ACCESS = FeatureDefinition(
        key=FeatureKey.REMOTE_ACCESS,
        name="远程访问",
        description="允许外部网络访问本机 API 服务",
        enabled=True,
        dynamic=True,
        env_override="STANDALONE_REMOTE_ACCESS_ENABLED",
    )

    AUTO_OPTIMIZE = FeatureDefinition(
        key=FeatureKey.AUTO_OPTIMIZE,
        name="自动优化",
        description="后台自动进行模型优化（量化、剪枝等）",
        enabled=False,
        dynamic=True,
        env_override="STANDALONE_AUTO_OPTIMIZE_ENABLED",
    )

    BACKGROUND_TASKS = FeatureDefinition(
        key=FeatureKey.BACKGROUND_TASKS,
        name="后台任务",
        description="允许执行后台任务（资源采集、GPU 监控等）",
        enabled=True,
        dynamic=True,
    )

    OS_SLEEP = FeatureDefinition(
        key=FeatureKey.OS_SLEEP,
        name="系统省电休眠",
        description="应用休眠持续一定时间后，自动触发操作系统睡眠/休眠以节约电力。需配置 Wake-on-LAN 实现远程唤醒",
        enabled=True,
        dynamic=True,
        env_override="STANDALONE_OS_SLEEP_ENABLED",
    )

    ALL = [
        SMART_SLEEP,
        API_AUTH,
        WATCHDOG,
        GPU_ENABLED,
        REMOTE_ACCESS,
        AUTO_OPTIMIZE,
        BACKGROUND_TASKS,
        OS_SLEEP,
    ]


# ── 全局单例 ────────────────────────────────────────

_state_switch: Optional[StateSwitch] = None


def init_state_switch(persist_path: str = "data/standalone_state.json") -> StateSwitch:
    global _state_switch
    if _state_switch is None:
        _state_switch = StateSwitch(persist_path=persist_path)
        # 注册所有预定义特征
        for feature in FeatureToggles.ALL:
            _state_switch.register(feature)
        # 从持久化文件恢复
        _state_switch.load_persisted()
        logger.info("StateSwitch initialized with %d features", len(_state_switch._features))
    return _state_switch


def get_state_switch() -> Optional[StateSwitch]:
    return _state_switch


# ── 便捷函数 ────────────────────────────────────────


def get_feature_state(key: str) -> Optional[bool]:
    """便捷接口：获取特征状态"""
    switch = get_state_switch()
    if switch is None:
        return None
    return switch.is_enabled(key)


async def set_feature_state(key: str, enabled: bool) -> bool:
    """便捷接口：设置特征状态"""
    switch = get_state_switch()
    if switch is None:
        return False
    return await switch.set(key, enabled)


def list_feature_states() -> list[dict]:
    """便捷接口：列出所有特征状态"""
    switch = get_state_switch()
    if switch is None:
        return []
    return switch.list_all()
