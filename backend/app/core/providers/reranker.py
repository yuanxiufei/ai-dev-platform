"""
Rerank Provider 抽象 —— 文档重排序

借鉴 AstrBot RerankProvider 设计:
- RerankProvider: 抽象基类
- CrossEncoderReranker: BGE-Reranker 本地
- OpenAIReranker: OpenAI 兼容 API
- 支持批量分片 + 级联降级
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger("providers.reranker")


# ── 结果类型 ─────────────────────────────────────────────────


@dataclass
class RerankResult:
    """重排序结果"""
    index: int
    content: str
    score: float
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


# ── 抽象基类 ─────────────────────────────────────────────────


class RerankProvider(ABC):
    """
    文档重排序 Provider 抽象

    借鉴 AstrBot RerankProvider，定义:
    - rerank(query, documents, top_n) → list[RerankResult]

    RAG pipeline 在 RRF 融合后使用此 Provider 进行精排。
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        """重排序文档"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        ...

    async def rerank_with_metadata(
        self,
        query: str,
        documents: list[dict],
        top_n: int | None = None,
        content_key: str = "content",
    ) -> list[dict]:
        """
        重排序带元数据的文档

        将文档列表按 content_key 提取文本 → rerank → 合并回元数据。
        """
        texts = [d.get(content_key, "") for d in documents]
        results = await self.rerank(query, texts, top_n)

        ranked = []
        for r in results:
            doc = documents[r.index].copy()
            doc["rerank_score"] = r.score
            doc["rerank_rank"] = r.index
            ranked.append(doc)
        return ranked

    async def test(self) -> bool:
        """健康检查"""
        try:
            results = await self.rerank(
                "Apple", ["apple fruit", "banana fruit", "computer brand"], top_n=2,
            )
            return len(results) > 0
        except Exception as e:
            logger.error("RerankProvider '%s' test failed: %s", self.name, e)
            return False


# ── CrossEncoder 本地 ────────────────────────────────────────


class CrossEncoderReranker(RerankProvider):
    """本地 CrossEncoder 重排序器 (BGE-Reranker)"""

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
                self._model = CrossEncoder(self._model_name, device=self._device)
                logger.info("Loaded CrossEncoder: %s", self._model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not documents:
            return []

        self._load()
        loop = asyncio.get_event_loop()
        pairs = [(query, doc) for doc in documents]

        scores = await loop.run_in_executor(
            None, lambda: self._model.predict(pairs)
        )

        # 归一化
        max_s = float(max(scores)) if len(scores) > 0 else 1.0
        min_s = float(min(scores)) if len(scores) > 0 else 0.0
        score_range = max_s - min_s or 1.0

        results = [
            RerankResult(
                index=i,
                content=doc,
                score=float((s - min_s) / score_range),
            )
            for i, (doc, s) in enumerate(zip(documents, scores))
        ]
        results.sort(key=lambda x: x.score, reverse=True)

        if top_n:
            results = results[:top_n]
        return results


# ── OpenAI 兼容 Rerank API ───────────────────────────────────


class OpenAIReranker(RerankProvider):
    """OpenAI 兼容 Rerank API（通过 embedding 相似度）"""

    def __init__(
        self,
        api_base: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "text-embedding-3-small",
    ):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model

    @property
    def name(self) -> str:
        return "openai_rerank"

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        if not documents:
            return []
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            # 获取 query embedding
            resp = await client.post(
                f"{self._api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model, "input": [query] + documents},
            )
            resp.raise_for_status()
            data = resp.json()

            query_vec = np.array(data["data"][0]["embedding"])
            doc_vecs = [np.array(d["embedding"]) for d in data["data"][1:]]

            query_norm = np.linalg.norm(query_vec)
            results = []
            for i, dv in enumerate(doc_vecs):
                sim = float(np.dot(query_vec, dv) / (query_norm * np.linalg.norm(dv) + 1e-8))
                results.append(RerankResult(
                    index=i, content=documents[i], score=max(0.0, sim),
                ))

            results.sort(key=lambda x: x.score, reverse=True)
            if top_n:
                results = results[:top_n]
            return results


# ── 级联 Reranker ────────────────────────────────────────────


class CascadeReranker(RerankProvider):
    """
    级联重排序 —— 尝试多个 Reranker，第一个成功即返回

    用途:
    - 本地 CrossEncoder 不可用时自动降级到 OpenAI API
    - 配置多个 Reranker 增加可靠性
    """

    def __init__(self, rerankers: list[RerankProvider]):
        self._rerankers = rerankers

    @property
    def name(self) -> str:
        return "cascade"

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int | None = None,
    ) -> list[RerankResult]:
        for reranker in self._rerankers:
            try:
                return await reranker.rerank(query, documents, top_n)
            except Exception as e:
                logger.warning(
                    "Reranker '%s' failed, trying next: %s", reranker.name, e,
                )
                continue

        # 所有 Reranker 都失败，返回原始顺序
        logger.error("All rerankers failed, returning original order")
        return [
            RerankResult(index=i, content=doc, score=1.0 / (i + 1))
            for i, doc in enumerate(documents)
        ][:top_n]


# ── 工厂 ─────────────────────────────────────────────────────


_global_reranker: Optional[RerankProvider] = None


def init_reranker() -> Optional[RerankProvider]:
    """初始化全局 Reranker"""
    global _global_reranker

    provider_type = os.getenv("RERANK_PROVIDER", "local").lower()

    if provider_type == "none":
        _global_reranker = None
        return None

    if provider_type == "openai":
        _global_reranker = OpenAIReranker(
            api_base=os.getenv("RERANK_API_BASE", "https://api.openai.com/v1"),
            api_key=os.getenv("RERANK_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            model=os.getenv("RERANK_API_MODEL", "text-embedding-3-small"),
        )
    elif provider_type == "cascade":
        # 级联：本地 → OpenAI
        components = []
        try:
            components.append(CrossEncoderReranker(
                model_name=os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
                device=os.getenv("RERANK_DEVICE", "cpu"),
            ))
        except Exception:
            pass
        try:
            components.append(OpenAIReranker())
        except Exception:
            pass
        if components:
            _global_reranker = CascadeReranker(components)
        else:
            _global_reranker = None
    else:  # local
        _global_reranker = CrossEncoderReranker(
            model_name=os.getenv("RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
            device=os.getenv("RERANK_DEVICE", "cpu"),
        )

    if _global_reranker:
        logger.info("Reranker initialized: %s", _global_reranker.name)
    return _global_reranker


def get_reranker() -> Optional[RerankProvider]:
    """获取全局 Reranker"""
    global _global_reranker
    if _global_reranker is None:
        return init_reranker()
    return _global_reranker
