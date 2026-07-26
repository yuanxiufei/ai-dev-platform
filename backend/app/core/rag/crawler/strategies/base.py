"""
爬取策略基类与注册表

设计模式: 策略模式 (Strategy Pattern)
- 每种抓取策略实现 `BaseCrawlerStrategy` 接口
- `StrategyRegistry` 统一管理策略选择与回退
- 自动策略检测: 基于 URL 特征 + 站点类型选择最优策略
"""

from __future__ import annotations

import abc
import logging
from typing import AsyncIterator, Optional

from ..types import CrawlTask, PageResult, StrategyType

logger = logging.getLogger("rag.crawler.strategy")


class BaseCrawlerStrategy(abc.ABC):
    """爬取策略基类

    子类必须实现:
    - strategy_type: 策略类型标识
    - can_handle(url): 判断是否能处理该 URL
    - fetch(task): 执行爬取并返回结果
    """

    strategy_type: StrategyType

    def __init__(self):
        self._stats = {"total": 0, "success": 0, "failed": 0, "total_time_ms": 0.0}

    @abc.abstractmethod
    async def fetch(self, task: CrawlTask) -> PageResult:
        """执行爬取任务

        Args:
            task: 爬取任务定义

        Returns:
            PageResult: 爬取结果 (成功/失败信息均在 result 内)
        """
        ...

    @abc.abstractmethod
    def can_handle(self, url: str) -> bool:
        """判断是否能处理此 URL

        Args:
            url: 目标 URL

        Returns:
            bool: True 表示此策略适用于该 URL
        """
        ...

    async def fetch_batch(
        self, tasks: list[CrawlTask]
    ) -> AsyncIterator[PageResult]:
        """批量爬取 (默认逐个执行，子类可覆写为并发)"""
        for task in tasks:
            yield await self.fetch(task)

    def get_stats(self) -> dict:
        return dict(self._stats)

    def __repr__(self) -> str:
        return f"<{self.strategy_type.value}Strategy stats={self._stats}>"


class StrategyRegistry:
    """策略注册表

    功能:
    - 注册/注销策略实现
    - 基于 URL 自动选择最优策略
    - 策略回退 (当前策略失败时自动切换)
    - 批量查询最佳策略
    """

    def __init__(self):
        self._strategies: dict[StrategyType, BaseCrawlerStrategy] = {}
        self._fallback_chain: list[StrategyType] = []

    def register(self, strategy: BaseCrawlerStrategy):
        """注册策略"""
        self._strategies[strategy.strategy_type] = strategy
        logger.debug("注册策略: %s", strategy.strategy_type.value)

    def unregister(self, strategy_type: StrategyType):
        """注销策略"""
        self._strategies.pop(strategy_type, None)

    def get(self, strategy_type: StrategyType) -> Optional[BaseCrawlerStrategy]:
        """获取指定策略"""
        return self._strategies.get(strategy_type)

    def select(self, url: str, preferred: Optional[StrategyType] = None) -> BaseCrawlerStrategy:
        """选择最优策略

        优先级: 指定策略 > 自动检测 > 第一个能处理 > 回退链

        Args:
            url: 目标 URL
            preferred: 偏好策略

        Returns:
            最佳策略实例
        """
        # 1. 用户指定策略
        if preferred and preferred != StrategyType.AUTO:
            strategy = self._strategies.get(preferred)
            if strategy and strategy.can_handle(url):
                return strategy

        # 2. 自动检测: 按注册顺序，找到第一个 can_handle
        for st in (StrategyType.API, StrategyType.FEED, StrategyType.SITEMAP,
                    StrategyType.DYNAMIC, StrategyType.STATIC):
            strategy = self._strategies.get(st)
            if strategy and strategy.can_handle(url):
                return strategy

        # 3. 回退到 STATIC (最通用)
        fallback = self._strategies.get(StrategyType.STATIC)
        if fallback:
            return fallback

        # 4. 任意可用策略
        for strategy in self._strategies.values():
            return strategy

        raise RuntimeError(f"无可用爬取策略处理 URL: {url}")

    def get_fallback_chain(self, current: StrategyType) -> list[BaseCrawlerStrategy]:
        """获取回退策略链 (当前策略之后的可选策略)"""
        chain = []
        found_current = False
        for st in self._fallback_chain:
            if found_current and st in self._strategies:
                chain.append(self._strategies[st])
            if st == current:
                found_current = True
        return chain

    def set_fallback_chain(self, chain: list[StrategyType]):
        """设置回退链顺序"""
        self._fallback_chain = chain

    def list_strategies(self) -> list[dict]:
        """列出所有已注册策略"""
        return [
            {
                "type": st.value,
                "can_handle": s.can_handle,
                "stats": s.get_stats(),
            }
            for st, s in self._strategies.items()
        ]

    @property
    def available_types(self) -> list[StrategyType]:
        return list(self._strategies.keys())

    def __len__(self) -> int:
        return len(self._strategies)


# ── 全局注册表 ─────────────────────────────────────────

_registry: Optional[StrategyRegistry] = None


def get_strategy_registry() -> StrategyRegistry:
    """获取策略注册表单例"""
    global _registry
    if _registry is None:
        _registry = StrategyRegistry()
    return _registry
