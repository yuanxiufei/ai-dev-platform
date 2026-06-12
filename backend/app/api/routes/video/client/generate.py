"""
视频生成 API - 专供 video-client C端
AI 生成视频、任务状态查询
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/videos", tags=["videos-generate"])


@router.post("/generate")
def generate_video(session: SessionDep, current_user: CurrentUser):
    """提交 AI 视频生成任务 - 待实现"""
    return {"message": "generate task submitted"}


@router.get("/generate/{task_id}")
def generate_status(task_id: str, session: SessionDep, current_user: CurrentUser):
    """查询生成任务状态 - 待实现"""
    return {"message": "generate task status", "task_id": task_id}
