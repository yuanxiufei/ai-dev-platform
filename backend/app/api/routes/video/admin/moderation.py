"""
视频审核 API - 专供 video-admin 后台系统
审核通过/驳回、内容安全检查
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/videos/moderation", tags=["videos-moderation"])


@router.get("/queue")
def moderation_queue(session: SessionDep, current_user: CurrentUser):
    """待审核队列 - 待实现"""
    return {"message": "moderation queue ready", "data": []}


@router.post("/{video_id}/approve")
def approve_video(video_id: str, session: SessionDep, current_user: CurrentUser):
    """审核通过 - 待实现"""
    return {"message": "video approved", "video_id": video_id}


@router.post("/{video_id}/reject")
def reject_video(video_id: str, session: SessionDep, current_user: CurrentUser):
    """审核驳回 - 待实现"""
    return {"message": "video rejected", "video_id": video_id}
