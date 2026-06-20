"""
Worktree API 路由 — Git Worktree 并行开发环境管理

端点：
  GET    /agent/worktree                    — 列出所有 worktree + 统计
  GET    /agent/worktree/branches           — 可用分支列表
  POST   /agent/worktree/create             — 创建 worktree
  POST   /agent/worktree/{worktree_id}/delete — 删除 worktree
  POST   /agent/worktree/cleanup            — 清理孤立 worktree
  GET    /agent/worktree/tasks              — 列出任务
  POST   /agent/worktree/tasks              — 注册任务
  POST   /agent/worktree/tasks/{task_id}/complete — 完成任务
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.agent.worktree import (
    WorktreeManager,
    WorktreeTask,
    get_worktree_manager,
)

logger = logging.getLogger("api.worktree")

router = APIRouter(prefix="/agent/worktree", tags=["Agent - Worktree"])


def _manager() -> WorktreeManager:
    return get_worktree_manager()


# ── Worktree CRUD ────────────────────────────────────────────


@router.get("")
async def list_worktrees() -> dict[str, Any]:
    """列出所有 worktree + 统计"""
    mgr = _manager()

    # 检查是否为 git 仓库
    is_repo = await mgr.is_git_repo()
    if not is_repo:
        return {
            "is_git_repo": False,
            "worktrees": [],
            "message": "Current directory is not a git repository",
        }

    stats = await mgr.stats()
    return {
        "is_git_repo": True,
        **stats,
    }


@router.get("/branches")
async def get_branches(
    include_worktree_branches: bool = Query(False, description="包含已在 worktree 中的分支"),
) -> dict[str, Any]:
    """获取可用分支列表"""
    mgr = _manager()

    is_repo = await mgr.is_git_repo()
    if not is_repo:
        raise HTTPException(status_code=400, detail="Not a git repository")

    return await mgr.get_branches(
        include_worktree_branches=include_worktree_branches,
    )


@router.post("/create")
async def create_worktree(payload: dict[str, Any]) -> dict[str, Any]:
    """创建新的 worktree

    Body:
        branch: str = ""           — 分支名
        base_branch: str = ""      — 基础分支
        create_new_branch: bool = True
        path_override: str = ""    — 覆盖路径
        description: str = ""      — 任务描述
    """
    mgr = _manager()

    is_repo = await mgr.is_git_repo()
    if not is_repo:
        raise HTTPException(status_code=400, detail="Not a git repository")

    branch = payload.get("branch", "")
    base_branch = payload.get("base_branch", "")
    create_new = payload.get("create_new_branch", True)
    path_override = payload.get("path_override", "")
    description = payload.get("description", "")

    result = await mgr.create_worktree(
        branch=branch,
        base_branch=base_branch,
        create_new_branch=create_new,
        path_override=path_override,
        description=description,
    )

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "success": True,
        "message": result.message,
        "worktree": result.worktree.to_dict() if result.worktree else None,
    }


@router.post("/{worktree_path:path}/delete")
async def delete_worktree(
    worktree_path: str,
    force: bool = Query(False, description="强制删除"),
) -> dict[str, Any]:
    """删除 worktree"""
    mgr = _manager()
    result = await mgr.delete_worktree(worktree_path, force=force)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "success": True,
        "message": result.message,
    }


@router.post("/cleanup")
async def cleanup_worktrees() -> dict[str, Any]:
    """清理孤立 worktree 目录"""
    mgr = _manager()

    is_repo = await mgr.is_git_repo()
    if not is_repo:
        raise HTTPException(status_code=400, detail="Not a git repository")

    result = await mgr.clean_orphan_worktrees()
    return {
        "success": result.success,
        "message": result.message,
    }


# ── Worktree 操作 ────────────────────────────────────────────


@router.post("/checkout")
async def checkout_branch(payload: dict[str, Any]) -> dict[str, Any]:
    """在 worktree 中检出分支

    Body:
        branch: str              — 目标分支
        worktree_path: str = ""  — worktree 路径（空=主仓库）
    """
    mgr = _manager()
    branch = payload.get("branch", "")
    wt_path = payload.get("worktree_path", "")

    if not branch:
        raise HTTPException(status_code=400, detail="branch is required")

    result = await mgr.checkout_branch(branch, wt_path or None)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)

    return {"success": True, "message": result.message}


@router.post("/merge")
async def merge_branch(payload: dict[str, Any]) -> dict[str, Any]:
    """在 worktree 中合并分支

    Body:
        source_branch: str       — 源分支
        worktree_path: str = ""  — worktree 路径
        message: str = ""        — merge commit message
    """
    mgr = _manager()
    source = payload.get("source_branch", "")
    wt_path = payload.get("worktree_path", "")
    message = payload.get("message", "")

    if not source:
        raise HTTPException(status_code=400, detail="source_branch is required")

    result = await mgr.merge_branch(source, wt_path or None, message)
    return {
        "success": result.success,
        "message": result.message,
        "conflict": result.data.get("conflict", False),
    }


@router.get("/{worktree_path:path}/diff")
async def get_worktree_diff(worktree_path: str) -> dict[str, Any]:
    """获取 worktree 的 git diff"""
    mgr = _manager()
    diff = await mgr.get_diff(worktree_path)
    return {"path": worktree_path, "diff": diff}


# ── 任务管理 ─────────────────────────────────────────────────


@router.get("/tasks")
async def list_tasks(
    worktree_path: str | None = Query(None, description="按 worktree 过滤"),
    status: str | None = Query(None, description="按状态过滤: pending|running|completed|failed"),
) -> dict[str, Any]:
    """列出 worktree 任务"""
    mgr = _manager()
    tasks = await mgr.list_tasks(worktree_path=worktree_path, status=status)
    return {
        "tasks": [t.to_dict() for t in tasks],
        "total": len(tasks),
    }


@router.post("/tasks")
async def register_task(payload: dict[str, Any]) -> dict[str, Any]:
    """注册新任务到 worktree

    Body:
        worktree_path: str  — worktree 路径
        branch: str = ""    — 分支
        description: str = "" — 描述
    """
    mgr = _manager()

    task = WorktreeTask(
        task_id=payload.get("task_id", str(uuid.uuid4())[:8]),
        worktree_path=payload["worktree_path"],
        branch=payload.get("branch", ""),
        description=payload.get("description", ""),
    )

    await mgr.register_task(task)
    return {"task": task.to_dict()}


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """完成任务

    Body:
        success: bool
        error: str = ""
        result: dict = {}
    """
    mgr = _manager()

    success = payload.get("success", True)
    error = payload.get("error", "")
    result_data = payload.get("result", {})

    task = await mgr.complete_task(task_id, success, error, result_data)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    return {"task": task.to_dict()}
