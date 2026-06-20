"""
X-Request-ID 中间件 — 全链路请求追踪

功能:
- 从请求头 X-Request-ID 提取（上游传入），若无则自动生成 UUID7
- 注入到 request.state.request_id 供下游使用
- 响应头 X-Request-ID 回传，确保链路可追溯
- 通过 contextvars 支持异步上下文传播（无需显式传参）
"""

import logging
import uuid

from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("middleware.request_id")

# 跨异步上下文传播的请求 ID
_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """获取当前异步上下文中的请求 ID（供任意深层代码调用）"""
    return _request_id_var.get()


def generate_request_id() -> str:
    """生成 UUID7 格式的请求 ID（时间排序 + 唯一性）"""
    return str(uuid.uuid4()).replace("-", "")[:16]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    X-Request-ID 中间件

    优先级: 最高（应在管道最内层，确保所有下游都能获取 request_id）
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint,
    ) -> Response:
        # 优先使用上游传入的 request_id，否则自动生成
        request_id = request.headers.get("X-Request-ID", generate_request_id())

        # 注入到请求状态 + contextvar
        request.state.request_id = request_id
        token = _request_id_var.set(request_id)

        try:
            response = await call_next(request)
        except Exception:
            # 即使异常也回传 request_id 便于排查
            _request_id_var.reset(token)
            raise

        _request_id_var.reset(token)

        # 响应头回传
        response.headers["X-Request-ID"] = request_id
        return response
