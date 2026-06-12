"""
视频统计 API - 专供 video-admin 后台系统
播放量、用户数据、趋势分析
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/videos/analytics", tags=["videos-analytics"])


@router.get("/overview")
def analytics_overview(session: SessionDep, current_user: CurrentUser):
    """数据概览 - 待实现"""
    return {"message": "analytics overview ready", "data": {}}


@router.get("/{video_id}")
def video_analytics(video_id: str, session: SessionDep, current_user: CurrentUser):
    """单个视频分析 - 待实现"""
    return {"message": "video analytics ready", "video_id": video_id}
