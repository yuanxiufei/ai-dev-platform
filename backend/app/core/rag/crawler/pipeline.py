"""
端到端爬取流水线

将策略、反检测、去重、质量管控、调度器串联为一个完整的爬取流程:

Pipeline 阶段:
  1. URL 预处理 → 规范/过滤/去重
  2. robots.txt 合法性检查
  3. 策略选择 (API > Feed > Sitemap > Dynamic > Static)
  4. 反检测 + 请求
  5. 内容提取 + 质量评分
  6. SimHash 去重
  7. 结果汇总 → PageResult[]

使用示例:
    pipeline = CrawlPipeline(registry=registry)
    results = await pipeline.crawl(["https://docs.example.com", ...])
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlparse, urljoin

from .types import (
    AntiDetectConfig,
    CrawlProgress,
    CrawlTask,
    PageResult,
    QualityConfig,
    SchedulerConfig,
    StrategyType,
    TaskPriority,
    TaskStatus,
)
from .strategies.base import StrategyRegistry
from .scheduler import CrawlScheduler

# OCR 插件 (可选依赖, 导入失败不影响主流程)
try:
    from .ocr_plugin import OcrConfig, get_ocr_engine
    _OCR_AVAILABLE = True
except ImportError:
    _OCR_AVAILABLE = False
    OcrConfig = None  # type: ignore

logger = logging.getLogger("rag.crawler.pipeline")


# ══════════════════════════════════════════════════════════════
# 爬取配置
# ══════════════════════════════════════════════════════════════

@dataclass
class CrawlConfig:
    """端到端爬取配置"""
    # 并发控制
    max_concurrent: int = 5                # 全局最大并发
    domain_max_concurrent: int = 3          # 单域名最大并发
    delay_seconds: float = 1.0              # 请求间隔

    # 范围限制
    max_pages: int = 500                    # 最大抓取页数
    max_depth: int = 3                      # 同站链接发现深度
    same_domain_only: bool = True           # 是否仅限同域名
    allowed_domains: list[str] = field(default_factory=list)
    disallowed_domains: list[str] = field(default_factory=list)

    # 质量阈值
    min_quality_score: float = 30.0        # 最低质量分 (低于则丢弃)
    min_text_length: int = 200             # 最低文本长度

    # 重试
    max_retries: int = 3
    retry_delay_base: float = 1.0

    # 行为
    respect_robots: bool = True
    enable_sitemap_discovery: bool = True   # 自动发现 sitemap.xml
    enable_feed_discovery: bool = True      # 自动发现 RSS/Atom feed
    follow_links: bool = False              # 是否跟随页面链接
    deduplicate: bool = True                # 是否去重

    # OCR (SmolDocling 实时图片文字提取)
    enable_ocr: bool = False                # 是否启用 OCR 插件
    ocr_config: Optional["OcrConfig"] = None  # OCR 详细配置 (None=默认)

    # 反检测
    anti_detect: AntiDetectConfig = field(default_factory=AntiDetectConfig)

    # 质量
    quality: QualityConfig = field(default_factory=QualityConfig)

    # 暂停恢复
    checkpoint_file: str = ""               # 断点续爬文件路径
    progress_callback: Optional[Callable[[CrawlProgress], None]] = None


# ══════════════════════════════════════════════════════════════
# 爬取流水线
# ══════════════════════════════════════════════════════════════

class CrawlPipeline:
    """端到端爬取流水线

    职责:
    - 统一入口: 接收 URL 列表 → 生成结果
    - 策略路由: 自动选择最优策略 + 回退链
    - 质量过滤: 评分 → 去重 → 清洗
    - 并发调度: 域名限速 + 优先级 + 自适应
    - 进度: 实时回调 + 断点续爬

    """

    def __init__(
        self,
        registry: Optional[StrategyRegistry] = None,
        config: Optional[CrawlConfig] = None,
    ):
        self.config = config or CrawlConfig()

        # 策略注册表 (共享实例)
        if registry is None:
            from .strategies import create_registry
            registry = create_registry(
                anti_detect_cfg=self.config.anti_detect,
                quality_cfg=self.config.quality,
            )
        self._registry = registry

        # 调度器
        self._scheduler: Optional[CrawlScheduler] = None

        # 统计
        self._start_time = 0.0
        self._end_time = 0.0
        self._total_urls = 0

    # ── 单 URL 爬取 ───────────────────────────────────

    async def crawl_one(self, url: str, **kwargs) -> PageResult:
        """抓取单个 URL (快速模式)"""
        from urllib.parse import urlparse

        result = await self._registry.fetch(
            url=url,
            timeout=self.config.anti_detect.timeout_seconds,
            skip_robots=not self.config.respect_robots,
            **kwargs,
        )

        # 质量检查
        if result.success and self.config.min_text_length > 0:
            if len(result.text or "") < self.config.min_text_length:
                result.success = False
                result.error = f"Text too short: {len(result.text or '')} < {self.config.min_text_length}"

        if result.success and result.quality_score is not None:
            if result.quality_score < self.config.min_quality_score:
                result.success = False
                result.error = f"Quality {result.quality_score:.0f} < {self.config.min_quality_score}"

        return result

    # ── 批量爬取 ─────────────────────────────────────

    async def crawl(
        self,
        urls: list[str],
        on_progress: Optional[Callable[[CrawlProgress], None]] = None,
        **kwargs,
    ) -> list[PageResult]:
        """批量抓取 URL 列表

        Args:
            urls: URL 列表
            on_progress: 实时进度回调 (WebSocket 推送)
            **kwargs: 覆盖 config 参数

        Returns:
            PageResult 列表
        """
        if not urls:
            return []

        self._start_time = time.time()
        self._total_urls = min(len(urls), self.config.max_pages)

        # 预处理
        tasks = self._prepare_tasks(urls[:self.config.max_pages])

        # 构建调度器配置
        sched_cfg = SchedulerConfig(
            global_max_concurrent=kwargs.get("max_concurrent", self.config.max_concurrent),
            domain_max_concurrent=kwargs.get("domain_max_concurrent", self.config.domain_max_concurrent),
            delay_seconds=kwargs.get("delay_seconds", self.config.delay_seconds),
        )

        # 创建调度器
        self._scheduler = CrawlScheduler(
            registry=self._registry,
            config=sched_cfg,
        )

        # 批量提交
        self._scheduler.submit_batch(tasks)
        logger.info(
            "Pipeline: submitting %d tasks (max_concurrent=%d)",
            len(tasks), sched_cfg.global_max_concurrent,
        )

        # 执行
        callback = on_progress or self.config.progress_callback
        progress = await self._scheduler.run(on_progress=callback)

        self._end_time = time.time()
        elapsed = self._end_time - self._start_time

        # OCR 后处理 (SmolDocling — 轻量实时图片文字提取)
        if self.config.enable_ocr and _OCR_AVAILABLE:
            await self._run_ocr_postprocess(progress.results)

        # 汇总
        ok_count = sum(1 for r in progress.results if r.success)
        logger.info(
            "Pipeline done: %d/%d ok in %.1fs (%.1f pages/s)",
            ok_count, len(progress.results), elapsed,
            ok_count / max(elapsed, 0.1),
        )

        return progress.results

    async def _run_ocr_postprocess(self, results: list[PageResult]) -> None:
        """对爬取结果执行 OCR 后处理 (SmolDocling)"""
        if not _OCR_AVAILABLE:
            return

        ocr_engine = get_ocr_engine(self.config.ocr_config)
        if not self.config.ocr_config:
            # 使用默认配置, 但开启 OCR
            from .ocr_plugin import OcrConfig as _OC
            ocr_engine.config = _OC(enabled=True)

        eligible = [
            r for r in results
            if r.success and r.html and not r.ocr_text
        ]
        if not eligible:
            logger.debug("OCR: no eligible pages (need success + html + not-yet-ocr'd)")
            return

        logger.info("OCR postprocess: %d pages eligible for SmolDocling", len(eligible))

        # 并发 OCR (每页 15s 总超时)
        async def _ocr_page(r: PageResult):
            ocr_result = await ocr_engine.extract_from_html(r.html, r.url)
            r.ocr_text = ocr_result.merged_text
            r.ocr_images = ocr_result.image_urls
            r.ocr_elapsed_ms = ocr_result.elapsed_ms

        tasks = [_ocr_page(r) for r in eligible]
        await asyncio.gather(*tasks, return_exceptions=True)

        ocr_ok = sum(1 for r in eligible if r.ocr_text)
        logger.info("OCR done: %d/%d pages extracted image text", ocr_ok, len(eligible))

    # ── Sitemap 爬取 ──────────────────────────────────

    async def crawl_sitemap(
        self,
        sitemap_url: str,
        on_progress: Optional[Callable[[CrawlProgress], None]] = None,
        **kwargs,
    ) -> list[PageResult]:
        """从 sitemap 批量抓取

        Args:
            sitemap_url: sitemap.xml 地址
            on_progress: 进度回调
        """
        from .strategies.sitemap_crawler import SitemapCrawlerStrategy

        sitemap_strategy = SitemapCrawlerStrategy(
            anti_detect_cfg=self.config.anti_detect,
            quality_cfg=self.config.quality,
        )

        # 解析 sitemap 获取 URL 列表
        urls = []
        async for url in sitemap_strategy.parse_sitemap(sitemap_url):
            urls.append(url)
            if len(urls) >= self.config.max_pages:
                break

        if not urls:
            logger.warning("Sitemap returned no URLs: %s", sitemap_url)
            return []

        logger.info("Sitemap: discovered %d URLs from %s", len(urls), sitemap_url)
        return await self.crawl(urls, on_progress=on_progress, **kwargs)

    # ── Feed 爬取 ─────────────────────────────────────

    async def crawl_feed(
        self,
        feed_url: str,
        on_progress: Optional[Callable[[CrawlProgress], None]] = None,
        **kwargs,
    ) -> list[PageResult]:
        """从 RSS/Atom Feed 批量抓取"""
        from .strategies.feed_crawler import FeedCrawlerStrategy

        feed_strategy = FeedCrawlerStrategy(
            anti_detect_cfg=self.config.anti_detect,
            quality_cfg=self.config.quality,
        )

        # 解析 Feed 获取条目 URL
        urls = []
        async for url in feed_strategy.parse_feed_urls(feed_url):
            urls.append(url)
            if len(urls) >= self.config.max_pages:
                break

        if not urls:
            logger.warning("Feed returned no URLs: %s", feed_url)
            return []

        logger.info("Feed: discovered %d entries from %s", len(urls), feed_url)
        return await self.crawl(urls, on_progress=on_progress, **kwargs)

    # ── 站点全爬 ──────────────────────────────────────

    async def crawl_site(
        self,
        start_url: str,
        on_progress: Optional[Callable[[CrawlProgress], None]] = None,
        **kwargs,
    ) -> list[PageResult]:
        """完整站点抓取: robots.txt + sitemap + 链接发现

        最优策略:
        1. 解析 robots.txt → 获取 sitemap URLs
        2. 解析 sitemap → 获取页面列表
        3. 逐页抓取 → 同域链接发现 (可选)
        """
        from urllib.parse import urlparse

        domain = urlparse(start_url).netloc
        all_urls: set[str] = set()
        fed_url = start_url

        # 1. 尝试 robots.txt → sitemap 发现
        if self.config.respect_robots and self.config.enable_sitemap_discovery:
            from .robots import get_robots_parser
            try:
                rp = get_robots_parser()
                sitemaps = list(rp.get_sitemaps(start_url))
                logger.info("Site crawl: found %d sitemaps from robots.txt", len(sitemaps))
                for sitemap_url in sitemaps[:3]:   # 最多 3 个 sitemap
                    try:
                        sitemap_results = await self.crawl_sitemap(
                            sitemap_url,
                            on_progress=on_progress,
                            **{**kwargs, "max_concurrent": kwargs.get("max_concurrent", 3)},
                        )
                        for r in sitemap_results:
                            if r.success:
                                all_urls.add(r.url)
                    except Exception as e:
                        logger.warning("Failed to process sitemap %s: %s", sitemap_url, e)
            except Exception as e:
                logger.warning("robots.txt check failed for %s: %s", start_url, e)

        # 2. 直接抓取入口页
        entry_result = await self.crawl_one(fed_url)
        if entry_result.success:
            all_urls.add(fed_url)

        # 3. Feed 发现
        if self.config.enable_feed_discovery:
            try:
                feed_urls = await self._discover_feeds(start_url)
                for fu in feed_urls[:3]:
                    try:
                        feed_results = await self.crawl_feed(
                            fu,
                            on_progress=on_progress,
                            **{**kwargs, "max_concurrent": kwargs.get("max_concurrent", 3)},
                        )
                        for r in feed_results:
                            if r.success:
                                all_urls.add(r.url)
                    except Exception:
                        pass
            except Exception:
                pass

        # 4. 同域链接发现 (可选)
        if self.config.follow_links and len(all_urls) < self.config.max_pages:
            discovered = set()
            from bs4 import BeautifulSoup
            import httpx

            for url in list(all_urls):
                try:
                    async with httpx.AsyncClient(
                        timeout=self.config.anti_detect.timeout_seconds,
                        follow_redirects=True,
                    ) as client:
                        resp = await client.get(url)
                        soup = BeautifulSoup(resp.text, "html.parser")
                        for a in soup.find_all("a", href=True):
                            href = a["href"]
                            full_url = urljoin(url, href)
                            if urlparse(full_url).netloc == domain:
                                discovered.add(full_url)
                except Exception:
                    continue

            new_urls = discovered - all_urls
            remaining = self.config.max_pages - len(all_urls)
            all_urls.update(list(new_urls)[:remaining])

        # 5. 批量抓取所有 URL
        url_list = list(all_urls)[:self.config.max_pages]
        return await self.crawl(url_list, on_progress=on_progress, **kwargs)

    # ── 内部方法 ──────────────────────────────────────

    def _prepare_tasks(self, urls: list[str]) -> list[CrawlTask]:
        """URL 列表 → 任务对象列表"""
        tasks = []
        for url in urls:
            domain = urlparse(url).netloc
            # 域名过滤
            if self.config.allowed_domains and domain not in self.config.allowed_domains:
                continue
            if self.config.disallowed_domains and domain in self.config.disallowed_domains:
                continue

            task = CrawlTask(
                url=url,
                domain=domain,
                priority=TaskPriority.NORMAL,
                strategy=StrategyType.AUTO,
                skip_robots=not self.config.respect_robots,
            )
            tasks.append(task)
        return tasks

    async def _discover_feeds(self, url: str) -> list[str]:
        """从 HTML 页面发现 Feed URL (RSS/Atom)"""
        from .strategies.feed_crawler import FeedCrawlerStrategy
        strategy = FeedCrawlerStrategy(
            anti_detect_cfg=self.config.anti_detect,
            quality_cfg=self.config.quality,
        )
        return await strategy.discover_feed_url(url)

    # ── 统计 ──────────────────────────────────────────

    @property
    def stats(self) -> dict:
        """获取当前统计"""
        elapsed = time.time() - self._start_time if self._start_time else 0
        return {
            "elapsed_sec": elapsed,
            "total_urls": self._total_urls,
            "scheduler": self._scheduler.stats if self._scheduler else {},
            "strategies": self._registry.list_strategies(),
        }


# ══════════════════════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════════════════════

_pipeline: Optional[CrawlPipeline] = None


def get_pipeline(config: Optional[CrawlConfig] = None) -> CrawlPipeline:
    """获取全局爬取流水线实例"""
    global _pipeline
    if _pipeline is None:
        _pipeline = CrawlPipeline(config=config)
    elif config is not None:
        _pipeline.config = config
    return _pipeline
