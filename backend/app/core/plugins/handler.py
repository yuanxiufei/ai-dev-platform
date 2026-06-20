"""
Handler 注册表与事件类型定义

借鉴 AstrBot star_handler.py 设计：
- EventType 枚举：定义平台内部事件类型
- StarHandlerMetadata: Handler 元数据 dataclass
- StarHandlerRegistry: 按事件类型/优先级有序管理 Handlers
- 全局单例 star_handlers_registry
"""

from __future__ import annotations

import enum
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Generic, Literal, TypeVar, overload

from .metadata import plugin_map

H = TypeVar("H", bound=Callable[..., Any])
T = TypeVar("T", bound="HandlerMetadata")


class EventType(enum.Enum):
    """平台内部事件类型枚举。

    用于对 Handler 按职能分组，不同事件类型触发不同阶段的 Handler 执行。
    """

    # ── 生命周期事件 ──
    OnPlatformLoadedEvent = enum.auto()
    """平台加载完成"""
    OnPluginLoadedEvent = enum.auto()
    """插件加载完成"""
    OnPluginUnloadedEvent = enum.auto()
    """插件卸载完成"""

    # ── 请求/响应事件 ──
    OnRequestReceivedEvent = enum.auto()
    """收到用户请求"""
    OnLLMRequestEvent = enum.auto()
    """即将调用 LLM"""
    OnLLMResponseEvent = enum.auto()
    """LLM 响应后"""
    OnBeforeSendEvent = enum.auto()
    """发送响应前（装饰结果）"""
    OnAfterSendEvent = enum.auto()
    """发送响应后"""

    # ── Agent 事件 ──
    OnAgentBeginEvent = enum.auto()
    """Agent 开始运行"""
    OnAgentStepEvent = enum.auto()
    """Agent 单步完成"""
    OnAgentDoneEvent = enum.auto()
    """Agent 运行完成"""

    # ── 工具调用事件 ──
    OnToolCallStartEvent = enum.auto()
    """工具调用开始"""
    OnToolCallEndEvent = enum.auto()
    """工具调用结束"""

    # ── 错误事件 ──
    OnErrorEvent = enum.auto()
    """插件/工具执行异常"""


@dataclass
class HandlerMetadata(Generic[H]):
    """描述一个 Handler 的元数据。"""

    event_type: EventType
    """Handler 绑定的事件类型"""

    handler_full_name: str
    """全局唯一名，格式: f"{handler.__module__}_{handler.__name__}\""""

    handler_name: str
    """Handler 方法名"""

    handler_module_path: str
    """Handler 所在模块路径"""

    handler: H
    """Handler 函数对象（异步函数）"""

    desc: str = ""
    """Handler 描述信息"""

    extras: dict[str, Any] = field(default_factory=dict)
    """额外配置，如 priority、enabled 等"""

    enabled: bool = True
    """是否启用"""

    def __lt__(self, other: HandlerMetadata) -> bool:
        """按优先级降序排列"""
        return (self.extras.get("priority") or 0) > (other.extras.get("priority") or 0)


class HandlerRegistry(Generic[T]):
    """Handler 注册表 — 按事件类型和优先级管理所有 Handler。

    内部维护两个结构：
    - _handlers: 按 priority 降序排列的列表
    - handler_full_name → HandlerMetadata 映射
    """

    def __init__(self) -> None:
        self._map: dict[str, HandlerMetadata] = {}
        self._handlers: list[HandlerMetadata] = []

    def register(self, handler: HandlerMetadata) -> None:
        """注册一个 Handler，保持按优先级排序"""
        if "priority" not in handler.extras:
            handler.extras["priority"] = 0
        self._map[handler.handler_full_name] = handler
        self._handlers.append(handler)
        self._handlers.sort(
            key=lambda h: -(h.extras.get("priority") or 0)
        )

    def unregister(self, full_name: str) -> bool:
        """移除一个 Handler"""
        removed = self._map.pop(full_name, None)
        if removed:
            self._handlers = [h for h in self._handlers if h is not removed]
        return removed is not None

    def unregister_by_module(self, module_path: str) -> int:
        """移除某模块所有 Handler，返回移除数量"""
        to_remove = [h for h in self._handlers if h.handler_module_path == module_path]
        for h in to_remove:
            self._map.pop(h.handler_full_name, None)
            self._handlers = [x for x in self._handlers if x is not h]
        return len(to_remove)

    def get_by_event_type(
        self,
        event_type: EventType,
        only_activated: bool = True,
        plugin_allowlist: list[str] | None = None,
    ) -> list[HandlerMetadata]:
        """获取指定事件类型的所有 Handler，按优先级排序。

        Args:
            event_type: 事件类型
            only_activated: 是否仅返回已激活插件的 Handler
            plugin_allowlist: 插件名称白名单，None 不过滤
        """
        result: list[HandlerMetadata] = []
        for handler in self._handlers:
            if handler.event_type != event_type:
                continue
            if not handler.enabled:
                continue
            if only_activated:
                plugin = plugin_map.get(handler.handler_module_path)
                if plugin is None or not plugin.activated:
                    continue
            if plugin_allowlist is not None and plugin_allowlist != ["*"]:
                plugin = plugin_map.get(handler.handler_module_path)
                if plugin is None or plugin.name not in plugin_allowlist:
                    continue
            result.append(handler)
        return result

    def get_by_module(self, module_path: str) -> list[HandlerMetadata]:
        """获取某模块注册的所有 Handler"""
        return [h for h in self._handlers if h.handler_module_path == module_path]

    def get_by_name(self, full_name: str) -> HandlerMetadata | None:
        """按全名精确查找"""
        return self._map.get(full_name)

    def clear(self) -> None:
        """清空所有 Handler"""
        self._map.clear()
        self._handlers.clear()

    def __iter__(self):
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)


# ── 全局单例 ──
handler_registry = HandlerRegistry()
"""平台全局 Handler 注册表单例"""
