"""
Compound Vault — 借鉴 claude-obsidian 知识引擎

Anthropic Contextual Retrieval 模式 (Sept 2024):
  ingest:  page → contextual_prefix → bm25_index → embed_cache
  query:   query → bm25 → rerank → final top-k

三层前缀生成（借鉴 claude-obsidian）:
  Tier 1: OpenAI/Anthropic API → LLM 生成前缀（最佳质量，需要 API Key）
  Tier 2: 本地模型 → 通过 model_router 生成（免费，速度较慢）
  Tier 3: 合成前缀 → zero-cost 回退（标题 + 首段摘要）

关键设计:
- 上下文前缀让 chunk 在检索时携带文档级上下文
- Anthropic 测量降低 35-49% 检索失败率
- 纯 stdlib BM25 + 持久化磁盘索引 + 原子写入
- embedding 按 body_hash 缓存，并发安全
"""

from app.core.rag.compound.contextual_prefix import ContextualPrefixer, PrefixContext
from app.core.rag.compound.bm25_index import BM25IndexManager, BM25Index
from app.core.rag.compound.embed_cache import EmbeddingCache
from app.core.rag.compound.hot_cache import HotCache, HotCacheEntry

__all__ = [
    "ContextualPrefixer",
    "PrefixContext",
    "BM25IndexManager",
    "BM25Index",
    "EmbeddingCache",
    "HotCache",
    "HotCacheEntry",
]
