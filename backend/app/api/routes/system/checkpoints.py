"""
Checkpoints API — 代码修改检查点/回滚
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.checkpoint import get_checkpoint_manager

router = APIRouter(prefix="/system/checkpoints", tags=["checkpoints"])


class CreateCheckpointRequest(BaseModel):
    label: str = ""
    metadata: dict[str, str] = {}


class CheckpointResponse(BaseModel):
    id: str
    timestamp: str
    git_ref: str
    metadata: dict[str, str]
    file_count: int
    diff_summary: str


@router.post("")
def create_checkpoint(req: CreateCheckpointRequest) -> dict:
    """创建检查点"""
    mgr = get_checkpoint_manager()
    result = mgr.create(label=req.label, metadata=req.metadata)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    cp = result.checkpoint
    return {
        "id": cp.id,
        "timestamp": cp.timestamp,
        "git_ref": cp.git_ref,
        "metadata": cp.metadata,
        "file_count": cp.file_count,
        "diff_summary": cp.diff_summary,
        "message": "Checkpoint created",
    }


@router.get("")
def list_checkpoints() -> list[CheckpointResponse]:
    """列出所有活跃检查点"""
    mgr = get_checkpoint_manager()
    return [
        CheckpointResponse(
            id=c.id,
            timestamp=c.timestamp,
            git_ref=c.git_ref,
            metadata=c.metadata,
            file_count=c.file_count,
            diff_summary=c.diff_summary,
        )
        for c in mgr.list_all()
    ]


@router.post("/{checkpoint_id}/restore")
def restore_checkpoint(checkpoint_id: str) -> dict:
    """回滚到指定检查点"""
    mgr = get_checkpoint_manager()
    result = mgr.restore(checkpoint_id)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)
    return {"message": f"Restored to checkpoint {checkpoint_id}"}


@router.delete("/{checkpoint_id}")
def delete_checkpoint(checkpoint_id: str) -> dict:
    """删除检查点"""
    mgr = get_checkpoint_manager()
    if mgr.delete(checkpoint_id):
        return {"message": f"Checkpoint {checkpoint_id} deleted"}
    raise HTTPException(status_code=404, detail="Checkpoint not found")


@router.get("/{checkpoint_id}/diff")
def get_checkpoint_diff(checkpoint_id: str) -> dict:
    """获取检查点差异"""
    mgr = get_checkpoint_manager()
    diff = mgr.get_diff(checkpoint_id)
    return {"checkpoint_id": checkpoint_id, "diff": diff}
