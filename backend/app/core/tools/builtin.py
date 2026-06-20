"""
内置工具 — 开箱即用的 Agent 工具集

提供常见的工具实现，供 Agent 直接使用：
- web_search — 网页搜索（占位，需替换为实际 API）
- calculate — 数学计算
- file_read — 读取文件
- datetime_now — 获取当前时间
- echo — 回声（调试用）
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
