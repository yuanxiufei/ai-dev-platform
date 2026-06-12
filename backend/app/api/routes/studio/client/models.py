"""
模型管理 API - 专供 studio-client C端（admin 也复用）
可用模型列表、模型切换
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser

router = APIRouter(prefix="/studio/models", tags=["studio-client"])


@router.get("/")
def list_models(current_user: CurrentUser):
    """可用模型列表 - 待实现"""
    return {"message": "models list ready", "models": []}
