from app.api.routes.studio.admin.projects import router as projects_router, static_deploy_router
from app.api.routes.studio.admin.templates import router as templates_router

__all__ = ["projects_router", "templates_router", "static_deploy_router"]
