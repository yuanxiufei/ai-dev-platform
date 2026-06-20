"""
内置工具类——基于类的工具定义 + 配置条件规则

借鉴 AstrBot @builtin_tool 装饰器 + BuiltinToolConfigRule 模式:
- BuiltinTool: 类级别的工具注册（继承 FunctionTool）
- builtin_tool: 装饰器，自动注册到 ToolRegistry
- BuiltinToolConfigRule: 配置驱动的工具启用条件
- BuiltinToolConfigCondition: 条件原子（equals/in/truthy）

用法:
    @builtin_tool(config={"provider_settings.web_search": True})
    @dataclass
    class WebSearchTool(BuiltinTool):
        name: str = "web_search"
        description: str = "Search the web"
        parameters: list[ToolParam] = field(default_factory=lambda: [
            ToolParam("query", ParamType.STRING, description="Search query"),
        ])

        async def handler(self, query: str) -> str:
            return f"Results for: {query}"
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.tools.schema import FunctionTool, ToolParam, ToolResult, ToolSchema

logger = logging.getLogger("tools.builtin")


@dataclass
class ToolExecResult:
    """工具执行结果（简化版，用于 web_search 等工具）"""
    success: bool = True
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] | None = None

# ── 配置条件 ────────────────────────────────────────────────


@dataclass(frozen=True)
class BuiltinToolConfigCondition:
    """
    工具启用的单个配置条件

    借鉴 AstrBot BuiltinToolConfigCondition：
    - 支持点号分隔的键路径（如 "provider_settings.web_search"）
    - 四种操作符: equals | in | truthy | custom
    """
    key: str
    operator: str = "equals"       # equals | in | truthy | custom
    expected: Any = None
    message: str | None = None

    def evaluate(self, config: dict[str, Any]) -> dict[str, Any]:
        """评估条件是否满足"""
        actual = self._get_config_value(config, self.key)

        if self.operator == "truthy":
            matched = bool(actual)
        elif self.operator == "in":
            expected_values = self.expected if isinstance(self.expected, (tuple, list)) else (self.expected,)
            matched = actual in expected_values
        elif self.operator == "custom":
            matched = bool(self.expected)
        else:  # equals
            matched = actual == self.expected

        return {
            "key": self.key,
            "operator": self.operator,
            "expected": self.expected,
            "actual": actual,
            "matched": matched,
            "message": self.message or "",
        }

    @staticmethod
    def _get_config_value(config: dict[str, Any], key_path: str) -> Any:
        """从嵌套字典中按点号分隔的键路径取值"""
        parts = key_path.split(".")
        current = config
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return _MISSING
        return current


class _MISSING:
    """sentinel: 键不存在"""
    def __repr__(self):
        return "<MISSING>"


# ── 配置规则 ────────────────────────────────────────────────


@dataclass(frozen=True)
class BuiltinToolConfigRule:
    """
    工具启用的配置规则

    包含一组条件和一个可选的自定义评估器。
    - 简单条件: conditions 列表，全部满足才启用
    - 自定义评估器: evaluator 函数接收整个配置 dict，返回条件结果列表
    """
    conditions: tuple[BuiltinToolConfigCondition, ...] = ()
    evaluator: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None

    def evaluate(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """评估规则，返回条件结果列表"""
        if self.evaluator:
            return self.evaluator(config)
        return [c.evaluate(config) for c in self.conditions]

    def is_enabled(self, config: dict[str, Any]) -> bool:
        """检查工具在此配置下是否启用"""
        results = self.evaluate(config)
        return all(r.get("matched", False) for r in results)

    @classmethod
    def from_config_map(cls, config_map: dict[str, Any]) -> BuiltinToolConfigRule:
        """从简单配置字典构建规则"""
        conditions = []
        for key, value in config_map.items():
            if isinstance(value, (tuple, list)):
                cond = BuiltinToolConfigCondition(
                    key=key, operator="in", expected=tuple(value),
                    message=f"{key} in {value}",
                )
            elif isinstance(value, bool):
                cond = BuiltinToolConfigCondition(
                    key=key, operator="truthy" if value else "equals",
                    expected=value,
                )
            else:
                cond = BuiltinToolConfigCondition(
                    key=key, operator="equals", expected=value,
                )
            conditions.append(cond)
        return cls(conditions=tuple(conditions))


# ── 内置工具基类 ────────────────────────────────────────────


@dataclass
class BuiltinTool(FunctionTool):
    """
    内置工具基类 —— 类级别的工具定义

    继承 FunctionTool，支持：
    - 类属性定义 name/description/parameters/category
    - handler() 方法定义执行逻辑
    - 配置条件规则控制启用状态

    用法:
        @dataclass
        class MyTool(BuiltinTool):
            name: str = "my_tool"
            description: str = "My tool description"
            parameters: list[ToolParam] = field(default_factory=lambda: [
                ToolParam("input", description="Input parameter"),
            ])

            async def handler(self, input: str) -> str:
                return f"Processed: {input}"
    """

    # 类级别默认值
    name: str = ""
    description: str = ""
    parameters: list[ToolParam] = field(default_factory=list)
    category: str = "general"
    tags: list[str] = field(default_factory=list)
    timeout: float = 30.0
    version: str = "1.0.0"

    # 配置规则（类变量，非实例字段）
    _config_rule: BuiltinToolConfigRule | None = None

    def __post_init__(self):
        # 构建 schema
        if not self.name:
            self.name = self.__class__.__name__.lower().replace("tool", "")
        self.schema = ToolSchema(
            name=self.name,
            description=self.description,
            parameters=list(self.parameters),
            category=self.category,
            tags=list(self.tags),
            version=self.version,
        )
        self.tool_id = f"builtin:{self.name}"
        self.timeout_seconds = self.timeout
        self.func = self._make_handler()

    def _make_handler(self) -> Callable[..., Any]:
        """将 handler 方法包装为 callable"""
        instance = self

        async def wrapper(**kwargs):
            if hasattr(instance, "handler"):
                return await instance.handler(**kwargs)
            raise NotImplementedError(
                f"BuiltinTool '{instance.name}' must implement handler()"
            )

        return wrapper

    def is_enabled_for_config(self, config: dict[str, Any]) -> bool:
        """检查工具在指定配置下是否启用"""
        if self._config_rule is None:
            return True
        return self._config_rule.is_enabled(config)

    def get_config_status(self, configs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """获取工具在各配置下的启用状态"""
        if self._config_rule is None:
            return [
                {
                    "conf_id": cfg.get("id", ""),
                    "conf_name": cfg.get("name", ""),
                    "enabled": True,
                    "conditions": [],
                }
                for cfg in configs
            ]

        results = []
        for cfg in configs:
            cond_results = self._config_rule.evaluate(cfg.get("config", cfg))
            results.append({
                "conf_id": cfg.get("id", ""),
                "conf_name": cfg.get("name", ""),
                "enabled": all(r["matched"] for r in cond_results),
                "matched_conditions": [r for r in cond_results if r["matched"]],
                "failed_conditions": [r for r in cond_results if not r["matched"]],
            })
        return results


# ── 装饰器 ──────────────────────────────────────────────────


def builtin_tool(
    name: str = "",
    description: str = "",
    config: dict[str, Any] | None = None,
    category: str = "general",
    timeout: float = 30.0,
) -> Callable:
    """
    类装饰器：注册 BuiltinTool 子类

    借鉴 AstrBot @builtin_tool 装饰器，自动注册到 ToolRegistry。

    用法:
        @builtin_tool(config={"provider_settings.web_search": True})
        @dataclass
        class WebSearchTool(BuiltinTool):
            name: str = "web_search"
            description: str = "Search the web"

            async def handler(self, query: str) -> str:
                return f"Results for: {query}"
    """
    def decorator(cls) -> type:
        from app.core.tools.registry import get_tool_registry

        # 创建实例
        instance = cls()

        # 覆盖装饰器参数
        if name:
            instance.schema.name = name
        if description:
            instance.schema.description = description
        if category != "general":
            instance.schema.category = category

        # 绑定配置规则
        if config:
            instance._config_rule = BuiltinToolConfigRule.from_config_map(config)

        # 注册到全局注册中心
        registry = get_tool_registry()
        registry.register_sync(instance)

        logger.info(
            "BuiltinTool registered: %s (config_rule=%s)",
            instance.name,
            "yes" if instance._config_rule else "no",
        )
        return cls

    return decorator


# ── 全局配置规则注册表 ──────────────────────────────────────

_BUILTIN_TOOL_CONFIG_RULES: dict[str, BuiltinToolConfigRule] = {}


def register_config_rule(tool_name: str, rule: BuiltinToolConfigRule) -> None:
    """为指定工具注册配置规则"""
    _BUILTIN_TOOL_CONFIG_RULES[tool_name] = rule
    logger.info("Config rule registered for tool '%s': %d conditions", tool_name, len(rule.conditions))


def get_config_rule(tool_name: str) -> BuiltinToolConfigRule | None:
    """获取工具的配置规则"""
    return _BUILTIN_TOOL_CONFIG_RULES.get(tool_name)


def evaluate_all_tools(config: dict[str, Any]) -> dict[str, bool]:
    """批量评估所有工具的启用状态"""
    return {
        name: rule.is_enabled(config)
        for name, rule in _BUILTIN_TOOL_CONFIG_RULES.items()
    }
