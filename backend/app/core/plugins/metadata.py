"""
插件元数据与全局注册表

借鉴 AstrBot star.py / star_registry / star_map 架构：
- PluginMetadata: 描述插件完整元数据的 dataclass
- plugin_registry: list[PluginMetadata] 全局有序列表
- plugin_map: dict[str, PluginMetadata] 按模块路径索引
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import Plugin

# 全局插件注册表
plugin_registry: list[PluginMetadata] = []
"""所有已注册插件的元数据列表（按加载顺序）"""

plugin_map: dict[str, PluginMetadata] = {}
"""模块路径 → PluginMetadata 映射，key 为插件的 __module__"""


@dataclass
class PluginMetadata:
    """描述一个插件的完整元数据。

    当 activated 为 False 时，plugin_cls 可能为 None，
    请不要在插件未激活时调用 plugin_cls 的方法。
    """

    # ── 插件基本信息 ──
    name: str | None = None
    """插件名称"""
    author: str | None = None
    """插件作者"""
    desc: str | None = None
    """插件简介"""
    version: str | None = None
    """插件版本"""
    repo: str | None = None
    """插件仓库地址"""
    display_name: str | None = None
    """用于展示的插件名称"""
    logo_path: str | None = None
    """插件 Logo 路径"""

    # ── 类/模块引用 ──
    plugin_cls_type: type[Plugin] | None = None
    """插件类对象的类型"""
    module_path: str | None = None
    """插件的模块路径（__module__）"""
    plugin_cls: Plugin | None = None
    """插件类实例（activated 时才非空）"""
    module: ModuleType | None = None
    """插件模块对象"""
    root_dir_name: str | None = None
    """插件目录名称"""

    # ── 状态标志 ──
    reserved: bool = False
    """是否为系统保留插件（不可卸载）"""
    activated: bool = True
    """是否已激活"""

    # ── 配置与钩子 ──
    config: dict[str, Any] | None = None
    """插件配置字典"""
    handler_full_names: list[str] = field(default_factory=list)
    """该插件注册的所有 Handler 全名列表"""
    tool_names: list[str] = field(default_factory=list)
    """该插件注册的所有工具名称列表"""

    # ── 平台与版本约束 ──
    support_platforms: list[str] = field(default_factory=list)
    """插件声明支持的平台 ID 列表"""
    required_version: str | None = None
    """插件要求的最小平台版本（PEP 440 specifier）"""

    # ── 国际化 ──
    i18n: dict[str, dict] = field(default_factory=dict)
    """插件自带的国际化文案，按 locale 分组"""

    # ── 页面注册 ──
    pages: list[dict] = field(default_factory=list)
    """插件注册的管理页面元数据"""

    def __str__(self) -> str:
        return f"Plugin {self.name} ({self.version}) by {self.author}: {self.desc}"

    def __repr__(self) -> str:
        return self.__str__()
