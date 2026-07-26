"""
API 接口爬取策略

适用场景:
- REST API 数据批量抓取 (GET pagination)
- GraphQL 查询
- JSON API 响应解析
- 分页自动遍历 (Cursor / Offset / Page-based)
- 速率控制 (429 响应自适应降速)

支持分页模式:
- offset/limit: ?offset=0&limit=20
- page/size: ?page=1&size=20
- cursor: ?cursor=xxx (基于响应中的 next_cursor)
- link-header: RFC 5988 Link 头部
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import AsyncIterator, Optional
from urllib.parse import urljoin, urlparse
from urllib.parse import parse_qs, urlencode, urlunparse

import httpx

from ..anti_detect import get_anti_detect
from ..quality import get_cleaner, get_scorer
from ..types import CrawlTask, PageResult, StrategyType
from .base import BaseCrawlerStrategy

logger = logging.getLogger("rag.crawler.api")


class APICrawlerStrategy(BaseCrawlerStrategy):
    """API 接口爬取策略

    支持 REST / GraphQL API，自动分页遍历。
    """

    strategy_type = StrategyType.API

    def __init__(
        self,
        timeout: float = 30.0,
        max_pages: int = 50,
        page_size: int = 100,
    ):
        super().__init__()
        self.timeout = timeout
        self.max_pages = max_pages
        self.page_size = page_size
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                http2=True,
            )
        return self._client

    def can_handle(self, url: str) -> bool:
        """识别 API 端点"""
        parsed = urlparse(url)
        path = parsed.path.lower()

        api_indicators = [
            "/api/", "/graphql", "/v1/", "/v2/", "/v3/",
            "/rest/", "/json", ".json",
            "/wp-json/", "/wp/v2/",
        ]
        for ind in api_indicators:
            if ind in path:
                return True

        # URL 参数中含 api 特征
        query = parsed.query.lower()
        if "format=json" in query or "api_key" in query or "access_token" in query:
            return True

        return False

    async def fetch(self, task: CrawlTask) -> PageResult:
        """执行单次 API 抓取"""
        start = time.time()

        result = PageResult(
            url=task.url, task_id=task.task_id, strategy=StrategyType.API,
            domain=task.domain or urlparse(task.url).netloc,
        )

        try:
            client = await self._get_client()
            anti = get_anti_detect()
            headers = anti.get_api_headers(task.url)
            proxy = anti.get_proxy()

            method = task.api_method or "GET"
            body = task.api_body if method in ("POST", "PUT", "PATCH") else None

            delay = anti.get_delay(result.domain)
            if delay > 0:
                await asyncio.sleep(delay)

            if method == "GET":
                resp = await client.get(task.url, headers=headers, proxy=proxy)
            else:
                resp = await client.request(method, task.url, headers=headers, json=body, proxy=proxy)

            anti.mark_request(result.domain)
            result.http_status = resp.status_code

            if resp.status_code >= 400:
                result.error = f"HTTP {resp.status_code}"
                if resp.status_code in (429, 503):
                    # 速率限制 → 等待更长时间
                    await asyncio.sleep(5.0)
                return result

            # 解析 JSON
            try:
                data = resp.json()
            except json.JSONDecodeError:
                data = {"_raw": resp.text}

            result.extra["api_response"] = data

            # JSON → 文本转换
            result.text = self._json_to_text(data)
            result.text_length = len(result.text.split())
            result.title = self._extract_title(data, task.url)

            # 发现下一页 (分页)
            next_url = self._discover_next_page(resp, task.url, data)
            if next_url:
                result.discovered_urls = [next_url]

            # 评分
            scorer = get_scorer()
            result = scorer.score(result)

            if result.quality != "rejected":
                result.success = True

        except httpx.TimeoutException:
            result.error = "API 请求超时"
        except Exception as e:
            result.error = str(e)

        result.fetch_time_ms = (time.time() - start) * 1000
        self._stats["total"] += 1
        self._stats["success"] += 1 if result.success else 0
        self._stats["failed"] += 0 if result.success else 1
        return result

    async def fetch_all_pages(self, task: CrawlTask) -> AsyncIterator[PageResult]:
        """自动遍历所有分页 (支持 offset/page/cursor)"""
        current_url = task.url
        pages_fetched = 0

        while current_url and pages_fetched < self.max_pages:
            task.url = current_url
            result = await self.fetch(task)

            if not result.success:
                yield result
                break

            yield result
            pages_fetched += 1

            # 检查是否有下一页
            next_url = result.discovered_urls[0] if result.discovered_urls else None
            if not next_url or next_url == current_url:
                break
            current_url = next_url

            # 分页速率控制
            await asyncio.sleep(0.5)

    # ── 分页发现 ────────────────────────────────────────

    def _discover_next_page(
        self, response: httpx.Response, url: str, data: dict
    ) -> Optional[str]:
        """从响应中发现下一页 URL

        优先级: Link Header > JSON metadata > URL 参数推算
        """
        # 1. RFC 5988 Link Header
        link_header = response.headers.get("link", "")
        if 'rel="next"' in link_header:
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    link = part.split(";")[0].strip(" <>")
                    return urljoin(url, link)

        # 2. JSON 响应中的分页字段
        if isinstance(data, dict):
            # Cursor-based
            for key in ("next_cursor", "next", "next_page", "next_page_token"):
                cursor = data.get(key)
                if cursor and isinstance(cursor, str):
                    parsed = urlparse(url)
                    query = parse_qs(parsed.query)
                    query["cursor"] = [cursor]
                    new_query = urlencode(query, doseq=True)
                    return urlunparse(parsed._replace(query=new_query))

            # Meta 分页
            meta = data.get("meta") or data.get("pagination") or data.get("page_info") or {}
            if isinstance(meta, dict):
                for key in ("next", "next_url", "next_page"):
                    if meta.get(key):
                        return urljoin(url, str(meta[key]))

            # Total/Meta 推算
            has_more = data.get("has_more") or data.get("hasNextPage") or data.get("has_next")
            if has_more:
                return self._build_next_page_url(url, data)

        # 3. 列表类型不自动翻页 (无法推断)
        return None

    def _build_next_page_url(self, url: str, data: dict) -> Optional[str]:
        """基于 URL 参数自动推算下一页"""
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        # page/size 模式
        if "page" in query:
            page = int(query["page"][0]) + 1
            query["page"] = [str(page)]
            return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

        # offset/limit 模式
        if "offset" in query:
            limit = int(query.get("limit", query.get("size", ["20"]))[0])
            offset = int(query["offset"][0]) + limit
            query["offset"] = [str(offset)]
            return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))

        return None

    # ── 文本提取 ────────────────────────────────────────

    def _json_to_text(self, data, depth: int = 0, max_depth: int = 3) -> str:
        """JSON 数据 → 文本 (递归提取字符串字段)"""
        if depth > max_depth:
            return ""

        if isinstance(data, str):
            return data
        elif isinstance(data, (int, float, bool)):
            return str(data)
        elif isinstance(data, list):
            return "\n".join(
                self._json_to_text(item, depth, max_depth)
                for item in data[:20]  # 限制数量
            )
        elif isinstance(data, dict):
            parts = []
            # 常见的文本字段名
            text_keys = {
                "title", "name", "description", "summary", "content", "text",
                "body", "excerpt", "bio", "message", "comment", "answer",
                "question", "headline", "abstract", "snippet",
            }
            for key, value in data.items():
                if key in text_keys and isinstance(value, str):
                    parts.append(value)
                elif isinstance(value, str) and len(value) > 20:
                    parts.append(value)
            return "\n".join(parts)
        return ""

    def _extract_title(self, data, url: str) -> str:
        """从 API 响应中提取标题"""
        if isinstance(data, dict):
            for key in ("title", "name", "headline", "subject"):
                val = data.get(key)
                if isinstance(val, str) and val:
                    return val
        return url.rsplit("/", 1)[-1]

    async def close(self):
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None
