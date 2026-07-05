"""
Local History + Indent Detection API

GET    /api/v1/system/local-history/{file_path:path}          — 文件快照列表
GET    /api/v1/system/local-history/snapshot/{snapshot_id}   — 获取单个快照
POST   /api/v1/system/local-history/{file_path:path}          — 保存文件快照
DELETE /api/v1/system/local-history/{file_path:path}          — 删除文件所有快照
DELETE /api/v1/system/local-history/snapshot/{snapshot_id}   — 删除单个快照
GET    /api/v1/system/local-history/stats                    — 存储统计
POST   /api/v1/system/local-history/prune                    — 清理旧快照
POST   /api/v1/system/indent/detect                          — 检测缩进风格
"""

from fastapi import APIRouter, Query, Body
from pydantic import BaseModel
from typing import Optional

from app.core.local_history import (
    get_local_history, detect_indentation, IndentInfo
)

router = APIRouter(prefix="/system", tags=["Local History"])


class SnapshotRequest(BaseModel):
    content: str
    label: str = ""


class IndentDetectRequest(BaseModel):
    content: str
    sample_lines: int = 500


class PruneRequest(BaseModel):
    days: int = 30


# ---- Local History ----

@router.get("/local-history/{file_path:path}")
def list_snapshots(file_path: str, limit: int = Query(default=50, le=200)):
    """列出文件所有快照"""
    store = get_local_history()
    snapshots = store.get_snapshots(file_path, limit)
    return {"filePath": file_path, "total": len(snapshots), "snapshots": snapshots}


@router.get("/local-history/snapshot/{snapshot_id}")
def get_snapshot(snapshot_id: str):
    """获取单个快照 (含内容)"""
    store = get_local_history()
    snapshot = store.get_snapshot(snapshot_id)
    if not snapshot:
        return {"error": "Snapshot not found", "id": snapshot_id}
    return snapshot


@router.post("/local-history/{file_path:path}")
def save_snapshot(file_path: str, req: SnapshotRequest):
    """保存文件快照"""
    store = get_local_history()
    snapshot = store.save_snapshot(file_path, req.content, req.label)
    return snapshot.to_dict(include_content=False)


@router.delete("/local-history/{file_path:path}")
def delete_file_snapshots(file_path: str):
    """删除文件的所有历史快照"""
    store = get_local_history()
    count = store.delete_file_snapshots(file_path)
    return {"filePath": file_path, "deletedCount": count}


@router.delete("/local-history/snapshot/{snapshot_id}")
def delete_snapshot(snapshot_id: str):
    """删除单个快照"""
    store = get_local_history()
    ok = store.delete_snapshot(snapshot_id)
    return {"id": snapshot_id, "deleted": ok}


@router.get("/local-history/stats")
def get_history_stats():
    """获取存储统计"""
    store = get_local_history()
    return store.get_stats()


@router.post("/local-history/prune")
def prune_old(req: PruneRequest):
    """清理超过 N 天的旧快照"""
    store = get_local_history()
    count = store.prune_old(req.days)
    return {"prunedCount": count, "days": req.days}


# ---- Indent Detection ----

@router.post("/indent/detect")
def detect_indent(req: IndentDetectRequest):
    """检测文本的缩进风格"""
    info = detect_indentation(req.content, req.sample_lines)
    return info.to_dict()
