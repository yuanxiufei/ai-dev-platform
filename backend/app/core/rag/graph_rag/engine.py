"""
GraphRAG 多跳检索引擎

借鉴 SAG search-service.ts 的 multiSearch 算法:
  step1: 抽取/匹配查询实体 (fast:BM25 / standard:LLM)
  step2: 召回相关实体 (名称匹配 + 向量搜索)
  step3: 实体关联事件 + 标题向量召回事件
  step4: 读取候选事件详情
  step5: 沿 entity-event 关系多跳扩展
  step6: 按事件内容向量粗排
  step7: 精排 (rerank模型 / LLM rerank)
  step8: 回取关联切片
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from app.core.rag.graph_rag.models import (
    GraphEntity, GraphEvent, MultiHopOptions,
    SearchResult, SearchSection, SearchTrace,
    SearchTraceEvent,
)

logger = logging.getLogger("app.core.rag.graph_rag.engine")


class SearchMode(str, Enum):
    FAST = "fast"
    STANDARD = "standard"


class SubStrategy(str, Enum):
    MULTI = "multi"
    HOPLLM = "hopllm"


class ProgressStatus(str, Enum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class GraphRAGConfig:
    search_mode: SearchMode = SearchMode.STANDARD
    sub_strategy: SubStrategy = SubStrategy.MULTI
    return_trace: bool = False
    entity_top_k: int = 20
    multi_top_k: int = 20
    key_similarity_threshold: float = 0.9
    similarity_threshold: float = 0.4
    max_hops: int = 1
    max_events: int = 100
    max_events_a: int = 100
    max_events_b: int = 0
    max_hop_retries: int = 3
    rerank_top_k: int = 10
    max_sections: int = 10
    timeout_seconds: float = 30.0


class GraphRAGEngine:
    """GraphRAG 多跳检索引擎 —— 无状态算法，通过依赖注入对接后端"""

    def __init__(
        self,
        config: Optional[GraphRAGConfig] = None,
        embed_fn: Optional[Callable] = None,
        llm_extract_fn: Optional[Callable] = None,
        llm_rerank_fn: Optional[Callable] = None,
        rerank_model_fn: Optional[Callable] = None,
        db: Optional[Any] = None,  # GraphRepositoryPG(session) 或 GraphRepository()
        on_progress: Optional[Callable] = None,
    ):
        self.config = config or GraphRAGConfig()
        self._embed = embed_fn
        self._llm_extract = llm_extract_fn
        self._llm_rerank = llm_rerank_fn
        self._rerank_model = rerank_model_fn
        self._db = db
        self._on_progress = on_progress

    # ── 主入口 ───────────────────────────────────────────

    async def search(self, query: str, kb_ids: list[str],
                     options: Optional[MultiHopOptions] = None) -> SearchResult:
        cfg = self.config
        opts = options or self._build_options()
        trace_id = str(uuid.uuid4())
        timings: dict[str, float] = {}
        trace = SearchTrace(trace_id=trace_id, query=query, search_mode=cfg.search_mode.value)
        emit = self._on_progress

        # queryVector
        qv = await self._timed(timings, "queryEmbedding",
                               lambda: self._embed(query), emit,
                               {"t": "查询向量化", "d": "把用户问题转成向量"})

        # step1 & step2: 提取/匹配实体 + 召回
        recalled_entities, query_entities = await self._step_entities(
            query, kb_ids, opts, timings, trace, emit)

        # step3: 实体关联事件 + 标题向量召回
        ee_ids = await self._timed(timings, "step3EntityEvents",
            lambda: self._db_get("get_event_ids_by_entity_ids",
                entity_ids=[e.id for e in recalled_entities], source_ids=kb_ids),
            emit, {"t": "实体关联事件", "d": f"找到 {len(ee_ids or [])} 个"})
        trace.entity_event_ids = ee_ids or []

        q_events = (await self._timed(timings, "step3QueryEvents",
            lambda: self._db_get("search_events_by_title",
                source_ids=kb_ids, query_vector=qv,
                top_k=min(opts.multi_top_k * 3, 500),
                threshold=opts.similarity_threshold),
            emit, {"t": "标题向量召回事件", "d": "按查询向量召回标题相关事件"})) or []
        q_events = q_events[:opts.multi_top_k]
        trace.query_event_ids = [e.id for e in q_events]
        tq_evs = [_trace_event(e) for e in q_events]
        _append_snapshots(trace, tq_evs)

        # seed events
        seeds = _unique([*(ee_ids or []), *(e.id for e in q_events)])
        if not seeds:
            trace.fallback_reason = "no seed events; fallback to vector"
            fb = await self._vector_search(kb_ids, qv, opts.max_sections)
            if cfg.return_trace:
                fb.trace = trace
            return fb

        # step4: 事件详情
        seed_map = await self._timed(timings, "step4FetchDetails",
            lambda: self._db_get("get_events_with_entity_ids", event_ids=seeds),
            emit, {"t": "读取候选事件详情", "d": f"读取 {len(seeds)} 个"})
        seed_map = seed_map or {}

        # step5: 多跳扩展
        expanded = await self._expand(seed_map, [e.id for e in recalled_entities],
                                       kb_ids, qv, opts, timings, trace, emit)
        trace.expanded_event_ids = expanded["ids"]

        # step6: 粗排
        cr = await self._timed(timings, "step6CoarseRank",
            lambda: self._coarse_rank(cfg.sub_strategy, seeds, expanded,
                                      kb_ids, qv, opts),
            emit, {"t": "粗排事件", "d": "按内容向量相似度粗排"})
        trace.coarse_ranked_event_ids = [e.id for e in cr]
        tcr = [_trace_event(e) for e in cr]
        _append_snapshots(trace, tcr)

        # step7: 精排
        is_fast = cfg.search_mode == SearchMode.FAST
        sid = await self._timed(timings, "step7Rerank" if is_fast else "step7LlmRerank",
            lambda: self._do_rerank(query, cr, is_fast, opts.rerank_top_k),
            emit, {"t": "Rerank 重排", "d": "cc 模型排序" if is_fast else "LLM 重排"})
        if not sid:
            trace.fallback_reason = "rerank empty; used coarse rank"
            sid = [e.id for e in cr[:opts.rerank_top_k]]
        trace.reranked_event_ids = sid

        # step8: 回取切片
        sects = await self._timed(timings, "step8FetchChunks",
            lambda: self._sections_for_events(sid, cr, opts.max_sections),
            emit, {"t": "回取关联切片", "d": f"读取 {len(sid)} 个事件切片"})

        # 切片补全
        if len(sects) < opts.max_sections:
            sup = await self._db_get("search_chunks_by_vector",
                source_ids=kb_ids, query_vector=qv, top_k=opts.max_sections * 2)
            seen = {s.chunk_id for s in sects}
            for c in (sup or []):
                cid = c.get("chunk_id", c.get("chunkId", ""))
                if cid not in seen:
                    sects.append(self._dict_section(c))
                    seen.add(cid)
                    if len(sects) >= opts.max_sections:
                        break

        trace.timings = timings
        return SearchResult(trace_id=trace_id,
                            sections=sects[:opts.max_sections],
                            trace=trace if cfg.return_trace else None)

    # ── Step 1+2: 实体提取与召回 ─────────────────────────

    async def _step_entities(self, query, kb_ids, opts, timings, trace, emit):
        if self.config.search_mode == SearchMode.FAST:
            ents = await self._timed(timings, "step1Bm25Entities",
                lambda: self._db_get("search_entities_by_text",
                    source_ids=kb_ids, query=query, limit=opts.entity_top_k),
                emit, {"t": "BM25 匹配实体", "d": "全文匹配实体库"})
            ents = _to_entities(ents or [])
            trace.query_entities = [e.name for e in ents]
            return ents, trace.query_entities

        # Standard
        if not self._llm_extract:
            raise RuntimeError("llm_extract_fn required for standard mode")

        qe = await self._timed(timings, "step1ExtractEntities",
            lambda: self._llm_extract(query),
            emit, {"t": "LLM 抽取实体", "d": "识别关键实体"})
        trace.query_entities = qe or []

        ents = await self._timed(timings, "step2RetrieveEntities",
            lambda: self._retrieve_entities(qe or [], kb_ids, opts),
            emit, {"t": "召回相关实体", "d": "名称匹配+向量搜索"})

        trace.recalled_entities = [
            {"id": e.id, "name": e.name, "type": e.type, "score": e.score or 0}
            for e in ents
        ]
        return ents, qe or []

    async def _retrieve_entities(self, names, kb_ids, opts):
        if not names:
            return []
        exact = _to_entities(
            await self._db_get("search_entities_by_name",
                source_ids=kb_ids, names=names, limit=opts.entity_top_k) or [])
        bv: list[GraphEntity] = []
        if self._embed and self._db and hasattr(self._db, "search_entities_by_vector"):
            for name in names:
                try:
                    vec = await self._embed(name)
                    r = await self._db.search_entities_by_vector(
                        source_ids=kb_ids, query_vector=vec,
                        top_k=opts.entity_top_k,
                        threshold=opts.key_similarity_threshold)
                    bv.extend(_to_entities(r or []))
                except Exception as e:
                    logger.warning("Entity vector search '%s': %s", name, e)
        return _dedupe(exact + bv)

    # ── 步骤实现 ─────────────────────────────────────────

    async def _expand(self, seed_map, init_ent_ids, kb_ids, qv, opts, timings, trace, emit):
        if self.config.sub_strategy == SubStrategy.MULTI:
            return self._expand_fixed_hops(seed_map, init_ent_ids, kb_ids, opts.max_hops)

        # hopllm
        a = await self._expand_one_hot(seed_map, init_ent_ids, kb_ids, set(seed_map.keys()))
        tracked = _unique([*init_ent_ids, *a["eids"]])
        seed_b = a["events"]

        if self.config.sub_strategy == SubStrategy.HOPLLM:
            merged = _unique([*seed_map.keys(), *a["ids"]])
            ranked = await self._db_get("coarse_rank_events",
                source_ids=kb_ids, event_ids=merged,
                query_vector=qv, max_events=opts.max_events_a)
            if ranked:
                seed_b = await self._db_get("get_events_with_entity_ids",
                    event_ids=[e.id for e in ranked]) or {}

        b = await self._expand_dynamic(
            seed_b, tracked, kb_ids,
            set([*seed_map.keys(), *a["ids"]]),
            opts.max_events_b, opts.max_hop_retries)
        return {"ids": _unique([*a["ids"], *b["ids"]]),
                "eventset_ids": a["ids"], "eventset1_ids": b["ids"]}

    async def _expand_fixed_hops(self, seed_map, init_ents, kb_ids, max_hops):
        tracked_evs = set(seed_map.keys())
        tracked_ents = set(init_ents)
        current = seed_map
        expanded: list[str] = []
        for _ in range(max_hops):
            new_ents = _collect_new_ents(current, tracked_ents)
            tracked_ents.update(new_ents)
            if not new_ents:
                break
            new_evs = await self._db_get("get_event_ids_by_entity_ids",
                entity_ids=new_ents, source_ids=kb_ids,
                exclude_event_ids=list(tracked_evs)) or []
            if not new_evs:
                break
            tracked_evs.update(new_evs)
            expanded.extend(new_evs)
            current = await self._db_get("get_events_with_entity_ids",
                event_ids=new_evs) or {}
        return {"ids": expanded, "eventset_ids": expanded, "eventset1_ids": []}

    async def _expand_one_hot(self, seed_map, init_ents, kb_ids, exclude):
        tracked = set(init_ents)
        eids = _collect_new_ents(seed_map, tracked)
        ids = await self._db_get("get_event_ids_by_entity_ids",
            entity_ids=eids, source_ids=kb_ids,
            exclude_event_ids=list(exclude)) or []
        return {"ids": ids, "eids": eids,
                "events": await self._db_get("get_events_with_entity_ids",
                    event_ids=ids) or {}}

    async def _expand_dynamic(self, seed_map, init_ents, kb_ids, exclude, target, max_retries):
        if target == 0 or not seed_map:
            return {"ids": []}
        tracked = set(init_ents)
        collected: list[str] = []
        current = seed_map
        for _ in range(max_retries):
            new_ents = _collect_new_ents(current, tracked)
            tracked.update(new_ents)
            if not new_ents:
                break
            new_evs = await self._db_get("get_event_ids_by_entity_ids",
                entity_ids=new_ents, source_ids=kb_ids,
                exclude_event_ids=list(exclude) + collected) or []
            if not new_evs:
                break
            collected.extend(new_evs)
            if len(collected) >= target:
                break
            current = await self._db_get("get_events_with_entity_ids",
                event_ids=new_evs) or {}
        return {"ids": collected}

    async def _coarse_rank(self, strategy, seeds, expanded, kb_ids, qv, opts):
        if not self._db:
            return []
        if strategy == SubStrategy.MULTI:
            return await self._db_get("coarse_rank_events",
                source_ids=kb_ids,
                event_ids=_unique([*seeds, *expanded["eventset_ids"]]),
                query_vector=qv, max_events=opts.max_events) or []
        # hopllm
        a = await self._db_get("coarse_rank_events",
            source_ids=kb_ids,
            event_ids=_unique([*seeds, *expanded["eventset_ids"]]),
            query_vector=qv, max_events=opts.max_events_a) or []
        b = []
        if expanded.get("eventset1_ids") and opts.max_events_b > 0:
            b = await self._db_get("coarse_rank_events",
                source_ids=kb_ids, event_ids=expanded["eventset1_ids"],
                query_vector=qv, max_events=opts.max_events_b) or []
        return a + b

    async def _do_rerank(self, query, candidates, is_fast, top_k):
        cands = [{"id": e.id, "title": e.title, "summary": e.summary,
                   "content": e.content} for e in candidates]
        if is_fast and self._rerank_model:
            return await self._rerank_model(query=query, candidates=cands, top_k=top_k) or []
        if not is_fast and self._llm_rerank:
            return await self._llm_rerank(query=query, candidates=cands, top_k=top_k) or []
        return [e.id for e in candidates[:top_k]]

    async def _sections_for_events(self, event_ids, ranked, max_n):
        score_map = {e.id: (e.score or 0) for e in ranked}
        raw = await self._db_get("get_sections_for_events", event_ids=event_ids) or []
        seen: set[str] = set()
        sects: list[SearchSection] = []
        for r in raw:
            cid = r.get("chunk_id", r.get("chunkId", ""))
            if cid in seen:
                continue
            seen.add(cid)
            sects.append(SearchSection(
                chunk_id=cid,
                source_id=r.get("source_id", r.get("sourceId", "")),
                document_id=r.get("document_id", r.get("documentId")),
                heading=r.get("heading"),
                content=r.get("content", ""),
                rank=r.get("rank", 0),
                score=score_map.get(r.get("event_id", r.get("eventId", "")), 0),
                event_id=r.get("event_id", r.get("eventId")),
            ))
            if len(sects) >= max_n:
                break
        return sects

    async def _vector_search(self, kb_ids, qv, top_k):
        chunks = await self._db_get("search_chunks_by_vector",
            source_ids=kb_ids, query_vector=qv, top_k=top_k) or []
        return SearchResult(
            trace_id=str(uuid.uuid4()),
            sections=[self._dict_section(c) for c in chunks[:top_k]])

    # ── 工具方法 ─────────────────────────────────────────

    def _build_options(self):
        c = self.config
        return MultiHopOptions(
            sub_strategy=c.sub_strategy.value, entity_top_k=c.entity_top_k,
            multi_top_k=c.multi_top_k, key_similarity_threshold=c.key_similarity_threshold,
            similarity_threshold=c.similarity_threshold, max_hops=c.max_hops,
            max_events=c.max_events, max_events_a=c.max_events_a,
            max_events_b=c.max_events_b, max_hop_retries=c.max_hop_retries,
            rerank_top_k=c.rerank_top_k, max_sections=c.max_sections)

    async def _db_get(self, method: str, **kwargs):
        if not self._db:
            return None
        fn = getattr(self._db, method, None)
        if not fn:
            logger.warning("DB method '%s' not found", method)
            return None
        result = fn(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def _timed(self, timings, key, fn, emit, step_info):
        start = time.monotonic()
        try:
            r = fn()
            if asyncio.iscoroutine(r):
                r = await r
            timings[key] = round((time.monotonic() - start) * 1000, 2)
            return r
        except Exception as e:
            timings[key] = round((time.monotonic() - start) * 1000, 2)
            raise

    def _dict_section(self, d: dict) -> SearchSection:
        return SearchSection(
            chunk_id=d.get("chunk_id", d.get("chunkId", "")),
            source_id=d.get("source_id", d.get("sourceId", "")),
            document_id=d.get("document_id", d.get("documentId")),
            heading=d.get("heading"), content=d.get("content", ""),
            rank=d.get("rank", 0), score=d.get("score", 0))


# ── 纯函数辅助 ───────────────────────────────────────────

def _to_entities(rows: list[dict]) -> list[GraphEntity]:
    return [GraphEntity(
        id=r.get("id", ""), source_id=r.get("source_id", r.get("sourceId", "")),
        type=r.get("type", ""), name=r.get("name", ""),
        normalized_name=r.get("normalized_name", r.get("normalizedName", "")),
        score=r.get("score")) for r in rows]


def _dedupe(entities: list[GraphEntity]) -> list[GraphEntity]:
    seen, out = set(), []
    for e in entities:
        if e.id not in seen:
            seen.add(e.id)
            out.append(e)
    return out


def _unique(items: list) -> list:
    return list(dict.fromkeys(items))


def _collect_new_ents(events: dict[str, GraphEvent], tracked: set[str]) -> list[str]:
    ids = _unique([eid for e in events.values() for eid in e.entity_ids])
    return [i for i in ids if i not in tracked]


def _trace_event(e: GraphEvent) -> SearchTraceEvent:
    return SearchTraceEvent(
        id=e.id, title=e.title, summary=e.summary,
        content_preview=_preview(e.content or e.summary or e.title, 160),
        score=e.score)


def _append_snapshots(trace: SearchTrace, events: list[SearchTraceEvent]):
    by_id = {e.id: e for e in (trace.event_snapshots or [])}
    for e in events:
        by_id[e.id] = e
    trace.event_snapshots = list(by_id.values())


def _preview(text: str, limit: int) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:limit - 1] + "…" if len(cleaned) > limit else cleaned
