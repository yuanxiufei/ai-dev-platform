"""
Cron 定时任务管理器

借鉴 AstrBot CronJobManager:
- 基于 apscheduler AsyncIOScheduler
- 支持 Basic Job（简单回调）和 Active Agent Job（唤醒 Agent）
- cron 表达式 + 一次性任务
- 持久化 + 启动恢复
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.core.cron.models import CronJob, CronJobStatus, CronJobType

logger = logging.getLogger("cron.manager")

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    logger.warning("apscheduler not installed. Cron system will run in stub mode.")


class CronSchedulingError(Exception):
    """任务调度失败"""


class CronJobManager:
    """定时任务调度器"""

    if HAS_APSCHEDULER:
        scheduler: AsyncIOScheduler

    def __init__(self) -> None:
        if HAS_APSCHEDULER:
            self.scheduler = AsyncIOScheduler()
        else:
            self.scheduler = None  # type: ignore[assignment]
        self._jobs: dict[str, CronJob] = {}
        self._basic_handlers: dict[str, Callable[..., Any]] = {}
        self._lock = asyncio.Lock()
        self._started = False

        # Agent 唤醒回调（由外部注入）
        self._agent_wake_callback: Callable[..., Any] | None = None

    # ── 生命周期 ───────────────────────────────────────

    async def start(self) -> None:
        """启动调度器"""
        async with self._lock:
            if self._started:
                return
            if self.scheduler is not None:
                self.scheduler.start()
            self._started = True
            logger.info("CronJobManager: started")

    async def shutdown(self) -> None:
        """停止调度器"""
        async with self._lock:
            if not self._started:
                return
            if self.scheduler is not None:
                self.scheduler.shutdown(wait=False)
            self._started = False
            logger.info("CronJobManager: shutdown")

    # ── Basic Job ──────────────────────────────────────

    async def add_basic_job(
        self,
        name: str,
        cron_expression: str,
        handler: Callable[..., Any | Awaitable[Any]],
        description: str | None = None,
        timezone_str: str | None = None,
        payload: dict[str, Any] | None = None,
        enabled: bool = True,
        persistent: bool = False,
    ) -> CronJob:
        """添加简单定时任务"""
        job = CronJob(
            job_id=uuid.uuid4().hex[:12],
            name=name,
            job_type=CronJobType.BASIC,
            cron_expression=cron_expression,
            timezone=timezone_str,
            payload=payload or {},
            description=description,
            enabled=enabled,
            persistent=persistent,
        )
        self._jobs[job.job_id] = job
        self._basic_handlers[job.job_id] = handler

        if enabled:
            self._schedule_job(job)
        logger.info("CronJobManager: added basic job '%s' (cron=%s)", name, cron_expression)
        return job

    # ── Active Agent Job ───────────────────────────────

    async def add_active_job(
        self,
        name: str,
        cron_expression: str | None = None,
        payload: dict[str, Any] | None = None,
        description: str | None = None,
        timezone_str: str | None = None,
        enabled: bool = True,
        persistent: bool = True,
        run_once: bool = False,
        run_at: datetime | None = None,
    ) -> CronJob:
        """添加 Agent 唤醒任务

        Args:
            name: 任务名称（也用作 Agent 唤醒的提示信息）
            cron_expression: Cron 表达式（run_once 时可为 None）
            payload: 传递给 Agent 的上下文载荷
            run_once: 是否仅运行一次
            run_at: 一次性任务的运行时间
        """
        job_payload = {**(payload or {})}
        if run_once and run_at:
            job_payload["run_at"] = run_at.isoformat()

        job = CronJob(
            job_id=uuid.uuid4().hex[:12],
            name=name,
            job_type=CronJobType.ACTIVE_AGENT,
            cron_expression=cron_expression,
            timezone=timezone_str,
            payload=job_payload,
            description=description,
            enabled=enabled,
            persistent=persistent,
            run_once=run_once,
        )
        self._jobs[job.job_id] = job

        if enabled:
            self._schedule_job(job)
        logger.info(
            "CronJobManager: added active agent job '%s' (cron=%s, run_once=%s)",
            name, cron_expression, run_once,
        )
        return job

    # ── 任务管理 ───────────────────────────────────────

    async def update_job(self, job_id: str, **kwargs: Any) -> CronJob | None:
        """更新任务"""
        job = self._jobs.get(job_id)
        if not job:
            return None

        for key, value in kwargs.items():
            if hasattr(job, key):
                setattr(job, key, value)

        self._remove_scheduled(job_id)
        if job.enabled:
            self._schedule_job(job)
        logger.info("CronJobManager: updated job '%s'", job_id)
        return job

    async def delete_job(self, job_id: str) -> None:
        """删除任务"""
        self._remove_scheduled(job_id)
        self._basic_handlers.pop(job_id, None)
        self._jobs.pop(job_id, None)
        logger.info("CronJobManager: deleted job '%s'", job_id)

    async def list_jobs(self, job_type: CronJobType | None = None) -> list[CronJob]:
        """列出所有任务"""
        jobs = list(self._jobs.values())
        if job_type:
            jobs = [j for j in jobs if j.job_type == job_type]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    async def get_job(self, job_id: str) -> CronJob | None:
        """获取指定任务"""
        return self._jobs.get(job_id)

    async def run_job_now(self, job_id: str) -> None:
        """立即触发一次任务"""
        await self._run_job(job_id, ignore_enabled=True, delete_run_once=False)

    # ── 调度逻辑 ───────────────────────────────────────

    def _schedule_job(self, job: CronJob) -> None:
        """将任务注册到 apscheduler"""
        if self.scheduler is None:
            logger.warning("CronJobManager: scheduler not available (apscheduler missing)")
            return
        if not self._started:
            self.scheduler.start()
            self._started = True

        try:
            tzinfo = None
            if job.timezone:
                try:
                    tzinfo = ZoneInfo(job.timezone)
                except Exception:
                    logger.warning("Invalid timezone '%s' for job '%s'", job.timezone, job.job_id)

            if job.run_once:
                run_at_str = None
                if isinstance(job.payload, dict):
                    run_at_str = job.payload.get("run_at")
                run_at_str = run_at_str or job.cron_expression
                if not run_at_str:
                    raise ValueError(f"run_once job '{job.job_id}' missing run_at timestamp")

                run_at = datetime.fromisoformat(run_at_str)
                if run_at.tzinfo is None and tzinfo is not None:
                    run_at = run_at.replace(tzinfo=tzinfo)
                trigger = DateTrigger(run_date=run_at, timezone=tzinfo)
            else:
                if not job.cron_expression:
                    raise ValueError(f"Recurring job '{job.job_id}' missing cron_expression")
                trigger = CronTrigger.from_crontab(job.cron_expression, timezone=tzinfo)

            self.scheduler.add_job(
                self._run_job,
                id=job.job_id,
                trigger=trigger,
                args=[job.job_id],
                replace_existing=True,
                misfire_grace_time=30,
            )
            logger.debug("CronJobManager: scheduled job '%s'", job.job_id)
        except Exception as e:
            logger.exception("Failed to schedule job '%s': %s", job.job_id, e)
            raise CronSchedulingError(str(e)) from e

    def _remove_scheduled(self, job_id: str) -> None:
        """从 apscheduler 移除任务"""
        if self.scheduler is not None and self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

    async def _run_job(
        self,
        job_id: str,
        *,
        ignore_enabled: bool = False,
        delete_run_once: bool = True,
    ) -> None:
        """执行任务"""
        job = self._jobs.get(job_id)
        if not job or (not job.enabled and not ignore_enabled):
            return

        start_time = datetime.now(timezone.utc)
        job.status = CronJobStatus.RUNNING
        job.last_run_at = start_time.isoformat()
        job.last_error = None

        try:
            if job.job_type == CronJobType.BASIC:
                await self._run_basic_job(job)
            elif job.job_type == CronJobType.ACTIVE_AGENT:
                await self._run_active_agent_job(job, start_time)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")
            job.status = CronJobStatus.COMPLETED
        except Exception as e:
            job.status = CronJobStatus.FAILED
            job.last_error = str(e)[:500]
            logger.error("Cron job '%s' failed: %s", job_id, e, exc_info=True)
        finally:
            if job.run_once and delete_run_once:
                await self.delete_job(job_id)

    async def _run_basic_job(self, job: CronJob) -> None:
        """执行简单定时任务"""
        handler = self._basic_handlers.get(job.job_id)
        if not handler:
            raise RuntimeError(f"Basic job handler not found for '{job.job_id}'")
        payload = job.payload or {}
        result = handler(**payload) if payload else handler()
        if asyncio.iscoroutine(result):
            await result

    async def _run_active_agent_job(self, job: CronJob, start_time: datetime) -> None:
        """执行 Agent 唤醒任务"""
        if not self._agent_wake_callback:
            logger.warning(
                "CronJobManager: no agent_wake_callback set, job '%s' skipped", job.job_id,
            )
            return

        cron_meta = {
            "id": job.job_id,
            "name": job.name,
            "type": job.job_type.value,
            "run_once": job.run_once,
            "description": job.description,
            "run_started_at": start_time.isoformat(),
        }

        message = job.description or job.name
        await self._agent_wake_callback(
            message=message,
            payload=job.payload,
            cron_meta=cron_meta,
        )

    # ── 回调设置 ───────────────────────────────────────

    def set_agent_wake_callback(self, callback: Callable[..., Any]) -> None:
        """设置 Agent 唤醒回调

        当 Agent Job 触发时调用此回调。
        签名: async def callback(*, message: str, payload: dict, cron_meta: dict) -> None
        """
        self._agent_wake_callback = callback

    # ── 属性 ───────────────────────────────────────────

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def job_count(self) -> int:
        return len(self._jobs)


# ── 全局单例 ──────────────────────────────────────────────

_cron_manager: CronJobManager | None = None


def init_cron_manager() -> CronJobManager:
    """初始化全局 CronJobManager"""
    global _cron_manager
    _cron_manager = CronJobManager()
    return _cron_manager


def get_cron_manager() -> CronJobManager:
    """获取全局 CronJobManager"""
    global _cron_manager
    if _cron_manager is None:
        _cron_manager = CronJobManager()
    return _cron_manager
