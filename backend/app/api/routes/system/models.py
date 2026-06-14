"""
系统 — 全局模型管理 API

统一的模型管理接口（Studio + Video 共用）：
  - 列出所有模型（本地 + 远程 API）
  - 模型下载/状态
  - 模型加载/卸载
  - API 提供商配置
  - 模型使用统计
  - 自动优化触发
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep
from app.models.system_models import (
    ModelDownload,
    DownloadStatus,
    ModelUsageStat,
    ApiCredential,
)

router = APIRouter(prefix="/system/models", tags=["system-models"])


# ── Schemas ──────────────────────────────────────────────

class DownloadRequest(BaseModel):
    model_name: str = Field(max_length=100)
    source: str = Field(default="huggingface", max_length=50)


class CredentialRequest(BaseModel):
    provider: str = Field(max_length=50)
    api_key: str = Field(max_length=500)
    endpoint: str | None = None


class LoadModelRequest(BaseModel):
    model_name: str


# ── 模型列表 ─────────────────────────────────────────────

@router.get("")
def list_all_models(
    session: SessionDep,
    user: CurrentUser,
    capability: str | None = None,
):
    """
    列出所有可用模型

    包括：
    - 本地模型（已下载 + 可下载）
    - 远程 API 模型（已配置密钥）
    """
    from ai_models import get_all_models, ModelType
    from ai_models.registry import get_all_local_configs, get_all_remote_configs
    from app.core.model_downloader import get_downloader

    # 获取本地模型配置
    local_configs = get_all_local_configs()
    remote_configs = get_all_remote_configs()

    # 检测下载状态
    downloader = get_downloader()

    models = []

    # 本地模型
    for name, config in local_configs.items():
        local_path = downloader.models_dir / name
        is_downloaded = local_path.exists() and any(local_path.rglob("*"))

        models.append({
            "name": name,
            "display_name": config.display_name,
            "capability": config.model_type.value,
            "format": config.model_format.value,
            "priority": config.priority,
            "is_local": True,
            "is_downloaded": is_downloaded,
            "max_tokens": config.max_tokens,
        })

    # 远程模型
    for name, config in remote_configs.items():
        models.append({
            "name": name,
            "display_name": config.display_name,
            "capability": config.model_type.value,
            "provider": config.provider,
            "priority": config.priority,
            "is_local": False,
            "is_remote": True,
            "requires_api_key": config.requires_api_key,
            "max_tokens": config.max_tokens,
        })

    # 按优先级排序
    models.sort(key=lambda m: m["priority"], reverse=True)

    # 按能力筛选
    if capability:
        models = [m for m in models if m["capability"] == capability]

    return {
        "models": models,
        "total": len(models),
    }


@router.get("/{model_name}")
def get_model_detail(
    model_name: str,
    session: SessionDep,
    user: CurrentUser,
):
    """获取模型详细信息"""
    from ai_models.registry import get_config, get_remote_config
    from app.core.model_downloader import get_downloader

    # 查找本地模型
    local_config = get_config(model_name)
    if local_config:
        downloader = get_downloader()
        local_path = downloader.models_dir / model_name

        return {
            "name": model_name,
            "display_name": local_config.display_name,
            "capability": local_config.model_type.value,
            "format": local_config.model_format.value,
            "priority": local_config.priority,
            "is_local": True,
            "is_downloaded": local_path.exists(),
            "model_path": local_config.model_path,
            "model_file": local_config.model_file,
            "device": local_config.device,
            "max_tokens": local_config.max_tokens,
            "temperature": local_config.temperature,
        }

    # 查找远程模型
    remote_config = get_remote_config(model_name)
    if remote_config:
        return {
            "name": model_name,
            "display_name": remote_config.display_name,
            "capability": remote_config.model_type.value,
            "provider": remote_config.provider,
            "priority": remote_config.priority,
            "is_local": False,
            "is_remote": True,
            "api_model_id": remote_config.api_model_id,
            "requires_api_key": remote_config.requires_api_key,
            "max_tokens": remote_config.max_tokens,
        }

    raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")


# ── 模型下载 ─────────────────────────────────────────────

@router.post("/download", status_code=202)
async def start_download(
    dl_in: DownloadRequest,
    session: SessionDep,
    user: CurrentUser,
):
    """触发模型下载"""
    record = ModelDownload(
        model_name=dl_in.model_name,
        source=dl_in.model_name,
        source_type=dl_in.source,
        started_by=user.id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)

    # 异步执行
    import asyncio
    from app.core.model_downloader import get_downloader

    downloader = get_downloader()
    asyncio.create_task(
        _run_download(downloader, dl_in, record.id, session)
    )

    return {
        "task_id": str(record.id),
        "model_name": dl_in.model_name,
        "status": "pending",
    }


async def _run_download(downloader, dl_in, record_id, db_session):
    """后台下载"""
    try:
        task_id = await downloader.start_download(
            dl_in.model_name, dl_in.source
        )

        import asyncio
        while True:
            progress = downloader.get_progress(task_id)
            if not progress:
                break

            record = db_session.get(ModelDownload, record_id)
            if record:
                record.progress = int(progress.progress_pct)
                record.downloaded = progress.downloaded_bytes
                record.file_size = progress.total_bytes
                db_session.add(record)
                db_session.commit()

            if progress.state.value in ("completed", "failed", "cancelled"):
                record = db_session.get(ModelDownload, record_id)
                if record:
                    if progress.state.value == "completed":
                        record.status = DownloadStatus.COMPLETED
                        record.progress = 100
                    elif progress.state.value == "cancelled":
                        record.status = DownloadStatus.FAILED
                        record.error_message = "Cancelled"
                    else:
                        record.status = DownloadStatus.FAILED
                        record.error_message = progress.error_message
                    db_session.add(record)
                    db_session.commit()
                break

            await asyncio.sleep(2)

    except Exception as e:
        record = db_session.get(ModelDownload, record_id)
        if record:
            record.status = DownloadStatus.FAILED
            record.error_message = str(e)
            db_session.add(record)
            db_session.commit()


@router.get("/download/{task_id}")
def get_download_status(
    task_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """查询下载进度"""
    record = session.get(ModelDownload, task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Download task not found")

    return {
        "task_id": str(record.id),
        "model_name": record.model_name,
        "status": record.status.value,
        "progress": record.progress,
        "downloaded_bytes": record.downloaded,
        "total_bytes": record.file_size,
        "speed_mbps": (
            round(record.downloaded / 1024 / 1024, 2) if record.downloaded > 0 else 0
        ),
        "error_message": record.error_message,
        "created_at": record.created_at.isoformat(),
    }


@router.delete("/{model_name}", status_code=204)
def delete_model(
    model_name: str,
    user: CurrentUser,
):
    """删除本地模型"""
    from app.core.model_downloader import get_downloader

    downloader = get_downloader()
    success = downloader.delete_model(model_name)

    if not success:
        raise HTTPException(status_code=404, detail="Model not found or already deleted")


# ── 模型加载/卸载 ────────────────────────────────────────

@router.post("/{model_name}/load")
def load_model(
    model_name: str,
    user: CurrentUser,
):
    """加载模型到内存"""
    from ai_models.registry import get_config
    from ai_models.coder_model import CodeGenerationModel

    config = get_config(model_name)
    if not config:
        raise HTTPException(status_code=404, detail=f"Model {model_name} not registered")

    # TODO: 实际加载模型
    return {
        "model_name": model_name,
        "status": "loaded",
        "message": f"Model {model_name} is ready",
    }


@router.post("/{model_name}/unload")
def unload_model(
    model_name: str,
    user: CurrentUser,
):
    """卸载模型"""
    return {
        "model_name": model_name,
        "status": "unloaded",
        "message": f"Model {model_name} unloaded",
    }


# ── API 提供商 ──────────────────────────────────────────

@router.get("/providers")
def list_providers(user: CurrentUser):
    """列出支持的 API 提供商"""
    from app.core.api_gateway import get_api_gateway

    gateway = get_api_gateway()
    return {"providers": gateway.list_providers()}


@router.post("/providers", status_code=201)
def configure_provider(
    cred: CredentialRequest,
    session: SessionDep,
    user: CurrentUser,
):
    """配置 API 提供商密钥"""
    credential = ApiCredential(
        provider=cred.provider,
        api_key_encrypted=cred.api_key,  # TODO: AES 加密
        endpoint=cred.endpoint,
        owner_id=user.id,
    )
    session.add(credential)
    session.commit()
    session.refresh(credential)

    # 更新网关
    from app.core.api_gateway import get_api_gateway
    gateway = get_api_gateway()
    gateway.update_credential(cred.provider, cred.api_key)

    return {
        "provider": cred.provider,
        "status": "configured",
        "message": f"{cred.provider} API key saved",
    }


# ── 使用统计 ─────────────────────────────────────────────

@router.get("/usage-stats")
def get_usage_stats(
    session: SessionDep,
    user: CurrentUser,
    model_name: str | None = None,
    days: int = 7,
):
    """获取模型使用统计"""
    stmt = select(ModelUsageStat)

    if model_name:
        stmt = stmt.where(ModelUsageStat.model_name == model_name)

    stats = session.exec(
        stmt.order_by(ModelUsageStat.created_at.desc()).limit(days * 200)
    ).all()

    # 汇总
    aggregated: dict[str, dict] = {}
    for stat in stats:
        if stat.model_name not in aggregated:
            aggregated[stat.model_name] = {
                "total": 0, "success": 0, "failed": 0,
                "latency_total": 0, "tokens_total": 0,
            }
        a = aggregated[stat.model_name]
        a["total"] += 1
        a["success"] += 1 if stat.success else 0
        a["failed"] += 0 if stat.success else 1
        a["latency_total"] += stat.latency_ms
        a["tokens_total"] += stat.token_count or 0

    return {
        "stats": {
            name: {
                **data,
                "success_rate": (
                    data["success"] / data["total"] if data["total"] > 0 else 0
                ),
                "avg_latency_ms": (
                    data["latency_total"] / data["total"] if data["total"] > 0 else 0
                ),
            }
            for name, data in aggregated.items()
        },
        "period_days": days,
    }


@router.post("/optimize")
def trigger_optimize(days: int = 7):
    """触发自动优化"""
    from ai_models.optimizer import get_optimizer
    optimizer = get_optimizer()
    result = optimizer.auto_tune(days=days)
    return result
