"""
模型健康检查 API

借鉴 Agent-Reach Channel.check() 设计：
- GET  /system/model-health       — 查询所有模型的健康状态
- POST /system/model-health/check — 手动触发一次健康检查
"""

from fastapi import APIRouter, HTTPException

from app.core.agent.model_health import (
    get_model_health,
    HealthStatus,
)

router = APIRouter(prefix="/system", tags=["model-health"])


@router.get("/model-health")
async def get_model_health_status() -> dict:
    """获取所有注册模型的健康状态"""
    checker = get_model_health()
    if not checker:
        raise HTTPException(status_code=503, detail="Model health checker not initialized")

    models = []
    for m in checker.get_all():
        models.append({
            "name": m.name,
            "provider": m.provider,
            "api_model_id": m.api_model_id or m.name,
            "priority": m.priority,
            "health_status": m.health.status.value,
            "health_message": m.health.message,
            "health_latency_ms": round(m.health.latency_ms, 1),
            "failure_count": m.failure_count,
            "success_count": m.success_count,
            "last_checked": round(m.health.timestamp),
        })

    stats = checker.get_stats()
    return {
        "status": "ok",
        "summary": {
            "total": stats["total"],
            "healthy": stats["healthy"],
            "unhealthy": stats["unhealthy"],
            "check_count": stats["check_count"],
        },
        "models": models,
    }


@router.post("/model-health/check")
async def trigger_health_check() -> dict:
    """手动触发一次健康检查"""
    checker = get_model_health()
    if not checker:
        raise HTTPException(status_code=503, detail="Model health checker not initialized")

    results = checker.run_check_now()
    return {
        "status": "done",
        "checked": len(results),
        "results": {
            name: {
                "status": result.status.value,
                "message": result.message,
                "latency_ms": round(result.latency_ms, 1),
            }
            for name, result in results.items()
        },
    }
