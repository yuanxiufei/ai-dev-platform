"""RAG 检索与生成查询"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

router = APIRouter(prefix="/rag", tags=["RAG — 查询"])

logger = logging.getLogger("app.api.rag.query")


class RAGQueryRequest(BaseModel):
    question: str
    kb_ids: Optional[list[str]] = None
    top_k: int = 5
    max_context_tokens: int = 3000
    include_sources: bool = True


class RAGSearchRequest(BaseModel):
    query: str
    kb_ids: Optional[list[str]] = None
    top_k: int = 10


# ── RAG 全流程（检索+生成） ──────────────────────────────

@router.post("/rag/query")
async def rag_query(body: RAGQueryRequest):
    """
    RAG 全流程: 检索 → 压缩 → 生成

    返回结构:
      {
        "answer": str,
        "sources": [...],
        "context": str,
        "original_chunks": int,
        "final_chunks": int,
        "compressed": bool,
      }
    """
    from app.core.rag.rag_pipeline import RAGPipeline

    pipeline = RAGPipeline(max_context_tokens=body.max_context_tokens)
    result = await pipeline.query(
        question=body.question,
        kb_or_ids=body.kb_ids,
        top_k=body.top_k,
        include_sources=body.include_sources,
        max_context_tokens=body.max_context_tokens,
    )
    return result


# ── 纯检索（不生成回答） ─────────────────────────────────

@router.post("/rag/search")
async def rag_search(body: RAGSearchRequest):
    """
    纯检索接口 — 返回相关文档块（不调用 LLM 生成）

    作为 Agent Tool 使用:
      POST /agent/chat ← ToolRegistry 可封装此 API 为 rag_search tool
    """
    from app.core.rag.rag_pipeline import rag_search as _search

    results = await _search(
        query=body.query,
        kb_ids=body.kb_ids,
        top_k=body.top_k,
    )
    return {
        "data": [
            {
                "content": r.get("content", ""),
                "score": r.get("rerank_score", r.get("rrf_score", r.get("score", 0))),
                "source": r.get("metadata", {}).get("source", ""),
                "kb_name": r.get("kb_name", ""),
                "chunk_index": r.get("chunk_index", 0),
            }
            for r in results
        ],
        "total": len(results),
    }


# ── 健康探针 ─────────────────────────────────────────────

@router.get("/rag/health")
async def rag_health():
    """RAG 系统健康检查"""
    from app.core.rag.knowledge_base import get_knowledge_base

    mgr = get_knowledge_base()
    kbs = mgr.list_all()

    return {
        "status": "ok",
        "knowledge_bases": len(kbs),
        "kb_names": [kb.name for kb in kbs],
        "ready": True,
    }
