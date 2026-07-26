"""
动态渲染爬取策略

使用 Playwright 无头浏览器渲染 JS 页面:
- SPA (React/Vue/Angular) 页面抓取
- 需要 JavaScript 才能加载内容的页面
- 反爬严重的站点 (浏览器指纹更像真人)
- 可选: 滚动加载更多 (懒加载内容)
- 可选: 鼠标移动 + 点击模拟

依赖: playwright (可选，未安装时自动降级为 static)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional
from urllib.parse import urlparse

from ..anti_detect import get_anti_detect
from ..quality import get_cleaner, get_scorer
from ..types import CrawlTask, PageResult, StrategyType
from .base import BaseCrawlerStrategy

logger = logging.getLogger("rag.crawler.dynamic")


class DynamicCrawlerStrategy(BaseCrawlerStrategy):
    """动态渲染策略 (Headless Browser)

    适用场景:
    - 单页应用 (SPA): React, Vue, Angular
    - 需要 JS 渲染的页面 (Next.js, Nuxt)
    - 反爬严格的站点
    - 懒加载/无限滚动内容

    特性:
    - Playwright Chromium/Firefox 无头模式
    - 自动等待网络空闲 (networkidle)
    - 页面滚动加载更多内容
    - 截图采集 (可选)
    - 浏览器实例池复用
    - 不安装时自动降级为 static
    """

    strategy_type = StrategyType.DYNAMIC

    def __init__(
        self,
        headless: bool = True,
        viewport_width: int = 1920,
        viewport_height: int = 1080,
        wait_until: str = "networkidle",
        page_timeout: float = 30.0,
        scroll_to_load: bool = True,
        max_scrolls: int = 5,
        screenshot: bool = False,
        browser_type: str = "chromium",  # chromium | firefox | webkit
    ):
        super().__init__()
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.wait_until = wait_until
        self.page_timeout = page_timeout * 1000  # ms
        self.scroll_to_load = scroll_to_load
        self.max_scrolls = max_scrolls
        self.screenshot = screenshot
        self.browser_type = browser_type

        self._browser = None
        self._playwright = None
        self._available = None  # None=未检测, True/False

    async def _ensure_browser(self):
        """延迟初始化浏览器"""
        if self._available is False:
            return False

        if self._browser is None:
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()

                browser_launcher = getattr(self._playwright, self.browser_type)
                self._browser = await browser_launcher.launch(
                    headless=self.headless,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                    ],
                )
                self._available = True
                logger.info("Playwright 浏览器启动成功 (%s, headless=%s)", self.browser_type, self.headless)
            except ImportError:
                logger.warning(
                    "playwright 未安装，动态渲染不可用。"
                    "安装: pip install playwright && playwright install chromium"
                )
                self._available = False
            except Exception as e:
                logger.warning("Playwright 启动失败: %s", e)
                self._available = False

        return self._available

    def can_handle(self, url: str) -> bool:
        """识别需要动态渲染的页面"""
        parsed = urlparse(url)
        path = parsed.path.lower()

        # SPA 框架特征
        spa_patterns = [
            "/app.", "/_next/", "/__nuxt", "/_nuxt/",
            "webpack", "chunk-", "bundle.",
            "/static/js/", "/assets/",
        ]
        # JS 渲染主力站点
        js_sites = [
            "medium.com", "twitter.com", "x.com",
            "zhihu.com", "juejin.cn", "jianshu.com",
            "linkedin.com", "reddit.com",
        ]

        for pattern in spa_patterns:
            if pattern in path or pattern in url:
                return True
        for site in js_sites:
            if site in parsed.netloc:
                return True
        return False

    async def fetch(self, task: CrawlTask) -> PageResult:
        """执行动态渲染抓取"""
        start = time.time()

        result = PageResult(
            url=task.url, task_id=task.task_id, strategy=StrategyType.DYNAMIC,
            domain=task.domain or urlparse(task.url).netloc,
        )

        available = await self._ensure_browser()
        if not available:
            # 自动降级为静态抓取
            logger.info("Playwright 不可用，降级为静态抓取: %s", task.url)
            from .static import StaticCrawlerStrategy
            static = StaticCrawlerStrategy()
            return await static.fetch(task)

        try:
            anti = get_anti_detect()
            domain = result.domain

            # 反爬延迟
            delay = anti.get_delay(domain)
            if delay > 0:
                await asyncio.sleep(delay)

            # 视口随机化 (反指纹)
            vp_w = self.viewport_width + (hash(task.url) % 200 - 100) if anti.config.viewport_randomize else self.viewport_width
            vp_h = self.viewport_height + (hash(task.url) % 200 - 100) if anti.config.viewport_randomize else self.viewport_height

            page = await self._browser.new_page(
                viewport={"width": vp_w, "height": vp_h},
                user_agent=anti.get_user_agent(domain),
            )

            # 注入反检测脚本
            await page.add_init_script("""
                // 隐藏 webdriver 属性
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                // 模拟 chrome 对象
                window.chrome = {runtime: {}};
                // 伪造 plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });
                // 伪造 languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en'],
                });
            """)

            # 导航到页面
            response = await page.goto(
                task.url,
                wait_until=self.wait_until,
                timeout=self.page_timeout,
            )
            anti.mark_request(domain)

            result.http_status = response.status if response else 0

            if response and response.status >= 400:
                result.error = f"HTTP {response.status}"
                await page.close()
                return result

            # 行为模拟: 鼠标移动
            if anti.config.simulate_human:
                await self._simulate_human_behavior(page)

            # 滚动加载更多
            if self.scroll_to_load:
                await self._scroll_page(page)

            # 提取内容
            html = await page.content()
            title = await page.title()

            result.html = html
            result.title = title

            # 提取正文
            cleaner = get_cleaner()
            try:
                title_extracted, content = cleaner.extract_readability(html, task.url)
                result.text = content if content and len(content.split()) > 50 else cleaner.clean(html)
                if not result.title:
                    result.title = title_extracted
            except Exception:
                result.text = cleaner._regex_clean(html)

            result.text_length = len(result.text.split())

            # 截图 (可选)
            if self.screenshot:
                try:
                    result.extra["screenshot_b64"] = await page.screenshot(
                        type="jpeg", quality=80, full_page=False
                    )
                except Exception:
                    pass

            # 发现链接
            discovered = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(h => h.startsWith('http'))
            """)
            result.discovered_urls = list(set(discovered))[:100]

            await page.close()

            # 质量评分
            scorer = get_scorer()
            result = scorer.score(result)

            if result.quality != "rejected":
                result.success = True

        except Exception as e:
            result.error = str(e)
            logger.warning("动态渲染异常 %s: %s", task.url, e)

        result.fetch_time_ms = (time.time() - start) * 1000
        self._stats["total"] += 1
        self._stats["success"] += 1 if result.success else 0
        self._stats["failed"] += 0 if result.success else 1
        return result

    # ── 行为模拟 ────────────────────────────────────────

    async def _simulate_human_behavior(self, page):
        """模拟人类浏览行为: 鼠标移动 + 随机滚动"""
        try:
            # 鼠标移动到页面中间
            w = await page.evaluate("window.innerWidth")
            h = await page.evaluate("window.innerHeight")
            await page.mouse.move(w * 0.3, h * 0.05)
            await asyncio.sleep(0.3)
            await page.mouse.move(w * 0.7, h * 0.5)
            await asyncio.sleep(0.2)
            await page.mouse.move(w * 0.5, h * 0.3)
        except Exception:
            pass

    async def _scroll_page(self, page):
        """滚动页面加载懒加载内容"""
        for _ in range(self.max_scrolls):
            prev_height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1.5)  # 等待加载
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == prev_height:
                break  # 无更多内容

    # ── 资源管理 ────────────────────────────────────────

    async def close(self):
        """关闭浏览器"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
