"""
Context Keys API — when 条件评估 + 上下文管理

POST   /api/v1/system/context-keys/evaluate — 求值 when 子句
GET    /api/v1/system/context-keys/{ws}     — 获取工作区所有 keys
GET    /api/v1/system/context-keys/{ws}/{k} — 获取单个 key
POST   /api/v1/system/context-keys/{ws}     — 设置/批量设置 keys
PUT    /api/v1/system/context-keys/{ws}/{k} — 设置单个 key
DELETE /api/v1/system/context-keys/{ws}/{k} — 删除 key
POST   /api/v1/system/context-keys/{ws}/editor-state — 快捷更新编辑器状态
POST   /api/v1/system/context-keys/{ws}/debug-state   — 快捷更新调试状态
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional

from app.core.context_key import ContextKeyEngine

router = APIRouter(prefix="/system/context-keys", tags=["Context Keys"])


class WhenEvaluateRequest(BaseModel):
    when: str
    workspace_id: str


class BatchSetRequest(BaseModel):
    updates: dict[str, Any]
    persist: bool = False


class SingleSetRequest(BaseModel):
    value: Any
    persist: bool = False


class EditorStateRequest(BaseModel):
    lang_id: str = ""
    has_selection: Optional[bool] = None
    has_multi_selections: Optional[bool] = None
    readonly: Optional[bool] = None
    is_modified: Optional[bool] = None
    resource_ext: str = ""
    resource_filename: str = ""
    resource_path: str = ""


class DebugStateRequest(BaseModel):
    state: str  # stopped / running / paused


@router.post("/evaluate")
def evaluate_when(req: WhenEvaluateRequest):
    """求值 when 子句 (无需预先设置 context keys)"""
    engine = ContextKeyEngine.get_engine(req.workspace_id)
    result = engine.evaluate(req.when)
    return {"result": result, "when": req.when}


@router.get("/{workspace_id}")
def get_all_keys(workspace_id: str):
    """获取工作区所有 context keys"""
    engine = ContextKeyEngine.get_engine(workspace_id)
    return {"workspaceId": workspace_id, "keys": engine.get_snapshot()}


@router.get("/{workspace_id}/{key:path}")
def get_key(workspace_id: str, key: str):
    """获取单个 context key 值"""
    engine = ContextKeyEngine.get_engine(workspace_id)
    value = engine.get(key)
    return {"key": key, "value": value}


@router.post("/{workspace_id}")
def batch_set_keys(workspace_id: str, req: BatchSetRequest):
    """批量设置 context keys"""
    engine = ContextKeyEngine.get_engine(workspace_id)
    changes = engine.batch_set(req.updates)
    return {
        "workspaceId": workspace_id,
        "updated": len(changes),
        "changes": [{"key": c.key, "oldValue": c.old_value, "newValue": c.new_value} for c in changes]
    }


@router.put("/{workspace_id}/{key:path}")
def set_key(workspace_id: str, key: str, req: SingleSetRequest):
    """设置单个 context key"""
    engine = ContextKeyEngine.get_engine(workspace_id)
    change = engine.set(key, req.value, persist=req.persist)
    return {
        "key": key,
        "oldValue": change.old_value,
        "newValue": change.new_value,
    }


@router.delete("/{workspace_id}/{key:path}")
def delete_key(workspace_id: str, key: str):
    """删除 context key"""
    engine = ContextKeyEngine.get_engine(workspace_id)
    old = engine.delete(key)
    return {"key": key, "deleted": old is not None}


@router.post("/{workspace_id}/editor-state")
def update_editor_state(workspace_id: str, req: EditorStateRequest):
    """快捷更新编辑器相关的 context keys"""
    engine = ContextKeyEngine.get_engine(workspace_id)
    changes = engine.update_editor_state(
        lang_id=req.lang_id,
        has_selection=req.has_selection,
        has_multi_selections=req.has_multi_selections,
        readonly=req.readonly,
        is_modified=req.is_modified,
        resource_ext=req.resource_ext,
        resource_filename=req.resource_filename,
        resource_path=req.resource_path,
    )
    return {"updated": len(changes)}


@router.post("/{workspace_id}/debug-state")
def update_debug_state(workspace_id: str, req: DebugStateRequest):
    """快捷更新调试状态 context keys"""
    engine = ContextKeyEngine.get_engine(workspace_id)
    engine.update_debug_state(req.state)
    return {"debugState": req.state}
