"""
插件系统 — 可扩展的插件架构

借鉴 AstrBot star/ 架构：
- Plugin: 插件基类（__init_subclass__ 自动注册）
- PluginMetadata: 插件元数据 dataclass
- PluginManager: 插件生命周期管理器
- EventType: 平台内部事件类型枚举
- HandlerRegistry: 事件驱动的 Handler 注册表
"""

from .base import Plugin  # noqa: F401
from .metadata import (  # noqa: F401
    PluginMetadata,
    plugin_registry,
    plugin_map,
)
from .manager import PluginManager  # noqa: F401
from .handler import (  # noqa: F401
    EventType,
    HandlerMetadata,
    HandlerRegistry,
    handler_registry,
)
