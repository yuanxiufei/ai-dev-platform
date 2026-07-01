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

        try:
            import torch
            from transformers import Qwen2VLForConditionalGeneration, AutoProcessor

            dtype_map = {
                "float16": torch.float16,
                "bfloat16": torch.bfloat16,
                "float32": torch.float32,
            }
            torch_dtype = dtype_map.get(self.config.dtype, "auto")

            self._model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.config.model_path,
                torch_dtype=torch_dtype,
                device_map="auto",
                trust_remote_code=True,
            )
            self._processor = AutoProcessor.from_pretrained(
                self.config.model_path,
                trust_remote_code=True,
            )

            self._loaded = True
            device = "GPU (CUDA)" if torch.cuda.is_available() else "CPU"
            logger.info(f"{self.config.display_name} loaded successfully ({device})")

        except ImportError as e:
            logger.error(
                "transformers/torch not installed for VL model. "
                "Run: pip install torch transformers accelerate. "
                "Error: %s", e
            )
        except Exception as e:
            logger.error(f"Failed to load {self.config.display_name}: {e}")

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

        if not self._loaded:
            return {
                "page": "unknown",
                "layout": "flex",
                "components": [],
                "raw_image_path": image_path,
                "_error": f"{self.config.display_name} not loaded",
            }

        prompt = SCREENSHOT_TO_LAYOUT
        if extra_prompt:
            prompt += f"\n\nAdditional instructions: {extra_prompt}"

        logger.info(f"Analyzing screenshot: {image_path}")

        try:
            import torch
            from PIL import Image

            image = Image.open(image_path).convert("RGB")

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt},
                    ],
                },
            ]

            text = self._processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
            )
            inputs = self._processor(
                text=[text], images=[image],
                return_tensors="pt",
            )

            # 自动设备迁移
            if hasattr(self._model, 'device'):
                inputs = {k: v.to(self._model.device) for k, v in inputs.items()}

            with torch.no_grad():
                generated_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=self.config.max_tokens,
                )

            # 只解码新生成部分
            input_len = inputs["input_ids"].shape[1]
            output_text = self._processor.batch_decode(
                generated_ids[:, input_len:],
                skip_special_tokens=True,
            )[0]

            logger.info(f"VL model output ({len(output_text)} chars)")

            # 尝试解析 JSON 输出
            import json
            try:
                result = json.loads(output_text)
                result["raw_image_path"] = image_path
                return result
            except json.JSONDecodeError:
                return {
                    "page": "analyzed_page",
                    "layout": "flex",
                    "components": [],
                    "raw_output": output_text,
                    "raw_image_path": image_path,
                }

        except ImportError as e:
            logger.error(f"VL inference failed — missing dependency: {e}")
            return {
                "page": "error",
                "layout": "flex",
                "components": [],
                "raw_image_path": image_path,
                "_error": f"Missing dependency: {e}",
            }
        except Exception as e:
            logger.error(f"VL inference error: {e}")
            return {
                "page": "error",
                "layout": "flex",
                "components": [],
                "raw_image_path": image_path,
                "_error": str(e),
            }


# ============ 模块级单例 ============

# 延迟加载 — 首次调用 .load() 时才真正加载模型
_config = get_config("qwen25-vl-7b")
VLMODEL = VisionLanguageModel(_config) if _config else None


def get_vl_model() -> Optional[VisionLanguageModel]:
    """Get the VL model instance."""
    return VLMODEL
