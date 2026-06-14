from fastapi import APIRouter

from app.api.routes.auth.login import router as login_router
from app.api.routes.auth.users import router as users_router
from app.api.routes.common.utils import router as utils_router
from app.api.routes.video import (
    admin_videos_router,
    analytics_router,
    browse_router,
    generate_router,
    moderation_router,
    play_router,
)
from app.api.routes.studio import (
    chat_router,
    models_router,
    projects_router,
    sessions_router,
    templates_router,
)
from app.api.routes.system import models_router as system_models_router
from app.api.routes.system import health_router as system_health_router
from app.api.routes import items, private
from app.core.config import settings

api_router = APIRouter()

# ===== 所有前端共享 =====
api_router.include_router(login_router)       # POST /login/access-token
api_router.include_router(users_router)       # CRUD /users
api_router.include_router(utils_router)       # GET /health-check/

# ===== 系统管理 API =====
api_router.include_router(system_models_router)  # /system/models — 全局模型管理
api_router.include_router(system_health_router)  # /system/health — 系统健康检查

# ===== video-admin 后台 =====
api_router.include_router(items.router)        # 模板占位，后续替换
api_router.include_router(admin_videos_router) # /videos CRUD
api_router.include_router(analytics_router)    # /videos/analytics
api_router.include_router(moderation_router)   # /videos/moderation

# ===== video-client C端 =====
api_router.include_router(browse_router)       # /videos/browse, /videos/search
api_router.include_router(play_router)         # /videos/{id}/play
api_router.include_router(generate_router)     # /videos/generate

# ===== studio-admin 管理端 (Vue) =====
api_router.include_router(projects_router)     # /studio/projects CRUD
api_router.include_router(templates_router)    # /studio/templates

# ===== studio-client C端 =====
api_router.include_router(chat_router)         # /studio/chat
api_router.include_router(sessions_router)     # /studio/sessions
api_router.include_router(models_router)       # /studio/models

# ===== local 专用 =====
if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
