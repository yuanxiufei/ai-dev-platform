"""
Embedding Service — 多 Provider embedding 生成

借鉴 Open WebUI 的 embedding 架构：
- OpenAIEmbeddingProvider: text-embedding-3-small/large
- 本地模型 Provider: BGE / sentence-transformers（可选）
- Hash fallback: SHA-256 哈希降级

使用方式：
    svc = get_embedding_service()
    vec = await svc.embed("hello world")  # → list[float]
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("memory.embedding")

DEFAULT_EMBEDDING_DIM = 768
"""默认嵌入维度（BGE-base 标准）"""


# ── EmbeddingProvider 抽象 ────────────────────────────


class EmbeddingProvider(ABC):
    """Embedding Provider 抽象基类"""

    name: str = "base"
    dim: int = DEFAULT_EMBEDDING_DIM

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """生成文本嵌入向量"""
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量生成嵌入"""
        return [await self.embed(t) for t in texts]


# ── OpenAI Provider ───────────────────────────────────


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI Embedding API Provider"""

    name = "openai"
    dim = 1536
    DEFAULT_MODEL = "text-embedding-3-small"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model

        if model == "text-embedding-3-large":
            self.dim = 3072
        elif model == "text-embedding-ada-002":
            self.dim = 1536
        else:
            self.dim = 1536

    async def embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise ValueError("OpenAI API key not configured")

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "input": text[:8192],  # OpenAI token limit
                        "model": self.model,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]

        except Exception as e:
            logger.warning("OpenAI embedding failed: %s, falling back to hash", e)
            raise


# ── 本地模型 Provider（BGE 等）─────────────────────────


class LocalEmbeddingProvider(EmbeddingProvider):
    """本地 sentence-transformers / BGE Provider

    需要安装: pip install sentence-transformers
    """

    name = "local"
    dim = 768  # BGE-base-en-v1.5 default

    def __init__(self, model_name: str = "BAAI/bge-base-en-v1.5") -> None:
        self.model_name = model_name
        self._model: Any = None

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            self.dim = self._model.get_sentence_embedding_dimension()
            logger.info("Local embedding model loaded: %s (dim=%d)", self.model_name, self.dim)
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed. Run: pip install sentence-transformers"
            )

    async def embed(self, text: str) -> list[float]:
        self._ensure_model()
        # sentence-transformers 是同步的，在线程池中运行
        import asyncio
        loop = asyncio.get_running_loop()
        embedding = await loop.run_in_executor(
            None, lambda: self._model.encode(text, normalize_embeddings=True).tolist()
        )
        return embedding

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        self._ensure_model()
        import asyncio
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(
            None,
            lambda: self._model.encode(texts, normalize_embeddings=True).tolist(),
        )
        return embeddings


# ── Hash Fallback Provider ────────────────────────────


class HashEmbeddingProvider(EmbeddingProvider):
    """SHA-256 哈希降级（永远可用）"""

    name = "hash"
    dim = 768

    async def embed(self, text: str) -> list[float]:
        return _hash_embedding(text, self.dim)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embedding(t, self.dim) for t in texts]


# ── EmbeddingService — 多 Provider 统一接口 ───────────


class EmbeddingService:
    """多 Provider embedding 服务

    策略：
    1. 优先使用配置的 Provider（OpenAI → Local → Hash fallback）
    2. 自动回退到 Hash（永远可用）
    """

    def __init__(self) -> None:
        self._providers: dict[str, EmbeddingProvider] = {}
        self._default: str = "hash"
        self._fallback_chain: list[str] = []
        self._load_providers()

    def _load_providers(self) -> None:
        """从环境变量加载 Provider 配置"""
        # 总是注册 hash fallback
        self._providers["hash"] = HashEmbeddingProvider()

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            self._providers["openai"] = OpenAIEmbeddingProvider()
            self._fallback_chain.append("openai")

        # 本地模型
        local_model = os.getenv("EMBEDDING_LOCAL_MODEL", "")
        if local_model:
            try:
                self._providers["local"] = LocalEmbeddingProvider(local_model)
                self._fallback_chain.append("local")
            except Exception as e:
                logger.warning("Local embedding model init failed: %s", e)

        # 设置默认优先级
        provider_order = os.getenv("EMBEDDING_PROVIDER_ORDER", "")
        if provider_order:
            self._fallback_chain = [
                p.strip() for p in provider_order.split(",")
                if p.strip() in self._providers
            ]

        # Hash 作为最后安全网
        if "hash" not in self._fallback_chain:
            self._fallback_chain.append("hash")

        logger.info(
            "EmbeddingService: providers=%s fallback_chain=%s",
            list(self._providers.keys()), self._fallback_chain,
        )

    async def embed(self, text: str) -> list[float]:
        """生成 embedding（自动回退）"""
        last_error: Exception | None = None

        for name in self._fallback_chain:
            provider = self._providers.get(name)
            if not provider:
                continue
            try:
                return await provider.embed(text)
            except Exception as e:
                last_error = e
                logger.debug("Embedding provider '%s' failed: %s", name, e)

        # 最终回退到 hash
        logger.warning("All embedding providers failed, using hash fallback")
        return _hash_embedding(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        result: list[list[float]] = []
        for text in texts:
            result.append(await self.embed(text))
        return result

    @property
    def provider_name(self) -> str:
        """当前主 Provider 名称"""
        return self._fallback_chain[0] if self._fallback_chain else "hash"

    @property
    def dim(self) -> int:
        """当前主 Provider 的嵌入维度"""
        for name in self._fallback_chain:
            p = self._providers.get(name)
            if p:
                return p.dim
        return DEFAULT_EMBEDDING_DIM


# ── 全局单例 ──────────────────────────────────────────

_embedding_service: EmbeddingService | None = None


def init_embedding_service() -> EmbeddingService:
    global _embedding_service
    _embedding_service = EmbeddingService()
    return _embedding_service


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


# ── 哈希降级 ──────────────────────────────────────────


def _hash_embedding(text: str, dim: int = DEFAULT_EMBEDDING_DIM) -> list[float]:
    """SHA-256 哈希降级 embedding（永远可用）"""
    import hashlib
    import math

    hash_bytes = hashlib.sha256(text.encode()).digest()
    vec = [(hash_bytes[i % len(hash_bytes)] / 127.5) - 1.0 for i in range(dim)]
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec
