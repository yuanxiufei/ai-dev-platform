"""
RAG — 检索增强生成系统

借鉴 AstrBot + SAG (Zleap-AI) 架构精华：

传统管道:
  Upload → Parse → Clean(LLM) → Chunk → Embed → [FAISS/Qdrant + FTS5] → KB Ready
  Query  → Dense + Sparse → RRF → Rerank → Compress → Generate

GraphRAG (新增):
  Document → Chunk → Extract(events, entities) → Build Graph → KB Ready
  Query  → Entity Extract → Entity Recall → Event Search → Multi-hop Expand
        → Coarse Rank → Rerank → Fetch Sections → Answer

向量存储:
- VectorStore (FAISS): 内存向量索引，适合开发/小规模
- QdrantVectorStore: 持久化向量数据库，生产环境推荐
- GraphRepository: 事件-实体图存储 (内存实现)
"""

# 传统模块
from app.core.rag.vector_store import (  # noqa: F401
    VectorStore,
    DocumentStore,
    HybridStorage,
)
from app.core.rag.qdrant_store import (  # noqa: F401
    QdrantVectorStore,
    QdrantHybridStorage,
    create_qdrant_hybrid_storage,
)

# GraphRAG 模块 (新增)
from app.core.rag.graph_rag import (  # noqa: F401
    GraphRAGEngine,
    GraphRAGConfig,
    GraphBuilder,
    SearchMode,
    SubStrategy,
    GraphEvent,
    GraphEntity,
    EventEntityLink,
    SearchTrace,
    SearchTraceStep,
    SearchSection,
    SearchResult,
    MultiHopOptions,
    # 存储层
    GraphRepository,
    GraphRepositoryPG,
)

# 提取模块
from app.core.rag.extraction import (  # noqa: F401
    EventExtractor,
    EntityExtractor,
    create_event_extractor,
    create_entity_extractor,
)

# 追踪与降级
from app.core.rag.search_trace import SearchTracer  # noqa: F401
from app.core.rag.fallback import FallbackChain, FallbackResult  # noqa: F401

__version__ = "3.2.0"
