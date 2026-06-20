"""
PDF 解析器 — 提取文本和嵌入图片
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

from . import BaseParser, ParseResult

logger = logging.getLogger("app.core.rag.parsers.pdf")


class PDFParser(BaseParser):
    """PDF 解析器，使用 pypdf 提取文本 + 嵌入图片"""

    @property
    def name(self) -> str:
        return "pdf"

    def supports(self, filepath: str) -> bool:
        return Path(filepath).suffix.lower() == ".pdf"

    async def parse(self, filepath: str) -> ParseResult:
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError("pypdf not installed. Run: pip install pypdf")

        reader = PdfReader(filepath)
        title = os.path.basename(filepath)

        # 提取文本
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())

        full_text = "\n\n".join(pages)

        # 提取嵌入图片
        images: list[bytes] = []
        try:
            from pypdf.filters import _xobj_to_image
            for page in reader.pages:
                for _, img_bytes in _xobj_to_image(page).items():
                    if img_bytes:
                        images.append(img_bytes)
        except Exception as e:
            logger.debug("Image extraction skipped: %s", e)

        return ParseResult(
            text=full_text,
            title=title,
            metadata={"pages": len(reader.pages)},
            images=images,
        )
