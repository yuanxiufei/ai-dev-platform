"""
Agent 工具管理路由

端点:
  GET  /agent/tools          — 列出所有已注册工具
  GET  /agent/tools/{name}   — 工具详情
  POST /agent/tools/{name}   — 直接调用工具（测试用）
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.agent.tool_executor import get_tool_executor
from app.core.tools.registry import get_tool_registry

logger = logging.getLogger("api.agent.tools")

router = APIRouter(prefix="/agent", tags=["agent"])


class ToolCallRequest(BaseModel):
    """直接工具调用请求"""
    arguments: dict[str, Any]


@router.get("/tools")
async def list_tools(category: str | None = None) -> dict[str, Any]:
    """列出所有已注册的工具"""
    registry = get_tool_registry()
    tools = registry.list_all()

    if category:
        tools = [t for t in tools if t["category"] == category]

    return {
        "total": len(tools),
        "tools": tools,
        "categories": list(set(t["category"] for t in registry.list_all())),
    }


@router.get("/tools/{name:path}")
async def get_tool(name: str) -> dict[str, Any]:
    """获取指定工具的详情"""
    registry = get_tool_registry()
    tool = registry.get(name)

    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")

    return {
        "name": tool.schema.name,
        "description": tool.schema.description,
        "category": tool.schema.category,
        "tags": tool.schema.tags,
        "version": tool.schema.version,
        "parameters": [
            {
                "name": p.name,
                "type": p.type.value,
                "required": p.required,
                "description": p.description,
                "default": p.default,
            }
            for p in tool.schema.parameters
        ],
        "signature": tool.signature_summary(),
        "is_async": tool.is_async,
    }


@router.post("/tools/{name:path}")
async def call_tool(name: str, payload: ToolCallRequest) -> dict[str, Any]:
    """直接调用指定工具（用于测试/调试）"""
    registry = get_tool_registry()
    tool = registry.get(name)

    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")

    try:
        result = await tool.call(**payload.arguments)
        return {
            "success": True,
            "tool_name": name,
            "result": str(result),
        }
    except Exception as e:
        logger.error("Tool '%s' call error: %s", name, str(e)[:200])
        return {
            "success": False,
            "tool_name": name,
            "error": str(e),
        }
