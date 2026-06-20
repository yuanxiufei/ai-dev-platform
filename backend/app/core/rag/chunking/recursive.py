"""
递归字符分块器 — 优先级分隔符递归分割

分隔符优先级（借鉴 AstrBot）：
  \\n\\n → \\n → 。 → ， → . → , → 空格 → 字符级
"""

from __future__ import annotations

import re
from typing import Optional

from . import BaseChunker


class RecursiveCharacterChunker(BaseChunker):
    """递归字符分块器 — 默认通用分块策略"""

    # 分离符优先级
    SEPARATORS = [
        "\n\n",   # 段落
        "\n",     # 行
        "。",     # 中文句号
        "！",     # 中文感叹号
        "？",     # 中文问号
        "；",     # 中文分号
        "，",     # 中文逗号
        ". ",     # 英文句号+空格
        "! ",     # 英文感叹号
        "? ",     # 英文问号
        "; ",     # 英文分号
        ", ",     # 英文逗号
        ".",      # 英文句号（无空格）
        " ",      # 空格
        "",       # 字符级
    ]

    @property
    def name(self) -> str:
        return "recursive"

    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[dict]:
        if not text.strip():
            return []

        meta = metadata or {}
        chunks_raw = self._split_recursive(text, self.SEPARATORS)
        return self._merge_chunks(chunks_raw, meta)

    def _split_recursive(
        self, text: str, separators: list[str]
    ) -> list[str]:
        """递归分割"""
        sep = separators[0] if separators else ""
        remaining = separators[1:] if len(separators) > 1 else []

        if not sep:
            # 字符级分割
            return list(text)

        parts = re.split(f"({re.escape(sep)})", text)
        result: list[str] = []

        for i in range(0, len(parts), 2):
            segment = parts[i]
            if i + 1 < len(parts):
                segment += parts[i + 1]

            if len(segment) <= self.chunk_size:
                result.append(segment)
            elif remaining:
                result.extend(self._split_recursive(segment, remaining))
            else:
                # 字符级强制截断
                for j in range(0, len(segment), self.chunk_size):
                    result.append(segment[j:j + self.chunk_size])

        return result

    def _merge_chunks(
        self, chunks: list[str], metadata: dict
    ) -> list[dict]:
        """将小片段合并为一个 chunk（保持 chunk_size）"""
        merged: list[dict] = []
        buffer = ""
        chunk_idx = 0

        for piece in chunks:
            if len(buffer) + len(piece) <= self.chunk_size:
                buffer += piece
            else:
                if buffer:
                    merged.append({
                        "text": buffer.strip(),
                        "index": chunk_idx,
                        "metadata": {**metadata, "chunk_index": chunk_idx},
                    })
                    chunk_idx += 1
                    # 重叠处理
                    if self.chunk_overlap > 0 and len(buffer) > self.chunk_overlap:
                        buffer = buffer[-self.chunk_overlap:] + piece
                    else:
                        buffer = piece
                else:
                    buffer = piece

        if buffer.strip():
            merged.append({
                "text": buffer.strip(),
                "index": chunk_idx,
                "metadata": {**metadata, "chunk_index": chunk_idx},
            })

        return merged
