"""
并发任务调度器

核心职责:
- 优先级队列管理 (FCPS + 优先级老化)
- 域名级并发限制 + 速率控制
- 自适应并发调整 (基于域名响应统计)
- 全局/域名 Semaphore 控制
- 批量提交 + 进度追踪

参考: Scrapy AutoThrottle + Crawlee ConcurrencyManager
"""

from __future__ import annotations

import asyncio
import heapq
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import AsyncIterator, Callable, Optional

from .types import (
    AntiDetectConfig,
    CrawlProgress,
    CrawlTask,
    DomainRateLimit,
    PageResult,
    QualityConfig,
    SchedulerConfig,
    TaskPriority,
    TaskStatus,
)

logger = logging.getLogger("rag.crawler.scheduler")


# ══════════════════════════════════════════════════════════════
# 优先级队列 (heapq 实现)
# ══════════════════════════════════════════════════════════════

@dataclass(order=True)
class _PriorityTask:
    """heapq 排序项: (priority_value, seq, task)"""
    priority_value: int
    seq: int
    task: CrawlTask = field(compare=False)


class PriorityQueue:
    """基于 heapq 的线程安全优先级队列

    特性:
    - 优先级老化: 等待超过 max_wait_seconds 的任务自动提升优先级
    - FIFO 平局打破: 同优先级按入队顺序
    - 支持动态重新入队 (重试)
    """

    def __init__(self):
        self._heap: list[_PriorityTask] = []
        self._seq = 0   # FIFO tie-breaker

    def push(self, task: CrawlTask):
        """入队 (值越小优先级越高)"""
        self._seq += 1
        heapq.heappush(self._heap, _PriorityTask(
            priority_value=task.priority.value,
            seq=self._seq,
            task=task,
        ))

    def pop(self) -> Optional[CrawlTask]:
        """出队 (最高优先级)"""
        if not self._heap:
            return None
        return heapq.heappop(self._heap).task

    def peek(self) -> Optional[CrawlTask]:
        """查看最高优先级任务 (不出队)"""
        if not self._heap:
            return None
        return self._heap[0].task

    def age_priorities(self, max_wait_seconds: float = 60.0):
        """优先级老化: 久等任务自动提升优先级"""
        now = time.time()
        new_heap = []
        self._seq = 0
        while self._heap:
            item = heapq.heappop(self._heap)
            elapsed = now - item.task.created_at
            if elapsed > max_wait_seconds:
                # 提升至最高优先级
                if item.task.priority != TaskPriority.HIGH:
                    item.task.priority = TaskPriority.HIGH
                    item.priority_value = TaskPriority.HIGH.value
                    logger.debug(
                        "Task %s priority aged to HIGH (waited %.0fs)",
                        item.task.task_id, elapsed,
                    )
            self._seq += 1
            item.seq = self._seq
            new_heap.append(item)
        self._heap = new_heap
        heapq.heapify(self._heap)

    def remove(self, task_id: str) -> bool:
        """移除指定任务"""
        for i, item in enumerate(self._heap):
            if item.task.task_id == task_id:
                self._heap.pop(i)
                heapq.heapify(self._heap)
                return True
        return False

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)


# ══════════════════════════════════════════════════════════════
# 域名限速器
# ══════════════════════════════════════════════════════════════

@dataclass
class _DomainState:
    """单个域名的状态追踪"""
    domain: str
    concurrent: int = 0                # 当前并发数
    last_request_time: float = 0.0     # 上次请求时间戳
    total_requests: int = 0            # 总请求数
    total_errors: int = 0              # 总错误数
    avg_response_time: float = 0.0     # 平均响应时间 (指数移动平均)
    rate_limit: DomainRateLimit = field(default_factory=DomainRateLimit)
    semaphore: Optional[asyncio.Semaphore] = None


class DomainThrottler:
    """域名级速率限制 + 并发控制

    策略:
    - 每个域名独立的 Semaphore (限制并发)
    - 请求间隔控制 (遵守 Crawl-Delay + 自定义 delay)
    - 自适应降速: 错误率高/响应慢时自动降低并发和增加延迟
    """

    def __init__(
        self,
        default_max_concurrent: int = 3,
        default_delay: float = 1.0,
    ):
        self._default_max_concurrent = default_max_concurrent
        self._default_delay = default_delay
        self._domains: dict[str, _DomainState] = {}
        self._lock = asyncio.Lock()

    async def _get_domain(self, domain: str) -> _DomainState:
        """获取或创建域名状态"""
        if domain not in self._domains:
            async with self._lock:
                if domain not in self._domains:
                    limit = DomainRateLimit(
                        domain=domain,
                        max_concurrent=self._default_max_concurrent,
                        delay_seconds=self._default_delay,
                    )
                    self._domains[domain] = _DomainState(
                        domain=domain,
                        rate_limit=limit,
                        semaphore=asyncio.Semaphore(self._default_max_concurrent),
                    )
        return self._domains[domain]

    async def acquire(self, domain: str) -> float:
        """获取域名许可，返回建议延迟时间 (秒)"""
        state = await self._get_domain(domain)
        # 等待信号量
        await state.semaphore.acquire()
        state.concurrent += 1

        # 计算需要等待的时间
        now = time.time()
        elapsed = now - state.last_request_time
        delay = state.rate_limit.delay_seconds
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)

        state.last_request_time = time.time()
        state.total_requests += 1
        return delay

    def release(self, domain: str, response_time: float = 0, success: bool = True):
        """释放域名许可 + 更新统计"""
        if domain not in self._domains:
            return
        state = self._domains[domain]
        state.concurrent = max(0, state.concurrent - 1)
        state.semaphore.release()

        # 更新统计
        if response_time > 0:
            # 指数移动平均 α=0.1
            if state.avg_response_time == 0:
                state.avg_response_time = response_time
            else:
                state.avg_response_time = 0.9 * state.avg_response_time + 0.1 * response_time

        if not success:
            state.total_errors += 1

        # 自适应调整
        self._auto_adjust(state)

    def _auto_adjust(self, state: _DomainState):
        """自适应调速 (参考 Scrapy AutoThrottle)"""
        if state.total_requests < 10:
            return

        error_rate = state.total_errors / max(state.total_requests, 1)

        # 错误率 > 30%: 降速
        if error_rate > 0.3:
            state.rate_limit.max_concurrent = max(1, state.rate_limit.max_concurrent - 1)
            state.rate_limit.delay_seconds = min(10.0, state.rate_limit.delay_seconds * 1.5)
            logger.debug(
                "Throttle DOWN domain=%s err=%.1f%% concurrency=%d delay=%.1fs",
                state.domain, error_rate * 100, state.rate_limit.max_concurrent,
                state.rate_limit.delay_seconds,
            )

        # 错误率 < 5%: 慢慢加速
        elif error_rate < 0.05 and state.avg_response_time < 3.0:
            state.rate_limit.max_concurrent = min(
                self._default_max_concurrent * 2, state.rate_limit.max_concurrent + 1
            )
            state.rate_limit.delay_seconds = max(0.3, state.rate_limit.delay_seconds * 0.9)

    def set_limit(self, domain: str, limit: DomainRateLimit):
        """手动设置域名限制"""
        self._domains[domain] = _DomainState(
            domain=domain,
            rate_limit=limit,
            semaphore=asyncio.Semaphore(limit.max_concurrent),
        )

    def get_stats(self, domain: str) -> Optional[dict]:
        """获取域名统计"""
        if domain not in self._domains:
            return None
        s = self._domains[domain]
        return {
            "domain": s.domain,
            "concurrent": s.concurrent,
            "total_requests": s.total_requests,
            "total_errors": s.total_errors,
            "error_rate": (s.total_errors / max(s.total_requests, 1)),
            "avg_response_time_ms": s.avg_response_time * 1000,
            "max_concurrent": s.rate_limit.max_concurrent,
            "delay_seconds": s.rate_limit.delay_seconds,
        }

    def get_all_stats(self) -> dict[str, dict]:
        """获取所有域名统计"""
        return {d: self.get_stats(d) for d in self._domains}

    def reset(self):
        self._domains.clear()


# ══════════════════════════════════════════════════════════════
# 任务调度器
# ══════════════════════════════════════════════════════════════

class CrawlScheduler:
    """多策略并发任务调度器

    功能:
    - 优先级队列 + 域名限速 + 自适应并发
    - 进度追踪 (实时反馈)
    - 批量任务提交 (sitemap / URL 列表)
    - 全局并行上限 (global_max_concurrent)
    - 干净关闭 (cancel pending / graceful drain)

    使用示例:
        scheduler = CrawlScheduler(registry=registry)
        progress = await scheduler.submit_batch(tasks, on_progress=callback)
    """

    def __init__(
        self,
        registry,
        config: Optional[SchedulerConfig] = None,
    ):
        from .strategies.base import StrategyRegistry
        self._registry: StrategyRegistry = registry
        self.config = config or SchedulerConfig()

        # 核心组件
        self._queue = PriorityQueue()
        self._throttler = DomainThrottler(
            default_max_concurrent=self.config.domain_max_concurrent,
            default_delay=self.config.delay_seconds,
        )

        # 全局信号量
        self._global_semaphore = asyncio.Semaphore(self.config.global_max_concurrent)

        # 状态
        self._running = False
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0
        self._progress: Optional[CrawlProgress] = None
        self._on_progress: Optional[Callable] = None

    # ── 启动/停止 ───────────────────────────────────────

    async def start(self):
        """启动调度器"""
        self._running = True
        logger.info(
            "Scheduler started: global_concurrent=%d domain_concurrent=%d delay=%.1fs",
            self.config.global_max_concurrent,
            self.config.domain_max_concurrent,
            self.config.delay_seconds,
        )

    async def stop(self):
        """停止调度器 (排空队列)"""
        self._running = False
        self._throttler.reset()
        logger.info(
            "Scheduler stopped: submitted=%d completed=%d failed=%d",
            self._total_submitted, self._total_completed, self._total_failed,
        )

    # ── 任务提交 ───────────────────────────────────────

    def submit(self, task: CrawlTask):
        """提交单个任务到队列"""
        self._queue.push(task)
        self._total_submitted += 1

    def submit_batch(self, tasks: list[CrawlTask]):
        """批量提交任务"""
        for task in tasks:
            self.submit(task)

    # ── 核心调度循环 ───────────────────────────────────

    async def run(
        self,
        on_progress: Optional[Callable[[CrawlProgress], None]] = None,
    ) -> CrawlProgress:
        """执行调度循环 (会阻塞直到队列空)

        Args:
            on_progress: 进度回调 (用于 WebSocket 实时推送)

        Returns:
            CrawlProgress: 最终进度汇总
        """
        from urllib.parse import urlparse

        await self.start()
        self._on_progress = on_progress

        running_tasks: dict[str, asyncio.Task] = {}
        results: list[PageResult] = []

        try:
            while self._running:
                # 优先级老化
                self._queue.age_priorities(max_wait_seconds=60.0)

                # 提交新任务 (不超过全局并发上限)
                async with self._global_semaphore:
                    while self._running and len(running_tasks) < self.config.global_max_concurrent:
                        task = self._queue.pop()
                        if task is None:
                            break

                        # robots.txt 检查
                        if task.domain:
                            if not self._check_robots(task):
                                failed = PageResult(
                                    url=task.url, task_id=task.task_id,
                                    domain=task.domain,
                                    error="Blocked by robots.txt",
                                    success=False,
                                )
                                results.append(failed)
                                self._total_completed += 1
                                self._total_failed += 1
                                self._emit_progress()
                                continue

                        # 启动异步任务
                        coro = self._execute_one(task)
                        t = asyncio.create_task(coro)
                        running_tasks[task.task_id] = t

                # 等待任一个任务完成
                if not running_tasks:
                    if not self._queue:
                        break   # 队列空 + 无线程 → 结束
                    await asyncio.sleep(0.05)
                    continue

                done, pending = await asyncio.wait(
                    running_tasks.values(),
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=0.5,
                )

                # 收集完成的任务
                for t in done:
                    try:
                        result = await t
                        results.append(result)
                        self._total_completed += 1
                        if not result.success:
                            self._total_failed += 1
                    except Exception as e:
                        logger.warning("Task execution error: %s", e)
                        self._total_completed += 1
                        self._total_failed += 1

                # 清理已完成的任务
                for task_id in [k for k, v in running_tasks.items() if v.done()]:
                    running_tasks.pop(task_id, None)

                self._emit_progress()

            # ── 等待剩余任务 ──────────────────────────
            if running_tasks:
                logger.info("Draining %d remaining tasks...", len(running_tasks))
                for t in asyncio.as_completed(running_tasks.values()):
                    try:
                        result = await t
                        results.append(result)
                        self._total_completed += 1
                        if not result.success:
                            self._total_failed += 1
                    except Exception:
                        self._total_completed += 1
                        self._total_failed += 1

        finally:
            await self.stop()

        final_progress = CrawlProgress(
            total=self._total_submitted,
            completed=self._total_completed,
            failed=self._total_failed,
            results=results,
            domain_stats=self._throttler.get_all_stats(),
        )
        self._emit_progress()
        return final_progress

    # ── 单任务执行 ─────────────────────────────────────

    async def _execute_one(self, task: CrawlTask) -> PageResult:
        """执行单个任务 (含限速等待 + 重试 + 策略回退)"""
        from urllib.parse import urlparse

        from .quality import get_retry_manager, get_deduper
        from .robots import get_robots_parser

        domain = task.domain or urlparse(task.url).netloc
        task.domain = domain

        # ── robots.txt 检查 ─────────────────────────
        if not task.skip_robots:
            rp = get_robots_parser()
            if not rp.is_allowed(task.url, user_agent=task.user_agent or "*"):
                logger.info("Task %s blocked by robots.txt: %s", task.task_id, task.url)
                return PageResult(
                    url=task.url, task_id=task.task_id, domain=domain,
                    error="Blocked by robots.txt", success=False,
                    strategy=task.strategy,
                )

        # ── 去重检查 ─────────────────────────────────
        deduper = get_deduper()
        if deduper.is_seen(task.url):
            logger.debug("Task %s skipped (duplicate URL): %s", task.task_id, task.url)
            return PageResult(
                url=task.url, task_id=task.task_id, domain=domain,
                error="Duplicate URL", success=False,
                strategy=task.strategy,
            )

        # ── 限速等待 ─────────────────────────────────
        delay = await self._throttler.acquire(domain)
        if delay > 0:
            await asyncio.sleep(delay)

        # ── 重试循环 (含策略回退) ────────────────────
        retry_mgr = get_retry_manager()
        strategy = self._registry.select(task.url, preferred=task.strategy)
        fallback_chain = self._registry.get_fallback_chain(strategy.strategy_type)

        attempt = 0
        max_attempts = 1 + len(fallback_chain)
        last_result: Optional[PageResult] = None

        for attempt in range(max_attempts):
            try:
                start = time.time()
                result = await strategy.fetch(task)
                elapsed = time.time() - start

                self._throttler.release(domain, response_time=elapsed, success=result.success)

                if result.success:
                    # 合格结果
                    deduper.mark_seen(task.url, result.text)
                    result.strategy = strategy.strategy_type
                    return result

                # 检查是否需要策略回退
                if attempt < max_attempts - 1 and fallback_chain:
                    strategy = fallback_chain[attempt]
                    logger.info(
                        "Task %s: strategy fallback to %s (attempt %d/%d)",
                        task.task_id, strategy.strategy_type.value, attempt + 2, max_attempts,
                    )
                    last_result = result
                    continue

                # 最后一次 retry
                retry_mgr.record_failure(domain)
                retry_delay = retry_mgr.get_delay(domain)
                if retry_delay == -1:
                    # 达上限，返回失败
                    return result
                await asyncio.sleep(retry_delay)

            except Exception as e:
                logger.warning(
                    "Task %s attempt %d/%d exception: %s",
                    task.task_id, attempt + 1, max_attempts, e,
                )
                self._throttler.release(domain, success=False)
                if attempt < max_attempts - 1:
                    retry_mgr.record_failure(domain)
                    retry_delay = retry_mgr.get_delay(domain)
                    if retry_delay > 0:
                        await asyncio.sleep(retry_delay)

        # 全部策略均已尝试
        if last_result:
            return last_result
        return PageResult(
            url=task.url, task_id=task.task_id, domain=domain,
            error="All strategies exhausted",
            success=False, strategy=task.strategy,
        )

    # ── 进度追踪 ─────────────────────────────────────

    def _emit_progress(self):
        """发送进度回调"""
        if self._on_progress:
            try:
                progress = CrawlProgress(
                    total=self._total_submitted,
                    completed=self._total_completed,
                    failed=self._total_failed,
                    pending=self._total_submitted - self._total_completed,
                )
                self._on_progress(progress)
            except Exception:
                pass

    def get_progress(self) -> CrawlProgress:
        """获取当前进度"""
        return CrawlProgress(
            total=self._total_submitted,
            completed=self._total_completed,
            failed=self._total_failed,
            pending=max(0, self._total_submitted - self._total_completed),
        )

    # ── 辅助 ─────────────────────────────────────────

    @staticmethod
    def _check_robots(task: CrawlTask) -> bool:
        """检查 robots.txt 合规性"""
        if task.skip_robots:
            return True
        try:
            from .robots import get_robots_parser
            rp = get_robots_parser()
            if rp.is_site_blocked(task.domain):
                return False
            return rp.is_allowed(task.url)
        except Exception:
            return True  # 网络异常时放行

    @property
    def stats(self) -> dict:
        return {
            "queue_size": len(self._queue),
            "submitted": self._total_submitted,
            "completed": self._total_completed,
            "failed": self._total_failed,
            "domains": self._throttler.get_all_stats(),
        }
