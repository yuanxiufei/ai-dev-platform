"""
元数据提取器 — 借鉴 obsidian-clipper Defuddle 引擎模式

能力:
1. Schema.org JSON-LD 结构化数据提取
2. Open Graph / Twitter Card 社交元数据
3. HTML <meta> 标签解析
4. 自动语言检测
5. 站点名/域名推断

数据流:
  HTML → DOM 解析 → JSON-LD 提取 → Meta 标签提取 → Open Graph → 合并 → PageMetadata
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger("app.core.rag.metadata")


@dataclass
class PageMetadata:
    """网页结构化元数据 — 借鉴 obsidian-clipper buildVariables() 模式"""

    title: str = ""
    author: str = ""
    description: str = ""
    published_date: str = ""      # ISO 8601 格式
    language: str = ""
    site_name: str = ""
    domain: str = ""
    favicon_url: str = ""
    image_url: str = ""
    word_count: int = 0
    content_type: str = ""        # article | recipe | product | video | unknown

    # Schema.org 结构化数据
    schema_org_data: dict = field(default_factory=dict)

    # Open Graph / Twitter Card
    og_data: dict = field(default_factory=dict)

    # 原始 meta 标签 (key → 去重列表)
    meta_tags: dict[str, list[str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转为字典，过滤空值"""
        d = {k: v for k, v in self.__dict__.items() if v}
        return d


class MetadataExtractor:
    """
    HTML 元数据提取器

    借鉴 obsidian-clipper defuddle 引擎的提取流水线:
    1. JSON-LD 结构化数据 (优先级最高)
    2. Open Graph + Twitter Card (次高)
    3. HTML <title> 和 <meta> 标签 (兜底)
    """

    # Schema.org type 到 content_type 的映射
    _SCHEMA_TYPE_MAP: dict[str, str] = {
        "Article":        "article",
        "NewsArticle":    "article",
        "BlogPosting":    "article",
        "Recipe":         "recipe",
        "Product":        "product",
        "VideoObject":    "video",
        "Book":           "article",
        "WebPage":        "article",
        "Review":         "article",
        "HowTo":          "article",
        "FAQPage":        "article",
    }

    # 已知站点名映射 (用于无法从元数据提取时)
    _KNOWN_DOMAINS: dict[str, str] = {
        "github.com":      "GitHub",
        "stackoverflow.com": "Stack Overflow",
        "medium.com":      "Medium",
        "dev.to":          "DEV Community",
        "arxiv.org":       "arXiv",
        "zhihu.com":       "知乎",
        "juejin.cn":       "掘金",
        "segmentfault.com":"SegmentFault",
        "docs.python.org": "Python Docs",
        "developer.mozilla.org": "MDN Web Docs",
    }

    def __init__(self, html: str, url: str = ""):
        self._html = html
        self._url = url
        self._domain = self._extract_domain(url)
        self._parsed = self._parse_html()

    def extract(self) -> PageMetadata:
        """完整提取流水线"""
        meta = PageMetadata(domain=self._domain)

        # 1. JSON-LD 结构化数据 (最可信的来源)
        meta.schema_org_data = self._extract_json_ld()
        meta = self._apply_schema_org(meta)

        # 2. Open Graph / Twitter Card
        meta.og_data = self._extract_open_graph()
        meta = self._apply_og(meta)

        # 3. HTML Meta + Title
        meta = self._extract_meta_tags(meta)
        meta = self._extract_title(meta)

        # 4. 推断字段
        meta = self._infer_missing(meta)

        return meta

    # ── 提取器核心方法 ──────────────────────────────────────

    def _extract_json_ld(self) -> dict:
        """提取 JSON-LD 结构化数据"""
        result = {}
        # 匹配 <script type="application/ld+json">...</script>
        pattern = re.compile(
            r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE,
        )
        for match in pattern.finditer(self._html):
            try:
                data = json.loads(match.group(1))
                # 支持数组和单个对象
                if isinstance(data, list):
                    for item in data:
                        result.update(item)
                else:
                    result.update(data)
            except json.JSONDecodeError:
                logger.debug("Failed to parse JSON-LD block")
        return result

    def _apply_schema_org(self, meta: PageMetadata) -> PageMetadata:
        """从 Schema.org 数据填充元数据"""
        data = meta.schema_org_data
        if not data:
            return meta

        # @type → content_type
        schema_type = data.get("@type", "")
        if schema_type in self._SCHEMA_TYPE_MAP:
            meta.content_type = self._SCHEMA_TYPE_MAP[schema_type]
        elif schema_type:
            meta.content_type = schema_type.lower()

        # 通用字段
        if not meta.title:
            meta.title = data.get("headline") or data.get("name", "")
        if not meta.author:
            author = data.get("author", {})
            if isinstance(author, dict):
                meta.author = author.get("name", "")
            elif isinstance(author, list) and author:
                a = author[0]
                meta.author = a.get("name", "") if isinstance(a, dict) else str(a)
            elif isinstance(author, str):
                meta.author = author
        if not meta.description:
            meta.description = data.get("description", "")
        if not meta.published_date:
            meta.published_date = data.get("datePublished", "") or data.get("dateCreated", "")
        if not meta.language:
            meta.language = data.get("inLanguage", "")
        if not meta.image_url:
            image = data.get("image", {})
            if isinstance(image, dict):
                meta.image_url = image.get("url", "")
            elif isinstance(image, str):
                meta.image_url = image

        # publisher → site_name
        if not meta.site_name:
            publisher = data.get("publisher", {})
            if isinstance(publisher, dict):
                meta.site_name = publisher.get("name", "")
            elif isinstance(publisher, str):
                meta.site_name = publisher

        return meta

    def _extract_open_graph(self) -> dict:
        """提取 Open Graph + Twitter Card 元数据"""
        result: dict = {}
        tag_map: dict[str, tuple[str, str]] = {
            # (property/name attr, content attr 的 key)
            "title":       ("og:title", "twitter:title"),
            "description": ("og:description", "twitter:description"),
            "image":       ("og:image", "twitter:image"),
            "site_name":   ("og:site_name", None),
            "type":        ("og:type", None),
            "locale":      ("og:locale", None),
        }

        for field, (og_key, twitter_key) in tag_map.items():
            # 尝试 property=og:xxx
            m = re.search(
                rf'<meta[^>]+property\s*=\s*["\']{re.escape(og_key)}["\'][^>]+content\s*=\s*["\']([^"\']*)["\']',
                self._html, re.IGNORECASE,
            )
            if not m:
                # 反序: content 在前 property 在后
                m = re.search(
                    rf'<meta[^>]+content\s*=\s*["\']([^"\']*)["\'][^>]+property\s*=\s*["\']{re.escape(og_key)}["\']',
                    self._html, re.IGNORECASE,
                )
            if not m and twitter_key:
                m = re.search(
                    rf'<meta[^>]+name\s*=\s*["\']{re.escape(twitter_key)}["\'][^>]+content\s*=\s*["\']([^"\']*)["\']',
                    self._html, re.IGNORECASE,
                )
            if m:
                result[field] = m.group(1).strip()

        return result

    def _apply_og(self, meta: PageMetadata) -> PageMetadata:
        """从 OG 数据填充 (优先级低于 JSON-LD)"""
        og = meta.og_data
        if not meta.title:
            meta.title = og.get("title", "")
        if not meta.description:
            meta.description = og.get("description", "")
        if not meta.image_url:
            meta.image_url = og.get("image", "")
        if not meta.site_name:
            meta.site_name = og.get("site_name", "")
        if not meta.language:
            lang = og.get("locale", "")
            if lang:
                meta.language = lang.replace("_", "-").split("-")[0]
        content_type = og.get("type", "")
        if content_type and not meta.content_type:
            meta.content_type = content_type.lower()
        return meta

    def _extract_meta_tags(self, meta: PageMetadata) -> PageMetadata:
        """提取 HTML <meta> 标签"""
        meta_tags: dict[str, list[str]] = {}

        # 匹配所有 meta 标签
        tag_pattern = re.compile(
            r'<meta[^>]+(?:name|property|http-equiv)\s*=\s*["\']([^"\']*)["\'](?:[^>]+content\s*=\s*["\']([^"\']*)["\']|[^>]+?)',
            re.IGNORECASE,
        )
        # 更简单的双模式匹配
        pattern_a = re.compile(
            r'<meta[^>]+name\s*=\s*["\']([^"\']*)["\'][^>]+content\s*=\s*["\']([^"\']*)["\']',
            re.IGNORECASE,
        )
        pattern_b = re.compile(
            r'<meta[^>]+content\s*=\s*["\']([^"\']*)["\'][^>]+name\s*=\s*["\']([^"\']*)["\']',
            re.IGNORECASE,
        )
        pattern_c = re.compile(
            r'<meta[^>]+property\s*=\s*["\']([^"\']*)["\'][^>]+content\s*=\s*["\']([^"\']*)["\']',
            re.IGNORECASE,
        )

        for p in (pattern_a, pattern_b):
            for m in p.finditer(self._html):
                name = m.group(1).strip().lower()
                value = m.group(2).strip()
                meta_tags.setdefault(name, []).append(value)

        for m in pattern_c.finditer(self._html):
            name = m.group(1).strip().lower()
            value = m.group(2).strip()
            meta_tags.setdefault(name, []).append(value)

        meta.meta_tags = meta_tags

        # 从 meta 标签填充元数据
        if not meta.author:
            meta.author = meta_tags.get("author", [""])[0]
        if not meta.description:
            meta.description = meta_tags.get("description", [""])[0]
        if not meta.published_date:
            meta.published_date = (
                meta_tags.get("article:published_time", [""])[0] or
                meta_tags.get("date", [""])[0]
            )
        if not meta.language:
            meta.language = (
                meta_tags.get("language", [""])[0] or
                meta_tags.get("content-language", [""])[0]
            )

        return meta

    def _extract_title(self, meta: PageMetadata) -> PageMetadata:
        """从 <title> 标签提取标题 (最低优先级兜底)"""
        if meta.title:
            return meta

        m = re.search(
            r'<title[^>]*>(.*?)</title>',
            self._html, re.IGNORECASE | re.DOTALL,
        )
        if m:
            meta.title = m.group(1).strip()
        return meta

    def _infer_missing(self, meta: PageMetadata) -> PageMetadata:
        """推断缺失字段"""
        # 站点名: 已知域名 → domain
        if not meta.site_name and self._domain:
            meta.site_name = self._KNOWN_DOMAINS.get(self._domain, self._domain)

        # 语言: 从 lang 属性检测
        if not meta.language:
            m = re.search(r'<html[^>]+lang\s*=\s*["\']([a-z]{2})', self._html, re.IGNORECASE)
            if m:
                meta.language = m.group(1)

        # favicon
        if not meta.favicon_url:
            meta.favicon_url = self._extract_favicon()

        return meta

    def _extract_favicon(self) -> str:
        """提取 favicon URL"""
        patterns = [
            r'<link[^>]+rel\s*=\s*["\'](?:shortcut\s+)?icon["\'][^>]+href\s*=\s*["\']([^"\']*)["\']',
            r'<link[^>]+href\s*=\s*["\']([^"\']*)["\'][^>]+rel\s*=\s*["\'](?:shortcut\s+)?icon["\']',
        ]
        for p in patterns:
            m = re.search(p, self._html, re.IGNORECASE)
            if m:
                favicon = m.group(1).strip()
                return self._resolve_url(favicon)
        # 默认 favicon
        if self._domain:
            return f"https://{self._domain}/favicon.ico"
        return ""

    # ── 工具方法 ──────────────────────────────────────────────

    def _parse_html(self) -> dict:
        """快速解析 HTML 关键部分（轻量，不建 DOM）"""
        return {}

    def _resolve_url(self, href: str) -> str:
        """解析相对 URL 为绝对 URL"""
        if href.startswith(("http://", "https://")):
            return href
        if href.startswith("//"):
            return f"https:{href}"
        if self._url:
            from urllib.parse import urljoin
            return urljoin(self._url, href)
        return href

    @staticmethod
    def _extract_domain(url: str) -> str:
        """提取域名"""
        if not url:
            return ""
        try:
            return urlparse(url).netloc.lower()
        except Exception:
            return ""
