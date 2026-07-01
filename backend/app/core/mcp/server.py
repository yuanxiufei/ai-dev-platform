"""
MCP Server — SAG 风格的 Model Context Protocol 服务端实现

借鉴 SAG src/mcp/server.ts 架构:
  - 4 个核心工具: sag_search, sag_ingest, sag_list_sources, sag_get_event
  - 进度通知: /notifications/progress 带 status/detail
  - 日志管道: logging/setLevel + logging/message
  - 工具调用记录: 持久化到 DB
  - 双模式: stdio / SSE

协议: JSON-RPC 2.0
  - initialize: 握手
  - tools/list: 列出工具
  - tools/call: 调用工具
  - notifications/progress: 推送进度
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional, Callable

logger = logging.getLogger("mcp.server")


# ── 工具定义 ────────────────────────────────────────────────

MCP_TOOLS = [
    {
        "name": "sag_search",
        "description": "在知识库中执行 GraphRAG 多跳检索。返回最相关的事件和切片。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索查询"},
                "source_ids": {
                    "type": "array", "items": {"type": "string"},
                    "description": "知识库 ID 列表 (空=全部)",
                },
                "strategy": {
                    "type": "string", "enum": ["vector", "multi"],
                    "description": "检索策略: vector=纯向量, multi=多跳图检索",
                },
                "search_mode": {
                    "type": "string", "enum": ["fast", "standard"],
                    "description": "fast=BM25+rerank(低延迟), standard=LLM抽取+Rerank(高质量)",
                },
                "top_k": {"type": "integer", "description": "返回结果数 (默认10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "sag_ingest",
        "description": "将文档/文本摄入知识库，构建事件-实体图索引。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要摄入的文本内容"},
                "source_id": {"type": "string", "description": "目标知识库 ID"},
                "document_name": {"type": "string", "description": "文档名称"},
                "chunk_size": {"type": "integer", "description": "分块大小 (默认1024)"},
                "chunk_overlap": {"type": "integer", "description": "分块重叠 (默认200)"},
            },
            "required": ["text", "source_id"],
        },
    },
    {
        "name": "sag_list_sources",
        "description": "列出所有可用的知识库来源。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "返回数量 (默认50)"},
                "cursor": {"type": "string", "description": "分页游标"},
            },
        },
    },
    {
        "name": "sag_get_event",
        "description": "获取指定事件的详细信息，包括关联实体和来源切片。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "事件 ID"},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "sag_status",
        "description": "获取知识库的统计信息 (文档数/切片数/事件数/实体数)。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "知识库 ID"},
            },
            "required": ["source_id"],
        },
    },
]


# ── 进度通知 ────────────────────────────────────────────────

@dataclass
class ProgressNotification:
    """搜索/摄入进度通知"""
    type: str = "step"
    status: str = "running"  # running | done | failed
    key: str = ""
    title: str = ""
    detail: str = ""
    duration_ms: float = 0
    payload: Any = None

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "status": self.status,
            "key": self.key,
            "title": self.title,
            "detail": self.detail,
            "durationMs": self.duration_ms,
            "payload": self.payload,
        }


# ── MCP Server ──────────────────────────────────────────────

@dataclass
class MCPServerConfig:
    """MCP Server 配置"""
    name: str = "ai-fullstack-platform-mcp"
    version: str = "2.0.0"
    transport: str = "stdio"  # stdio | sse
    sse_host: str = "0.0.0.0"
    sse_port: int = 18000


class MCPServer:
    """
    SAG 风格的 MCP Server

    特性:
      - 5 个内置工具: sag_search, sag_ingest, sag_list_sources, sag_get_event, sag_status
      - 进度通知管道: 搜索/摄入过程中的实时状态推送
      - 日志管理: 支持客户端动态调整日志级别
      - 工具调用记录: 持久化到 DB 的 mcp_tool_calls 表

    用法:
        server = MCPServer(config=MCPServerConfig(), handlers=MyToolHandlers())
        await server.run_stdio()  # 或 server.run_sse()
    """

    def __init__(
        self,
        config: Optional[MCPServerConfig] = None,
        handlers: Optional[Any] = None,
        db: Optional[Any] = None,
    ):
        self.config = config or MCPServerConfig()
        self._handlers = handlers
        self._db = db
        self._next_id = 0
        self._session_id: str = ""
        self._log_level = "info"

    # ── JSON-RPC 入口 ────────────────────────────────────

    async def handle_request(self, raw: dict) -> Optional[dict]:
        """处理 JSON-RPC 请求，返回响应"""
        method = raw.get("method", "")
        req_id = raw.get("id")
        params = raw.get("params", {})

        try:
            if method == "initialize":
                return self._response(req_id, self._handle_initialize(params))
            elif method == "tools/list":
                return self._response(req_id, {"tools": MCP_TOOLS})
            elif method == "tools/call":
                return self._response(req_id, await self._handle_tool_call(params))
            elif method == "resources/list":
                return self._response(req_id, {"resources": []})
            elif method == "notifications/initialized":
                return None  # 无需响应
            elif method == "ping":
                return self._response(req_id, {})
            elif method == "logging/setLevel":
                self._log_level = params.get("level", "info")
                logger.info("MCP log level set to: %s", self._log_level)
                return self._response(req_id, {})
            else:
                return self._error(req_id, -32601, f"Method not found: {method}")
        except Exception as e:
            logger.exception("MCP request error: %s", e)
            return self._error(req_id, -32603, str(e))

    # ── 核心方法 ──────────────────────────────────────────

    def _handle_initialize(self, params: dict) -> dict:
        """初始化握手"""
        self._session_id = str(uuid.uuid4())
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {
                "tools": {},
                "resources": {},
                "logging": {},
            },
            "serverInfo": {
                "name": self.config.name,
                "version": self.config.version,
            },
        }

    async def _handle_tool_call(self, params: dict) -> dict:
        """执行工具调用"""
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        start = time.time()

        handler_map = {
            "sag_search": self._handle_search,
            "sag_ingest": self._handle_ingest,
            "sag_list_sources": self._handle_list_sources,
            "sag_get_event": self._handle_get_event,
            "sag_status": self._handle_status,
        }

        handler = handler_map.get(tool_name)
        if not handler:
            return {"content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}], "isError": True}

        try:
            result = await handler(arguments)
            elapsed = (time.time() - start) * 1000
            await self._record_tool_call(tool_name, arguments, result, elapsed, "SUCCEEDED")
            return result
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            error_text = f"{type(e).__name__}: {e}"
            await self._record_tool_call(tool_name, arguments, None, elapsed, "FAILED", error_text)
            return {"content": [{"type": "text", "text": error_text}], "isError": True}

    # ── 工具实现 (委托给 handlers) ────────────────────────

    async def _handle_search(self, args: dict) -> dict:
        """sag_search 工具"""
        query = args.get("query", "")
        kb_ids = args.get("source_ids", [])
        strategy = args.get("strategy", "multi")
        search_mode = args.get("search_mode", "standard")
        top_k = args.get("top_k", 10)

        await self._notify_progress("search", "running", "搜索中...", f"策略={strategy} 模式={search_mode}")

        if not self._handlers or not hasattr(self._handlers, "search"):
            return {"content": [{"type": "text", "text": "Search handler not configured"}]}

        result = await self._handlers.search(
            query=query, kb_ids=kb_ids, strategy=strategy,
            search_mode=search_mode, top_k=top_k,
        )

        await self._notify_progress("search", "done", "搜索完成",
            f"找到 {len(result.get('sections', []))} 个相关片段")

        # 格式化输出
        sections = result.get("sections", [])
        if not sections:
            return {"content": [{"type": "text", "text": f"未找到与 '{query}' 相关的内容"}]}

        lines = [f"## 搜索结果: {query}\n"]
        for i, s in enumerate(sections[:top_k], 1):
            heading = s.get("heading", f"片段 {i}")
            content = s.get("content", "")[:500]
            score = s.get("score", 0)
            lines.append(f"### [{i}] {heading} (相关性: {score:.2f})")
            lines.append(content)
            lines.append("")

        return {"content": [{"type": "text", "text": "\n".join(lines)}]}

    async def _handle_ingest(self, args: dict) -> dict:
        """sag_ingest 工具"""
        text = args.get("text", "")
        kb_id = args.get("source_id", "")
        doc_name = args.get("document_name", "mcp_ingest")

        if not text or not kb_id:
            return {"content": [{"type": "text", "text": "text 和 source_id 为必填项"}], "isError": True}

        await self._notify_progress("ingest", "running", "摄入中...", f"文档={doc_name}")

        if not self._handlers or not hasattr(self._handlers, "ingest"):
            return {"content": [{"type": "text", "text": "Ingest handler not configured"}]}

        result = await self._handlers.ingest(
            text=text, kb_id=kb_id, document_name=doc_name,
            chunk_size=args.get("chunk_size", 1024),
            chunk_overlap=args.get("chunk_overlap", 200),
        )

        await self._notify_progress("ingest", "done", "摄入完成",
            f"events={result.get('events_created', 0)} entities={result.get('entities_created', 0)}")

        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}

    async def _handle_list_sources(self, args: dict) -> dict:
        """sag_list_sources 工具"""
        if not self._handlers or not hasattr(self._handlers, "list_sources"):
            return {"content": [{"type": "text", "text": "[]"}]}

        result = await self._handlers.list_sources(
            limit=args.get("limit", 50),
            cursor=args.get("cursor"),
        )

        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}

    async def _handle_get_event(self, args: dict) -> dict:
        """sag_get_event 工具"""
        event_id = args.get("event_id", "")
        if not self._handlers or not hasattr(self._handlers, "get_event"):
            return {"content": [{"type": "text", "text": "Event handler not configured"}]}

        result = await self._handlers.get_event(event_id=event_id)
        if not result:
            return {"content": [{"type": "text", "text": f"事件 {event_id} 未找到"}], "isError": True}

        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}

    async def _handle_status(self, args: dict) -> dict:
        """sag_status 工具"""
        kb_id = args.get("source_id", "")
        if not self._handlers or not hasattr(self._handlers, "get_status"):
            return {"content": [{"type": "text", "text": "Status handler not configured"}]}

        result = await self._handlers.get_status(source_id=kb_id)

        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]}

    # ── 进度通知 ──────────────────────────────────────────

    async def _notify_progress(self, key: str, status: str, title: str, detail: str, payload: Any = None):
        """推送进度通知 (SSE/stdio)"""
        notification = ProgressNotification(
            key=key, status=status, title=title, detail=detail, payload=payload)
        notif = {
            "jsonrpc": "2.0",
            "method": "notifications/progress",
            "params": notification.to_dict(),
        }
        # 由具体传输实现负责发送
        if hasattr(self, "_send_raw"):
            await self._send_raw(notif)

    # ── 工具调用记录 ──────────────────────────────────────

    async def _record_tool_call(
        self, tool_name: str, arguments: dict,
        result: Any, duration_ms: float, status: str, error: Optional[str] = None,
    ):
        """持久化工具调用记录到 DB"""
        if not self._db or not hasattr(self._db, "add_mcp_tool_call"):
            return
        try:
            await self._db.add_mcp_tool_call(
                session_id=self._session_id,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                status=status,
                duration_ms=duration_ms,
                error=error,
            )
        except Exception as e:
            logger.warning("Failed to record MCP tool call: %s", e)

    # ── JSON-RPC 格式化 ──────────────────────────────────

    def _response(self, req_id, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(self, req_id, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    # ── 传输实现 ──────────────────────────────────────────

    async def run_stdio(self):
        """通过 stdio 运行 MCP Server"""
        import sys
        logger.info("MCP Server starting (stdio)...")

        # 发送 initialize
        self._send_stdio({
            "jsonrpc": "2.0", "id": None,
            "method": "notifications/initialized", "params": {},
        })

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                response = await self.handle_request(request)
                if response:
                    self._send_stdio(response)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON-RPC: %s", line[:100])
            except Exception as e:
                logger.exception("Stdio handler error: %s", e)

    async def run_sse(self):
        """通过 SSE/HTTP 运行 MCP Server"""
        logger.info("MCP Server starting (SSE on %s:%d)...",
                     self.config.sse_host, self.config.sse_port)

        # 简化版: 使用 aiohttp
        from aiohttp import web

        async def handle_sse(request):
            resp = web.StreamResponse()
            resp.headers["Content-Type"] = "text/event-stream"
            resp.headers["Cache-Control"] = "no-cache"
            await resp.prepare(request)

            # 发送 session endpoint
            endpoint = f"http://{self.config.sse_host}:{self.config.sse_port}/message"
            await resp.write(
                f"data: {json.dumps({'sessionId': self._session_id, 'messageEndpoint': endpoint})}\n\n".encode()
            )
            await resp.write_eof()
            return resp

        async def handle_message(request):
            body = await request.json()
            response = await self.handle_request(body)
            if response:
                return web.json_response(response)
            return web.Response(status=204)

        app = web.Application()
        app.router.add_get("/sse", handle_sse)
        app.router.add_post("/message", handle_message)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.config.sse_host, self.config.sse_port)
        await site.start()
        logger.info("MCP SSE Server running on %s:%d",
                     self.config.sse_host, self.config.sse_port)

    def _send_stdio(self, message: dict):
        """通过 stdout 发送 JSON-RPC 消息"""
        import sys
        sys.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        sys.stdout.flush()
