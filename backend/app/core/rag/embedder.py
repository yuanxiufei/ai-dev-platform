"""
插件式 Embedding Provider

借鉴 AstrBot Provider 架构：
- 统一接口：BaseEmbeddingProvider
- 多种后端：本地 BGE / OpenAI 兼容 / Ollama / 百炼
- 批量并发 + 重试 + 进度回调
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable

import numpy as np

logger = logging.getLogger("app.core.rag.embedder")

# ── 抽象基类 ──────────────────────────────────────────────


class BaseEmbeddingProvider(ABC):
    """Embedding Provider 抽象基类"""

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """单条文本向量化"""

    @abstractmethod
    async def embed_batch(
        self,
        texts: list[str],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[list[float]]:
        """批量向量化（带并发和重试）"""

    @abstractmethod
    def get_dim(self) -> int:
        """获取向量维度"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""


# ── 本地 BGE 模型 ─────────────────────────────────────────


class LocalBGEProvider(BaseEmbeddingProvider):
    """本地 BGE 模型（sentence-transformers）"""

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cpu",
    ):
        self._model_name = model_name
        self._device = device
        self._model = None
        self._dim: int = 1024

    @property
    def name(self) -> str:
        return "local_bge"

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading BGE model: %s on %s", self._model_name, self._device)
            self._model = SentenceTransformer(self._model_name, device=self._device)
            self._dim = self._model.get_sentence_embedding_dimension()

    def get_dim(self) -> int:
        self._load_model()
        return self._dim

    async def embed(self, text: str) -> list[float]:
        self._load_model()
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    async def embed_batch(
        self,
        texts: list[str],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[list[float]]:
        self._load_model()
        embeddings = self._model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=64,
        )
        results = [e.tolist() for e in embeddings]
        if progress_callback:
            progress_callback(len(texts), len(texts))
        return results


# ── OpenAI 兼容 API ───────────────────────────────────────


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """OpenAI 兼容 Embedding API"""

    def __init__(
        self,
        api_base: str = "https://api.openai.com/v1",
        api_key: str = "",
        model: str = "text-embedding-3-small",
        max_concurrency: int = 4,
        max_retries: int = 3,
    ):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._max_concurrency = max_concurrency
        self._max_retries = max_retries
        self._dim: int = 1536  # text-embedding-3-small 默认维度
        self._client: Optional[object] = None

    @property
    def name(self) -> str:
        return "openai"

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                base_url=self._api_base,
                api_key=self._api_key or "sk-placeholder",
            )
        return self._client

    def get_dim(self) -> int:
        return self._dim

    async def embed(self, text: str) -> list[float]:
        results = await self.embed_batch([text])
        return results[0]

    async def embed_batch(
        self,
        texts: list[str],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[list[float]]:
        client = self._get_client()
        sem = asyncio.Semaphore(self._max_concurrency)
        total = len(texts)

        async def _do_batch(batch: list[str], batch_idx: int):
            async with sem:
                for attempt in range(self._max_retries):
                    try:
                        resp = await client.embeddings.create(
                            input=batch,
                            model=self._model,
                        )
                        return zip(range(batch_idx, batch_idx + len(batch)),
                                   [d.embedding for d in resp.data])
                    except Exception as e:
                        if attempt == self._max_retries - 1:
                            logger.error("Embedding failed after %d retries: %s",
                                        self._max_retries, e)
                            raise
                        await asyncio.sleep(1.5 ** attempt)

        # 分批 + 并发
        batch_size = 32
        tasks = []
        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            tasks.append(_do_batch(batch, i))

        results = [None] * total
        for task in asyncio.as_completed(tasks):
            for pos, vec in await task:
                results[pos] = vec
            if progress_callback:
                done = sum(1 for r in results if r is not None)
                progress_callback(done, total)

        # 维度检测
        if results:
            self._dim = len(results[0])

        return results  # type: ignore


# ── 工厂函数 ──────────────────────────────────────────────

_global_provider: Optional[BaseEmbeddingProvider] = None


def init_embedding_provider(config=None) -> BaseEmbeddingProvider:
    """初始化全局 Embedding Provider"""
    global _global_provider
    if config is None:
        from app.core.rag.config import get_rag_config
        config = get_rag_config()

    provider_type = config.embedding_provider

    if provider_type == "openai":
        _global_provider = OpenAIEmbeddingProvider(
            api_base=config.embedding_api_base,
            api_key=config.embedding_api_key,
            model=config.embedding_api_model,
            max_concurrency=config.embed_max_concurrency,
            max_retries=config.embed_max_retries,
        )
    else:
        _global_provider = LocalBGEProvider(
            model_name=config.embedding_model,
            device=config.embedding_device,
        )

    logger.info("Embedding provider initialized: %s (dim=%d)",
                 _global_provider.name, _global_provider.get_dim())
    return _global_provider


def get_embedding_provider() -> BaseEmbeddingProvider:
    global _global_provider
    if _global_provider is None:
        return init_embedding_provider()
    return _global_provider
