"""
备份/恢复 REST API — Session 52

对标 VSCode userDataSync backup + platform/backup:
- 全量导出 ZIP (KB元数据+FAISS索引+配置+目录)
- 全量导入恢复 (版本检查+安全验证+逐表导入)
- 增量检查点 (Git-based file checkpoint)

路由:
  POST   /system/backup/export      — 触发全量导出，返回ZIP下载URL
  GET    /system/backup/export/{id} — 下载导出的ZIP文件
  POST   /system/backup/import      — 上传ZIP并触发全量恢复
  GET    /system/backup/status      — 查看备份/恢复任务状态
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from starlette.responses import FileResponse

from app.core.backup import DataExporter, DataImporter, ImportResult

logger = logging.getLogger("app.api.routes.system.backup")

router = APIRouter(prefix="/system/backup", tags=["system-backup"])

# ── 任务状态管理 (内存) ──
_task_store: dict[str, dict] = {}

_EXPORT_DIR = Path("data/backups")
_EXPORT_DIR.mkdir(parents=True, exist_ok=True)


class ExportResponse(BaseModel):
    """导出触发响应"""
    task_id: str
    status: str = "pending"
    message: str = "Export started in background"


class ImportResponse(BaseModel):
    """导入触发响应"""
    task_id: str
    status: str = "pending"
    message: str = "Import started in background"


class TaskStatusResponse(BaseModel):
    """任务状态"""
    task_id: str
    type: str  # "export" | "import"
    status: str  # "pending" | "running" | "completed" | "failed"
    progress: float = 0.0
    message: str = ""
    result: Optional[dict] = None
    error: Optional[str] = None
    created_at: str
    updated_at: str


class BackupListResponse(BaseModel):
    """备份文件列表"""
    backups: list[dict]
    total: int


# ═══════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════

@router.post("/export", response_model=ExportResponse)
async def trigger_export(
    background_tasks: BackgroundTasks,
    kb_manager: Optional[object] = None,  # 由依赖注入提供
) -> ExportResponse:
    """触发全量数据导出到ZIP，后台异步执行"""
    task_id = f"export-{uuid.uuid4().hex[:12]}"
    output_path = str(_EXPORT_DIR / f"backup-{task_id}.zip")

    _task_store[task_id] = {
        "type": "export",
        "status": "pending",
        "progress": 0.0,
        "message": "Queued",
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    background_tasks.add_task(
        _run_export, task_id, output_path, kb_manager
    )

    return ExportResponse(task_id=task_id, message="Export started in background")


async def _run_export(task_id: str, output_path: str, kb_manager=None) -> None:
    """后台导出任务"""
    task = _task_store.get(task_id)
    if not task:
        return

    task["status"] = "running"
    task["message"] = "Exporting..."
    task["updated_at"] = datetime.now(timezone.utc).isoformat()

    def progress_cb(stage: str, pct: float, detail: str) -> None:
        task["progress"] = pct
        task["message"] = f"[{stage}] {detail}"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        exporter = DataExporter(
            kb_manager=kb_manager,
            config_dir="",
            progress_callback=progress_cb,
        )
        result_path = await exporter.export_all(output_path)

        task["status"] = "completed"
        task["progress"] = 100.0
        task["message"] = "Export completed"
        task["result"] = {"file": result_path, "size_bytes": os.path.getsize(result_path)}
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Backup export completed: {result_path}")
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["message"] = f"Export failed: {e}"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        logger.exception(f"Backup export failed: {e}")


@router.get("/export/{task_id}")
async def download_export(task_id: str):
    """下载已完成的导出ZIP文件"""
    task = _task_store.get(task_id)
    if not task or task["type"] != "export":
        raise HTTPException(status_code=404, detail="Export task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"Export not ready, status: {task['status']}")

    file_path = task.get("result", {}).get("file", "")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Export file not found on disk")

    return FileResponse(
        path=file_path,
        filename=f"ai-fullstack-backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip",
        media_type="application/zip",
    )


# ═══════════════════════════════════════════════════════════════
# 导入
# ═══════════════════════════════════════════════════════════════

@router.post("/import", response_model=ImportResponse)
async def trigger_import(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    kb_manager: Optional[object] = None,
) -> ImportResponse:
    """上传ZIP备份文件并触发全量恢复，后台异步执行"""
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are accepted")

    task_id = f"import-{uuid.uuid4().hex[:12]}"
    upload_path = str(_EXPORT_DIR / f"upload-{task_id}.zip")

    # 保存上传文件
    content = await file.read()
    if len(content) > 500 * 1024 * 1024:  # 500MB hard limit
        raise HTTPException(status_code=413, detail="Backup file too large (>500MB)")

    with open(upload_path, "wb") as f:
        f.write(content)

    _task_store[task_id] = {
        "type": "import",
        "status": "pending",
        "progress": 0.0,
        "message": "Uploaded, queued for import",
        "result": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    background_tasks.add_task(_run_import, task_id, upload_path, kb_manager)

    return ImportResponse(task_id=task_id, message="Import started in background")


async def _run_import(task_id: str, zip_path: str, kb_manager=None) -> None:
    """后台导入任务"""
    task = _task_store.get(task_id)
    if not task:
        return

    task["status"] = "running"
    task["message"] = "Importing..."
    task["updated_at"] = datetime.now(timezone.utc).isoformat()

    def progress_cb(stage: str, pct: float, detail: str) -> None:
        task["progress"] = pct
        task["message"] = f"[{stage}] {detail}"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()

    try:
        importer = DataImporter(
            kb_manager=kb_manager,
            config_dir="",
            progress_callback=progress_cb,
        )
        result: ImportResult = await importer.import_all(zip_path)

        task["status"] = "completed" if result.success else "completed_with_warnings"
        task["progress"] = 100.0
        task["message"] = "Import completed"
        task["result"] = {
            "success": result.success,
            "imported_tables": result.imported_tables,
            "warnings": result.warnings,
            "errors": result.errors,
        }
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        logger.info(f"Backup import completed: {result}")
    except Exception as e:
        task["status"] = "failed"
        task["error"] = str(e)
        task["message"] = f"Import failed: {e}"
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        logger.exception(f"Backup import failed: {e}")
    finally:
        # 清理上传的临时文件
        try:
            os.remove(zip_path)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════
# 状态查询
# ═══════════════════════════════════════════════════════════════

@router.get("/status", response_model=list[TaskStatusResponse])
async def list_tasks(
    task_type: Optional[str] = Query(None, description="Filter: export | import"),
    status: Optional[str] = Query(None, description="Filter: pending | running | completed | failed"),
) -> list[TaskStatusResponse]:
    """列出所有备份/恢复任务"""
    tasks = []
    for tid, t in _task_store.items():
        if task_type and t["type"] != task_type:
            continue
        if status and t["status"] != status:
            continue
        tasks.append(TaskStatusResponse(
            task_id=tid, type=t["type"], status=t["status"],
            progress=t["progress"], message=t["message"],
            result=t.get("result"), error=t.get("error"),
            created_at=t["created_at"], updated_at=t["updated_at"],
        ))
    # 最近优先
    tasks.sort(key=lambda x: x.created_at, reverse=True)
    return tasks


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str) -> TaskStatusResponse:
    """查询单个任务状态"""
    task = _task_store.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatusResponse(
        task_id=task_id, type=task["type"], status=task["status"],
        progress=task["progress"], message=task["message"],
        result=task.get("result"), error=task.get("error"),
        created_at=task["created_at"], updated_at=task["updated_at"],
    )


@router.get("/files", response_model=BackupListResponse)
async def list_backup_files() -> BackupListResponse:
    """列出本地已有的备份ZIP文件"""
    if not _EXPORT_DIR.exists():
        return BackupListResponse(backups=[], total=0)

    backups = []
    for f in sorted(_EXPORT_DIR.glob("backup-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = f.stat()
        backups.append({
            "filename": f.name,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })

    return BackupListResponse(backups=backups[:50], total=len(backups))
