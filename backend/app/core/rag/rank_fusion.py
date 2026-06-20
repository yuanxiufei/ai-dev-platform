"""
RRF 结果融合 — Reciprocal Rank Fusion

公式：
  RRF_score(d) = Σ 1/(k + rank_i(d))

借鉴 AstrBot RankFusion:
- 融合稠密检索和稀疏检索的结果列表
- k 值控制排名的权重衰减
"""

from __future__ import annotations

import logging

logger = logging.getLogger("app.core.rag.rank_fusion")


class RankFusion:
    """RRF 结果融合器"""

    def __init__(self, k: int = 60):
        """
        Args:
            k: RRF 平滑常数。默认 60（经典值）
               - k 越大，排名靠后的文档权重越大
               - k 越小，排名越关键
        """
        self.k = k

    def fuse(
        self,
        dense_results: list[dict],
        sparse_results: list[dict],
        top_k: int = 10,
    ) -> list[dict]:
        """
        融合稠密和稀疏检索结果

        Args:
            dense_results: [{"doc_id": ..., "content": ..., "score": ..., "metadata": ...}, ...]
            sparse_results: 同上
            top_k: 返回 top-k 结果

        Returns:
            融合后的结果列表，按 RRF 分数降序
        """
        # 收集所有文档
        doc_map: dict[str, dict] = {}
        rrf_scores: dict[str, float] = {}

        # 稠密检索排名
        for rank, item in enumerate(dense_results):
            doc_id = item["doc_id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + self._rrf_score(rank)
            doc_map[doc_id] = item

        # 稀疏检索排名
        for rank, item in enumerate(sparse_results):
            doc_id = item["doc_id"]
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + self._rrf_score(rank)
            if doc_id not in doc_map:
                doc_map[doc_id] = item

        # 按 RRF 分数排序
        sorted_docs = sorted(
            rrf_scores.items(), key=lambda x: x[1], reverse=True
        )[:top_k]

        # 构建结果
        results = []
        for doc_id, rrf_score in sorted_docs:
            doc = doc_map[doc_id].copy()
            doc["rrf_score"] = rrf_score
            doc["rrf_rank"] = len(results) + 1
            results.append(doc)

        logger.debug("RRF: dense=%d + sparse=%d → fused=%d",
                     len(dense_results), len(sparse_results), len(results))
        return results

    def _rrf_score(self, rank: int) -> float:
        """单路 RRF 分数"""
        return 1.0 / (self.k + rank + 1)  # rank 从 0 开始，+1 转 1-based
