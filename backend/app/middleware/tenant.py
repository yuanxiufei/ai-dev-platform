"""
多租户中间件 — 请求级租户隔离

工作原理：
1. 从请求 Header `X-Tenant-ID` 或 JWT token 中提取 tenant_id
2. 注入到 request.state.tenant_id 供下游路由使用
3. 启用时自动过滤/scoped所有数据查询

配置: settings.MULTI_TENANCY_ENABLED=True 时生效
"""

from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.db import engine
from app.models.core_models import Tenant
from sqlmodel import Session, select


# 跳过租户检查的公开路由前缀
_TENANT_FREE_PREFIXES = (
    "/api/v1/login",
    "/api/v1/health-check",
    "/api/v1/tenants",
    "/api/v1/docs",
    "/api/v1/openapi.json",
)


class TenantMiddleware(BaseHTTPMiddleware):
    """请求级租户解析中间件

    从 X-Tenant-ID header 解析租户，注入 request.state.tenant_id。
    启用 MULTI_TENANCY_ENABLED 后自动注册。
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 公共路由直接放行
        path = request.url.path
        if any(path.startswith(p) for p in _TENANT_FREE_PREFIXES):
            request.state.tenant_id = None
            return await call_next(request)

        tenant_id = self._resolve_tenant_id(request)

        if tenant_id:
            # 验证租户存在且活跃
            if not self._validate_tenant(tenant_id):
                return JSONResponse(
                    status_code=404,
                    content={"detail": f"Tenant {tenant_id} not found or inactive"},
                )
            request.state.tenant_id = tenant_id
        else:
            request.state.tenant_id = None

        return await call_next(request)

    def _resolve_tenant_id(self, request: Request) -> uuid.UUID | None:
        """从请求中解析 tenant_id"""
        # 方式 1: Header
        header_val = request.headers.get("X-Tenant-ID")
        if header_val:
            try:
                return uuid.UUID(header_val)
            except ValueError:
                pass

        # 方式 2: 从已认证用户的 token 中获取 (由 deps 注入)
        # tenant_id 会在下游 deps.py 中通过 get_current_user 从 DB 取到
        return None

    def _validate_tenant(self, tenant_id: uuid.UUID) -> bool:
        """验证租户是否有效"""
        try:
            with Session(engine) as session:
                tenant = session.get(Tenant, tenant_id)
                return tenant is not None and tenant.is_active
        except Exception:
            return False


def get_tenant_id(request: Request) -> uuid.UUID | None:
    """便捷函数：从 request.state 获取当前租户 ID"""
    return getattr(request.state, "tenant_id", None)
