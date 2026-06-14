"""
Video — C端播放 API

提供视频播放相关功能：
  - 播放信息（文件URL + 元数据）
  - 增加观看计数
  - 字幕获取
"""

import uuid

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from app.api.deps import SessionDep
from app.models.video_models import VideoAsset

router = APIRouter(prefix="/videos", tags=["video-play"])


@router.get("/{video_id}/play")
def get_play_info(
    video_id: uuid.UUID,
    session: SessionDep,
):
    """获取视频播放信息"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if not video.is_public:
        raise HTTPException(status_code=403, detail="Video is not public")

    # 增加观看次数
    video.view_count += 1
    session.add(video)
    session.commit()

    return {
        "id": str(video.id),
        "title": video.title,
        "description": video.description,
        "file_path": video.file_path,
        "thumbnail_path": video.thumbnail_path,
        "duration": video.duration,
        "tags": video.tags,
        "view_count": video.view_count,
        "created_at": video.created_at.isoformat(),
    }


@router.get("/{video_id}/subtitles")
def get_subtitles(
    video_id: uuid.UUID,
    session: SessionDep,
    lang: str = "zh",
):
    """获取视频字幕"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # TODO: 实际字幕文件检索
    return {
        "video_id": str(video.id),
        "language": lang,
        "subtitles": [],
    }
