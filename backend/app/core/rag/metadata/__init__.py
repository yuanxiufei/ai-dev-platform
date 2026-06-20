"""
结构化元数据提取引擎

借鉴 obsidian-clipper (MIT) 的 Defuddle 提取模式:
- 自动提取网页元数据（title, author, description, date, language, site_name）
- Schema.org JSON-LD 结构化数据提取
- Open Graph / Twitter Card 社交元数据
- 去噪后的纯文本正文
"""

from .extractor import MetadataExtractor, PageMetadata
from .sanitizer import HTMLSanitizer, SanitizeLevel

__all__ = [
    "MetadataExtractor",
    "PageMetadata",
    "HTMLSanitizer",
    "SanitizeLevel",
]
