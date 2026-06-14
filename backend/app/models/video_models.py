"""
Video 域数据模型

VideoTask   —  视频生成任务（文本→视频、UI录屏→视频）
VideoAsset  —  视频资产（管理端发布、分发）
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Text
from sqlmodel import Column, Field, Relationship, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


# ── VideoTask ───────────────────────────────────────────

class VideoTask(SQLModel, table=True):
    """视频生成任务 — 异步执行，支持进度查询"""
    __tablename__ = "video_tasks"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    prompt: str = Field(sa_column=Column("prompt", Text))
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    model_name: str = Field(max_length=100)

    params: dict | None = Field(default=None, sa_column=Column("params", Text))  # {num_frames, fps, seed, ...}
    output_path: str | None = Field(default=None, max_length=500)
    thumbnail_path: str | None = Field(default=None, max_length=500)
    duration: float | None = None
    error_message: str | None = Field(default=None, sa_column=Column("error_message", Text))
    progress: int = Field(default=0)  # 0 - 100

    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── VideoAsset ──────────────────────────────────────────

class VideoAsset(SQLModel, table=True):
    """视频资产 — 管理端发布和分发"""
    __tablename__ = "video_assets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=2000)

    task_id: uuid.UUID | None = Field(default=None, foreign_key="video_tasks.id", nullable=True)
    file_path: str = Field(max_length=500)
    thumbnail_path: str | None = Field(default=None, max_length=500)
    duration: float | None = None

    tags: list | None = Field(default=None, sa_column=Column("tags", Text))  # ["demo", "tutorial"]
    view_count: int = Field(default=0)
    is_public: bool = Field(default=True)
    is_approved: bool = Field(default=False)

    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
