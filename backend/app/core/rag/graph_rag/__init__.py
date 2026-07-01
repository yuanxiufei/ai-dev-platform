"""
GraphRAG — 事件-实体多跳检索引擎

借鉴 SAG (Zleap-AI/SAG) 架构:
  - 三层索引: chunk → event → entity
  - 双模式检索: fast (BM25) / standard (LLM 实体抽取)
  - 多跳扩展: 沿 entity-event 关系图多跳遍历
  - SearchTrace: 每步耗时 + 中间结果全量追踪
  - 智能降级: 无 seed events → 回退纯向量搜索

存储 (PG 一把梭, Qdrant 透明加速):
  GraphRepositoryPG(session)
    ├── 关系查询: PG SQL JOIN / ILIKE (始终)
    ├── 向量搜索: Qdrant → pgvector → JSON (自动回退)
    └── Qdrant: 设置 QDRANT_URL 环境变量自动启用

用法:
    from app.core.rag.graph_rag import GraphRAGEngine, GraphRAGConfig, GraphRepositoryPG

    store = GraphRepositoryPG(session)
    engine = GraphRAGEngine(config=GraphRAGConfig(), db=store)
    result = await engine.search(query="如何优化数据库性能？", kb_ids=["kb_abc123"])
"""

from app.core.rag.graph_rag.models import (  # noqa: F401
    GraphEvent, GraphEntity, EventEntityLink,
    SearchTrace, SearchTraceStep, SearchSection, SearchResult, MultiHopOptions,
)
from app.core.rag.graph_rag.engine import (  # noqa: F401
    GraphRAGEngine, GraphRAGConfig, SearchMode, SubStrategy,
)
from app.core.rag.graph_rag.builder import GraphBuilder  # noqa: F401
from app.core.rag.graph_rag.repository import (  # noqa: F401
    GraphRepository,
    GraphEntityModel, GraphEventModel, EventEntityLinkModel, MCPToolCallModel,
)
from app.core.rag.graph_rag.repository_pg import GraphRepositoryPG  # noqa: F401

__version__ = "2.0.0"
