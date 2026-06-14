"""
系统管理 API 路由

提供跨 Studio/Video 共用的系统级功能：
  - /system/models      — 全局模型管理
  - /system/health      — 系统健康检查
"""

from app.api.routes.system.models import router as models_router
from app.api.routes.system.health import router as health_router

__all__ = ["models_router", "health_router"]
