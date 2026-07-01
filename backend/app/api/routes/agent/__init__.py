"""
Agent API 路由 — Agent 对话、工具调用、MCP 管理、插件市场、模型预设、Arena 评测、分析看板、长期记忆
结构化输出、图像生成、语音、Webhook、Skills、Prompt Templates、Task Management、OpenAPI Discovery
CKG 代码知识图谱、Trajectory 轨迹记录、Worktree 并行开发、Code Completion 代码补全、Reflection 自省/反思
"""

from app.api.routes.agent.chat import router as agent_chat_router  # noqa: F401
from app.api.routes.agent.tools import router as agent_tools_router  # noqa: F401
from app.api.routes.agent.mcp_servers import router as agent_mcp_router  # noqa: F401
from app.api.routes.agent.mcp_marketplace import router as agent_mcp_marketplace_router  # noqa: F401
from app.api.routes.agent.plugin_marketplace import router as plugin_marketplace_router  # noqa: F401
from app.api.routes.agent.model_presets import router as model_presets_router  # noqa: F401
from app.api.routes.agent.model_arena import router as model_arena_router  # noqa: F401
from app.api.routes.agent.analytics import router as analytics_router  # noqa: F401
from app.api.routes.agent.memory import router as memory_router  # noqa: F401
from app.api.routes.agent.structured_output import router as structured_output_router  # noqa: F401
from app.api.routes.agent.image_gen import router as image_gen_router  # noqa: F401
from app.api.routes.agent.voice import router as voice_router  # noqa: F401
from app.api.routes.agent.webhooks import router as webhooks_router  # noqa: F401
from app.api.routes.agent.skills import router as skills_router  # noqa: F401
from app.api.routes.agent.prompt_templates import router as prompt_templates_router  # noqa: F401
from app.api.routes.agent.tasks import router as tasks_router  # noqa: F401
from app.api.routes.agent.openapi_discovery import router as openapi_discovery_router  # noqa: F401
from app.api.routes.agent.knowledge_graph import router as knowledge_graph_router  # noqa: F401
from app.api.routes.agent.ckg import router as ckg_router  # noqa: F401
from app.api.routes.agent.trajectory import router as trajectory_router  # noqa: F401
from app.api.routes.agent.traces import router as traces_router  # noqa: F401
from app.api.routes.agent.modes import router as modes_router  # noqa: F401
from app.api.routes.agent.lakeview import router as lakeview_router  # noqa: F401
from app.api.routes.agent.worktree import router as worktree_router  # noqa: F401
from app.api.routes.agent.code_completion import router as code_completion_router  # noqa: F401
from app.api.routes.agent.reflection import router as reflection_router  # noqa: F401
from app.api.routes.agent.rules import router as rules_router  # noqa: F401
from app.api.routes.agent.integrations import router as integrations_router  # noqa: F401
from app.api.routes.agent.run import router as agent_run_router  # noqa: F401
from app.api.routes.agent.agents import router as agents_router  # noqa: F401
from app.api.routes.agent.checkpoint import router as checkpoint_router  # noqa: F401
from app.api.routes.agent.auto_approval import router as auto_approval_router  # noqa: F401
