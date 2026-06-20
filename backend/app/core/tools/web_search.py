"""
Web Search Tool — 借鉴 Open WebUI Web Search 功能

作为 Agent 工具注册，供 LLM Function Calling 使用。
支持:
- Tavily Search API（推荐，专为 AI Agent 设计）
- Brave Search API
- Firecrawl（网页抓取）
"""

from __future__ import annotations

import logging
from typing import Any

from app.core.tools.builtin_tool import BuiltinTool, ToolParam, ToolExecResult
from app.core.config import settings

logger = logging.getLogger("tools.web_search")


class WebSearchTool(BuiltinTool):
    """Web 搜索工具 — 借鉴 Open WebUI 的实时搜索 + 引用来源

    让 Agent 能够搜索互联网最新信息并返回结构化结果。
    """

    name: str = "web_search"
    description: str = (
        "搜索互联网获取最新信息。返回标题、URL、摘要。"
        "适用于需要实时信息的查询。"
    )
    category: str = "web"
    is_async: bool = True

    parameters: list[ToolParam] = [
        ToolParam(name="query", type="string", description="搜索关键词", required=True),
        ToolParam(name="max_results", type="integer", description="最大结果数，默认5", required=False),
        ToolParam(name="search_depth", type="string", description="搜索深度: basic / advanced", required=False),
    ]

    def _get_tavily_client(self):
        """懒加载 Tavily 客户端"""
        try:
            from tavily import TavilyClient
            api_key = settings.TAVILY_API_KEY
            if not api_key:
                return None
            # 支持逗号分隔的多个 key
            keys = [k.strip() for k in api_key.split(",") if k.strip()]
            return TavilyClient(api_key=keys[0])
        except ImportError:
            logger.warning("tavily-python not installed, fallback to HTTP API")
            return None
        except Exception as e:
            logger.error(f"Failed to init Tavily client: {e}")
            return None

    async def _tavily_search(self, query: str, max_results: int = 5, depth: str = "basic") -> list[dict]:
        """通过 Tavily API 搜索"""
        import httpx

        api_key = settings.TAVILY_API_KEY
        if not api_key:
            return []

        keys = [k.strip() for k in api_key.split(",") if k.strip()]
        if not keys:
            return []

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": keys[0],
                    "query": query,
                    "max_results": max_results,
                    "search_depth": depth,
                    "include_answer": True,
                    "include_raw_content": False,
                },
            )
            if resp.status_code != 200:
                logger.error(f"Tavily search error: {resp.status_code} {resp.text}")
                return []

            data = resp.json()
            results: list[dict] = []

            # Answer
            if data.get("answer"):
                results.append({
                    "type": "answer",
                    "content": data["answer"],
                })

            # Search results
            for r in data.get("results", []):
                results.append({
                    "type": "result",
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("content", ""),
                    "score": r.get("score", 0),
                })

            return results

    async def _brave_search(self, query: str, max_results: int = 5) -> list[dict]:
        """通过 Brave Search API 搜索"""
        import httpx

        api_key = settings.BRAVE_API_KEY
        if not api_key:
            return []

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": max_results},
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": api_key,
                },
            )
            if resp.status_code != 200:
                logger.error(f"Brave search error: {resp.status_code}")
                return []

            data = resp.json()
            results: list[dict] = []
            for r in data.get("web", {}).get("results", []):
                results.append({
                    "type": "result",
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "content": r.get("description", ""),
                })
            return results

    async def execute(self, **kwargs) -> ToolExecResult:
        query: str = kwargs.get("query", "")
        max_results: int = int(kwargs.get("max_results", 5))
        depth: str = kwargs.get("search_depth", "basic")

        if not query:
            return ToolExecResult(success=False, error="query is required")

        results: list[dict] = []

        # 优先级: Tavily → Brave
        if settings.TAVILY_API_KEY:
            results = await self._tavily_search(query, max_results, depth)
        
        if not results and settings.BRAVE_API_KEY:
            results = await self._brave_search(query, max_results)

        if not results:
            return ToolExecResult(
                success=False,
                error="No search API keys configured. Set TAVILY_API_KEY or BRAVE_API_KEY.",
            )

        # 格式化输出
        output_parts: list[str] = []
        for r in results:
            if r["type"] == "answer":
                output_parts.append(f"📝 Answer: {r['content']}")
            else:
                output_parts.append(
                    f"🔗 [{r.get('title', 'Untitled')}]({r.get('url', '')})\n"
                    f"   {r.get('content', '')}"
                )

        return ToolExecResult(
            success=True,
            output="\n\n".join(output_parts),
            metadata={
                "query": query,
                "result_count": len(results),
                "source": "tavily" if settings.TAVILY_API_KEY else "brave",
            },
        )


class WebFetchTool(BuiltinTool):
    """网页抓取工具 — 借鉴 Open WebUI 的 Firecrawl 集成

    抓取指定 URL 的内容并转换为 Markdown。
    """

    name: str = "web_fetch"
    description: str = "抓取网页内容并返回 Markdown 格式文本。用于阅读和提取网页信息。"
    category: str = "web"
    is_async: bool = True

    parameters: list[ToolParam] = [
        ToolParam(name="url", type="string", description="目标网页 URL", required=True),
        ToolParam(name="selector", type="string", description="CSS 选择器（可选），只提取匹配元素", required=False),
    ]

    async def execute(self, **kwargs) -> ToolExecResult:
        url: str = kwargs.get("url", "")
        selector: str | None = kwargs.get("selector")

        if not url:
            return ToolExecResult(success=False, error="url is required")

        # 尝试 Firecrawl
        if settings.FIRECRAWL_API_KEY:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        "https://api.firecrawl.dev/v1/scrape",
                        json={"url": url, "formats": ["markdown"]},
                        headers={"Authorization": f"Bearer {settings.FIRECRAWL_API_KEY}"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        content = data.get("data", {}).get("markdown", "")
                        if selector:
                            # 简单 CSS 选择器过滤
                            import re
                            pattern = re.compile(re.escape(selector), re.IGNORECASE)
                            lines = [l for l in content.split("\n") if pattern.search(l)]
                            content = "\n".join(lines)
                        return ToolExecResult(
                            success=True,
                            output=content[:10000],  # 限制输出长度
                            metadata={"url": url, "source": "firecrawl", "length": len(content)},
                        )
            except Exception as e:
                logger.warning(f"Firecrawl failed: {e}")

        # Fallback: 直接 HTTP GET + 简单 HTML 转文本
        try:
            import httpx
            import re
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "AI-Fullstack-Platform/1.0"})
                resp.raise_for_status()
                html = resp.text

                # 简单 HTML 标签清理
                text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text).strip()

                return ToolExecResult(
                    success=True,
                    output=text[:10000],
                    metadata={"url": url, "source": "direct", "length": len(text)},
                )
        except Exception as e:
            return ToolExecResult(success=False, error=f"Failed to fetch {url}: {str(e)}")


# ── 注册工具 ───────────────────────────────────────────
def register_web_tools():
    """注册 Web 搜索工具到工具注册中心"""
    from app.core.tools.registry import get_tool_registry

    registry = get_tool_registry()
    registry.register(WebSearchTool())
    registry.register(WebFetchTool())
    logger.info("Web search tools registered: web_search, web_fetch")
