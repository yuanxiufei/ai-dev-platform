"""
分块器 — 多策略文本分割
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger("app.core.rag.chunking")


class BaseChunker(ABC):
    """分块器抽象基类"""

    def __init__(self, chunk_size: int = 1024, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    @abstractmethod
    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[dict]:
        """将文本分割为 chunks，每个 chunk 带元数据"""

    @property
    @abstractmethod
    def name(self) -> str:
        """分块器名称"""


def get_chunker(strategy: str = "recursive", **kwargs) -> BaseChunker:
    """根据策略名获取分块器"""
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

    return chunker_cls(**kwargs)
