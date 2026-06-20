"""
文档解析器基类与自动路由
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("app.core.rag.parsers")


@dataclass
class ParseResult:
    """解析结果"""
    text: str
    title: str = ""
    metadata: dict = field(default_factory=dict)
    images: list[bytes] = field(default_factory=list)  # 嵌入图片（PDF）
    chunks: list[str] = field(default_factory=list)     # 解析后预分块（可选）


class BaseParser(ABC):
    """文档解析器抽象基类"""

    @abstractmethod
    async def parse(self, filepath: str) -> ParseResult:
        """解析文件，返回结构化文本"""

    @abstractmethod
    def supports(self, filepath: str) -> bool:
        """检查是否支持该文件类型"""

    @property
    @abstractmethod
    def name(self) -> str:
        """解析器名称"""


def select_parser(filepath: str) -> Optional[BaseParser]:
    """根据文件类型自动选择解析器"""
    from .txt_parser import TextParser
    from .pdf_parser import PDFParser
    from .markitdown_parser import MarkitdownParser
    from .url_parser import URLParser

    ext = filepath.lower()

    # URL 检测
    if ext.startswith("http://") or ext.startswith("https://"):
        return URLParser()

    # 按扩展名路由
    if ext.endswith(".txt") or ext.endswith(".log") or ext.endswith(".csv"):
        return TextParser()

    if ext.endswith(".pdf"):
        return PDFParser()

    if any(ext.endswith(e) for e in (".docx", ".xlsx", ".xls", ".pptx",
                                       ".md", ".rst", ".adoc", ".epub")):
        return MarkitdownParser()

    logger.warning("No parser found for: %s", filepath)
    return None
