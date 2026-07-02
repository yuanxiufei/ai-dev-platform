"""
Prometheus 指标导出 — 请求 / 模型调用 / 系统指标

功能:
- HTTP 请求计数 + 延迟直方图
- 模型调用计数 + 延迟（按 provider + model_name）
- 暴露 /metrics 端点供 Prometheus 抓取
- 可选启用（METRICS_ENABLED 配置）

使用:
    from app.core.metrics import (
        http_requests_total,
        http_request_duration_seconds,
        model_calls_total,
        record_http_request,
        record_model_call,
    )
"""

import logging
import time
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("metrics")

_metrics_enabled: bool = False
_prometheus_available: bool = False

# ── NoOp 回退类 (无论 prometheus 是否安装都可用) ─────

class _NoopMetric:
    def labels(self, **kwargs: object) -> "_NoopMetric":
        return self
    def inc(self, amount: float = 1) -> None:
        pass
    def observe(self, amount: float) -> None:
        pass
    def set(self, value: float) -> None:
        pass
    def dec(self, amount: float = 1) -> None:
        pass

# 延迟导入 prometheus_client（可选依赖）
try:
    from prometheus_client import (  # type: ignore[import-untyped]
        CONTENT_TYPE_LATEST,
        REGISTRY,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )
    _prometheus_available = True
except ImportError:
    Counter = _NoopMetric  # type: ignore[misc,assignment]
    Gauge = _NoopMetric  # type: ignore[misc,assignment]
    Histogram = _NoopMetric  # type: ignore[misc,assignment]
    REGISTRY = None  # type: ignore[assignment,misc]
    CONTENT_TYPE_LATEST = "text/plain"
    generate_latest = lambda: b"# prometheus_client not installed\n"  # type: ignore[assignment]

_noop_metric = _NoopMetric()


# ── HTTP 指标 ───────────────────────────────────────

http_requests_total: "Counter" = _noop_metric  # type: ignore[assignment]
http_request_duration_seconds: "Histogram" = _noop_metric  # type: ignore[assignment]
http_requests_in_progress: "Gauge" = _noop_metric  # type: ignore[assignment]

# ── 模型调用指标 ─────────────────────────────────────

model_calls_total: "Counter" = _noop_metric  # type: ignore[assignment]
model_call_duration_seconds: "Histogram" = _noop_metric  # type: ignore[assignment]
model_call_errors_total: "Counter" = _noop_metric  # type: ignore[assignment]

# ── 系统指标 ─────────────────────────────────────────

active_tasks_gauge: "Gauge" = _noop_metric  # type: ignore[assignment]
memory_usage_gauge: "Gauge" = _noop_metric  # type: ignore[assignment]

# ── 容器健康指标 ──────────────────────────────────────

container_health_gauge: "Gauge" = _noop_metric  # type: ignore[assignment]


def init_metrics() -> None:
    """初始化 Prometheus 指标（可选启用）"""
    global _metrics_enabled
    global http_requests_total, http_request_duration_seconds, http_requests_in_progress
    global model_calls_total, model_call_duration_seconds, model_call_errors_total
    global active_tasks_gauge, memory_usage_gauge
    global container_health_gauge

    enabled = getattr(settings, "METRICS_ENABLED", True)

    if not enabled:
        logger.info("Metrics disabled by config (METRICS_ENABLED=false)")
        return

    if not _prometheus_available:
        logger.info("prometheus-client not installed, metrics disabled")
        return

    _metrics_enabled = True

    # HTTP 指标
    http_requests_total = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "path", "status"],
    )
    http_request_duration_seconds = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "path"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    )
    http_requests_in_progress = Gauge(
        "http_requests_in_progress",
        "HTTP requests currently in progress",
    )

    # 模型调用指标
    model_calls_total = Counter(
        "model_calls_total",
        "Total model API calls",
        ["provider", "model_name", "capability"],
    )
    model_call_duration_seconds = Histogram(
        "model_call_duration_seconds",
        "Model call duration in seconds",
        ["provider", "model_name"],
        buckets=(0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300),
    )
    model_call_errors_total = Counter(
        "model_call_errors_total",
        "Total model call errors",
        ["provider", "model_name", "error_type"],
    )

    # 系统指标
    active_tasks_gauge = Gauge(
        "active_tasks_total",
        "Currently active background tasks",
    )
    memory_usage_gauge = Gauge(
        "memory_usage_bytes",
        "Process memory usage in bytes",
    )

    # 容器健康指标
    container_health_gauge = Gauge(
        "container_health_status",
        "Docker container health status (1=healthy, 0=unhealthy)",
        ["container"],
    )

    logger.info("Prometheus metrics initialized")


def is_metrics_enabled() -> bool:
    """检查指标是否已启用"""
    return _metrics_enabled


def record_http_request(method: str, path: str, status: int, duration: float) -> None:
    """记录 HTTP 请求指标"""
    if not _metrics_enabled:
        return
    try:
        http_requests_total.labels(method=method, path=path, status=str(status)).inc()
        http_request_duration_seconds.labels(method=method, path=path).observe(duration)
    except Exception:
        pass


def record_model_call(
    provider: str,
    model_name: str,
    capability: str,
    duration: float,
    error: Optional[str] = None,
) -> None:
    """记录模型调用指标"""
    if not _metrics_enabled:
        return
    try:
        model_calls_total.labels(
            provider=provider, model_name=model_name, capability=capability,
        ).inc()
        model_call_duration_seconds.labels(
            provider=provider, model_name=model_name,
        ).observe(duration)
        if error:
            model_call_errors_total.labels(
                provider=provider, model_name=model_name, error_type=error,
            ).inc()
    except Exception:
        pass


def update_container_health(container: str, healthy: bool) -> None:
    """更新容器健康状态 (1=healthy, 0=unhealthy)"""
    if not _metrics_enabled:
        return
    try:
        container_health_gauge.labels(container=container).set(1 if healthy else 0)
    except Exception:
        pass


def update_system_gauges() -> None:
    """更新系统资源 gauge (内存/tasks)"""
    if not _metrics_enabled:
        return
    try:
        import os
        import threading

        import psutil
        proc = psutil.Process(os.getpid())
        mem = proc.memory_info()
        memory_usage_gauge.set(mem.rss)
        active_tasks_gauge.set(threading.active_count())
    except Exception:
        pass
