"""
Sitemap 批量爬取策略

基于 sitemap.xml 的大规模站点抓取:
- 解析标准 sitemap.xml (支持嵌套索引)
- 提取 <url> / <loc> / <lastmod> / <changefreq> / <priority>
- 过滤策略: lastmod 增量 / 优先级排序 / changefreq 筛选
- 增量抓取: 仅抓取 lastmod 晚于上次抓取的页面
- 大规模并发控制

与现有 site_crawler.py 的关系:
  本模块是重构版，提供更精细的策略抽象和并发控制，
  旧 site_crawler.py 保留作为兼容层。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import AsyncIterator, Optional
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from ..types import CrawlTask, PageResult, StrategyType
from .base import BaseCrawlerStrategy
from .static import StaticCrawlerStrategy

logger = logging.getLogger("rag.crawler.sitemap")

# 标准 XML 命名空间
_SITEMAP_NS = {
    "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
    "image": "http://www.google.com/schemas/sitemap-image/1.1",
    "news": "http://www.google.com/schemas/sitemap-news/0.9",
    "video": "http://www.google.com/schemas/sitemap-video/1.1",
}


class SitemapCrawlerStrategy(BaseCrawlerStrategy):
    """Sitemap 批量抓取策略

    工作流:
        1. 下载 sitemap.xml (支持 gzip)
        2. 解析 URL 列表
        3. 过滤 (增量/优先级/频率)
        4. 并发抓取 (委托给 StaticCrawlerStrategy)
    """

    strategy_type = StrategyType.SITEMAP

    def __init__(
        self,
        timeout: float = 30.0,
        max_urls: int = 500,
        concurrent_fetches: int = 5,
        incremental: bool = False,          # 增量模式: 仅抓取 lastmod 晚于某日期
        last_fetch_before: str = "",        # ISO 日期: 抓取此日期之后的内容
        respect_priority: bool = True,       # 按 priority 排序
        respect_changefreq: bool = False,    # 按 changefreq 筛选
        allow_sub_sitemaps: bool = True,    # 解析嵌套 sitemap 索引
    ):
        super().__init__()
        self.timeout = timeout
        self.max_urls = max_urls
        self.concurrent_fetches = concurrent_fetches
        self.incremental = incremental
        self.last_fetch_before = last_fetch_before
        self.respect_priority = respect_priority
        self.respect_changefreq = respect_changefreq
        self.allow_sub_sitemaps = allow_sub_sitemaps

        self._client: Optional[httpx.AsyncClient] = None
        self._static_crawler = StaticCrawlerStrategy(timeout=timeout)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                http2=True,
            )
        return self._client

    def can_handle(self, url: str) -> bool:
        """识别 sitemap URL"""
        path = urlparse(url).path.lower()
        return (
            path.endswith("sitemap.xml")
            or path.endswith("sitemap.xml.gz")
            or path.endswith("sitemap_index.xml")
            or "/sitemap" in path
            or "sitemap" in url
        )

    async def fetch(self, task: CrawlTask) -> PageResult:
        """下载并解析 sitemap (不抓取具体页面)"""
        # Sitemap 本身只返回摘要信息，实际页面通过 fetch_batch 获取
        parsed = urlparse(task.url)
        result = PageResult(
            url=task.url, task_id=task.task_id, strategy=StrategyType.SITEMAP,
            domain=parsed.netloc,
            success=True,
            text=f"Sitemap at {task.url}",
        )
        return result

    async def fetch_batch(self, tasks: list[CrawlTask]) -> AsyncIterator[PageResult]:
        """批量抓取 sitemap 中的所有页面"""
        # 收集所有 sitemap URL
        all_urls: list[dict] = []

        for task in tasks:
            urls = await self._parse_sitemap(task.url)
            all_urls.extend(urls)

            if len(all_urls) >= self.max_urls:
                break

        # 过滤 + 排序
        filtered = self._filter_urls(all_urls)
        logger.info("Sitemap 解析完成: %d → %d URLs (筛选后)", len(all_urls), len(filtered))

        # 并发抓取
        semaphore = asyncio.Semaphore(self.concurrent_fetches)

        async def _fetch_one(entry: dict) -> PageResult:
            async with semaphore:
                crawl_task = CrawlTask(
                    url=entry["url"],
                    strategy=StrategyType.STATIC,
                    domain=entry.get("domain", ""),
                    metadata={
                        "lastmod": entry.get("lastmod", ""),
                        "changefreq": entry.get("changefreq", ""),
                        "priority": entry.get("priority", "0.5"),
                    },
                )
                return await self._static_crawler.fetch(crawl_task)

        # 分批并发
        for i in range(0, len(filtered), self.concurrent_fetches):
            batch = filtered[i:i + self.concurrent_fetches]
            results = await asyncio.gather(*[_fetch_one(e) for e in batch], return_exceptions=True)
            for r in results:
                if isinstance(r, PageResult):
                    if r.success:
                        self._stats["success"] += 1
                    else:
                        self._stats["failed"] += 1
                    self._stats["total"] += 1
                    yield r
                elif isinstance(r, Exception):
                    logger.warning("Sitemap 抓取异常: %s", r)

    # ── Sitemap 解析 ────────────────────────────────────

    async def _parse_sitemap(self, sitemap_url: str) -> list[dict]:
        """解析 sitemap.xml，返回 URLs 列表"""
        urls = []
        try:
            client = await self._get_client()
            resp = await client.get(sitemap_url)
            if resp.status_code != 200:
                return urls

            xml_text = resp.text

            # 尝试 gzip 解码
            if sitemap_url.endswith(".gz"):
                import gzip
                xml_text = gzip.decompress(resp.content).decode("utf-8")

            root = ElementTree.fromstring(xml_text)

            # 判断 sitemap index vs urlset
            root_tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag

            if root_tag == "sitemapindex" and self.allow_sub_sitemaps:
                # 嵌套 sitemap 索引 → 递归解析
                sub_sitemaps = []
                for sm in root.findall("sm:sitemap", _SITEMAP_NS) or root.findall("sitemap"):
                    loc = sm.find("sm:loc", _SITEMAP_NS) or sm.find("loc")
                    if loc is not None and loc.text:
                        sub_sitemaps.append(loc.text.strip())

                logger.debug("发现 %d 个子 sitemap", len(sub_sitemaps))
                for sub_url in sub_sitemaps[:20]:  # 限制子 sitemap 数量
                    sub_urls = await self._parse_sitemap(sub_url)
                    urls.extend(sub_urls)
            else:
                # urlset → 提取页面 URL
                for url_el in root.findall("sm:url", _SITEMAP_NS) or root.findall("url"):
                    loc = url_el.find("sm:loc", _SITEMAP_NS) or url_el.find("loc")
                    if loc is None or not loc.text:
                        continue

                    entry = {"url": loc.text.strip()}

                    lastmod = url_el.find("sm:lastmod", _SITEMAP_NS) or url_el.find("lastmod")
                    if lastmod is not None and lastmod.text:
                        entry["lastmod"] = lastmod.text.strip()

                    changefreq = url_el.find("sm:changefreq", _SITEMAP_NS) or url_el.find("changefreq")
                    if changefreq is not None and changefreq.text:
                        entry["changefreq"] = changefreq.text.strip()

                    priority = url_el.find("sm:priority", _SITEMAP_NS) or url_el.find("priority")
                    if priority is not None and priority.text:
                        entry["priority"] = priority.text.strip()

                    entry["domain"] = urlparse(entry["url"]).netloc
                    urls.append(entry)

        except ElementTree.ParseError:
            logger.warning("Sitemap XML 解析失败: %s", sitemap_url)
        except Exception as e:
            logger.warning("Sitemap 下载失败 %s: %s", sitemap_url, e)

        return urls

    # ── 过滤与排序 ──────────────────────────────────────

    def _filter_urls(self, urls: list[dict]) -> list[dict]:
        """过滤 + 排序 URLs"""
        # 增量过滤
        if self.incremental and self.last_fetch_before:
            urls = [
                u for u in urls
                if u.get("lastmod", "") >= self.last_fetch_before
            ]

        # changefreq 过滤
        if self.respect_changefreq:
            freq_order = {"always": 0, "hourly": 1, "daily": 2, "weekly": 3, "monthly": 4, "yearly": 5, "never": 99}
            urls = sorted(urls, key=lambda u: freq_order.get(u.get("changefreq", "weekly"), 3))

        # 优先级排序
        if self.respect_priority:
            urls = sorted(urls, key=lambda u: float(u.get("priority", "0.5")), reverse=True)

        # 截断
        return urls[:self.max_urls]

    async def close(self):
        """清理资源"""
        if self._client:
            await self._client.aclose()
            self._client = None
        await self._static_crawler.close()
