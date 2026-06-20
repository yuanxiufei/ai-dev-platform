"""
Celery 后台任务队列 — 持久化 + 重试 + 监控

功能:
- 基于 Celery + Redis broker 的分布式任务队列
- 任务持久化（任务状态保存在 Redis/DB，重启不丢失）
- 自动重试（指数退避）
- 任务优先级（HIGH/MEDIUM/LOW）
- 任务监控（查询状态/进度/结果）
- 可选启用（TASK_QUEUE_ENABLED 配置）

任务类型:
- model_download: 异步下载模型
- video_generate: 异步视频生成
- batch_process: 批量数据处理
- cleanup: 定时清理
"""

import logging
from enum import Enum
from typing import Any, Optional

from celery import Celery, Task
from celery.result import AsyncResult

from app.core.config import settings

logger = logging.getLogger("task_queue")


class TaskPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    STARTED = "STARTED"
    RETRY = "RETRY"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    REVOKED = "REVOKED"


def _build_broker_url() -> str:
    """组装 Celery broker URL"""
    broker_url = getattr(settings, "CELERY_BROKER_URL", "") or ""
    if broker_url:
        return str(broker_url)

    # 从 Redis 配置组装
    host = getattr(settings, "REDIS_HOST", "localhost") or "localhost"
    port = int(getattr(settings, "REDIS_PORT", 6379) or 6379)
    password = getattr(settings, "REDIS_PASSWORD", "") or ""
    db = int(getattr(settings, "REDIS_DB", 0) or 0)

    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


def _build_backend_url() -> str:
    """组装 Celery result backend URL"""
    backend_url = getattr(settings, "CELERY_RESULT_BACKEND", "") or ""
    if backend_url:
        return str(backend_url)
    return _build_broker_url()


celery_app = Celery(
    "ai_fullstack",
    broker=_build_broker_url(),
    backend=_build_backend_url(),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
    worker_prefetch_multiplier=1,
    # 重试策略
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # 默认重试
    task_default_retry_delay=60,  # 初始重试间隔 60s
    task_max_retries=3,
    # 结果过期
    result_expires=3600 * 24,  # 24 小时
    result_extended=True,
    # 路由
    task_routes={
        "app.core.task_queue.tasks.*": {"queue": "default"},
    },
    # 优先级队列
    task_queue_max_priority=10,
    task_default_priority=5,
)

# 根据配置决定是否加载任务
_task_queue_enabled = getattr(settings, "TASK_QUEUE_ENABLED", True)

if _task_queue_enabled:
    try:
        # 延迟导入避免循环依赖
        from app.core.task_queue import tasks  # noqa: F401
        logger.info(
            "Celery task queue initialized (broker=%s)",
            _build_broker_url(),
        )
    except ImportError as e:
        logger.warning("Task queue tasks module not found: %s", e)
else:
    logger.info("Task queue disabled by config (TASK_QUEUE_ENABLED=false)")


# ── 任务管理辅助 ──────────────────────────────────────

def get_task_status(task_id: str) -> dict[str, Any]:
    """查询任务状态"""
    result = AsyncResult(task_id, app=celery_app)

    response: dict[str, Any] = {
        "task_id": task_id,
        "status": result.status,
    }

    if result.ready():
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.info) if result.info else "Unknown error"

    if result.info and isinstance(result.info, dict):
        info = result.info
        if "progress" in info:
            response["progress"] = info["progress"]
        if "stage" in info:
            response["stage"] = info["stage"]

    return response


def revoke_task(task_id: str, terminate: bool = False) -> bool:
    """撤销任务"""
    try:
        celery_app.control.revoke(task_id, terminate=terminate)
        logger.info("Task revoked: %s (terminate=%s)", task_id, terminate)
        return True
    except Exception as e:
        logger.error("Failed to revoke task %s: %s", task_id, e)
        return False


class TrackedTask(Task):
    """带进度追踪的任务基类"""

    abstract = True

    def update_progress(self, progress: int, stage: str = "") -> None:
        """更新任务进度（0-100）"""
        self.update_state(
            state="PROGRESS",
            meta={"progress": progress, "stage": stage},
        )
