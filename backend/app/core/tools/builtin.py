"""
内置工具 — 开箱即用的 Agent 工具集

提供常见的工具实现，供 Agent 直接使用：
- web_search — 网页搜索
- get_weather — 天气查询
- calculate — 数学计算
- file_read — 读取文件
- datetime_now — 获取当前时间
- echo — 回声（调试用）
- json_parse — JSON 解析
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from typing import Any

from app.core.tools.registry import register_tool
from app.core.tools.schema import ToolParam, ParamType


# ══════════════════════════════════════════════════════════════
# 工具实现
# ══════════════════════════════════════════════════════════════


@register_tool(
    "calculate",
    "Evaluate a mathematical expression safely. Supports: + - * / ** sqrt() sin() cos() log() abs() round()",
    [
        ToolParam("expression", ParamType.STRING, description="Mathematical expression to evaluate"),
    ],
    category="general",
)
def _calculate(expression: str) -> str:
    """安全计算数学表达式"""
    allowed = {
        "abs": abs, "round": round,
        "sqrt": math.sqrt, "pow": pow,
        "sin": math.sin, "cos": math.cos, "tan": math.tan,
        "log": math.log, "log10": math.log10,
        "pi": math.pi, "e": math.e,
        "ceil": math.ceil, "floor": math.floor,
    }

    try:
        result = eval(expression, {"__builtins__": {}}, allowed)
        return json.dumps({"expression": expression, "result": result})
    except Exception as e:
        return json.dumps({"expression": expression, "error": str(e)})


@register_tool(
    "datetime_now",
    "Get the current date and time in ISO 8601 format",
    [],
    category="general",
)
def _datetime_now() -> str:
    """获取当前 UTC 时间"""
    now = datetime.now(timezone.utc)
    return json.dumps({
        "iso": now.isoformat(),
        "timestamp": int(now.timestamp()),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "timezone": "UTC",
    })


@register_tool(
    "echo",
    "Echo back the input — useful for debugging and testing",
    [
        ToolParam("message", ParamType.STRING, description="Message to echo back"),
    ],
    category="general",
)
def _echo(message: str = "Hello") -> str:
    """回显输入"""
    return json.dumps({"echo": message, "length": len(message)})


@register_tool(
    "file_read",
    "Read the contents of a file from the filesystem",
    [
        ToolParam("path", ParamType.STRING, description="Absolute or relative path to the file"),
        ToolParam("max_lines", ParamType.INTEGER, required=False, description="Maximum lines to read (default: 200)"),
    ],
    category="file",
)
def _file_read(path: str, max_lines: int = 200) -> str:
    """读取文件内容"""
    try:
        # 安全检查
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            return json.dumps({"error": f"File not found: {path}"})

        if os.path.getsize(abs_path) > 10 * 1024 * 1024:
            return json.dumps({"error": "File too large (>10MB)"})

        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    lines.append(f"... (truncated at {max_lines} lines, {os.path.getsize(abs_path)} bytes total)")
                    break
                lines.append(line.rstrip("\n\r"))

        return json.dumps({
            "path": abs_path,
            "lines": len(lines),
            "content": "\n".join(lines),
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    "json_parse",
    "Parse and validate a JSON string",
    [
        ToolParam("json_string", ParamType.STRING, description="JSON string to parse"),
    ],
    category="general",
)
def _json_parse(json_string: str) -> str:
    """解析 JSON 字符串"""
    try:
        data = json.loads(json_string)
        return json.dumps({
            "valid": True,
            "parsed": data,
            "keys": list(data.keys()) if isinstance(data, dict) else None,
            "type": type(data).__name__,
        })
    except json.JSONDecodeError as e:
        return json.dumps({"valid": False, "error": str(e)})


@register_tool(
    "get_weather",
    "Get the current weather for a specified city. Returns temperature, humidity, conditions, and wind info.",
    [
        ToolParam("city", ParamType.STRING, description="City name (e.g. Beijing, Tokyo, New York)"),
        ToolParam("unit", ParamType.STRING, required=False, description="Temperature unit: celsius or fahrenheit (default: celsius)"),
    ],
    category="general",
)
def _get_weather(city: str, unit: str = "celsius") -> str:
    """获取城市天气（模拟数据）"""
    import hashlib

    # 用城市名的 hash 生成一致的模拟数据
    h = int(hashlib.md5(city.encode()).hexdigest()[:8], 16)
    conditions = ["晴", "多云", "阴", "小雨", "晴间多云"]
    wind_dir = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]

    temp_base = (h % 25) + 5
    temp = temp_base if unit == "celsius" else round(temp_base * 9 / 5 + 32)

    return json.dumps({
        "city": city,
        "temperature": temp,
        "unit": unit,
        "condition": conditions[h % len(conditions)],
        "humidity": f"{(h % 40) + 40}%",
        "wind": f"{wind_dir[h % len(wind_dir)]}风 {(h % 5) + 1}级",
        "note": "模拟数据，请连接真实天气 API 获取准确信息",
    })


@register_tool(
    "web_search",
    "Search the web for information. Returns top results with title, snippet, and URL.",
    [
        ToolParam("query", ParamType.STRING, description="Search query string"),
        ToolParam("max_results", ParamType.INTEGER, required=False, description="Maximum number of results (default: 5)"),
    ],
    category="general",
)
def _web_search(query: str, max_results: int = 5) -> str:
    """网页搜索（模拟数据）"""
    results = [
        {
            "title": f"搜索结果: {query}",
            "snippet": f"关于 '{query}' 的综合信息。这是一个模拟的搜索结果，包含了您查询的相关内容摘要。",
            "url": f"https://example.com/search?q={query.replace(' ', '+')}",
        }
        for _ in range(min(max_results, 5))
    ]
    return json.dumps({
        "query": query,
        "total_results": len(results),
        "results": results,
        "note": "模拟数据，请替换为 SerpAPI / Bing Search API 获取真实结果",
    })
