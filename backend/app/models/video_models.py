"""
Video 域数据模型

VideoTask     —  视频生成任务（文本→视频、UI录屏→视频）
VideoAsset    —  视频资产（管理端发布、分发）
VideoSubtitle —  视频字幕（SRT/VTT 多语言）
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime, Float, Integer, Text
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

    params: dict | None = Field(default=None, sa_column=Column("params", Text))
    output_path: str | None = Field(default=None, max_length=500)
    thumbnail_path: str | None = Field(default=None, max_length=500)
    duration: float | None = None
    error_message: str | None = Field(default=None, sa_column=Column("error_message", Text))
    progress: int = Field(default=0)

    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── VideoAsset ──────────────────────────────────────────

class VideoAsset(SQLModel, table=True):
    """视频资产 — 管理端发布和分发"""
    __tablename__ = "video_assets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    description: str | None = Field(default=None, max_length=2000)

    task_id: uuid.UUID | None = Field(default=None, foreign_key="video_tasks.id", nullable=True, index=True)
    file_path: str = Field(max_length=500)
    thumbnail_path: str | None = Field(default=None, max_length=500)
    duration: float | None = None

    tags: list | None = Field(default=None, sa_column=Column("tags", Text))
    view_count: int = Field(default=0)
    is_public: bool = Field(default=True)
    is_approved: bool = Field(default=False)

    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── VideoSubtitle ───────────────────────────────────────

class VideoSubtitle(SQLModel, table=True):
    """视频字幕 — 支持 SRT/VTT 多语言字幕存储与检索"""
    __tablename__ = "video_subtitles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    video_id: uuid.UUID = Field(foreign_key="video_assets.id", nullable=False, ondelete="CASCADE", index=True)
    language: str = Field(max_length=10, index=True)    # zh, en, ja, ko...
    format: str = Field(default="srt", max_length=10)    # srt | vtt | ass
    content: str = Field(sa_column=Column("content", Text))  # 完整字幕文本
    source: str = Field(default="manual", max_length=20)  # manual | whisper | auto
    file_path: str | None = Field(default=None, max_length=500)  # 原始文件路径

    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


# ── 字幕条目 (反范式化，用于按时间查询字幕片段) ──────────

class SubtitleCue(SQLModel, table=True):
    """字幕条目 — 单条字幕的时间段与文本"""
    __tablename__ = "subtitle_cues"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    subtitle_id: uuid.UUID = Field(foreign_key="video_subtitles.id", nullable=False, ondelete="CASCADE", index=True)
    sequence: int = Field(sa_column=Column("sequence", Integer, nullable=False))  # 序号
    start_time: float = Field(sa_column=Column("start_time", Float, nullable=False))  # 开始秒
    end_time: float = Field(sa_column=Column("end_time", Float, nullable=False))      # 结束秒
    text: str = Field(sa_column=Column("text", Text, nullable=False))                 # 字幕文本
