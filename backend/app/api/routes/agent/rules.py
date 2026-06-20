"""
Rules API — AI 行为规则管理 CRUD

端点:
- GET    /rules              — 列出所有规则（支持 scope/type 筛选 + 分页）
- GET    /rules/{id}         — 获取单条规则
- POST   /rules              — 创建规则
- PUT    /rules/{id}         — 更新规则
- DELETE /rules/{id}         — 删除规则
- POST   /rules/{id}/toggle  — 启用/禁用规则
- GET    /rules/stats        — 统计信息
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from app.api.deps import get_current_user, get_db
from app.models.system_models import Rule

router = APIRouter(prefix="/rules", tags=["Rules"])


# ── Schemas ──────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    rule_type: str = Field(default="always", pattern="^(always|requested|manual)$")
    scope: str = Field(default="project", pattern="^(project|user)$")
    content: str = Field(..., min_length=1)
    triggers: list[str] = Field(default_factory=list)
    priority: float = Field(default=0.0)


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    description: str | None = None
    rule_type: str | None = Field(default=None, pattern="^(always|requested|manual)$")
    scope: str | None = Field(default=None, pattern="^(project|user)$")
    content: str | None = None
    triggers: list[str] | None = None
    priority: float | None = None


class RuleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    rule_type: str
    scope: str
    content: str
    enabled: bool
    triggers: list[str] | None
    priority: float
    created_at: str | None
    updated_at: str | None


def _rule_to_response(r: Rule) -> RuleResponse:
    triggers = None
    if r.triggers:
        try:
            triggers = json.loads(r.triggers) if isinstance(r.triggers, str) else r.triggers
        except (json.JSONDecodeError, TypeError):
            triggers = []
    return RuleResponse(
        id=r.id,
        name=r.name,
        description=r.description,
        rule_type=r.rule_type,
        scope=r.scope,
        content=r.content,
        enabled=r.enabled,
        triggers=triggers,
        priority=r.priority,
        created_at=r.created_at.isoformat() if r.created_at else None,
        updated_at=r.updated_at.isoformat() if r.updated_at else None,
    )


# ── Endpoints ────────────────────────────────────────────

@router.get("")
async def list_rules(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    scope: str | None = Query(None),
    rule_type: str | None = Query(None, alias="type"),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """列出所有规则"""
    stmt = select(Rule).where(Rule.user_id == current_user.id)
    if scope:
        stmt = stmt.where(Rule.scope == scope)
    if rule_type:
        stmt = stmt.where(Rule.rule_type == rule_type)
    if search:
        stmt = stmt.where(
            (Rule.name.ilike(f"%{search}%")) | (Rule.description.ilike(f"%{search}%"))
        )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.exec(count_stmt).one()

    items = db.exec(
        stmt.order_by(Rule.priority.desc(), Rule.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return {
        "data": [_rule_to_response(r) for r in items],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/{rule_id}")
async def get_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> RuleResponse:
    """获取单条规则"""
    rule = db.get(Rule, rule_id)
    if not rule or rule.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="规则不存在")
    return _rule_to_response(rule)


@router.post("")
async def create_rule(
    body: RuleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """创建规则"""
    rule = Rule(
        name=body.name,
        description=body.description,
        rule_type=body.rule_type,
        scope=body.scope,
        content=body.content,
        triggers=json.dumps(body.triggers) if body.triggers else None,
        priority=body.priority,
        user_id=current_user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"data": _rule_to_response(rule).model_dump(), "message": "规则已创建"}


@router.put("/{rule_id}")
async def update_rule(
    rule_id: uuid.UUID,
    body: RuleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """更新规则"""
    from datetime import datetime, timezone

    rule = db.get(Rule, rule_id)
    if not rule or rule.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="规则不存在")

    if body.name is not None:
        rule.name = body.name
    if body.description is not None:
        rule.description = body.description
    if body.rule_type is not None:
        rule.rule_type = body.rule_type
    if body.scope is not None:
        rule.scope = body.scope
    if body.content is not None:
        rule.content = body.content
    if body.triggers is not None:
        rule.triggers = json.dumps(body.triggers)
    if body.priority is not None:
        rule.priority = body.priority

    rule.updated_at = datetime.now(timezone.utc)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"data": _rule_to_response(rule).model_dump(), "message": "规则已更新"}


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """删除规则"""
    rule = db.get(Rule, rule_id)
    if not rule or rule.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="规则不存在")
    db.delete(rule)
    db.commit()
    return {"message": "规则已删除", "ok": True}


@router.post("/{rule_id}/toggle")
async def toggle_rule(
    rule_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """启用/禁用规则"""
    from datetime import datetime, timezone

    rule = db.get(Rule, rule_id)
    if not rule or rule.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.enabled = not rule.enabled
    rule.updated_at = datetime.now(timezone.utc)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"name": rule.name, "enabled": rule.enabled}


@router.get("/stats")
async def rules_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """规则统计"""
    stmt = select(
        func.count().label("total"),
        func.sum((1).filter(Rule.enabled == True)).label("enabled"),
    ).where(Rule.user_id == current_user.id)
    row = db.exec(stmt).one()

    by_type = db.exec(
        select(Rule.rule_type, func.count())
        .where(Rule.user_id == current_user.id)
        .group_by(Rule.rule_type)
    ).all()

    by_scope = db.exec(
        select(Rule.scope, func.count())
        .where(Rule.user_id == current_user.id)
        .group_by(Rule.scope)
    ).all()

    return {
        "total": row.total,
        "enabled": row.enabled or 0,
        "by_type": {t: c for t, c in by_type},
        "by_scope": {s: c for s, c in by_scope},
    }
