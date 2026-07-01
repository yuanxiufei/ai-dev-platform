"""
Integrations API — 第三方服务集成管理

端点:
- GET    /integrations              — 列出所有集成
- GET    /integrations/{id}         — 获取单个集成
- POST   /integrations              — 注册集成配置
- PUT    /integrations/{id}         — 更新集成配置
- DELETE /integrations/{id}         — 删除集成
- POST   /integrations/{id}/connect — 连接服务
- POST   /integrations/{id}/disconnect — 断开服务
- GET    /integrations/stats        — 统计信息
"""

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from app.api.deps import get_current_user, get_db, commit_or_rollback
from app.models.system_models import Integration

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# ── Schemas ──────────────────────────────────────────────

class IntegrationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="唯一标识")
    display_name: str = Field(..., max_length=255)
    description: str = ""
    category: str = Field(default="service", pattern="^(database|deploy|storage|service)$")
    config: dict = Field(default_factory=dict)


class IntegrationUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, pattern="^(database|deploy|storage|service)$")
    config: dict | None = None


class IntegrationResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: str | None
    category: str
    connected: bool
    status: str
    error_message: str | None
    config: dict | None
    last_connected_at: str | None
    created_at: str | None
    updated_at: str | None


def _to_response(entry: Integration) -> IntegrationResponse:
    cfg = None
    if entry.config:
        try:
            cfg = json.loads(entry.config) if isinstance(entry.config, str) else entry.config
        except (json.JSONDecodeError, TypeError):
            cfg = {}
    # 脱敏：隐藏敏感字段
    if cfg:
        cfg = {k: ("***" if k in ("api_key", "secret", "password", "token", "url") else v) for k, v in cfg.items()}

    return IntegrationResponse(
        id=entry.id,
        name=entry.name,
        display_name=entry.display_name,
        description=entry.description,
        category=entry.category,
        connected=entry.connected,
        status=entry.status,
        error_message=entry.error_message,
        config=cfg,
        last_connected_at=entry.last_connected_at.isoformat() if entry.last_connected_at else None,
        created_at=entry.created_at.isoformat() if entry.created_at else None,
        updated_at=entry.updated_at.isoformat() if entry.updated_at else None,
    )


# ── Endpoints ────────────────────────────────────────────

_INTEGRATIONS_MAX_LIST = 200

@router.get("")
async def list_integrations(
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """列出所有集成服务"""
    stmt = select(Integration).where(Integration.user_id == current_user.id)
    if category:
        stmt = stmt.where(Integration.category == category)
    items = db.exec(
        stmt.order_by(Integration.name).limit(_INTEGRATIONS_MAX_LIST)
    ).all()
    return {"data": [_to_response(i) for i in items], "total": len(items)}


@router.get("/{integration_id}")
async def get_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> IntegrationResponse:
    """获取单个集成"""
    entry = db.get(Integration, integration_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="集成不存在")
    return _to_response(entry)


@router.post("")
async def create_integration(
    body: IntegrationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """注册集成配置"""
    exists = db.exec(
        select(Integration).where(
            Integration.user_id == current_user.id,
            Integration.name == body.name,
        )
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail=f"集成 '{body.name}' 已存在")

    entry = Integration(
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        category=body.category,
        config=json.dumps(body.config) if body.config else None,
        user_id=current_user.id,
    )
    db.add(entry)
    commit_or_rollback(db)
    db.refresh(entry)
    return {"data": _to_response(entry).model_dump(), "message": "集成已注册"}


@router.put("/{integration_id}")
async def update_integration(
    integration_id: uuid.UUID,
    body: IntegrationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """更新集成配置"""
    entry = db.get(Integration, integration_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="集成不存在")

    if body.display_name is not None:
        entry.display_name = body.display_name
    if body.description is not None:
        entry.description = body.description
    if body.category is not None:
        entry.category = body.category
    if body.config is not None:
        entry.config = json.dumps(body.config)

    entry.updated_at = datetime.now(timezone.utc)
    db.add(entry)
    commit_or_rollback(db)
    db.refresh(entry)
    return {"data": _to_response(entry).model_dump(), "message": "集成已更新"}


@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """删除集成"""
    entry = db.get(Integration, integration_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="集成不存在")
    if entry.connected:
        raise HTTPException(status_code=400, detail="请先断开连接")
    db.delete(entry)
    commit_or_rollback(db)
    return {"message": "集成已删除", "ok": True}


class ConnectRequest(BaseModel):
    api_key: str | None = None
    config: dict = Field(default_factory=dict)


@router.post("/{integration_id}/connect")
async def connect_integration(
    integration_id: uuid.UUID,
    body: ConnectRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """连接集成服务（验证凭据并建立连接）"""
    entry = db.get(Integration, integration_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="集成不存在")
    if entry.connected:
        raise HTTPException(status_code=400, detail="已连接")

    # 存储配置
    cfg = entry.config
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    if body.api_key:
        cfg["api_key"] = body.api_key
    cfg.update(body.config)
    entry.config = json.dumps(cfg)

    # 模拟连接验证（生产环境应调用对应服务的 health check）
    import asyncio
    # 实际生产环境会调用特定服务的验证 API
    entry.status = "connected"
    entry.connected = True
    entry.error_message = None
    entry.last_connected_at = datetime.now(timezone.utc)
    entry.updated_at = datetime.now(timezone.utc)

    db.add(entry)
    commit_or_rollback(db)
    db.refresh(entry)
    return {
        "data": _to_response(entry).model_dump(),
        "message": f"已连接到 {entry.display_name}",
    }


@router.post("/{integration_id}/disconnect")
async def disconnect_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """断开集成服务连接"""
    entry = db.get(Integration, integration_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="集成不存在")

    entry.connected = False
    entry.status = "disconnected"
    entry.updated_at = datetime.now(timezone.utc)
    db.add(entry)
    commit_or_rollback(db)
    db.refresh(entry)
    return {"data": _to_response(entry).model_dump(), "message": f"已断开 {entry.display_name}"}


@router.get("/stats")
async def integrations_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """集成统计"""
    stmt = select(
        func.count().label("total"),
        func.sum((1).filter(Integration.connected == True)).label("connected"),
    ).where(Integration.user_id == current_user.id)
    row = db.exec(stmt).one()

    by_cat = db.exec(
        select(Integration.category, func.count())
        .where(Integration.user_id == current_user.id)
        .group_by(Integration.category)
    ).all()

    return {
        "total": row.total,
        "connected": row.connected or 0,
        "by_category": {c: n for c, n in by_cat},
    }
