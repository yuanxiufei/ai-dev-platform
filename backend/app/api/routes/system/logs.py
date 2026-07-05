"""
Log Service API — 日志通道管理与实时推送

GET    /api/v1/system/logs/channels                     — 列出日志通道
GET    /api/v1/system/logs/{channel}                    — 获取通道日志条目
GET    /api/v1/system/logs/{channel}/stream             — WebSocket 实时流
GET    /api/v1/system/logs/search                       — 全文搜索日志
POST   /api/v1/system/logs/{channel}                    — 写入日志
DELETE /api/v1/system/logs/{channel}                    — 清空通道
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from pydantic import BaseModel
from typing import Optional
import asyncio

from app.core.log_service import LogService, LogLevel, LogEntry, log_service

router = APIRouter(prefix="/system/logs", tags=["Logs"])


class LogWriteRequest(BaseModel):
    message: str
    level: str = "info"
    source: str = ""


@router.get("/channels")
def list_channels():
    """列出所有日志通道"""
    svc = log_service()
    return {"channels": svc.list_channels()}


@router.get("/{channel}")
def get_logs(
    channel: str,
    level: Optional[str] = None,
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """获取通道日志条目"""
    svc = log_service()
    log_level = LogLevel.from_str(level) if level else None
    entries = svc.get_entries(channel, log_level, limit, offset)
    return {"channel": channel, "total": len(entries), "entries": entries}


@router.post("/{channel}")
def write_log(channel: str, req: LogWriteRequest):
    """写入日志到指定通道"""
    svc = log_service()
    level = LogLevel.from_str(req.level)
    entry = svc.log(req.message, level, channel, req.source)
    return entry.to_dict()


@router.delete("/{channel}")
def clear_channel(channel: str):
    """清空日志通道"""
    svc = log_service()
    svc.clear_channel(channel)
    return {"channel": channel, "cleared": True}


@router.get("/search")
def search_logs(
    q: str = Query(..., min_length=1),
    channel: Optional[str] = None,
    level: Optional[str] = None,
    limit: int = Query(default=100, le=500),
):
    """全文搜索日志"""
    svc = log_service()
    log_level = LogLevel.from_str(level) if level else None
    results = svc.search(q, channel, log_level, limit)
    return {"query": q, "total": len(results), "results": results}


@router.websocket("/{channel}/stream")
async def stream_logs(websocket: WebSocket, channel: str):
    """WebSocket 实时日志推送"""
    await websocket.accept()

    svc = log_service()
    subscriber_id = f"ws_{id(websocket)}"
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def on_log(entry: LogEntry):
        asyncio.run_coroutine_threadsafe(queue.put(entry.to_dict()), loop)

    svc.subscribe(channel, subscriber_id, on_log)

    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=30.0)
                await websocket.send_json(data)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        svc.unsubscribe(channel, subscriber_id)
