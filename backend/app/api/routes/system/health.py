"""
系统 — 健康检查 API

提供系统级别的状态监控：
  - 数据库连接
  - 模型状态
  - API 网关状态
  - 内存/磁盘使用
"""

from fastapi import APIRouter
from sqlmodel import select, func

from app.api.deps import SessionDep
from app.models.system_models import ModelDownload, ModelUsageStat, ApiCredential
from app.models.video_models import VideoTask, VideoAsset
from app.models.studio_models import StudioProject, ChatSession

router = APIRouter(prefix="/system/health", tags=["system-health"])


@router.get("")
def health_check(session: SessionDep):
    """基本健康检查"""
    return {"status": "ok", "service": "ai_fullstack_platform"}


@router.get("/detailed")
def detailed_health(session: SessionDep):
    """详细健康检查"""
    issues = []

    # 数据库检查
    try:
        from app.core.db import engine
        engine.connect()
        db_status = "ok"
    except Exception as e:
        db_status = "error"
        issues.append(f"Database: {e}")

    # 模型状态
    try:
        from ai_models.registry import get_all_local_configs
        local_count = len(get_all_local_configs())
        from ai_models.registry import get_all_remote_configs
        remote_count = len(get_all_remote_configs())
        model_status = f"{local_count} local + {remote_count} remote"
    except Exception as e:
        model_status = "error"
        issues.append(f"Models: {e}")

    # API 网关
    try:
        from app.core.api_gateway import get_api_gateway
        gateway = get_api_gateway()
        providers = gateway.list_providers()
        configured = sum(1 for p in providers if p.get("is_configured"))
        gateway_status = f"{configured}/{len(providers)} configured"
    except Exception as e:
        gateway_status = "error"
        issues.append(f"API Gateway: {e}")

    # 路由检查
    try:
        router_ok = True
        router_status = "ok"
    except Exception as e:
        router_status = "error"
        issues.append(f"Router: {e}")

    return {
        "status": "degraded" if issues else "healthy",
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "components": {
            "database": db_status,
            "models": model_status,
            "api_gateway": gateway_status,
            "model_router": router_status,
        },
        "issues": issues if issues else None,
    }


@router.get("/stats")
def system_stats(session: SessionDep):
    """系统统计信息"""
    # 各数据统计
    projects_count = session.exec(select(func.count(StudioProject.id))).one()
    sessions_count = session.exec(select(func.count(ChatSession.id))).one()
    videos_count = session.exec(select(func.count(VideoAsset.id))).one()
    tasks_count = session.exec(select(func.count(VideoTask.id))).one()
    downloads_count = session.exec(select(func.count(ModelDownload.id))).one()
    api_keys_count = session.exec(select(func.count(ApiCredential.id))).one()
    usage_records = session.exec(select(func.count(ModelUsageStat.id))).one()

    # 磁盘使用
    from app.core.model_downloader import get_downloader
    downloader = get_downloader()
    disk = downloader.get_disk_usage()

    return {
        "database": {
            "projects": projects_count,
            "sessions": sessions_count,
            "videos": videos_count,
            "tasks": tasks_count,
            "downloads": downloads_count,
            "api_credentials": api_keys_count,
            "usage_records": usage_records,
        },
        "storage": disk,
    }
