"""
AI 对话 API - 专供 studio-client C端
流式对话、消息历史
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/studio/chat", tags=["studio-client"])


@router.post("/")
def send_message(session: SessionDep, current_user: CurrentUser):
    """发送消息 - 待实现"""
    return {"message": "chat send ready"}


@router.get("/{session_id}")
def get_messages(session_id: str, db_session: SessionDep, current_user: CurrentUser):
    """获取会话消息历史 - 待实现"""
    return {"message": "chat history ready", "session_id": session_id}
