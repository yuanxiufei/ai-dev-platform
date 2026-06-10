"""
Base model class and shared types for all AI models.

支持两种模型格式：
  - SAFETENSORS：transformers/diffusers 原生格式（Qwen-VL、CogVideoX）
  - GGUF：llama-cpp-python 量化格式（Gemma、本地大模型）

Usage — 继承 BaseModel 示例::

    from ai_models.base import BaseModel, ModelConfig, ModelType

    class MyCustomModel(BaseModel):
        def load(self):
            # 加载模型逻辑
            self._model = load_my_model(self.config.model_path)
            self._loaded = True
            return self

        def generate(self, prompt: str, **kwargs) -> str:
            if not self._loaded:
                self.load()
            return self._model.run(prompt)

    # 注册到 registry
    from ai_models.registry import register
    register(ModelConfig(
        name="my-model",
        display_name="My Custom LLM",
        model_type=ModelType.TEXT_GENERATION,
        model_path="/path/to/model",
    ))
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelType(str, Enum):
    """Supported model capability types.

    按能力分类，不是按厂商/平台分类：
      - VISION_LANGUAGE: 截图→布局分析
      - CODE_GENERATION: 任何代码生成任务（前端/全栈/API）
      - VIDEO_GENERATION: 文本→视频 / UI 演示
      - TEXT_GENERATION: 通用文本生成（预留扩展）
    """

    VISION_LANGUAGE = "vision_language"    # 视觉理解（截图→布局）
    CODE_GENERATION = "code_generation"    # 代码生成
    VIDEO_GENERATION = "video_generation"  # 视频生成
    TEXT_GENERATION = "text_generation"    # 通用文本生成


class ModelFormat(str, Enum):
    """Model file format — determines which loader to use.

    - SAFETENSORS: transformers / diffusers 原生格式
    - GGUF: llama-cpp-python 量化格式（仅自回归文本，不支持扩散/视觉模型）
    """

    SAFETENSORS = "safetensors"  # transformers / diffusers
    GGUF = "gguf"                # llama-cpp-python


@dataclass
class ModelConfig:
    """Configuration for loading and running a model.

    字段按是否 GGUF 分为两类：
    - 通用字段：name, display_name, model_type, model_format, device, dtype, priority
    - GGUF 专用：model_file, n_gpu_layers, n_ctx
    - safetensors 专用：max_tokens（GGUF 在调用时传，也受此默认值影响）
    """

    name: str                          # 唯一标识（如 "gemma-31b"、"qwen25-coder-7b"）
    display_name: str                  # 展示名称（用于日志和 UI）
    model_type: ModelType              # 能力类型
    model_path: str = ""               # 模型目录 或 HuggingFace repo id
    model_format: ModelFormat = ModelFormat.SAFETENSORS  # 文件格式
    model_file: str = ""               # GGUF 的文件名（safetensors 留空）
    device: str = "cuda"               # cuda / cpu / metal
    dtype: str = "auto"                # float16 / bfloat16 / auto
    n_gpu_layers: int = -1             # GGUF: 卸载到 GPU 的层数（-1=全部, 0=纯 CPU）
    n_ctx: int = 8192                  # GGUF: 上下文长度
    max_tokens: int = 4096             # 最大输出 token 数
    temperature: float = 0.7           # 生成温度（0=确定性, 越高越随机）
    priority: int = 0                  # 同类型多模型时的优先级（越大越优先）
    extra: dict[str, Any] = field(default_factory=dict)  # 扩展字段（未来新增参数用）

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict（不含路径等敏感信息）。"""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "model_type": self.model_type.value,
            "model_format": self.model_format.value,
            "device": self.device,
            "dtype": self.dtype,
            "priority": self.priority,
        }

    @property
    def is_gguf(self) -> bool:
        """快捷判断是否为 GGUF 格式。"""
        return self.model_format == ModelFormat.GGUF


class BaseModel:
    """Base class for all AI models.

    每个模型包装器（VL、Coder、Video）继承此类。
    子类只需实现 load() 和业务方法。generate() 预留通用推理入口。

    Usage::

        class MyModel(BaseModel):
            def load(self):
                if self._loaded:
                    return self
                # ... 加载逻辑 ...
                self._loaded = True
                return self

            def generate(self, **kwargs):
                if not self._loaded:
                    self.load()
                # ... 推理逻辑 ...
    """

    def __init__(self, config: ModelConfig):
        self.config = config
        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        """模型是否已加载到内存。"""
        return self._loaded

    def load(self):
        """加载模型到内存。返回 self 支持链式调用。

        Returns:
            self: 支持 model = MyModel(cfg).load()
        """
        raise NotImplementedError

    def unload(self) -> None:
        """释放模型占用的资源（显存/内存）。"""
        self._loaded = False

    def generate(self, **kwargs) -> Any:
        """通用推理入口。子类应覆盖此方法或提供专门的业务方法。

        Args:
            **kwargs: 模型相关的推理参数
        """
        raise NotImplementedError

    def __repr__(self) -> str:
        status = "loaded" if self._loaded else "not loaded"
        fmt = self.config.model_format.value
        return f"<{self.config.display_name} [{fmt}] [{status}]>"
