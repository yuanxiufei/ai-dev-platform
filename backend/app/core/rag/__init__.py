"""
RAG — 检索增强生成系统

借鉴 AstrBot 架构精华：
- 混合检索: Dense (FAISS / 🆕 Qdrant) + Sparse (FTS5/BM25) → RRF 融合 → CrossEncoder Rerank
- 上下文压缩: 去重 + Token 感知裁剪 (3 种策略: truncate/head/hybrid)
- 多格式解析: txt / md / pdf / docx / xls / epub / url
- 插件式 Embedding: OpenAI / Ollama / 本地 BGE / 百炼
- 多知识库管理: 每 KB 独立索引 + FTS5
- 代码感知分块: Python AST + 通用多语言 + Markdown 结构
- SQLite 持久化: KB 元数据 + 文档追踪 + 多媒体管理
- LLM 文本修复: 噪音清洗 + 多主题拆分
- URL 导入: Tavily + 直接 HTTP 回退

向量存储:
- VectorStore (FAISS): 内存向量索引，适合开发/小规模
- 🆕 QdrantVectorStore: 持久化向量数据库，生产环境推荐

Pipeline:
  Upload → Parse → Clean(LLM) → Chunk → Embed → [FAISS/Qdrant + FTS5] → KB Ready
  Query  → Dense + Sparse → RRF → Rerank → Compress → Generate
"""

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

__version__ = "3.1.0"
