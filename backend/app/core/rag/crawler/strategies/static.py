"""
静态页面爬取策略

技术栈: httpx + readability-lxml + BeautifulSoup
- readability 提取正文 (参考 Mozilla Readability 算法)
- 元数据提取 (title, author, date, OG, Schema.org, JSON-LD)
- 链接发现 (同域链接收集，供深度爬取)
- 三级回退: readability → bs4 正文 → 纯文本
"""

from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx

from ..anti_detect import get_anti_detect
from ..quality import get_cleaner, get_scorer
from ..types import CrawlTask, PageResult, StrategyType
from .base import BaseCrawlerStrategy

logger = logging.getLogger("rag.crawler.static")


class StaticCrawlerStrategy(BaseCrawlerStrategy):
    """静态 HTML 解析策略

    适用场景: 博客、文档站、新闻站、Wiki 等传统 SSR 站点
    不适用: SPA (React/Vue/Angular) 需 JS 渲染的页面

    技术路径:
        httpx GET → HTML → readability 提取 → 元数据解析 → 链接发现
    """

    strategy_type = StrategyType.STATIC

    def __init__(
        self,
        timeout: float = 30.0,
        max_redirects: int = 5,
        follow_redirects: bool = True,
    ):
        super().__init__()
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.follow_redirects = follow_redirects
        self._client: Optional[httpx.AsyncClient] = None
        self._cleaner = None
        self._scorer = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=self.follow_redirects,
                max_redirects=self.max_redirects,
                http2=True,
            )
        return self._client

    @property
    def _clean(self):
        if get_cleaner is None:
            return None
        return get_cleaner()

    def can_handle(self, url: str) -> bool:
        """静态策略几乎能处理所有 URL (作为兜底)"""
        parsed = urlparse(url)
        # 排除明显需要动态渲染的 SPA 特征
        spa_indicators = ["/app.", "/_next/", "/__nuxt", "webpack", "chunk-"]
        path = parsed.path.lower()
        if any(ind in path or ind in url for ind in spa_indicators):
            return False  # 让 DYNAMIC 策略处理
        return True

    async def fetch(self, task: CrawlTask) -> PageResult:
        """执行静态抓取"""
        import time as time_mod
        start = time_mod.time()

        result = PageResult(
            url=task.url,
            task_id=task.task_id,
            strategy=StrategyType.STATIC,
            domain=task.domain or urlparse(task.url).netloc,
        )

        try:
            client = await self._get_client()
            anti = get_anti_detect()
            domain = result.domain

            headers = anti.get_headers(task.url, domain=domain)
            proxy = anti.get_proxy()

            # 请求延迟
            delay = anti.get_delay(domain)
            if delay > 0:
                import asyncio
                await asyncio.sleep(delay)

            # 发起请求
            response = await client.get(
                task.url,
                headers=headers,
                proxy=proxy,
            )
            anti.mark_request(domain)

            result.http_status = response.status_code
            result.content_type = response.headers.get("content-type", "")
            result.html = response.text

            if response.status_code >= 400:
                result.error = f"HTTP {response.status_code}"
                return result

            # 更新 Cookie
            if response.cookies:
                anti.set_cookies(domain, dict(response.cookies))

            # ── 内容提取 ─────────────────────────────────
            content = await self._extract_content(result.html, task.url, result)

            result.title = content.get("title", "")
            result.text = content.get("text", "")
            result.text_length = len(result.text.split())
            result.author = content.get("author", "")
            result.published_date = content.get("date", "")
            result.language = content.get("language", "")
            result.schema_org = content.get("schema_org", {})
            result.open_graph = content.get("open_graph", {})
            result.json_ld = content.get("json_ld", [])
            result.discovered_urls = content.get("links", [])

            # ── 质量评分 ─────────────────────────────────
            scorer = get_scorer()
            result = scorer.score(result)

            if result.quality != "rejected":
                result.success = True

            self._stats["total"] += 1
            self._stats["success"] += 1 if result.success else 0
            self._stats["failed"] += 0 if result.success else 1

        except httpx.TimeoutException:
            result.error = "请求超时"
        except httpx.ConnectError as e:
            result.error = f"连接失败: {e}"
        except Exception as e:
            result.error = str(e)
            logger.warning("静态抓取异常 %s: %s", task.url, e)

        result.fetch_time_ms = (time_mod.time() - start) * 1000
        return result

    async def _extract_content(
        self, html: str, url: str, result: PageResult
    ) -> dict:
        """提取内容 (readability 优先 → bs4 回退)"""
        import asyncio

        info: dict = {
            "title": "", "text": "", "author": "", "date": "",
            "language": "", "schema_org": {}, "open_graph": {}, "json_ld": [],
            "links": [],
        }

        cleaner = get_cleaner()

        # 1. readability 提取正文
        try:
            loop = asyncio.get_event_loop()
            title, content = await loop.run_in_executor(
                None, cleaner.extract_readability, html, url
            )
            if title:
                info["title"] = title
            if content and len(content.split()) > 50:
                info["text"] = content
                info["language"] = self._detect_lang(content)
        except Exception:
            pass

        # 2. 回退: bs4 全页面清理
        if len((info.get("text") or "").split()) < 30:
            try:
                loop = asyncio.get_event_loop()
                info["text"] = await loop.run_in_executor(None, cleaner.clean, html)
            except Exception:
                # 最终回退: 正则
                info["text"] = cleaner._regex_clean(html)

        # 3. 元数据提取
        await self._extract_metadata(html, url, info)

        # 4. 链接发现
        info["links"] = await self._discover_links(html, url)

        return info

    async def _extract_metadata(self, html: str, url: str, info: dict):
        """提取结构化元数据"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml" if self._has_lxml() else "html.parser")

            # <title> 标签
            if not info.get("title"):
                title_tag = soup.find("title")
                if title_tag:
                    info["title"] = title_tag.get_text(strip=True)

            # Meta 标签
            meta_tags = {}
            for meta in soup.find_all("meta"):
                name = meta.get("name") or meta.get("property") or ""
                content = meta.get("content") or ""
                if name and content:
                    meta_tags[name.lower()] = content

            # Open Graph
            info["open_graph"] = {
                k.replace("og:", ""): v
                for k, v in meta_tags.items()
                if k.startswith("og:")
            }
            if not info.get("title"):
                info["title"] = meta_tags.get("og:title", "")
            if meta_tags.get("og:description"):
                info.setdefault("description", meta_tags["og:description"])

            # Author
            if not info.get("author"):
                info["author"] = meta_tags.get("author") or meta_tags.get("article:author") or ""

            # Published Date
            if not info.get("date"):
                info["date"] = (
                    meta_tags.get("article:published_time")
                    or meta_tags.get("date")
                    or ""
                )

            # Schema.org JSON-LD
            json_ld_items = []
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    import json
                    data = json.loads(script.string or "{}")
                    if isinstance(data, list):
                        json_ld_items.extend(data)
                    else:
                        json_ld_items.append(data)
                except Exception:
                    pass
            info["json_ld"] = json_ld_items

            # 从 JSON-LD 提取额外信息
            for ld in json_ld_items:
                if isinstance(ld, dict):
                    if not info.get("title") and ld.get("headline"):
                        info["title"] = ld["headline"]
                    if not info.get("author") and ld.get("author"):
                        if isinstance(ld["author"], dict):
                            info["author"] = ld["author"].get("name", "")
                        elif isinstance(ld["author"], str):
                            info["author"] = ld["author"]
                    if not info.get("date") and ld.get("datePublished"):
                        info["date"] = ld["datePublished"]

        except ImportError:
            pass
        except Exception as e:
            logger.debug("元数据提取异常: %s", e)

    async def _discover_links(self, html: str, base_url: str) -> list[str]:
        """发现同域名链接"""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml" if self._has_lxml() else "html.parser")
            base_domain = urlparse(base_url).netloc

            links = set()
            for a in soup.find_all("a", href=True):
                href = a["href"]
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                # 只保留同域名 + http/https
                if parsed.netloc == base_domain and parsed.scheme in ("http", "https"):
                    links.add(full_url)

            return list(links)
        except Exception:
            return []

    # ── 工具方法 ───────────────────────────────────────

    @staticmethod
    def _detect_lang(text: str) -> str:
        """快速语言检测"""
        cjk = sum(1 for c in text[:500] if '\u4e00' <= c <= '\u9fff')
        latin = sum(1 for c in text[:500] if c.isascii() and c.isalpha())
        return "zh" if cjk > latin else "en" if latin > 0 else "unknown"

    @staticmethod
    def _has_lxml() -> bool:
        try:
            import lxml  # noqa: F401
            return True
        except ImportError:
            return False

    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
