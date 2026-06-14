"""
Video — 数据分析 API

提供视频平台的数据分析：
  - 整体数据概览
  - 单个视频分析
  - 趋势报表
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select, func

from app.api.deps import CurrentUser, SessionDep
from app.models.video_models import VideoAsset, VideoTask

router = APIRouter(prefix="/videos/analytics", tags=["video-analytics"])


@router.get("/overview")
def get_overview(
    session: SessionDep,
    user: CurrentUser,
):
    """获取整体数据概览"""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser only")

    # 视频总数
    total_videos = session.exec(
        select(func.count(VideoAsset.id))
    ).one()

    # 公开视频数
    public_videos = session.exec(
        select(func.count(VideoAsset.id)).where(VideoAsset.is_public == True)
    ).one()

    # 总播放次数
    total_views = session.exec(
        select(func.coalesce(func.sum(VideoAsset.view_count), 0))
    ).one()

    # 任务统计
    total_tasks = session.exec(
        select(func.count(VideoTask.id))
    ).one()

    completed_tasks = session.exec(
        select(func.count(VideoTask.id)).where(VideoTask.status == "completed")
    ).one()

    failed_tasks = session.exec(
        select(func.count(VideoTask.id)).where(VideoTask.status == "failed")
    ).one()

    # 今日数据
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_videos = session.exec(
        select(func.count(VideoAsset.id)).where(VideoAsset.created_at >= today)
    ).one()

    today_tasks = session.exec(
        select(func.count(VideoTask.id)).where(VideoTask.created_at >= today)
    ).one()

    return {
        "videos": {
            "total": total_videos,
            "public": public_videos,
            "total_views": total_views,
            "today_new": today_videos,
        },
        "tasks": {
            "total": total_tasks,
            "completed": completed_tasks,
            "failed": failed_tasks,
            "today_new": today_tasks,
            "success_rate": (
                completed_tasks / total_tasks if total_tasks > 0 else 0
            ),
        },
    }


@router.get("/{video_id}")
def get_video_analytics(
    video_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """获取单个视频的详细分析"""
    video = session.get(VideoAsset, video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # 关联任务
    task = None
    if video.task_id:
        task = session.get(VideoTask, video.task_id)

    return {
        "video_id": str(video.id),
        "title": video.title,
        "view_count": video.view_count,
        "duration": video.duration,
        "is_public": video.is_public,
        "is_approved": video.is_approved,
        "created_at": video.created_at.isoformat(),
        "task": {
            "id": str(task.id),
            "status": task.status.value if task else None,
            "model_name": task.model_name if task else None,
            "progress": task.progress if task else None,
        } if task else None,
    }


@router.get("/trends/daily")
def get_daily_trends(
    session: SessionDep,
    user: CurrentUser,
    days: int = 7,
):
    """获取每日趋势数据"""
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Superuser only")

    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    trends = []

    for i in range(days):
        day_start = start_date + timedelta(days=i)
        day_end = day_start + timedelta(days=1)

        videos_count = session.exec(
            select(func.count(VideoAsset.id)).where(
                VideoAsset.created_at >= day_start,
                VideoAsset.created_at < day_end,
            )
        ).one()

        tasks_count = session.exec(
            select(func.count(VideoTask.id)).where(
                VideoTask.created_at >= day_start,
                VideoTask.created_at < day_end,
            )
        ).one()

        views_count = session.exec(
            select(func.coalesce(func.sum(VideoAsset.view_count), 0)).where(
                VideoAsset.created_at >= day_start,
                VideoAsset.created_at < day_end,
            )
        ).one()

        trends.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "new_videos": videos_count,
            "new_tasks": tasks_count,
            "views": views_count,
        })

    return {"trends": trends, "days": days}
