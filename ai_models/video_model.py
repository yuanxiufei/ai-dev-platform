"""
CogVideoX Model — 视频生成

Usage:
    from ai_models.video_model import VIDEO_MODEL
    model = VIDEO_MODEL.load()
    result = model.generate_video(prompt="sunset over mountains", num_frames=48)
"""

import logging
from pathlib import Path
from typing import Optional

from ai_models.base import BaseModel, ModelConfig
from ai_models.registry import get_config

logger = logging.getLogger(__name__)

# 视频输出目录
VIDEO_OUTPUT_DIR = Path("output/videos")
VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class VideoGenerationModel(BaseModel):
    """Wrapper for CogVideoX text-to-video model.

    负责：文本 → 视频、UI 代码 → 演示视频。
    仅支持 safetensors 格式（扩散模型无法量化到 GGUF）。

    Usage:
        model = get_video_model()
        model.load()
        result = model.generate_video("sunset over mountains", num_frames=48)
        # 或为 UI 代码生成演示视频
        result = model.generate_ui_demo("<button>Submit</button>", duration=6.0)
    """

    def __init__(self, config: ModelConfig):
        """初始化视频生成模型。

        Args:
            config: 模型配置（从 registry 获取的 CogVideoX 配置）
        """
        super().__init__(config)
        self._pipeline = None  # CogVideoXPipeline 实例

    def load(self) -> "VideoGenerationModel":
        """Load CogVideoX pipeline with memory optimizations."""
        if self._loaded:
            return self

        logger.info(f"Loading {self.config.display_name}...")

        try:
            import torch
            from diffusers import CogVideoXPipeline

            self._pipeline = CogVideoXPipeline.from_pretrained(
                self.config.model_path,
                torch_dtype=torch.bfloat16,
            )

            # 显存优化
            if torch.cuda.is_available():
                self._pipeline.enable_model_cpu_offload()
                self._pipeline.vae.enable_slicing()
                self._pipeline.vae.enable_tiling()
                logger.info(f"{self.config.display_name}: GPU optimizations enabled")
            else:
                logger.warning(f"{self.config.display_name}: loading on CPU (slow)")

            self._loaded = True
            device = "GPU (CUDA)" if torch.cuda.is_available() else "CPU"
            logger.info(f"{self.config.display_name} loaded ({device})")

        except ImportError as e:
            logger.error(
                "diffusers/torch not installed for video model. "
                "Run: pip install torch diffusers transformers accelerate. "
                "Error: %s", e
            )
        except Exception as e:
            logger.error(f"Failed to load {self.config.display_name}: {e}")

        return self

    def generate(self, **kwargs) -> dict:
        """Alias for generate_video()."""
        return self.generate_video(**kwargs)

    def generate_video(
        self,
        prompt: str,
        num_frames: int = 48,
        fps: int = 8,
        num_inference_steps: int = 50,
        seed: int = 42,
    ) -> dict:
        """
        Generate video from text prompt.

        Args:
            prompt: Text description of the video scene
            num_frames: Total number of frames to generate
            fps: Frames per second (determines duration = num_frames / fps)
            num_inference_steps: Diffusion denoising steps (more = higher quality, slower)
            seed: Random seed for reproducible results

        Returns:
            dict::
                {
                    "task_id": str,       # 任务唯一标识
                    "status": str,        # "completed"
                    "video_path": str,    # 输出 MP4 路径
                    "prompt": str,
                    "num_frames": int,
                    "fps": int,
                    "duration": float,    # num_frames / fps
                    "seed": int,
                }
        """
        if not self._loaded:
            self.load()

        task_id = f"vid_{abs(hash(prompt)) % 10**8}"
        output_path = VIDEO_OUTPUT_DIR / f"{task_id}.mp4"

        if not self._loaded:
            return {
                "task_id": task_id,
                "status": "error",
                "video_path": "",
                "prompt": prompt,
                "error": f"{self.config.display_name} not loaded",
            }

        logger.info(f"Generating video: '{prompt[:60]}...'")

        try:
            import torch
            from diffusers.utils import export_to_video

            video_frames = self._pipeline(
                prompt=prompt,
                num_videos_per_prompt=1,
                num_inference_steps=num_inference_steps,
                num_frames=num_frames,
                generator=torch.Generator(device="cuda").manual_seed(seed)
                if torch.cuda.is_available()
                else torch.Generator(device="cpu").manual_seed(seed),
            ).frames[0]

            export_to_video(video_frames, str(output_path), fps=fps)

            return {
                "task_id": task_id,
                "status": "completed",
                "video_path": str(output_path),
                "prompt": prompt,
                "num_frames": num_frames,
                "fps": fps,
                "duration": num_frames / fps,
                "seed": seed,
            }

        except ImportError as e:
            logger.error(f"Video generation failed — missing dependency: {e}")
            return {
                "task_id": task_id,
                "status": "error",
                "video_path": "",
                "prompt": prompt,
                "error": f"Missing dependency: {e}",
            }
        except Exception as e:
            logger.error(f"Video generation error: {e}")
            return {
                "task_id": task_id,
                "status": "error",
                "video_path": "",
                "prompt": prompt,
                "error": str(e),
            }

    def generate_ui_demo(
        self,
        code_snippet: str,
        task_id: str = "",
        duration: float = 10.0,
        fps: int = 30,
    ) -> dict:
        """
        Generate a demo video from UI code.

        实际会将 code_snippet 截取前 200 字符作为视频描述 prompt，
        然后调用 generate_video() 生成视频。

        Args:
            code_snippet: HTML/CSS/JS 代码片段
            task_id: 任务标识（为空则自动生成）
            duration: 视频时长（秒），会影响 num_frames = duration * fps
            fps: 帧率

        Returns:
            dict: generate_video() 的返回值 + "type": "ui_demo"
        """
        if not self._loaded:
            self.load()

        task_id = task_id or f"demo_{abs(hash(code_snippet)) % 10**8}"

        prompt = f"A software UI demonstration showing: {code_snippet[:200]}"
        result = self.generate_video(
            prompt=prompt,
            num_frames=int(duration * fps),
            fps=fps,
        )
        result["task_id"] = task_id
        result["type"] = "ui_demo"
        return result


# ============ 模块级单例 ============

_config = get_config("cogvideox-5b")
VIDEO_MODEL = VideoGenerationModel(_config) if _config else None


def get_video_model() -> Optional[VideoGenerationModel]:
    """Get the video generation model instance."""
    return VIDEO_MODEL
