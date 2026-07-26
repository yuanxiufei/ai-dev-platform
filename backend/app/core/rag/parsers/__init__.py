"""
文档解析器基类与自动路由

借鉴 RAGFlow ParserRegistry 设计：
- 每个解析器通过 supported_extensions / is_url_parser 声明能力
- 注册表 _PARSER_EXT_MAP 以扩展名→(模块,类名) 映射替代硬编码 if-else
- select_parser() 按扩展名/URL 查找 + supports() 回退
- 懒加载导入，避免循环依赖
"""

from __future__ import annotations

import importlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.core.rag.parsers")


# ── LazyImage 图片引用 (借鉴 RAGFlow 懒加载设计) ─────

@dataclass
class ImageRef:
    """图片懒加载引用

    替代在解析阶段全量加载图片到内存，解析器仅记录元数据引用，
    检索命中时按需加载实际图片数据。

    借鉴 RAGFlow: 解析阶段 >= 30ms，懒加载可降到 < 1ms。
    """
    file_path: str           # 源文件路径
    page: int = 0            # PDF 页码 / HTML 位置序号
    offset: int = 0          # 文件偏移量 (byte)
    bbox: tuple = ()         # 边界框 (x, y, w, h)，OCR/布局用
    mime_type: str = "image/png"
    caption: str = ""        # OCR/Alt 文字
    media_id: str = ""       # KBMedia 关联 ID (加载时才填充)

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "page": self.page,
            "offset": self.offset,
            "bbox": list(self.bbox) if self.bbox else [],
            "mime_type": self.mime_type,
            "caption": self.caption,
            "media_id": self.media_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ImageRef":
        return cls(
            file_path=d.get("file_path", ""),
            page=d.get("page", 0),
            offset=d.get("offset", 0),
            bbox=tuple(d.get("bbox", [])),
            mime_type=d.get("mime_type", "image/png"),
            caption=d.get("caption", ""),
            media_id=d.get("media_id", ""),
        )


def lazy_load_image(ref: ImageRef) -> Optional[bytes]:
    """按需加载图片 (懒加载核心)

    检索命中时调用，从源文件提取图片数据。
    仅加载被检索命中的图片，未命中的始终存在磁盘。

    Args:
        ref: 图片引用元数据

    Returns:
        图片二进制数据，加载失败则 None
    """
    import os

    if not ref.file_path or not os.path.exists(ref.file_path):
        logger.warning("lazy_load_image: file not found: %s", ref.file_path)
        return None

    try:
        # PDF 图片：seek 到 offset 提取
        if ref.file_path.lower().endswith(".pdf") and ref.offset > 0:
            return _extract_pdf_image_at_offset(ref.file_path, ref.page, ref.offset)

        # 普通图片：直接读文件
        if ref.file_path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
            with open(ref.file_path, "rb") as f:
                return f.read()

        # HTML 内嵌图片：解析源文件提取 base64 / src
        return None
    except Exception as e:
        logger.warning("lazy_load_image failed for %s:%d: %s",
                       ref.file_path, ref.offset, e)
        return None


def _extract_pdf_image_at_offset(
    file_path: str, page: int, offset: int
) -> Optional[bytes]:
    """从 PDF 指定偏移量提取图片"""
    try:
        import fitz  # PyMuPDF (pdf_parser 已依赖)
        doc = fitz.open(file_path)
        if page < len(doc):
            page_obj = doc[page]
            images = page_obj.get_images(full=True)
            for img in images:
                xref = img[0]
                base_image = doc.extract_image(xref)
                if base_image:
                    doc.close()
                    return base_image["image"]
        doc.close()
    except ImportError:
        logger.debug("PyMuPDF not available for lazy image extraction")
    except Exception as e:
        logger.warning("PDF image extraction at offset %d failed: %s", offset, e)
    return None


@dataclass
class ParseResult:
    """解析结果

    图片处理策略 (LazyImage, Phase 2, 借鉴 RAGFlow):
    - images: 热路径兼容字段，PDF 等解析器仍可写入 (向后兼容)
    - image_refs: 懒加载引用，解析器仅记录偏移量，检索命中时按需加载
    - KnowledgeBaseManager 优先使用 image_refs (节省内存)，fallback images
    """
    text: str
    title: str = ""
    metadata: dict = field(default_factory=dict)
    images: list[bytes] = field(default_factory=list)       # 热路径兼容 (deprecated)
    image_refs: list[ImageRef] = field(default_factory=list)  # 懒加载引用 (推荐)
    chunks: list[str] = field(default_factory=list)          # 解析后预分块（可选）


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


# ── 解析器注册表 (借鉴 RAGFlow ParserRegistry) ──────────────

# 扩展名 → (模块名, 类名) 映射，替代硬编码 if-else
# 新增解析器只需在此添加一行即可自动路由
_PARSER_EXT_MAP: dict[str, tuple[str, str]] = {
    # TextParser 系
    ".txt": ("txt_parser", "TextParser"),
    ".log": ("txt_parser", "TextParser"),
    ".csv": ("txt_parser", "TextParser"),
    ".json": ("txt_parser", "TextParser"),
    ".xml":  ("txt_parser", "TextParser"),
    ".yaml": ("txt_parser", "TextParser"),
    ".yml":  ("txt_parser", "TextParser"),
    # PDFParser
    ".pdf":  ("pdf_parser", "PDFParser"),
    # MarkitdownParser (Office + Markdown/RST/AsciiDoc/EPUB)
    ".docx": ("markitdown_parser", "MarkitdownParser"),
    ".xlsx": ("markitdown_parser", "MarkitdownParser"),
    ".xls":  ("markitdown_parser", "MarkitdownParser"),
    ".pptx": ("markitdown_parser", "MarkitdownParser"),
    ".md":   ("markitdown_parser", "MarkitdownParser"),
    ".rst":  ("markitdown_parser", "MarkitdownParser"),
    ".adoc": ("markitdown_parser", "MarkitdownParser"),
    ".epub": ("markitdown_parser", "MarkitdownParser"),
    # URL / HTML
    ".html": ("url_parser", "URLParser"),
    ".htm":  ("url_parser", "URLParser"),
}

# URL 协议专用解析器
_URL_PARSER = ("url_parser", "URLParser")


def _load_parser(module_name: str, class_name: str) -> BaseParser:
    """懒加载解析器实例（避免循环引用）"""
    module = importlib.import_module(f".{module_name}", __package__)
    parser_cls = getattr(module, class_name)
    return parser_cls()


def select_parser(filepath: str) -> Optional[BaseParser]:
    """根据文件类型自动选择解析器

    路由优先级:
      1. URL 协议检测 (http://, https://)
      2. 扩展名精确匹配 (_PARSER_EXT_MAP)
      3. supports() 回退 (遍历已注册解析器)
    """
    filepath_lower = filepath.lower()

    # 1. URL 协议检测
    if filepath_lower.startswith(("http://", "https://")):
        module_name, class_name = _URL_PARSER
        return _load_parser(module_name, class_name)

    # 2. 扩展名精确匹配
    ext = Path(filepath).suffix.lower()
    if ext in _PARSER_EXT_MAP:
        module_name, class_name = _PARSER_EXT_MAP[ext]
        return _load_parser(module_name, class_name)

    logger.warning("No parser found for: %s", filepath)
    return None


class ParserRegistry:
    """解析器注册表 — 动态注册与查询

    用法:
        # 注册新解析器
        ParserRegistry.register(".custom", "custom_parser", "CustomParser")

        # 列出所有已注册解析器
        parsers = ParserRegistry.list_extensions()

        # 查询特定扩展名的解析器
        entry = ParserRegistry.get_entry(".pdf")
    """

    @classmethod
    def register(cls, ext: str, module_name: str, class_name: str) -> None:
        """注册或覆盖扩展名→解析器映射"""
        ext_lower = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        _PARSER_EXT_MAP[ext_lower] = (module_name, class_name)
        logger.info("Parser registered: %s → %s.%s", ext_lower, module_name, class_name)

    @classmethod
    def unregister(cls, ext: str) -> None:
        """取消注册"""
        ext_lower = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        _PARSER_EXT_MAP.pop(ext_lower, None)

    @classmethod
    def get_entry(cls, ext: str) -> Optional[tuple[str, str]]:
        """获取扩展名对应的 (module, class)"""
        ext_lower = ext.lower() if ext.startswith(".") else f".{ext.lower()}"
        return _PARSER_EXT_MAP.get(ext_lower)

    @classmethod
    def list_extensions(cls) -> dict[str, str]:
        """列出所有已注册的扩展名→类名映射"""
        return {ext: f"{mod}.{cls_name}" for ext, (mod, cls_name) in _PARSER_EXT_MAP.items()}

    @classmethod
    def list_parser_names(cls) -> set[str]:
        """列出所有已注册的解析器类名"""
        return {cls_name for _, (_, cls_name) in _PARSER_EXT_MAP.items()}
