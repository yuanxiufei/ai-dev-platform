"""
系统域数据模型

ModelDownload    —  模型下载任务（HuggingFace / ModelScope）
ModelUsageStat   —  模型使用统计（驱动自动优化）
ApiCredential    —  第三方 API 密钥（AES-256 加密存储）
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import DateTime
from sqlmodel import Column, Field, Relationship, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


# ── ModelDownload ───────────────────────────────────────

class ModelDownload(SQLModel, table=True):
    """模型下载记录 — 支持 HuggingFace / ModelScope 双源"""
    __tablename__ = "model_downloads"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    model_name: str = Field(max_length=100)
    source: str = Field(max_length=200)          # huggingface id 或 ModelScope id
    source_type: str = Field(default="huggingface", max_length=50)  # huggingface | modelscope

    status: DownloadStatus = Field(default=DownloadStatus.PENDING)
    progress: int = Field(default=0)             # 0 - 100
    file_size: int | None = Field(default=None)  # 总字节数
    downloaded: int = Field(default=0)           # 已下载字节数
    error_message: str | None = Field(default=None, max_length=500)

    started_by: uuid.UUID = Field(foreign_key="user.id", nullable=False)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── ModelUsageStat ──────────────────────────────────────

class ModelUsageStat(SQLModel, table=True):
    """模型使用统计 — 每次调用的记录，驱动 AutoOptimizer"""
    __tablename__ = "model_usage_stats"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    model_name: str = Field(max_length=100)
    task_type: str = Field(max_length=50)        # code_gen | video_gen | chat | vision
    success: bool
    latency_ms: int                              # 推理耗时（毫秒）
    token_count: int | None = Field(default=None)
    error_message: str | None = Field(default=None, max_length=500)

    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── ApiCredential ───────────────────────────────────────

class ApiCredential(SQLModel, table=True):
    """第三方 API 密钥 — AES-256 加密存储"""
    __tablename__ = "api_credentials"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    provider: str = Field(max_length=50)         # openai | anthropic | replicate | azure | deepseek
    api_key_encrypted: str = Field(max_length=500)
    endpoint: str | None = Field(default=None, max_length=300)
    is_active: bool = Field(default=True)

    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
