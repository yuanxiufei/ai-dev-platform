"""
MCP 客户端 — Model Context Protocol 集成

借鉴 AstrBot agent/mcp_client.py 设计，支持三种传输：
- SSE (Server-Sent Events) — HTTP + SSE 双向通信
- Streamable HTTP — 单次 HTTP POST 流式响应
- Stdio — 本地子进程标准输入/输出

特性：
- 自动重连（指数退避 + 抖动）
- 心跳健康检查
- 工具列表自动发现 (list_tools)
- MCP 工具无缝注册到 ToolRegistry
- 多 MCP 服务器管理
- 安全验证（命令白名单 + 注入防护）
- 统一错误码体系

协议参考：
  https://modelcontextprotocol.io/docs/concepts/transports
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, AsyncIterator

import httpx

from app.core.mcp.security import (  # noqa: F401
    validate_mcp_stdio_config,
    validate_mcp_command_safe,
    validate_mcp_url,
    validate_mcp_server_config,
)

logger = logging.getLogger("mcp.client")


# ── MCP 错误码 ───────────────────────────────────────────


class MCPErrCode(IntEnum):
    """MCP 操作统一错误码"""
    # 通用 1xxx
    OK = 0
    UNKNOWN = 1001
    INVALID_CONFIG = 1002
    ALREADY_EXISTS = 1003
    NOT_FOUND = 1004

    # 连接 2xxx
    CONNECT_FAILED = 2001
    CONNECT_TIMEOUT = 2002
    DISCONNECTED = 2003
    RECONNECT_EXHAUSTED = 2004
    INIT_FAILED = 2005

    # 协议 3xxx
    PROTOCOL_ERROR = 3001
    JSONRPC_ERROR = 3002
    METHOD_NOT_FOUND = 3003
    INVALID_PARAMS = 3004

    # 工具 4xxx
    TOOL_NOT_FOUND = 4001
    TOOL_EXEC_ERROR = 4002
    TOOL_TIMEOUT = 4003

    # 资源 5xxx
    RESOURCE_NOT_FOUND = 5001
    RESOURCE_READ_ERROR = 5002

    # 安全 6xxx
    SECURITY_VIOLATION = 6001
    COMMAND_DENIED = 6002

    @property
    def http_status(self) -> int:
        """映射到 HTTP 状态码"""
        mapping = {
            self.OK: 200,
            self.NOT_FOUND: 404,
            self.ALREADY_EXISTS: 409,
            self.INVALID_CONFIG: 422,
            self.CONNECT_FAILED: 502,
            self.CONNECT_TIMEOUT: 504,
            self.DISCONNECTED: 503,
            self.SECURITY_VIOLATION: 403,
        }
        return mapping.get(self, 500)

    @property
    def message(self) -> str:
        """默认人类可读消息"""
        _messages = {
            self.OK: "Success",
            self.UNKNOWN: "Unknown error",
            self.INVALID_CONFIG: "Invalid configuration",
            self.ALREADY_EXISTS: "Resource already exists",
            self.NOT_FOUND: "Resource not found",
            self.CONNECT_FAILED: "Connection failed",
            self.CONNECT_TIMEOUT: "Connection timeout",
            self.DISCONNECTED: "Not connected",
            self.RECONNECT_EXHAUSTED: "All reconnection attempts exhausted",
            self.INIT_FAILED: "MCP initialize handshake failed",
            self.PROTOCOL_ERROR: "Protocol error",
            self.JSONRPC_ERROR: "JSON-RPC error response",
            self.METHOD_NOT_FOUND: "Method not found",
            self.INVALID_PARAMS: "Invalid parameters",
            self.TOOL_NOT_FOUND: "Tool not found",
            self.TOOL_EXEC_ERROR: "Tool execution error",
            self.TOOL_TIMEOUT: "Tool execution timeout",
            self.RESOURCE_NOT_FOUND: "Resource not found",
            self.RESOURCE_READ_ERROR: "Resource read error",
            self.SECURITY_VIOLATION: "Security violation",
            self.COMMAND_DENIED: "Command denied by security policy",
        }
        return _messages.get(self, "Unknown error")


class MCPError(Exception):
    """MCP 统一异常"""

    def __init__(self, code: MCPErrCode | int, message: str = "", detail: Any = None):
        if isinstance(code, int):
            code = MCPErrCode(code)
        self.code = code
        self.message = message or code.message
        self.detail = detail
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error_code": self.code.value,
            "error": self.message,
            "detail": self.detail,
        }


# ── 传输类型 ────────────────────────────────────────────────


class MCPTransport(str, Enum):
    """MCP 传输协议"""
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"
    STDIO = "stdio"


# ── 连接状态 ────────────────────────────────────────────────


class ConnState(str, Enum):
    """MCP 服务器连接状态"""
    DISCONNECTED = "disconnected"       # 未连接
    CONNECTING = "connecting"           # 正在连接
    CONNECTED = "connected"             # 已连接（正常）
    RECONNECTING = "reconnecting"       # 重连中
    FAILED = "failed"                   # 永久失败（放弃重连）
    DISABLED = "disabled"               # 已禁用


# ── MCP 工具 ────────────────────────────────────────────────


@dataclass
class MCPToolInfo:
    """从 MCP 服务器发现的工具描述"""
    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str = ""

    def to_openai_function(self) -> dict[str, Any]:
        """转为 OpenAI Function Calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }


@dataclass
class MCPCallResult:
    """MCP 工具调用结果"""
    tool_name: str
    content: list[dict[str, Any]]
    is_error: bool = False
    latency_ms: float = 0
    error_code: MCPErrCode | None = None


# ── 服务器状态快照 ──────────────────────────────────────────


@dataclass
class MCPServerStatus:
    """单个 MCP 服务器的完整状态快照（用于 API 返回）"""
    name: str
    transport: str
    url: str = ""
    command: str = ""
    state: str = ConnState.DISCONNECTED.value
    connected: bool = False
    tools_count: int = 0
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_prefix: str = ""
    auto_discover: bool = True
    enabled: bool = True
    timeout_seconds: float = 30.0
    # 时间戳
    connected_at: float = 0          # epoch seconds
    last_heartbeat_at: float = 0     # 上次心跳时间
    last_error: str = ""              # 最近一次错误信息
    retry_count: int = 0              # 当前重试次数
    total_retries: int = 0            # 累计重试次数
    # 统计
    calls_total: int = 0              # 累计调用次数
    calls_success: int = 0            # 成功次数
    calls_failed: int = 0             # 失败次数
    avg_latency_ms: float = 0         # 平均延迟

    @property
    def uptime_seconds(self) -> float:
        """运行时长（秒）"""
        if not self.connected_at:
            return 0
        return time.time() - self.connected_at

    @property
    def success_rate(self) -> float:
        """调用成功率 (0~1)"""
        total = self.calls_success + self.calls_failed
        if total == 0:
            return 1.0
        return self.calls_success / total


# ── MCP 服务器配置 ──────────────────────────────────────────


@dataclass
class MCPServerConfig:
    """MCP 服务器配置"""
    name: str
    transport: MCPTransport = MCPTransport.SSE

    # HTTP 传输
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    # Stdio 传输
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    # 连接管理
    reconnect: bool = True
    max_retries: int = 5
    retry_delay_seconds: float = 2.0
    retry_jitter_seconds: float = 1.0   # 随机抖动范围
    timeout_seconds: float = 30.0

    # 心跳
    heartbeat_interval_seconds: float = 30.0  # 0 = 禁用心跳

    # 工具管理
    tool_prefix: str = ""  # 工具名前缀（避免冲突）
    auto_discover: bool = True
    enabled: bool = True


# ── MCP 客户端 ──────────────────────────────────────────────


class MCPClient:
    """
    MCP 协议客户端

    支持三种传输方式：
    - SSE: GET /sse 获取 endpoint → POST /message 发送请求
    - Streamable HTTP: POST /message 直接流式响应
    - Stdio: 启动子进程，通过 stdin/stdout JSON-RPC 通信

    用法:
        client = MCPClient(MCPServerConfig(
            name="my-server",
            transport=MCPTransport.SSE,
            url="http://localhost:18000/sse",
        ))
        await client.connect()
        tools = await client.list_tools()
        result = await client.call_tool("my_tool", {"arg": "value"})
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._http_client: httpx.AsyncClient | None = None
        self._session_id: str = ""
        self._message_endpoint: str = ""
        self._process: subprocess.Popen[str] | None = None  # type: ignore[assignment]
        self._next_id: int = 0
        self._connected: bool = False
        self._lock = asyncio.Lock()
        self._state: ConnState = (
            ConnState.DISCONNECTED if config.enabled else ConnState.DISABLED
        )

        # 统计 & 重连状态
        self._retry_count: int = 0
        self._total_retries: int = 0
        self._calls_total: int = 0
        self._calls_success: int = 0
        self._calls_failed: int = 0
        self._latencies: list[float] = []  # 最近 N 次 latency
        self._latency_window: int = 50      # 保留最近 50 个样本
        self._connected_at: float = 0
        self._last_heartbeat_at: float = 0
        self._last_error: str = ""

        # 心跳任务
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._heartbeat_cancel = asyncio.Event()

    # ── 属性 ────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def state(self) -> ConnState:
        return self._state

    @property
    def status(self) -> MCPServerStatus:
        """返回服务器状态快照"""
        avg_lat = sum(self._latencies) / len(self._latencies) if self._latencies else 0
        return MCPServerStatus(
            name=self.config.name,
            transport=self.config.transport.value,
            url=self.config.url,
            command=f"{self.config.command} {' '.join(self.config.args)}".strip(),
            state=self._state.value,
            connected=self._connected,
            tool_prefix=self.config.tool_prefix,
            auto_discover=self.config.auto_discover,
            enabled=self.config.enabled,
            timeout_seconds=self.config.timeout_seconds,
            connected_at=self._connected_at,
            last_heartbeat_at=self._last_heartbeat_at,
            last_error=self._last_error,
            retry_count=self._retry_count,
            total_retries=self._total_retries,
            calls_total=self._calls_total,
            calls_success=self._calls_success,
            calls_failed=self._calls_failed,
            avg_latency_ms=avg_lat,
        )

    # ── 连接管理 ────────────────────────────────────────

    async def connect(self) -> bool:
        """
        建立到 MCP 服务器的连接。

        Returns:
            True 连接成功, False 失败
        """
        if not self.config.enabled:
            logger.info("MCP '%s' is disabled, skipping connect", self.config.name)
            return False

        self._next_id = 0
        self._state = ConnState.CONNECTING

        try:
            if self.config.transport == MCPTransport.STDIO:
                ok = await self._connect_stdio()
            else:
                ok = await self._connect_http()

            if ok:
                self._connected = True
                self._state = ConnState.CONNECTED
                self._connected_at = time.time()
                self._retry_count = 0
                self._last_error = ""

                # 启动心跳
                if self.config.heartbeat_interval_seconds > 0:
                    self._start_heartbeat()

                logger.info(
                    "MCP '%s' connected (%s)",
                    self.config.name, self.config.transport.value,
                )
                return True
            else:
                self._state = ConnState.FAILED
                return False

        except Exception as e:
            err_msg = f"{type(e).__name__}: {e}"
            self._state = ConnState.FAILED
            self._last_error = err_msg
            logger.error(
                "MCP '%s' connect failed (%s): %s",
                self.config.name, self.config.transport.value, err_msg,
            )

            # 自动重连
            if self.config.reconnect:
                asyncio.create_task(self._auto_reconnect())
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        await self._stop_heartbeat()
        self._connected = False
        self._state = ConnState.DISCONNECTED
        self._connected_at = 0

        if self._http_client:
            try:
                await self._http_client.aclose()
            except Exception:
                pass
            self._http_client = None

        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        logger.info("MCP '%s' disconnected", self.config.name)

    async def reconnect(self) -> bool:
        """显式重连（先断开再重新连接）"""
        logger.info("MCP '%s' manual reconnect...", self.config.name)
        await self.disconnect()
        # 给一点缓冲时间
        await asyncio.sleep(0.5)
        return await self.connect()

    async def update_config(self, **kwargs: Any) -> None:
        """
        更新运行时配置（无需重建客户端）。

        支持的参数：url, headers, command, args, env, timeout_seconds,
                     max_retries, retry_delay_seconds, tool_prefix,
                     auto_discover, enabled, heartbeat_interval_seconds
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
            else:
                raise ValueError(f"Unknown config key: {key}")

        logger.info("MCP '%s' config updated: %s", self.config.name, list(kwargs.keys()))

        # 如果从禁用变为启用，尝试连接
        if kwargs.get("enabled") and not self._connected:
            await self.connect()

    # ── 内部连接实现 ───────────────────────────────────

    async def _connect_http(self) -> bool:
        """建立 HTTP 连接（SSE 或 Streamable HTTP）"""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds),
                headers={
                    "Content-Type": "application/json",
                    **self.config.headers,
                },
            )

        if self.config.transport == MCPTransport.SSE:
            # SSE: GET /sse → 获取 session + message endpoint
            try:
                async with self._http_client.stream("GET", self.config.url) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.startswith("data: "):
                            data = json.loads(line[6:])
                            if "sessionId" in data:
                                self._session_id = data["sessionId"]
                            if "messageEndpoint" in data:
                                self._message_endpoint = data["messageEndpoint"]
                                break
                        elif line.startswith("event: endpoint"):
                            pass
            except Exception as e:
                logger.error("MCP '%s' SSE handshake failed: %s", self.config.name, e)
                return False

            if not self._message_endpoint:
                base = self.config.url.rstrip("/")
                if base.endswith("/sse"):
                    self._message_endpoint = base[:-4] + "/message"
                else:
                    self._message_endpoint = base + "/message"

            logger.debug(
                "MCP '%s' SSE endpoint acquired: %s",
                self.config.name, self._message_endpoint,
            )
        else:
            # Streamable HTTP: 直接用 URL 作为 message endpoint
            self._message_endpoint = self.config.url

        # 发送 initialize 握手
        init_result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "ai-fullstack-platform",
                "version": "2.0.0",
            },
        })
        if not init_result:
            self._last_error = "initialize handshake failed"
            logger.error("MCP '%s' initialize failed", self.config.name)
            return False

        return True

    async def _connect_stdio(self) -> bool:
        """启动 Stdio 子进程"""
        env = {**os.environ, **self.config.env}

        # 安全校验
        sec_errors = validate_mcp_stdio_config(
            self.config.command, self.config.args, self.config.env,
        )
        if sec_errors:
            self._last_error = f"Security check failed: {'; '.join(sec_errors)}"
            logger.error("MCP '%s' security violation: %s", self.config.name, sec_errors)
            raise MCPError(MCPErrCode.SECURITY_VIOLATION, self._last_error)

        try:
            self._process = subprocess.Popen(
                [self.config.command, *self.config.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            self._last_error = f"Command not found: {self.config.command}"
            logger.error("MCP '%s': %s", self.config.name, self._last_error)
            return False
        except Exception as e:
            self._last_error = f"Process spawn failed: {e}"
            logger.error("MCP '%s': %s", self.config.name, self._last_error)
            return False

        # Initialize
        init_result = await self._send_stdio_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "ai-fullstack-platform",
                "version": "2.0.0",
            },
        })
        if not init_result:
            return False

        return True

    # ── 自动重连 ────────────────────────────────────────

    async def _auto_reconnect(self) -> None:
        """
        自动重连逻辑：指数退避 + 随机抖动

        delay = base_delay * 2^attempt + random(0, jitter)
        最大重试次数由 config.max_retries 控制。
        """
        if not self.config.reconnect or self.config.max_retries <= 0:
            self._state = ConnState.FAILED
            return

        self._state = ConnState.RECONNECTING
        base_delay = self.config.retry_delay_seconds
        jitter = self.config.retry_jitter_seconds
        max_attempts = self.config.max_retries

        for attempt in range(1, max_attempts + 1):
            # 计算延迟：指数退避 + 随机抖动
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, jitter)
            self._retry_count = attempt
            self._total_retries += 1

            logger.info(
                "MCP '%s' reconnect attempt %d/%d in %.1fs...",
                self.config.name, attempt, max_attempts, delay,
            )
            await asyncio.sleep(delay)

            try:
                ok = await self.connect()
                if ok:
                    logger.info(
                        "MCP '%s' reconnected successfully (attempt %d)",
                        self.config.name, attempt,
                    )
                    return
            except Exception as e:
                logger.warning(
                    "MCP '%s' reconnect attempt %d failed: %s",
                    self.config.name, attempt, e,
                )

        # 所有重试耗尽
        self._state = ConnState.FAILED
        self._last_error = f"All {max_attempts} reconnect attempts exhausted"
        logger.error("MCP '%s': %s", self.config.name, self._last_error)

    # ── 心跳健康检查 ────────────────────────────────────

    def _start_heartbeat(self) -> None:
        """启动心跳任务"""
        self._stop_heartbeat()
        self._heartbeat_cancel.clear()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _stop_heartbeat(self) -> None:
        """停止心跳任务"""
        self._heartbeat_cancel.set()
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except (asyncio.CancelledError, Exception):
                pass
            self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """
        心跳循环。

        通过发送 ping 或轻量级请求来检测连接是否存活。
        如果心跳失败，触发自动重连。
        """
        interval = self.config.heartbeat_interval_seconds
        while not self._heartbeat_cancel.is_set():
            try:
                await asyncio.wait_for(
                    self._heartbeat_cancel.wait(), timeout=interval,
                )
                return  # 收到取消信号
            except asyncio.TimeoutError:
                pass

            try:
                # 使用 ping 方法（如果服务器支持），否则用空 tools/list 作为探活
                result = await self._send_request("ping", {})
                if result is None:
                    # ping 不支持，尝试 tools/list 作为备选
                    result = await self._send_request("tools/list", {})

                self._last_heartbeat_at = time.time()
                logger.debug("MCP '%s' heartbeat OK", self.config.name)

            except Exception as e:
                self._last_heartbeat_at = 0
                logger.warning(
                    "MCP '%s' heartbeat failed: %s", self.config.name, e,
                )
                # 心跳失败 → 触发重连
                if self.config.reconnect and self._connected:
                    asyncio.create_task(self._auto_reconnect())
                    return  # 重连会启动新的心跳

    async def health_check(self) -> dict[str, Any]:
        """
        执行健康检查并返回详细状态。

        Returns:
            包含 healthy, latency_ms, state 等信息的字典
        """
        start = time.monotonic()
        healthy = False
        detail = ""

        try:
            if not self._connected:
                detail = "not connected"
            elif not self._http_client and not self._process:
                detail = "no active connection channel"
            else:
                result = await self._send_request("ping", {})
                if result is None:
                    result = await self._send_request("tools/list", {})

                healthy = result is not None
                if not healthy:
                    detail = "request returned no data"
                else:
                    self._last_heartbeat_at = time.time()
        except Exception as e:
            detail = str(e)[:200]

        elapsed_ms = (time.monotonic() - start) * 1000

        return {
            "healthy": healthy,
            "latency_ms": round(elapsed_ms, 2),
            "state": self._state.value,
            "connected": self._connected,
            "detail": detail,
            "uptime_seconds": round(self.status.uptime_seconds, 1),
            "success_rate": round(self.status.success_rate, 4),
            "last_heartbeat_age_seconds": (
                round(time.time() - self._last_heartbeat_at, 1)
                if self._last_heartbeat_at else -1
            ),
        }

    # ── JSON-RPC 通信 ───────────────────────────────────

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """发送 JSON-RPC 请求（带统计）"""
        request_id = self._next_id
        self._next_id += 1
        self._calls_total += 1

        start_time = time.monotonic()

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        if self.config.transport == MCPTransport.STDIO:
            result = await self._send_stdio_request(method, params)
        else:
            result = await self._send_http_request(payload)

        # 记录统计
        elapsed_ms = (time.monotonic() - start_time) * 1000
        self._record_latency(elapsed_ms)
        if result is not None and method != "ping":
            self._calls_success += 1
        elif result is None and method != "ping":
            self._calls_failed += 1

        return result

    async def _send_http_request(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """HTTP 发送请求"""
        if not self._http_client or not self._message_endpoint:
            return None

        try:
            headers = {}
            if self.config.transport == MCPTransport.SSE and self._session_id:
                headers["X-Session-Id"] = self._session_id

            resp = await self._http_client.post(
                self._message_endpoint,
                json=payload,
                headers=headers,
            )
            data = resp.json()

            if "error" in data:
                err_info = data["error"]
                msg = err_info.get("message", str(err_info))
                code = err_info.get("code", -1)
                logger.warning(
                    "MCP '%s' JSON-RPC error (code=%d): %s",
                    self.config.name, code, msg,
                )
                self._last_error = f"[{code}] {msg}"
                return None

            return data.get("result", {})

        except httpx.TimeoutException:
            self._last_error = "Request timeout"
            logger.warning("MCP '%s' request timeout", self.config.name)
            return None
        except httpx.HTTPError as e:
            self._last_error = f"HTTP error: {e}"
            logger.error("MCP '%s' HTTP error: %s", self.config.name, e)
            return None
        except Exception as e:
            self._last_error = f"Unexpected error: {str(e)[:200]}"
            logger.error("MCP '%s' request error: %s", self.config.name, self._last_error)
            return None

    async def _send_stdio_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """通过 stdio 发送 JSON-RPC 请求"""
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None

        request_id = self._next_id
        self._next_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        loop = asyncio.get_event_loop()
        try:
            line = json.dumps(payload) + "\n"
            self._process.stdin.write(line)
            self._process.stdin.flush()

            response_line = await asyncio.wait_for(
                loop.run_in_executor(None, self._process.stdout.readline),
                timeout=self.config.timeout_seconds,
            )

            if not response_line:
                self._last_error = "Empty response from stdio process"
                return None

            data = json.loads(response_line.strip())
            if "error" in data:
                err_info = data["error"]
                msg = err_info.get("message", str(err_info))
                self._last_error = f"[stdio] {msg}"
                logger.warning("MCP '%s' stdio error: %s", self.config.name, self._last_error)
                return None

            return data.get("result", {})

        except asyncio.TimeoutError:
            self._last_error = f"Stdio timeout ({method})"
            logger.warning("MCP '%s' stdio timeout for %s", self.config.name, method)
            return None
        except BrokenPipeError:
            self._last_error = "Broken pipe (process likely exited)"
            logger.error("MCP '%s' broken pipe", self.config.name)
            # 尝试重连
            if self.config.reconnect and self._connected:
                asyncio.create_task(self._auto_reconnect())
            return None
        except Exception as e:
            self._last_error = f"Stdio error: {e}"
            logger.error("MCP '%s' stdio error: %s", self.config.name, e)
            return None

    # ── 统计辅助 ────────────────────────────────────────

    def _record_latency(self, ms: float) -> None:
        """记录延迟采样（滑动窗口）"""
        self._latencies.append(ms)
        if len(self._latencies) > self._latency_window:
            self._latencies.pop(0)

    # ── 工具操作 ────────────────────────────────────────

    async def list_tools(self) -> list[MCPToolInfo]:
        """列出 MCP 服务器提供的所有工具"""
        result = await self._send_request("tools/list", {})
        if not result:
            return []

        tools: list[MCPToolInfo] = []
        for t in result.get("tools", []):
            name = t["name"]
            if self.config.tool_prefix:
                name = f"{self.config.tool_prefix}_{name}"

            tools.append(MCPToolInfo(
                name=name,
                description=t.get("description", ""),
                input_schema=t.get("inputSchema", {"type": "object", "properties": {}}),
                server_name=self.config.name,
            ))

        return tools

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        """调用 MCP 工具"""
        start = time.monotonic()

        # 去掉前缀
        real_name = tool_name
        if self.config.tool_prefix and tool_name.startswith(self.config.tool_prefix + "_"):
            real_name = tool_name[len(self.config.tool_prefix) + 1:]

        result = await self._send_request("tools/call", {
            "name": real_name,
            "arguments": arguments,
        })

        elapsed_ms = (time.monotonic() - start) * 1000

        if not result:
            return MCPCallResult(
                tool_name=tool_name,
                content=[{"type": "text", "text": self._last_error or "MCP tool call failed"}],
                is_error=True,
                latency_ms=elapsed_ms,
                error_code=MCPErrCode.TOOL_EXEC_ERROR,
            )

        is_err = result.get("isError", False)
        content = result.get("content", [])
        err_code = MCPErrCode.TOOL_EXEC_ERROR if is_err else None

        return MCPCallResult(
            tool_name=tool_name,
            content=content,
            is_error=is_err,
            latency_ms=elapsed_ms,
            error_code=err_code,
        )

    # ── 资源操作 ────────────────────────────────────────

    async def list_resources(self) -> list[dict[str, Any]]:
        """列出 MCP 服务器提供的资源"""
        result = await self._send_request("resources/list", {})
        if not result:
            return []
        return result.get("resources", [])

    async def read_resource(self, uri: str) -> dict[str, Any] | None:
        """读取 MCP 资源"""
        return await self._send_request("resources/read", {"uri": uri})


# ── MCP 管理器（多服务器） ─────────────────────────────────


@dataclass
class MCPManagerResult:
    """管理器操作结果"""
    success: bool
    error_code: MCPErrCode = MCPErrCode.OK
    total_servers: int = 0
    connected: int = 0
    tools_discovered: int = 0
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


class MCPManager:
    """
    MCP 多服务器管理器

    管理多个 MCP 服务器连接，自动发现工具并注册到 ToolRegistry。

    特性：
    - 并发连接 / 断开
    - 自动重连委托给各 MCPClient
    - 工具路由到正确的服务器
    - 全局状态聚合

    用法:
        manager = MCPManager([
            MCPServerConfig(name="filesystem", transport=MCPTransport.STDIO, ...),
            MCPServerConfig(name="my-api", transport=MCPTransport.SSE, url="..."),
        ])
        await manager.connect_all()
        tools = await manager.discover_all_tools()
    """

    def __init__(self, servers: list[MCPServerConfig] | None = None):
        self._clients: dict[str, MCPClient] = {}
        self._tools: dict[str, MCPToolInfo] = {}
        self._connected: bool = False

        for s in (servers or []):
            self.add_server(s)

    def add_server(self, config: MCPServerConfig) -> None:
        """添加 MCP 服务器（如果已存在则替换）"""
        if config.name in self._clients:
            # 先断开旧连接
            old = self._clients[config.name]
            logger.warning(
                "MCP server '%s' already exists, replacing (old state=%s)",
                config.name, old.state.value,
            )
            # 清理旧的工具引用
            self._tools = {
                k: v for k, v in self._tools.items()
                if v.server_name != config.name
            }

        self._clients[config.name] = MCPClient(config)

    def remove_server(self, name: str) -> bool:
        """移除 MCP 服务器并断开连接"""
        client = self._clients.pop(name, None)
        if client is None:
            return False

        # 异步断开（不等待完成以避免阻塞）
        asyncio.create_task(client.disconnect())

        # 清理关联工具
        self._tools = {
            k: v for k, v in self._tools.items()
            if v.server_name != name
        }
        return True

    async def get_server(self, name: str) -> MCPClient | None:
        """获取指定名称的 MCP 客户端"""
        return self._clients.get(name)

    async def update_server(self, name: str, **kwargs: Any) -> bool:
        """更新服务器配置（委托给 client.update_config）"""
        client = self._clients.get(name)
        if not client:
            return False
        await client.update_config(**kwargs)
        return True

    async def reconnect_server(self, name: str) -> bool:
        """重连指定的服务器"""
        client = self._clients.get(name)
        if not client:
            return False
        return await client.reconnect()

    async def health_check(self, name: str | None = None) -> dict[str, Any]:
        """
        执行健康检查。

        Args:
            name: 指定服务器名，None 表示全部

        Returns:
            健康检查结果字典
        """
        if name:
            client = self._clients.get(name)
            if not client:
                return {"healthy": False, "error": f"Server '{name}' not found"}
            return await client.health_check()

        # 全部服务器的健康汇总
        results = {}
        all_healthy = True
        for n, c in self._clients.items():
            r = await c.health_check()
            results[n] = r
            if not r.get("healthy"):
                all_healthy = False

        return {
            "overall_healthy": all_healthy,
            "servers_checked": len(results),
            "servers_healthy": sum(1 for r in results.values() if r.get("healthy")),
            "details": results,
        }

    # ── 批量操作 ──────────────────────────────────────

    async def connect_all(self) -> MCPManagerResult:
        """并发连接所有已启用的 MCP 服务器"""
        result = MCPManagerResult(success=False)
        result.total_servers = len(self._clients)

        tasks = []
        names = []
        for name, client in self._clients.items():
            if client.config.enabled:
                tasks.append(client.connect())
                names.append(name)

        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for name, outcome in zip(names, outcomes):
            if isinstance(outcome, Exception):
                result.connected += 0
                result.errors.append(f"Server '{name}': {outcome}")
            elif outcome:
                result.connected += 1
            else:
                result.errors.append(f"Server '{name}' connection failed")

        self._connected = result.connected > 0
        result.success = result.connected > 0
        if not result.success:
            result.error_code = MCPErrCode.CONNECT_FAILED

        return result

    async def disconnect_all(self) -> None:
        """断开所有连接"""
        tasks = [c.disconnect() for c in self._clients.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
        self._connected = False

    async def discover_all_tools(self) -> list[MCPToolInfo]:
        """扫描所有已连接服务器的工具"""
        all_tools: list[MCPToolInfo] = []
        for name, client in self._clients.items():
            if not client.is_connected:
                continue
            try:
                tools = await client.list_tools()
                all_tools.extend(tools)
                logger.info(
                    "MCP '%s': discovered %d tools", name, len(tools),
                )
            except Exception as e:
                logger.error(
                    "MCP '%s': tool discovery failed: %s", name, e,
                )

        self._tools = {t.name: t for t in all_tools}
        return all_tools

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> MCPCallResult:
        """调用已发现的 MCP 工具"""
        tool_info = self._tools.get(tool_name)
        if not tool_info:
            return MCPCallResult(
                tool_name=tool_name,
                content=[{"type": "text", "text": f"Tool '{tool_name}' not found"}],
                is_error=True,
                error_code=MCPErrCode.TOOL_NOT_FOUND,
            )

        client = self._clients.get(tool_info.server_name)
        if not client or not client.is_connected:
            return MCPCallResult(
                tool_name=tool_name,
                content=[{"type": "text", "text": f"MCP server '{tool_info.server_name}' not connected"}],
                is_error=True,
                error_code=MCPErrCode.DISCONNECTED,
            )

        return await client.call_tool(tool_name, arguments)

    async def register_to_toolset(self) -> int:
        """
        将 MCP 工具注册到全局 ToolRegistry

        Returns:
            注册的工具数量
        """
        from app.core.tools.registry import get_tool_registry

        tools = await self.discover_all_tools()
        registry = get_tool_registry()

        count = 0
        for t in tools:
            from app.core.tools.schema import FunctionTool, ToolSchema

            props = t.input_schema.get("properties", {})
            required = t.input_schema.get("required", [])

            tool = FunctionTool(
                schema=ToolSchema(
                    name=t.name,
                    description=t.description,
                    parameters=[],
                    category="mcp",
                    tags=[t.server_name, "mcp"],
                ),
                func=self._make_mcp_callable(t.name),
                tool_id=f"mcp:{t.server_name}:{t.name}",
            )
            registry.register_sync(tool)
            count += 1

        logger.info("Registered %d MCP tools to global registry", count)
        return count

    def _make_mcp_callable(self, tool_name: str):
        """创建 MCP 工具的 callable 包装"""
        async def mcp_call(**kwargs):
            result = await self.call_tool(tool_name, kwargs)
            texts = []
            for item in result.content:
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
            return "\n".join(texts) if texts else json.dumps(result.content)
        return mcp_call

    # ── 状态聚合 ──────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def servers(self) -> list[str]:
        return list(self._clients.keys())

    @property
    def tools(self) -> list[MCPToolInfo]:
        return list(self._tools.values())

    def get_all_statuses(self) -> list[MCPServerStatus]:
        """获取所有服务器的状态快照（用于 API 返回）"""
        return [client.status for client in self._clients.values()]
