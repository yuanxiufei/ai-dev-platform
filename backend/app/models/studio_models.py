"""
Studio 域数据模型

StudioProject  —  AI 编程项目（截图→代码 / 文本→全栈项目）
StudioTemplate —  项目模板市场
ChatSession    —  AI 对话会话
ChatMessage    —  对话消息（user / assistant / system / tool）
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Text
from sqlmodel import Column, Field, Relationship, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ───────────────────────────────────────────────

class ProjectStatus(str, Enum):
    DRAFT = "draft"
    BUILDING = "building"
    DEPLOYING = "deploying"
    RUNNING = "running"
    FAILED = "failed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


# ── StudioProject ───────────────────────────────────────

class StudioProject(SQLModel, table=True):
    __tablename__ = "studio_projects"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    status: ProjectStatus = Field(default=ProjectStatus.DRAFT)

    # 技术栈
    framework: str | None = Field(default=None, max_length=50)  # vue | react | html
    stack: str | None = Field(default=None, max_length=100)     # fastapi+vue | django+react

    # 模板关联
    template_id: uuid.UUID | None = Field(default=None, foreign_key="studio_templates.id")

    # 生成结果
    generated_code: dict | None = Field(default=None, sa_column=Column("generated_code", Text))
    build_log: str | None = Field(default=None, sa_column=Column("build_log", Text))
    deploy_url: str | None = Field(default=None, max_length=500)

    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── StudioTemplate ──────────────────────────────────────

class StudioTemplate(SQLModel, table=True):
    __tablename__ = "studio_templates"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=100)  # landing-page | dashboard | api-service

    framework: str | None = Field(default=None, max_length=50)
    stack: str | None = Field(default=None, max_length=100)
    preview_url: str | None = Field(default=None, max_length=500)
    template_data: dict | None = Field(default=None, sa_column=Column("template_data", Text))

    usage_count: int = Field(default=0)
    is_public: bool = Field(default=True)

    created_by: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))

    # 关联
    projects: list[StudioProject] = Relationship()


# ── ChatSession ─────────────────────────────────────────

class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(default="New Chat", max_length=255)
    model_name: str | None = Field(default=None, max_length=100)

    project_id: uuid.UUID | None = Field(default=None, foreign_key="studio_projects.id", nullable=True)

    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))

    messages: list["ChatMessage"] = Relationship(back_populates="session", cascade_delete=True)


# ── ChatMessage ─────────────────────────────────────────

class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    session_id: uuid.UUID = Field(foreign_key="chat_sessions.id", nullable=False, ondelete="CASCADE")
    role: MessageRole
    content: str = Field(sa_column=Column("content", Text))

    # 元数据：token 数、模型名、生成耗时等
    metadata_: dict | None = Field(default=None, sa_column=Column("metadata", Text))

    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))

    session: ChatSession = Relationship(back_populates="messages")
