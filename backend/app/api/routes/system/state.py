"""
State Service API — 全局/工作区状态持久化

GET    /api/v1/system/state/{scope}/{workspace_id}     — 列出所有状态
GET    /api/v1/system/state/{scope}/{ws}/{key}         — 获取单个状态
POST   /api/v1/system/state/{scope}/{ws}/{key}         — 设置状态
DELETE /api/v1/system/state/{scope}/{ws}/{key}         — 删除状态
POST   /api/v1/system/state/cleanup                    — 清理过期状态
POST   /api/v1/system/state/clear/{workspace_id}       — 清除工作区状态
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any, Optional

from app.core.state_service import StateService, state

router = APIRouter(prefix="/system/state", tags=["State"])


class StateSetRequest(BaseModel):
    value: Any
    ttl: float = 0  # 秒, 0=永不过期


class SessionStateSetRequest(BaseModel):
    value: Any


@router.get("/{scope}/global")
def list_global_state(scope: str):
    """列出全局状态 (scope=global)"""
    svc = state()
    return {"scope": "global", "data": svc._memory["global"]}


@router.get("/{scope}/{workspace_id}")
def list_workspace_state(scope: str, workspace_id: str):
    """列出工作区状态"""
    svc = state()
    if scope == "workspace":
        data = svc.list_workspace(workspace_id)
    elif scope == "session":
        data = {k: v.value for k, v in svc._memory["session"].items()}
    else:
        data = {}
    return {"scope": scope, "workspaceId": workspace_id, "data": data}


@router.get("/{scope}/{workspace_id}/{key:path}")
def get_state(scope: str, workspace_id: str, key: str):
    """获取单个状态值"""
    svc = state()
    if scope == "global":
        value = svc.get_global(key)
    elif scope == "workspace":
        value = svc.get_workspace(workspace_id, key)
    elif scope == "session":
        value = svc.get_session(key)
    else:
        value = None
    return {"key": key, "value": value}


@router.post("/{scope}/{workspace_id}/{key:path}")
def set_state(scope: str, workspace_id: str, key: str, req: StateSetRequest):
    """设置状态值"""
    svc = state()
    if scope == "global":
        svc.set_global(key, req.value, ttl=req.ttl)
    elif scope == "workspace":
        svc.set_workspace(workspace_id, key, req.value, ttl=req.ttl)
    elif scope == "session":
        svc.set_session(key, req.value)
    return {"key": key, "set": True}


@router.delete("/{scope}/{workspace_id}/{key:path}")
def delete_state(scope: str, workspace_id: str, key: str):
    """删除状态值"""
    svc = state()
    if scope == "global":
        svc.delete_global(key)
    elif scope == "workspace":
        svc.delete_workspace(workspace_id, key)
    elif scope == "session":
        svc.delete_session(key)
    return {"key": key, "deleted": True}


@router.post("/cleanup")
def cleanup_expired():
    """清理所有过期状态"""
    svc = state()
    count = svc.cleanup_expired()
    return {"cleaned": count}


@router.post("/clear/{workspace_id}")
def clear_all(workspace_id: str):
    """清除工作区所有状态"""
    svc = state()
    svc.clear_all(workspace_id)
    return {"workspaceId": workspace_id, "cleared": True}


@router.post("/flush")
def flush_all():
    """强制持久化所有状态"""
    svc = state()
    svc.flush()
    return {"flushed": True}
