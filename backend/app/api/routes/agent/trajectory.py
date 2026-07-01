"""
Trajectory 轨迹 API

端点：
- GET /agent/trajectory/{agent_id}  — 列出轨迹文件
- GET /agent/trajectory/{agent_id}/{session_id} — 获取指定轨迹
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/agent/trajectory", tags=["Trajectory"])


def _read_json_sync(filepath: str) -> dict[str, Any]:
    """同步读取 JSON 文件（用于 asyncio.to_thread 包装）"""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


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
                data = await asyncio.to_thread(
                    _read_json_sync, filepath
                )
                data["_filename"] = fname
                matches.append(data)
            except (json.JSONDecodeError, Exception):
                continue

    matches.sort(key=lambda x: x.get("started_at", ""), reverse=True)
    return {"status": "ok", "trajectories": matches[:limit], "total": len(matches)}


@router.get("/{agent_id}/replay")
async def replay_trajectory(
    agent_id: str,
    session_id: str | None = Query(None, description="指定 session"),
) -> dict[str, Any]:
    """P2.10: 获取轨迹回放数据 — 步骤时间线 + 详情"""
    from app.core.config import settings

    output_dir = settings.TRAJECTORY_OUTPUT_DIR
    if not os.path.exists(output_dir):
        raise HTTPException(status_code=404, detail="No trajectories found")

    # 查找匹配的轨迹文件
    matches = []
    for fname in os.listdir(output_dir):
        if fname.startswith(agent_id) and fname.endswith((".json", ".jsonl")):
            if session_id and session_id not in fname:
                continue
            filepath = os.path.join(output_dir, fname)
            matches.append(filepath)

    if not matches:
        raise HTTPException(status_code=404, detail=f"No trajectory for agent '{agent_id}'")

    # 取最新的
    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    filepath = matches[0]

    raw = await asyncio.to_thread(_read_json_sync, filepath)

    # 构建回放步骤时间线
    steps = []
    # 支持多种轨迹格式
    raw_steps = raw.get("steps") or raw.get("trajectory") or raw.get("events") or []
    if isinstance(raw_steps, list):
        for i, step in enumerate(raw_steps):
            if isinstance(step, dict):
                steps.append({
                    "step": i + 1,
                    "type": step.get("type", "unknown"),
                    "action": step.get("action") or step.get("tool_call") or step.get("name", ""),
                    "input": step.get("input") or step.get("arguments", ""),
                    "output": step.get("output") or step.get("result", "") if isinstance(step.get("output"), str) else str(step.get("output", "") or step.get("result", ""))[:500],
                    "elapsed_ms": step.get("elapsed_ms") or step.get("latency_ms", 0),
                    "error": step.get("error", ""),
                    "timestamp": step.get("timestamp") or step.get("time", ""),
                })
    elif isinstance(raw_steps, dict):
        # 结构化为 timeline
        for key, val in raw_steps.items():
            steps.append({"step": key, "action": key, "output": str(val)[:500]})

    # 摘要
    summary = {
        "agent_id": agent_id,
        "session_id": raw.get("session_id") or raw.get("request_id", ""),
        "total_steps": len(steps),
        "total_time_ms": raw.get("total_time_ms") or raw.get("elapsed_ms", 0),
        "success": raw.get("success", True),
        "error": raw.get("error", ""),
        "started_at": raw.get("started_at") or raw.get("start_time", ""),
        "final_answer": raw.get("final_answer") or raw.get("result", "") if isinstance(raw.get("final_answer"), str) else str(raw.get("final_answer", "") or raw.get("result", ""))[:1000],
    }

    return {
        "status": "ok",
        "summary": summary,
        "steps": steps,
        "_filename": os.path.basename(filepath),
    }


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
