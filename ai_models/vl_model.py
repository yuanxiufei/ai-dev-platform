"""
Qwen2.5-VL Model — 视觉理解（截图 → 布局 JSON）

Usage:
    from ai_models.vl_model import VLMODEL
    model = VLMODEL.load()
    layout = model.analyze_screenshot("path/to/screenshot.png")
"""

import logging
from typing import Optional

from ai_models.base import BaseModel, ModelConfig, ModelType
from ai_models.prompts.code_gen import SCREENSHOT_TO_LAYOUT
from ai_models.registry import get_config

logger = logging.getLogger(__name__)


class VisionLanguageModel(BaseModel):
    """Wrapper for Qwen2.5-VL vision-language model.

    负责：截图 → 布局 JSON 分析。
    仅支持 safetensors 格式（视觉-语言模型无法量化到 GGUF）。

    Usage:
        model = get_vl_model()
        model.load()
        layout = model.analyze_screenshot("screenshot.png")
    """

    def __init__(self, config: ModelConfig):
        """初始化 VL 模型。

        Args:
            config: 模型配置（从 registry 获取的 Qwen2.5-VL 配置）
        """
        super().__init__(config)
        self._model = None       # Qwen2VLForConditionalGeneration 实例
        self._processor = None   # AutoProcessor 实例

    def load(self) -> "VisionLanguageModel":
        """Load VL model and processor."""
        if self._loaded:
            return self

        logger.info(f"Loading {self.config.display_name} from {self.config.model_path}...")

        # TODO: 实际加载模型（需要 transformers + torch）
        # from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        # self._model = Qwen2VLForConditionalGeneration.from_pretrained(
        #     self.config.model_path,
        #     torch_dtype=self.config.dtype,
        #     device_map="auto",
        # )
        # self._processor = AutoProcessor.from_pretrained(self.config.model_path)

        self._loaded = True
        logger.info(f"{self.config.display_name} loaded successfully")
        return self

    def generate(self, **kwargs) -> dict:
        """Not used directly — use analyze_screenshot() instead."""
        raise NotImplementedError("Use analyze_screenshot() for VL tasks")

    def analyze_screenshot(
        self,
        image_path: str,
        extra_prompt: str = "",
    ) -> dict:
        """
        Analyze a UI screenshot and return structured layout JSON.

        Args:
            image_path: Path to the screenshot image (PNG/JPG)
            extra_prompt: Additional instructions appended to the system prompt
                          (e.g. "focus on the login form only")

        Returns:
            dict::
                {
                    "page": str,       # 页面名称
                    "layout": str,     # flex | grid | absolute
                    "components": [    # 组件树（嵌套）
                        {
                            "type": str,     # button | input | card | ...
                            "text": str,     # 可见文本
                            "position": {"x", "y", "w", "h"},
                            "style": {"bg", "rounded", "shadow", ...},
                            "children": [...]
                        }
                    ],
                    "raw_image_path": str,
                }
        """
        if not self._loaded:
            self.load()

        prompt = SCREENSHOT_TO_LAYOUT
        if extra_prompt:
            prompt += f"\n\nAdditional instructions: {extra_prompt}"

        logger.info(f"Analyzing screenshot: {image_path}")

        # TODO: 实际推理
        # messages = [
        #     {"role": "user", "content": [
        #         {"type": "image", "image": image_path},
        #         {"type": "text", "text": prompt},
        #     ]},
        # ]
        # text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        # inputs = self._processor(text=[text], images=[image], return_tensors="pt").to(self.config.device)
        # generated_ids = self._model.generate(**inputs, max_new_tokens=self.config.max_tokens)
        # output = self._processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        # Placeholder
        return {
            "page": "analyzed_page",
            "layout": "flex",
            "components": [],
            "raw_image_path": image_path,
        }


# ============ 模块级单例 ============

# 延迟加载 — 首次调用 .load() 时才真正加载模型
_config = get_config("qwen25-vl-7b")
VLMODEL = VisionLanguageModel(_config) if _config else None


def get_vl_model() -> Optional[VisionLanguageModel]:
    """Get the VL model instance."""
    return VLMODEL
