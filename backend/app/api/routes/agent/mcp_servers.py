"""
MCP 服务器管理路由 — 完整 RESTful API

端点:
  GET    /servers              — 列出所有 MCP 服务器（含状态快照）
  GET    /servers/{name}       — 单个服务器详情（含工具列表）
  POST   /servers              — 添加并连接 MCP 服务器
  PUT    /servers/{name}       — 更新服务器配置
  DELETE /servers/{name}       — 移除并断开 MCP 服务器
  POST   /servers/discover     — 扫描所有服务器工具
  POST   /servers/register     — 将 MCP 工具注册到全局 ToolRegistry
  POST   /servers/{name}/reconnect — 重连单个服务器
  GET    /servers/{name}/health    — 单个服务器健康检查
  POST   /health                   — 全部服务器健康检查
  POST   /tools/call               — 直接调用 MCP 工具（调试用）

错误码体系 (MCPErrCode):
  - 0: OK
  - 1001-1004: 通用错误（未知/配置/已存在/未找到）
  - 2001-2005: 连接错误（失败/超时/断开/重连耗尽/初始化）
  - 3001-3004: 协议错误（JSON-RPC/方法/参数）
  - 4001-4003: 工具错误（不存在/执行/超时）
  - 6001-6002: 安全违规
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.mcp import (
    MCPErrCode,
    MCPServerConfig,
    MCPTransport,
    MCPManager,
    MCPError,
)

logger = logging.getLogger("api.agent.mcp")

router = APIRouter(prefix="/agent/mcp", tags=["agent"])

# ── 全局单例 ──────────────────────────────────────────────

_mcp_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """获取 MCP 管理器（懒初始化）"""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


# ── 请求模型 ──────────────────────────────────────────────


class MCPAddServerRequest(BaseModel):
    """添加 MCP 服务器请求"""
    name: str = Field(..., description="服务器名称", min_length=1, max_length=128)
    transport: str = Field(default="sse", description="传输类型: sse | streamable_http | stdio")
    url: str = Field(default="", description="HTTP URL（SSE / Streamable HTTP）")
    command: str = Field(default="", description="Stdio 命令路径")
    args: list[str] = Field(default_factory=list, description="Stdio 命令参数")
    env: dict[str, str] = Field(default_factory=dict, description="环境变量")
    tool_prefix: str = Field(default="", description="工具名前缀（避免冲突）")
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP 请求头")
    auto_discover: bool = Field(default=True, description="是否自动发现工具")
    timeout: float = Field(default=30.0, description="超时秒数", ge=5, le=300)
    reconnect: bool = Field(default=True, description="是否自动重连")
    max_retries: int = Field(default=5, description="最大重试次数", ge=0, le=20)
    retry_delay: float = Field(default=2.0, description="基础重试延迟(秒)", ge=0.5)
    enabled: bool = Field(default=True, description="是否启用")
    heartbeat_interval: float = Field(default=30.0, description="心跳间隔(秒), 0禁用", ge=0)


class MCPUpdateServerRequest(BaseModel):
    """更新 MCP 服务器请求（所有字段可选）"""
    url: str | None = Field(default=None)
    command: str | None = Field(default=None)
    args: list[str] | None = Field(default=None)
    env: dict[str, str] | None = Field(default=None)
    tool_prefix: str | None = Field(default=None)
    headers: dict[str, str] | None = Field(default=None)
    auto_discover: bool | None = Field(default=None)
    timeout: float | None = Field(default=None, ge=5, le=300)
    reconnect: bool | None = Field(default=None)
    max_retries: int | None = Field(default=None, ge=0, le=20)
    retry_delay: float | None = Field(default=None, ge=0.5)
    enabled: bool | None = Field(default=None)
    heartbeat_interval: float | None = Field(default=None, ge=0)


class MCPCallToolRequest(BaseModel):
    """直接调用 MCP 工具请求（调试用途）"""
    server_name: str = Field(..., description="目标服务器名称")
    tool_name: str = Field(..., description="工具名称")
    arguments: dict[str, Any] = Field(default_factory=dict, description="工具参数")


# ── 响应辅助 ──────────────────────────────────────────────

def _ok(data: Any) -> dict[str, Any]:
    """构造成功响应"""
    return {"error_code": MCPErrCode.OK.value, "success": True, **data}


def _err(code: MCPErrCode, detail: Any = None, http_status: int | None = None):
    """构造错误响应并抛 HTTPException"""
    status = http_status or code.http_status
    raise HTTPException(
        status_code=status,
        detail={
            "error_code": code.value,
            "error": code.message,
            "detail": detail,
        },
    )


# ══════════════════════════════════════════════════════════
# 路由定义
# ══════════════════════════════════════════════════════════


@router.get("/servers")
async def list_servers() -> dict[str, Any]:
    """
    列出所有已配置的 MCP 服务器及其状态快照。

    Response:
        servers: MCPServerStatus[]  — 每个服务器的完整状态
        connected: bool             — 是否至少有一个连接
        total_tools: int            — 已发现的工具总数
        summary: object             — 汇总统计
    """
    manager = get_mcp_manager()
    statuses = manager.get_all_statuses()

    total_tools = len(manager.tools)
    connected_count = sum(1 for s in statuses if s.connected)

    # 按传输协议分组统计
    by_transport: dict[str, int] = {}
    for s in statuses:
        by_transport[s.transport] = by_transport.get(s.transport, 0) + 1

    # 按状态分组统计
    by_state: dict[str, int] = {}
    for s in statuses:
        by_state[s.state] = by_state.get(s.state, 0) + 1

    return _ok({
        "servers": [s.__dict__ for s in statuses],
        "connected": manager.is_connected,
        "total_tools": total_tools,
        "summary": {
            "total_servers": len(statuses),
            "connected_servers": connected_count,
            "by_transport": by_transport,
            "by_state": by_state,
        },
    })


@router.get("/servers/{name}")
async def get_server(name: str) -> dict[str, Any]:
    """
    获取单个 MCP 服务器的详细信息。

    Path: name — 服务器名称

    Response:
        server: MCPServerStatus          — 状态信息
        tools: MCPToolInfo[]             — 该服务器的工具列表
    """
    manager = get_mcp_manager()
    client = await manager.get_server(name)
    if not client:
        _err(MCPErrCode.NOT_FOUND, f"Server '{name}' not found")

    status = client.status

    # 如果已连接，尝试获取工具列表
    tools_data = []
    if client.is_connected:
        try:
            tools = await client.list_tools()
            tools_data = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
        except Exception as e:
            tools_data = [{"error": f"Tool discovery failed: {e}"}]

    return _ok({"server": status.__dict__, "tools": tools_data})


@router.post("/servers")
async def add_server(payload: MCPAddServerRequest) -> dict[str, Any]:
    """
    添加并连接一个 MCP 服务器。

    Request body: MCPAddServerRequest

    触发条件:
      - name 非空且唯一
      - 根据 transport 提供对应的 URL 或 command

    边界约束:
      - name 最大128字符，仅允许字母数字、连字符、下划线
      - SSE/Streamable HTTP 必须提供有效 URL
      - Stdio 必须提供命令且通过安全校验
      - timeout 范围 [5, 300]
      - max_retries 范围 [0, 20]

    Response:
        success: bool
        message: str
        tools_discovered?: int
        tools?: string[]
        warnings?: string[]
    """
    # 名称规范化与验证
    safe_name = payload.name.strip()
    if not safe_name.isidentifier() and not all(c.isalnum() or c in "-_" for c in safe_name):
        _err(MCPErrCode.INVALID_CONFIG,
             "Name must contain only alphanumeric characters, hyphens, underscores")

    manager = get_mcp_manager()

    # 检查重复
    existing_client = await manager.get_server(safe_name)
    if existing_client is not None:
        _err(MCPErrCode.ALREADY_EXISTS, f"Server '{safe_name}' already exists")

    # 传输映射
    transport_map = {
        "sse": MCPTransport.SSE,
        "streamable_http": MCPTransport.STREAMABLE_HTTP,
        "stdio": MCPTransport.STDIO,
    }
    transport = transport_map.get(payload.transport, MCPTransport.SSE)

    config = MCPServerConfig(
        name=safe_name,
        transport=transport,
        url=payload.url.strip(),
        command=payload.command.strip(),
        args=payload.args or [],
        env=payload.env or {},
        tool_prefix=payload.tool_prefix.strip(),
        headers=payload.headers or {},
        auto_discover=payload.auto_discover,
        timeout_seconds=payload.timeout,
        reconnect=payload.reconnect,
        max_retries=payload.max_retries,
        retry_delay_seconds=payload.retry_delay,
        enabled=payload.enabled,
        heartbeat_interval_seconds=payload.heartbeat_interval,
    )

    # 安全验证（Stdio 类型）
    warnings: list[str] = []
    if transport == MCPTransport.STDIO:
        from app.core.mcp.security import validate_mcp_stdio_config
        sec_errs = validate_mcp_stdio_config(config.command, config.args, config.env)
        if sec_errs:
            _err(MCPErrCode.SECURITY_VIOLATION, sec_errs)

    # URL 验证（HTTP 类型）
    elif transport in (MCPTransport.SSE, MCPTransport.STREAMABLE_HTTP):
        from app.core.mcp.security import validate_mcp_url
        url_errs = validate_mcp_url(config.url)
        for e in url_errs:
            warnings.append(e)
        # localhost 仅警告不拒绝

    # 添加并连接
    manager.add_server(config)
    result = await manager.connect_all()

    response_data: dict[str, Any] = {}
    if result.success:
        response_data["message"] = f"Connected to '{safe_name}'"
    else:
        response_data["message"] = f"Failed to connect to '{safe_name}'"
        response_data["errors"] = result.errors
        # 即使连接失败，配置已保存（可后续手动重连）

    # 自动发现工具
    if result.success and payload.auto_discover:
        try:
            tools = await manager.discover_all_tools()
            response_data["tools_discovered"] = len(tools)
            response_data["tools"] = [t.name for t in tools]
        except Exception as e:
            response_data["warnings"] = [f"Auto-discover failed: {e}"]

    if warnings:
        response_data.setdefault("warnings", []).extend(warnings)

    response_data["success"] = result.success
    return _ok(response_data)


@router.put("/servers/{name}")
async def update_server(name: str, payload: MCPUpdateServerRequest) -> dict[str, Any]:
    """
    更新指定 MCP 服务器的运行时配置。

    Path: name — 服务器名称
    Body: MCPUpdateServerRequest（所有字段可选）

    更新后：
      - 如果从 disabled → enabled，自动触发连接
      - 如果修改了 URL/command，需要手动重连才生效

    Response:
        success: bool
        message: str
    """
    manager = get_mcp_manager()
    client = await manager.get_server(name)
    if not client:
        _err(MCPErrCode.NOT_FOUND, f"Server '{name}' not found")

    # 构建更新参数字典（过滤 None 值）
    kwargs = {}
    field_mapping = {
        "url": "url",
        "command": "command",
        "args": "args",
        "env": "env",
        "tool_prefix": "tool_prefix",
        "headers": "headers",
        "auto_discover": "auto_discover",
        "timeout": "timeout_seconds",
        "reconnect": "reconnect",
        "max_retries": "max_retries",
        "retry_delay": "retry_delay_seconds",
        "enabled": "enabled",
        "heartbeat_interval": "heartbeat_interval_seconds",
    }
    for req_field, cfg_field in field_mapping.items():
        val = getattr(payload, req_field, None)
        if val is not None:
            kwargs[cfg_field] = val

    if not kwargs:
        return _ok({"message": f"No changes for '{name}'"})

    try:
        ok = await manager.update_server(name, **kwargs)
        if not ok:
            _err(MCPErrCode.NOT_FOUND)
        return _ok({"message": f"Server '{name}' configuration updated"})
    except ValueError as e:
        _err(MCPErrCode.INVALID_CONFIG, str(e))


@router.delete("/servers/{name}")
async def remove_server(name: str) -> dict[str, Any]:
    """
    移除并断开指定 MCP 服务器。

    Path: name — 服务器名称

    操作：
      1. 从管理器中移除客户端
      2. 异步断开底层连接
      3. 清理关联的工具注册

    Response:
        success: bool
        message: str
    """
    manager = get_mcp_manager()
    if not manager.remove_server(name):
        _err(MCPErrCode.NOT_FOUND, f"Server '{name}' not found")

    return _ok({"message": f"Server '{name}' removed"})


# ── 运维操作 ────────────────────────────────────────────


@router.post("/servers/discover")
async def discover_all_tools() -> dict[str, Any]:
    """
    扫描所有已连接 MCP 服务器的工具列表。

    Response:
        total: int                    — 发现的工具总数
        tools: object[]               — 工具详情列表
        servers_scanned: int          — 扫描的服务器数量
    """
    manager = get_mcp_manager()
    tools = await manager.discover_all_tools()

    return _ok({
        "total": len(tools),
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "server": t.server_name,
                "parameters": t.input_schema.get("properties", {}),
                "required": t.input_schema.get("required", []),
            }
            for t in tools
        ],
        "servers_scanned": sum(1 for c in manager.servers if True),
    })


@router.post("/servers/register")
async def register_mcp_tools() -> dict[str, Any]:
    """
    将所有 MCP 工具注册到全局 ToolRegistry。
    注册后 Agent 对话即可使用这些工具。

    前置条件：至少有一个 MCP 服务器处于 connected 状态

    Response:
        success: bool
        tools_registered: int
        message: str
    """
    manager = get_mcp_manager()
    if not manager.is_connected:
        _err(MCPErrCode.DISCONNECTED, "No MCP servers connected")

    count = await manager.register_to_toolset()

    return _ok({
        "tools_registered": count,
        "message": f"Registered {count} MCP tools to global registry",
    })


@router.post("/servers/{name}/reconnect")
async def reconnect_server(name: str) -> dict[str, Any]:
    """
    重连指定的 MCP 服务器。

    Path: name — 服务器名称

    流程：disconnect → wait(0.5s) → connect（含可能的自动重连链）

    Response:
        success: bool
        message: str
        state: string                  — 新的连接状态
    """
    manager = get_mcp_manager()
    client = await manager.get_server(name)
    if not client:
        _err(MCPErrCode.NOT_FOUND, f"Server '{name}' not found")

    ok = await manager.reconnect_server(name)
    new_state = client.state.value

    return _ok({
        "success": ok,
        "message": (
            f"Server '{name}' reconnected successfully"
            if ok else
            f"Server '{name}' reconnect failed (state={new_state})"
        ),
        "state": new_state,
    })


@router.get("/servers/{name}/health")
async def get_server_health(name: str) -> dict[str, Any]:
    """
    执行单个 MCP 服务器的健康检查。

    Path: name — 服务器名称

    Response:
        healthy: bool
        latency_ms: float
        state: string
        uptime_seconds: float
        success_rate: float
        detail: string
    """
    manager = get_mcp_manager()
    health = await manager.health_check(name)

    if "error" in health:
        _err(MCPErrCode.NOT_FOUND, health["error"])

    return _ok({**health})


@router.post("/health")
async def check_all_health() -> dict[str, Any]:
    """
    检查所有 MCP 服务器的健康状态。

    Response:
        overall_healthy: bool
        servers_checked: int
        servers_healthy: int
        details: dict<string, HealthResult>
    """
    manager = get_mcp_manager()
    health = await manager.health_check()
    return _ok(health)


@router.post("/tools/call")
async def call_tool_directly(payload: MCPCallToolRequest) -> dict[str, Any]:
    """
    直接调用 MCP 工具（调试/测试用途）。

    Request body:
        server_name: str   — 目标服务器
        tool_name: str     — 工具名称
        arguments: dict    — 参数

    Response:
        success: bool
        content: any[]     — MCP 标准内容数组
        is_error: bool
        latency_ms: float
    """
    manager = get_mcp_manager()
    client = await manager.get_server(payload.server_name)
    if not client:
        _err(MCPErrCode.NOT_FOUND, f"Server '{payload.server_name}' not found")

    if not client.is_connected:
        _err(MCPErrCode.DISCONNECTED,
             f"Server '{payload.server_name}' is not connected")

    try:
        result = await client.call_tool(payload.tool_name, payload.arguments)
        return _ok({
            "content": result.content,
            "is_error": result.is_error,
            "latency_ms": round(result.latency_ms, 2),
        })
    except Exception as e:
        _err(MCPErrCode.TOOL_EXEC_ERROR, str(e))
