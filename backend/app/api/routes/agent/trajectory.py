"""
Trajectory 轨迹 API

端点：
- GET  /agent/trajectory/                       — 列出轨迹文件
- GET  /agent/trajectory/list                    — 分页列表 (带筛选/搜索)
- GET  /agent/trajectory/stats                   — 聚合统计
- GET  /agent/trajectory/{agent_id}              — 获取指定 Agent 轨迹
- GET  /agent/trajectory/{agent_id}/replay       — 轨迹回放
- DELETE /agent/trajectory/{agent_id}            — 删除轨迹
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


@router.get("/list")
async def list_trajectories_paginated(
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页数量"),
    status: str | None = Query(None, description="状态筛选: success/error/cancelled"),
    model: str | None = Query(None, description="模型名称模糊搜索"),
    agent_id: str | None = Query(None, description="Agent ID 筛选"),
    search: str | None = Query(None, description="关键词搜索 (匹配 agent_id/session_id)"),
) -> dict[str, Any]:
    """分页列出轨迹记录，带筛选和搜索"""
    from app.core.config import settings

    output_dir = settings.TRAJECTORY_OUTPUT_DIR
    if not os.path.exists(output_dir):
        return {"status": "ok", "data": [], "total": 0, "page": page, "size": size}

    # 收集所有 JSON 轨迹文件的元信息
    items: list[dict[str, Any]] = []
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json") or fname.endswith(".jsonl"):
            continue
        filepath = os.path.join(output_dir, fname)
        try:
            data = await asyncio.to_thread(_read_json_sync, filepath)
        except (json.JSONDecodeError, OSError):
            continue

        # 解析基本元信息
        summary = data.get("summary", {})
        item = {
            "agent_id": data.get("agent_id", ""),
            "session_id": data.get("session_id", ""),
            "started_at": data.get("started_at", ""),
            "completed_at": summary.get("completed_at", ""),
            "total_steps": summary.get("total_steps", 0),
            "total_tool_calls": summary.get("total_tool_calls", 0),
            "total_tokens": summary.get("total_tokens", 0),
            "total_latency_ms": summary.get("total_latency_ms", 0),
            "final_model": summary.get("final_model", ""),
            "final_provider": summary.get("final_provider", ""),
            "has_error": bool(summary.get("error", "")),
            "cancelled": bool(summary.get("cancelled", False)),
            "filename": fname,
            "file_size_bytes": os.path.getsize(filepath),
        }
        items.append(item)

    # 筛选
    if status:
        if status == "success":
            items = [i for i in items if not i["has_error"] and not i["cancelled"]]
        elif status == "error":
            items = [i for i in items if i["has_error"]]
        elif status == "cancelled":
            items = [i for i in items if i["cancelled"]]

    if model:
        model_lower = model.lower()
        items = [i for i in items if model_lower in i["final_model"].lower()]

    if agent_id:
        items = [i for i in items if i["agent_id"] == agent_id]

    if search:
        search_lower = search.lower()
        items = [
            i for i in items
            if search_lower in i["agent_id"].lower()
            or search_lower in i["session_id"].lower()
            or search_lower in i["final_model"].lower()
        ]

    # 排序 (按时间倒序)
    items.sort(key=lambda x: x["started_at"], reverse=True)

    total = len(items)

    # 分页
    start = (page - 1) * size
    end = start + size
    page_items = items[start:end]

    return {
        "status": "ok",
        "data": page_items,
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/stats")
async def trajectory_stats() -> dict[str, Any]:
    """轨迹聚合统计"""
    from app.core.config import settings

    output_dir = settings.TRAJECTORY_OUTPUT_DIR
    if not os.path.exists(output_dir):
        return {"status": "ok", "stats": {"total_runs": 0}}

    runs = []
    for fname in os.listdir(output_dir):
        if not fname.endswith(".json") or fname.endswith(".jsonl"):
            continue
        filepath = os.path.join(output_dir, fname)
        try:
            data = await asyncio.to_thread(_read_json_sync, filepath)
        except (json.JSONDecodeError, OSError):
            continue

        summary = data.get("summary", {})
        runs.append({
            "has_error": bool(summary.get("error", "")),
            "cancelled": bool(summary.get("cancelled", False)),
            "total_steps": summary.get("total_steps", 0),
            "total_tool_calls": summary.get("total_tool_calls", 0),
            "total_tokens": summary.get("total_tokens", 0),
            "total_latency_ms": summary.get("total_latency_ms", 0),
            "model": summary.get("final_model", ""),
            "provider": summary.get("final_provider", ""),
        })

    total_runs = len(runs)
    success_runs = sum(1 for r in runs if not r["has_error"] and not r["cancelled"])
    error_runs = sum(1 for r in runs if r["has_error"])
    cancelled_runs = sum(1 for r in runs if r["cancelled"])

    total_steps = sum(r["total_steps"] for r in runs)
    total_tool_calls = sum(r["total_tool_calls"] for r in runs)
    total_tokens = sum(r["total_tokens"] for r in runs)
    total_latency_ms = sum(r["total_latency_ms"] for r in runs)

    # 模型使用统计
    model_counts: dict[str, int] = {}
    for r in runs:
        model = r["model"] or "unknown"
        model_counts[model] = model_counts.get(model, 0) + 1

    top_models = sorted(model_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "status": "ok",
        "stats": {
            "total_runs": total_runs,
            "success_runs": success_runs,
            "error_runs": error_runs,
            "cancelled_runs": cancelled_runs,
            "success_rate": round(success_runs / total_runs * 100, 1) if total_runs > 0 else 0,
            "total_steps": total_steps,
            "total_tool_calls": total_tool_calls,
            "total_tokens": total_tokens,
            "total_latency_ms": total_latency_ms,
            "avg_steps_per_run": round(total_steps / total_runs, 1) if total_runs > 0 else 0,
            "avg_tool_calls_per_run": round(total_tool_calls / total_runs, 1) if total_runs > 0 else 0,
            "avg_tokens_per_run": round(total_tokens / total_runs) if total_runs > 0 else 0,
            "top_models": [{"model": m, "count": c} for m, c in top_models],
        },
    }


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
