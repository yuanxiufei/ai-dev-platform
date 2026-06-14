"""
AI Models Package — 统一模型管理

按「能力类型」组织 AI 模型，而不是按格式或厂商分类。
支持 safetensors（transformers/diffusers）和 GGUF（llama-cpp）两种格式自动适配，
以及远程 API（OpenAI / Anthropic / DeepSeek / Replicate / 智谱 / 通义千问）。

核心组件：
  - registry:     模型注册中心（本地 + 远程）
  - scheduler:    多模型动态调度器（评分排序）
  - api_proxy:    第三方 API 统一代理（格式适配）
  - optimizer:    使用数据自动优化引擎
  - downloader:   模型下载器（HF / ModelScope 双源）

Worker 通过 registry + scheduler 自动选择最优可用模型（本地优先 → API 回退）。

Usage:
    # 查看所有模型（本地 + 远程）
    from ai_models import get_all_models, ModelType
    models = get_all_models(ModelType.CODE_GENERATION)
    for m in models:
        print(f"{m['display_name']} [remote={m.get('is_remote')}]")

    # 使用调度器找到最优模型
    from ai_models.scheduler import get_scheduler
    scheduler = get_scheduler()
    best = scheduler.get_best_model("code_gen")

    # 使用优化器自动调整
    from ai_models.optimizer import get_optimizer
    optimizer = get_optimizer()
    optimizer.auto_tune(days=7)
"""

from ai_models.base import BaseModel, ModelConfig, ModelType, ModelFormat, ModelStrength
from ai_models.registry import (
    get_model,
    list_models,
    list_by_type,
    list_all,
    get_all_models,
    get_best_candidates,
    list_remote_models,
    list_remote_dicts,
    register_remote,
    RemoteModelConfig,
    get_all_local_configs,
    get_all_remote_configs,
)
from ai_models.scheduler import (
    ModelScheduler,
    get_scheduler,
    init_scheduler,
    ModelScore,
    SchedulerConfig,
)
from ai_models.optimizer import (
    AutoOptimizer,
    get_optimizer,
    init_optimizer,
    OptimizationAction,
    OptimizationSuggestion,
)
from ai_models.api_proxy import (
    create_proxy,
    OpenAiCompatibleProxy,
    AnthropicProxy,
    ReplicateProxy,
    ApiProxyConfig,
)
from ai_models.downloader import ModelDownloader

__all__ = [
    # Base
    "BaseModel",
    "ModelConfig",
    "ModelType",
    "ModelFormat",
    "ModelStrength",
    # Registry
    "get_model",
    "list_models",
    "list_by_type",
    "list_all",
    "get_all_models",
    "get_best_candidates",
    "list_remote_models",
    "list_remote_dicts",
    "register_remote",
    "RemoteModelConfig",
    "get_all_local_configs",
    "get_all_remote_configs",
    # Scheduler
    "ModelScheduler",
    "get_scheduler",
    "init_scheduler",
    "ModelScore",
    "SchedulerConfig",
    # Optimizer
    "AutoOptimizer",
    "get_optimizer",
    "init_optimizer",
    "OptimizationAction",
    "OptimizationSuggestion",
    # API Proxy
    "create_proxy",
    "OpenAiCompatibleProxy",
    "AnthropicProxy",
    "ReplicateProxy",
    "ApiProxyConfig",
    # Downloader
    "ModelDownloader",
]
