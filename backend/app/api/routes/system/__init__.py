"""
系统管理 API 路由

提供跨 Studio/Video 共用的系统级功能：
  - /system/models      — 全局模型管理
  - /system/health      — 系统健康检查
  - /system/gpu         — GPU 设备与分配管理
  - /system/resources   — 系统资源监控
  - /system/catalog     — 模型目录浏览
  - /system/remote      — 远程代理/端口转发/工作区信任
  - /system/tasks/queue — 任务队列监控
  - /system/terminal    — 远程终端/PTY 管理
  - /system/benchmarks  — 模型基准测试
  - /system/config      — 配置热加载
  - /system/storage     — 存储管理
  - /system/checkpoints — Git 检查点
  - /system/guardrails  — 护栏系统
  - /system/session-tree — Session 树 + 检查点恢复（借鉴 hermes-agent）
  - /system/cli-pipeline — CLI 流水线组合
  - /system/diagnostics — 代码诊断分析 (Error Lens 后端)（借鉴 AutoCLI YAML 适配器）
  - /system/format          — 代码格式化服务 (多语言/多 Provider)
  - /system/terminal/quickfix — 终端错误快速修复建议
  - /system/problem-matchers — 构建输出解析为结构化诊断 (Session 49)
  - /system/diff             — 服务端差异计算 (Session 49)
  - /system/hierarchy        — 调用层次+类型层次分析 (Session 50)
  - /system/notebook         — Notebook 多语言 Kernel 执行引擎 (Session 50)
  - /system/testing          — 测试发现+执行引擎 (Session 50)
  - /system/search           — 全文本搜索+文件搜索+替换 (Session 51)
  - /system/snippets          — 代码片段 CRUD + 导入导出 (Session 51)
  - /system/lsp               — LSP 适配桥接 (completion/hover/def/ref) (Session 51)
  - /system/filesystem        — 文件系统 CRUD API (Session 51)
  - /system/backup            — 全量备份导出/导入 (Session 52)
  - /system/sync              — 用户数据跨设备同步 (Session 52)
  - /system/feature-flags     — 特性开关/A/B实验分组 (Session 52)
  - /system/git               — Git/SCM 版本控制 API (Session 53)
  - /system/debug             — DAP 调试协议桥接 (Session 53)
  - /system/comments          — 代码评审评论系统 (Session 53)
  - /system/tasks             — 构建任务配置与执行 (Session 53)
  - /system/extensions        — 扩展市场与管理 (Session 53)
  - /system/context-keys      — when 条件评估引擎 (Session 55)
  - /system/config-resolver   — ${variable} 配置变量解析 (Session 55)
  - /system/state             — 全局/工作区状态持久化 (Session 55)
  - /system/logs              — 多通道日志管理+WebSocket流 (Session 55)
  - /system/local-history     — 文件本地历史+缩进检测 (Session 55)
  - /system/external-terminal — 外部终端打开 (Session 57)
"""

from app.api.routes.system.models import router as models_router
from app.api.routes.system.health import router as health_router
from app.api.routes.system.gpu import router as gpu_router
from app.api.routes.system.resources import router as resources_router
from app.api.routes.system.catalog import router as catalog_router
from app.api.routes.system.remote import router as remote_router
from app.api.routes.system.terminal import router as terminal_router
from app.api.routes.system.benchmarks import router as benchmarks_router
from app.api.routes.system.config import router as config_router
from app.api.routes.system.storage import router as storage_router
from app.api.routes.system.checkpoints import router as checkpoints_router
from app.api.routes.system.guardrails import router as guardrails_router
from app.api.routes.system.memory_graph import router as memory_graph_router
from app.api.routes.system.cli_history import router as cli_history_router
from app.api.routes.system.model_health import router as model_health_router
from app.api.routes.system.session_tree import router as session_tree_router
from app.api.routes.system.cli_pipeline import router as cli_pipeline_router
from app.api.routes.system.diagnostics import router as diagnostics_router
from app.api.routes.system.format import router as format_router
from app.api.routes.system.terminal_quickfix import router as terminal_quickfix_router
from app.api.routes.system.language_detection import router as language_detection_router
from app.api.routes.system.code_actions import router as code_actions_router
from app.api.routes.system.symbols import router as symbols_router
from app.api.routes.system.problem_matchers import router as problem_matchers_router
from app.api.routes.system.diff import router as diff_router
from app.api.routes.system.hierarchy import router as hierarchy_router
from app.api.routes.system.notebook import router as notebook_router
from app.api.routes.system.testing import router as testing_router
from app.api.routes.system.search import router as search_router
from app.api.routes.system.snippets import router as snippets_router
from app.api.routes.system.lsp_bridge import router as lsp_bridge_router
from app.api.routes.system.filesystem import router as filesystem_router
from app.api.routes.system.backup import router as backup_router
from app.api.routes.system.sync import router as sync_router
from app.api.routes.system.feature_flags import router as feature_flags_router
from app.api.routes.system.git import router as git_router
from app.api.routes.system.debug_api import router as debug_router
from app.api.routes.system.comments import router as comments_router
from app.api.routes.system.tasks import router as tasks_router
from app.api.routes.system.extensions import router as extensions_router
from app.api.routes.system.context_keys import router as context_keys_router
from app.api.routes.system.config_resolver import router as config_resolver_router
from app.api.routes.system.state import router as state_router
from app.api.routes.system.logs import router as logs_router
from app.api.routes.system.local_history import router as local_history_router
from app.api.routes.system.external_terminal import router as external_terminal_router
from app.api.routes.system.keybindings_export import router as keybindings_export_router
from app.api.routes.system.external_uri_opener import router as external_uri_opener_router

__all__ = [
    "models_router",
    "health_router",
    "gpu_router",
    "resources_router",
    "catalog_router",
    "remote_router",
    "terminal_router",
    "benchmarks_router",
    "config_router",
    "storage_router",
    "checkpoints_router",
    "guardrails_router",
    "memory_graph_router",
    "cli_history_router",
    "model_health_router",
    "session_tree_router",
    "cli_pipeline_router",
    "diagnostics_router",
    "format_router",
    "terminal_quickfix_router",
    "language_detection_router",
    "code_actions_router",
    "symbols_router",
    "problem_matchers_router",
    "diff_router",
    "hierarchy_router",
    "notebook_router",
    "testing_router",
    "search_router",
    "snippets_router",
    "lsp_bridge_router",
    "filesystem_router",
    "backup_router",
    "sync_router",
    "feature_flags_router",
    "git_router",
    "debug_router",
    "comments_router",
    "tasks_router",
    "extensions_router",
    "context_keys_router",
    "config_resolver_router",
    "state_router",
    "logs_router",
    "local_history_router",
    "external_terminal_router",
    "keybindings_export_router",
    "external_uri_opener_router",
]
