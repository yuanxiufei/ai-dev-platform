"""
任务监控 — 查询任务状态/进度/结果

提供:
- 按状态过滤任务
- 任务统计概览
- 单个任务详情
"""

import logging
from typing import Any

from celery.result import AsyncResult

from app.core.task_queue import celery_app

logger = logging.getLogger("task_queue.monitor")


async def get_active_tasks(limit: int = 50) -> list[dict[str, Any]]:
    """获取活跃任务列表"""
    inspect = celery_app.control.inspect()
    if not inspect:
        return []

    tasks: list[dict[str, Any]] = []

    try:
        active = inspect.active() or {}
        for worker, worker_tasks in active.items():
            for task in worker_tasks[:limit]:
                tasks.append({
                    "task_id": task.get("id", ""),
                    "name": task.get("name", ""),
                    "worker": worker,
                    "args": task.get("args", ""),
                    "started_at": task.get("time_start", ""),
                })
    except Exception as e:
        logger.warning("Failed to inspect active tasks: %s", e)

    return tasks


async def get_task_stats() -> dict[str, Any]:
    """获取任务队列统计概览"""
    inspect = celery_app.control.inspect()
    if not inspect:
        return {"workers": 0, "active": 0, "reserved": 0, "scheduled": 0}

    try:
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        scheduled = inspect.scheduled() or {}

        return {
            "workers": len(active.keys() | reserved.keys() | scheduled.keys()),
            "active": sum(len(v) for v in active.values()),
            "reserved": sum(len(v) for v in reserved.values()),
            "scheduled": sum(len(v) for v in scheduled.values()),
        }
    except Exception as e:
        logger.warning("Failed to get task stats: %s", e)
        return {"error": str(e)}


async def get_worker_status() -> list[dict[str, Any]]:
    """获取 Worker 状态"""
    inspect = celery_app.control.inspect()
    if not inspect:
        return []

    workers: list[dict[str, Any]] = []

    try:
        stats = inspect.stats() or {}
        for worker_name, worker_stats in stats.items():
            workers.append({
                "worker": worker_name,
                "pool_size": worker_stats.get("pool", {}).get("max-concurrency", 0),
                "total_tasks": worker_stats.get("total", {}),
                "pid": worker_stats.get("pid", 0),
            })
    except Exception as e:
        logger.warning("Failed to get worker status: %s", e)

    return workers
