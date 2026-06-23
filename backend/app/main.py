import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# 将项目根目录加入 sys.path，确保 ai_models 包可导入
# main.py → app/ → backend/ → 项目根目录 (ai-fullstack-platform/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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
            build_local_model_adapters,
            build_api_model_adapters,
            ModelCapability,
        )
        from app.core.api_gateway import get_api_gateway

        gateway = get_api_gateway()
        local_models = build_local_model_adapters()
        api_models = build_api_model_adapters(api_gateway=gateway)
        init_model_router(
            local_models=local_models,
            api_gateway=gateway,
            fallback_model=None,  # 自动创建内置兜底
            api_models=api_models,
        )
        logger.info("ModelRouter initialized with %d local + %d API models", len(local_models), len(api_models))
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

    # 初始化 Agent 系统（ToolRegistry + MCP）
    try:
        from app.core.tools.registry import init_tool_registry, get_tool_registry

        registry = init_tool_registry()

        # 自动注册内置工具
        import app.core.tools.builtin  # noqa: F401 — 触发 @register_tool 装饰器

        logger.info("ToolRegistry initialized (%d tools)", registry.count)

        # 加载 MCP 服务器配置
        import json as _json
        mcp_configs = _json.loads(settings.MCP_SERVERS or "[]")
        if mcp_configs:
            from app.core.mcp import MCPManager, MCPServerConfig, MCPTransport

            transport_map = {
                "sse": MCPTransport.SSE,
                "stdio": MCPTransport.STDIO,
                "streamable_http": MCPTransport.STREAMABLE_HTTP,
            }

            manager = MCPManager()
            for srv in mcp_configs:
                transport = transport_map.get(srv.get("transport", "sse"), MCPTransport.SSE)
                config = MCPServerConfig(
                    name=srv.get("name", ""),
                    transport=transport,
                    url=srv.get("url", ""),
                    command=srv.get("command", ""),
                    args=srv.get("args", []),
                    env=srv.get("env", {}),
                    tool_prefix=srv.get("tool_prefix", ""),
                    headers=srv.get("headers", {}),
                    auto_discover=srv.get("auto_discover", True),
                    timeout_seconds=srv.get("timeout", 30.0),
                )
                manager.add_server(config)

            result = await manager.connect_all()
            logger.info(
                "MCP Manager: %d/%d servers connected, %d tools discovered",
                result.connected, result.total_servers, result.tools_discovered,
            )

            if result.connected > 0:
                await manager.register_to_toolset()
    except Exception as e:
        logger.warning("Agent system init skipped: %s", e)

    # 初始化 Worktree 管理器（Git Worktree 并行开发环境 — 借鉴 Roo Code）
    try:
        from app.core.agent.worktree import init_worktree_manager, WorktreeConfig

        wt_config = WorktreeConfig(
            repo_root=os.getcwd(),
            worktrees_dir=os.getenv("WORKTREES_DIR", ".worktrees"),
            max_active_worktrees=int(os.getenv("MAX_ACTIVE_WORKTREES", "5")),
            auto_cleanup_minutes=int(os.getenv("WORKTREE_AUTO_CLEANUP_MINUTES", "60")),
        )
        wt_mgr = init_worktree_manager(wt_config)
        wt_list = await wt_mgr.list_worktrees()
        logger.info(
            "WorktreeManager initialized: %d worktrees (max: %d)",
            len(wt_list), wt_config.max_active_worktrees,
        )
    except Exception as e:
        logger.warning("WorktreeManager init skipped: %s", e)

    # 初始化 Code Completion 引擎（FIM 补全 + 上下文感知 — 借鉴 Continue）
    try:
        from app.core.tools.code_completion import init_completion_engine, register_code_completion_tools

        engine = init_completion_engine()
        register_code_completion_tools()
        logger.info("CodeCompletion engine initialized (FIM + ContextAssembler + Ranker + Cache)")
    except Exception as e:
        logger.warning("CodeCompletion engine init skipped: %s", e)

    # 初始化 Memory 核心层（向量化长期记忆 — 借鉴 Open WebUI Memory）
    try:
        from app.core.memory import init_memory_store, init_embedding_service

        emb_svc = init_embedding_service()
        mem_store = init_memory_store()
        logger.info(
            "MemoryStore initialized (provider=%s, dim=%d)",
            emb_svc.provider_name, emb_svc.dim,
        )
    except Exception as e:
        logger.warning("MemoryStore init skipped: %s", e)

    # 初始化 Reflection 管理器（LLM 自省/反思 — 借鉴 Trae Agent reflect）
    try:
        from app.core.agent.reflection import init_reflection_manager, ReflectionConfig

        reflect_cfg = ReflectionConfig(
            enabled=os.getenv("REFLECTION_ENABLED", "true").lower() == "true",
            reflect_on_error=os.getenv("REFLECTION_ON_ERROR", "true").lower() == "true",
            save_to_memory=os.getenv("REFLECTION_SAVE_TO_MEMORY", "true").lower() == "true",
        )
        reflect_mgr = init_reflection_manager(reflect_cfg)
        logger.info(
            "ReflectionManager initialized (enabled=%s, on_error=%s)",
            reflect_cfg.enabled, reflect_cfg.reflect_on_error,
        )
    except Exception as e:
        logger.warning("ReflectionManager init skipped: %s", e)

    # ═══ P1: Redis 分布式缓存 —————————————————————
    try:
        from app.core.cache import init_redis_client, init_rate_limiter, init_cache_manager

        redis = await init_redis_client()
        if redis:
            limit = init_rate_limiter(
                window_seconds=settings.REDIS_RATE_LIMIT_WINDOW,
                max_requests=settings.REDIS_RATE_LIMIT_PER_IP,
            )
            logger.info("DistributedRateLimiter initialized (redis, window=%ds, max=%d)",
                        settings.REDIS_RATE_LIMIT_WINDOW, settings.REDIS_RATE_LIMIT_PER_IP)
        else:
            limit = init_rate_limiter(
                window_seconds=settings.REDIS_RATE_LIMIT_WINDOW,
                max_requests=settings.REDIS_RATE_LIMIT_PER_IP,
            )
            logger.info("DistributedRateLimiter initialized (in-memory fallback)")

        cache_mgr = init_cache_manager()
        logger.info("CacheManager initialized")
    except Exception as e:
        logger.warning("Redis/Cache init skipped: %s", e)

    # ═══ P2: Celery 任务队列 ———————————————————————
    try:
        from app.core.task_queue import celery_app as _celery_app  # noqa: F401
        logger.info("Celery task queue initialized")
    except Exception as e:
        logger.warning("Task queue init skipped: %s", e)

    # ═══ P3: Prometheus Metrics ———————————————————
    try:
        from app.core.metrics import init_metrics
        init_metrics()
    except Exception as e:
        logger.warning("Metrics init skipped: %s", e)

    # ═══ GPU 控制层 (P2) —————————————————————————
    try:
        from app.core.gpu import init_gpu_detector, init_gpu_allocator, init_gpu_monitor
        if settings.GPU_ENABLED:
            detector = init_gpu_detector()
            devices = detector.detect_all()
            logger.info("GPU Detector initialized (%d GPU(s) found)", len(devices))
            allocator = init_gpu_allocator()
            allocator.refresh_devices()
            logger.info("GPU Allocator initialized (%d GPU(s), %d MB VRAM)",
                        allocator.total_gpu_count, allocator.total_vram_mb)
            monitor = init_gpu_monitor(interval_seconds=settings.GPU_MONITOR_INTERVAL)
            await monitor.start()
            logger.info("GPU Monitor started (interval=%ss)", settings.GPU_MONITOR_INTERVAL)
    except Exception as e:
        logger.warning("GPU layer init skipped: %s", e)

    # ═══ 系统资源采集器 (P2) —————————————————————
    try:
        from app.core.resources import init_resource_collector
        if settings.RESOURCE_COLLECTOR_ENABLED:
            collector = init_resource_collector(
                interval_seconds=settings.RESOURCE_COLLECTOR_INTERVAL,
            )
            await collector.start()
            logger.info("ResourceCollector started (interval=%ss)",
                        settings.RESOURCE_COLLECTOR_INTERVAL)
    except Exception as e:
        logger.warning("ResourceCollector init skipped: %s", e)

    # ═══ 模型目录 (P2) ———————————————————————————
    try:
        from app.core.catalog import init_catalog
        if settings.CATALOG_ENABLED:
            catalog = init_catalog(
                catalog_file=settings.CATALOG_FILE if settings.CATALOG_FILE else None,
            )
            logger.info("Model Catalog initialized (%d model sets)", len(catalog.model_sets))
    except Exception as e:
        logger.warning("Model Catalog init skipped: %s", e)

    # ═══ Auth 增强 (P2) ——————————————————————————
    try:
        from app.core.auth import init_api_key_manager, init_refresh_token_manager
        api_key_mgr = init_api_key_manager()
        logger.info("ApiKeyManager initialized")
        refresh_mgr = init_refresh_token_manager(
            ttl_seconds=settings.REFRESH_TOKEN_TTL_HOURS * 3600,
        )
        logger.info("RefreshTokenManager initialized (ttl=%dh)", settings.REFRESH_TOKEN_TTL_HOURS)
    except Exception as e:
        logger.warning("Auth enhancement init skipped: %s", e)

    # ═══ 远程代理 (P2) ———————————————————————————
    try:
        from app.core.remote import (
            init_remote_session_manager,
            init_port_forward_manager,
            init_workspace_trust_manager,
        )
        if settings.REMOTE_AGENT_ENABLED:
            session_mgr = init_remote_session_manager()
            logger.info("RemoteSessionManager initialized")
        if settings.PORT_FORWARD_ENABLED:
            pf_mgr = init_port_forward_manager(
                port_range_start=settings.PORT_FORWARD_RANGE_START,
                port_range_end=settings.PORT_FORWARD_RANGE_END,
            )
            logger.info("PortForwardManager initialized (range=%d-%d)",
                        settings.PORT_FORWARD_RANGE_START,
                        settings.PORT_FORWARD_RANGE_END)
        if settings.WORKSPACE_TRUST_ENABLED:
            trust_mgr = init_workspace_trust_manager()
            logger.info("WorkspaceTrustManager initialized")
    except Exception as e:
        logger.warning("Remote agent init skipped: %s", e)

    # ═══ EventBus 分布式协调 (P2) ————————————————
    try:
        from app.core.event_coordinator import create_coordinator
        coordinator = create_coordinator(
            coordinator_type=settings.EVENT_COORDINATOR_TYPE,
            redis_url=settings.EVENT_COORDINATOR_REDIS_URL,
        )
        await coordinator.start()
        from app.core.event_bus import get_event_bus
        bus = get_event_bus()
        if bus:
            bus.set_coordinator(coordinator)
            logger.info("EventBus distributed coordinator set (%s)",
                        settings.EVENT_COORDINATOR_TYPE)
    except Exception as e:
        logger.warning("EventBus coordinator init skipped: %s", e)

    # ═══ 配置热加载 (P2) ———————————————————————
    try:
        from app.core.config_reloader import init_config_reloader
        if settings.CONFIG_WATCH_ENABLED:
            def _reload_providers_on_env_change() -> None:
                """.env 变更后刷新 Provider 密钥/端点"""
                gw = get_api_gateway()
                if gw and hasattr(gw, '_registry'):
                    gw._registry.force_reload()

            reloader = init_config_reloader(
                env_file=".env",
                watch_interval=settings.CONFIG_WATCH_INTERVAL,
                auto_watch=True,
            )
            reloader.on_reload(_reload_providers_on_env_change)
            logger.info("ConfigReloader started (interval=%ss)", settings.CONFIG_WATCH_INTERVAL)
    except Exception as e:
        logger.warning("ConfigReloader init skipped: %s", e)

    # ═══ PTY 终端后端 (P2) ————————————————————
    try:
        from app.core.terminal import init_pty_backend
        if settings.TERMINAL_ENABLED:
            init_pty_backend()
            logger.info("PTY Backend initialized")
    except Exception as e:
        logger.warning("PTY Backend init skipped: %s", e)

    # ═══ Benchmark 引擎 (P2) ———————————————————
    try:
        from app.core.benchmark import init_benchmark_engine
        if settings.BENCHMARK_ENABLED:
            init_benchmark_engine(
                max_concurrent=settings.BENCHMARK_MAX_CONCURRENT,
            )
            logger.info("Benchmark Engine initialized (max_concurrent=%d)",
                        settings.BENCHMARK_MAX_CONCURRENT)
    except Exception as e:
        logger.warning("Benchmark Engine init skipped: %s", e)

    # ═══ 统一存储管理 (P2) —————————————————————
    try:
        from app.core.storage import init_storage_manager
        init_storage_manager(
            storage_root=settings.STORAGE_ROOT,
            max_storage_gb=settings.STORAGE_MAX_GB,
            max_workspace_gb=settings.STORAGE_MAX_WORKSPACE_GB,
            models_dir=settings.MODELS_DIR,
            data_dir=os.path.join(settings.STORAGE_ROOT, "data") if settings.STORAGE_ROOT else "data",
        )
        logger.info("StorageManager initialized (root=%s, max=%dGB)",
                     settings.STORAGE_ROOT, settings.STORAGE_MAX_GB)
    except Exception as e:
        logger.warning("StorageManager init skipped: %s", e)

    # ═══ Checkpoint 检查点系统 (P2) —————————————
    try:
        from app.core.checkpoint import init_checkpoint_manager
        if settings.CHECKPOINT_ENABLED:
            init_checkpoint_manager(
                repo_path=os.getcwd(),
                max_checkpoints=settings.CHECKPOINT_MAX_COUNT,
            )
            logger.info("CheckpointManager initialized (max=%d)", settings.CHECKPOINT_MAX_COUNT)
    except Exception as e:
        logger.warning("CheckpointManager init skipped: %s", e)

    # ═══ Guardrails 护栏系统 (P2) ———————————————
    try:
        from app.core.guardrails import init_guardrails
        if settings.GUARDRAILS_ENABLED:
            init_guardrails()
            logger.info("GuardrailsManager initialized")
    except Exception as e:
        logger.warning("GuardrailsManager init skipped: %s", e)

    # ═══ Standalone 独立运行方案 —————————————————
    try:
        from app.core.standalone.manager import (
            StandaloneManager, StandaloneConfig, init_standalone_manager,
        )
        from app.core.standalone.watchdog import WatchdogConfig
        from app.core.standalone.api_auth import ApiAuthConfig
        from app.core.standalone.sleep_manager import SleepConfig

        standalone_cfg = StandaloneConfig(
            watchdog_enabled=settings.STANDALONE_WATCHDOG_ENABLED,
            api_auth_enabled=settings.STANDALONE_API_AUTH_ENABLED,
            smart_sleep_enabled=settings.STANDALONE_SMART_SLEEP_ENABLED,
            state_switch_enabled=True,
            sleep_config=SleepConfig(
                idle_timeout_seconds=settings.STANDALONE_SLEEP_IDLE_TIMEOUT,
                unload_models_on_sleep=settings.STANDALONE_SLEEP_UNLOAD_MODELS,
                reduce_cpu_priority=settings.STANDALONE_SLEEP_REDUCE_CPU_PRIORITY,
            ),
            api_auth_config=ApiAuthConfig(
                enabled=settings.STANDALONE_API_AUTH_ENABLED,
            ),
            bind_host=settings.STANDALONE_BIND_HOST,
            bind_port=settings.STANDALONE_BIND_PORT,
        )
        manager = init_standalone_manager(standalone_cfg)
        await manager.setup(app)
        await manager.startup()
        logger.info("StandaloneManager initialized and started")
    except Exception as e:
        logger.warning("StandaloneManager init skipped: %s", e)

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
    try:
        from app.core.cache import close_redis_client
        import asyncio
        asyncio.ensure_future(close_redis_client())
    except Exception:
        pass
    # Shutdown GPU monitor
    try:
        from app.core.gpu import get_gpu_monitor
        monitor = get_gpu_monitor()
        if monitor:
            await monitor.stop()
    except Exception:
        pass
    # Shutdown resource collector
    try:
        from app.core.resources import get_resource_collector
        collector = get_resource_collector()
        if collector:
            await collector.stop()
    except Exception:
        pass
    # Shutdown config reloader
    try:
        from app.core.config_reloader import get_config_reloader
        reloader = get_config_reloader()
        if reloader:
            reloader.stop_watching()
    except Exception:
        pass
    # Shutdown PTY backend
    try:
        from app.core.terminal import get_pty_backend
        backend = get_pty_backend()
        if backend:
            backend.shutdown_all()
    except Exception:
        pass
    # Shutdown StandaloneManager
    try:
        from app.core.standalone.manager import get_standalone_manager
        mgr = get_standalone_manager()
        if mgr:
            await mgr.shutdown()
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

# ── P0: 全局 HTTP 中间件注册 —————————————————————
from app.middleware import register_global_middleware, register_exception_handlers
register_global_middleware(app)
register_exception_handlers(app)

# ── Standalone 中间件: 智能休眠感知 ——————————————
# 每个 HTTP 请求都通知 SleepManager 保持活跃
if settings.STANDALONE_SMART_SLEEP_ENABLED:
    from app.core.standalone.sleep_manager import SleepAwareMiddleware, get_sleep_manager
    # 中间件会在 dispatch 时动态获取 sleep_manager 单例
    app.add_middleware(SleepAwareMiddleware, sleep_manager=None)  # None = lazy lookup

# ── Standalone 中间件: API 鉴权 ——————————————————
if settings.STANDALONE_API_AUTH_ENABLED:
    from app.core.standalone.api_auth import ApiAuthMiddleware, ApiAuthConfig
    _api_auth_config = ApiAuthConfig(
        enabled=settings.STANDALONE_API_AUTH_ENABLED,
        whitelist_paths=[
            "/api/v1/utils/health-check/",
            "/api/v1/system/health",
            "/docs",
            "/openapi.json",
            "/metrics",
            "/api/v1/standalone",  # standalone 自身管理接口
            "/api/v1/auth",  # 登录接口
            "/api/v1/agent",  # Agent 对话（前端核心功能）
            "/api/v1/plugin-marketplace",  # 插件市场（前端）
            "/api/v1/studio",  # Studio 前端路由
        ],
    )
    app.add_middleware(ApiAuthMiddleware, config=_api_auth_config)

# ── P3: Prometheus /metrics 端点 ——————————————————
from app.core.metrics import is_metrics_enabled as _metrics_enabled
if _metrics_enabled():
    from app.core.metrics import generate_latest, CONTENT_TYPE_LATEST
    from starlette.responses import Response

    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

app.include_router(api_router, prefix=settings.API_V1_STR)



