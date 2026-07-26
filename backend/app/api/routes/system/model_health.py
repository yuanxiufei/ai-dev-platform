"""
模型健康检查 API

借鉴 Agent-Reach Channel.check() 设计：
- GET  /system/model-health       — 查询所有模型的健康状态
- POST /system/model-health/check — 手动触发一次健康检查
- POST /system/model-health/refresh-provider — 动态刷新 Provider 模型列表（Ollama / vLLM / llama.cpp）
"""

import logging

from fastapi import APIRouter, HTTPException

from app.core.agent.model_health import (
    get_model_health,
    HealthStatus,
)
from app.core.providers import get_provider_registry

logger = logging.getLogger("api.model-health")

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


@router.post("/model-health/refresh-provider")
async def refresh_provider_models(provider_name: str = "ollama") -> dict:
    """动态刷新 Provider 模型列表（无需重启后端）

    支持: ollama (POST /api/tags), vllm / llama_cpp (GET /v1/models)
    例如: POST /system/model-health/refresh-provider?provider_name=ollama
    """
    registry = get_provider_registry()
    providers = registry.list_all()

    # 查找目标 provider
    matched = [p for p in providers if p["name"] == provider_name]
    if not matched:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_name}' not found. "
            f"Available: {[p['name'] for p in providers]}",
        )

    provider = registry.get(provider_name)
    if provider is None:
        raise HTTPException(status_code=503, detail=f"Provider '{provider_name}' not instantiated")

    # 调用异步 sync_models() 拉取最新模型列表
    if not hasattr(provider, "sync_models"):
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{provider_name}' does not support dynamic model refresh",
        )

    try:
        new_models = await provider.sync_models()
    except Exception as e:
        logger.exception("refresh_provider_models(%s) failed: %s", provider_name, e)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to pull model list from {provider_name}: {e}",
        )

    logger.info("refresh_provider_models(%s) -> %d models: %s", provider_name, len(new_models), new_models)

    return {
        "status": "ok",
        "provider": provider_name,
        "models": new_models,
        "count": len(new_models),
    }
