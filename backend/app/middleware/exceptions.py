"""
全局异常处理 — 统一错误响应格式

功能:
- 捕获所有未处理的 HTTPException / StarletteHTTPException / 通用 Exception
- 统一返回格式: {"error": {"code": "...", "message": "...", "request_id": "..."}}
- 区分客户端错误(4xx)和服务器错误(5xx)的日志级别
- 服务器内部错误不泄露堆栈到响应体（仅记录到日志）
"""

import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("middleware.exceptions")


def _extract_request_id(request: Request) -> str:
    """安全提取 request_id"""
    return getattr(request.state, "request_id", "-")


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException,
) -> JSONResponse:
    """处理 HTTP 异常（400/401/403/404/429 等）"""
    request_id = _extract_request_id(request)
    status_code = exc.status_code

    if status_code < 500:
        logger.warning(
            "[%s] HTTP %d: %s %s — %s",
            request_id, status_code, request.method, request.url.path, exc.detail,
        )
    else:
        logger.error(
            "[%s] HTTP %d: %s %s — %s",
            request_id, status_code, request.method, request.url.path, exc.detail,
        )

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": "http_error",
                "message": str(exc.detail),
                "request_id": request_id,
            },
        },
    )


async def _validation_exception_handler(
    request: Request, exc: Exception,
) -> JSONResponse:
    """处理请求验证异常（422 Unprocessable Entity）"""
    request_id = _extract_request_id(request)

    logger.warning(
        "[%s] Validation error: %s %s — %s",
        request_id, request.method, request.url.path, str(exc),
    )

    # 提取 FastAPI RequestValidationError 的详情
    errors: list[dict[str, object]] = []
    if hasattr(exc, "errors"):
        errors = [
            {
                "field": ".".join(str(loc) for loc in e.get("loc", [])),
                "message": e.get("msg", ""),
            }
            for e in exc.errors()  # type: ignore[union-attr]
        ]

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "request_id": request_id,
                "details": errors if errors else str(exc),
            },
        },
    )


async def _generic_exception_handler(
    request: Request, exc: Exception,
) -> JSONResponse:
    """处理未预期的服务器内部错误（500）"""
    request_id = _extract_request_id(request)

    logger.exception(
        "[%s] Unhandled exception: %s %s — %s: %s",
        request_id, request.method, request.url.path,
        type(exc).__name__, str(exc),
    )

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
                "request_id": request_id,
            },
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    向 FastAPI 应用注册全局异常处理器

    优先级: StarletteHTTPException → RequestValidationError → Exception
    """
    # 标准 HTTP 异常
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)  # type: ignore[arg-type]

    # 请求验证异常 (422)
    try:
        from fastapi.exceptions import RequestValidationError  # noqa: PLC0415
        app.add_exception_handler(  # type: ignore[arg-type]
            RequestValidationError, _validation_exception_handler,
        )
    except ImportError:
        pass

    # 兜底通用异常
    app.add_exception_handler(Exception, _generic_exception_handler)  # type: ignore[arg-type]

    logger.info("Global exception handlers registered")


def register_global_middleware(app: FastAPI) -> None:
    """
    注册所有全局中间件（按正确顺序）

    中间件栈（从内到外）:
        1. RequestIDMiddleware       — 最先执行，注入 request_id
        2. RequestTimingMiddleware   — 记录 start_time
        3. AccessLogMiddleware       — 访问日志
    """
    from starlette.middleware import Middleware

    from app.middleware.request_id import RequestIDMiddleware
    from app.middleware.logging import AccessLogMiddleware, RequestTimingMiddleware

    # FastAPI add_middleware 按注册逆序执行（后注册的先执行）
    # 所以我们先注册最外层的（最后执行），再注册最内层的（最先执行）

    app.add_middleware(
        AccessLogMiddleware,
    )
    app.add_middleware(
        RequestTimingMiddleware,
    )
    app.add_middleware(
        RequestIDMiddleware,
    )

    logger.info("Global middleware stack registered (RequestID → Timing → AccessLog)")
