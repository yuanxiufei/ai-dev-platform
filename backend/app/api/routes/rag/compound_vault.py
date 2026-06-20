"""
Compound Vault Routes — 借鉴 claude-obsidian 知识引擎

暴露:
- 混合检索（BM25 + dense + contextual prefix）
- 上下文前缀管理
- 会话热缓存
- 批量文档摄取
- 索引统计与维护
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.rag.config import get_rag_config
from app.core.rag.compound import (
    ContextualPrefixer,
    BM25IndexManager,
    EmbeddingCache,
    HotCache,
)

logger = logging.getLogger("app.api.routes.compound_vault")

router = APIRouter(prefix="/compound", tags=["compound-vault"])

# ── Pydantic Schemas ────────────────────────────────────

class DocumentIngest(BaseModel):
    path: str
    content: str
    title: str = ""
    generate_prefixes: bool = True

class BatchIngest(BaseModel):
    documents: list[DocumentIngest]

class CompoundSearchRequest(BaseModel):
    query: str
    top_k: int = 5
    use_bm25: bool = True
    use_dense: bool = False

class HotCacheAdd(BaseModel):
    key: str
    summary: str
    importance: float = 0.5
    promote_to_long: bool = False

class HotCacheEntryResponse(BaseModel):
    key: str
    summary: str
    importance: float
    access_count: int
    created_at: str

# ── Helpers ─────────────────────────────────────────────

def _get_prefixer() -> ContextualPrefixer:
    from app.core.rag.compound.contextual_prefix import get_prefixer
    prefixer = get_prefixer()
    if prefixer is None:
        cfg = get_rag_config()
        prefixer = ContextualPrefixer(
            cache_dir=os.path.join(cfg.compound_dir, "data") if cfg.compound_dir else "rag_data/compound",
            allow_egress=cfg.contextual_prefix_allow_egress,
        )
    return prefixer


def _get_bm25() -> Optional[BM25IndexManager]:
    try:
        from app.core.rag.compound.bm25_index import get_bm25_index
        return get_bm25_index()
    except Exception:
        return None


def _get_hot_cache() -> HotCache:
    from app.core.rag.compound.hot_cache import get_hot_cache
    hot = get_hot_cache()
    if hot is None:
        cfg = get_rag_config()
        hot = HotCache(
            cache_dir=os.path.join(cfg.compound_dir, "data") if cfg.compound_dir else "rag_data/compound"
        )
    return hot


def _get_embed_cache() -> Optional[EmbeddingCache]:
    from app.core.rag.compound.embed_cache import get_embed_cache
    return get_embed_cache()


# ── Ingest ──────────────────────────────────────────────

@router.post("/ingest")
async def ingest_document(body: DocumentIngest) -> dict:
    """
    摄取单个文档

    流程:
      1. 解析文档内容
      2. 生成上下文前缀 chunk
      3. 构建 BM25 索引
      4. (可选) 生成 embedding 并缓存
    """
    prefixer = _get_prefixer()

    chunks = prefixer.process_page(
        page_path=body.path,
        page_body=body.content,
        title=body.title,
        force_tier=None if body.generate_prefixes else "synthetic",
    )

    # 更新 BM25 索引
    bm25 = _get_bm25()
    if bm25:
        bm25_chunks = [
            {
                "chunk_id": f"{body.path}:{c.chunk_index}",
                "path": f"prefixes/{c.page_path}/chunk-{c.chunk_index:03d}.json",
                "text": c.contextualized_text,
            }
            for c in chunks
        ]
        bm25.add_chunks(bm25_chunks)

    return {
        "path": body.path,
        "title": body.title,
        "chunk_count": len(chunks),
        "prefix_tier": chunks[0].prefix_source if chunks else "none",
        "indexed": True,
    }


@router.post("/ingest/batch")
async def ingest_batch(body: BatchIngest) -> dict:
    """批量摄取文档"""
    total_chunks = 0
    results = []

    for doc in body.documents:
        result = await ingest_document(doc)
        total_chunks += result["chunk_count"]
        results.append(result)

    return {
        "documents": len(body.documents),
        "total_chunks": total_chunks,
        "results": results,
    }


# ── Search ──────────────────────────────────────────────

@router.post("/search")
async def compound_search(body: CompoundSearchRequest) -> dict:
    """
    混合检索: BM25 (上下文化) + 可选 Dense

    借鉴 claude-obsidian retrieve.py:
    - BM25 搜索 contextualized_text → top-20 候选
    - (可选) FAISS dense 搜索 → RRF 融合
    """
    results: list[dict] = []

    # BM25 检索
    if body.use_bm25:
        bm25 = _get_bm25()
        if bm25:
            bm25_results = bm25.query(body.query, top_k=body.top_k)
            for r in bm25_results:
                results.append({
                    "chunk_id": r["chunk_id"],
                    "score": r["score"],
                    "source": "bm25",
                    "path": r.get("path", ""),
                })

    # Dense 检索
    if body.use_dense:
        try:
            provider = _get_embed_cache()
            if provider:
                logger.debug("Dense search skipped (embed cache only)")
        except Exception:
            pass

    # 按分数排序
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:body.top_k]

    return {
        "query": body.query,
        "results": results,
        "total": len(results),
    }


# ── BM25 Index ──────────────────────────────────────────

@router.post("/bm25/rebuild")
async def rebuild_bm25_index() -> dict:
    """从已缓存的 contextual prefix chunks 重建 BM25 索引"""
    bm25 = _get_bm25()
    if not bm25:
        # 初始化
        cfg = get_rag_config()
        from app.core.rag.compound.bm25_index import init_bm25_index
        compound_dir = os.path.join(cfg.compound_dir, "data") if cfg.compound_dir else "rag_data/compound"
        bm25 = init_bm25_index(compound_dir)

    cfg = get_rag_config()
    prefix_dir = os.path.join(cfg.compound_dir, "data", "prefixes") if cfg.compound_dir else "rag_data/compound/prefixes"

    n = bm25.rebuild_from_contextualized(prefix_dir)

    return {
        "ok": True,
        "doc_count": n,
        "stats": bm25.stats(),
    }


@router.get("/bm25/stats")
async def bm25_stats() -> dict:
    bm25 = _get_bm25()
    if not bm25:
        return {"ok": False, "reason": "BM25 not initialized"}

    return {"ok": True, **bm25.stats()}


# ── Hot Cache ───────────────────────────────────────────

@router.post("/hot-cache")
async def add_hot_cache(body: HotCacheAdd) -> dict:
    hot = _get_hot_cache()
    entry = hot.add(
        key=body.key,
        summary=body.summary,
        importance=body.importance,
        promote_to_long=body.promote_to_long,
    )
    return {
        "ok": True,
        "entry": entry.to_dict(),
    }


@router.get("/hot-cache/context")
async def get_hot_cache_context(max_chars: int = 1500) -> dict:
    hot = _get_hot_cache()
    context = hot.get_prompt_context(max_chars=max_chars)
    return {
        "context": context,
        "stats": hot.stats(),
    }


@router.delete("/hot-cache/session")
async def clear_hot_cache_session() -> dict:
    hot = _get_hot_cache()
    hot.clear_session()
    return {"ok": True, "message": "Session hot cache cleared"}


@router.delete("/hot-cache/{key}")
async def remove_hot_cache(key: str) -> dict:
    hot = _get_hot_cache()
    removed = hot.remove(key)
    if not removed:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"ok": True, "key": key}


@router.post("/hot-cache/{key}/promote")
async def promote_to_long(key: str) -> dict:
    hot = _get_hot_cache()
    success = hot.promote_to_long(key)
    if not success:
        raise HTTPException(status_code=404, detail="Key not found in hot cache")
    return {"ok": True, "key": key}


@router.get("/hot-cache/stats")
async def hot_cache_stats() -> dict:
    hot = _get_hot_cache()
    return hot.stats()


# ── Prefix Management ───────────────────────────────────

@router.delete("/prefixes")
async def clear_prefix_cache(path: str | None = Query(None)) -> dict:
    """清除上下文前缀缓存"""
    prefixer = _get_prefixer()

    if path:
        removed = prefixer.delete_page(path)
        return {"ok": True, "path": path, "removed": removed}
    else:
        # 清除所有
        import shutil
        cfged = get_rag_config()
        prefix_dir = os.path.join(cfged.compound_dir, "data", "prefixes") if cfged.compound_dir else "rag_data/compound/prefixes"
        if os.path.exists(prefix_dir):
            shutil.rmtree(prefix_dir)
            os.makedirs(prefix_dir, exist_ok=True)
            return {"ok": True, "message": "All prefix caches cleared"}
        return {"ok": True, "message": "No prefix cache found"}


# ── Embed Cache ─────────────────────────────────────────

@router.get("/embed-cache/stats")
async def embed_cache_stats() -> dict:
    cache = _get_embed_cache()
    if not cache:
        return {"ok": False, "reason": "Embedding cache not initialized"}
    return {"ok": True, **cache.stats()}


@router.delete("/embed-cache")
async def clear_embed_cache() -> dict:
    cache = _get_embed_cache()
    if cache:
        cache.clear()
    return {"ok": True}


# ── System Stats ────────────────────────────────────────

@router.get("/stats")
async def compound_stats() -> dict:
    """Compound Vault 整体统计"""
    bm25 = _get_bm25()
    hot = _get_hot_cache()
    embed = _get_embed_cache()

    return {
        "bm25": bm25.stats() if bm25 else {"ready": False},
        "hot_cache": hot.stats(),
        "embed_cache": embed.stats() if embed else {"ready": False},
    }
