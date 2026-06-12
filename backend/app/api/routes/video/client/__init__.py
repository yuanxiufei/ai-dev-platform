from app.api.routes.video.client.browse import router as browse_router
from app.api.routes.video.client.play import router as play_router
from app.api.routes.video.client.generate import router as generate_router

__all__ = ["browse_router", "play_router", "generate_router"]
