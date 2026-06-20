"""
工具 Schema — 统一的工具定义 + 多格式转换

借鉴 AstrBot agent/tool.py 的设计：
- ToolSchema: 工具元数据（名称、描述、参数）
- FunctionTool: 可调用工具的包装（schema + callable）
- ToolSet: 工具集合，支持 OpenAI / Anthropic 两种 schema 导出
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("tools.schema")


# ── 参数类型 ────────────────────────────────────────────────

class ParamType(str, Enum):
    """工具参数 JSON Schema 类型"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ToolParam:
    """工具参数定义"""
    name: str
    type: ParamType = ParamType.STRING
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[str] | None = None
    items: dict[str, Any] | None = None             # array items schema
    properties: dict[str, "ToolParam"] | None = None  # object properties

    def to_json_schema(self) -> dict[str, Any]:
        """转为 JSON Schema 片段"""
        schema: dict[str, Any] = {"type": self.type.value}
        if self.description:
            schema["description"] = self.description
        if self.enum:
            schema["enum"] = self.enum
        if self.items:
            schema["items"] = self.items
        if self.properties:
            schema["properties"] = {
                k: v.to_json_schema() for k, v in self.properties.items()
            }
            required_props = [
                k for k, v in self.properties.items() if v.required
            ]
            if required_props:
                schema["required"] = required_props
        return schema


# ── 工具 Schema ─────────────────────────────────────────────

@dataclass
class ToolSchema:
    """
    工具元数据定义

    支持三种 LLM provider 的 schema 格式：
    - openai_schema() → OpenAI Function Calling
    - anthropic_schema() → Anthropic Tool Use
    """
    name: str
    description: str
    parameters: list[ToolParam] = field(default_factory=list)

    # 元信息
    category: str = "general"           # general | code | file | web | system
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"

    def _params_schema(self) -> dict[str, Any]:
        """构建 JSON Schema parameters 对象"""
        props = {p.name: p.to_json_schema() for p in self.parameters}
        required = [p.name for p in self.parameters if p.required]
        schema: dict[str, Any] = {
            "type": "object",
            "properties": props,
        }
        if required:
            schema["required"] = required
        return schema

    # ── OpenAI 格式 ──────────────────────────────────────

    def openai_schema(self) -> dict[str, Any]:
        """生成 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self._params_schema(),
            },
        }

    # ── Anthropic 格式 ───────────────────────────────────

    def anthropic_schema(self) -> dict[str, Any]:
        """生成 Anthropic Tool Use 格式"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self._params_schema(),
        }


# ── 可调用工具 ──────────────────────────────────────────────

@dataclass
class FunctionTool:
    """
    可调用工具 —— 将 Python 函数包装为 LLM 可用的工具

    用法:
        async def get_weather(city: str) -> str: ...

        tool = FunctionTool(
            schema=ToolSchema(
                name="get_weather",
                description="获取指定城市的天气",
                parameters=[ToolParam(name="city", description="城市名称")],
            ),
            func=get_weather,
        )

        # 供 LLM 使用
        openai_tools = [tool.to_openai()]
        result = await tool.call(city="Beijing")
    """

    schema: ToolSchema | None = None
    func: Callable[..., Any] | None = None

    # 运行时标识
    tool_id: str = ""
    is_async: bool = False
    timeout_seconds: float = 30.0

    def __post_init__(self):
        if not self.tool_id and self.schema:
            self.tool_id = f"tool:{self.schema.name}"
        if self.func:
            self.is_async = asyncio.iscoroutinefunction(self.func)

    async def call(self, **kwargs: Any) -> Any:
        """执行工具调用"""
        try:
            if self.is_async:
                result = await asyncio.wait_for(
                    self.func(**kwargs),
                    timeout=self.timeout_seconds,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self.func, **kwargs),
                    timeout=self.timeout_seconds,
                )
            return result
        except asyncio.TimeoutError:
            logger.warning("Tool '%s' timed out after %.1fs", self.schema.name, self.timeout_seconds)
            return json.dumps({"error": f"Tool '{self.schema.name}' timed out"})
        except Exception as e:
            logger.error("Tool '%s' execution error: %s", self.schema.name, str(e)[:200])
            return json.dumps({"error": str(e)})

    def call_sync(self, **kwargs: Any) -> Any:
        """同步执行工具调用"""
        if self.is_async:
            raise RuntimeError(f"Tool '{self.schema.name}' is async, use call()")
        try:
            return self.func(**kwargs)
        except Exception as e:
            logger.error("Tool '%s' sync error: %s", self.schema.name, str(e)[:200])
            return json.dumps({"error": str(e)})

    def to_openai(self) -> dict[str, Any]:
        """OpenAI Function Calling 格式"""
        return self.schema.openai_schema()

    def to_anthropic(self) -> dict[str, Any]:
        """Anthropic Tool Use 格式"""
        return self.schema.anthropic_schema()

    def signature_summary(self) -> str:
        """生成人类可读的工具签名"""
        params = ", ".join(
            f"{p.name}: {p.type.value}" + ("" if p.required else " = ?")
            for p in self.schema.parameters
        )
        return f"{self.schema.name}({params}) → {self.schema.description[:60]}"


# ── 工具集合 ────────────────────────────────────────────────

@dataclass
class ToolSet:
    """
    工具集合 —— 管理一组工具并提供多格式导出

    借鉴 AstrBot ToolSet，支持：
    - 按名称查找工具
    - OpenAI / Anthropic 多格式批量导出
    - 按分类筛选
    """

    tools: list[FunctionTool] = field(default_factory=list)

    def add(self, tool: FunctionTool) -> None:
        """添加工具（同名替换）"""
        existing = self.get(tool.schema.name)
        if existing:
            logger.info("Tool '%s' already registered, replacing", tool.schema.name)
            self.tools = [t for t in self.tools if t.schema.name != tool.schema.name]
        self.tools.append(tool)

    def remove(self, name: str) -> bool:
        """按名称移除工具"""
        before = len(self.tools)
        self.tools = [t for t in self.tools if t.schema.name != name]
        return len(self.tools) < before

    def get(self, name: str) -> FunctionTool | None:
        """按名称获取工具"""
        for t in self.tools:
            if t.schema.name == name:
                return t
        return None

    def filter_by_category(self, category: str) -> ToolSet:
        """按分类筛选"""
        return ToolSet([t for t in self.tools if t.schema.category == category])

    # ── 多格式导出 ──────────────────────────────────────

    def openai_schema(self, category: str | None = None) -> list[dict[str, Any]]:
        """导出 OpenAI Function Calling 格式"""
        tools = self.tools if category is None else self.filter_by_category(category).tools
        return [t.to_openai() for t in tools]

    def anthropic_schema(self) -> list[dict[str, Any]]:
        """导出 Anthropic Tool Use 格式"""
        return [t.to_anthropic() for t in self.tools]

    # ── 属性 ────────────────────────────────────────────

    @property
    def names(self) -> list[str]:
        """所有工具名称"""
        return [t.schema.name for t in self.tools]

    @property
    def count(self) -> int:
        """工具数量"""
        return len(self.tools)

    def __len__(self) -> int:
        return self.count

    def __contains__(self, name: str) -> bool:
        return self.get(name) is not None

    def __iter__(self):
        return iter(self.tools)


# ── 工具调用结果 ────────────────────────────────────────────

@dataclass
class ToolResult:
    """单次工具调用结果"""
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    result: Any
    success: bool = True
    error: str = ""
    latency_ms: float = 0

    def to_openai_message(self) -> dict[str, Any]:
        """转为 OpenAI tool role 消息"""
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": str(self.result),
        }

    def to_content(self) -> str:
        """人类可读的结果摘要"""
        if self.success:
            return json.dumps(self.result, ensure_ascii=False)
        return f"Error: {self.error}"


# ── 装饰器语法糖 ────────────────────────────────────────────

def tool(
    name: str,
    description: str,
    parameters: list[ToolParam] | None = None,
    category: str = "general",
    timeout: float = 30.0,
) -> Callable[..., FunctionTool]:
    """
    装饰器：将函数快速注册为 FunctionTool

    用法:
        @tool("get_weather", "查天气", [ToolParam("city", description="城市名")])
        async def get_weather(city: str) -> str:
            return f"{city}: 晴天 22°C"
    """
    def decorator(func: Callable[..., Any]) -> FunctionTool:
        return FunctionTool(
            schema=ToolSchema(
                name=name,
                description=description,
                parameters=parameters or _infer_params(func),
                category=category,
            ),
            func=func,
            timeout_seconds=timeout,
        )
    return decorator


def _infer_params(func: Callable[..., Any]) -> list[ToolParam]:
    """从函数签名推断参数 Schema"""
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return []

    type_map = {
        str: ParamType.STRING,
        int: ParamType.INTEGER,
        float: ParamType.NUMBER,
        bool: ParamType.BOOLEAN,
        list: ParamType.ARRAY,
        dict: ParamType.OBJECT,
    }

    params: list[ToolParam] = []
    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue
        annotation = param.annotation
        param_type = type_map.get(annotation, ParamType.STRING)

        params.append(ToolParam(
            name=param_name,
            type=param_type,
            required=param.default is inspect.Parameter.empty,
            default=None if param.default is inspect.Parameter.empty else param.default,
        ))

    return params
