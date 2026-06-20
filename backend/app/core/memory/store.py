"""
Memory Store — 长期向量化记忆存储核心

借鉴 Open WebUI Memory 功能：
- CRUD 操作（DB 持久化 + embedding 向量索引）
- 语义检索（余弦相似度 × 重要性加权）
- 域管理（project/task/knowledge/preference/general）
- LLM 驱动的记忆更新（合并、修正、遗忘）
- Agent 工具接口（save_memory / recall_memory / forget_memory）

与 API 路由层的关系：
- API 路由层(routes/agent/memory.py) 直接操作 MemoryStore
- Agent 工具通过 MemoryStore.save/recall 接口调用
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("memory.store")


# ── 数据模型 ──────────────────────────────────────────


@dataclass
class MemoryRecord:
    """内存中的记忆记录（与 DB MemoryEntry 解耦）"""
    id: str = ""
    key: str = ""
    value: str = ""
    domain: str = "general"
    importance: float = 0.5
    embedding: list[float] | None = None
    embedding_dim: int = 0
    embedding_model: str = ""
    access_count: int = 0
    last_accessed_at: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_db(cls, entry: Any) -> MemoryRecord:
        """从 DB MemoryEntry 转换"""
        try:
            embedding = json.loads(entry.embedding) if entry.embedding else None
        except (json.JSONDecodeError, TypeError):
            embedding = None

        return cls(
            id=str(entry.id),
            key=entry.key,
            value=entry.value,
            domain=entry.domain or "general",
            importance=float(entry.importance or 0.5),
            embedding=embedding,
            embedding_dim=entry.embedding_dim or 0,
            embedding_model=entry.embedding_model or "",
            access_count=entry.access_count or 0,
            last_accessed_at=entry.last_accessed_at.isoformat() if entry.last_accessed_at else "",
            created_at=entry.created_at.isoformat() if entry.created_at else "",
            updated_at=entry.updated_at.isoformat() if entry.updated_at else "",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value[:500] + ("..." if len(self.value) > 500 else ""),
            "domain": self.domain,
            "importance": self.importance,
            "access_count": self.access_count,
        }


@dataclass
class MemorySearchResult:
    """记忆检索结果"""
    record: MemoryRecord
    similarity: float = 0.0
    score: float = 0.0
    """综合评分 = similarity × importance"""


# ── MemoryStore ───────────────────────────────────────


class MemoryStore:
    """长期记忆存储

    双写架构：
    1. SQLite/PostgreSQL（通过 SQLModel/SQLAlchemy）— 持久化
    2. 内存向量索引（numpy/custom）— 快速搜索
    """

    def __init__(self) -> None:
        self._index: dict[str, MemoryRecord] = {}
        """内存索引（id → record）"""
        self._domain_index: dict[str, list[str]] = {}
        """域索引（domain → [id, ...]）"""

    # ── CRUD ─────────────────────────────────────────

    async def save(
        self,
        key: str,
        value: str,
        domain: str = "general",
        importance: float = 0.5,
        user_id: str = "",
        generate_embedding: bool = True,
    ) -> str:
        """创建或更新记忆（upsert by key+domain+user_id）"""
        now = datetime.now(timezone.utc).isoformat()

        # 查找是否已存在
        existing = await self._find_by_key(key, domain, user_id)

        record_id = existing.id if existing else str(uuid.uuid4())
        embedding: list[float] | None = None
        embedding_dim = 0
        embedding_model = ""

        if generate_embedding:
            try:
                svc = get_embedding_service()
                embedding = await svc.embed(f"{key}: {value}")
                embedding_dim = len(embedding)
                embedding_model = svc.provider_name
            except Exception as e:
                logger.warning("Embedding generation failed: %s, using hash fallback", e)
                embedding = _hash_embedding(f"{key}: {value}")
                embedding_dim = len(embedding)
                embedding_model = "hash-sha256"

        record = MemoryRecord(
            id=record_id,
            key=key,
            value=value,
            domain=domain,
            importance=min(max(importance, 0.0), 1.0),
            embedding=embedding,
            embedding_dim=embedding_dim,
            embedding_model=embedding_model,
            access_count=existing.access_count if existing else 0,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )

        # 更新内存索引
        self._index[record_id] = record
        if domain not in self._domain_index:
            self._domain_index[domain] = []
        if record_id not in self._domain_index[domain]:
            self._domain_index[domain].append(record_id)

        # 持久化到 DB
        await self._persist_to_db(record, user_id, is_new=(existing is None))

        logger.debug("Memory saved: %s (domain=%s)", key, domain)
        return record_id

    async def get(self, record_id: str, user_id: str = "") -> MemoryRecord | None:
        """获取单条记忆"""
        record = self._index.get(record_id)
        if record:
            record.access_count += 1
            record.last_accessed_at = datetime.now(timezone.utc).isoformat()
            return record

        # 回退到 DB 查询
        return await self._load_from_db(record_id, user_id)

    async def update(
        self,
        record_id: str,
        key: str | None = None,
        value: str | None = None,
        domain: str | None = None,
        importance: float | None = None,
        user_id: str = "",
    ) -> MemoryRecord | None:
        """更新记忆"""
        record = self._index.get(record_id)
        if not record:
            record = await self._load_from_db(record_id, user_id)
            if not record:
                return None
            self._index[record_id] = record

        if key is not None:
            record.key = key
        if value is not None:
            record.value = value
        if domain is not None:
            record.domain = domain
        if importance is not None:
            record.importance = min(max(importance, 0.0), 1.0)

        # 重新生成 embedding
        if key is not None or value is not None:
            try:
                svc = get_embedding_service()
                record.embedding = await svc.embed(f"{record.key}: {record.value}")
                record.embedding_dim = len(record.embedding)
                record.embedding_model = svc.provider_name
            except Exception:
                record.embedding = _hash_embedding(f"{record.key}: {record.value}")
                record.embedding_dim = len(record.embedding)
                record.embedding_model = "hash-sha256"

        record.updated_at = datetime.now(timezone.utc).isoformat()

        # 持久化
        await self._update_db(record, user_id)

        return record

    async def delete(self, record_id: str, user_id: str = "") -> bool:
        """删除记忆"""
        if record_id in self._index:
            record = self._index.pop(record_id)
            domain_ids = self._domain_index.get(record.domain, [])
            if record_id in domain_ids:
                domain_ids.remove(record_id)

        try:
            from app.models.model_presets import MemoryEntry
            import sqlalchemy as sa
            from sqlmodel import Session

            engine = _get_engine()
            if engine:
                with Session(engine) as session:
                    entry = session.get(MemoryEntry, uuid.UUID(record_id))
                    if entry and (not user_id or str(entry.user_id) == user_id):
                        session.delete(entry)
                        session.commit()
                        return True
        except Exception as e:
            logger.warning("Failed to delete memory from DB: %s", e)

        return True

    async def search(
        self,
        query: str,
        domain: str | None = None,
        top_k: int = 5,
        min_similarity: float = 0.3,
        user_id: str = "",
    ) -> list[MemorySearchResult]:
        """语义检索记忆"""
        # 生成查询 embedding
        try:
            svc = get_embedding_service()
            query_emb = await svc.embed(query)
        except Exception:
            query_emb = _hash_embedding(query)

        # 候选集
        if domain:
            candidate_ids = self._domain_index.get(domain, [])
        else:
            candidate_ids = list(self._index.keys())

        if not candidate_ids:
            # 从 DB 加载候选
            candidates = await self._search_db(query, domain, top_k, user_id)
            return candidates

        # 向量相似度计算
        results: list[MemorySearchResult] = []
        for rid in candidate_ids:
            record = self._index.get(rid)
            if not record or not record.embedding:
                continue
            sim = _cosine_similarity(query_emb, record.embedding)
            if sim >= min_similarity:
                results.append(MemorySearchResult(
                    record=record,
                    similarity=sim,
                    score=sim * record.importance,
                ))

        # 按综合评分排序
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    async def list_by_domain(
        self, domain: str, user_id: str = ""
    ) -> list[MemoryRecord]:
        """按域列出记忆"""
        record_ids = self._domain_index.get(domain, [])
        records = [self._index[rid] for rid in record_ids if rid in self._index]
        records.sort(key=lambda r: r.updated_at, reverse=True)
        return records

    async def stats(self, user_id: str = "") -> dict[str, Any]:
        """记忆统计"""
        domains: dict[str, int] = {}
        for domain, ids in self._domain_index.items():
            domains[domain] = len(ids)

        total_access = sum(r.access_count for r in self._index.values())

        return {
            "total_memories": len(self._index),
            "total_accesses": total_access,
            "by_domain": domains,
        }

    # ── LLM 驱动记忆更新 (借鉴 DeerFlow) ──────────

    async def update_from_conversation(
        self,
        conversation_summary: str,
        domain: str = "conversation",
        user_id: str = "",
    ) -> list[str]:
        """从对话摘要中提取并更新记忆条目

        借鉴 DeerFlow 的 LLM 驱动记忆更新：
        1. 让 LLM 从对话中提取重要信息
        2. 与新记忆合并/去重
        3. 更新旧记忆（修正/补充）
        """
        extracted = await self._extract_memories_from_text(conversation_summary)

        new_ids: list[str] = []
        for item in extracted:
            # 检查是否与已有记忆冲突/重复
            existing_results = await self.search(
                query=item["value"],
                domain=domain,
                top_k=1,
                min_similarity=0.85,
                user_id=user_id,
            )
            if existing_results:
                # 合并/更新已有记忆
                old = existing_results[0].record
                merged_value = await self._merge_memories(old.value, item["value"])
                await self.update(
                    old.id,
                    value=merged_value,
                    importance=max(old.importance, item.get("importance", 0.5)),
                    user_id=user_id,
                )
                new_ids.append(old.id)
            else:
                rid = await self.save(
                    key=item["key"],
                    value=item["value"],
                    domain=domain,
                    importance=item.get("importance", 0.5),
                    user_id=user_id,
                )
                new_ids.append(rid)

        return new_ids

    async def _extract_memories_from_text(
        self, text: str
    ) -> list[dict[str, Any]]:
        """用 LLM 从文本中提取记忆条目"""
        try:
            from app.core.model_router import (
                ModelCapability, ModelRequest, get_model_router,
            )

            prompt = f"""Extract key memories from this conversation. For each memory:
- key: a short label (max 50 chars)
- value: the specific fact or information
- importance: 0.0 to 1.0

Text:
{text[:3000]}

Respond in JSON array:
```json
[{{"key": "...", "value": "...", "importance": 0.X}}]
```"""

            router = get_model_router()
            request = ModelRequest(
                capability=ModelCapability.CODE_GENERATION,
                prompt=prompt,
                max_tokens=1024,
                temperature=0.2,
            )
            response = await router.generate(request)

            import re
            json_match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', response.content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(1))

            # 直接尝试解析
            return json.loads(response.content)

        except Exception as e:
            logger.warning("Memory extraction via LLM failed: %s", e)
            return []

    async def _merge_memories(self, old_value: str, new_value: str) -> str:
        """用 LLM 合并新旧记忆"""
        try:
            from app.core.model_router import (
                ModelCapability, ModelRequest, get_model_router,
            )

            prompt = f"""Merge two memory entries about the same topic.
Keep all unique information. Resolve contradictions by keeping the newer information.
Be concise.

Old: {old_value[:1000]}
New: {new_value[:1000]}

Merged:"""

            router = get_model_router()
            request = ModelRequest(
                capability=ModelCapability.CODE_GENERATION,
                prompt=prompt,
                max_tokens=512,
                temperature=0.1,
            )
            response = await router.generate(request)
            return response.content.strip()

        except Exception as e:
            logger.warning("Memory merge via LLM failed: %s", e)
            # Fallback: 保留新信息
            return new_value

    # ── DB 持久化 ─────────────────────────────────

    async def _persist_to_db(self, record: MemoryRecord, user_id: str, is_new: bool) -> None:
        """持久化到数据库"""
        try:
            from app.models.model_presets import MemoryEntry
            from sqlmodel import Session

            engine = _get_engine()
            if not engine:
                return

            with Session(engine) as session:
                if is_new:
                    entry = MemoryEntry(
                        id=uuid.UUID(record.id),
                        key=record.key,
                        value=record.value,
                        domain=record.domain,
                        importance=record.importance,
                        embedding=json.dumps(record.embedding) if record.embedding else None,
                        embedding_dim=record.embedding_dim,
                        embedding_model=record.embedding_model,
                        user_id=uuid.UUID(user_id) if user_id else uuid.uuid4(),
                    )
                    session.add(entry)
                else:
                    entry = session.get(MemoryEntry, uuid.UUID(record.id))
                    if entry:
                        entry.key = record.key
                        entry.value = record.value
                        entry.domain = record.domain
                        entry.importance = record.importance
                        entry.embedding = json.dumps(record.embedding) if record.embedding else None
                        entry.embedding_dim = record.embedding_dim
                        entry.embedding_model = record.embedding_model
                        entry.access_count = record.access_count
                        session.add(entry)

                session.commit()

        except Exception as e:
            logger.debug("DB persist skipped (MemoryStore running in memory-only mode): %s", e)

    async def _load_from_db(self, record_id: str, user_id: str = "") -> MemoryRecord | None:
        """从 DB 加载记忆"""
        try:
            from app.models.model_presets import MemoryEntry
            from sqlmodel import Session

            engine = _get_engine()
            if not engine:
                return None

            with Session(engine) as session:
                entry = session.get(MemoryEntry, uuid.UUID(record_id))
                if entry and (not user_id or str(entry.user_id) == user_id):
                    record = MemoryRecord.from_db(entry)
                    self._index[record_id] = record
                    return record
        except Exception as e:
            logger.debug("DB load skipped: %s", e)

        return None

    async def _search_db(
        self, query: str, domain: str | None, top_k: int, user_id: str
    ) -> list[MemorySearchResult]:
        """从 DB 搜索（回退方案）"""
        try:
            from app.models.model_presets import MemoryEntry
            from sqlmodel import Session, select
            from app.models.model_presets import MemoryEntry as ME

            engine = _get_engine()
            if not engine:
                return []

            with Session(engine) as session:
                stmt = select(ME)
                if user_id:
                    stmt = stmt.where(ME.user_id == uuid.UUID(user_id))
                if domain:
                    stmt = stmt.where(ME.domain == domain)

                entries = session.exec(stmt).all()

                # 纯文本匹配（无向量时）
                query_lower = query.lower()
                results: list[MemorySearchResult] = []
                for entry in entries:
                    text = f"{entry.key} {entry.value}".lower()
                    if query_lower in text:
                        results.append(MemorySearchResult(
                            record=MemoryRecord.from_db(entry),
                            similarity=0.6,  # 纯文本匹配给基础分
                            score=0.6 * entry.importance,
                        ))

                results.sort(key=lambda x: x.score, reverse=True)
                return results[:top_k]
        except Exception as e:
            logger.debug("DB search skipped: %s", e)

        return []

    async def _update_db(self, record: MemoryRecord, user_id: str) -> None:
        """更新 DB 中的记录"""
        await self._persist_to_db(record, user_id, is_new=False)

    async def _find_by_key(
        self, key: str, domain: str, user_id: str
    ) -> MemoryRecord | None:
        """按 key+domain 查找已有记录"""
        # 先在内存索引中查找
        for record in self._index.values():
            if record.key == key and record.domain == domain:
                return record
        return None


# ── 全局单例 ──────────────────────────────────────────

_memory_store: MemoryStore | None = None


def init_memory_store() -> MemoryStore:
    global _memory_store
    _memory_store = MemoryStore()
    logger.info("MemoryStore initialized (in-memory index + DB persistence)")
    return _memory_store


def get_memory_store() -> MemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


# ── 工具函数 ──────────────────────────────────────────


def _get_engine():
    """获取 SQLAlchemy engine（延迟导入避免循环依赖）"""
    try:
        from app.core.db import engine
        return engine
    except Exception:
        return None


def _hash_embedding(text: str, dim: int = 768) -> list[float]:
    """哈希降级 embedding"""
    import hashlib
    import math

    hash_bytes = hashlib.sha256(text.encode()).digest()
    vec = [(hash_bytes[i % len(hash_bytes)] / 127.5) - 1.0 for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """余弦相似度"""
    import math

    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(ai * bi for ai, bi in zip(a, b))
    norm_a = math.sqrt(sum(ai * ai for ai in a))
    norm_b = math.sqrt(sum(bi * bi for bi in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
