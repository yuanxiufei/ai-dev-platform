"""
Studio — 会话管理 API

管理 AI 对话会话的生命周期：
  - 会话列表（分页）
  - 创建/重命名/删除会话
  - 关联项目
"""

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models.studio_models import ChatSession, ChatMessage

router = APIRouter(prefix="/studio/sessions", tags=["studio-sessions"])


# ── Schemas ──────────────────────────────────────────────

class SessionCreate(BaseModel):
    title: str = Field(default="New Chat", max_length=255)
    model_name: str | None = None
    project_id: uuid.UUID | None = None

class SessionUpdate(BaseModel):
    title: str | None = None
    model_name: str | None = None


# ── CRUD ─────────────────────────────────────────────────

@router.get("")
def list_sessions(
    session: SessionDep,
    user: CurrentUser,
    page: int = 1,
    size: int = 20,
    project_id: uuid.UUID | None = None,
):
    """获取会话列表"""
    stmt = select(ChatSession).where(
        ChatSession.owner_id == user.id
    )

    if project_id:
        stmt = stmt.where(ChatSession.project_id == project_id)

    total = len(session.exec(stmt).all())
    sessions = session.exec(
        stmt.order_by(ChatSession.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return {
        "data": [
            {
                "id": str(s.id),
                "title": s.title,
                "model_name": s.model_name,
                "project_id": str(s.project_id) if s.project_id else None,
                "message_count": len(s.messages) if s.messages else 0,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in sessions
        ],
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("", status_code=201)
def create_session(
    session_in: SessionCreate,
    session: SessionDep,
    user: CurrentUser,
):
    """创建新会话"""
    chat_session = ChatSession(
        title=session_in.title,
        model_name=session_in.model_name,
        project_id=session_in.project_id,
        owner_id=user.id,
    )
    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)

    return {
        "id": str(chat_session.id),
        "title": chat_session.title,
        "model_name": chat_session.model_name,
        "project_id": str(chat_session.project_id) if chat_session.project_id else None,
        "created_at": chat_session.created_at.isoformat(),
    }


@router.get("/{session_id}")
def get_session(
    session_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """获取会话详情"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if chat_session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "id": str(chat_session.id),
        "title": chat_session.title,
        "model_name": chat_session.model_name,
        "project_id": str(chat_session.project_id) if chat_session.project_id else None,
        "message_count": len(chat_session.messages) if chat_session.messages else 0,
        "created_at": chat_session.created_at.isoformat(),
        "updated_at": chat_session.updated_at.isoformat(),
    }


@router.put("/{session_id}")
def update_session(
    session_id: uuid.UUID,
    session_in: SessionUpdate,
    session: SessionDep,
    user: CurrentUser,
):
    """重命名会话"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if chat_session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    if session_in.title is not None:
        chat_session.title = session_in.title
    if session_in.model_name is not None:
        chat_session.model_name = session_in.model_name

    session.add(chat_session)
    session.commit()
    session.refresh(chat_session)

    return {
        "id": str(chat_session.id),
        "title": chat_session.title,
        "model_name": chat_session.model_name,
    }


@router.delete("/{session_id}", status_code=204)
def delete_session(
    session_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """删除会话（级联删除消息）"""
    chat_session = session.get(ChatSession, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found")
    if chat_session.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    session.delete(chat_session)
    session.commit()
