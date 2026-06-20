"""
Embedding Provider 抽象 —— 文本向量化

借鉴 AstrBot EmbeddingProvider 设计:
- EmbeddingProvider: 抽象基类（单文本 + 批量 + 维度）
- OpenAIEmbeddingProvider: OpenAI API 适配
- OllamaEmbeddingProvider: Ollama 本地适配
- SentenceTransformersProvider: sentence-transformers 本地适配
- 工厂函数支持环境变量配置
"""

from __future__ import annotations

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

logger = logging.getLogger("providers.embedding")


# ── 抽象基类 ─────────────────────────────────────────────────


class EmbeddingProvider(ABC):
    """
    文本向量化 Provider 抽象

    借鉴 AstrBot EmbeddingProvider，定义:
    - get_embedding(text) → list[float]
    - get_embeddings(texts) → list[list[float]]
    - get_embeddings_batch(texts, batch_size, tasks_limit, max_retries) → list[list[float]]
    - dim → int

    RAG / Agent 可通过此接口切换不同的 Embedding 后端。
    """

    @abstractmethod
    async def get_embedding(self, text: str) -> list[float]:
        """单文本向量化"""
        ...

    @abstractmethod
    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化"""
        ...

    @abstractmethod
    def get_dim(self) -> int:
        """向量维度"""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        ...

    async def get_embeddings_batch(
        self,
        texts: list[str],
        batch_size: int = 16,
        tasks_limit: int = 3,
        max_retries: int = 3,
    ) -> list[list[float]]:
        """
        大批量分片处理（带并发控制 + 指数退避重试）

        默认实现在 base 中，子类只需实现 get_embeddings。
        """
        if not texts:
            return []

        semaphore = asyncio.Semaphore(tasks_limit)
        results: list[list[float]] = [list(np.zeros(self.get_dim()))] * len(texts)

        async def _process_batch(batch_texts: list[str], start_idx: int):
            async with semaphore:
                for attempt in range(1, max_retries + 1):
                    try:
                        embeddings = await self.get_embeddings(batch_texts)
                        for j, emb in enumerate(embeddings):
                            results[start_idx + j] = emb
                        return
                    except Exception as e:
                        if attempt == max_retries:
                            logger.error(
                                "Embedding batch [%d:%d] failed after %d attempts: %s",
                                start_idx, start_idx + len(batch_texts), max_retries, e,
                            )
                            raise
                        wait = 2 ** (attempt - 1)
                        logger.warning(
                            "Embedding batch [%d:%d] attempt %d/%d failed, retry in %ds",
                            start_idx, start_idx + len(batch_texts), attempt, max_retries, wait,
                        )
                        await asyncio.sleep(wait)

        tasks = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            tasks.append(_process_batch(batch, i))

        await asyncio.gather(*tasks)
        return results

    async def test(self) -> bool:
        """健康检查"""
        try:
            emb = await self.get_embedding("AI Fullstack Platform")
            return len(emb) == self.get_dim()
        except Exception as e:
            logger.error("EmbeddingProvider '%s' test failed: %s", self.name, e)
            return False


# ── OpenAI 兼容 API ──────────────────────────────────────────


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI 兼容 Embedding API"""

    def __init__(
        self,
        api_base: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "text-embedding-3-small",
        dim: int = 1536,
    ):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model
        self._dim = dim

    @property
    def name(self) -> str:
        return "openai_embedding"

    def get_dim(self) -> int:
        return self._dim

    async def get_embedding(self, text: str) -> list[float]:
        embeddings = await self.get_embeddings([text])
        return embeddings[0] if embeddings else []

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY not configured")

        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model,
                    "input": texts,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [d["embedding"] for d in data["data"]]


# ── Ollama 本地 Embedding ────────────────────────────────────


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama 本地 Embedding"""

    def __init__(
        self,
        api_base: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        dim: int = 768,
    ):
        self._api_base = api_base.rstrip("/")
        self._model = model
        self._dim = dim

    @property
    def name(self) -> str:
        return "ollama_embedding"

    def get_dim(self) -> int:
        return self._dim

    async def get_embedding(self, text: str) -> list[float]:
        embeddings = await self.get_embeddings([text])
        return embeddings[0] if embeddings else []

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        import httpx

        embeddings: list[list[float]] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            for text in texts:
                resp = await client.post(
                    f"{self._api_base}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings.append(data["embedding"])

        return embeddings


# ── SentenceTransformers 本地 ────────────────────────────────


class SentenceTransformersProvider(EmbeddingProvider):
    """sentence-transformers 本地 Embedding"""

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cpu",
        dim: int = 1024,
    ):
        self._model_name = model_name
        self._device = device
        self._dim = dim
        self._model = None

    @property
    def name(self) -> str:
        return "sentence_transformers"

    def get_dim(self) -> int:
        return self._dim

    def _load(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    self._model_name, device=self._device,
                )
                logger.info("Loaded SentenceTransformer: %s", self._model_name)
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: pip install sentence-transformers"
                )

    async def get_embedding(self, text: str) -> list[float]:
        embeddings = await self.get_embeddings([text])
        return embeddings[0] if embeddings else []

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        self._load()
        loop = asyncio.get_event_loop()
        vectors = await loop.run_in_executor(
            None, lambda: self._model.encode(texts, normalize_embeddings=True)
        )
        return [v.tolist() for v in vectors]


# ── 工厂函数 ─────────────────────────────────────────────────


_global_embedder: Optional[EmbeddingProvider] = None


def init_embedding_provider() -> EmbeddingProvider:
    """初始化全局 EmbeddingProvider"""
    global _global_embedder

    provider_type = os.getenv("EMBEDDING_PROVIDER", "local").lower()

    if provider_type == "openai":
        _global_embedder = OpenAIEmbeddingProvider(
            api_base=os.getenv("EMBEDDING_API_BASE", "https://api.openai.com/v1"),
            api_key=os.getenv("EMBEDDING_API_KEY", os.getenv("OPENAI_API_KEY", "")),
            model=os.getenv("EMBEDDING_API_MODEL", "text-embedding-3-small"),
        )
    elif provider_type == "ollama":
        _global_embedder = OllamaEmbeddingProvider(
            api_base=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
            model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
        )
    else:  # local
        _global_embedder = SentenceTransformersProvider(
            model_name=os.getenv("EMBEDDING_MODEL", "BAAI/bge-large-zh-v1.5"),
            device=os.getenv("EMBEDDING_DEVICE", "cpu"),
        )

    logger.info(
        "EmbeddingProvider initialized: %s (dim=%d)",
        _global_embedder.name, _global_embedder.get_dim(),
    )
    return _global_embedder


def get_embedding_provider() -> EmbeddingProvider:
    """获取全局 EmbeddingProvider"""
    global _global_embedder
    if _global_embedder is None:
        return init_embedding_provider()
    return _global_embedder
