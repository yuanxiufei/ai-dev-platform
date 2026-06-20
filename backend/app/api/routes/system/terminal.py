"""
终端管理 API 路由 — 借鉴 OpenVSCode RemoteTerminalChannel

端点:
  POST   /api/v1/system/terminal/sessions       — 创建终端会话
  GET    /api/v1/system/terminal/sessions        — 列出活跃终端
  DELETE /api/v1/system/terminal/sessions/{id}   — 关闭终端
  WS     /api/v1/system/terminal/sessions/{id}/ws — WebSocket 终端通道
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from app.core.terminal import get_pty_backend
from app.core.terminal.channel import TerminalWebSocketChannel

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/system/terminal",
    tags=["Terminal"],
)


@router.post("/sessions")
async def create_terminal_session(
    shell: str = "/bin/bash",
    cwd: str | None = None,
) -> dict[str, Any]:
    """创建终端会话（返回 session_id）"""
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
async def list_terminal_sessions() -> list[dict[str, Any]]:
    """列出所有活跃终端"""
    backend = get_pty_backend()
    if not backend:
        return []
    return backend.list_terminals()


@router.delete("/sessions/{session_id}")
async def close_terminal_session(session_id: str, force: bool = False) -> dict[str, str]:
    """关闭终端会话"""
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
    """WebSocket 终端双向通道"""
    backend = get_pty_backend()
    if not backend:
        await websocket.close(code=1011, reason="PTY backend not initialized")
        return

    channel = TerminalWebSocketChannel(
        websocket=websocket,
        backend=backend,
        session_id=session_id,
    )
    await channel.handle()
