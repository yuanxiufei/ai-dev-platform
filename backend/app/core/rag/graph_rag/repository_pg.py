"""
GraphRepositoryPG — 生产级 GraphRAG 存储 (PG + pgvector + Qdrant 透明加速)

┌─────────────────────────────────────────────────┐
│           GraphRepositoryPG(session)             │
│                                                  │
│  关系查询 (PG, 始终)    │  向量搜索 (自动选最优) │
│  ───────────────────    │  ──────────────────── │
│  • ILIKE 名称搜索       │  1. Qdrant (env auto) │
│  • SQL JOIN 实体-事件   │  2. pgvector HNSW     │
│  • 精确名称匹配         │  3. JSON cosine (兜底) │
│  • 切片回取             │                        │
│  • 统计查询             │                        │
└─────────────────────────────────────────────────┘

用法 — 无论开发/生产，同一行代码:
    store = GraphRepositoryPG(session)
    engine = GraphRAGEngine(db=store)

Qdrant 自动检测:
    设置环境变量 QDRANT_URL + QDRANT_API_KEY 即自动启用
    未设置则走 pgvector → JSON 回退链
"""
from __future__ import annotations
import json, logging, os
from typing import Any, Optional

from sqlmodel import Session, col, select, text

from app.core.rag.graph_rag.repository import (
    EventEntityLinkModel, GraphEntityModel, GraphEventModel,
)

logger = logging.getLogger("app.core.rag.graph_rag.repository_pg")

# ── pgvector 检测 ──────────────────────────────────────────

_HAS_PGVECTOR: bool | None = None


def _check_pgvector(session: Session) -> bool:
    global _HAS_PGVECTOR
    if _HAS_PGVECTOR is not None:
        return _HAS_PGVECTOR
    try:
        row = session.exec(
            text("SELECT installed_version FROM pg_available_extensions WHERE name = 'vector'")
        ).first()
        _HAS_PGVECTOR = row is not None
    except Exception:
        _HAS_PGVECTOR = False
    return _HAS_PGVECTOR


# ── 向量工具 ──────────────────────────────────────────────

def _pg_vector_literal(vec: list[float]) -> str:
    return f"[{','.join(str(v) for v in vec)}]"


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _parse_json_vec(raw: Optional[str]) -> Optional[list[float]]:
    if not raw: return None
    try: return json.loads(raw)
    except Exception: return None


def _new_uuid() -> str:
    import uuid; return uuid.uuid4().hex


def _entity_dict(r: GraphEntityModel, score: float = 0) -> dict:
    return {"id": r.entity_id, "source_id": r.source_id, "type": r.type,
            "name": r.name, "normalized_name": r.normalized_name, "score": score}


def _event_dict(r: GraphEventModel, score: float = 0) -> dict:
    return {"id": r.event_id, "source_id": r.source_id, "document_id": r.document_id,
            "chunk_id": r.chunk_id, "title": r.title, "summary": r.summary,
            "content": r.content, "rank": r.rank, "score": score}


# ── Qdrant 懒加载 ─────────────────────────────────────────

_QDRANT_AVAILABLE: bool | None = None


def _qdrant_available() -> bool:
    """检测 qdrant-client 是否可导入"""
    global _QDRANT_AVAILABLE
    if _QDRANT_AVAILABLE is not None:
        return _QDRANT_AVAILABLE
    try:
        import qdrant_client  # noqa: F401
        _QDRANT_AVAILABLE = True
    except ImportError:
        _QDRANT_AVAILABLE = False
    return _QDRANT_AVAILABLE


def _qdrant_config_from_env() -> dict | None:
    """从环境变量读取 Qdrant 配置，未配置返回 None"""
    url = os.getenv("QDRANT_URL")
    if not url: return None
    return {
        "url": url,
        "api_key": os.getenv("QDRANT_API_KEY"),
        "host": os.getenv("QDRANT_HOST", "localhost"),
        "port": int(os.getenv("QDRANT_PORT", "6333")),
    }


# ── GraphRepositoryPG (生产级唯一存储) ─────────────────────

class GraphRepositoryPG:
    """
    GraphRAG 唯一持久化存储 — PG 管关系 + 自动向量加速

    向量搜索自动选最优后端:
      1. Qdrant (env QDRANT_URL 设置时自动启用)
      2. pgvector HNSW (PG 已装 pgvector 扩展时)
      3. JSON cosine 相似度 (纯 PG，无额外依赖)

    用法:
        store = GraphRepositoryPG(session)              # 自动检测
        store = GraphRepositoryPG(session, qdrant=qd)   # 显式传入 QdrantVectorStore
    """

    def __init__(self, session: Any, qdrant: Any = None):
        self._s: Session = session
        self._hv = _check_pgvector(session)
        self._qdrant = qdrant
        # 自动检测环境变量配置 Qdrant
        if self._qdrant is None and _qdrant_available():
            cfg = _qdrant_config_from_env()
            if cfg:
                try:
                    from app.core.rag.qdrant_store import QdrantVectorStore
                    self._qdrant = QdrantVectorStore(
                        collection_name="graphrag",
                        dim=1536,  # 默认维度，写入时动态适配
                        url=cfg["url"],
                        api_key=cfg["api_key"],
                        host=cfg["host"],
                        port=cfg["port"],
                    )
                    logger.info("GraphRepositoryPG: Qdrant auto-connected (collection=graphrag)")
                except Exception as e:
                    logger.warning("GraphRepositoryPG: Qdrant auto-connect failed: %s", e)

    # ═══════════════════════════════════════════════════════
    #  关系查询 — 始终走 PG (SQL JOIN / ILIKE)
    # ═══════════════════════════════════════════════════════

    def search_entities_by_text(self, source_ids: list[str], query: str, limit: int = 20) -> list[dict]:
        rows = self._s.exec(
            select(GraphEntityModel).where(
                col(GraphEntityModel.source_id).in_(source_ids),
                col(GraphEntityModel.normalized_name).ilike(f"%{query}%"),
            ).limit(limit)
        ).all()
        return [_entity_dict(r, 0.8) for r in rows]

    def search_entities_by_name(self, source_ids: list[str], names: list[str], limit: int = 20) -> list[dict]:
        n = [x.strip().lower() for x in names]
        rows = self._s.exec(
            select(GraphEntityModel).where(
                col(GraphEntityModel.source_id).in_(source_ids),
                col(GraphEntityModel.normalized_name).in_(n),
            ).limit(limit)
        ).all()
        return [_entity_dict(r) for r in rows]

    def get_event_ids_by_entity_ids(self, entity_ids, source_ids, exclude_event_ids=None):
        stmt = select(EventEntityLinkModel.event_id).join(
            GraphEventModel, EventEntityLinkModel.event_id == col(GraphEventModel.event_id)
        ).where(
            col(EventEntityLinkModel.entity_id).in_(entity_ids),
            col(GraphEventModel.source_id).in_(source_ids),
            col(GraphEventModel.deleted_at).is_(None),
        ).distinct()
        if exclude_event_ids:
            stmt = stmt.where(col(EventEntityLinkModel.event_id).not_in(exclude_event_ids))
        return list(self._s.exec(stmt).all())

    def get_events_with_entity_ids(self, event_ids):
        evs = {r.event_id: _event_dict(r) for r in self._s.exec(
            select(GraphEventModel).where(
                col(GraphEventModel.event_id).in_(event_ids),
                col(GraphEventModel.deleted_at).is_(None),
            )).all()}
        for link in self._s.exec(select(EventEntityLinkModel).where(
            col(EventEntityLinkModel.event_id).in_(event_ids)
        )).all():
            evs.setdefault(link.event_id, {}).setdefault("entity_ids", []).append(link.entity_id)
        return evs

    def get_sections_for_events(self, event_ids):
        sections = []
        for ev in self._s.exec(select(GraphEventModel).where(
            col(GraphEventModel.event_id).in_(event_ids),
            col(GraphEventModel.deleted_at).is_(None),
        )).all():
            sections.append({"event_id": ev.event_id, "chunk_id": ev.chunk_id or "",
                             "source_id": ev.source_id, "document_id": ev.document_id,
                             "heading": ev.title, "content": ev.content, "rank": ev.rank})
        return sections

    # ═══════════════════════════════════════════════════════
    #  向量搜索 — Qdrant → pgvector → JSON 自动回退
    # ═══════════════════════════════════════════════════════

    def search_entities_by_vector(self, source_ids, query_vector, top_k=20, threshold=0.4):
        # 1) Qdrant
        if self._qdrant and query_vector:
            r = self._qdrant_find("entity", source_ids, query_vector, top_k, threshold)
            if r: return r
        # 2) pgvector HNSW
        if self._hv and query_vector:
            return self._pg_entity_vector_search(source_ids, query_vector, top_k, threshold)
        # 3) JSON cosine fallback
        return self._json_entity_fallback(source_ids, query_vector, top_k, threshold)

    def search_events_by_title(self, source_ids, query_vector, top_k=20, threshold=0.4):
        if self._qdrant and query_vector:
            r = self._qdrant_find("event_title", source_ids, query_vector, top_k, threshold)
            if r: return r
        if self._hv and query_vector:
            return self._vector_search_events(source_ids, query_vector, top_k, threshold, "title_embedding")
        return self._json_fallback_events(source_ids, query_vector, top_k, threshold, "title_embedding_json")

    def coarse_rank_events(self, source_ids, event_ids, query_vector, max_events=100):
        if self._qdrant and query_vector:
            r = self._qdrant_find("event_content", source_ids, query_vector, max_events, -1,
                                   event_ids=event_ids)
            if r: return r
        if self._hv and query_vector:
            return self._vector_search_events(source_ids, query_vector, max_events, -1.0,
                                               "content_embedding", event_ids=event_ids)
        return self._json_fallback_events(source_ids, query_vector, max_events, -1.0,
                                           "content_embedding_json", event_ids=event_ids)

    def search_chunks_by_vector(self, source_ids, query_vector, top_k=10):
        if self._qdrant and query_vector:
            r = self._qdrant_find("chunk", source_ids, query_vector, top_k, -1)
            if r: return r
        if self._hv and query_vector:
            qv = _pg_vector_literal(query_vector)
            rows = self._s.exec(
                text("""SELECT *, 1-(content_embedding<=>:qv) AS score FROM graph_events
                    WHERE source_id=ANY(:s) AND content_embedding IS NOT NULL
                    AND deleted_at IS NULL ORDER BY content_embedding<=>:qv LIMIT :k"""),
                {"qv": qv, "s": source_ids, "k": top_k}
            ).mappings().all()
            return [{"chunk_id": r.get("chunk_id", ""), "source_id": r["source_id"],
                     "document_id": r.get("document_id"), "heading": r.get("title", ""),
                     "content": r.get("content", ""), "rank": r.get("rank", 0), "score": r["score"]}
                    for r in rows]
        results = []
        for ev in self._s.exec(select(GraphEventModel).where(
            col(GraphEventModel.source_id).in_(source_ids),
            col(GraphEventModel.content_embedding_json).is_not(None),
            col(GraphEventModel.deleted_at).is_(None),
        )).all():
            emb = _parse_json_vec(ev.content_embedding_json)
            if emb:
                results.append({"chunk_id": ev.chunk_id or "", "source_id": ev.source_id,
                    "document_id": ev.document_id, "heading": ev.title, "content": ev.content,
                    "rank": ev.rank, "score": _cosine_sim(query_vector, emb)})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ── pgvector 原生搜索 ─────────────────────────────────

    def _pg_entity_vector_search(self, source_ids, query_vector, top_k, threshold):
        qv = _pg_vector_literal(query_vector)
        rows = self._s.exec(
            text("""SELECT *, 1-(embedding<=>:qv) AS score FROM graph_entities
                WHERE source_id=ANY(:s) AND embedding IS NOT NULL
                AND 1-(embedding<=>:qv)>=:t ORDER BY embedding<=>:qv LIMIT :k"""),
            {"qv": qv, "s": source_ids, "t": threshold, "k": top_k}
        ).mappings().all()
        return [{"id": r["entity_id"], "source_id": r["source_id"], "type": r["type"],
                 "name": r["name"], "normalized_name": r["normalized_name"], "score": r["score"]}
                for r in rows]

    def _json_entity_fallback(self, source_ids, query_vector, top_k, threshold):
        results = []
        for r in self._s.exec(select(GraphEntityModel).where(
            col(GraphEntityModel.source_id).in_(source_ids),
            col(GraphEntityModel.embedding_json).is_not(None),
        )).all():
            emb = _parse_json_vec(r.embedding_json)
            if emb:
                sim = _cosine_sim(query_vector, emb)
                if sim >= threshold:
                    results.append({**_entity_dict(r), "score": sim})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _vector_search_events(self, source_ids, vec, top_k, threshold, emb_col,
                               event_ids: Optional[list[str]] = None):
        qv = _pg_vector_literal(vec)
        eid_filter = "AND event_id=ANY(:e)" if event_ids else ""
        th_filter = "AND 1-({col}<=>:qv)>=:t" if threshold >= 0 else ""
        sql = text(f"""SELECT *, 1-({emb_col}<=>:qv) AS score FROM graph_events
            WHERE source_id=ANY(:s) {eid_filter} AND {emb_col} IS NOT NULL {th_filter}
            AND deleted_at IS NULL ORDER BY {emb_col}<=>:qv LIMIT :k""")
        params: dict = {"qv": qv, "s": source_ids, "k": top_k}
        if threshold >= 0: params["t"] = threshold
        if event_ids: params["e"] = event_ids
        rows = self._s.exec(sql, params).mappings().all()
        return [{"id": r["event_id"], "source_id": r["source_id"], "document_id": r.get("document_id"),
                 "chunk_id": r.get("chunk_id"), "title": r["title"], "summary": r.get("summary", ""),
                 "content": r.get("content", ""), "rank": r.get("rank", 0), "score": r["score"]}
                for r in rows]

    def _json_fallback_events(self, source_ids, vec, top_k, threshold, json_col,
                               event_ids: Optional[list[str]] = None):
        stmt = select(GraphEventModel).where(
            col(GraphEventModel.source_id).in_(source_ids),
            col(getattr(GraphEventModel, json_col)).is_not(None),
            col(GraphEventModel.deleted_at).is_(None),
        )
        if event_ids: stmt = stmt.where(col(GraphEventModel.event_id).in_(event_ids))
        results = []
        for r in self._s.exec(stmt).all():
            emb = _parse_json_vec(getattr(r, json_col))
            sim = _cosine_sim(vec, emb) if emb else 0
            if threshold < 0 or sim >= threshold:
                results.append(_event_dict(r, sim))
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ── Qdrant 内部适配 ───────────────────────────────────

    def _qdrant_find(self, graph_type, source_ids, vec, top_k, threshold, event_ids=None):
        if not self._qdrant or not vec:
            return []
        try:
            hits = self._qdrant.search(query_vec=vec, k=top_k * 3)
        except Exception as e:
            logger.warning("Qdrant search failed: %s", e)
            return []
        results = []
        for h in hits:
            meta = h.get("metadata", {})
            if meta.get("graph_type") != graph_type: continue
            if source_ids and meta.get("source_id") not in source_ids: continue
            if threshold >= 0 and h.get("score", 0) < threshold: continue
            if event_ids and meta.get("id") not in event_ids: continue
            item = dict(meta); item["score"] = h.get("score", 0)
            results.append(item)
            if len(results) >= top_k: break
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    def _qdrant_index(self, graph_type, record_id, record, vector):
        if not self._qdrant or not record_id or not vector:
            return
        try:
            import uuid as _u
            pid = str(_u.uuid5(_u.NAMESPACE_DNS, f"{graph_type}:{record_id}"))
            payload = {"graph_type": graph_type, "id": record_id,
                        "source_id": record.get("source_id", ""),
                        "name": record.get("name", ""),
                        "type": record.get("type", ""),
                        "normalized_name": record.get("normalized_name", ""),
                        "title": record.get("title", ""),
                        "summary": record.get("summary", ""),
                        "chunk_id": record.get("chunk_id", ""),
                        "document_id": record.get("document_id"),
                        "rank": record.get("rank", 0),
                        "content": record.get("content", "")[:500]}
            self._qdrant.add(embeddings=[vector], doc_ids=[pid], payloads=[payload])
        except Exception as e:
            logger.warning("Qdrant index failed for %s: %s", graph_type, e)

    # ═══════════════════════════════════════════════════════
    #  写入 — PG 为主，Qdrant 同步索引
    # ═══════════════════════════════════════════════════════

    def upsert_event(self, **kwargs) -> dict:
        eid = kwargs.get("id") or kwargs.get("event_id", "")
        existing = self._s.exec(select(GraphEventModel).where(
            col(GraphEventModel.event_id) == eid)).first()
        title_emb = kwargs.get("title_embedding", [])
        content_emb = kwargs.get("content_embedding", [])
        if existing:
            for k in ("title", "summary", "content", "rank"):
                if k in kwargs: setattr(existing, k, kwargs[k])
        else:
            existing = GraphEventModel(event_id=eid or _new_uuid(),
                source_id=kwargs.get("source_id", ""), document_id=kwargs.get("document_id"),
                chunk_id=kwargs.get("chunk_id"), title=kwargs.get("title", ""),
                summary=kwargs.get("summary", ""), content=kwargs.get("content", ""),
                rank=kwargs.get("rank", 0))
        if title_emb: existing.title_embedding_json = json.dumps(title_emb)
        if content_emb: existing.content_embedding_json = json.dumps(content_emb)
        if self._hv:
            if title_emb: existing.title_embedding = _pg_vector_literal(title_emb)
            if content_emb: existing.content_embedding = _pg_vector_literal(content_emb)
        self._s.add(existing); self._s.commit()
        result = _event_dict(existing)
        # Qdrant 异步索引
        if self._qdrant and title_emb:
            self._qdrant_index("event_title", existing.event_id, result, title_emb)
        if self._qdrant and content_emb:
            self._qdrant_index("event_content", existing.event_id, result, content_emb)
        return result

    def upsert_entity(self, **kwargs) -> dict:
        name = kwargs.get("name", "").strip()
        eid = kwargs.get("entity_id") or kwargs.get("id", "")
        etype = kwargs.get("type", "concept")
        normalized = name.lower()
        sid = kwargs.get("source_id", "")
        existing = None
        if eid:
            existing = self._s.exec(select(GraphEntityModel).where(
                col(GraphEntityModel.entity_id) == eid)).first()
        if not existing:
            existing = self._s.exec(select(GraphEntityModel).where(
                col(GraphEntityModel.source_id) == sid,
                col(GraphEntityModel.normalized_name) == normalized,
                col(GraphEntityModel.type) == etype,
            )).first()
        if existing:
            existing.name = name
        else:
            existing = GraphEntityModel(entity_id=eid or _new_uuid(), source_id=sid,
                type=etype, name=name, normalized_name=normalized,
                description=kwargs.get("description", ""))
        emb = kwargs.get("embedding", [])
        if emb:
            existing.embedding_json = json.dumps(emb)
            if self._hv: existing.embedding = _pg_vector_literal(emb)
        self._s.add(existing); self._s.commit()
        result = _entity_dict(existing)
        if self._qdrant and emb:
            self._qdrant_index("entity", existing.entity_id, result, emb)
        return result

    def link_event_entity(self, event_id="", entity_id="", **kwargs):
        exists = self._s.exec(select(EventEntityLinkModel).where(
            col(EventEntityLinkModel.event_id) == event_id,
            col(EventEntityLinkModel.entity_id) == entity_id,
        )).first()
        if not exists:
            self._s.add(EventEntityLinkModel(event_id=event_id, entity_id=entity_id,
                         weight=kwargs.get("weight", 1.0)))
            self._s.commit()

    def add_chunk(self, chunk_id="", content="", source_id="", embedding=None, **kwargs):
        pass  # chunks 通过 events 存储

    def get_stats(self, source_id):
        ne = len(self._s.exec(select(GraphEventModel).where(
            col(GraphEventModel.source_id) == source_id,
            col(GraphEventModel.deleted_at).is_(None),
        )).all())
        nc = len(self._s.exec(select(GraphEntityModel).where(
            col(GraphEntityModel.source_id) == source_id
        )).all())
        return {"source_id": source_id, "event_count": ne, "entity_count": nc, "chunk_count": ne}
