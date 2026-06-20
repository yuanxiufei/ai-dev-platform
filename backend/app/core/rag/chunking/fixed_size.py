"""
FixedSizeChunker — 固定大小分块器

借鉴 AstrBot FixedSizeChunker:
- 按固定字符数切分
- 可选重叠
- 简单高效，适合结构化不强的文本
"""

from __future__ import annotations

from typing import Optional

from . import BaseChunker


class FixedSizeChunker(BaseChunker):
    """固定大小分块器"""

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        super().__init__(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    @property
    def name(self) -> str:
        return "fixed_size"

    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[dict]:
        """按固定大小切分文本"""
        if metadata is None:
            metadata = {}

        chunks = []
        text_len = len(text)
        start = 0
        idx = 0

        while start < text_len:
            end = min(start + self.chunk_size, text_len)
            chunk_text = text[start:end].strip()

            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "index": idx,
                    "metadata": {
                        **metadata,
                        "strategy": self.name,
                        "chunk_size": self.chunk_size,
                        "chunk_overlap": self.chunk_overlap,
                    },
                })
                idx += 1

            start += self.chunk_size - self.chunk_overlap
            if start >= text_len:
                break

        return chunks
