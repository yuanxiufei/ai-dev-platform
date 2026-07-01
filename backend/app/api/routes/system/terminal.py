"""
终端管理 API 路由 — 借鉴 OpenVSCode RemoteTerminalChannel

端点:
  POST   /api/v1/system/terminal/sessions       — 创建终端会话
  GET    /api/v1/system/terminal/sessions        — 列出活跃终端
  DELETE /api/v1/system/terminal/sessions/{id}   — 关闭终端
  WS     /api/v1/system/terminal/sessions/{id}/ws — WebSocket 终端通道

安全说明：终端端点需要 JWT 认证，WebSocket 通过 query 参数传递 token。
生产环境建议通过 DISABLE_TERMINAL_API 环境变量禁用此功能。
"""
from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from fastapi import status as http_status
from jose import JWTError

from app.api.deps import CurrentUser, get_current_user_ws
from app.core.config import settings
from app.core.terminal import get_pty_backend
from app.core.terminal.channel import TerminalWebSocketChannel
from app.core.ws_limiter import get_ws_limiter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/system/terminal",
    tags=["Terminal"],
)

# 允许通过环境变量禁用终端 API（生产环境强烈建议）
_TERMINAL_DISABLED = os.environ.get("DISABLE_TERMINAL_API", "").lower() in ("1", "true", "yes")


def _ensure_terminal_enabled() -> None:
    if _TERMINAL_DISABLED or not settings.TERMINAL_ENABLED:
        raise HTTPException(status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE, detail="Terminal API is disabled")


@router.post("/sessions")
async def create_terminal_session(
    shell: str = Query("/bin/bash", max_length=256),
    cwd: str | None = Query(None, max_length=1024),
    user: CurrentUser = None,
) -> dict[str, Any]:
    """创建终端会话（返回 session_id）"""
    _ensure_terminal_enabled()
    backend = get_pty_backend()
    if not backend:
        raise HTTPException(status_code=503, detail="PTY backend not initialized")

    import uuid
    session_id = str(uuid.uuid4())[:12]

    # 只注册 session，实际终端进程在 WebSocket 连接时创建
    return {
        "session_id": session_id,
        "shell": shell,
        "cwd": cwd,
        "ws_url": f"/api/v1/system/terminal/sessions/{session_id}/ws",
    }


@router.get("/sessions")
async def list_terminal_sessions(
    user: CurrentUser,
) -> list[dict[str, Any]]:
    """列出所有活跃终端"""
    _ensure_terminal_enabled()
    backend = get_pty_backend()
    if not backend:
        return []
    return backend.list_terminals()


@router.delete("/sessions/{session_id}")
async def close_terminal_session(
    session_id: str,
    force: bool = False,
    user: CurrentUser,
) -> dict[str, str]:
    """关闭终端会话"""
    _ensure_terminal_enabled()
    backend = get_pty_backend()
    if not backend:
        raise HTTPException(status_code=503, detail="PTY backend not initialized")

    # 清理该 session 下的所有终端
    for term in backend.list_terminals():
        if term["terminal_id"].startswith(session_id):
            backend.shutdown(term["terminal_id"], force=force)

    return {"status": "closed", "session_id": session_id}


@router.websocket("/sessions/{session_id}/ws")
async def terminal_websocket(websocket: WebSocket, session_id: str) -> None:
    """WebSocket 终端双向通道 — 通过 query 参数 ?token=... 传递 JWT"""
    # WebSocket 握手阶段验证 token
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    try:
        user = await get_current_user_ws(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    _ensure_terminal_enabled()
    backend = get_pty_backend()
    if not backend:
        await websocket.close(code=1011, reason="PTY backend not initialized")
        return

    # 连接数限制（终端连接更严格：每用户默认 2）
    limiter = get_ws_limiter()
    try:
        guard = await limiter.enforce(websocket, str(user.id))
    except ConnectionRefusedError:
        return
    async with guard:
        channel = TerminalWebSocketChannel(
            websocket=websocket,
            backend=backend,
            session_id=session_id,
        )
        await channel.handle()
