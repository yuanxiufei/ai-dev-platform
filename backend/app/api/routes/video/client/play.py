"""
视频播放 API - 专供 video-client C端
获取播放地址、字幕、清晰度切换
"""

from fastapi import APIRouter

from app.api.deps import SessionDep

router = APIRouter(prefix="/videos", tags=["videos-play"])


@router.get("/{video_id}/play")
def play_video(video_id: str, session: SessionDep):
    """播放视频（获取流地址）- 待实现"""
    return {"message": "video play ready", "video_id": video_id}


@router.get("/{video_id}/subtitles")
def get_subtitles(video_id: str, session: SessionDep):
    """获取字幕 - 待实现"""
    return {"message": "subtitles ready", "video_id": video_id}
