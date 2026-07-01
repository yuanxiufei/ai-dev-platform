"""
Studio — 模板管理 API

提供项目模板的 CRUD 和使用统计：
  - 模板列表/详情（分页 + 分类筛选）
  - 模板创建/更新/删除（管理端）
  - 使用模板创建项目
"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep, commit_or_rollback
from app.models.studio_models import StudioTemplate

router = APIRouter(prefix="/studio/templates", tags=["studio-templates"])

# 分页安全上限
_MAX_PAGE_SIZE = 200


# ── Schemas ──────────────────────────────────────────────

class TemplateCreate(BaseModel):
    name: str = Field(max_length=255)
    description: str | None = None
    category: str = Field(default="other", max_length=100)
    framework: str = Field(default="vue", max_length=50)
    stack: str = Field(default="fastapi+vue", max_length=100)
    preview_url: str | None = None
    template_data: dict | None = None
    is_public: bool = True


class TemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    preview_url: str | None = None
    template_data: dict | None = None
    is_public: bool | None = None


# ── Helpers ──────────────────────────────────────────────

def _template_to_dict(t: StudioTemplate) -> dict:
    return {
        "id": t.id,
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "framework": t.framework,
        "stack": t.stack,
        "preview_url": t.preview_url,
        "usage_count": t.usage_count,
        "is_public": t.is_public,
        "created_at": t.created_at,
    }


# ── CRUD ─────────────────────────────────────────────────

@router.get("")
def list_templates(
    session: SessionDep,
    user: CurrentUser,
    page: int = 1,
    size: int = 20,
    category: str | None = None,
    framework: str | None = None,
):
    """获取模板列表"""
    size = min(size, _MAX_PAGE_SIZE)
    if page < 1:
        page = 1

    stmt = select(StudioTemplate).where(
        StudioTemplate.is_public == True
    )

    if category:
        stmt = stmt.where(StudioTemplate.category == category)
    if framework:
        stmt = stmt.where(StudioTemplate.framework == framework)

    total = session.exec(
        select(func.count()).select_from(stmt.subquery())
    ).one()
    templates = session.exec(
        stmt.order_by(StudioTemplate.usage_count.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return {
        "data": [_template_to_dict(t) for t in templates],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("", status_code=201)
def create_template(
    template_in: TemplateCreate,
    session: SessionDep,
    user: CurrentUser,
):
    """创建模板"""
    template = StudioTemplate(
        name=template_in.name,
        description=template_in.description,
        category=template_in.category,
        framework=template_in.framework,
        stack=template_in.stack,
        preview_url=template_in.preview_url,
        template_data=template_in.template_data,
        is_public=template_in.is_public,
        created_by=user.id,
    )
    commit_or_rollback(session, template)
    return _template_to_dict(template)


@router.get("/{template_id}")
def get_template(
    template_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """获取模板详情（含代码数据）"""
    template = session.get(StudioTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if not template.is_public and template.created_by != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        **_template_to_dict(template),
        "template_data": template.template_data,
    }


@router.put("/{template_id}")
def update_template(
    template_id: uuid.UUID,
    template_in: TemplateUpdate,
    session: SessionDep,
    user: CurrentUser,
):
    """更新模板"""
    template = session.get(StudioTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.created_by != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    update_data = template_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(template, key, value)

    commit_or_rollback(session, template)
    return _template_to_dict(template)


@router.delete("/{template_id}", status_code=204)
def delete_template(
    template_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """删除模板"""
    template = session.get(StudioTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    if template.created_by != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    session.delete(template)
    commit_or_rollback(session)


@router.post("/{template_id}/use")
def use_template(
    template_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """
    使用模板创建项目 — 增加使用次数并返回模板数据
    """
    from app.models.studio_models import StudioProject

    template = session.get(StudioTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # 增加使用次数
    template.usage_count += 1
    session.add(template)

    # 创建项目
    project = StudioProject(
        name=f"{template.name} Project",
        description=f"Created from template: {template.name}",
        framework=template.framework or "vue",
        stack=template.stack or "fastapi+vue",
        template_id=template.id,
        generated_code=template.template_data,
        owner_id=user.id,
    )
    commit_or_rollback(session, project)

    return {
        "project_id": project.id,
        "project_name": project.name,
        "template_name": template.name,
        "template_data": template.template_data,
    }
