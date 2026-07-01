"""
Video — 内容审核 API

提供视频内容的审核流程：
  - 审核队列（待审核列表）
  - 批准/驳回操作
  - 审核日志
"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import func, select

from app.api.deps import CurrentUser, SessionDep, commit_or_rollback
from app.models.video_models import VideoAsset

router = APIRouter(prefix="/videos/moderation", tags=["video-moderation"])


# ── Schemas ──────────────────────────────────────────────

class ModerationAction(BaseModel):
    reason: str | None = None


# ── 审核队列 ─────────────────────────────────────────────

_MAX_PAGE_SIZE = 200


@router.get("/queue")
def get_moderation_queue(
    session: SessionDep,
    user: CurrentUser,
    page: int = 1,
    size: int = 20,
):
    """获取待审核视频队列"""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser only")

    size = min(size, _MAX_PAGE_SIZE)
    if page < 1:
        page = 1

    stmt = select(VideoAsset).where(
        VideoAsset.is_approved == False
    )

    total = session.exec(
        select(func.count()).select_from(stmt.subquery())
    ).one()
    videos = session.exec(
        stmt.order_by(VideoAsset.created_at.asc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return {
        "data": [
            {
                "id": str(v.id),
                "title": v.title,
                "description": v.description,
                "file_path": v.file_path,
                "thumbnail_path": v.thumbnail_path,
                "duration": v.duration,
                "tags": v.tags,
                "owner_id": v.owner_id,
                "created_at": v.created_at.isoformat(),
            }
            for v in videos
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("/{video_id}/approve")
def approve_video(
    video_id: uuid.UUID,
    action: ModerationAction | None = None,
    session: SessionDep = None,
    user: CurrentUser = None,
):
    """批准视频"""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser only")

    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video.is_approved = True
    video.is_public = True
    session.add(video)
    commit_or_rollback(session)

    return {
        "video_id": str(video.id),
        "status": "approved",
        "reason": action.reason if action else None,
    }


@router.post("/{video_id}/reject")
def reject_video(
    video_id: uuid.UUID,
    action: ModerationAction | None = None,
    session: SessionDep = None,
    user: CurrentUser = None,
):
    """驳回视频"""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser only")

    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    video.is_approved = False
    video.is_public = False
    session.add(video)
    commit_or_rollback(session)

    return {
        "video_id": str(video.id),
        "status": "rejected",
        "reason": action.reason if action else None,
    }
