"""
插件基类 — __init_subclass__ 自动注册

借鉴 AstrBot Star 基类的设计：
- 任何继承 Plugin 的子类都会在定义时自动注册到全局注册表
- 提供 initialize() / terminate() 生命周期钩子
- 提供便捷的日志、配置访问
"""

from __future__ import annotations

import logging
from typing import Any

from .metadata import PluginMetadata, plugin_map, plugin_registry

logger = logging.getLogger("platform.plugins")


class Plugin:
    """所有插件的父类，任何插件都应该继承此类。

    使用 __init_subclass__ 自动注册机制：
    子类在被 Python 解释器加载时自动将元数据写入 plugin_map 和 plugin_registry。

    Example:
        ```python
        class MyPlugin(Plugin):
            name = "my-plugin"
            author = "Alice"
            version = "1.0.0"
            desc = "An example plugin"

            async def initialize(self) -> None:
                logger.info(f"{self.name} loaded")

            async def terminate(self) -> None:
                logger.info(f"{self.name} unloaded")
        ```
    """

    # 子类应覆盖这些类属性
    name: str = ""
    """插件名称"""
    author: str = ""
    """插件作者"""
    version: str = "0.1.0"
    """插件版本"""
    desc: str = ""
    """插件简介"""
    display_name: str = ""
    """展示名称"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """子类被定义时自动注册到全局注册表。

        如果已有同模块路径的元数据，则更新类型引用；
        否则创建新的 PluginMetadata 并追加到 registry。
        """
        super().__init_subclass__(**kwargs)
        existing = plugin_map.get(cls.__module__)
        if existing is None:
            metadata = PluginMetadata(
                name=cls.name or cls.__name__,
                author=cls.author,
                version=cls.version,
                desc=cls.desc,
                display_name=cls.display_name or cls.name,
                plugin_cls_type=cls,
                module_path=cls.__module__,
            )
            plugin_map[cls.__module__] = metadata
            plugin_registry.append(metadata)
            logger.debug(
                "Plugin registered: %s (module=%s)",
                metadata.name,
                cls.__module__,
            )
        else:
            existing.plugin_cls_type = cls
            existing.module_path = cls.__module__
            logger.debug(
                "Plugin type updated: %s (module=%s)",
                existing.name,
                cls.__module__,
            )

    @property
    def config(self) -> dict[str, Any]:
        """获取插件配置"""
        return self._config

    def get_config(self, key: str, default: Any = None) -> Any:
        """安全获取配置项"""
        return self._config.get(key, default)

    async def initialize(self) -> None:
        """插件激活时调用。可重写以执行初始化逻辑。"""

    async def terminate(self) -> None:
        """插件禁用/重载时调用。可重写以执行清理逻辑。"""
