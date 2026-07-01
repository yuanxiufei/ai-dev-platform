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

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import CurrentUser, SessionDep, commit_or_rollback
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
        # Ollama 等本地服务虽然走 API，但实际运行在本机
        is_actually_local = config.extra.get("is_local_api", False) if config.extra else False
        models.append({
            "name": name,
            "display_name": config.display_name,
            "capability": config.model_type.value,
            "provider": config.provider,
            "priority": config.priority,
            "is_local": is_actually_local,
            "is_remote": not is_actually_local,
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
        is_actually_local = (
            remote_config.extra.get("is_local_api", False)
            if remote_config.extra else False
        )
        return {
            "name": model_name,
            "display_name": remote_config.display_name,
            "capability": remote_config.model_type.value,
            "provider": remote_config.provider,
            "priority": remote_config.priority,
            "is_local": is_actually_local,
            "is_remote": not is_actually_local,
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
    # 根据 source 获取实际的下载源标识
    from app.core.model_downloader import get_downloader
    downloader = get_downloader()
    config = downloader.get_model_config(dl_in.model_name)
    source_id = ""
    if config:
        if dl_in.source == "modelscope":
            source_id = config.get("ms_id", "")
        else:
            source_id = config.get("hf_id", "")
    if not source_id:
        source_id = dl_in.model_name

    record = ModelDownload(
        model_name=dl_in.model_name,
        source=source_id,
        source_type=dl_in.source,
        started_by=user.id,
    )
    commit_or_rollback(session, record)

    # 异步执行（创建独立 db session 避免异步上下文冲突）
    import asyncio
    from app.core.db import engine
    from sqlmodel import Session as DBSession

    asyncio.create_task(
        _run_download(downloader, dl_in, record.id, DBSession(engine))
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
                try:
                    db_session.commit()
                except Exception:
                    db_session.rollback()

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
                    try:
                        db_session.commit()
                    except Exception:
                        db_session.rollback()
                break

            await asyncio.sleep(2)

    except Exception as e:
        db_session.rollback()
        record = db_session.get(ModelDownload, record_id)
        if record:
            record.status = DownloadStatus.FAILED
            record.error_message = str(e)
            db_session.add(record)
            try:
                db_session.commit()
            except Exception:
                db_session.rollback()


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
        "status": record.status if record.status else str(record.status),
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

# 全局已加载模型缓存：{model_name: BaseModel instance}
_loaded_models: dict[str, Any] = {}
_loaded_models_lock = asyncio.Lock()


def _get_model_class(model_type: str):
    """根据 ModelType 获取对应的模型包装类。

    Args:
        model_type: ModelType 枚举值字符串

    Returns:
        对应的模型类（CodeGenerationModel / VisionLanguageModel / VideoGenerationModel）
    """
    from ai_models.base import ModelType as MT

    if model_type in (MT.CODE_GENERATION.value, "code_generation"):
        from ai_models.coder_model import CodeGenerationModel
        return CodeGenerationModel
    elif model_type in (MT.VISION_LANGUAGE.value, "vision_language"):
        from ai_models.vl_model import VisionLanguageModel
        return VisionLanguageModel
    elif model_type in (MT.VIDEO_GENERATION.value, "video_generation"):
        from ai_models.video_model import VideoGenerationModel
        return VideoGenerationModel
    elif model_type in (MT.TEXT_GENERATION.value, "text_generation"):
        from ai_models.coder_model import CodeGenerationModel
        return CodeGenerationModel
    return None


@router.post("/{model_name}/load")
async def load_model(
    model_name: str,
    user: CurrentUser,
):
    """加载模型到内存/显存。

    从 registry 获取模型配置，创建对应模型实例并调用 .load()。
    支持 safetensors（transformers）和 GGUF（llama-cpp）两种格式。
    已加载的模型会被缓存在全局 _loaded_models 字典中。
    """
    from ai_models.registry import get_config
    from ai_models.base import ModelConfig

    # 检查是否已加载
    async with _loaded_models_lock:
        if model_name in _loaded_models:
            cached = _loaded_models[model_name]
            return {
                "model_name": model_name,
                "status": "already_loaded",
                "message": f"Model {model_name} is already loaded",
                "display_name": getattr(cached.config, "display_name", model_name),
                "is_loaded": cached.is_loaded if hasattr(cached, "is_loaded") else True,
            }

    # 获取模型配置
    config: ModelConfig | None = get_config(model_name)
    if not config:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{model_name}' not registered. Available models: "
                   f"{list(_get_registered_names())}",
        )

    # 获取模型类
    model_cls = _get_model_class(config.model_type.value if hasattr(config.model_type, 'value') else str(config.model_type))
    if model_cls is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported model type: {config.model_type}",
        )

    # 创建并加载模型
    try:
        model = model_cls(config)
        model.load()

        if model.is_loaded:
            async with _loaded_models_lock:
                _loaded_models[model_name] = model
            return {
                "model_name": model_name,
                "status": "loaded",
                "display_name": config.display_name,
                "model_format": config.model_format.value if hasattr(config.model_format, 'value') else str(config.model_format),
                "message": f"Model {config.display_name} loaded successfully",
            }
        else:
            return {
                "model_name": model_name,
                "status": "load_failed",
                "display_name": config.display_name,
                "message": f"Model {config.display_name} failed to load (check logs for details)",
            }
    except ImportError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Model {model_name} requires missing dependencies: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load model {model_name}: {str(e)}",
        )


@router.post("/{model_name}/unload")
async def unload_model(
    model_name: str,
    user: CurrentUser,
):
    """卸载模型 — 释放内存/显存资源。

    从全局缓存中移除模型实例并调用 .unload() 释放资源。
    """
    async with _loaded_models_lock:
        if model_name in _loaded_models:
            model = _loaded_models.pop(model_name)
        else:
            model = None

    if model is not None:
        try:
            if hasattr(model, "unload"):
                model.unload()
            del model
        except Exception as e:
            # 即使卸载出错也清除引用
            pass

        # 强制垃圾回收
        import gc
        gc.collect()

        return {
            "model_name": model_name,
            "status": "unloaded",
            "message": f"Model {model_name} unloaded and resources freed",
        }

    # 尝试从未知状态卸载（registry 中存在的模型）
    from ai_models.registry import get_config
    config = get_config(model_name)
    if config:
        return {
            "model_name": model_name,
            "status": "not_loaded",
            "message": f"Model {model_name} is registered but was not loaded",
        }

    raise HTTPException(
        status_code=404,
        detail=f"Model '{model_name}' not found in registry",
    )


@router.get("/loaded")
async def list_loaded_models(user: CurrentUser):
    """列出当前已加载到内存的模型。"""
    async with _loaded_models_lock:
        loaded = dict(_loaded_models)
    return {
        "loaded_models": [
            {
                "name": name,
                "display_name": getattr(model.config, "display_name", name),
                "is_loaded": model.is_loaded if hasattr(model, "is_loaded") else True,
            }
            for name, model in loaded.items()
        ],
        "count": len(loaded),
    }


def _get_registered_names() -> list[str]:
    """获取所有已注册的模型名称。"""
    from ai_models.registry import list_all
    return list(list_all().keys())


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
    """配置 API 提供商密钥（AES 加密存储）。

    API 密钥使用 AES-256（Fernet）加密后存储到数据库，
    密钥由 SECRET_KEY 派生，确保服务重启后仍可正常解密。
    """
    from app.core.crypto import encrypt_api_key

    # AES 加密 API Key
    try:
        encrypted_key = encrypt_api_key(cred.api_key)
    except ImportError:
        # cryptography 未安装时回退到明文存储（开发环境）
        encrypted_key = cred.api_key

    credential = ApiCredential(
        provider=cred.provider,
        api_key_encrypted=encrypted_key,
        endpoint=cred.endpoint,
        owner_id=user.id,
    )
    commit_or_rollback(session, credential)

    # 更新网关凭据（用原始密钥）
    from app.core.api_gateway import get_api_gateway
    gateway = get_api_gateway()
    gateway.update_credential(cred.provider, cred.api_key)

    return {
        "provider": cred.provider,
        "status": "configured",
        "encrypted": encrypted_key != cred.api_key,
        "message": f"{cred.provider} API key saved (encrypted={encrypted_key != cred.api_key})",
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
        stmt.order_by(ModelUsageStat.created_at.desc()).limit(days * 200)  # type: ignore[arg-type]
    ).all()

    # 汇总
    aggregated: dict[str, dict[str, int]] = {}
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
