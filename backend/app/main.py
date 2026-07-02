import asyncio
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


def _register_native_codebase_tools() -> int:
    """将原生 Codebase Memory 工具注册到平台 ToolRegistry"""
    from app.core.codebase_memory.tools import TOOL_REGISTRY, call_tool
    from app.core.tools.registry import get_tool_registry
    from app.core.tools.schema import FunctionTool, ToolSchema, ToolParam, ParamType

    registry = get_tool_registry()

    tool_defs = [
        {
            "name": "cbm_search_graph",
            "desc": "搜索代码知识图谱，查找函数、类、路由和变量。用于代替 grep/glob 发现代码定义和关系。",
            "params": [
                ToolParam(name="query", type=ParamType.STRING, description="搜索查询关键词"),
                ToolParam(name="project", type=ParamType.STRING, description="项目名称", required=False),
                ToolParam(name="limit", type=ParamType.INTEGER, description="最大结果数", required=False, default=20),
            ],
            "tool_name": "search_graph",
        },
        {
            "name": "cbm_search_code",
            "desc": "图增强代码搜索，按模式搜索代码内容并按结构重要性排序。",
            "params": [
                ToolParam(name="pattern", type=ParamType.STRING, description="搜索模式"),
                ToolParam(name="project", type=ParamType.STRING, description="项目名称", required=False),
                ToolParam(name="limit", type=ParamType.INTEGER, description="最大结果数", required=False, default=20),
            ],
            "tool_name": "search_code",
        },
        {
            "name": "cbm_get_code_snippet",
            "desc": "获取函数/类/符号的源代码。先调用 search_graph 找到准确名称再传入。",
            "params": [
                ToolParam(name="qualified_name", type=ParamType.STRING, description="函数/类的限定名称"),
                ToolParam(name="project", type=ParamType.STRING, description="项目名称", required=False),
            ],
            "tool_name": "get_code_snippet",
        },
        {
            "name": "cbm_get_architecture",
            "desc": "获取项目架构总览 — 包、服务、依赖关系和项目结构。",
            "params": [
                ToolParam(name="project", type=ParamType.STRING, description="项目名称", required=False),
            ],
            "tool_name": "get_architecture",
        },
        {
            "name": "cbm_trace_path",
            "desc": "追踪代码调用链路径。用于调用者/被调用者分析、影响力分析和数据流追踪。",
            "params": [
                ToolParam(name="function_name", type=ParamType.STRING, description="函数名称"),
                ToolParam(name="project", type=ParamType.STRING, description="项目名称", required=False),
                ToolParam(name="direction", type=ParamType.STRING, description="追踪方向", required=False, enum=["inbound", "outbound", "both"]),
                ToolParam(name="depth", type=ParamType.INTEGER, description="追踪深度", required=False, default=3),
            ],
            "tool_name": "trace_path",
        },
        {
            "name": "cbm_index_repository",
            "desc": "将仓库索引到知识图谱中。",
            "params": [
                ToolParam(name="repo_path", type=ParamType.STRING, description="仓库路径"),
            ],
            "tool_name": "index_repository",
        },
        {
            "name": "cbm_list_projects",
            "desc": "列出所有已索引的项目。",
            "params": [],
            "tool_name": "list_projects",
        },
        {
            "name": "cbm_index_status",
            "desc": "获取项目的索引状态。",
            "params": [
                ToolParam(name="project", type=ParamType.STRING, description="项目名称", required=False),
            ],
            "tool_name": "index_status",
        },
    ]

    count = 0
    for td in tool_defs:
        tool_name = td["tool_name"]

        def make_handler(tn):
            async def handler(**kwargs):
                return call_tool(tn, kwargs)
            return handler

        tool = FunctionTool(
            schema=ToolSchema(
                name=td["name"],
                description=td["desc"],
                parameters=td["params"],
                category="code",
            ),
            func=make_handler(tool_name),
        )
        registry.register_sync(tool)
        count += 1

    return count


def custom_generate_unique_id(route: APIRoute) -> str:
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    return route.name


_bg_tasks: set[asyncio.Task] = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global _bg_tasks
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

    # 初始化数据库 + 创建初始超级用户
    try:
        from app.core.db import engine, init_db
        from sqlmodel import Session

        with Session(engine) as session:
            init_db(session)
        logger.info("Database initialized (tables created + first superuser)")
    except Exception as e:
        logger.warning("Database init skipped: %s", e)
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

        # 🆕 模型健康检查器（借鉴 Agent-Reach Channel.check() 设计）
        try:
            from app.core.agent.model_health import (
                init_model_health, MonitoredModel,
            )
            monitored = []
            for adapter in local_models + api_models:
                monitored.append(MonitoredModel(
                    name=getattr(adapter, "name", "unknown"),
                    provider=getattr(adapter, "provider", "unknown"),
                    api_model_id=getattr(adapter, "api_model_id", ""),
                    priority=getattr(adapter, "priority", 50),
                    model_adapter=adapter,
                ))
            health_checker = init_model_health(
                monitored_models=monitored,
                auto_start=True,
                interval=120.0,  # 每 2 分钟探测一次
            )
            logger.info("ModelHealthChecker started (interval=120s, %d models)", len(monitored))
        except Exception as e:
            logger.warning("ModelHealthChecker init skipped: %s", e)

        # 🆕 Session 树 + 检查点系统（借鉴 hermes-agent，持久化到 MemoryStore + StorageManager）
        try:
            from app.core.agent.session_tree import init_session_tree
            from app.core.memory.memory_store import get_memory_store
            from app.core.storage import get_storage_manager

            session_data_dir = os.path.join(settings.STORAGE_ROOT, "data") if settings.STORAGE_ROOT else "data"
            init_session_tree(
                max_nodes=settings.SESSION_TREE_MAX_NODES if hasattr(settings, "SESSION_TREE_MAX_NODES") else 100,
                data_dir=session_data_dir,
                memory_store=get_memory_store(),
                storage_manager=get_storage_manager(),
            )
            logger.info("SessionTree initialized on MemoryStore (max_nodes=%d, data_dir=%s)", 
                        settings.SESSION_TREE_MAX_NODES if hasattr(settings, "SESSION_TREE_MAX_NODES") else 100,
                        session_data_dir)
        except Exception as e:
            logger.warning("SessionTree init skipped: %s", e)

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

        # 初始化 Skills 技能系统
        try:
            from app.core.skills_manager import init_skills
            init_skills("skills")
            logger.info("SkillsManager initialized")

            # 启动技能热加载监听 (P1.6)
            from app.core.skills.skill_manager import SkillManager, init_skill_watcher
            mgr = SkillManager("skills")
            init_skill_watcher(mgr, poll_interval=5.0, auto_watch=True)
            logger.info("SkillWatcher started (hot-reload enabled)")
        except Exception as e:
            logger.warning("SkillsManager init skipped: %s", e)

        # 初始化原生 Codebase Memory（代码库知识图谱）
        try:
            from app.core.codebase_memory import init_codebase_memory
            cbm_result = init_codebase_memory()
            if cbm_result:
                # 旧版工具注册（cbm_ 前缀，向后兼容）
                legacy_count = _register_native_codebase_tools()
                # 新版工具注册（原始名称，供 Agent Function Calling 使用）
                from app.core.codebase_memory.tools import init_codebase_tools_to_global_registry
                global_count = init_codebase_tools_to_global_registry()
                logger.info(
                    "Codebase Memory: %d nodes, %d edges, %d legacy + %d global tools registered",
                    cbm_result.get("nodes", 0),
                    cbm_result.get("edges", 0),
                    legacy_count,
                    global_count,
                )
        except Exception as e:
            logger.debug("Codebase Memory init skipped: %s", e)

        # 启动 Git 增量索引 (P1.5) — 依赖 Codebase Memory 就绪
        if cbm_result:
            try:
                from app.core.codebase_memory.indexer import _indexers, GitIndexer
                for _path, idx in _indexers.items():
                    git_idx = GitIndexer(idx, poll_interval=60.0)
                    git_idx.start_watching()
                    logger.info("GitIndexer started for '%s' (poll=60s)", idx.project_name)
            except Exception as e:
                logger.debug("GitIndexer init skipped: %s", e)

        # 加载外部 MCP 服务器配置
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

    # 初始化平台消息历史 & 对话管理器（SQLite 持久化，防重启丢数据）
    try:
        from app.core.message_history import init_message_history_manager
        msg_hist_mgr = init_message_history_manager(use_sqlite=True)
        logger.info("PlatformMessageHistoryManager initialized (SQLite: data/messages.db)")
    except Exception as e:
        logger.warning("MessageHistoryManager init skipped: %s", e)

    try:
        from app.core.conversation.manager import init_conversation_manager
        conv_mgr = init_conversation_manager(use_sqlite=True)
        logger.info("ConversationManager initialized (SQLite: data/conversations.db)")
    except Exception as e:
        logger.warning("ConversationManager init skipped: %s", e)

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
        from app.core.metrics import update_system_gauges as _update_sys_gauges
        async def _metrics_updater():
            while True:
                try:
                    _update_sys_gauges()
                except Exception:
                    pass
                await asyncio.sleep(15)
        task = asyncio.create_task(_metrics_updater())
        _bg_tasks.add(task)
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
    # 取消后台指标更新任务
    for task in _bg_tasks:
        task.cancel()
    try:
        from app.core.api_gateway import get_api_gateway

        gateway = get_api_gateway()
        import asyncio
        asyncio.ensure_future(gateway.close())
    except Exception:
        logger.warning("Failed to shutdown API Gateway", exc_info=True)
    try:
        from app.core.cache import close_redis_client
        import asyncio
        asyncio.ensure_future(close_redis_client())
    except Exception:
        logger.warning("Failed to shutdown Redis client", exc_info=True)
    # Shutdown GPU monitor
    try:
        from app.core.gpu import get_gpu_monitor
        monitor = get_gpu_monitor()
        if monitor:
            await monitor.stop()
    except Exception:
        logger.warning("Failed to shutdown GPU monitor", exc_info=True)
    # Shutdown resource collector
    try:
        from app.core.resources import get_resource_collector
        collector = get_resource_collector()
        if collector:
            await collector.stop()
    except Exception:
        logger.warning("Failed to shutdown resource collector", exc_info=True)
    # Shutdown config reloader
    try:
        from app.core.config_reloader import get_config_reloader
        reloader = get_config_reloader()
        if reloader:
            reloader.stop_watching()
    except Exception:
        logger.warning("Failed to shutdown config reloader", exc_info=True)
    # Shutdown PTY backend
    try:
        from app.core.terminal import get_pty_backend
        backend = get_pty_backend()
        if backend:
            backend.shutdown_all()
    except Exception:
        logger.warning("Failed to shutdown PTY backend", exc_info=True)
    # Shutdown StandaloneManager
    try:
        from app.core.standalone.manager import get_standalone_manager
        mgr = get_standalone_manager()
        if mgr:
            await mgr.shutdown()
    except Exception:
        logger.warning("Failed to shutdown StandaloneManager", exc_info=True)
    logger.info("Server stopped.")


if settings.SENTRY_DSN and settings.ENVIRONMENT != "local":
    sentry_sdk.init(dsn=str(settings.SENTRY_DSN), enable_tracing=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
)

# CORS 配置 — 注意：allow_credentials=True 时 allow_origins 不能为 ["*"]
# 若 BACKEND_CORS_ORIGINS 设为 "*"，浏览器将拒绝该 CORS 配置（违反 CORS 规范）
# 生产环境应配置具体域名而非通配符
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
# 注意：白名单包含前端核心路由（agent/studio/plugin-marketplace/auth），
# 这些路由依赖自身的 JWT 认证（deps.py get_current_user），
# 因此 Standalone API Auth 仅作为额外层，不影响 JWT 安全性。
# 若需要更严格的鉴权，应从白名单中移除不需要公共访问的路径。
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

# ── 多租户中间件 ———————————————————————————————
if settings.MULTI_TENANCY_ENABLED:
    from app.middleware.tenant import TenantMiddleware, get_tenant_id
    app.add_middleware(TenantMiddleware)

# ── P3: Prometheus /metrics 端点 ——————————————————
from app.core.metrics import is_metrics_enabled as _metrics_enabled
from app.core.metrics import generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import Response


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint() -> Response:
    if not _metrics_enabled():
        return Response(
            content=b"# Metrics not enabled\n",
            media_type="text/plain",
            status_code=503,
        )
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

app.include_router(api_router, prefix=settings.API_V1_STR)



