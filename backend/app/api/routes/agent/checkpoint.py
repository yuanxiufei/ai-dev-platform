"""
Checkpoint/Rollback API — 状态快照 + 一键回滚

借鉴 RooCode checkpoints/ 设计：
  GET  /agent/checkpoints — 列出所有检查点
  GET  /agent/checkpoints/{id} — 获取检查点详情
  POST /agent/checkpoints/{id}/rollback — 回滚到指定检查点
  POST /agent/checkpoints/cleanup — 清理旧检查点
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.agent.checkpoint import (
    FileCheckpointManager,
    get_file_checkpoint_manager,
    init_file_checkpoint_manager,
)

logger = logging.getLogger("api.agent.checkpoint")

router = APIRouter(prefix="/agent/checkpoints", tags=["agent-checkpoint"])


@router.get("")
async def list_checkpoints(
    user: CurrentUser,
    agent_name: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    列出所有检查点
    
    Query:
        agent_name: 按 Agent 名称筛选
        limit: 分页大小 (默认 20)
        offset: 偏移量
    """
    cpm = get_file_checkpoint_manager()
    checkpoints = cpm.list(agent_name=agent_name, limit=limit, offset=offset)
    return {
        "data": checkpoints,
        "total": cpm.total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{checkpoint_id}")
async def get_checkpoint(
    checkpoint_id: str,
    user: CurrentUser,
) -> dict[str, Any]:
    """
    获取单个检查点详情
    
    Returns:
        检查点详细信息，包含所有文件快照
    """
    cpm = get_file_checkpoint_manager()
    cp = cpm.get(checkpoint_id)
    if not cp:
        return {"error": "Checkpoint not found", "id": checkpoint_id}
    
    return {
        "id": cp.id,
        "agent_name": cp.agent_name,
        "turn_number": cp.turn_number,
        "timestamp": cp.timestamp,
        "user_message": cp.user_message,
        "assistant_summary": cp.assistant_summary,
        "files_modified": [
            {
                "path": s.path,
                "hash": s.content_hash[:16],
                "preview": s.content[:200] if s.stored_inline else "[binary/large file]",
            }
            for s in cp.files_modified
        ],
        "model_used": cp.model_used,
        "tokens_used": cp.tokens_used,
        "tool_calls_count": cp.tool_calls_count,
    }


@router.post("/{checkpoint_id}/rollback")
async def rollback_checkpoint(
    checkpoint_id: str,
    user: CurrentUser,
) -> dict[str, Any]:
    """
    回滚到指定检查点
    
    将指定检查点的所有文件恢复到当时的状态。
    警告: 不可逆操作!
    
    Returns:
        {"restored": [...], "failed": [...], "checkpoint_id": "..."}
    """
    cpm = get_file_checkpoint_manager()
    cp = cpm.get(checkpoint_id)
    if not cp:
        return {"error": "Checkpoint not found", "id": checkpoint_id}
    
    try:
        result = await cpm.rollback(checkpoint_id)
        logger.info(
            "Rollback to %s: %d restored, %d failed (user=%s)",
            checkpoint_id,
            len(result["restored"]),
            len(result["failed"]),
            user.id if hasattr(user, "id") else "unknown",
        )
        return {
            **result,
            "checkpoint_id": checkpoint_id,
            "agent_name": cp.agent_name,
            "turn_number": cp.turn_number,
        }
    except Exception as e:
        logger.error("Rollback to %s failed: %s", checkpoint_id, e)
        return {"error": str(e), "restored": [], "failed": []}


@router.post("/cleanup")
async def cleanup_checkpoints(
    user: CurrentUser,
    max_checkpoints: int = 50,
) -> dict[str, Any]:
    """
    清理旧检查点
    
    保留最近的 N 个检查点，删除其余的。
    """
    cpm = get_file_checkpoint_manager()
    deleted = await cpm.cleanup(max_checkpoints=max_checkpoints)
    return {
        "deleted": deleted,
        "remaining": cpm.total,
        "max_checkpoints": max_checkpoints,
    }
