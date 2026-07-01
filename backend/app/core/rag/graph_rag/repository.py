"""
GraphRAG 数据模型 — SQLModel 持久化层

借鉴 SAG DB Schema (migrations/001_init.sql):
  - GraphEvent: 事件表 (chunk 粒度的事件化表达)
  - GraphEntity: 实体表 (跨文档归一化)
  - EventEntityLink: 事件-实体关联表
  - EntityType: 实体类型定义表
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


# ── EntityType ─────────────────────────────────────────────

class EntityTypeDef(SQLModel, table=True):
    """实体类型定义"""
    __tablename__ = "entity_types"

    id: int = Field(default=None, primary_key=True)
    type: str = Field(index=True)          # person, org, concept, technology, location, product
    display_name: str = Field(default="")
    is_active: bool = Field(default=True)
    is_default: bool = Field(default=False)


# ── GraphEntity ────────────────────────────────────────────

class GraphEntityModel(SQLModel, table=True):
    """
    实体表

    借鉴 SAG entities 表设计:
      - 按 (source_id, type, normalized_name) 唯一约束去重
      - embedding 使用 pgvector vector 类型
      - search_text 为 tsvector 全文搜索列
    """
    __tablename__ = "graph_entities"

    id: int = Field(default=None, primary_key=True)
    entity_id: str = Field(default_factory=_new_uuid, unique=True, index=True)
    source_id: str = Field(index=True)      # 对应 KB ID
    entity_type_id: Optional[int] = Field(default=None)
    type: str = Field(index=True)           # 实体类型
    name: str                               # 原始名称
    normalized_name: str = Field(index=True) # 归一化名称 (小写)
    description: str = Field(default="")
    # 双轨向量: embedding_json (JSON, 全兼容) + embedding (pgvector native, PG专用)
    embedding_json: Optional[str] = Field(default=None)
    embedding: Optional[str] = Field(default=None)  # pgvector vector → SQLAlchemy 透传

    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)


# ── GraphEvent ─────────────────────────────────────────────

class GraphEventModel(SQLModel, table=True):
    """
    事件表

    借鉴 SAG events 表设计:
      - 每个事件关联一个 source_chunk
      - title_embedding 和 content_embedding 分别索引
      - deleted_at 软删除
    """
    __tablename__ = "graph_events"

    id: int = Field(default=None, primary_key=True)
    event_id: str = Field(default_factory=_new_uuid, unique=True, index=True)
    source_id: str = Field(index=True)
    document_id: Optional[str] = Field(default=None, index=True)
    chunk_id: Optional[str] = Field(default=None, index=True)
    title: str
    summary: str = Field(default="")
    content: str = Field(default="")
    rank: int = Field(default=0)
    score: Optional[float] = Field(default=None)

    # 嵌入向量: _json (JSON全兼容) + 裸字段 (pgvector native)
    title_embedding_json: Optional[str] = Field(default=None)
    content_embedding_json: Optional[str] = Field(default=None)
    title_embedding: Optional[str] = Field(default=None)
    content_embedding: Optional[str] = Field(default=None)

    deleted_at: Optional[str] = Field(default=None)
    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)


# ── EventEntityLink ────────────────────────────────────────

class EventEntityLinkModel(SQLModel, table=True):
    """
    事件-实体关联表

    借鉴 SAG event_entities 表:
      - (event_id, entity_id) 复合唯一约束
      - weight 表示关联强度
    """
    __tablename__ = "graph_event_entities"

    id: int = Field(default=None, primary_key=True)
    event_id: str = Field(index=True)
    entity_id: str = Field(index=True)
    weight: float = Field(default=1.0)

    created_at: str = Field(default_factory=_utc_now)


# ── MCP Tool Call ─────────────────────────────────────────

class MCPToolCallModel(SQLModel, table=True):
    """MCP 工具调用记录 (借鉴 SAG mcp_tool_calls)"""
    __tablename__ = "mcp_tool_calls"

    id: int = Field(default=None, primary_key=True)
    call_id: str = Field(default_factory=_new_uuid, unique=True, index=True)
    session_id: str = Field(index=True)
    message_id: Optional[str] = Field(default=None)
    tool_name: str
    arguments_json: str = Field(default="{}")
    result_json: Optional[str] = Field(default=None)
    status: str = Field(default="PENDING")  # PENDING | SUCCEEDED | FAILED
    duration_ms: Optional[float] = Field(default=None)
    error: Optional[str] = Field(default=None)

    created_at: str = Field(default_factory=_utc_now)


# ── GraphRepository 接口 ────────────────────────────────────

class GraphRepository:
    """
    GraphRAG 数据仓库 (内存实现 + 可替换为 PostgreSQL)

    提供 GraphRAGEngine 和 GraphBuilder 所需的所有数据库操作。
    当前使用内存字典 + SQLModel 作为参考实现。
    """

    def __init__(self, use_db: bool = False):
        self._use_db = use_db
        # 内存存储 (开发阶段)
        self._events: dict[str, dict] = {}
        self._entities: dict[str, dict] = {}
        self._event_entities: dict[str, list[str]] = {}  # event_id → [entity_id, ...]
        self._chunks: dict[str, dict] = {}

    # ── 实体操作 ──────────────────────────────────────────

    async def search_entities_by_text(self, source_ids: list[str], query: str, limit: int = 20) -> list[dict]:
        """BM25/全文搜索实体 (简化实现: 子串匹配)"""
        results = []
        query_lower = query.lower()
        for ent in self._entities.values():
            if ent.get("source_id") not in source_ids:
                continue
            name = ent.get("name", "").lower()
            norm_name = ent.get("normalized_name", name)
            if query_lower in name or query_lower in norm_name:
                results.append({**ent, "score": 0.8})
                if len(results) >= limit:
                    break
        return results

    async def search_entities_by_name(self, source_ids: list[str], names: list[str], limit: int = 20) -> list[dict]:
        """精确名称匹配实体"""
        name_set = {n.strip().lower() for n in names}
        results = []
        for ent in self._entities.values():
            if ent.get("source_id") not in source_ids:
                continue
            if ent.get("normalized_name", ent.get("name", "").lower()) in name_set:
                results.append(ent)
                if len(results) >= limit:
                    break
        return results

    async def search_entities_by_vector(self, source_ids: list[str], query_vector: list[float], top_k: int = 20, threshold: float = 0.4) -> list[dict]:
        """向量搜索实体 (简化: 余弦相似度)"""
        results = []
        for ent in self._entities.values():
            if ent.get("source_id") not in source_ids:
                continue
            emb = ent.get("embedding")
            if not emb:
                continue
            sim = self._cosine_sim(query_vector, emb)
            if sim >= threshold:
                results.append({**ent, "score": sim})
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:top_k]

    # ── 事件操作 ──────────────────────────────────────────

    async def search_events_by_title(self, source_ids: list[str], query_vector: list[float], top_k: int = 20, threshold: float = 0.4) -> list[dict]:
        """标题向量搜索事件"""
        results = []
        for ev in self._events.values():
            if ev.get("source_id") not in source_ids:
                continue
            emb = ev.get("title_embedding")
            if not emb:
                continue
            sim = self._cosine_sim(query_vector, emb)
            if sim >= threshold:
                results.append({**ev, "score": sim})
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:top_k]

    async def coarse_rank_events(self, source_ids: list[str], event_ids: list[str], query_vector: list[float], max_events: int = 100) -> list[dict]:
        """按内容向量粗排"""
        results = []
        for eid in event_ids:
            ev = self._events.get(eid)
            if not ev or ev.get("source_id") not in source_ids:
                continue
            emb = ev.get("content_embedding")
            if not emb:
                ev_copy = dict(ev)
                ev_copy["score"] = 0
                results.append(ev_copy)
                continue
            sim = self._cosine_sim(query_vector, emb)
            results.append({**ev, "score": sim})
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:max_events]

    async def get_event_ids_by_entity_ids(self, entity_ids: list[str], source_ids: list[str], exclude_event_ids: Optional[list[str]] = None) -> list[str]:
        """获取实体关联的事件 ID"""
        exclude = set(exclude_event_ids or [])
        result = []
        for eid, ent_ids in self._event_entities.items():
            if eid in exclude:
                continue
            ev = self._events.get(eid, {})
            if ev.get("source_id") not in source_ids:
                continue
            if any(e in entity_ids for e in ent_ids):
                result.append(eid)
        return result

    async def get_events_with_entity_ids(self, event_ids: list[str]) -> dict[str, dict]:
        """获取事件及其关联实体"""
        result = {}
        for eid in event_ids:
            ev = self._events.get(eid)
            if ev:
                ev_copy = dict(ev)
                ev_copy["entity_ids"] = self._event_entities.get(eid, [])
                result[eid] = ev_copy
        return result

    async def get_sections_for_events(self, event_ids: list[str]) -> list[dict]:
        """获取事件关联的切片"""
        sections = []
        for eid in event_ids:
            ev = self._events.get(eid)
            if not ev:
                continue
            chunk_id = ev.get("chunk_id")
            if chunk_id and chunk_id in self._chunks:
                chunk = self._chunks[chunk_id]
                sections.append({
                    "event_id": eid,
                    "chunk_id": chunk_id,
                    "source_id": ev.get("source_id", ""),
                    "document_id": ev.get("document_id"),
                    "heading": ev.get("title", ""),
                    "content": chunk.get("content", ""),
                    "rank": ev.get("rank", 0),
                })
        return sections

    async def search_chunks_by_vector(self, source_ids: list[str], query_vector: list[float], top_k: int = 10) -> list[dict]:
        """向量搜索切片"""
        results = []
        for cid, chunk in self._chunks.items():
            if chunk.get("source_id") not in source_ids:
                continue
            emb = chunk.get("embedding")
            if emb:
                sim = self._cosine_sim(query_vector, emb)
                results.append({**chunk, "chunk_id": cid, "score": sim})
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        return results[:top_k]

    # ── 写入操作 ──────────────────────────────────────────

    async def upsert_event(self, id: str = "", **kwargs) -> dict:
        event_id = id or kwargs.get("event_id", str(uuid.uuid4()))
        event = {
            "id": event_id,
            "source_id": kwargs.get("source_id", ""),
            "document_id": kwargs.get("document_id"),
            "chunk_id": kwargs.get("chunk_id"),
            "title": kwargs.get("title", ""),
            "summary": kwargs.get("summary", ""),
            "content": kwargs.get("content", ""),
            "rank": kwargs.get("rank", 0),
            "title_embedding": kwargs.get("title_embedding", []),
            "content_embedding": kwargs.get("content_embedding", []),
        }
        self._events[event_id] = event
        return event

    async def upsert_entity(self, source_id: str = "", type: str = "concept", name: str = "", embedding: list = None, entity_id: str = "", **kwargs) -> dict:
        eid = entity_id or str(uuid.uuid4())
        normalized = name.strip().lower()
        entity = {
            "id": eid,
            "source_id": source_id,
            "type": type,
            "name": name,
            "normalized_name": normalized,
            "embedding": embedding or [],
        }
        self._entities[eid] = entity
        return entity

    async def link_event_entity(self, event_id: str = "", entity_id: str = "", **kwargs) -> None:
        if event_id not in self._event_entities:
            self._event_entities[event_id] = []
        if entity_id not in self._event_entities[event_id]:
            self._event_entities[event_id].append(entity_id)

    async def add_chunk(self, chunk_id: str, content: str, source_id: str = "", embedding: list = None, **kwargs):
        self._chunks[chunk_id] = {
            "chunk_id": chunk_id,
            "content": content,
            "source_id": source_id,
            "embedding": embedding or [],
            **kwargs,
        }

    # ── 统计 ──────────────────────────────────────────────

    async def get_stats(self, source_id: str) -> dict:
        events = [e for e in self._events.values() if e.get("source_id") == source_id]
        entities = [e for e in self._entities.values() if e.get("source_id") == source_id]
        chunks = [c for c in self._chunks.values() if c.get("source_id") == source_id]
        return {
            "source_id": source_id,
            "event_count": len(events),
            "entity_count": len(entities),
            "chunk_count": len(chunks),
        }

    # ── 工具 ──────────────────────────────────────────────

    @staticmethod
    def _cosine_sim(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
