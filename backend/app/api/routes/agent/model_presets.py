"""
Model Presets API — 借鉴 Open WebUI 的 Model Presets 功能

提供预设的完整 CRUD + 使用/应用
"""

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.api.deps import get_current_user, get_db
from app.models.model_presets import ModelPreset

router = APIRouter(prefix="/model-presets", tags=["model-presets"])


# ── Pydantic Schemas ────────────────────────────────────

class PresetCreate(BaseModel):
    name: str
    description: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    tools: list[str] | None = None
    force_tools: bool = False
    knowledge_bases: list[str] | None = None
    variables: dict[str, str] | None = None
    is_public: bool = False


class PresetUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    tools: list[str] | None = None
    force_tools: bool | None = None
    knowledge_bases: list[str] | None = None
    variables: dict[str, str] | None = None
    is_public: bool | None = None


class PresetResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    model_name: str | None
    system_prompt: str | None
    temperature: float | None
    max_tokens: int | None
    top_p: float | None
    tools: list[str] | None
    force_tools: bool
    knowledge_bases: list[str] | None
    variables: dict[str, str] | None
    is_public: bool
    usage_count: int
    created_at: Any
    updated_at: Any


class PaginatedResponse(BaseModel):
    data: list[PresetResponse]
    total: int
    page: int
    size: int


# ── Helper ──────────────────────────────────────────────

def _serialize_json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _deserialize_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


def _preset_to_response(p: ModelPreset) -> PresetResponse:
    return PresetResponse(
        id=p.id,
        name=p.name,
        description=p.description,
        model_name=p.model_name,
        system_prompt=p.system_prompt,
        temperature=p.temperature,
        max_tokens=p.max_tokens,
        top_p=p.top_p,
        tools=_deserialize_json(p.tools),
        force_tools=p.force_tools,
        knowledge_bases=_deserialize_json(p.knowledge_bases),
        variables=_deserialize_json(p.variables),
        is_public=p.is_public,
        usage_count=p.usage_count,
        created_at=p.created_at.isoformat() if p.created_at else None,
        updated_at=p.updated_at.isoformat() if p.updated_at else None,
    )


# ── Endpoints ───────────────────────────────────────────

@router.get("/presets", response_model=PaginatedResponse)
async def list_presets(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, description="按名称搜索"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PaginatedResponse:
    """列出预设（自己的 + 公开的）"""
    stmt = select(ModelPreset).where(
        (ModelPreset.owner_id == current_user.id) | (ModelPreset.is_public == True)
    )
    if search:
        stmt = stmt.where(ModelPreset.name.ilike(f"%{search}%"))
    
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.exec(count_stmt).one()

    presets = db.exec(stmt.order_by(ModelPreset.updated_at.desc()).offset((page - 1) * size).limit(size)).all()
    return PaginatedResponse(
        data=[_preset_to_response(p) for p in presets],
        total=total,
        page=page,
        size=size,
    )


@router.post("/presets", response_model=PresetResponse)
async def create_preset(
    body: PresetCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PresetResponse:
    """创建预设"""
    preset = ModelPreset(
        name=body.name,
        description=body.description,
        model_name=body.model_name,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        top_p=body.top_p,
        tools=_serialize_json(body.tools),
        force_tools=body.force_tools,
        knowledge_bases=_serialize_json(body.knowledge_bases),
        variables=_serialize_json(body.variables),
        is_public=body.is_public,
        owner_id=current_user.id,
    )
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return _preset_to_response(preset)


@router.get("/presets/{preset_id}", response_model=PresetResponse)
async def get_preset(
    preset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PresetResponse:
    """获取单个预设详情"""
    preset = db.get(ModelPreset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")
    if not preset.is_public and preset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问该预设")
    return _preset_to_response(preset)


@router.put("/presets/{preset_id}", response_model=PresetResponse)
async def update_preset(
    preset_id: uuid.UUID,
    body: PresetUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PresetResponse:
    """更新预设"""
    preset = db.get(ModelPreset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")
    if preset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权修改该预设")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field in ("tools", "knowledge_bases", "variables"):
            value = _serialize_json(value)
        setattr(preset, field, value)
    
    from datetime import datetime, timezone
    preset.updated_at = datetime.now(timezone.utc)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return _preset_to_response(preset)


@router.delete("/presets/{preset_id}")
async def delete_preset(
    preset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """删除预设"""
    preset = db.get(ModelPreset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")
    if preset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除该预设")
    db.delete(preset)
    db.commit()
    return {"ok": True, "message": "预设已删除"}


@router.post("/presets/{preset_id}/apply", response_model=PresetResponse)
async def apply_preset(
    preset_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PresetResponse:
    """应用预设（增加使用计数） — 借鉴 Open WebUI 的预设应用"""
    preset = db.get(ModelPreset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")
    if not preset.is_public and preset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权使用该预设")
    
    preset.usage_count += 1
    from datetime import datetime, timezone
    preset.updated_at = datetime.now(timezone.utc)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return _preset_to_response(preset)


# ── 动态变量解析 ───────────────────────────────────────

@router.post("/presets/{preset_id}/resolve")
async def resolve_preset_variables(
    preset_id: uuid.UUID,
    context: dict[str, str] | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """解析预设中的动态变量 — 借鉴 Open WebUI 的 {{ }} 语法

    内置变量:
      - {{ USER_NAME }} → 当前用户名
      - {{ CURRENT_DATE }} → 当前日期
      - {{ CURRENT_TIME }} → 当前时间
      - {{ MODEL_NAME }} → 绑定的模型名

    用户可通过 context 参数传入自定义变量。
    """
    from datetime import datetime, timezone

    preset = db.get(ModelPreset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="预设不存在")

    now = datetime.now(timezone.utc)
    vars_map: dict[str, str] = {
        "USER_NAME": getattr(current_user, "full_name", None) or getattr(current_user, "email", "User"),
        "CURRENT_DATE": now.strftime("%Y-%m-%d"),
        "CURRENT_TIME": now.strftime("%H:%M:%S"),
        "MODEL_NAME": preset.model_name or "auto",
    }
    if context:
        vars_map.update(context)

    system_prompt = preset.system_prompt or ""
    for key, val in vars_map.items():
        system_prompt = system_prompt.replace(f"{{{{ {key} }}}}", str(val))
        system_prompt = system_prompt.replace(f"{{{{{key}}}}}", str(val))

    tools = _deserialize_json(preset.tools) or []
    kb_list = _deserialize_json(preset.knowledge_bases) or []

    return {
        "preset_id": str(preset.id),
        "model_name": preset.model_name,
        "system_prompt": system_prompt,
        "temperature": preset.temperature,
        "max_tokens": preset.max_tokens,
        "tools": tools,
        "knowledge_bases": kb_list,
        "force_tools": preset.force_tools,
        "resolved_variables": vars_map,
    }
