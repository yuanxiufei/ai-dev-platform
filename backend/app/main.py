import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings

logger = logging.getLogger("app.main")


def custom_generate_unique_id(route: APIRoute) -> str:
    return f"{route.tags[0]}-{route.name}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # ═══ STARTUP ═══
    logger.info("=" * 60)
    logger.info(f"Starting {settings.PROJECT_NAME}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info("=" * 60)

    # 初始化 API 网关
    try:
        from app.core.api_gateway import init_api_gateway, get_api_gateway

        gateway = init_api_gateway()
        providers = gateway.list_providers()
        configured = sum(1 for p in providers if p.get("is_configured"))
        logger.info(
            "API Gateway initialized: %d/%d providers configured",
            configured,
            len(providers),
        )
    except Exception as e:
        logger.warning("API Gateway init skipped: %s", e)

    # 初始化模型下载管理器
    try:
        from app.core.model_downloader import init_downloader

        downloader = init_downloader(models_dir=settings.MODELS_DIR)
        models_available = len(downloader.get_model_list())
        logger.info("ModelDownloader initialized: %d models available", models_available)
    except Exception as e:
        logger.warning("ModelDownloader init skipped: %s", e)

    # 初始化模型调度器
    try:
        from ai_models.scheduler import get_scheduler
        from ai_models.registry import get_all_local_configs

        scheduler = get_scheduler()
        local_models = get_all_local_configs()
        for name, config in local_models.items():
            scheduler.register_model(
                model_name=name,
                base_priority=config.priority,
                capabilities=[config.model_type.value],
            )
        logger.info("Model Scheduler initialized: %d local models", len(local_models))
    except Exception as e:
        logger.warning("Scheduler init skipped: %s", e)

    # 初始化全局模型路由器
    try:
        from app.core.model_router import (
            init_model_router,
            ModelCapability,
        )
        from app.core.api_gateway import get_api_gateway

        gateway = get_api_gateway()
        init_model_router(
            local_models=[],  # 后续从 ai_models 层注入
            api_gateway=gateway,
            fallback_model=None,  # 自动创建内置兜底
        )
        logger.info("ModelRouter initialized")
    except Exception as e:
        logger.warning("ModelRouter init skipped: %s", e)

    # 初始化自动优化器
    try:
        from ai_models.optimizer import init_optimizer
        from ai_models.scheduler import get_scheduler

        opt = init_optimizer(scheduler=get_scheduler())
        logger.info("AutoOptimizer initialized")
    except Exception as e:
        logger.warning("AutoOptimizer init skipped: %s", e)

    logger.info("✓ All components initialized. Server ready.")
    yield
    # ═══ SHUTDOWN ═══
    logger.info("Shutting down...")
    try:
        from app.core.api_gateway import get_api_gateway

        gateway = get_api_gateway()
        import asyncio
        asyncio.ensure_future(gateway.close())
    except Exception:
        pass
    logger.info("Server stopped.")


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(api_router, prefix=settings.API_V1_STR)
