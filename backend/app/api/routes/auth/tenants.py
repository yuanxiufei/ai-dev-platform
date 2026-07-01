"""
多租户管理 API — CRUD 租户、启用/禁用、配额管理

路由:
  GET    /api/v1/tenants                  — 列出所有租户 (Superuser)
  POST   /api/v1/tenants                  — 创建租户 (Superuser)
  GET    /api/v1/tenants/{id}             — 获取租户详情
  PATCH  /api/v1/tenants/{id}             — 更新租户
  DELETE /api/v1/tenants/{id}             — 删除租户 (Superuser)
  GET    /api/v1/tenants/my               — 获取当前用户所属租户
"""

import uuid

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import func, select

from app.api.deps import SessionDep, CurrentUser, commit_or_rollback
from app.models.core_models import Tenant, TenantPublic, TenantCreate, TenantUpdate, User
from app.core.config import settings

router = APIRouter(prefix="/tenants", tags=["multi-tenancy"])


def _require_multitenancy():
    if not settings.MULTI_TENANCY_ENABLED:
        raise HTTPException(status_code=501, detail="Multi-tenancy is not enabled")


def _require_superuser(user: User):
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser required")


@router.get("/my", response_model=TenantPublic)
def get_my_tenant(current_user: CurrentUser, session: SessionDep):
    """获取当前用户所属租户"""
    _require_multitenancy()
    if not current_user.tenant_id:
        raise HTTPException(status_code=404, detail="You are not assigned to any tenant")
    tenant = session.get(Tenant, current_user.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.get("/")
def list_tenants(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(False),
):
    """列出所有租户 (仅 Superuser)"""
    _require_multitenancy()
    _require_superuser(current_user)

    stmt = select(Tenant)
    if active_only:
        stmt = stmt.where(Tenant.is_active == True)
    stmt = stmt.offset(skip).limit(limit)
    tenants = session.exec(stmt).all()
    return {"data": tenants, "total": len(tenants), "skip": skip, "limit": limit}


@router.post("/", response_model=TenantPublic, status_code=201)
def create_tenant(
    tenant_in: TenantCreate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """创建新租户 (仅 Superuser)"""
    _require_multitenancy()
    _require_superuser(current_user)

    # 检查 slug 唯一性
    existing = session.exec(
        select(Tenant).where(Tenant.slug == tenant_in.slug)
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Tenant slug '{tenant_in.slug}' already exists")

    tenant = Tenant.model_validate(tenant_in)
    commit_or_rollback(session, tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantPublic)
def get_tenant(
    tenant_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """获取租户详情 (Superuser 或本租户用户)"""
    _require_multitenancy()
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    # 权限检查：superuser 或本租户用户
    if not current_user.is_superuser and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return tenant


@router.patch("/{tenant_id}", response_model=TenantPublic)
def update_tenant(
    tenant_id: uuid.UUID,
    tenant_in: TenantUpdate,
    session: SessionDep,
    current_user: CurrentUser,
):
    """更新租户配置 (仅 Superuser)"""
    _require_multitenancy()
    _require_superuser(current_user)

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    update_data = tenant_in.model_dump(exclude_unset=True)
    tenant.sqlmodel_update(update_data)
    commit_or_rollback(session, tenant)
    return tenant


@router.delete("/{tenant_id}")
def delete_tenant(
    tenant_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """删除租户及关联数据 (仅 Superuser)"""
    _require_multitenancy()
    _require_superuser(current_user)

    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # 检查是否还有用户（使用 COUNT 而非 .all() 避免全量拉取）
    user_count = session.exec(
        select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
    ).one()
    if user_count:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete tenant with {user_count} active users. Reassign or delete users first.",
        )

    session.delete(tenant)
    commit_or_rollback(session)
    return {"message": f"Tenant '{tenant.slug}' deleted"}
