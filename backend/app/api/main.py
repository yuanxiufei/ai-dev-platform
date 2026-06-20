from fastapi import APIRouter

from app.api.routes.auth.login import router as login_router
from app.api.routes.auth.users import router as users_router
from app.api.routes.common.utils import router as utils_router
from app.api.routes.video import (
    admin_videos_router,
    analytics_router,
    browse_router,
    generate_router,
    moderation_router,
    play_router,
)
from app.api.routes.studio import (
    chat_router,
    models_router,
    projects_router,
    sessions_router,
    templates_router,
)
from app.api.routes.system import (
    models_router as system_models_router,
    health_router as system_health_router,
    gpu_router as system_gpu_router,
    resources_router as system_resources_router,
    catalog_router as system_catalog_router,
    remote_router as system_remote_router,
    terminal_router as system_terminal_router,
    benchmarks_router as system_benchmarks_router,
    config_router as system_config_router,
    storage_router as system_storage_router,
    checkpoints_router as system_checkpoints_router,
    guardrails_router as system_guardrails_router,
)
from app.api.routes.system.task_queue import router as task_queue_router
from app.api.routes.agent import (
    agent_chat_router,
    agent_tools_router,
    agent_mcp_router,
    agent_mcp_marketplace_router,
    plugin_marketplace_router,
    model_presets_router,
    model_arena_router,
    analytics_router as agent_analytics_router,
    memory_router,
    structured_output_router,
    image_gen_router,
    voice_router,
    webhooks_router,
    skills_router,
    prompt_templates_router,
    tasks_router,
    openapi_discovery_router,
    knowledge_graph_router,
    ckg_router,
    trajectory_router,
    modes_router,
    lakeview_router,
    worktree_router,
    code_completion_router,
    reflection_router,
)
from app.api.routes.agent import (
    rules_router,
    integrations_router,
    agents_router as agent_mgmt_router,
)
from app.api.routes.rag import kb_router as rag_kb_router, query_router as rag_query_router
from app.api.routes.rag.compound_vault import router as rag_compound_router
from app.api.routes.rag.filter_routes import router as rag_filter_router
from app.api.routes import items, private
from app.core.config import settings

api_router = APIRouter()

# ===== 所有前端共享 =====
api_router.include_router(login_router)       # POST /login/access-token
api_router.include_router(users_router)       # CRUD /users
api_router.include_router(utils_router)       # GET /health-check/

# ===== 系统管理 API =====
api_router.include_router(system_models_router)      # /system/models — 全局模型管理
api_router.include_router(system_health_router)      # /system/health — 系统健康检查
api_router.include_router(task_queue_router)         # /system/tasks/queue — 任务队列监控
api_router.include_router(system_gpu_router)         # /system/gpu — GPU 设备管理
api_router.include_router(system_resources_router)   # /system/resources — 系统资源监控
api_router.include_router(system_catalog_router)     # /system/catalog — 模型目录
api_router.include_router(system_remote_router)      # /system/remote — 远程代理
api_router.include_router(system_terminal_router)     # /system/terminal — 远程终端
api_router.include_router(system_benchmarks_router)   # /system/benchmarks — 基准测试
api_router.include_router(system_config_router)       # /system/config — 配置管理
api_router.include_router(system_storage_router)      # /system/storage — 存储管理
api_router.include_router(system_checkpoints_router)  # /system/checkpoints — Git 检查点
api_router.include_router(system_guardrails_router)   # /system/guardrails — 护栏系统

# ===== video-admin 后台 =====
api_router.include_router(items.router)        # 模板占位，后续替换
api_router.include_router(admin_videos_router) # /videos CRUD
api_router.include_router(analytics_router)    # /videos/analytics
api_router.include_router(moderation_router)   # /videos/moderation

# ===== video-client C端 =====
api_router.include_router(browse_router)       # /videos/browse, /videos/search
api_router.include_router(play_router)         # /videos/{id}/play
api_router.include_router(generate_router)     # /videos/generate

# ===== studio-admin 管理端 (Vue) =====
api_router.include_router(projects_router)     # /studio/projects CRUD
api_router.include_router(templates_router)    # /studio/templates

# ===== studio-client C端 =====
api_router.include_router(chat_router)         # /studio/chat
api_router.include_router(sessions_router)     # /studio/sessions
api_router.include_router(models_router)       # /studio/models

# ===== Agent 系统 =====
api_router.include_router(agent_chat_router)           # /agent/chat, /agent/chat/stream, /agent/chat/simple
api_router.include_router(agent_tools_router)          # /agent/tools
api_router.include_router(agent_mcp_router)            # /agent/mcp/servers
api_router.include_router(agent_mcp_marketplace_router) # /agent/mcp/marketplace (MCP 市场)
api_router.include_router(plugin_marketplace_router)   # /plugin-marketplace/registry, /install, /installed

# ===== Model Presets (借鉴 Open WebUI) =====
api_router.include_router(model_presets_router)        # /model-presets/presets CRUD + apply + resolve

# ===== Model Arena (借鉴 Open WebUI Arena) =====
api_router.include_router(model_arena_router)          # /arena/compare, /arena/vote, /arena/rankings

# ===== Model Analytics (借鉴 Open WebUI Dashboard) =====
api_router.include_router(agent_analytics_router)      # /analytics/overview, /analytics/by-model, /analytics/trends

# ===== Long-term Memory (借鉴 Open WebUI Memory) =====
api_router.include_router(memory_router)               # /memory CRUD + /memory/search 语义检索

# ===== Structured Output (借鉴 llama.cpp GBNF) =====
api_router.include_router(structured_output_router)  # /structured-output/json-schema-to-gbnf + validate + templates + preview

# ===== Image Generation (借鉴 Open WebUI Images) =====
api_router.include_router(image_gen_router)          # /image-gen/generate + batch + providers

# ===== Voice TTS/STT (借鉴 Open WebUI Audio) =====
api_router.include_router(voice_router)              # /voice/tts + /voice/stt + /voice/voices

# ===== Webhooks (借鉴 Open WebUI Webhooks) =====
api_router.include_router(webhooks_router)           # /webhooks CRUD + /webhooks/trigger + /webhooks/{id}/test + logs

# ===== Skills (借鉴 Open WebUI Skills) =====
api_router.include_router(skills_router)              # /skills CRUD + /skills/apply + /skills/load

# ===== Prompt Templates (借鉴 Open WebUI Prompt Templates) =====
api_router.include_router(prompt_templates_router)    # /prompt-templates CRUD + /prompt-templates/search + /resolve

# ===== Task Management (借鉴 Open WebUI Tasks) =====
api_router.include_router(tasks_router)               # /tasks CRUD + steps + /tasks/{id}/tree + /auto-generate

# ===== OpenAPI Discovery (借鉴 Open WebUI OpenAPI) =====
api_router.include_router(openapi_discovery_router)   # /openapi/discover + servers + tools

# ===== Knowledge Graph (借鉴 Obsidian Wikilinks + JSON Canvas) =====
api_router.include_router(knowledge_graph_router)     # /knowledge-graph canvas + backlinks + parse + graph-data

# ===== CKG 代码知识图谱 (借鉴 Trae Agent tree-sitter) =====
api_router.include_router(ckg_router)                  # /agent/ckg index + search + stats

# ===== Trajectory 轨迹记录 =====
api_router.include_router(trajectory_router)            # /agent/trajectory list + get + delete

# ===== Custom Modes (借鉴 Roo Code) =====
api_router.include_router(modes_router)                  # /agent/modes list + CRUD + load + activate

# ===== Lakeview 步骤摘要 (借鉴 Trae Agent) =====
api_router.include_router(lakeview_router)               # /agent/lakeview session summary

# ===== Worktree 并行开发 (借鉴 Roo Code) =====
api_router.include_router(worktree_router)               # /agent/worktree list/create/delete/branches/tasks

# ===== Code Completion 代码补全 (借鉴 Continue) =====
api_router.include_router(code_completion_router)        # /agent/code-completion complete/analyze/feedback

# ===== Reflection 自省/反思 (借鉴 Trae Agent reflect) =====
api_router.include_router(reflection_router)              # /agent/reflection reflect/self-critique/history/stats

# ===== Rules 规则管理 =====
api_router.include_router(rules_router)                   # /rules CRUD + /rules/stats

# ===== Integrations 集成服务 =====
api_router.include_router(integrations_router)            # /integrations CRUD + connect/disconnect

# ===== Agent Management =====
api_router.include_router(agent_mgmt_router)              # /agents CRUD + toggle + clone

# ===== RAG 检索增强生成 =====
api_router.include_router(rag_kb_router)       # /rag/knowledge-bases
api_router.include_router(rag_query_router)    # /rag/query, /rag/search, /rag/health
api_router.include_router(rag_compound_router) # /compound ingest/search/bm25/hot-cache (借鉴 claude-obsidian)
api_router.include_router(rag_filter_router)   # /rag/filters list/apply/preview (借鉴 obsidian-clipper)

# ===== local 专用 =====
if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
