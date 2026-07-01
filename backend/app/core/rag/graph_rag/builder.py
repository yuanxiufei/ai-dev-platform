"""
GraphBuilder — 从文档切片构建事件-实体图

借鉴 SAG ingestion-service.ts + extractor.ts:
  Input: 文档切片 (chunks) + 嵌入向量
  Process:
    1. 对每个 chunk 用 LLM 提取事件 (title, summary, entities)
    2. 对提取的实体做归一化 (trim + lowercase + dedupe)
    3. 生成事件 & 实体的嵌入向量
    4. 写入存储 (events, entities, event_entities 表)
    5. 返回统计信息
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.core.rag.graph_rag.models import GraphEntity, GraphEvent

logger = logging.getLogger("app.core.rag.graph_rag.builder")


@dataclass
class BuildResult:
    """图构建结果统计"""
    chunks_processed: int = 0
    events_created: int = 0
    entities_created: int = 0
    links_created: int = 0
    errors: list[str] = field(default_factory=list)
    latency_ms: float = 0


class GraphBuilder:
    """
    事件-实体图构建器

    依赖注入:
      - llm_fn: (chunk_text: str) -> EventExtraction
      - embed_fn: (text: str) -> list[float]
      - db: GraphRepository (upsert_event, upsert_entity, link_event_entity)
    """

    def __init__(
        self,
        llm_fn: Optional[Callable] = None,
        embed_fn: Optional[Callable] = None,
        batch_embed_fn: Optional[Callable] = None,
        db: Optional[Any] = None,
        max_concurrency: int = 3,
    ):
        self._llm = llm_fn
        self._embed = embed_fn
        self._batch_embed = batch_embed_fn
        self._db = db
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def build_from_chunks(
        self,
        chunks: list[dict],
        kb_id: str,
        document_id: Optional[str] = None,
    ) -> BuildResult:
        """
        从切片列表构建事件-实体图

        Args:
            chunks: [{"chunk_id": str, "content": str, "heading": str, "rank": int}, ...]
            kb_id: 知识库 ID
            document_id: 可选父文档 ID

        Returns:
            BuildResult 构建统计
        """
        import time
        start = time.monotonic()
        result = BuildResult(chunks_processed=len(chunks))

        if not self._llm:
            result.errors.append("llm_fn not configured")
            return result

        # 并发处理每个 chunk
        tasks = [self._process_chunk(c, kb_id, document_id) for c in chunks]
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        for i, outcome in enumerate(outcomes):
            if isinstance(outcome, Exception):
                err = f"Chunk[{i}]: {outcome}"
                result.errors.append(err)
                logger.warning(err)
            elif outcome:
                ev, entities, links = outcome
                result.events_created += 1
                result.entities_created += len(entities)
                result.links_created += len(links)

        result.latency_ms = round((time.monotonic() - start) * 1000, 2)
        logger.info(
            "GraphBuilder: %d chunks → %d events, %d entities, %d links (%.0fms)",
            result.chunks_processed, result.events_created,
            result.entities_created, result.links_created, result.latency_ms,
        )
        return result

    async def _process_chunk(
        self, chunk: dict, kb_id: str, document_id: Optional[str]
    ) -> Optional[tuple]:
        """处理单个 chunk: LLM 提取 → 生成嵌入 → 写入存储"""
        async with self._semaphore:
            content = chunk.get("content", "")
            if not content or len(content.strip()) < 10:
                return None

            # 1. LLM 提取事件和实体
            extraction = await self._llm(content)
            if not extraction or not extraction.get("title"):
                return None

            event_id = str(uuid.uuid4())
            title = extraction.get("title", content[:80])
            summary = extraction.get("summary", title)
            raw_entities = extraction.get("entities", [])

            # 2. 归一化实体
            normalized_entities = self._normalize_entities(raw_entities, kb_id)

            # 3. 生成嵌入
            event_title_vec = await self._embed(title) if self._embed else []
            # 实体批量嵌入
            entity_texts = [e["name"] for e in normalized_entities]
            entity_vecs = []
            if entity_texts and self._embed:
                if self._batch_embed:
                    entity_vecs = await self._batch_embed(entity_texts)
                else:
                    entity_vecs = [await self._embed(t) for t in entity_texts]

            for i, vec in enumerate(entity_vecs):
                normalized_entities[i]["embedding"] = vec

            # 4. 写入存储
            if self._db:
                await self._db_write("upsert_event", id=event_id, source_id=kb_id,
                    document_id=document_id, chunk_id=chunk.get("chunk_id"),
                    title=title, summary=summary, content=content,
                    rank=chunk.get("rank", 0),
                    title_embedding=event_title_vec)
                for ent in normalized_entities:
                    await self._db_write("upsert_entity",
                        source_id=kb_id, type=ent.get("type", "concept"),
                        name=ent["name"], embedding=ent.get("embedding", []),
                        entity_id=ent.get("id"))
                    await self._db_write("link_event_entity",
                        event_id=event_id, entity_id=ent.get("id", ""))

            return (event_id, normalized_entities,
                    [(event_id, e.get("id", "")) for e in normalized_entities])

    def _normalize_entities(self, raw_entities: list[dict], kb_id: str) -> list[dict]:
        """实体归一化: 去重 + 生成 ID"""
        seen: dict[str, dict] = {}
        for ent in raw_entities:
            name = (ent.get("name", "") or "").strip()
            if not name:
                continue
            key = (name.lower(), ent.get("type", "concept"))
            if key not in seen:
                seen[key] = {
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "type": ent.get("type", "concept"),
                    "normalized_name": name.lower(),
                    "source_id": kb_id,
                }
        return list(seen.values())

    async def _db_write(self, method: str, **kwargs):
        fn = getattr(self._db, method, None)
        if fn:
            r = fn(**kwargs)
            if asyncio.iscoroutine(r):
                return await r
            return r
        return None
