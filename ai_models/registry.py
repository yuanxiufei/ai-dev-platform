"""
Model registry — 中心注册与发现

所有 AI 模型在此处统一注册，Worker 通过 ModelType + priority 自动选择最优可用模型。

## 模型路径解析规则
  1. 环境变量 `MODEL_<NAME>_PATH` 指定绝对路径（最高优先级）
  2. 自动拼接 `{MODELS_DIR}/{default_subdir}` — 默认从项目根 models/ 下加载
  3. GGUF 模型还需通过 `model_file` 字段指定 .gguf 文件名

## 添加新模型步骤
  1. 在下方注册区块调用 `register(ModelConfig(...))`
  2. 设置 `model_type` 匹配已有的能力类型
  3. 设置 `priority` 确定选择优先级
  4. 无需修改任何模型类代码（同类型自动复用）

## Priority 优先级机制
  同类型多个模型按 priority 降序排列，Worker 取第一个可用的。
  例如：Gemma GGUF(priority=20) > Qwen-Coder safetensors(priority=10)
  部署时只需配置好对应路径，自动选择最优模型。

Usage:
    from ai_models.registry import list_by_type, get_config, ModelType
    coders = list_by_type(ModelType.CODE_GENERATION)
    for c in sorted(coders, key=lambda c: c.priority, reverse=True):
        print(f"{c.display_name} [priority={c.priority}]")
"""

import os
from pathlib import Path
from typing import Optional

from ai_models.base import BaseModel, ModelConfig, ModelType, ModelFormat

# 模型存放根目录（可通过环境变量 MODELS_DIR 覆盖）
# 默认指向项目根目录下的 models/ 文件夹
_MODELS_DIR = Path(
    os.getenv("MODELS_DIR", str(Path(__file__).resolve().parent.parent / "models"))
)

# 全局模型注册表: {model_name: ModelConfig}
# 所有模型通过 register() 函数注册到此字典
_registry: dict[str, ModelConfig] = {}


def _model_path(name: str, default: str) -> str:
    """支持两种来源：
    1. 环境变量 MODEL_<NAME>_PATH 指向本地路径
    2. 自动拼接 MODELS_DIR/<default>
    """
    env_key = f"MODEL_{name.upper().replace('-', '_')}_PATH"
    env_val = os.getenv(env_key)
    if env_val:
        return env_val
    return str(_MODELS_DIR / default)


def register(config: ModelConfig) -> None:
    """Register a model configuration."""
    _registry[config.name] = config


def get_config(name: str) -> Optional[ModelConfig]:
    """Get model config by name."""
    return _registry.get(name)


def list_all() -> dict[str, ModelConfig]:
    """Return all registered model configs."""
    return dict(_registry)


def list_by_type(model_type: ModelType) -> list[ModelConfig]:
    """List models filtered by type."""
    return [c for c in _registry.values() if c.model_type == model_type]


# ============ 注册内置模型 ============

# --- 视觉理解（safetensors 格式）---
register(ModelConfig(
    name="qwen25-vl-7b",
    display_name="Qwen2.5-VL 7B (视觉理解)",
    model_type=ModelType.VISION_LANGUAGE,
    model_format=ModelFormat.SAFETENSORS,
    model_path=_model_path("qwen25-vl-7b", "Qwen2.5-VL-7B-Instruct"),
    device="cuda",
    max_tokens=4096,
))

# --- 代码生成 — safetensors（Qwen-Coder）---
register(ModelConfig(
    name="qwen25-coder-7b",
    display_name="Qwen2.5-Coder 7B (代码生成)",
    model_type=ModelType.CODE_GENERATION,
    model_format=ModelFormat.SAFETENSORS,
    model_path=_model_path("qwen25-coder-7b", "Qwen2.5-Coder-7B-Instruct"),
    device="cuda",
    max_tokens=8192,
    temperature=0.3,
    priority=10,
))

# --- 代码生成 — GGUF（Gemma 31B，本地量化）---
register(ModelConfig(
    name="gemma-31b",
    display_name="Gemma 4 31B IT (代码生成·GGUF)",
    model_type=ModelType.CODE_GENERATION,
    model_format=ModelFormat.GGUF,
    model_path=_model_path("gemma-31b", "gemma-4-31B-it-qat-GGUF"),
    model_file="gemma-4-31B-it-qat-UD-Q4_K_XL.gguf",
    device="cpu",
    n_gpu_layers=0,       # 纯 CPU 模式；有 GPU 的话改成 -1
    n_ctx=8192,
    max_tokens=4096,
    temperature=0.3,
    priority=20,           # 优先级更高，有 Gemma 就用 Gemma
))

# --- 视频生成（safetensors 格式）---
register(ModelConfig(
    name="cogvideox-5b",
    display_name="CogVideoX 5B (视频生成)",
    model_type=ModelType.VIDEO_GENERATION,
    model_format=ModelFormat.SAFETENSORS,
    model_path=_model_path("cogvideox-5b", "CogVideoX-5b"),
    device="cuda",
    dtype="bfloat16",
))


# ============ 便捷函数 ============

def get_model(name: str) -> Optional[ModelConfig]:
    """Alias for get_config."""
    return get_config(name)


def list_models(model_type: Optional[ModelType] = None) -> list[dict]:
    """List model info dicts, optionally filtered by type."""
    configs = list_by_type(model_type) if model_type else list(_registry.values())
    return [c.to_dict() for c in configs]
