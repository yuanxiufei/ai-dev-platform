"""
任务队列路由 — Celery 任务状态查询、Worker 监控

端点:
    GET  /tasks/queue/stats    — Worker + 队列统计
    GET  /tasks/queue/active   — 活跃任务列表
    GET  /tasks/queue/{id}     — 单个任务状态
    POST /tasks/queue/{id}/revoke — 撤销任务
"""

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.task_queue import get_task_status, revoke_task
from app.core.task_queue.monitor import (
    get_active_tasks,
    get_task_stats,
    get_worker_status,
)

router = APIRouter(prefix="/tasks/queue", tags=["task-queue"])


@router.get("/stats")
async def task_queue_stats() -> dict[str, Any]:
    """任务队列统计概览（Worker 数量 + 各队列任务数）"""
    stats = await get_task_stats()
    workers = await get_worker_status()
    return {
        "queue_stats": stats,
        "workers": workers,
    }


@router.get("/active")
async def task_queue_active(limit: int = Query(50, ge=1, le=200)) -> list[dict[str, Any]]:
    """获取当前活跃任务列表"""
    return await get_active_tasks(limit=limit)


@router.get("/{task_id}")
async def task_queue_status(task_id: str) -> dict[str, Any]:
    """查询单个任务状态"""
    status = get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return status


@router.post("/{task_id}/revoke")
async def task_queue_revoke(task_id: str, terminate: bool = Query(False)) -> dict[str, Any]:
    """撤销任务"""
    success = revoke_task(task_id, terminate=terminate)
    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to revoke task {task_id}")
    return {"task_id": task_id, "revoked": True, "terminated": terminate}
