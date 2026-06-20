"""
工具注册中心 — 全局工具管理 + 自动发现

借鉴 AstrBot 的插件注册机制：
- 通过 register_tool() 或 @tool 装饰器注册
- 按名称 / 分类查找
- 支持模块级别的自动发现（扫描 app/tools/ 目录）
- 线程安全（asyncio.Lock）
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
from pathlib import Path
from typing import Callable

from app.core.tools.schema import FunctionTool, ToolParam, ToolSchema, ToolSet

logger = logging.getLogger("tools.registry")


class ToolRegistry:
    """
    全局工具注册中心

    用法:
        registry = ToolRegistry()
        registry.register(my_tool)
        registry.register_from_module("app.tools.builtin.web_search")

        tools_for_llm = registry.get_toolset()
        openai_schemas = tools_for_llm.openai_schema()
    """

    def __init__(self):
        self._tools: dict[str, FunctionTool] = {}
        self._lock = asyncio.Lock()
        self._discovery_dirs: list[str] = []

    # ── 注册/注销 ───────────────────────────────────────────

    async def register(self, tool: FunctionTool) -> None:
        """注册一个工具（异步安全）"""
        async with self._lock:
            name = tool.schema.name
            if name in self._tools:
                logger.info("Tool '%s' already registered, replacing", name)
            self._tools[name] = tool
            logger.info(
                "Tool registered: %s (category=%s, params=%d)",
                name, tool.schema.category, len(tool.schema.parameters),
            )

    def register_sync(self, tool: FunctionTool) -> None:
        """同步注册（用于模块加载时）"""
        name = tool.schema.name
        if name in self._tools:
            logger.info("Tool '%s' already registered, replacing", name)
        self._tools[name] = tool
        logger.info(
            "Tool registered: %s (category=%s, params=%d)",
            name, tool.schema.category, len(tool.schema.parameters),
        )

    async def unregister(self, name: str) -> bool:
        """注销工具"""
        async with self._lock:
            if name in self._tools:
                del self._tools[name]
                logger.info("Tool unregistered: %s", name)
                return True
            return False

    async def clear(self) -> int:
        """清空所有注册"""
        async with self._lock:
            count = len(self._tools)
            self._tools.clear()
            logger.info("ToolRegistry cleared: %d tools removed", count)
            return count

    # ── 查找 ────────────────────────────────────────────────

    def get(self, name: str) -> FunctionTool | None:
        """按名称查找工具"""
        return self._tools.get(name)

    def get_by_category(self, category: str) -> list[FunctionTool]:
        """按分类查找工具"""
        return [t for t in self._tools.values() if t.schema.category == category]

    def get_toolset(self, category: str | None = None) -> ToolSet:
        """获取工具集（可按分类筛选）"""
        if category:
            return ToolSet(self.get_by_category(category))
        return ToolSet(list(self._tools.values()))

    def list_all(self) -> list[dict[str, object]]:
        """列出所有已注册工具（供 API 返回）"""
        return [
            {
                "name": t.schema.name,
                "description": t.schema.description,
                "category": t.schema.category,
                "tags": t.schema.tags,
                "params": [
                    {"name": p.name, "type": p.type.value, "required": p.required, "description": p.description}
                    for p in t.schema.parameters
                ],
                "signature": t.signature_summary(),
            }
            for t in self._tools.values()
        ]

    @property
    def count(self) -> int:
        """已注册工具数量"""
        return len(self._tools)

    @property
    def names(self) -> list[str]:
        """所有已注册工具名称"""
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    # ── 自动发现 ────────────────────────────────────────────

    def add_discovery_dir(self, module_path: str) -> None:
        """添加自动发现目录（Python 模块路径）"""
        if module_path not in self._discovery_dirs:
            self._discovery_dirs.append(module_path)

    async def discover_from_module(self, module_path: str) -> int:
        """
        从指定 Python 模块自动发现工具

        扫描模块中所有 FunctionTool 实例并注册。
        模块中的工具通常定义为模块级变量或通过 @tool 装饰器创建。
        """
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            logger.warning("Cannot import module '%s' for tool discovery: %s", module_path, e)
            return 0

        count = 0
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, FunctionTool):
                await self.register(attr)
                count += 1

        if count > 0:
            logger.info("Discovered %d tools from module '%s'", count, module_path)
        return count

    async def discover_from_path(self, dir_path: str) -> int:
        """从文件系统目录扫描并导入工具模块"""
        from pathlib import Path

        dir_path_obj = Path(dir_path)
        if not dir_path_obj.exists() or not dir_path_obj.is_dir():
            logger.warning("Tool discovery path not found: %s", dir_path)
            return 0

        total = 0
        for py_file in sorted(dir_path_obj.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            # 计算相对于项目根目录的模块路径
            try:
                module_name = py_file.stem
                # 构建 import 路径
                rel = py_file.relative_to(Path.cwd())
                module_path = str(rel.with_suffix("")).replace(os.sep, ".")
                total += await self.discover_from_module(module_path)
            except Exception as e:
                logger.warning("Failed to discover tools from %s: %s", py_file, e)

        return total

    async def discover_all(self) -> int:
        """扫描所有已注册的发现目录"""
        total = 0
        for module_path in self._discovery_dirs:
            try:
                total += await self.discover_from_module(module_path)
            except Exception as e:
                logger.warning("Discovery failed for '%s': %s", module_path, e)
        return total


# ── 全局单例 ────────────────────────────────────────────────

_global_registry: ToolRegistry | None = None


def init_tool_registry() -> ToolRegistry:
    """初始化全局工具注册中心"""
    global _global_registry
    _global_registry = ToolRegistry()
    logger.info("ToolRegistry initialized")
    return _global_registry


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册中心"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        logger.info("ToolRegistry auto-initialized")
    return _global_registry


def register_tool(
    name: str,
    description: str,
    parameters: list[ToolParam] | None = None,
    category: str = "general",
    timeout: float = 30.0,
) -> Callable[..., FunctionTool]:
    """
    装饰器：注册工具到全局注册中心

    用法:
        @register_tool("calculate", "执行数学计算", [ToolParam("expr", description="数学表达式")])
        def calculate(expr: str) -> str:
            return str(eval(expr))
    """
    def decorator(func: Callable[..., object]) -> FunctionTool:
        from app.core.tools.schema import _infer_params, FunctionTool, ToolSchema

        tool = FunctionTool(
            schema=ToolSchema(
                name=name,
                description=description,
                parameters=parameters or _infer_params(func),
                category=category,
            ),
            func=func,
            timeout_seconds=timeout,
        )
        get_tool_registry().register_sync(tool)
        return tool
    return decorator
