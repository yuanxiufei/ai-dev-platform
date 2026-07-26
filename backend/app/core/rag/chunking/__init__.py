"""
分块器 — 多策略文本分割 + 自适应 Token 预算

借鉴 AnythingLLM chunkHeader 设计：
- 每个 chunk 可注入文档上下文头（标题/来源/日期）
- 上下文头在分块后、embedding 前注入，保证向量检索可感知文档来源

自适应 Token 预算 (Phase 2, 借鉴 AnythingLLM embedder-aware chunking):
- 不同 Embedding Provider 有不同的 max_chunk_tokens
- 分块器自动感知嵌入模型的 token 上限，裁剪超出的 chunk
- 避免 embedding API 返回 400 / 向量截断丢失信息
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("app.core.rag.chunking")


class BaseChunker(ABC):
    """分块器抽象基类 — 支持自适应 Token 预算"""

    # 中文字符→token 估算比 (约 1 汉字 = 1.5 tokens for most models)
    _CHAR_TO_TOKEN_RATIO = 1.5

    def __init__(
        self,
        chunk_size: int = 1024,
        chunk_overlap: int = 200,
        context_header: Optional[str] = None,
        token_budget: int = 0,  # 0 = 禁用自适应裁剪, >0 = embedder.max_chunk_tokens
    ):
        """
        Args:
            chunk_size: 分块大小（字符数）
            chunk_overlap: 块间重叠（字符数）
            context_header: 文档上下文头，注入到每个 chunk 文本前
                            格式: "[Document: xxx]\n[Source: xxx]\n[Date: xxx]\n"
                            借鉴 AnythingLLM chunkHeader: prepend context before embedding
            token_budget: 嵌入模型的最大 token 数 (取自 embedder.max_chunk_tokens)
                          正值时，分块后自动裁剪超出的 chunk
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.context_header = context_header
        self.token_budget = token_budget

    @abstractmethod
    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[dict]:
        """将文本分割为 chunks，每个 chunk 带元数据"""

    def _apply_context_header(self, chunks: list[dict]) -> list[dict]:
        """在每个 chunk 文本前注入文档上下文头（借鉴 AnythingLLM chunkHeader）

        上下文头会前置到 chunk["text"]，让向量检索时感知文档来源，
        解决检索结果脱离上下文语义不清的问题。
        """
        if not self.context_header:
            return chunks
        for c in chunks:
            c["text"] = f"{self.context_header}\n\n{c['text']}"
        return chunks

    def _apply_token_budget(self, chunks: list[dict]) -> list[dict]:
        """自适应裁剪超出 token 预算的 chunk (Phase 2)

        借鉴 AnythingLLM embedder-aware chunking:
        不同 embedder 有不同的 max_chunk_tokens，分块器自动裁剪，
        防止 embedding API 400 错误或向量截断。

        裁剪策略：
        1. 估算 chunk 的 token 数 (字符数 × CHAR_TO_TOKEN_RATIO)
        2. 超出 token_budget 则截断字符到安全长度
        3. 追加 "[truncated]" 标记
        """
        if self.token_budget <= 0:
            return chunks

        safe_chars = int(self.token_budget / self._CHAR_TO_TOKEN_RATIO)

        for c in chunks:
            text = c["text"]
            est_tokens = int(len(text) * self._CHAR_TO_TOKEN_RATIO)

            if est_tokens > self.token_budget:
                truncated = text[:safe_chars].rstrip()
                c["text"] = truncated + "\n[truncated]"
                c.setdefault("metadata", {})["_truncated"] = True
                c.setdefault("metadata", {})["_original_length"] = len(text)
                logger.debug(
                    "Chunk truncated: %d → %d chars (token budget: %d)",
                    len(text), len(c["text"]), self.token_budget,
                )

        return chunks

    @property
    @abstractmethod
    def name(self) -> str:
        """分块器名称"""


def get_chunker(
    strategy: str = "recursive",
    token_budget: int = 0,
    embedder = None,  # 可选: BaseEmbeddingProvider, 自动提取 max_chunk_tokens
    **kwargs,
) -> BaseChunker:
    """根据策略名获取分块器（支持自适应 Token 预算）

    Args:
        strategy: 分块策略 (recursive / markdown / code)
        token_budget: 嵌入模型的 token 上限 (覆盖 embedder 的值)
        embedder: 嵌入 provider 实例 (自动提取 max_chunk_tokens)
        **kwargs: 传递给分块器构造函数 (chunk_size, chunk_overlap, context_header)
    """
    from .recursive import RecursiveCharacterChunker
    from .markdown_chunker import MarkdownChunker
    from .code_chunker import CodeChunker

    chunkers = {
        "recursive": RecursiveCharacterChunker,
        "markdown": MarkdownChunker,
        "code": CodeChunker,
    }

    chunker_cls = chunkers.get(strategy)
    if chunker_cls is None:
        logger.warning("Unknown chunk strategy '%s', fallback to recursive", strategy)
        chunker_cls = RecursiveCharacterChunker

    # 自适应 token 预算: embedder 能力 → chunker 参数
    if token_budget <= 0 and embedder is not None:
        token_budget = getattr(embedder, "max_chunk_tokens", 0) or 0
        if token_budget > 0:
            logger.debug("Adaptive token budget: %d (from %s)",
                         token_budget, getattr(embedder, "name", "unknown"))

    kwargs["token_budget"] = token_budget
    return chunker_cls(**kwargs)
