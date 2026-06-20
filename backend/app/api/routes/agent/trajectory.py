"""
Trajectory 轨迹 API

端点：
- GET /agent/trajectory/{agent_id}  — 列出轨迹文件
- GET /agent/trajectory/{agent_id}/{session_id} — 获取指定轨迹
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/agent/trajectory", tags=["Trajectory"])


@router.get("/")
async def list_trajectories(
    agent_id: str | None = Query(None, description="筛选 Agent ID"),
) -> dict[str, Any]:
    """列出所有轨迹文件"""
    from app.core.config import settings

    output_dir = settings.TRAJECTORY_OUTPUT_DIR
    if not os.path.exists(output_dir):
        return {"status": "ok", "trajectories": []}

    files = []
    for fname in os.listdir(output_dir):
        if fname.endswith((".json", ".jsonl")):
            filepath = os.path.join(output_dir, fname)
            stat = os.stat(filepath)
            if agent_id and not fname.startswith(agent_id):
                continue
            files.append({
                "filename": fname,
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            })

    return {"status": "ok", "trajectories": sorted(files, key=lambda x: x["modified_at"], reverse=True)}


@router.get("/{agent_id}")
async def get_trajectory(
    agent_id: str,
    session_id: str | None = Query(None, description="筛选 session"),
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """获取指定 Agent 的最近轨迹"""
    from app.core.config import settings

    output_dir = settings.TRAJECTORY_OUTPUT_DIR
    if not os.path.exists(output_dir):
        return {"status": "ok", "trajectories": []}

    matches = []
    for fname in os.listdir(output_dir):
        if fname.startswith(agent_id) and (not session_id or session_id in fname):
            filepath = os.path.join(output_dir, fname)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["_filename"] = fname
                    matches.append(data)
            except (json.JSONDecodeError, Exception):
                continue

    matches.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return {"status": "ok", "trajectories": matches[:limit], "total": len(matches)}


@router.delete("/{agent_id}")
async def delete_trajectories(
    agent_id: str,
    session_id: str | None = Query(None, description="删除指定 session 的轨迹"),
) -> dict[str, Any]:
    """删除 Agent 的轨迹文件"""
    from app.core.config import settings

    output_dir = settings.TRAJECTORY_OUTPUT_DIR
    if not os.path.exists(output_dir):
        return {"status": "ok", "deleted": 0}

    deleted = 0
    for fname in os.listdir(output_dir):
        if fname.startswith(agent_id) and (not session_id or session_id in fname):
            try:
                os.remove(os.path.join(output_dir, fname))
                deleted += 1
            except OSError:
                pass

    return {"status": "ok", "deleted": deleted}
