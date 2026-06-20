"""RAG 检索增强生成 — API 路由"""

from app.api.routes.rag.knowledge_bases import router as kb_router
from app.api.routes.rag.queries import router as query_router

__all__ = ["kb_router", "query_router"]
