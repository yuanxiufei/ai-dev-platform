"""
视频浏览 API - 专供 video-client C端
公开浏览、搜索、推荐
"""

from fastapi import APIRouter

from app.api.deps import SessionDep

router = APIRouter(prefix="/videos", tags=["videos-client"])


@router.get("/browse")
def browse_videos(session: SessionDep):
    """视频广场 - 待实现"""
    return {"message": "client browse ready", "data": []}


@router.get("/search")
def search_videos(q: str = "", session: SessionDep = None):
    """搜索视频 - 待实现"""
    return {"message": "client search ready", "query": q, "data": []}
