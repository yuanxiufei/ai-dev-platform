"""
Markdown 结构感知分块器 — 按标题层级分割

借鉴 AstrBot:
- 按 #~###### 标题层级切割
- 围栏代码块不参与切割
- 标题作为上下文前缀附加到 chunk
- 短块合并 + 子章节递归
"""

from __future__ import annotations

import re
from typing import Optional

from . import BaseChunker

logger = __import__("logging").getLogger("app.core.rag.chunking.markdown")


class MarkdownChunker(BaseChunker):
    """Markdown 结构感知分块器"""

    HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    FENCE_PATTERN = re.compile(r"```[\s\S]*?```", re.MULTILINE)

    def __init__(self, chunk_size: int = 1024, chunk_overlap: int = 200):
        super().__init__(chunk_size, chunk_overlap)
        self._min_chunk_size = max(50, chunk_size // 4)  # 短块合并阈值

    @property
    def name(self) -> str:
        return "markdown"

    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[dict]:
        if not text.strip():
            return []

        meta = metadata or {}
        sections = self._split_by_headings(text)
        merged = self._merge_short_sections(sections)
        return self._build_chunks(merged, meta)

    def _split_by_headings(self, text: str) -> list[dict]:
        """按标题层级分割，保护围栏代码块"""
        # 保护代码块
        code_blocks: list[str] = []
        def _save_fence(m):
            code_blocks.append(m.group(0))
            return f"__CODE_BLOCK_{len(code_blocks) - 1}__"
        text_clean = self.FENCE_PATTERN.sub(_save_fence, text)

        # 找所有标题位置
        headings = list(self.HEADING_PATTERN.finditer(text_clean))
        if not headings:
            return [{"level": 0, "title": "", "content": text}]

        sections: list[dict] = []
        for i, h in enumerate(headings):
            start = h.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(text_clean)
            content = text_clean[start:end].strip()

            # 还原代码块
            content = self._restore_code_blocks(content, code_blocks)

            sections.append({
                "level": len(h.group(1)),
                "title": h.group(2).strip(),
                "content": content,
            })

        # 第一个标题前的内容
        if headings and headings[0].start() > 0:
            prefix = text_clean[:headings[0].start()].strip()
            prefix = self._restore_code_blocks(prefix, code_blocks)
            if prefix:
                sections.insert(0, {"level": 0, "title": "", "content": prefix})

        return sections

    @staticmethod
    def _restore_code_blocks(text: str, code_blocks: list[str]) -> str:
        for i, cb in enumerate(code_blocks):
            text = text.replace(f"__CODE_BLOCK_{i}__", cb)
        return text

    def _merge_short_sections(self, sections: list[dict]) -> list[dict]:
        """合并过短的章节到前一个"""
        merged: list[dict] = []
        for sec in sections:
            if len(sec["content"]) < self._min_chunk_size and merged:
                # 附加到前一个
                merged[-1]["content"] += "\n\n" + sec["content"]
            else:
                merged.append(sec)
        return merged

    def _build_chunks(
        self, sections: list[dict], metadata: dict
    ) -> list[dict]:
        """构建带标题上下文的 chunks"""
        chunks: list[dict] = []
        idx = 0

        for sec in sections:
            # 构建上下文前缀
            prefix = ""
            if sec["title"]:
                prefix = f"# {sec['title']}\n\n"

            content = prefix + sec["content"]

            # 如果内容在 chunk_size 内，直接作为整体
            if len(content) <= self.chunk_size:
                chunks.append({
                    "text": content,
                    "index": idx,
                    "metadata": {
                        **metadata,
                        "chunk_index": idx,
                        "heading_level": sec["level"],
                        "section_title": sec["title"],
                    },
                })
                idx += 1
            else:
                # 子分割（递归处理大章节）
                from .recursive import RecursiveCharacterChunker
                sub = RecursiveCharacterChunker(
                    self.chunk_size - len(prefix),
                    self.chunk_overlap,
                )
                sub_chunks = sub.chunk(sec["content"])
                for sc in sub_chunks:
                    chunks.append({
                        "text": prefix + sc["text"],
                        "index": idx,
                        "metadata": {
                            **metadata,
                            "chunk_index": idx,
                            "heading_level": sec["level"],
                            "section_title": sec["title"],
                        },
                    })
                    idx += 1

        return chunks
