"""
KB 数据模型 — SQLModel 持久化层

借鉴 AstrBot KnowledgeBase/KBDocument/KBMedia:
- KnowledgeBase: 知识库主表 (UUID, 嵌入/Rerank provider, 分块/检索配置)
- KBDocument: 文档元数据表 (kb_id 关联, 文件类型/大小/路径)
- KBMedia: 多媒体资源表 (图片/视频, base64 或文件路径)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_uuid() -> str:
    return uuid.uuid4().hex


# ── KnowledgeBase 表 ────────────────────────────────

class KnowledgeBase(SQLModel, table=True):
    """知识库主表"""
    __tablename__ = "knowledge_bases"

    id: int = Field(default=None, primary_key=True)
    kb_id: str = Field(default_factory=_new_uuid, unique=True, index=True)
    kb_name: str = Field(unique=True, index=True)
    description: str = Field(default="")
    emoji: str = Field(default="")

    # Provider 配置
    embedding_provider_id: Optional[str] = Field(default=None)
    rerank_provider_id: Optional[str] = Field(default=None)

    # 分块配置
    chunk_size: int = Field(default=512)
    chunk_overlap: int = Field(default=50)

    # 检索配置
    top_k_dense: int = Field(default=50)
    top_k_sparse: int = Field(default=50)
    top_m_final: int = Field(default=5)

    # 统计
    doc_count: int = Field(default=0)
    chunk_count: int = Field(default=0)

    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)


# ── KBDocument 表 ───────────────────────────────────

class KBDocument(SQLModel, table=True):
    """知识库文档元数据"""
    __tablename__ = "kb_documents"

    id: int = Field(default=None, primary_key=True)
    doc_id: str = Field(default_factory=_new_uuid, unique=True, index=True)
    kb_id: str = Field(index=True)
    doc_name: str
    file_type: str = Field(default="")
    file_size: int = Field(default=0)
    file_path: str = Field(default="")
    chunk_count: int = Field(default=0)
    media_count: int = Field(default=0)

    created_at: str = Field(default_factory=_utc_now)


# ── KBMedia 表 ──────────────────────────────────────

class KBMedia(SQLModel, table=True):
    """多媒体资源"""
    __tablename__ = "kb_media"

    id: int = Field(default=None, primary_key=True)
    media_id: str = Field(default_factory=_new_uuid, unique=True, index=True)
    doc_id: str = Field(index=True)
    kb_id: str = Field(index=True)
    media_type: str = Field(default="image")  # image / video
    file_name: str
    file_path: str = Field(default="")
    file_size: int = Field(default=0)
    mime_type: str = Field(default="")

    created_at: str = Field(default_factory=_utc_now)
