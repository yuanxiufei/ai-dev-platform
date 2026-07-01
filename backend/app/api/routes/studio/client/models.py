"""
Studio — 模型管理 API

提供面向 Studio 用户的模型管理：
  - 列出可用模型（本地 + 远程 API）
  - 模型下载/状态查询
  - 模型切换
"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep, commit_or_rollback
from app.models.system_models import ModelDownload, DownloadStatus, ModelUsageStat

router = APIRouter(prefix="/studio/models", tags=["studio-models"])


# ── Schemas ──────────────────────────────────────────────

class ModelDownloadRequest(BaseModel):
    model_name: str = Field(..., max_length=100)
    source: str = Field(default="huggingface", max_length=50)


# ── 模型列表 ─────────────────────────────────────────────

@router.get("")
def list_models(
    session: SessionDep,
    user: CurrentUser,
    capability: str | None = None,
):
    """
    获取可用模型列表（本地 + 远程）

    包括：
    - 本地已下载模型（实时检测）
    - 可下载的本地模型
    - 已配置的远程 API 模型
    """
    from ai_models import get_all_models, ModelType

    models = get_all_models()

    # 筛选能力类型
    if capability:
        try:
            model_type = ModelType(capability)
            models = get_all_models(model_type)
        except ValueError:
            pass

    return {
        "models": models,
        "total": len(models),
    }


@router.get("/providers")
def list_providers():
    """获取支持的 API 提供商"""
    from app.core.api_gateway import get_api_gateway

    gateway = get_api_gateway()
    providers = gateway.list_providers()

    return {
        "providers": providers,
        "total": len(providers),
    }


# ── 模型下载 ─────────────────────────────────────────────

@router.post("/download", status_code=202)
def trigger_download(
    dl_in: ModelDownloadRequest,
    session: SessionDep,
    user: CurrentUser,
):
    """
    触发模型下载

    异步执行，返回 task_id 用于查询进度
    """
    # 创建下载记录
    download = ModelDownload(
        model_name=dl_in.model_name,
        source=dl_in.model_name,
        source_type=dl_in.source,
        started_by=user.id,
    )
    commit_or_rollback(session, download)

    # 触发异步下载任务（已实现：通过 asyncio.create_task 调度后台下载）
    from app.core.model_downloader import get_downloader
    downloader = get_downloader()

    try:
        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(
                _execute_download(downloader, dl_in, download.id, session)
            )
        else:
            loop.run_until_complete(
                _execute_download(downloader, dl_in, download.id, session)
            )
    except RuntimeError:
        # 在同步上下文中，用 asyncio 运行
        import asyncio
        asyncio.create_task(
            _execute_download(downloader, dl_in, download.id, session)
        )

    return {
        "task_id": str(download.id),
        "model_name": dl_in.model_name,
        "status": "pending",
    }


async def _execute_download(downloader, dl_in, download_id, db_session):
    """执行异步下载"""
    try:
        task_id = await downloader.start_download(
            dl_in.model_name, dl_in.source
        )

        download = db_session.get(ModelDownload, download_id)
        if download:
            download.status = DownloadStatus.DOWNLOADING
            db_session.add(download)
            try:
                db_session.commit()
            except Exception:
                db_session.rollback()

        # 轮询进度
        import asyncio
        while True:
            progress = downloader.get_progress(task_id)
            if not progress:
                break

            download = db_session.get(ModelDownload, download_id)
            if download:
                download.progress = int(progress.progress_pct)
                download.downloaded = progress.downloaded_bytes
                download.file_size = progress.total_bytes
                db_session.add(download)
                try:
                    db_session.commit()
                except Exception:
                    db_session.rollback()

            if progress.state.value in ("completed", "failed", "cancelled"):
                download = db_session.get(ModelDownload, download_id)
                if download:
                    if progress.state.value == "completed":
                        download.status = DownloadStatus.COMPLETED
                        download.progress = 100
                    elif progress.state.value == "cancelled":
                        download.status = DownloadStatus.FAILED
                        download.error_message = "Cancelled"
                    else:
                        download.status = DownloadStatus.FAILED
                        download.error_message = progress.error_message
                    db_session.add(download)
                    try:
                        db_session.commit()
                    except Exception:
                        db_session.rollback()
                break

            await asyncio.sleep(2)

    except Exception as e:
        db_session.rollback()
        download = db_session.get(ModelDownload, download_id)
        if download:
            download.status = DownloadStatus.FAILED
            download.error_message = str(e)
            db_session.add(download)
            try:
                db_session.commit()
            except Exception:
                db_session.rollback()


@router.get("/download/{task_id}")
def get_download_progress(
    task_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """查询下载进度"""
    download = session.get(ModelDownload, task_id)
    if not download:
        raise HTTPException(status_code=404, detail="Download task not found")
    if download.started_by != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "task_id": str(download.id),
        "model_name": download.model_name,
        "status": download.status.value,
        "progress": download.progress,
        "downloaded_bytes": download.downloaded,
        "total_bytes": download.file_size,
        "error_message": download.error_message,
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

    if not user.is_superuser:
        stmt = stmt.where(ModelUsageStat.user_id == user.id)

    if model_name:
        stmt = stmt.where(ModelUsageStat.model_name == model_name)

    stats = session.exec(
        stmt.order_by(ModelUsageStat.created_at.desc()).limit(days * 100)
    ).all()

    # 汇总
    model_stats = {}
    for stat in stats:
        if stat.model_name not in model_stats:
            model_stats[stat.model_name] = {
                "total_calls": 0,
                "success": 0,
                "failed": 0,
                "total_latency_ms": 0,
                "total_tokens": 0,
            }
        ms = model_stats[stat.model_name]
        ms["total_calls"] += 1
        if stat.success:
            ms["success"] += 1
        else:
            ms["failed"] += 1
        ms["total_latency_ms"] += stat.latency_ms
        ms["total_tokens"] += stat.token_count or 0

    return {
        "stats": {
            name: {
                **data,
                "success_rate": (
                    data["success"] / data["total_calls"]
                    if data["total_calls"] > 0 else 0
                ),
                "avg_latency_ms": (
                    data["total_latency_ms"] / data["total_calls"]
                    if data["total_calls"] > 0 else 0
                ),
            }
            for name, data in model_stats.items()
        },
        "period_days": days,
    }


@router.post("/optimize")
async def trigger_optimization(
    days: int = 7,
):
    """触发自动优化"""
    from ai_models.optimizer import get_optimizer

    optimizer = get_optimizer()
    result = optimizer.auto_tune(days=days)

    return result
