"""
Cron 任务数据模型

借鉴 AstrBot CronJob:
- Basic Job: 简单定时回调
- Active Agent Job: 定时唤醒 Agent 执行任务
- 支持 cron 表达式 + 一次性任务
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class CronJobType(str, Enum):
    BASIC = "basic"             # 简单定时回调
    ACTIVE_AGENT = "active_agent"  # 唤醒 Agent 执行任务


class CronJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CronJob:
    """定时任务定义"""

    job_id: str
    """唯一标识"""

    name: str
    """任务名称"""

    job_type: CronJobType = CronJobType.BASIC
    """任务类型"""

    cron_expression: str | None = None
    """Cron 表达式（Active Agent 时可选，一次性任务时不需）"""

    timezone: str | None = None
    """时区"""

    payload: dict[str, Any] = field(default_factory=dict)
    """任务载荷（传递给 handler 或 Agent）"""

    description: str | None = None
    """任务描述"""

    enabled: bool = True
    """是否启用"""

    persistent: bool = False
    """是否持久化（重启后恢复）"""

    run_once: bool = False
    """是否仅运行一次"""

    status: CronJobStatus = CronJobStatus.PENDING
    """当前状态"""

    last_run_at: str | None = None
    """上次运行时间"""

    next_run_time: str | None = None
    """下次运行时间"""

    last_error: str | None = None
    """上次错误信息"""

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "job_type": self.job_type.value,
            "cron_expression": self.cron_expression,
            "timezone": self.timezone,
            "payload": self.payload,
            "description": self.description,
            "enabled": self.enabled,
            "persistent": self.persistent,
            "run_once": self.run_once,
            "status": self.status.value,
            "last_run_at": self.last_run_at,
            "next_run_time": self.next_run_time,
            "last_error": self.last_error,
            "created_at": self.created_at,
        }
