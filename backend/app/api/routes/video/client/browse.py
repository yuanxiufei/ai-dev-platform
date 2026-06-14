"""
Video — C端浏览 API

提供面向用户的视频浏览功能：
  - 视频列表（仅公开视频）
  - 搜索
  - 按标签筛选
"""

from fastapi import APIRouter, Query
from sqlmodel import select, func

from app.api.deps import SessionDep
from app.models.video_models import VideoAsset

router = APIRouter(prefix="/videos", tags=["video-browse"])


@router.get("/browse")
def browse_videos(
    session: SessionDep,
    page: int = 1,
    size: int = 20,
    tag: str | None = None,
    sort: str = "newest",
):
    """
    浏览公开视频（C端用户）

    排序方式：
    - newest: 最新发布
    - popular: 最多观看
    """
    stmt = select(VideoAsset).where(
        VideoAsset.is_public == True,
        VideoAsset.is_approved == True,
    )

    if tag:
        # 按标签筛选（JSON 字段模糊匹配）
        stmt = stmt.where(
            func.cast(VideoAsset.tags, type_=VideoAsset.tags).like(f"%{tag}%")
        )

    # 排序
    if sort == "popular":
        stmt = stmt.order_by(VideoAsset.view_count.desc())
    else:
        stmt = stmt.order_by(VideoAsset.created_at.desc())

    total = len(session.exec(stmt).all())
    videos = session.exec(
        stmt.offset((page - 1) * size).limit(size)
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
                "view_count": v.view_count,
                "created_at": v.created_at.isoformat(),
            }
            for v in videos
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/search")
def search_videos(
    session: SessionDep,
    q: str = Query(..., min_length=1, max_length=200),
    page: int = 1,
    size: int = 20,
):
    """搜索视频（标题+描述模糊匹配）"""
    stmt = select(VideoAsset).where(
        VideoAsset.is_public == True,
        VideoAsset.is_approved == True,
        (VideoAsset.title.ilike(f"%{q}%")
         | func.coalesce(VideoAsset.description, "").ilike(f"%{q}%")),
    )

    total = len(session.exec(stmt).all())
    videos = session.exec(
        stmt.order_by(VideoAsset.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return {
        "data": [
            {
                "id": str(v.id),
                "title": v.title,
                "description": v.description,
                "thumbnail_path": v.thumbnail_path,
                "duration": v.duration,
                "view_count": v.view_count,
            }
            for v in videos
        ],
        "total": total,
        "page": page,
        "size": size,
        "query": q,
    }
