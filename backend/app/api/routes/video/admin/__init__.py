from app.api.routes.video.admin.videos import router as videos_router
from app.api.routes.video.admin.analytics import router as analytics_router
from app.api.routes.video.admin.moderation import router as moderation_router

__all__ = ["videos_router", "analytics_router", "moderation_router"]
