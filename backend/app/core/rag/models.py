"""
KB 数据模型 — SQLModel 持久化层

借鉴 AstrBot KnowledgeBase/KBDocument/KBMedia:
- KnowledgeBase: 知识库主表 (UUID, 嵌入/Rerank provider, 分块/检索配置)
- KBDocument: 文档元数据表 (kb_id 关联, 文件类型/大小/路径)
- KBMedia: 多媒体资源表 (图片/视频, base64 或文件路径)
- Segment: Segment 实例映射表 (借鉴 Chroma, 记录每个 KB 的存储后端类型)
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

    # 嵌入生命周期追踪
    embedding_status: str = Field(default="pending")  # pending | embedding | completed | failed
    embedded_at: Optional[str] = Field(default=None)   # ISO 时间戳，嵌入完成时赋值

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


# ── Segment 实例映射表 — 借鉴 Chroma ────────────────

class Segment(SQLModel, table=True):
    """Segment 实例映射表

    记录每个 KB 使用的存储后端类型，支持运行时替换:
    - metadata: 元数据存储类型 (sqlite | pg)
    - vector: 向量存储类型 (faiss | hnsw | qdrant)
    - record: 记录存储类型 (blockfile | sqlite)
    """
    __tablename__ = "kb_segments"

    id: int = Field(default=None, primary_key=True)
    kb_id: str = Field(index=True)
    scope: str = Field(default="default")  # 多 scope 隔离 (同一 KB 的不同数据分区)
    segment_name: str  # "metadata" | "vector" | "record"
    segment_type: str  # 后端类型: "sqlite" | "faiss" | "blockfile" | "qdrant" | ...
    segment_config: str = Field(default="{}")  # JSON 配置 (路径/维度/参数)

    created_at: str = Field(default_factory=_utc_now)


# ── KBJob 异步任务表 ─────────────────────────────

class KBJob(SQLModel, table=True):
    """知识库异步后台任务队列（PostgreSQL 持久化，无需 Redis/RabbitMQ）

    用于：重新训练（retrain）、批量嵌入、大文件解析等耗时操作。
    前端轮询 GET /jobs/{job_id} 获取进度，完成后读取 result_json。
    """
    __tablename__ = "kb_jobs"

    id: int = Field(default=None, primary_key=True)
    job_id: str = Field(default_factory=_new_uuid, unique=True, index=True)
    kb_id: str = Field(index=True)
    job_type: str  # retrain | batch_embed | file_parse | health_check
    status: str = Field(default="pending", index=True)  # pending | running | completed | failed
    progress: float = Field(default=0.0)  # 0.0 ~ 1.0
    payload_json: Optional[str] = Field(default=None)   # 请求参数 JSON
    result_json: Optional[str] = Field(default=None)    # 结果 JSON（成功）或错误信息（失败）
    error_message: Optional[str] = Field(default=None)  # 错误详情
    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)

    @property
    def payload(self) -> dict:
        """解析 payload_json"""
        import json
        return json.loads(self.payload_json) if self.payload_json else {}

    @property
    def result(self) -> dict:
        """解析 result_json"""
        import json
        return json.loads(self.result_json) if self.result_json else {}

    def set_payload(self, payload: dict):
        """设置 payload_json"""
        import json
        self.payload_json = json.dumps(payload, ensure_ascii=False)

    def set_result(self, result: dict):
        """设置 result_json"""
        import json
        self.result_json = json.dumps(result, ensure_ascii=False)
