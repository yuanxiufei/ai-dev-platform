"""
ApiAuthMiddleware — 远程 API Key 鉴权

提供类似 API Key 的鉴权接口，允许外部公司直接远程调用本机的后端、模型及知识库 Agent 能力。

特性：
- 支持多种密钥传递方式：Authorization Bearer / X-API-Key Header / 查询参数
- 基于现有 ApiKeyManager 的密钥管理
- 可配置白名单路径（无需鉴权的端点）
- 请求速率追踪与用量统计
- 租户隔离（通过 API Key 关联命名空间）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("standalone.api_auth")


@dataclass
class ApiAuthConfig:
    """API 鉴权配置"""

    # 是否启用鉴权
    enabled: bool = True

    # 允许的 API Key 来源
    allow_header_bearer: bool = True      # Authorization: Bearer <key>
    allow_header_x_api_key: bool = True   # X-API-Key: <key>
    allow_query_param: bool = False       # ?api_key=<key>

    # 查询参数中的 key 名称
    query_param_name: str = "api_key"

    # 白名单路径（支持前缀匹配）
    whitelist_paths: list[str] = field(default_factory=lambda: [
        "/api/v1/utils/health-check/",
        "/api/v1/system/health",
        "/docs",
        "/openapi.json",
        "/metrics",
        "/standalone",  # standalone 管理接口自己处理鉴权
    ])

    # 是否在鉴权失败时返回 401（否则仅记录日志）
    reject_on_failure: bool = True

    # 密钥缓存时间（秒）
    key_cache_ttl: float = 60.0

    # 自定义鉴权回调：参数 (request, api_key) -> bool
    custom_validator: Optional[Callable] = None

    # 遥测回调
    on_auth_success: Optional[Callable[[Request, str], None]] = None
    on_auth_failure: Optional[Callable[[Request, str], None]] = None


class RemoteApiKeyManager:
    """扩展的 API Key 管理器 — 支持租户、配额和远程管理。

    在核心 auth.ApiKeyManager 基础上增加：
    - 租户命名空间隔离
    - 请求配额追踪
    - 速率限制
    - 密钥元数据
    """

    def __init__(self) -> None:
        from app.core.auth.api_key import ApiKeyManager
        self._inner = ApiKeyManager()
        self._key_meta: dict[str, dict] = {}  # hashed_key → {tenant, quota, roles, ...}
        self._request_counts: dict[str, dict] = {}  # hashed_key → {window_start, count}

    def create_remote_key(
        self,
        tenant: str = "default",
        name: str = "",
        roles: list[str] | None = None,
        quota_per_hour: int = 0,
        metadata: dict | None = None,
    ) -> dict:
        """创建一个远程调用的 API Key。

        Args:
            tenant: 租户标识
            name: 密钥名称
            roles: 授予的角色（如 ["studio.chat", "video.generate", "rag.query"]）
            quota_per_hour: 每小时请求配额（0=不限）
            metadata: 自定义元数据

        Returns:
            Dict with full_key, access_key_prefix, tenant, roles, etc.
        """
        result = self._inner.create_key(name=name or f"remote-{tenant}")
        hashed = result["hashed_key"]

        self._key_meta[hashed] = {
            "tenant": tenant,
            "name": name or f"remote-{tenant}",
            "roles": roles or ["*"],  # * = 全部权限
            "quota_per_hour": quota_per_hour,
            "metadata": metadata or {},
            "created_at": time.time(),
        }

        return {
            **result,
            "tenant": tenant,
            "roles": roles or ["*"],
            "quota_per_hour": quota_per_hour,
        }

    def verify(self, key: str) -> Optional[dict]:
        """验证 API Key 并返回完整信息（含租户、角色等）"""
        record = self._inner.verify(key)
        if record is None:
            return None

        # 查找扩展元数据
        hashed = record.get("hashed_key", "")
        meta_from_key = None
        for h, meta in self._key_meta.items():
            if self._inner.verify(key):
                meta_from_key = meta
                break

        return {
            **record,
            "tenant": meta_from_key.get("tenant", "default") if meta_from_key else "default",
            "roles": meta_from_key.get("roles", ["*"]) if meta_from_key else ["*"],
            "quota_per_hour": meta_from_key.get("quota_per_hour", 0) if meta_from_key else 0,
        }

    def check_quota(self, hashed_key: str, quota_per_hour: int) -> bool:
        """检查请求配额"""
        if quota_per_hour <= 0:
            return True

        now = time.time()
        window_start = now - 3600  # 1 小时窗口

        if hashed_key not in self._request_counts:
            self._request_counts[hashed_key] = {"window_start": now, "count": 0}

        entry = self._request_counts[hashed_key]
        if entry["window_start"] < window_start:
            # 新窗口
            entry["window_start"] = now
            entry["count"] = 0

        if entry["count"] >= quota_per_hour:
            return False

        entry["count"] += 1
        return True

    def list_keys(self) -> list[dict]:
        """列出所有远程 API Key（含租户信息）"""
        keys = self._inner.list_keys()
        result = []
        for k in keys:
            # 匹配元数据
            meta = None
            for h, m in self._key_meta.items():
                if m.get("name") == k.get("name"):
                    meta = m
                    break
            result.append({
                **k,
                "tenant": meta.get("tenant", "default") if meta else "default",
                "roles": meta.get("roles", ["*"]) if meta else ["*"],
                "quota_per_hour": meta.get("quota_per_hour", 0) if meta else 0,
            })
        return result

    def revoke_key(self, hashed_key: str) -> bool:
        """撤销密钥"""
        self._key_meta.pop(hashed_key, None)
        self._request_counts.pop(hashed_key, None)
        return self._inner.revoke(hashed_key)

    def count(self) -> int:
        return self._inner.count()


# ── FastAPI 中间件 ──────────────────────────────────


class ApiAuthMiddleware(BaseHTTPMiddleware):
    """API Key 鉴权中间件 — 拦截所有请求并验证 API Key。

    使用方式：
        ```python
        app.add_middleware(
            ApiAuthMiddleware,
            config=ApiAuthConfig(enabled=True),
        )
        ```
    """

    def __init__(self, app, config: ApiAuthConfig | None = None) -> None:
        super().__init__(app)
        self.config = config or ApiAuthConfig()
        self._manager: Optional[RemoteApiKeyManager] = None

    @property
    def key_manager(self) -> RemoteApiKeyManager:
        if self._manager is None:
            self._manager = RemoteApiKeyManager()
        return self._manager

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.config.enabled:
            return await call_next(request)

        # 白名单路径检查
        if self._is_whitelisted(request.url.path):
            return await call_next(request)

        # OPTIONS 预检请求放行
        if request.method == "OPTIONS":
            return await call_next(request)

        # 提取 API Key
        api_key = self._extract_api_key(request)

        if not api_key:
            if self.config.reject_on_failure:
                return self._unauthorized("Missing API key. Provide via Authorization: Bearer <key> or X-API-Key header.")
            logger.warning("Request without API key: %s %s", request.method, request.url.path)
            return await call_next(request)

        # 验证 API Key
        key_info = self.key_manager.verify(api_key)
        if key_info is None:
            if self.config.on_auth_failure:
                try:
                    self.config.on_auth_failure(request, api_key)
                except Exception:
                    pass
            if self.config.reject_on_failure:
                return self._unauthorized("Invalid API key.")
            return await call_next(request)

        # 配额检查
        hashed = key_info.get("hashed_key", "")
        quota = key_info.get("quota_per_hour", 0)
        if not self.key_manager.check_quota(hashed, quota):
            return JSONResponse(
                status_code=429,
                content={"detail": "API key quota exceeded. Try again later."},
            )

        # 注入认证信息到 request.state
        request.state.api_key_info = key_info
        request.state.tenant = key_info.get("tenant", "default")
        request.state.roles = key_info.get("roles", ["*"])

        if self.config.on_auth_success:
            try:
                self.config.on_auth_success(request, api_key)
            except Exception:
                pass

        logger.debug(
            "API auth success: tenant=%s, roles=%s, path=%s",
            request.state.tenant, request.state.roles, request.url.path,
        )
        return await call_next(request)

    def _extract_api_key(self, request: Request) -> Optional[str]:
        """从请求中提取 API Key"""
        # 方式 1: Authorization: Bearer <key>
        if self.config.allow_header_bearer:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                return auth_header[7:].strip()

        # 方式 2: X-API-Key: <key>
        if self.config.allow_header_x_api_key:
            key = request.headers.get("X-API-Key", "")
            if key:
                return key.strip()

        # 方式 3: 查询参数 ?api_key=<key>
        if self.config.allow_query_param:
            key = request.query_params.get(self.config.query_param_name, "")
            if key:
                return key.strip()

        return None

    def _is_whitelisted(self, path: str) -> bool:
        """检查路径是否在白名单中"""
        for pattern in self.config.whitelist_paths:
            if path.startswith(pattern) or path == pattern:
                return True
        return False

    def _unauthorized(self, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": detail},
        )


# ── 装饰器 ──────────────────────────────────────────


def require_api_key(roles: list[str] | None = None):
    """路由级别的 API Key 鉴权装饰器。

    使用方式：
        ```python
        @router.post("/agent/chat")
        @require_api_key(roles=["agent.chat"])
        async def agent_chat(request: Request, ...):
            tenant = request.state.tenant  # 可用
        ```
    """
    roles = roles or ["*"]

    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            key_info = getattr(request.state, "api_key_info", None)
            if key_info is None:
                raise HTTPException(status_code=401, detail="API key required")

            user_roles = key_info.get("roles", [])
            if "*" not in roles and "*" not in user_roles:
                if not any(r in user_roles for r in roles):
                    raise HTTPException(
                        status_code=403,
                        detail=f"Insufficient permissions. Required roles: {roles}",
                    )
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator


# ── 全局单例 ────────────────────────────────────────

_remote_key_manager: Optional[RemoteApiKeyManager] = None


def init_remote_key_manager() -> RemoteApiKeyManager:
    global _remote_key_manager
    if _remote_key_manager is None:
        _remote_key_manager = RemoteApiKeyManager()
    return _remote_key_manager


def get_remote_key_manager() -> Optional[RemoteApiKeyManager]:
    return _remote_key_manager
