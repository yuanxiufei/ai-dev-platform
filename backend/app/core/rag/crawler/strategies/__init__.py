"""
爬取策略包

策略层级 (优先→后备):
  API → Feed → Sitemap → Dynamic → Static

使用:
    from app.core.rag.crawler.strategies import create_registry
    reg = create_registry()
    result = await reg.fetch("https://example.com/api/data")
"""

from .base import BaseCrawlerStrategy, StrategyRegistry
from .static import StaticCrawlerStrategy
from .dynamic import DynamicCrawlerStrategy
from .api_crawler import APICrawlerStrategy
from .sitemap_crawler import SitemapCrawlerStrategy
from .feed_crawler import FeedCrawlerStrategy

__all__ = [
    "BaseCrawlerStrategy",
    "StrategyRegistry",
    "StaticCrawlerStrategy",
    "DynamicCrawlerStrategy",
    "APICrawlerStrategy",
    "SitemapCrawlerStrategy",
    "FeedCrawlerStrategy",
    "create_registry",
]


def create_registry(
    anti_detect_cfg=None,
    quality_cfg=None,
) -> StrategyRegistry:
    """创建预注册所有策略的注册表

    策略优先级 (高→低):
      API (明确路径特征) → Feed (XML) → Sitemap → Dynamic (SPA) → Static (兜底)
    """
    from ..types import AntiDetectConfig, QualityConfig

    anti_cfg = anti_detect_cfg or AntiDetectConfig()
    qual_cfg = quality_cfg or QualityConfig()

    registry = StrategyRegistry()

    # 注册策略 (按优先级)
    registry.register(APICrawlerStrategy(anti_detect_cfg=anti_cfg, quality_cfg=qual_cfg))
    registry.register(FeedCrawlerStrategy(anti_detect_cfg=anti_cfg, quality_cfg=qual_cfg))
    registry.register(SitemapCrawlerStrategy(anti_detect_cfg=anti_cfg, quality_cfg=qual_cfg))
    registry.register(DynamicCrawlerStrategy(anti_detect_cfg=anti_cfg, quality_cfg=qual_cfg))
    registry.register(StaticCrawlerStrategy(anti_detect_cfg=anti_cfg, quality_cfg=qual_cfg))

    return registry
