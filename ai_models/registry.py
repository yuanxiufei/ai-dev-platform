"""
Model registry — 中心注册与发现

所有 AI 模型在此处统一注册（本地 + 远程），Worker 通过 ModelType + priority 自动选择最优可用模型。

## 模型来源：
  - 本地模型：safetensors / GGUF 格式，从 MODELS_DIR 加载
  - 远程 API：OpenAI / Anthropic / DeepSeek / Replicate 等，通过 API 网关调用
  - 优先使用本地模型（低延迟、无成本），API 作为回退

## 模型路径解析规则
  1. 环境变量 `MODEL_<NAME>_PATH` 指定绝对路径（最高优先级）
  2. 自动拼接 `{MODELS_DIR}/{default_subdir}` — 默认从项目根 models/ 下加载
  3. GGUF 模型还需通过 `model_file` 字段指定 .gguf 文件名

## 添加新模型步骤
  1. 在下方注册区块调用 `register(ModelConfig(...))` 或 `register_remote()`
  2. 设置 `model_type` 匹配已有的能力类型
  3. 设置 `priority` 确定选择优先级
  4. 无需修改任何模型类代码（同类型自动复用）

## Priority 优先级机制
  同类型多个模型按 priority 降序排列，Worker 取第一个可用的。
  本地模型默认 priority 高于远程 API，确保优先使用本地资源。

Usage:
    from ai_models.registry import list_by_type, get_config, ModelType
    coders = list_by_type(ModelType.CODE_GENERATION)
    for c in sorted(coders, key=lambda c: c.priority, reverse=True):
        print(f"{c.display_name} [priority={c.priority}]")

    # 查看远程模型
    remotes = list_remote_models()
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ai_models.base import BaseModel, ModelConfig, ModelType, ModelFormat, ModelStrength

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
    strengths=[ModelStrength.VISION_DENSE.value],
))

# --- 代码生成 — safetensors（Qwen-Coder）---
register(ModelConfig(
    name="qwen25-coder-7b",
    display_name="Qwen2.5-Coder 7B (代码生成·后端)",
    model_type=ModelType.CODE_GENERATION,
    model_format=ModelFormat.SAFETENSORS,
    model_path=_model_path("qwen25-coder-7b", "Qwen2.5-Coder-7B-Instruct"),
    device="cuda",
    max_tokens=8192,
    temperature=0.3,
    priority=10,
    strengths=[ModelStrength.BACKEND_CODE.value, ModelStrength.GENERAL_CODE.value],
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
    strengths=[ModelStrength.GENERAL_CODE.value],
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
    strengths=[ModelStrength.SHORT_VIDEO.value],
))


# ── 远程 API 模型 ──────────────────────────────────────────

@dataclass
class RemoteModelConfig:
    """远程 API 模型配置"""
    name: str                        # 模型标识
    display_name: str                # 展示名称
    model_type: ModelType            # 能力类型
    provider: str                    # openai | anthropic | deepseek | replicate | zhipu | qwen | ollama
    api_model_id: str               # API 中的模型 ID
    priority: int = 30               # 优先级（低于本地模型）
    is_active: bool = True
    requires_api_key: bool = True
    max_tokens: int = 4096
    temperature: float = 0.7
    strengths: list[str] = field(default_factory=list)  # 擅长方向
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "model_type": self.model_type.value if hasattr(self.model_type, "value") else str(self.model_type),
            "provider": self.provider,
            "api_model_id": self.api_model_id,
            "priority": self.priority,
            "is_active": self.is_active,
            "is_remote": True,
            "requires_api_key": self.requires_api_key,
            "max_tokens": self.max_tokens,
            "strengths": self.strengths,
        }


# 远程模型注册表: {model_name: RemoteModelConfig}
_remote_registry: dict[str, RemoteModelConfig] = {}


def register_remote(config: RemoteModelConfig) -> None:
    """注册远程 API 模型"""
    _remote_registry[config.name] = config


def get_remote_config(name: str) -> Optional[RemoteModelConfig]:
    """获取远程模型配置"""
    return _remote_registry.get(name)


def list_remote_models(model_type: Optional[ModelType] = None) -> list[RemoteModelConfig]:
    """列出远程 API 模型，可按类型筛选"""
    if model_type:
        return [c for c in _remote_registry.values() if c.model_type == model_type]
    return list(_remote_registry.values())


def list_remote_dicts() -> list[dict]:
    """列出所有远程模型为字典"""
    return [c.to_dict() for c in _remote_registry.values()]


# ── 注册远程 API 模型 ─────────────────────────────────────

# 代码生成远程模型
register_remote(RemoteModelConfig(
    name="openai-gpt4o",
    display_name="GPT-4o (OpenAI·前端UI)",
    model_type=ModelType.CODE_GENERATION,
    provider="openai",
    api_model_id="gpt-4o",
    priority=35,
    max_tokens=4096,
    strengths=[ModelStrength.UI_DESIGN.value, ModelStrength.FRONTEND_CODE.value, ModelStrength.GENERAL_CODE.value],
))

register_remote(RemoteModelConfig(
    name="openai-o3",
    display_name="o3 (OpenAI·全栈)",
    model_type=ModelType.CODE_GENERATION,
    provider="openai",
    api_model_id="o3",
    priority=38,
    max_tokens=8192,
    strengths=[ModelStrength.GENERAL_CODE.value, ModelStrength.BACKEND_CODE.value],
))

register_remote(RemoteModelConfig(
    name="claude-sonnet",
    display_name="Claude Sonnet 4 (Anthropic·前端UI)",
    model_type=ModelType.CODE_GENERATION,
    provider="anthropic",
    api_model_id="claude-sonnet-4-20250514",
    priority=36,
    max_tokens=4096,
    strengths=[ModelStrength.UI_DESIGN.value, ModelStrength.FRONTEND_CODE.value],
))

register_remote(RemoteModelConfig(
    name="deepseek-v3",
    display_name="DeepSeek-V3 (后端·全栈)",
    model_type=ModelType.CODE_GENERATION,
    provider="deepseek",
    api_model_id="deepseek-chat",
    priority=34,
    max_tokens=4096,
    strengths=[ModelStrength.BACKEND_CODE.value, ModelStrength.GENERAL_CODE.value],
))

register_remote(RemoteModelConfig(
    name="zhipu-glm4",
    display_name="GLM-4 Plus (智谱·通用)",
    model_type=ModelType.CODE_GENERATION,
    provider="zhipu",
    api_model_id="glm-4-plus",
    priority=32,
    max_tokens=4096,
    strengths=[ModelStrength.GENERAL_CODE.value],
))

# ═════ Ollama 本地模型（无需 API 密钥）═════

register_remote(RemoteModelConfig(
    name="ollama-qwen3-coder-30b",
    display_name="Qwen3-Coder 30B (Ollama·主力编程)",
    model_type=ModelType.CODE_GENERATION,
    provider="ollama",
    api_model_id="qwen3-coder:30b",
    priority=50,  # 最高优先级
    max_tokens=8192,
    temperature=0.3,
    requires_api_key=False,
    strengths=[ModelStrength.GENERAL_CODE.value, ModelStrength.BACKEND_CODE.value, ModelStrength.FRONTEND_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-qwen3-32b",
    display_name="Qwen3 32B (Ollama·通用)",
    model_type=ModelType.TEXT_GENERATION,
    provider="ollama",
    api_model_id="qwen3:32b",
    priority=45,
    max_tokens=8192,
    temperature=0.5,
    requires_api_key=False,
    strengths=[ModelStrength.GENERAL_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-deepseek-r1",
    display_name="DeepSeek-R1 132B (Ollama·推理)",
    model_type=ModelType.TEXT_GENERATION,
    provider="ollama",
    api_model_id="deepseek-r1",
    priority=48,
    max_tokens=8192,
    temperature=0.6,
    requires_api_key=False,
    strengths=[ModelStrength.GENERAL_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-gemma4-31b",
    display_name="Gemma 4 31B IT (Ollama·代码)",
    model_type=ModelType.CODE_GENERATION,
    provider="ollama",
    api_model_id="gemma4:31b",
    priority=44,
    max_tokens=8192,
    temperature=0.3,
    requires_api_key=False,
    strengths=[ModelStrength.UI_DESIGN.value, ModelStrength.FRONTEND_CODE.value, ModelStrength.GENERAL_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-gemma4-26b",
    display_name="Gemma 4 26B IT (Ollama·备用)",
    model_type=ModelType.CODE_GENERATION,
    provider="ollama",
    api_model_id="gemma4:26b",
    priority=40,
    max_tokens=8192,
    temperature=0.3,
    requires_api_key=False,
    strengths=[ModelStrength.FRONTEND_CODE.value, ModelStrength.GENERAL_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-llama3.1-8b",
    display_name="Llama3.1 8B (Ollama·极速)",
    model_type=ModelType.TEXT_GENERATION,
    provider="ollama",
    api_model_id="llama3.1:8b",
    priority=38,
    max_tokens=4096,
    temperature=0.5,
    requires_api_key=False,
    strengths=[ModelStrength.GENERAL_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-qwen25-coder",
    display_name="Qwen2.5-Coder (Ollama·轻量快)",
    model_type=ModelType.CODE_GENERATION,
    provider="ollama",
    api_model_id="qwen2.5-coder",
    priority=42,
    max_tokens=8192,
    temperature=0.3,
    requires_api_key=False,
    strengths=[ModelStrength.GENERAL_CODE.value, ModelStrength.BACKEND_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-deepseek-coder-v2",
    display_name="DeepSeek-Coder V2 (Ollama·长上下文)",
    model_type=ModelType.CODE_GENERATION,
    provider="ollama",
    api_model_id="deepseek-coder-v2",
    priority=43,
    max_tokens=16384,
    temperature=0.3,
    requires_api_key=False,
    strengths=[ModelStrength.GENERAL_CODE.value, ModelStrength.BACKEND_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-deepseek-coder",
    display_name="DeepSeek-Coder (Ollama·极速)",
    model_type=ModelType.CODE_GENERATION,
    provider="ollama",
    api_model_id="deepseek-coder",
    priority=41,
    max_tokens=8192,
    temperature=0.3,
    requires_api_key=False,
    strengths=[ModelStrength.GENERAL_CODE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-gemma3-27b",
    display_name="Gemma3 27B (Ollama·备用)",
    model_type=ModelType.TEXT_GENERATION,
    provider="ollama",
    api_model_id="gemma3:27b",
    priority=37,
    max_tokens=8192,
    temperature=0.5,
    requires_api_key=False,
    strengths=[ModelStrength.GENERAL_CODE.value],
    extra={"is_local_api": True},
))

# 视觉模型
register_remote(RemoteModelConfig(
    name="ollama-minicpm-v-8b",
    display_name="MiniCPM-V 8B (Ollama·截图分析)",
    model_type=ModelType.VISION_LANGUAGE,
    provider="ollama",
    api_model_id="minicpm-v:8b",
    priority=36,
    max_tokens=4096,
    temperature=0.4,
    requires_api_key=False,
    strengths=[ModelStrength.VISION_DENSE.value],
    extra={"is_local_api": True},
))

register_remote(RemoteModelConfig(
    name="ollama-llama3.2-vision-11b",
    display_name="Llama3.2 Vision 11B (Ollama·视觉)",
    model_type=ModelType.VISION_LANGUAGE,
    provider="ollama",
    api_model_id="llama3.2-vision",
    priority=35,
    max_tokens=4096,
    temperature=0.4,
    requires_api_key=False,
    strengths=[ModelStrength.VISION_DENSE.value],
    extra={"is_local_api": True},
))

# 视觉理解远程模型
register_remote(RemoteModelConfig(
    name="openai-gpt4o-vision",
    display_name="GPT-4o Vision (OpenAI)",
    model_type=ModelType.VISION_LANGUAGE,
    provider="openai",
    api_model_id="gpt-4o",
    priority=35,
    max_tokens=4096,
    strengths=[ModelStrength.VISION_DENSE.value],
))

register_remote(RemoteModelConfig(
    name="zhipu-glm4v",
    display_name="GLM-4V (智谱)",
    model_type=ModelType.VISION_LANGUAGE,
    provider="zhipu",
    api_model_id="glm-4v",
    priority=32,
    max_tokens=2048,
    strengths=[ModelStrength.VISION_DENSE.value],
))

# 视频生成远程模型
register_remote(RemoteModelConfig(
    name="replicate-cogvideox",
    display_name="CogVideoX-5B (Replicate)",
    model_type=ModelType.VIDEO_GENERATION,
    provider="replicate",
    api_model_id="lucataco/cogvideox-5b",
    priority=30,
    max_tokens=0,
    extra={"num_frames": 49, "fps": 8},
    strengths=[ModelStrength.SHORT_VIDEO.value],
))

register_remote(RemoteModelConfig(
    name="replicate-svd",
    display_name="Stable Video Diffusion (Replicate)",
    model_type=ModelType.VIDEO_GENERATION,
    provider="replicate",
    api_model_id="stability-ai/stable-video-diffusion",
    priority=28,
    max_tokens=0,
    extra={"num_frames": 25, "fps": 6},
    strengths=[ModelStrength.SHORT_VIDEO.value],
))

# 通用对话远程模型
register_remote(RemoteModelConfig(
    name="openai-gpt4o-chat",
    display_name="GPT-4o Chat (OpenAI)",
    model_type=ModelType.TEXT_GENERATION,
    provider="openai",
    api_model_id="gpt-4o",
    priority=35,
    max_tokens=4096,
    strengths=[ModelStrength.GENERAL_CODE.value],
))

register_remote(RemoteModelConfig(
    name="deepseek-v3-chat",
    display_name="DeepSeek-V3 Chat",
    model_type=ModelType.TEXT_GENERATION,
    provider="deepseek",
    api_model_id="deepseek-chat",
    priority=34,
    max_tokens=4096,
    strengths=[ModelStrength.GENERAL_CODE.value],
))

register_remote(RemoteModelConfig(
    name="claude-sonnet-chat",
    display_name="Claude Sonnet 4 Chat (Anthropic)",
    model_type=ModelType.TEXT_GENERATION,
    provider="anthropic",
    api_model_id="claude-sonnet-4-20250514",
    priority=36,
    max_tokens=4096,
    strengths=[ModelStrength.UI_DESIGN.value, ModelStrength.GENERAL_CODE.value],
))


# ── 统一模型查询 ──────────────────────────────────────────

def get_all_models(model_type: Optional[ModelType] = None) -> list[dict]:
    """获取所有模型（本地 + 远程）"""
    local = list_models(model_type)
    remotes = [
        c.to_dict() for c in (
            list_remote_models(model_type) if model_type
            else list_remote_models()
        )
    ]
    return local + remotes


def get_best_candidates(model_type: ModelType, limit: int = 5) -> list[dict]:
    """获取指定类型的最优候选模型（按 priority 排序）"""
    all_models = get_all_models(model_type)
    all_models.sort(key=lambda m: m.get("priority", 0), reverse=True)
    return all_models[:limit]


def get_all_remote_configs() -> dict[str, RemoteModelConfig]:
    """获取所有远程模型配置"""
    return dict(_remote_registry)


def get_all_local_configs() -> dict[str, ModelConfig]:
    """获取所有本地模型配置"""
    return dict(_registry)


# ============ 便捷函数 ============

def get_model(name: str) -> Optional[ModelConfig]:
    """Alias for get_config."""
    return get_config(name)


def list_models(model_type: Optional[ModelType] = None) -> list[dict]:
    """List model info dicts, optionally filtered by type."""
    configs = list_by_type(model_type) if model_type else list(_registry.values())
    return [c.to_dict() for c in configs]
