"""
会话管理 API - 专供 studio-client C端
创建/删除/整理对话会话
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/studio/sessions", tags=["studio-client"])


@router.get("/")
def list_sessions(session: SessionDep, current_user: CurrentUser):
    """会话列表 - 待实现"""
    return {"message": "sessions list ready", "sessions": []}


@router.post("/")
def create_session(session: SessionDep, current_user: CurrentUser):
    """创建新会话 - 待实现"""
    return {"message": "session created"}


@router.delete("/{session_id}")
def delete_session(session_id: str, db_session: SessionDep, current_user: CurrentUser):
    """删除会话 - 待实现"""
    return {"message": "session deleted", "session_id": session_id}
