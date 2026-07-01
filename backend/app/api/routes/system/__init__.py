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
  - /system/cli-pipeline — CLI 流水线组合（借鉴 AutoCLI YAML 适配器）
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
]
