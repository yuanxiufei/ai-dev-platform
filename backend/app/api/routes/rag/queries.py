"""RAG 检索与生成查询"""

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
    filter_dict: Optional[dict] = None  # WhereFilter DSL


class RAGSearchRequest(BaseModel):
    query: str
    kb_ids: Optional[list[str]] = None
    top_k: int = 10
    filter_dict: Optional[dict] = None  # WhereFilter DSL


# ── RAG 全流程（检索+生成） ──────────────────────────────

@router.post("/query")
async def rag_query(body: RAGQueryRequest):
    """
    RAG 全流程: 检索 → 压缩 → 生成

    支持 WhereFilter 元数据过滤 DSL:
      { "source": "docs", "date": {"$gte": "2024-01-01"} }
    """
    from app.core.rag.rag_pipeline import RAGPipeline

    pipeline = RAGPipeline(max_context_tokens=body.max_context_tokens)
    result = await pipeline.query(
        question=body.question,
        kb_or_ids=body.kb_ids,
        top_k=body.top_k,
        include_sources=body.include_sources,
        max_context_tokens=body.max_context_tokens,
        filter_dict=body.filter_dict,
    )
    return result


# ── 纯检索（不生成回答） ─────────────────────────────────

@router.post("/search")
async def rag_search(body: RAGSearchRequest):
    """
    纯检索接口 — 返回相关文档块（不调用 LLM 生成），支持 WhereFilter

    Agent Tool: POST /agent/chat ← ToolRegistry 可封装此 API 为 rag_search tool
    """
    from app.core.rag.rag_pipeline import rag_search as _search

    results = await _search(
        query=body.query,
        kb_ids=body.kb_ids,
        top_k=body.top_k,
        filter_dict=body.filter_dict,
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

@router.get("/health")
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
