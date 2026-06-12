from app.api.routes.video.admin import (
    analytics_router,
    moderation_router,
    videos_router as admin_videos_router,
)
from app.api.routes.video.client import (
    browse_router,
    generate_router,
    play_router,
)

__all__ = [
    "admin_videos_router",
    "analytics_router",
    "moderation_router",
    "browse_router",
    "play_router",
    "generate_router",
]
