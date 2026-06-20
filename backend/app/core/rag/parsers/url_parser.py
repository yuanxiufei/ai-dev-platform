"""
URL 解析器 — 借鉴 obsidian-clipper Defuddle 模式的三级提取策略

借鉴来源:
  obsidian-clipper (MIT) Defuddle 引擎模式:
    - 自动正文提取 + 结构化元数据 (JSON-LD/Open Graph/Meta)
  AstrBot URLExtractor:
    - Tavily API 多 key 轮换
    - readability 回退

升级内容 (v2):
  ✅ MetadataExtractor — JSON-LD / OG / Meta 标签结构化元数据
  ✅ HTMLSanitizer — 三重清洗级别 (NORMAL/STRICT/MINIMAL)
  ✅ ParseResult 元数据富化 — title/author/date/language/site_name/schema_org
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from . import BaseParser, ParseResult

logger = logging.getLogger("app.core.rag.parsers.url")


class URLParser(BaseParser):
    """URL 内容提取器 — 三级回退: Tavily → readability → 简单清洗"""

    def __init__(
        self,
        tavily_api_keys: list[str] | None = None,
        use_tavily: bool = True,
    ):
        self._tavily_keys = tavily_api_keys or []
        self._key_index = 0
        self._use_tavily = use_tavily

    @property
    def name(self) -> str:
        return "url_parser"

    def supports(self, filepath: str) -> bool:
        return filepath.lower().startswith(("http://", "https://"))

    async def parse(self, filepath: str) -> ParseResult:
        """解析 URL 内容 — 三级回退 + 元数据富化"""
        # 尝试 Tavily
        if self._use_tavily and self._tavily_keys:
            try:
                text, title = await self._tavily_extract(filepath)
                if text:
                    return ParseResult(
                        text=text,
                        title=title,
                        metadata={
                            "parser": self.name,
                            "source": filepath,
                            "method": "tavily",
                        },
                    )
            except Exception as e:
                logger.debug("Tavily extraction failed for %s: %s", filepath, e)

        # 回退: 直接 HTTP + readability + 元数据富化
        try:
            result = await self._http_extract_rich(filepath)
            return result
        except Exception as e:
            logger.warning("HTTP extraction failed for %s: %s", filepath, e)
            return ParseResult(
                text=f"[Content unavailable: {filepath}]",
                title=self._extract_domain(filepath),
                metadata={
                    "parser": self.name,
                    "source": filepath,
                    "method": "fallback",
                    "error": str(e),
                },
            )

    # ── Tavily API ────────────────────────────────────────────

    async def _tavily_extract(self, url: str) -> tuple[str, str]:
        """通过 Tavily Extract API 提取"""
        api_key = self._rotate_key()
        if not api_key:
            raise ValueError("No Tavily API key available")

        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tavily.com/extract",
                json={"api_key": api_key, "urls": [url]},
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Tavily API error: {resp.status}")
                data = await resp.json()
                results = data.get("results", [])
                if results and results[0].get("raw_content"):
                    return results[0]["raw_content"], results[0].get("title", "")
        return "", ""

    # ── HTTP 提取 (v2 升级: 元数据富化) ──────────────────────

    async def _http_extract_rich(self, url: str) -> ParseResult:
        """HTTP 提取 + readability + 元数据富化"""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                html = await resp.text()

        text_content = ""
        title = ""

        # 1. 提取正文 (readability)
        try:
            from readability import Document
            doc = Document(html)
            title = doc.short_title()
            text_content = self._strip_html(doc.summary(html_partial=True))
        except (ImportError, Exception):
            text_content = self._strip_html(html)
            import re
            m = re.search(
                r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL,
            )
            if m:
                title = m.group(1).strip()

        # 2. 元数据富化 (借鉴 obsidian-clipper Defuddle)
        metadata = {
            "parser": self.name,
            "source": url,
            "method": "http",
        }

        try:
            from app.core.rag.metadata.extractor import MetadataExtractor
            extractor = MetadataExtractor(html, url)
            page_meta = extractor.extract()

            # 融入核心元数据
            if not title and page_meta.title:
                title = page_meta.title

            metadata.update({
                "title": page_meta.title or title,
                "author": page_meta.author,
                "published_date": page_meta.published_date,
                "language": page_meta.language,
                "site_name": page_meta.site_name,
                "domain": page_meta.domain,
                "image_url": page_meta.image_url,
                "favicon_url": page_meta.favicon_url,
                "word_count": page_meta.word_count or (
                    len(text_content.split()) if text_content else 0
                ),
                "content_type": page_meta.content_type,
                "schema_org_data": page_meta.schema_org_data if page_meta.schema_org_data else None,
                "og_data": page_meta.og_data if page_meta.og_data else None,
            })

            # 移除 None 值
            metadata = {k: v for k, v in metadata.items() if v is not None}

        except ImportError as e:
            logger.debug("Metadata module not available: %s", e)
        except Exception as e:
            logger.warning("Metadata extraction failed for %s: %s", url, e)

        return ParseResult(
            text=text_content.strip() if text_content else f"[Failed to extract content from: {url}]",
            title=title.strip() if title else self._extract_domain(url),
            metadata=metadata,
        )

    # ── 工具方法 ──────────────────────────────────────────────

    def _rotate_key(self) -> str:
        """轮换 Tavily API key"""
        if not self._tavily_keys:
            return ""
        key = self._tavily_keys[self._key_index]
        self._key_index = (self._key_index + 1) % len(self._tavily_keys)
        return key

    @staticmethod
    def _strip_html(html: str) -> str:
        """
        移除 HTML 标签 — 使用 HTMLSanitizer (normal 级别)

        借鉴 obsidian-clipper: DOMPurify → readability → sanitize
        """
        try:
            from app.core.rag.metadata.sanitizer import HTMLSanitizer, SanitizeLevel
            return HTMLSanitizer(level=SanitizeLevel.NORMAL).sanitize(html)
        except ImportError:
            # 回退: 简单正则
            import re
            text = re.sub(
                r"<(script|style)[^>]*>.*?</\1>",
                "", html, flags=re.DOTALL | re.IGNORECASE,
            )
            text = re.sub(r"<[^>]+>", " ", text)
            import html as _html
            text = _html.unescape(text)
            text = re.sub(r"\s+", " ", text)
            return text

    @staticmethod
    def _extract_domain(url: str) -> str:
        parsed = urlparse(url)
        return parsed.netloc or url
