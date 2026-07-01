"""
Benchmark API 路由 — 借鉴 GPUStack routes/benchmarks.py

端点:
  POST   /api/v1/system/benchmarks              — 创建 Benchmark 任务
  GET    /api/v1/system/benchmarks              — 列出任务
  GET    /api/v1/system/benchmarks/{id}         — 任务详情
  POST   /api/v1/system/benchmarks/{id}/submit  — 提交执行
  POST   /api/v1/system/benchmarks/{id}/stop    — 停止
  GET    /api/v1/system/benchmarks/{id}/export  — 导出 YAML
  WS     /api/v1/system/benchmarks/{id}/ws      — 实时日志流
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query

from app.api.deps import CurrentUser, get_current_user_ws
from app.core.benchmark import (
    BenchmarkEngine,
    BenchmarkState,
    get_benchmark_engine,
)
from app.core.ws_limiter import get_ws_limiter

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/system/benchmarks",
    tags=["Benchmark"],
)


def _require_engine() -> BenchmarkEngine:
    """确保引擎已初始化"""
    engine = get_benchmark_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Benchmark engine not initialized")
    return engine


@router.post("")
async def create_benchmark(
    model_name: str = Query(..., description="模型名称"),
    capability: str = Query("code_generation", description="能力类型"),
    dataset: str = Query("random", description="数据集: random | sharegpt"),
    num_requests: int = Query(100, ge=1, le=10000, description="请求数"),
    concurrency: int = Query(1, ge=1, le=16, description="并发数"),
    max_tokens: int = Query(512, ge=1, le=4096, description="最大输出 token 数"),
    user: CurrentUser = None,  # JWT 认证
) -> dict[str, Any]:
    """创建 Benchmark 任务"""
    engine = _require_engine()
    task = engine.create(
        model_name=model_name,
        capability=capability,
        dataset=dataset,
        num_requests=num_requests,
        concurrency=concurrency,
        max_tokens=max_tokens,
    )
    return task.to_dict()


@router.get("")
async def list_benchmarks(
    state: str | None = Query(None, description="按状态筛选"),
    user: CurrentUser = None,
) -> list[dict[str, Any]]:
    """列出 Benchmark 任务"""
    engine = _require_engine()
    state_enum = BenchmarkState(state) if state else None
    tasks = engine.list_tasks(state=state_enum)
    return [t.to_dict() for t in tasks]


@router.get("/{task_id}")
async def get_benchmark(
    task_id: str,
    user: CurrentUser = None,
) -> dict[str, Any]:
    """获取 Benchmark 任务详情"""
    engine = _require_engine()
    task = engine.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Benchmark not found")
    return task.to_dict()


@router.post("/{task_id}/submit")
async def submit_benchmark(
    task_id: str,
    user: CurrentUser = None,
) -> dict[str, str]:
    """提交 Benchmark 执行"""
    engine = _require_engine()
    await engine.submit(task_id)
    return {"status": "submitted", "task_id": task_id}


@router.post("/{task_id}/stop")
async def stop_benchmark(
    task_id: str,
    user: CurrentUser = None,
) -> dict[str, str]:
    """停止 Benchmark"""
    engine = _require_engine()
    success = await engine.stop(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Benchmark not found or cannot be stopped")
    return {"status": "stopped", "task_id": task_id}


@router.get("/{task_id}/export")
async def export_benchmark(
    task_id: str,
    user: CurrentUser = None,
) -> dict[str, str]:
    """导出 Benchmark 结果为 YAML"""
    engine = _require_engine()
    yaml_str = engine.export_yaml(task_id)
    if yaml_str is None:
        raise HTTPException(
            status_code=400,
            detail="Benchmark not found or not completed",
        )
    return {"yaml": yaml_str, "task_id": task_id}


@router.websocket("/{task_id}/ws")
async def benchmark_websocket(websocket: WebSocket, task_id: str) -> None:
    """WebSocket 实时日志流 — 通过 ?token=... 传递 JWT"""
    # WebSocket 握手阶段验证 token
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing authentication token")
        return
    try:
        user = await get_current_user_ws(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    # 连接数限制
    limiter = get_ws_limiter()
    try:
        guard = await limiter.enforce(websocket, str(user.id))
    except ConnectionRefusedError:
        return
    async with guard:
        await websocket.accept()

        engine = get_benchmark_engine()
        if not engine:
            await websocket.send_json({"error": "Engine not initialized"})
            await websocket.close()
            return

        task = engine.get_task(task_id)
        if not task:
            await websocket.send_json({"error": "Benchmark not found"})
            await websocket.close()
            return

        log_idx = 0
        try:
            while task.state in (BenchmarkState.QUEUED, BenchmarkState.RUNNING, BenchmarkState.PENDING):
                # 推送新日志
                while log_idx < len(task.logs):
                    await websocket.send_json({
                        "type": "log",
                        "message": task.logs[log_idx],
                        "progress": len(task.logs) / max(task.num_requests, 1) * 100,
                    })
                    log_idx += 1

                # 推送状态
                await websocket.send_json({
                    "type": "status",
                    "state": task.state.value,
                    "metrics": {
                        "tokens_per_second": task.metrics.tokens_per_second,
                        "latency_avg_ms": task.metrics.latency_avg_ms,
                    },
                })

                if task.state in (BenchmarkState.COMPLETED, BenchmarkState.FAILED, BenchmarkState.STOPPED):
                    break

                await asyncio.sleep(0.5)

            # 最终推送
            await websocket.send_json({
                "type": "done",
                "state": task.state.value,
                "task": task.to_dict(),
            })

        except WebSocketDisconnect:
            pass
    except Exception as e:
        logger.error("Benchmark WebSocket error: %s", e)
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
