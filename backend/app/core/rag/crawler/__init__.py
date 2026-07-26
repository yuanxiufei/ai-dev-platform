"""
多策略网页爬取系统

架构层次:
  types      — 类型定义 + 数据结构
  anti_detect — 反检测引擎 (UA轮换/请求头/延迟抖动/代理)
  robots     — robots.txt 合规解析
  quality    — SimHash去重 + 内容评分 + 指数退避重试 + HTML清洗
  strategies — 5种爬取策略 (Static/Dynamic/API/Sitemap/Feed)
  scheduler  — 并发任务调度 (优先级队列 + 域名限速 + 自适应)
  pipeline   — 端到端爬取流水线 (策略→反检测→去重→质量→调度)

使用示例:
    from app.core.rag.crawler import CrawlPipeline, CrawlConfig

    pipeline = CrawlPipeline()
    results = await pipeline.crawl([
        "https://example.com/docs/getting-started",
        "https://example.com/api/products",
    ])

    for r in results:
        if r.success:
            print(f"OK: {r.title} ({len(r.text)} chars, quality={r.quality_score:.0f})")

WebSocket 进度推送:
    async def on_progress(progress):
        await ws.send_json(progress.to_dict())

    results = await pipeline.crawl(urls, on_progress=on_progress)

Sitemap 站点爬取:
    results = await pipeline.crawl_sitemap("https://docs.example.com/sitemap.xml")

站点全爬 (robots + sitemap + Feed + 链接):
    results = await pipeline.crawl_site("https://example.com")
"""

from .types import (
    StrategyType,
    TaskPriority,
    TaskStatus,
    AntiDetectConfig,
    QualityConfig,
    SchedulerConfig,
    DomainRateLimit,
    CrawlTask,
    PageResult,
    BatchResult,
    CrawlProgress,
)
from .anti_detect import AntiDetectEngine, get_anti_detect
from .robots import RobotsParser, get_robots_parser
from .quality import (
    SimHashDeduper,
    get_deduper,
    ContentScorer,
    get_scorer,
    RetryManager,
    get_retry_manager,
    HTMLCleaner,
    get_cleaner,
    LanguageDetector,
)
from .strategies import (
    BaseCrawlerStrategy,
    StrategyRegistry,
    StaticCrawlerStrategy,
    DynamicCrawlerStrategy,
    APICrawlerStrategy,
    SitemapCrawlerStrategy,
    FeedCrawlerStrategy,
    create_registry,
)
from .scheduler import CrawlScheduler, PriorityQueue, DomainThrottler
from .pipeline import CrawlPipeline, CrawlConfig, get_pipeline

# OCR 插件 (可选)
try:
    from .ocr_plugin import SmolDoclingOCR, OcrConfig, OcrPageResult, get_ocr_engine
    _OCR_EXPORT = [
        "SmolDoclingOCR",
        "OcrConfig",
        "OcrPageResult",
        "get_ocr_engine",
    ]
except ImportError:
    _OCR_EXPORT = []

__all__ = [
    # 类型
    "StrategyType",
    "TaskPriority",
    "TaskStatus",
    "AntiDetectConfig",
    "QualityConfig",
    "SchedulerConfig",
    "DomainRateLimit",
    "CrawlTask",
    "PageResult",
    "BatchResult",
    "CrawlProgress",
    # 反检测
    "AntiDetectEngine",
    "get_anti_detect",
    # robots
    "RobotsParser",
    "get_robots_parser",
    # 质量
    "SimHashDeduper",
    "get_deduper",
    "ContentScorer",
    "get_scorer",
    "RetryManager",
    "get_retry_manager",
    "HTMLCleaner",
    "get_cleaner",
    "LanguageDetector",
    # 策略
    "BaseCrawlerStrategy",
    "StrategyRegistry",
    "StaticCrawlerStrategy",
    "DynamicCrawlerStrategy",
    "APICrawlerStrategy",
    "SitemapCrawlerStrategy",
    "FeedCrawlerStrategy",
    "create_registry",
    # 调度
    "CrawlScheduler",
    "PriorityQueue",
    "DomainThrottler",
    # 流水线
    "CrawlPipeline",
    "CrawlConfig",
    "get_pipeline",
    # OCR
    *_OCR_EXPORT,
]
