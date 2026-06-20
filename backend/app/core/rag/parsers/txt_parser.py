"""
纯文本解析器 — 多编码自动检测
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from . import BaseParser, ParseResult

logger = logging.getLogger("app.core.rag.parsers.text")


class TextParser(BaseParser):
    """纯文本解析器，支持多编码自动检测"""

    _ENCODINGS = ["utf-8", "gbk", "gb2312", "latin-1"]

    @property
    def name(self) -> str:
        return "text"

    def supports(self, filepath: str) -> bool:
        ext = Path(filepath).suffix.lower()
        return ext in (".txt", ".log", ".csv", ".json", ".xml", ".yaml", ".yml")

    async def parse(self, filepath: str) -> ParseResult:
        content = self._read_with_fallback(filepath)
        title = os.path.basename(filepath)
        return ParseResult(text=content, title=title)

    def _read_with_fallback(self, filepath: str) -> str:
        """尝试多种编码读取"""
        for enc in self._ENCODINGS:
            try:
                with open(filepath, "r", encoding=enc) as f:
                    return f.read()
            except (UnicodeDecodeError, UnicodeError):
                continue
        # 最终回退
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            logger.warning("Fallback to utf-8 with replace for: %s", filepath)
            return f.read()
