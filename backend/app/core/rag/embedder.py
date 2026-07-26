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

    @property
    def max_chunk_tokens(self) -> int:
        """单 chunk 最大 token 数（借鉴 embedder 能力声明模式）

        用于自适应截断：chunk 超过此值时自动裁剪，
        防止 input 超出模型的 max_seq_length。
        子类按实际模型能力覆盖。
        """
        return 512  # 安全默认值


# ── 本地 BGE 模型 ─────────────────────────────────────────


class LocalBGEProvider(BaseEmbeddingProvider):
    """本地 BGE 模型（sentence-transformers）

    性能优化：
    - ONNX 自动启用（CPU 上 2-3x 加速）
    - 在线程池中运行，不阻塞事件循环
    - batch_size=64 充分利用 CPU 向量化
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
        batch_size: int = 256,
    ):
        self._model_name = model_name
        self._device = device
        self._batch_size = batch_size
        self._model = None
        self._dim: int = 384

    @property
    def name(self) -> str:
        return "local_bge"

    def _load_model(self):
        if self._model is not None:
            return
        import os

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers 未安装，无法使用本地 BGE 向量模型。"
                "请执行: pip install sentence-transformers "
                "或在 pyproject.toml 中启用 rag 可选依赖: pip install -e '.[rag]'"
            )

        # CPU 上自动尝试 ONNX 加速
        backend = "onnx" if self._device == "cpu" else None
        load_kwargs: dict = {"device": self._device}
        if backend:
            try:
                import onnxruntime  # noqa: F401
                load_kwargs["backend"] = backend
                logger.info("Loading BGE model: %s on %s (ONNX accelerated)",
                            self._model_name, self._device)
            except ImportError:
                logger.info("ONNX not available, loading BGE model: %s on %s",
                            self._model_name, self._device)
        else:
            logger.info("Loading BGE model: %s on %s", self._model_name, self._device)

        # 优先使用本地缓存，避免 HuggingFace Hub 网络超时
        # HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE 环境变量强制离线
        force_offline = os.getenv("HF_HUB_OFFLINE", "") in ("1", "true", "True") \
            or os.getenv("TRANSFORMERS_OFFLINE", "") in ("1", "true", "True")

        # 自动检测 HF 镜像（国内加速），不覆盖用户已设的值
        mirror = os.getenv("HF_ENDPOINT", "")
        if mirror:
            logger.info("Using HF mirror: %s", mirror)

        try:
            if force_offline:
                logger.info("HF offline mode enabled, loading from local cache only")
                self._model = SentenceTransformer(
                    self._model_name, local_files_only=True, **load_kwargs
                )
            else:
                # 先尝试本地缓存（快速路径，无网络请求）
                try:
                    self._model = SentenceTransformer(
                        self._model_name, local_files_only=True, **load_kwargs
                    )
                    logger.info("BGE model loaded from local cache")
                except Exception:
                    if mirror:
                        logger.info(
                            "Model not in local cache, downloading via mirror %s...",
                            mirror,
                        )
                    else:
                        logger.warning(
                            "Model not in local cache, attempting download from HuggingFace. "
                            "Set HF_ENDPOINT=https://hf-mirror.com for faster download in China."
                        )
                    self._model = SentenceTransformer(self._model_name, **load_kwargs)
        except Exception as e:
            raise RuntimeError(
                f"无法加载本地 BGE 模型 '{self._model_name}'。"
                f"请确认模型已下载到 ~/.cache/huggingface/hub/，"
                f"或设置 HF_ENDPOINT=https://hf-mirror.com 使用国内镜像下载。"
                f"手动下载命令: python -c \"from sentence_transformers import SentenceTransformer; "
                f"SentenceTransformer('{self._model_name}')\""
                f"\n原始错误: {e}"
            ) from e

        self._dim = self._model.get_sentence_embedding_dimension()

    def get_dim(self) -> int:
        self._load_model()
        return self._dim

    @property
    def max_chunk_tokens(self) -> int:
        """all-MiniLM-L6-v2 最大 256 wordpiece tokens"""
        self._load_model()
        try:
            return self._model.max_seq_length
        except Exception:
            return 256

    async def embed(self, text: str) -> list[float]:
        self._load_model()
        loop = asyncio.get_running_loop()
        vec = await loop.run_in_executor(
            None,
            lambda: self._model.encode(text, normalize_embeddings=True),
        )
        return vec.tolist()

    async def embed_batch(
        self,
        texts: list[str],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[list[float]]:
        if not texts:
            return []

        self._load_model()
        loop = asyncio.get_running_loop()

        embeddings = await loop.run_in_executor(
            None,
            lambda: self._model.encode(
                texts,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=self._batch_size,
            ),
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
            import os
            # 优先使用注入的 api_key，其次环境变量，最后使用占位符（仅开发/测试）
            api_key = self._api_key or os.getenv("OPENAI_API_KEY", "")
            self._client = AsyncOpenAI(
                base_url=self._api_base,
                api_key=api_key,
            )
        return self._client

    def get_dim(self) -> int:
        return self._dim

    @property
    def max_chunk_tokens(self) -> int:
        """text-embedding-3-small: 最大输入 8191 tokens"""
        return 8191

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
            batch_size=config.embed_batch_size,
        )

    logger.info("Embedding provider initialized: %s", _global_provider.name)
    return _global_provider


def get_embedding_provider() -> BaseEmbeddingProvider:
    global _global_provider
    if _global_provider is None:
        return init_embedding_provider()
    return _global_provider
