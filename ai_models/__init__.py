"""
AI Models Package — 统一模型管理

按「能力类型」组织 AI 模型，而不是按格式或厂商分类。
支持 safetensors（transformers/diffusers）和 GGUF（llama-cpp）两种格式自动适配。

Worker 通过 registry 自动选择最优可用模型（priority 机制）。

Usage:
    # 查看所有模型
    from ai_models import list_all, list_by_type, ModelType
    for cfg in list_by_type(ModelType.CODE_GENERATION):
        print(cfg.display_name)

    # 使用模型（业务代码直接 import 具体模型模块）
    from ai_models.coder_model import get_coder_model
    model = get_coder_model()
    model.load()
    code = model.generate_code(layout_json, framework="vue")
"""

from ai_models.base import BaseModel, ModelConfig, ModelType, ModelFormat
from ai_models.registry import get_model, list_models, list_by_type, list_all

__all__ = [
    "BaseModel",
    "ModelConfig",
    "ModelType",
    "ModelFormat",
    "get_model",
    "list_models",
    "list_by_type",
    "list_all",
]
