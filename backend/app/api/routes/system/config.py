"""
配置管理 API 路由

端点:
  GET   /api/v1/system/config        — 当前配置（脱敏）
  POST  /api/v1/system/config/reload — 热加载配置
"""
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

from app.core.config import settings
from app.core.config_reloader import get_config_reloader

router = APIRouter(
    prefix="/system/config",
    tags=["Config"],
)

_SENSITIVE_KEYS = {
    "SECRET_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
    "AZURE_OPENAI_API_KEY", "REPLICATE_API_KEY", "ZHIPU_API_KEY", "QWEN_API_KEY",
    "DATABASE_URL", "JWT_SECRET_KEY",
}


def _mask_value(val: str) -> str:
    """脱敏"""
    if len(val) <= 8:
        return "***"
    return val[:4] + "****" + val[-4:]


@router.get("")
async def get_config() -> dict[str, Any]:
    """获取当前配置（敏感值脱敏）"""
    try:
        config_dict = settings.model_dump()
    except AttributeError:
        config_dict = settings.dict()

    result: dict[str, Any] = {}
    for key, val in sorted(config_dict.items()):
        if key.startswith("_"):
            continue
        if key.upper() in _SENSITIVE_KEYS and val:
            result[key] = "*** (masked)"
        else:
            result[key] = val
    return result


@router.post("/reload")
async def reload_config() -> dict[str, Any]:
    """热加载配置"""
    reloader = get_config_reloader()
    if not reloader:
        # 返回近似信息
        return {
            "status": "no_reloader",
            "message": "ConfigReloader not initialized. Use CLI: ai-platform config reload",
        }

    result = reloader.reload_now()
    return {
        "status": "reloaded",
        "reload_count": result["reload_count"],
        "timestamp": result["timestamp"],
    }
