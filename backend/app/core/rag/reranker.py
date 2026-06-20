"""
重排序器 — CrossEncoder 本地 vs API

借鉴 AstrBot RerankProvider:
- 本地: BGE-Reranker (CrossEncoder)
- 远程: OpenAI 兼容 / 百炼 Rerank API
- 降级: Rerank 失败时跳过，使用融合结果
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

logger = logging.getLogger("app.core.rag.reranker")


class BaseReranker(ABC):
    """Rerank Provider 抽象基类"""

    @abstractmethod
    async def rerank(
        self, query: str, documents: list[dict], top_k: int = 5
    ) -> list[dict]:
        """重排序文档"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Reranker 名称"""


class CrossEncoderReranker(BaseReranker):
    """本地 CrossEncoder 重排序器"""

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cpu",
    ):
        self._model_name = model_name
        self._device = device
        self._model = None

    @property
    def name(self) -> str:
        return "cross_encoder"

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(
                    self._model_name, device=self._device,
                )
                logger.info("Loaded CrossEncoder: %s", self._model_name)
            except Exception as e:
                logger.error("Failed to load CrossEncoder: %s", e)
                raise

    async def rerank(
        self, query: str, documents: list[dict], top_k: int = 5
    ) -> list[dict]:
        if not documents:
            return []

        self._load()

        # 构建 query-doc 对
        pairs = [(query, doc["content"]) for doc in documents]
        scores = self._model.predict(pairs)

        # 归一化
        max_s = max(scores) if len(scores) > 0 else 1.0
        min_s = min(scores) if len(scores) > 0 else 0.0
        score_range = max_s - min_s or 1.0

        # 排序
        ranked = []
        for i, score in enumerate(scores):
            normalized = float((score - min_s) / score_range)
            doc = documents[i].copy()
            doc["rerank_score"] = normalized
            ranked.append(doc)

        ranked.sort(key=lambda x: x["rerank_score"], reverse=True)
        return ranked[:top_k]


class OpenAIReranker(BaseReranker):
    """OpenAI 兼容 Rerank API"""

    def __init__(
        self,
        api_base: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "text-embedding-3-small",
    ):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return "openai_rerank"

    async def rerank(
        self, query: str, documents: list[dict], top_k: int = 5
    ) -> list[dict]:
        """通过 embedding 相似度做 rerank（OpenAI 无原生 rerank API）"""
        from app.core.rag.embedder import OpenAIEmbeddingProvider

        embedder = OpenAIEmbeddingProvider(
            api_base=self._api_base,
            api_key=self._api_key,
            model=self._model,
        )

        query_vec = np.array(await embedder.embed(query))
        doc_texts = [d["content"] for d in documents]
        doc_vecs = [np.array(v) for v in await embedder.embed_batch(doc_texts)]

        # 余弦相似度
        query_norm = np.linalg.norm(query_vec)
        scored = []
        for i, dv in enumerate(doc_vecs):
            sim = float(np.dot(query_vec, dv) / (query_norm * np.linalg.norm(dv) + 1e-8))
            doc = documents[i].copy()
            doc["rerank_score"] = max(0.0, sim)
            scored.append(doc)

        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:top_k]


# ── 工厂 ──────────────────────────────────────────────────

_global_reranker: Optional[BaseReranker] = None


def init_reranker(config=None) -> BaseReranker:
    global _global_reranker
    if config is None:
        from app.core.rag.config import get_rag_config
        config = get_rag_config()

    if config.rerank_provider == "none":
        _global_reranker = None
        return None

    if config.rerank_provider == "openai":
        _global_reranker = OpenAIReranker(
            api_base=config.embedding_api_base,
            api_key=config.embedding_api_key,
            model=config.embedding_api_model,
        )
    else:
        _global_reranker = CrossEncoderReranker(
            model_name=config.rerank_model,
            device=config.rerank_device,
        )

    logger.info("Reranker initialized: %s", _global_reranker.name)
    return _global_reranker


def get_reranker() -> Optional[BaseReranker]:
    if _global_reranker is None:
        return init_reranker()
    return _global_reranker
