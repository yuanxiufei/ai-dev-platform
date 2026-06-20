"""
配置管理器 — 多配置路由与查詢

借鉴 AstrBot AstrBotConfigManager 设计：
- 支持多套配置（UUID-keyed），按 unified_msg_origin 路由
- 默认配置 fallback 机制
- 配置的 CRUD 操作
- 配置变更通知

使用方式：
    >>> mgr = ConfigManager({"default": {"model": "gpt-4"}})
    >>> cfg = mgr.get_config("chat_room_123")
    >>> cfg.get("model")
"""

from __future__ import annotations

import copy
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("platform.config_manager")


@dataclass
class ConfigInfo:
    """配置文件的元信息"""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    """配置唯一 ID"""
    name: str = "default"
    """配置名称"""
    path: str = ""
    """配置文件路径（如有）"""


class ConfigManager:
    """多配置管理器。

    管理多个配置文件，根据 unified_msg_origin (umo) 路由到对应配置。
    如果未找到特定配置，则回退到默认配置。

    配置路由规则：
    1. umo → 专用配置
    2. 未匹配 → 默认配置
    """

    def __init__(self, default_config: dict[str, Any] | None = None) -> None:
        # 所有配置映射: conf_id → config_dict
        self._confs: dict[str, dict[str, Any]] = {}

        # 配置元信息映射: conf_id → ConfigInfo
        self._conf_infos: dict[str, ConfigInfo] = {}

        # umo → conf_id 的路由映射
        self._umo_routing: dict[str, str] = {}

        # 默认配置
        default_id = uuid.uuid4().hex
        default_config = default_config or {}
        self._confs[default_id] = default_config
        self._conf_infos[default_id] = ConfigInfo(
            id=default_id, name="default"
        )
        self._default_id = default_id

        # 配置变更监听器
        self._on_change_callbacks: list[
            Callable[[str, dict[str, Any]], Awaitable[None]]
        ] = []

    # ── 配置路由 ─────────────────────────────────────

    def set_routing(self, umo: str, conf_id: str) -> None:
        """设置 umo → 配置的路由规则"""
        self._umo_routing[umo] = conf_id

    def remove_routing(self, umo: str) -> None:
        """移除 umo 的路由规则"""
        self._umo_routing.pop(umo, None)

    def get_config(self, umo: str | None = None) -> dict[str, Any]:
        """根据 umo 获取配置。

        路由规则：umo → 专用配置 → 默认配置 (fallback)
        """
        # 尝试 umo 路由
        if umo and umo in self._umo_routing:
            conf_id = self._umo_routing[umo]
            if conf_id in self._confs:
                return self._confs[conf_id]

        # fallback 到默认配置
        return self._confs.get(self._default_id, {})

    # ── 配置 CRUD ─────────────────────────────────────

    def create_config(
        self,
        config: dict[str, Any],
        name: str = "",
        umo_mapping: str | None = None,
    ) -> str:
        """创建新配置。

        Args:
            config: 配置字典
            name: 配置名称
            umo_mapping: 可选，将新配置绑定到指定 umo

        Returns:
            conf_id: 新配置的唯一 ID
        """
        conf_id = uuid.uuid4().hex
        self._confs[conf_id] = config
        self._conf_infos[conf_id] = ConfigInfo(
            id=conf_id, name=name or f"conf_{conf_id[:8]}"
        )
        if umo_mapping:
            self._umo_routing[umo_mapping] = conf_id
        logger.info(
            "Config created: id=%s name=%s", conf_id, name
        )
        return conf_id

    def delete_config(self, conf_id: str) -> None:
        """删除配置（不能删除默认配置）"""
        if conf_id == self._default_id:
            raise ValueError("Cannot delete default configuration")

        self._confs.pop(conf_id, None)
        self._conf_infos.pop(conf_id, None)
        # 清理路由
        self._umo_routing = {
            k: v for k, v in self._umo_routing.items() if v != conf_id
        }
        logger.info("Config deleted: id=%s", conf_id)

    def update_config(
        self, conf_id: str, config: dict[str, Any]
    ) -> None:
        """更新指定配置"""
        if conf_id not in self._confs:
            raise ValueError(f"Config not found: {conf_id}")
        self._confs[conf_id] = config
        logger.debug("Config updated: id=%s", conf_id)

    def update_config_info(self, conf_id: str, name: str) -> None:
        """更新配置元信息"""
        info = self._conf_infos.get(conf_id)
        if info:
            info.name = name

    # ── 查询接口 ────────────────────────────────────

    @property
    def default_config(self) -> dict[str, Any]:
        """返回默认配置"""
        return self._confs.get(self._default_id, {})

    @property
    def default_id(self) -> str:
        """返回默认配置 ID"""
        return self._default_id

    def get_config_info(self, umo: str | None = None) -> ConfigInfo:
        """获取 umo 对应的配置元信息"""
        conf_id = self._default_id
        if umo and umo in self._umo_routing:
            conf_id = self._umo_routing[umo]
        return self._conf_infos.get(conf_id, ConfigInfo())

    def list_configs(self) -> list[ConfigInfo]:
        """列出所有配置元信息"""
        return list(self._conf_infos.values())

    def get_config_by_id(self, conf_id: str) -> dict[str, Any] | None:
        """按 ID 获取配置"""
        return self._confs.get(conf_id)

    def get(self, umo: str | None, key: str, default: Any = None) -> Any:
        """便捷获取配置项。

        Args:
            umo: 消息来源
            key: 配置键
            default: 默认值
        """
        return self.get_config(umo).get(key, default)

    # ── 配置变更通知 ─────────────────────────────────

    def on_change(
        self,
        callback: Callable[[str, dict[str, Any]], Awaitable[None]],
    ) -> None:
        """注册配置变更监听器"""
        self._on_change_callbacks.append(callback)

    async def notify_change(self, conf_id: str) -> None:
        """通知所有监听器配置已变更"""
        config = self._confs.get(conf_id, {})
        for cb in self._on_change_callbacks:
            try:
                await cb(conf_id, config)
            except Exception as e:
                logger.error(
                    "Config change callback failed for '%s': %s",
                    conf_id, e,
                )
