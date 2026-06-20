"""
多格式解析器 — DOCX / XLSX / MD / RST / EPUB
基于 markitdown 统一转换
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from . import BaseParser, ParseResult

logger = logging.getLogger("app.core.rag.parsers.markitdown")


class MarkitdownParser(BaseParser):
    """通过 markitdown 解析 Office/Markdown/EPUB 等多格式"""

    SUPPORTED_EXTENSIONS = {
        ".docx", ".xlsx", ".xls", ".pptx",
        ".md", ".rst", ".adoc", ".epub",
    }

    @property
    def name(self) -> str:
        return "markitdown"

    def supports(self, filepath: str) -> bool:
        return Path(filepath).suffix.lower() in self.SUPPORTED_EXTENSIONS

    async def parse(self, filepath: str) -> ParseResult:
        try:
            from markitdown import MarkItDown
        except ImportError:
            raise ImportError(
                "markitdown not installed. Run: pip install markitdown"
            )

        md = MarkItDown()
        result = md.convert(filepath)
        title = os.path.basename(filepath)

        return ParseResult(
            text=result.text_content,
            title=title,
            metadata={"source_format": Path(filepath).suffix},
        )
