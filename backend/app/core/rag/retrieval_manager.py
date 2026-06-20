"""
检索引擎 — 混合检索编排器

全流程：
  Query → Embed → DenseSearch (FAISS) + SparseSearch (FTS5/BM25)
        → RRF Fusion → Rerank → Final Top-K

借鉴 AstrBot RetrievalManager：
- 协调多知识库独立检索 + 结果合并
- 优雅降级：FTS5 不可用→BM25；Rerank 失败→跳过
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.rag.config import get_rag_config
from app.core.rag.embedder import get_embedding_provider, BaseEmbeddingProvider
from app.core.rag.rank_fusion import RankFusion
from app.core.rag.reranker import get_reranker, BaseReranker
from app.core.rag.sparse_retriever import BM25SparseRetriever
from app.core.rag.vector_store import HybridStorage

logger = logging.getLogger("app.core.rag.retrieval")


class RetrievalManager:
    """
    混合检索编排器

    每个知识库的 HybridStorage 自行管理 Dense + Sparse 索引，
    RetrievalManager 负责跨 KB 的编排 + 融合 + Rerank。
    """

    def __init__(
        self,
        embedder: Optional[BaseEmbeddingProvider] = None,
        reranker: Optional[BaseReranker] = None,
    ):
        self._config = get_rag_config()
        self._embedder = embedder or get_embedding_provider()
        self._reranker = reranker or get_reranker()
        self._fusion = RankFusion(k=self._config.rrf_k)
        self._bm25_index: dict[str, BM25SparseRetriever] = {}  # KB name → BM25

    async def search(
        self,
        query: str,
        kb_storage: HybridStorage,
        top_k: int = 5,
    ) -> list[dict]:
        """
        对单个知识库执行混合检索

        流程:
          1. Query 向量化
          2. Dense: FAISS L2 搜索
          3. Sparse: FTS5 搜索（回退 BM25）
          4. RRF 融合
          5. Rerank 重排序
          6. 返回 top-k
        """
        # 1. 向量化
        query_vec = await self._embedder.embed(query)

        # 2. 稠密检索
        dense = kb_storage.dense_search(query_vec, k=self._config.dense_top_k)

        # 3. 稀疏检索
        sparse = kb_storage.sparse_search(query, limit=self._config.sparse_top_k)

        # FTS5 回退到 BM25
        if not sparse:
            sparse = await self._bm25_fallback(query, kb_storage)

        logger.debug("Retrieval: dense=%d sparse=%d", len(dense), len(sparse))

        # 4. RRF 融合
        fused = self._fusion.fuse(dense, sparse, top_k=self._config.fusion_top_k)

        # 5. Rerank
        if self._reranker and self._config.rerank_enabled and len(fused) > 1:
            try:
                fused = await self._reranker.rerank(
                    query, fused, top_k=self._config.rerank_top_k
                )
            except Exception as e:
                logger.warning("Rerank failed, using fusion results: %s", e)
                fused = fused[:top_k]
        else:
            fused = fused[:top_k]

        # 6. 格式化为最终结果
        return self._format_results(fused)

    async def search_multi(
        self,
        query: str,
        kb_storages: dict[str, HybridStorage],
        top_k: int = 5,
    ) -> list[dict]:
        """
        跨多知识库检索

        每个 KB 独立检索，结果合并后按分数排序。
        """
        all_results: list[dict] = []

        for kb_name, storage in kb_storages.items():
            try:
                results = await self.search(query, storage, top_k=top_k)
                for r in results:
                    r["kb_name"] = kb_name
                all_results.extend(results)
            except Exception as e:
                logger.error("KB '%s' search failed: %s", kb_name, e)

        # 按分数降序
        all_results.sort(
            key=lambda x: x.get("rerank_score", x.get("rrf_score", 0)),
            reverse=True,
        )
        return all_results[:top_k]

    async def _bm25_fallback(
        self, query: str, storage: HybridStorage
    ) -> list[dict]:
        """BM25 内存回退"""
        # 从存储中加载所有文档
        doc_ids = storage._doc_store.get_all_ids()
        texts = []
        for did in doc_ids[:500]:  # 限制 500 防止内存爆炸
            t = storage.get_text(did)
            if t:
                texts.append(t)

        if not texts:
            return []

        # 构建内存 BM25
        from app.core.rag.sparse_retriever import BM25SparseRetriever
        bm25 = BM25SparseRetriever()
        chunks = [{"text": t, "metadata": {"_doc_id": d}}
                  for t, d in zip(texts, doc_ids[:len(texts)])]
        bm25.index(chunks)
        return bm25.search(query, top_k=self._config.sparse_top_k)

    @staticmethod
    def _format_results(results: list[dict]) -> list[dict]:
        """格式化输出"""
        formatted = []
        for r in results:
            formatted.append({
                "content": r.get("content", ""),
                "score": r.get("rerank_score", r.get("rrf_score", r.get("score", 0))),
                "metadata": r.get("metadata", {}),
                "doc_id": r.get("doc_id", ""),
                "rank": len(formatted) + 1,
            })
        return formatted


# ── 全局单例 ──────────────────────────────────────────────

_global_retriever: Optional[RetrievalManager] = None


def init_retrieval_manager() -> RetrievalManager:
    global _global_retriever
    _global_retriever = RetrievalManager()
    return _global_retriever


def get_retrieval_manager() -> RetrievalManager:
    if _global_retriever is None:
        return init_retrieval_manager()
    return _global_retriever
