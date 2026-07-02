"""
结构化访问日志中间件 — 请求耗时跟踪 + 访问日志记录

功能:
- AccessLogMiddleware: 记录每个请求的 method / path / status / duration / request_id
- RequestTimingMiddleware: 在 request.state 上挂载 start_time，供下游计算耗时
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import record_http_request, http_requests_in_progress

logger = logging.getLogger("middleware.access")

# 避免记录到日志中的敏感路径
_EXCLUDED_PATHS: frozenset[str] = frozenset({
    "/api/v1/system/health",
    "/metrics",
})


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """
    请求计时中间件

    在 request.state.start_time 记录请求到达时间，供下游（如 Metrics）计算耗时。
    不记录日志，仅注入时间戳。
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        http_requests_in_progress.inc()
        request.state.start_time = time.monotonic()
        try:
            return await call_next(request)
        finally:
            http_requests_in_progress.dec()


class AccessLogMiddleware(BaseHTTPMiddleware):
    """
    结构化访问日志中间件

    在每个请求完成后记录:
        [request_id] METHOD /path → STATUS (耗时ms)

    跳过健康检查和 metrics 端点以减少日志噪音。
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        # 跳过排除的路径
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        request_id = getattr(request.state, "request_id", "-")
        start_time = getattr(request.state, "start_time", time.monotonic())

        response = await call_next(request)

        elapsed_ms = (time.monotonic() - start_time) * 1000
        duration_s = elapsed_ms / 1000.0

        # 记录 Prometheus 指标
        try:
            record_http_request(
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration=duration_s,
            )
        except Exception:
            pass

        logger.info(
            "[%s] %s %s → %d (%.1fms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        return response
