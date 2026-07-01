"""
Session 树 API — 借鉴 hermes-agent SessionTree 设计

端点：
  - GET  /system/session-tree       — 树总览（所有分支链）
  - GET  /system/session-tree/{id} — 节点详情（含子树）
  - POST /system/session-tree/fork  — 从节点 fork 新分支
  - POST /system/session-tree/checkpoints — 保存检查点
  - POST /system/session-tree/restore      — 从检查点恢复
  - GET  /system/session-tree/checkpoints  — 检查点列表
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/session-tree", tags=["SessionTree"])


class ForkRequest(BaseModel):
    node_id: str
    branch_name: str = ""
    branch_reason: str = ""
    save_checkpoint: bool = True


class SaveCheckpointRequest(BaseModel):
    session_id: str
    agent_id: str = ""
    label: str = ""
    description: str = ""
    turn: int = 0


class RestoreRequest(BaseModel):
    checkpoint_id: str
    agent_config: dict = {}
    user_message: str = ""


@router.get("")
async def get_tree_overview():
    """获取 Session 树总览"""
    try:
        from app.core.agent.session_tree import get_session_tree
        tree = get_session_tree()
        return {
            "summary": tree.tree_summary(),
            "roots": [n.to_dict(include_messages=False) for n in tree.root_nodes],
        }
    except Exception as e:
        logger.exception("Failed to get tree overview")
        raise HTTPException(status_code=500, detail="Internal error retrieving session tree")


@router.get("/{node_id}")
async def get_node_detail(node_id: str, include_messages: bool = False):
    """获取节点详情（含子树）"""
    try:
        from app.core.agent.session_tree import get_session_tree
        tree = get_session_tree()

        node = tree.get_node(node_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

        return {
            "node": node.to_dict(include_messages=include_messages),
            "children": [c.to_dict(include_messages=False) for c in tree.get_children(node_id)],
            "branch_chain": [n.to_dict(include_messages=False) for n in tree.get_branch_chain(node_id)],
            "checkpoints": [cp.to_dict() for cp in tree.get_checkpoints_for_node(node_id)],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get node detail: %s", node_id)
        raise HTTPException(status_code=500, detail="Internal error retrieving node detail")


@router.get("/{node_id}/subtree")
async def get_subtree(node_id: str):
    """获取节点的完整子树"""
    try:
        from app.core.agent.session_tree import get_session_tree
        tree = get_session_tree()

        if not tree.get_node(node_id):
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")

        subtree = tree.get_subtree(node_id)
        return {
            "root_id": node_id,
            "node_count": len(subtree),
            "nodes": [n.to_dict(include_messages=False) for n in subtree],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get subtree: %s", node_id)
        raise HTTPException(status_code=500, detail="Internal error retrieving subtree")


@router.post("/fork")
async def fork_branch(req: ForkRequest):
    """从指定节点 fork 新分支"""
    try:
        from app.core.agent.session_tree import get_session_tree
        tree = get_session_tree()

        branch = tree.fork(
            node_id=req.node_id,
            branch_name=req.branch_name,
            branch_reason=req.branch_reason,
            save_checkpoint=req.save_checkpoint,
        )

        if not branch:
            raise HTTPException(status_code=404, detail=f"Node {req.node_id} not found")

        return {"branch": branch.to_dict(include_messages=False)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fork branch: %s", req.node_id)
        raise HTTPException(status_code=500, detail="Internal error creating branch")


@router.get("/branches/all")
async def list_all_branches(root_id: str | None = None):
    """列出所有分支"""
    try:
        from app.core.agent.session_tree import get_session_tree
        tree = get_session_tree()
        branches = tree.get_all_branches(root_id)
        return {"branches": branches, "total": len(branches)}
    except Exception as e:
        logger.exception("Failed to list branches")
        raise HTTPException(status_code=500, detail="Internal error listing branches")


# ── 检查点 ───────────────────────────────────────────

@router.post("/checkpoints")
async def save_checkpoint(req: SaveCheckpointRequest):
    """保存检查点"""
    try:
        from app.core.agent.session_tree import get_session_tree
        tree = get_session_tree()

        node = tree.get_node(req.session_id)
        if not node:
            raise HTTPException(status_code=404, detail=f"Session {req.session_id} not found")

        cp = tree.save_checkpoint(
            session_id=req.session_id,
            agent_id=req.agent_id or node.agent_id,
            messages=node.messages,
            tool_results=node.tool_results,
            agent_config=node.agent_config,
            label=req.label,
            description=req.description,
            turn=node.total_turns,
            total_tokens=node.total_tokens,
        )
        return {"checkpoint": cp.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to save checkpoint: %s", req.session_id)
        raise HTTPException(status_code=500, detail="Internal error saving checkpoint")


@router.get("/checkpoints")
async def list_checkpoints():
    """列出所有检查点"""
    try:
        from app.core.agent.session_tree import get_checkpoint_manager
        cpm = get_checkpoint_manager()
        checkpoints = cpm.list_all()
        return {"checkpoints": checkpoints, "total": len(checkpoints)}
    except Exception as e:
        logger.exception("Failed to list checkpoints")
        raise HTTPException(status_code=500, detail="Internal error listing checkpoints")


@router.get("/checkpoints/{checkpoint_id}")
async def get_checkpoint(checkpoint_id: str):
    """获取检查点详情"""
    try:
        from app.core.agent.session_tree import get_checkpoint_manager
        cpm = get_checkpoint_manager()
        cp = cpm.load(checkpoint_id)
        if not cp:
            raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")
        return {"checkpoint": cp.to_dict(), "messages_count": len(cp.messages)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to get checkpoint: %s", checkpoint_id)
        raise HTTPException(status_code=500, detail="Internal error retrieving checkpoint")


@router.delete("/checkpoints/{checkpoint_id}")
async def delete_checkpoint(checkpoint_id: str):
    """删除检查点"""
    try:
        from app.core.agent.session_tree import get_checkpoint_manager
        cpm = get_checkpoint_manager()
        success = cpm.delete(checkpoint_id)
        if not success:
            raise HTTPException(status_code=404, detail=f"Checkpoint {checkpoint_id} not found")
        return {"deleted": True, "checkpoint_id": checkpoint_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to delete checkpoint: %s", checkpoint_id)
        raise HTTPException(status_code=500, detail="Internal error deleting checkpoint")


@router.post("/restore")
async def restore_from_checkpoint(req: RestoreRequest):
    """从检查点恢复会话"""
    try:
        from app.core.agent.session_tree import get_session_tree
        tree = get_session_tree()

        node = await tree.restore(
            checkpoint_id=req.checkpoint_id,
            agent_config=req.agent_config,
            user_message=req.user_message,
        )

        if not node:
            raise HTTPException(status_code=404, detail=f"Checkpoint {req.checkpoint_id} not found")

        return {
            "restored_session": node.to_dict(include_messages=False),
            "messages_count": len(node.messages),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to restore checkpoint: %s", req.checkpoint_id)
        raise HTTPException(status_code=500, detail="Internal error restoring checkpoint")
