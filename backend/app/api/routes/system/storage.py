"""
存储管理 API — 用户自定义存储路径、配额查看、统计信息
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.storage import get_storage_manager

router = APIRouter(prefix="/system/storage", tags=["storage"])


class StorageStatsResponse(BaseModel):
    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    file_count: int
    is_readable: bool


class StorageAllStatsResponse(BaseModel):
    categories: dict[str, StorageStatsResponse]


class MigrateRequest(BaseModel):
    new_root: str


class StorageConfigResponse(BaseModel):
    storage_root: str
    models_dir: str
    kb_dir: str
    workspace_dir: str
    trajectories_dir: str
    backups_dir: str
    plugins_dir: str
    data_dir: str
    skills_dir: str
    max_storage_gb: int
    max_workspace_gb: int


class CleanupRequest(BaseModel):
    path: str
    max_age_hours: int = 24


@router.get("/stats")
def get_storage_stats() -> StorageAllStatsResponse:
    """获取所有存储类别的统计信息"""
    mgr = get_storage_manager()
    all_stats = mgr.get_all_stats()
    categories = {
        k: StorageStatsResponse(
            path=v.path,
            total_gb=round(v.total_bytes / (1024**3), 2),
            used_gb=round(v.used_bytes / (1024**3), 2),
            free_gb=round(v.free_bytes / (1024**3), 2),
            file_count=v.file_count,
            is_readable=v.is_readable,
        )
        for k, v in all_stats.items()
    }
    return StorageAllStatsResponse(categories=categories)


@router.get("/config")
def get_storage_config() -> StorageConfigResponse:
    """获取当前存储配置"""
    mgr = get_storage_manager()
    cfg = mgr.config
    return StorageConfigResponse(
        storage_root=cfg.storage_root,
        models_dir=cfg.models_dir,
        kb_dir=cfg.kb_dir,
        workspace_dir=cfg.workspace_dir,
        trajectories_dir=cfg.trajectories_dir,
        backups_dir=cfg.backups_dir,
        plugins_dir=cfg.plugins_dir,
        data_dir=cfg.data_dir,
        skills_dir=cfg.skills_dir,
        max_storage_gb=cfg.max_storage_gb,
        max_workspace_gb=cfg.max_workspace_gb,
    )


@router.post("/config")
async def update_storage_config(config: StorageConfigResponse) -> dict[str, str]:
    """更新存储配置（部分字段）"""
    mgr = get_storage_manager()
    # 注意：这是运行时更新，不会写入 .env
    mgr.config.max_storage_gb = config.max_storage_gb
    mgr.config.max_workspace_gb = config.max_workspace_gb
    return {"message": "Storage config updated"}


@router.post("/migrate")
async def migrate_storage_root(req: MigrateRequest) -> dict[str, str]:
    """迁移存储根目录到新位置"""
    mgr = get_storage_manager()
    success = await mgr.migrate_storage_root(req.new_root)
    if not success:
        raise HTTPException(status_code=400, detail="Migration failed: target not empty or invalid")
    return {"message": f"Storage migrated to {req.new_root}"}


@router.post("/cleanup")
def cleanup_storage(req: CleanupRequest) -> dict[str, int]:
    """清理临时文件"""
    mgr = get_storage_manager()
    deleted = mgr.cleanup_old_files(req.path, req.max_age_hours)
    return {"deleted": deleted}


@router.get("/quota")
def check_storage_quota() -> dict[str, bool]:
    """检查存储配额"""
    mgr = get_storage_manager()
    ok, reason = mgr.check_quota(mgr.config.storage_root)
    return {"ok": ok, "reason": reason}
