"""
视频管理 API - 专供 video-admin 后台系统
视频 CRUD 操作
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/videos", tags=["videos-admin"])


@router.get("/")
def list_videos(session: SessionDep, current_user: CurrentUser):
    """管理端视频列表 - 待实现"""
    return {"message": "admin videos list ready", "data": []}


@router.get("/{video_id}")
def get_video(video_id: str, session: SessionDep, current_user: CurrentUser):
    """管理端视频详情 - 待实现"""
    return {"message": "admin video detail ready", "video_id": video_id}


@router.post("/")
def create_video(session: SessionDep, current_user: CurrentUser):
    """创建视频 - 待实现"""
    return {"message": "admin create video ready"}


@router.put("/{video_id}")
def update_video(video_id: str, session: SessionDep, current_user: CurrentUser):
    """更新视频 - 待实现"""
    return {"message": "admin update video ready", "video_id": video_id}


@router.delete("/{video_id}")
def delete_video(video_id: str, session: SessionDep, current_user: CurrentUser):
    """删除视频 - 待实现"""
    return {"message": "admin delete video ready", "video_id": video_id}
