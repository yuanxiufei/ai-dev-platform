"""
Video — 管理端 API

提供管理后台的视频 CRUD 操作：
  - 视频列表（分页+筛选）
  - 创建/更新/删除
  - 批量操作
"""

import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models.video_models import VideoAsset, VideoTask

router = APIRouter(prefix="/videos", tags=["video-admin"])


# ── Schemas ──────────────────────────────────────────────

class VideoCreate(BaseModel):
    title: str = Field(max_length=255)
    description: str | None = None
    file_path: str
    thumbnail_path: str | None = None
    duration: float | None = None
    tags: list[str] | None = None
    is_public: bool = True
    is_approved: bool = False
    task_id: uuid.UUID | None = None

class VideoUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    is_public: bool | None = None
    is_approved: bool | None = None


# ── Helpers ──────────────────────────────────────────────

def _video_to_dict(v: VideoAsset) -> dict:
    return {
        "id": v.id,
        "title": v.title,
        "description": v.description,
        "task_id": v.task_id,
        "file_path": v.file_path,
        "thumbnail_path": v.thumbnail_path,
        "duration": v.duration,
        "tags": v.tags,
        "view_count": v.view_count,
        "is_public": v.is_public,
        "is_approved": v.is_approved,
        "owner_id": v.owner_id,
        "created_at": v.created_at,
    }


# ── CRUD ─────────────────────────────────────────────────

@router.get("")
def list_videos(
    session: SessionDep,
    user: CurrentUser,
    page: int = 1,
    size: int = 20,
    is_approved: bool | None = None,
    is_public: bool | None = None,
):
    """获取视频列表（管理端所有视频）"""
    stmt = select(VideoAsset)

    if not user.is_superuser:
        stmt = stmt.where(VideoAsset.owner_id == user.id)

    if is_approved is not None:
        stmt = stmt.where(VideoAsset.is_approved == is_approved)
    if is_public is not None:
        stmt = stmt.where(VideoAsset.is_public == is_public)

    total = len(session.exec(stmt).all())
    videos = session.exec(
        stmt.order_by(VideoAsset.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return {
        "data": [_video_to_dict(v) for v in videos],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("", status_code=201)
def create_video(
    video_in: VideoCreate,
    session: SessionDep,
    user: CurrentUser,
):
    """创建视频记录"""
    video = VideoAsset(
        title=video_in.title,
        description=video_in.description,
        file_path=video_in.file_path,
        thumbnail_path=video_in.thumbnail_path,
        duration=video_in.duration,
        tags=video_in.tags,
        is_public=video_in.is_public,
        is_approved=video_in.is_approved,
        task_id=video_in.task_id,
        owner_id=user.id,
    )
    session.add(video)
    session.commit()
    session.refresh(video)
    return _video_to_dict(video)


@router.get("/{video_id}")
def get_video(
    video_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """获取视频详情"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.owner_id != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    return _video_to_dict(video)


@router.put("/{video_id}")
def update_video(
    video_id: uuid.UUID,
    video_in: VideoUpdate,
    session: SessionDep,
    user: CurrentUser,
):
    """更新视频信息"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.owner_id != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    update_data = video_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(video, key, value)

    session.add(video)
    session.commit()
    session.refresh(video)
    return _video_to_dict(video)


@router.delete("/{video_id}", status_code=204)
def delete_video(
    video_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """删除视频"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.owner_id != user.id and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    session.delete(video)
    session.commit()
