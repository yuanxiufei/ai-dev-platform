"""
OpenAPI Discovery API — 自动发现 OpenAPI 端点并注册为工具 (借鉴 Open WebUI OpenAPI)

端点:
- GET    /openapi/servers              — 列出已注册的 OpenAPI 服务器
- POST   /openapi/discover             — 发现并注册 OpenAPI 服务器
- GET    /openapi/servers/{id}         — 查看服务器详情
- DELETE /openapi/servers/{id}         — 删除服务器
- GET    /openapi/tools                — 列出所有发现的工具
- GET    /openapi/tools/schemas        — 获取 OpenAI function calling 格式的工具 schema
- POST   /openapi/tools/{id}/call      — 调用发现的工具
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.openapi_discovery import (
    get_openapi_discovery,
    OpenAPIDiscovery,
)

router = APIRouter(prefix="/openapi", tags=["OpenAPI Discovery"])


class DiscoverRequest(BaseModel):
    spec_url: str = Field(..., description="OpenAPI spec JSON 的完整 URL")
    server_name: str = Field(default="", description="自定义服务器名称")
    headers: dict[str, str] = Field(default_factory=dict, description="自定义请求头")


class ToolCallRequest(BaseModel):
    arguments: dict[str, str | int | float | bool] = Field(default_factory=dict)


@router.get("/servers")
async def list_servers() -> dict:
    discovery = get_openapi_discovery()
    return {"servers": discovery.list_servers(), "count": discovery.server_count}


@router.post("/discover")
async def discover_server(data: DiscoverRequest) -> dict:
    discovery = get_openapi_discovery()
    server = await discovery.discover(
        spec_url=data.spec_url,
        server_name=data.server_name,
        headers=data.headers,
    )
    if not server:
        raise HTTPException(status_code=400, detail=f"Failed to discover OpenAPI spec from {data.spec_url}")
    return {
        "server": server.to_dict(),
        "tool_count": server.tool_count,
        "message": f"Discovered {server.tool_count} tools from {server.name}",
    }


@router.get("/servers/{server_id}")
async def get_server(server_id: str) -> dict:
    discovery = get_openapi_discovery()
    server = discovery.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    return {"server": server.to_dict()}


@router.delete("/servers/{server_id}")
async def delete_server(server_id: str) -> dict:
    discovery = get_openapi_discovery()
    if not discovery.delete_server(server_id):
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
    return {"message": f"Server '{server_id}' deleted"}


@router.get("/tools")
async def list_tools(server_id: str = Query(default=None)) -> dict:
    discovery = get_openapi_discovery()
    tools = discovery.list_all_tools(server_id=server_id)
    return {
        "tools": [t.to_tool_schema() for t in tools],
        "count": len(tools),
    }


@router.get("/tools/schemas")
async def get_tool_schemas(server_id: str = Query(default=None)) -> dict:
    discovery = get_openapi_discovery()
    schemas = discovery.get_tool_schemas(server_id=server_id)
    return {"schemas": schemas, "count": len(schemas)}


@router.post("/tools/{tool_id}/call")
async def call_tool(tool_id: str, data: ToolCallRequest) -> dict:
    discovery = get_openapi_discovery()
    tools = discovery.list_all_tools()
    tool = next((t for t in tools if t.id == tool_id), None)
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_id}' not found")
    result = await tool.call(data.arguments)
    return {"tool_id": tool_id, "tool_name": tool.name, "result": result}
