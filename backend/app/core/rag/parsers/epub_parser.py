"""
EPUB 解析器 — MarkItDown 委托 + 内容清洗

借鉴 AstrBot EpubParser:
- 使用 MarkItDown 解析 EPUB
- 清洗页头页脚、超链接噪音
- 保留排版结构
"""

from __future__ import annotations

import re
from typing import Optional

from . import BaseParser, ParseResult


class EPUBParser(BaseParser):
    """EPUB 文档解析器"""

    @property
    def name(self) -> str:
        return "epub_parser"

    def supports(self, filepath: str) -> bool:
        return filepath.lower().endswith(".epub")

    async def parse(self, filepath: str) -> ParseResult:
        """解析 EPUB 文件"""
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(filepath)
            raw_text = result.text_content if hasattr(result, "text_content") else str(result)
        except ImportError:
            raise ImportError("markitdown is required for EPUB parsing. pip install markitdown")
        except Exception as e:
            raise RuntimeError(f"Failed to parse EPUB: {e}")

        # 清洗
        cleaned = self._sanitize(raw_text)

        # 提取标题（第一个 # 开头行）
        title = ""
        for line in cleaned.split("\n"):
            if line.startswith("# "):
                title = line.replace("# ", "").strip()
                break

        return ParseResult(
            text=cleaned,
            title=title,
            metadata={"parser": self.name, "file_type": "epub"},
        )

    def _sanitize(self, text: str) -> str:
        """清洗 EPUB 提取文本中的噪音"""
        # 移除空行过多
        text = re.sub(r"\n{4,}", "\n\n\n", text)

        # 移除纯链接行
        text = re.sub(r"^\s*(https?://\S+)\s*$", "", text, flags=re.MULTILINE)

        # 移除常见页眉页脚模式
        patterns = [
            r"^\s*Page\s+\d+\s*(of\s+\d+)?\s*$",
            r"^\s*\d+\s*$",  # 独立页码
            r"^\s*[─═━\-_=]{3,}\s*$",  # 分割线
        ]
        for pattern in patterns:
            text = re.sub(pattern, "", text, flags=re.MULTILINE)

        # 压缩多余空行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
