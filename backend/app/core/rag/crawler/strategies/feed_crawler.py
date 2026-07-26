"""
RSS / Atom Feed 爬取策略

支持 RSS 2.0 和 Atom 1.0 格式:
- 解析 <item> / <entry> 元素
- 提取标题、摘要、全文、发布日期、作者
- 检测全文是否已包含（无需二次抓取）
- HTML 标签清洗
- 分页自动发现 (RSS Hub/自增分页)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from ..quality import get_cleaner, get_scorer
from ..types import CrawlTask, PageResult, StrategyType
from .base import BaseCrawlerStrategy

logger = logging.getLogger("rag.crawler.feed")

# Atom 命名空间
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
# 常见的 RSS/Atom feed 路径模式
_FEED_PATTERNS = [
    "/feed", "/feed/", "/rss", "/rss/", "/atom.xml", "/rss.xml",
    "/feed.xml", "/index.xml", "/feeds/posts/default",
    "?feed=rss2", "?format=feed&type=rss",
]


class FeedCrawlerStrategy(BaseCrawlerStrategy):
    """RSS/Atom Feed 解析策略

    优势: 结构化数据，无需 HTML 解析，可直接获取标题+摘要+日期
    适用: 博客、新闻站点的 RSS/Atom 订阅源
    """

    strategy_type = StrategyType.FEED

    def __init__(
        self,
        timeout: float = 30.0,
        max_entries: int = 200,
        fetch_full_content: bool = False,  # 是否二次抓取全文
    ):
        super().__init__()
        self.timeout = timeout
        self.max_entries = max_entries
        self.fetch_full_content = fetch_full_content

        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                http2=True,
            )
        return self._client

    def can_handle(self, url: str) -> bool:
        """识别 RSS/Atom Feed URL"""
        path = urlparse(url).path.lower()
        for pattern in _FEED_PATTERNS:
            if pattern in path or pattern in url.lower():
                return True
        return False

    @staticmethod
    def discover_feed_url(html: str, base_url: str) -> Optional[str]:
        """从 HTML 页面中发现 Feed URL"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            # <link rel="alternate" type="application/rss+xml">
            for link in soup.find_all("link", rel="alternate"):
                link_type = link.get("type", "")
                if "rss" in link_type or "atom" in link_type or "feed" in link_type:
                    href = link.get("href", "")
                    if href:
                        return urljoin(base_url, href)
        except Exception:
            pass
        return None

    async def fetch(self, task: CrawlTask) -> PageResult:
        """下载并解析 Feed"""
        start = time.time()

        result = PageResult(
            url=task.url, task_id=task.task_id, strategy=StrategyType.FEED,
            domain=task.domain or urlparse(task.url).netloc,
        )

        try:
            client = await self._get_client()
            resp = await client.get(task.url)

            result.http_status = resp.status_code
            if resp.status_code != 200:
                result.error = f"HTTP {resp.status_code}"
                return result

            xml_text = resp.text
            entries = self._parse_feed(xml_text)

            # 转换为文本
            texts = []
            for entry in entries[:self.max_entries]:
                parts = []
                if entry.get("title"):
                    parts.append(f"# {entry['title']}")
                if entry.get("author"):
                    parts.append(f"作者: {entry['author']}")
                if entry.get("published"):
                    parts.append(f"日期: {entry['published']}")
                if entry.get("summary"):
                    parts.append(entry["summary"])
                if entry.get("content"):
                    parts.append(entry["content"])
                texts.append("\n\n".join(parts))

            result.title = f"RSS Feed: {resp.headers.get('title', task.url)}"
            result.text = "\n\n---\n\n".join(texts)
            result.text_length = len(result.text.split())
            result.language = self._detect_feed_lang(entries)
            result.extra["feed_entries"] = entries[:self.max_entries]
            result.extra["entry_count"] = len(entries)

            # 发现各篇文章链接
            result.discovered_urls = [
                e["link"] for e in entries[:self.max_entries] if e.get("link")
            ]

            scorer = get_scorer()
            result = scorer.score(result)

            if result.quality != "rejected":
                result.success = True

        except Exception as e:
            result.error = str(e)
            logger.warning("Feed 解析异常 %s: %s", task.url, e)

        result.fetch_time_ms = (time.time() - start) * 1000
        self._stats["total"] += 1
        self._stats["success"] += 1 if result.success else 0
        self._stats["failed"] += 0 if result.success else 1
        return result

    async def fetch_batch(self, tasks: list[CrawlTask]) -> AsyncIterator[PageResult]:
        """批量获取 Feeds"""
        results = await asyncio.gather(
            *[self.fetch(t) for t in tasks],
            return_exceptions=True,
        )
        for r in results:
            if isinstance(r, PageResult):
                yield r

    # ── Feed 解析 ───────────────────────────────────────

    def _parse_feed(self, xml_text: str) -> list[dict]:
        """解析 RSS 2.0 / Atom 1.0"""
        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError:
            logger.warning("Feed XML 解析失败")
            return []

        # 判断类型
        root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

        if root_tag == "rss":
            return self._parse_rss2(root)
        elif root_tag == "feed":
            return self._parse_atom(root)
        else:
            # RDF (RSS 1.0)
            return self._parse_rss1(root)

    def _parse_rss2(self, root) -> list[dict]:
        """解析 RSS 2.0"""
        entries = []
        channel = root.find("channel")
        if channel is None:
            return entries

        for item in channel.findall("item"):
            entry = {
                "title": self._text_of(item, "title"),
                "link": self._text_of(item, "link"),
                "summary": self._text_of(item, "description"),
                "author": self._text_of(item, "author") or self._text_of(item, "dc:creator"),
                "published": self._text_of(item, "pubDate"),
                "content": self._text_of(item, "content:encoded"),
            }
            # HTML 清理
            cleaner = get_cleaner()
            for field in ("summary", "content"):
                if entry.get(field):
                    entry[field] = cleaner._regex_clean(entry[field])
            entries.append(entry)

        return entries

    def _parse_atom(self, root) -> list[dict]:
        """解析 Atom 1.0"""
        entries = []
        for entry in root.findall("atom:entry", _ATOM_NS) or root.findall("entry"):
            data = {
                "title": self._atom_text(entry, "title"),
                "link": self._atom_link(entry),
                "summary": self._atom_text(entry, "summary"),
                "author": self._atom_author(entry),
                "published": self._atom_text(entry, "published") or self._atom_text(entry, "updated"),
                "content": self._atom_text(entry, "content"),
            }
            cleaner = get_cleaner()
            for field in ("summary", "content"):
                if data.get(field):
                    data[field] = cleaner._regex_clean(data[field])
            entries.append(data)

        return entries

    def _parse_rss1(self, root) -> list[dict]:
        """解析 RSS 1.0 (RDF)"""
        entries = []
        for item in root.findall("item") or root.findall("{http://purl.org/rss/1.0/}item"):
            entries.append({
                "title": self._text_of(item, "title"),
                "link": self._text_of(item, "link"),
                "summary": self._text_of(item, "description"),
                "author": self._text_of(item, "{http://purl.org/dc/elements/1.1/}creator"),
                "published": self._text_of(item, "{http://purl.org/dc/elements/1.1/}date"),
                "content": self._text_of(item, "{http://purl.org/rss/1.0/modules/content/}encoded"),
            })
        return entries

    # ── 提取辅助 ────────────────────────────────────────

    def _text_of(self, el, tag: str, default: str = "") -> str:
        """安全获取元素文本"""
        found = el.find(tag)
        if found is not None and found.text:
            return found.text.strip()
        return default

    def _atom_text(self, entry, tag: str) -> str:
        """获取 Atom 元素文本 (支持 type="html")"""
        for ns_tag in [f"atom:{tag}", tag]:
            found = entry.find(ns_tag, _ATOM_NS) if "atom:" in ns_tag else entry.find(ns_tag)
            if found is not None:
                if found.text:
                    return found.text.strip()
                # Atom content 可能为内嵌 XHTML
                if found.get("type") == "xhtml":
                    div = found.find("{http://www.w3.org/1999/xhtml}div")
                    if div is not None:
                        return ElementTree.tostring(div, encoding="unicode")
        return ""

    def _atom_link(self, entry) -> str:
        """获取 Atom 链接 (rel=alternate)"""
        for ns_tag in [f"atom:link", "link"]:
            for link in entry.findall(ns_tag, _ATOM_NS) if "atom:" in ns_tag else entry.findall(ns_tag):
                if link.get("rel") in (None, "alternate") and link.get("href"):
                    return link.get("href", "")
        return ""

    def _atom_author(self, entry) -> str:
        """获取 Atom 作者"""
        for ns_tag in [f"atom:author", "author"]:
            author_el = entry.find(ns_tag, _ATOM_NS) if "atom:" in ns_tag else entry.find(ns_tag)
            if author_el is not None:
                name = author_el.find("atom:name", _ATOM_NS) or author_el.find("name")
                if name is not None and name.text:
                    return name.text.strip()
        return ""

    def _detect_feed_lang(self, entries: list[dict]) -> str:
        """从条目内容检测语言"""
        sample = " ".join(
            e.get("title", "") + " " + e.get("summary", "")
            for e in entries[:5]
        )
        cjk = sum(1 for c in sample[:2000] if '\u4e00' <= c <= '\u9fff')
        latin = sum(1 for c in sample[:2000] if c.isascii() and c.isalpha())
        return "zh" if cjk > latin else "en" if latin > 0 else "unknown"

    async def close(self):
        """清理资源"""
        if self._client:
            await self._client.aclose()
            self._client = None
