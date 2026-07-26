"""
文档网站批量抓取器 — Sitemap 解析 + 同域爬取

支持两种模式:
  1. Sitemap 模式 — 解析 sitemap.xml (支持嵌套索引), 批量提取所有 URL
  2. URL 列表模式 — 直接传入 URL 列表, 逐个抓取

使用现有 URLParser 三级回退策略抓取每个页面内容。
"""

from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, urljoin

import aiohttp

logger = logging.getLogger("app.core.rag.parsers.crawler")


@dataclass
class CrawlResult:
    """单个页面抓取结果"""
    url: str
    title: str = ""
    text: str = ""
    success: bool = False
    error: str = ""
    word_count: int = 0


@dataclass
class BatchCrawlResult:
    """批量抓取结果汇总"""
    total_urls: int = 0
    succeeded: int = 0
    failed: int = 0
    pages: list[CrawlResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    base_domain: str = ""

    @property
    def all_texts(self) -> list[dict]:
        """返回所有成功抓取的文本 (title + content)"""
        return [
            {"title": p.title, "text": p.text, "url": p.url, "word_count": p.word_count}
            for p in self.pages if p.success
        ]


class SitemapParser:
    """Sitemap XML 解析器 — 支持 .xml / .xml.gz / 嵌套索引"""

    SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"

    @staticmethod
    async def fetch_urls(sitemap_url: str, timeout: int = 30) -> list[str]:
        """
        从 sitemap URL 提取所有页面链接

        支持:
          - 标准 sitemap.xml
          - 嵌套 sitemap index (多个子 sitemap)
          - gzip 压缩的 sitemap
        """
        async with aiohttp.ClientSession() as session:
            return await SitemapParser._fetch_recursive(session, sitemap_url, timeout, set())

    @classmethod
    async def _fetch_recursive(
        cls,
        session: aiohttp.ClientSession,
        url: str,
        timeout: int,
        visited: set[str],
    ) -> list[str]:
        """递归解析 sitemap (处理索引嵌套)"""
        if url in visited:
            return []
        visited.add(url)

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    logger.warning("Failed to fetch sitemap %s: HTTP %d", url, resp.status)
                    return []

                content_type = resp.headers.get("Content-Type", "")
                body = await resp.read()

                # 检测 gzip
                if url.endswith(".gz") or "gzip" in content_type.lower():
                    import gzip
                    try:
                        body = gzip.decompress(body)
                    except Exception as e:
                        logger.warning("Failed to decompress gzip sitemap %s: %s", url, e)
                        return []

                xml_text = body.decode("utf-8", errors="replace")

        except asyncio.TimeoutError:
            logger.warning("Timeout fetching sitemap: %s", url)
            return []
        except Exception as e:
            logger.warning("Failed to fetch sitemap %s: %s", url, e)
            return []

        return cls._parse_xml(session, url, xml_text, timeout, visited)

    @classmethod
    def _parse_xml(
        cls,
        session: aiohttp.ClientSession,
        base_url: str,
        xml_text: str,
        timeout: int,
        visited: set[str],
    ) -> list[str]:
        """解析 XML 内容，区分 URL 条目和子索引"""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning("XML parse error for %s: %s", base_url, e)
            return []

        # 检测命名空间
        ns = cls.SITEMAP_NS
        has_ns = root.tag.startswith("{")

        # 判断是否为 sitemap index (嵌套)
        sitemap_tags = root.findall(f"{{{ns}}}sitemap") if has_ns else root.findall("sitemap")
        if sitemap_tags:
            # 递归处理子 sitemap
            all_urls = []
            for sm in sitemap_tags:
                loc = sm.find(f"{{{ns}}}loc") if has_ns else sm.find("loc")
                if loc is not None and loc.text:
                    sub_url = loc.text.strip()
                    # 异步递归需要事件循环处理
                    all_urls.append(sub_url)
            logger.debug("Sitemap index with %d sub-sitemaps at %s", len(all_urls), base_url)
            return all_urls  # 返回子 sitemap URL，由调用方递归 fetch

        # 标准 sitemap: 提取 <url><loc> 条目
        url_tags = root.findall(f"{{{ns}}}url") if has_ns else root.findall("url")
        urls = []
        for tag in url_tags:
            loc = tag.find(f"{{{ns}}}loc") if has_ns else tag.find("loc")
            if loc is not None and loc.text:
                urls.append(loc.text.strip())

        logger.info("Parsed %d URLs from sitemap: %s", len(urls), base_url)
        return urls


class SiteCrawler:
    """
    文档网站批量抓取器

    支持:
      - sitemap 自动发现: 传入网站首页, 自动查找 sitemap.xml
      - 同域限制: 只抓取同一域名下的页面
      - 并发控制: max_concurrent 限制同时抓取数
      - 进度回调: progress_callback(done, total, current_url)
      - 单页使用现有 URLParser (三级回退: Tavily → readability → 简单清洗)
    """

    # sitemap 常见路径
    SITEMAP_PATHS = [
        "sitemap.xml",
        "sitemap_index.xml",
        "sitemap-index.xml",
        "sitemap/sitemap.xml",
        "wp-sitemap.xml",
    ]

    def __init__(
        self,
        max_concurrent: int = 3,
        timeout: int = 30,
        request_delay: float = 0.5,
        same_domain_only: bool = True,
    ):
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self.request_delay = request_delay
        self.same_domain_only = same_domain_only
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def crawl_sitemap(
        self,
        sitemap_url: str,
        url_filter: Optional[callable] = None,
        max_pages: int = 100,
        progress_callback: Optional[callable] = None,
    ) -> BatchCrawlResult:
        """
        从 sitemap 抓取所有页面

        Args:
            sitemap_url: sitemap.xml 地址
            url_filter: 可选过滤函数, (url: str) -> bool
            max_pages: 最大抓取页数
            progress_callback: async (done: int, total: int, current_url: str) -> None
        """
        domain = urlparse(sitemap_url).netloc

        # 1. 解析 sitemap (支持嵌套索引)
        all_urls = await self._resolve_sitemap_tree(sitemap_url)
        if not all_urls:
            logger.warning("No URLs found in sitemap: %s", sitemap_url)
            return BatchCrawlResult(base_domain=domain)

        # 2. 过滤
        urls = self._filter_urls(all_urls, domain, url_filter, max_pages)
        logger.info("Crawling %d/%d URLs from %s", len(urls), len(all_urls), domain)

        # 3. 并发抓取
        return await self._crawl_batch(urls, domain, progress_callback)

    async def crawl_from_page(
        self,
        start_url: str,
        url_filter: Optional[callable] = None,
        max_pages: int = 100,
        progress_callback: Optional[callable] = None,
    ) -> BatchCrawlResult:
        """
        从 HTML 页面出发，通过链接发现进行抓取（sitemap 不可用时的降级方案）

        1. 抓取 start_url 页面，提取所有同域 <a href> 链接
        2. 并发抓取所有发现的页面
        """
        domain = urlparse(start_url).netloc

        # 发现链接
        logger.info("Discovering links from start page: %s", start_url)
        links = await self._extract_links_from_page(start_url)
        if not links:
            logger.warning("No links extracted from %s, crawling single page", start_url)
            links = [start_url]
        else:
            logger.info("Discovered %d links from %s", len(links), start_url)

        # 过滤
        urls = self._filter_urls(links, domain, url_filter, max_pages)
        return await self._crawl_batch(urls, domain, progress_callback)

    async def _extract_links_from_page(self, url: str) -> list[str]:
        """从 HTML 页面提取所有同域链接"""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    allow_redirects=True,
                    ssl=False,  # 部分中文站点证书不标准
                ) as resp:
                    if resp.status != 200:
                        logger.warning(
                            "Link extraction: HTTP %d for %s", resp.status, url,
                        )
                        return []
                    html = await resp.text()
        except Exception as e:
            logger.warning("Failed to fetch page for link extraction %s: %s", url, str(e)[:200])
            return []

        import re
        href_pattern = re.compile(r'<a[^>]+href=["\']([^"\']+)["\']', re.IGNORECASE)
        matches = href_pattern.findall(html)

        domain = urlparse(url).netloc
        links = []
        seen = set()
        for href in matches:
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            full_url = urljoin(url, href)
            parsed = urlparse(full_url)
            if parsed.netloc != domain:
                continue
            # 跳过非页面资源
            skip_ext = (
                ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
                ".css", ".js", ".woff", ".woff2", ".ttf",
                ".pdf", ".zip", ".tar", ".gz", ".mp4", ".webm",
            )
            if any(full_url.lower().endswith(ext) for ext in skip_ext):
                continue
            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)

        return links

    async def crawl_urls(
        self,
        urls: list[str],
        url_filter: Optional[callable] = None,
        progress_callback: Optional[callable] = None,
    ) -> BatchCrawlResult:
        """
        从 URL 列表批量抓取 (非 sitemap 模式)
        """
        if not urls:
            return BatchCrawlResult()

        domain = urlparse(urls[0]).netloc
        filtered = self._filter_urls(urls, domain, url_filter, len(urls))
        return await self._crawl_batch(filtered, domain, progress_callback)

    async def discover_and_crawl(
        self,
        base_url: str,
        url_filter: Optional[callable] = None,
        max_pages: int = 100,
        progress_callback: Optional[callable] = None,
    ) -> BatchCrawlResult:
        """
        自动发现 sitemap 并抓取

        传入网站首页 (如 https://docs.example.com),
        自动尝试 sitemap.xml / robots.txt 等发现 sitemap。
        """
        base_url = base_url.rstrip("/")
        domain = urlparse(base_url).netloc

        # 尝试发现 sitemap
        sitemap_url = await self._discover_sitemap(base_url)
        if sitemap_url:
            logger.info("Discovered sitemap: %s", sitemap_url)
            return await self.crawl_sitemap(sitemap_url, url_filter, max_pages, progress_callback)

        logger.warning("No sitemap found for %s", base_url)
        return BatchCrawlResult(base_domain=domain)

    # ── sitemap 发现 ─────────────────────────────────────

    async def _discover_sitemap(self, base_url: str) -> Optional[str]:
        """自动发现 sitemap URL"""
        # 1. 尝试 robots.txt
        sitemap_url = await self._check_robots_txt(base_url)
        if sitemap_url:
            return sitemap_url

        # 2. 尝试常见路径
        for path in self.SITEMAP_PATHS:
            sitemap_url = urljoin(base_url + "/", path)
            if await self._url_exists(sitemap_url):
                return sitemap_url

        return None

    async def _check_robots_txt(self, base_url: str) -> Optional[str]:
        """从 robots.txt 提取 Sitemap 声明"""
        robots_url = urljoin(base_url + "/", "robots.txt")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    robots_url, timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        for line in text.splitlines():
                            line_lower = line.strip().lower()
                            if line_lower.startswith("sitemap:"):
                                return line.strip().split(":", 1)[1].strip()
        except Exception:
            pass
        return None

    async def _url_exists(self, url: str) -> bool:
        """HEAD 请求检查 URL 是否存在"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url, timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False

    # ── sitemap 解析 (处理嵌套) ─────────────────────────

    async def _resolve_sitemap_tree(self, sitemap_url: str) -> list[str]:
        """
        递归解析 sitemap 树 (索引 → 子 sitemap → URL)

        因为 SitemapParser._parse_xml 返回的是子 sitemap URL 列表(索引)
        或页面 URL 列表(最终), 这里要区分处理。
        """
        all_urls = []
        visited = {sitemap_url}
        queue = [sitemap_url]

        async with aiohttp.ClientSession() as session:
            while queue:
                batch = queue[:10]
                queue = queue[10:]

                # 并发解析当前批次
                tasks = [self._fetch_sitemap(session, url) for url in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for url, result in zip(batch, results):
                    if isinstance(result, Exception):
                        logger.warning("Error resolving sitemap %s: %s", url, result)
                        continue

                    sub_urls, is_index = result
                    for u in sub_urls:
                        if u not in visited:
                            visited.add(u)
                            if is_index:
                                queue.append(u)  # 子 sitemap, 继续递归
                            else:
                                all_urls.append(u)  # 最终页面 URL

        return all_urls

    async def _fetch_sitemap(
        self, session: aiohttp.ClientSession, url: str,
    ) -> tuple[list[str], bool]:
        """获取并解析单个 sitemap, 返回 (URL列表, 是否为索引)"""
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status != 200:
                    return [], False

                body = await resp.read()
                if url.endswith(".gz"):
                    import gzip
                    body = gzip.decompress(body)

                xml_text = body.decode("utf-8", errors="replace")
                root = ET.fromstring(xml_text)

                ns = SitemapParser.SITEMAP_NS
                has_ns = root.tag.startswith("{")

                # 检测是否为 sitemap index
                sitemap_tags = root.findall(f"{{{ns}}}sitemap") if has_ns else root.findall("sitemap")
                if sitemap_tags:
                    urls = []
                    for sm in sitemap_tags:
                        loc = sm.find(f"{{{ns}}}loc") if has_ns else sm.find("loc")
                        if loc is not None and loc.text:
                            urls.append(loc.text.strip())
                    return urls, True  # 是索引

                # 标准 sitemap: 提取 <url><loc>
                url_tags = root.findall(f"{{{ns}}}url") if has_ns else root.findall("url")
                urls = []
                for tag in url_tags:
                    loc = tag.find(f"{{{ns}}}loc") if has_ns else tag.find("loc")
                    if loc is not None and loc.text:
                        urls.append(loc.text.strip())

                return urls, False  # 是页面链接

        except Exception as e:
            logger.warning("Sitemap fetch error %s: %s", url, e)
            return [], False

    # ── 批量抓取 ────────────────────────────────────────

    async def _crawl_batch(
        self,
        urls: list[str],
        domain: str,
        progress_callback: Optional[callable] = None,
    ) -> BatchCrawlResult:
        """并发抓取 URL 列表"""
        total = len(urls)
        result = BatchCrawlResult(total_urls=total, base_domain=domain)

        if total == 0:
            return result

        sem = asyncio.Semaphore(self.max_concurrent)
        done_count = 0

        async def crawl_one(url: str) -> CrawlResult:
            nonlocal done_count
            async with sem:
                if self.request_delay > 0:
                    await asyncio.sleep(self.request_delay)

                cr = await self._crawl_single_page(url)

                done_count += 1
                if progress_callback:
                    try:
                        await progress_callback(done_count, total, url)
                    except Exception:
                        pass
                return cr

        tasks = [crawl_one(url) for url in urls]
        pages = await asyncio.gather(*tasks, return_exceptions=True)

        for page in pages:
            if isinstance(page, Exception):
                result.failed += 1
                result.errors.append(str(page))
            elif page.success:
                result.succeeded += 1
                result.pages.append(page)
            else:
                result.failed += 1
                result.errors.append(f"{page.url}: {page.error}")

        logger.info(
            "Batch crawl done: %d/%d succeeded for %s",
            result.succeeded, result.total_urls, domain,
        )
        return result

    async def _crawl_single_page(self, url: str) -> CrawlResult:
        """抓取单个页面 (使用 URLParser 三级回退)"""
        try:
            from app.core.rag.parsers.url_parser import URLParser

            parser = URLParser()
            parsed = await parser.parse(url)

            text = parsed.text if parsed.text and not parsed.text.startswith("[Content unavailable") else ""
            if not text or len(text.strip()) < 50:
                return CrawlResult(url=url, success=False, error="Content too short or unavailable")

            return CrawlResult(
                url=url,
                title=parsed.title or urlparse(url).path.rsplit("/", 1)[-1] or "Untitled",
                text=text,
                success=True,
                word_count=len(text.split()),
            )

        except Exception as e:
            logger.debug("Crawl failed for %s: %s", url, e)
            return CrawlResult(url=url, success=False, error=str(e))

    # ── URL 过滤 ─────────────────────────────────────────

    def _filter_urls(
        self,
        urls: list[str],
        domain: str,
        url_filter: Optional[callable],
        max_pages: int,
    ) -> list[str]:
        """过滤 URL 列表"""
        result = []
        seen = set()

        for url in urls:
            if len(result) >= max_pages:
                break

            url = url.strip()
            if not url or url in seen:
                continue
            seen.add(url)

            # 同域检查
            if self.same_domain_only:
                parsed = urlparse(url)
                if parsed.netloc != domain:
                    continue

            # 跳过非页面资源
            skip_extensions = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
                               ".ico", ".css", ".js", ".woff", ".woff2", ".ttf",
                               ".pdf", ".zip", ".tar", ".gz", ".mp4", ".webm")
            if any(url.lower().endswith(ext) for ext in skip_extensions):
                continue

            # 自定义过滤
            if url_filter and not url_filter(url):
                continue

            result.append(url)

        return result
