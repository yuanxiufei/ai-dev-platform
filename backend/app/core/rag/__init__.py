"""
RAG — 检索增强生成系统

借鉴 AstrBot + SAG (Zleap-AI) 架构精华：

传统管道:
  Upload → Parse → Clean(LLM) → Chunk → Embed → [FAISS/Qdrant + tsvector] → KB Ready
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

# 数据模型
from app.core.rag.models import (  # noqa: F401
    KnowledgeBase,
    KBDocument,
    KBMedia,
    Segment,
    KBJob,
)

# 传统模块
from app.core.rag.vector_store import (  # noqa: F401
    VectorStore,
    DocumentStore,
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

# Dify 知识桥接
from app.core.rag.dify_bridge import (  # noqa: F401
    DifyKnowledgeBridge,
    DifyChunk,
    ImportStats,
    WeaviateExtractor,
    DifyAPIExtractor,
    FileImporter,
    import_dify_to_kb,
)

# MinerU 批量文档解析器 (可选依赖)
try:
    from app.core.rag.parsers.mineru_parser import (  # noqa: F401
        MinerUParser,
        MinerUConfig,
        MinerUResult,
        get_mineru_parser,
    )
    _MINERU_AVAILABLE = True
except ImportError:
    _MINERU_AVAILABLE = False

# 多策略网页爬取系统
from app.core.rag.crawler import (  # noqa: F401
    CrawlPipeline,
    CrawlConfig,
    CrawlScheduler,
    get_pipeline,
    # 策略
    StrategyRegistry,
    StaticCrawlerStrategy,
    DynamicCrawlerStrategy,
    APICrawlerStrategy,
    SitemapCrawlerStrategy,
    FeedCrawlerStrategy,
    create_registry,
    # 基础设施
    AntiDetectEngine,
    RobotsParser,
    SimHashDeduper,
    ContentScorer,
    RetryManager,
    HTMLCleaner,
    # 类型
    CrawlTask,
    PageResult,
    BatchResult,
    CrawlProgress,
    StrategyType,
    TaskPriority,
    # OCR 插件 (可选)
    OcrConfig,
    OcrPageResult,
)

# Segment 抽象层 (Phase 3 — 借鉴 Chroma)
from app.core.rag.segments import (  # noqa: F401
    Segment,
    SegmentManager,
    register_segment,
    get_segment_class,
    list_segment_types,
)

# RAPTOR 摘要树 (Phase 3)
# from app.core.rag.raptor import RaptorSummarizer, RaptorTree, RaptorConfig  # 待实现

__version__ = "3.5.0"
