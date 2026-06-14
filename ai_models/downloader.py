"""
模型下载器（ai_models 层）

职责：
1. 模型文件的本地下载管理
2. 支持 HuggingFace / ModelScope 双源
3. 断点续传
4. GGUF / Safetensors 文件识别和路径解析
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

logger = logging.getLogger("ai_models.downloader")


class ModelDownloader:
    """
    模型下载器

    使用方式：
      downloader = ModelDownloader(models_dir="models")
      path = await downloader.download("Qwen/Qwen2.5-Coder-7B-Instruct", source="huggingface")
    """

    def __init__(
        self,
        models_dir: str | Path = "models",
        hf_token: str | None = None,
    ):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.hf_token = hf_token or os.getenv("HF_TOKEN", "")

        # 镜像源
        self._mirrors = {
            "huggingface": os.getenv("HF_ENDPOINT", "https://hf-mirror.com"),
            "modelscope": os.getenv("MODELSCOPE_ENDPOINT", "https://modelscope.cn"),
        }

    def resolve_path(self, model_id: str) -> Path:
        """
        解析本地模型路径

        规则：
        1. 环境变量 MODEL_<NAME>_PATH 优先
        2. models_dir / model_name 次之
        """
        safe_name = model_id.replace("/", "_").replace(":", "_").lower()
        env_var = f"MODEL_{safe_name.upper()}_PATH"

        if env_path := os.getenv(env_var):
            return Path(env_path)

        return self.models_dir / safe_name

    async def download(
        self,
        model_id: str,
        source: str = "huggingface",
        on_progress: Callable[[int, int, float], None] | None = None,
    ) -> Path:
        """
        下载模型到本地

        Args:
            model_id: HuggingFace ID (如 Qwen/Qwen2.5-Coder-7B-Instruct)
            source: 下载源 huggingface | modelscope
            on_progress: 进度回调 (downloaded_bytes, total_bytes, speed_mbps)

        Returns:
            本地模型路径
        """
        local_path = self.resolve_path(model_id)

        if local_path.exists() and self._verify_model(local_path):
            logger.info(f"Model already exists: {local_path}")
            return local_path

        # 选择下载源
        download_func = self._download_from_hf
        if source == "modelscope":
            download_func = self._download_from_ms

        try:
            result = await download_func(model_id, local_path, on_progress)
        except Exception as e:
            # 回退到备用源
            logger.warning(f"Primary source failed ({e}), trying fallback")
            alt_func = (
                self._download_from_ms if source == "huggingface"
                else self._download_from_hf
            )
            result = await alt_func(model_id, local_path, on_progress)

        return result

    async def _download_from_hf(
        self,
        model_id: str,
        local_path: Path,
        on_progress=None,
    ) -> Path:
        """从 HuggingFace 下载"""
        mirror = self._mirrors["huggingface"]
        logger.info(f"Downloading {model_id} from HF ({mirror})")

        # 使用 huggingface_hub 库
        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=model_id,
                local_dir=str(local_path),
                endpoint=mirror,
                token=self.hf_token or True,
                resume_download=True,
            )
            return local_path
        except ImportError:
            logger.warning("huggingface_hub not installed, using httpx fallback")
            return await self._download_via_httpx(
                f"{mirror}/{model_id}/resolve/main",
                local_path,
                on_progress,
            )

    async def _download_from_ms(
        self,
        model_id: str,
        local_path: Path,
        on_progress=None,
    ) -> Path:
        """从 ModelScope 下载"""
        logger.info(f"Downloading {model_id} from ModelScope")

        try:
            from modelscope.hub.snapshot_download import snapshot_download

            snapshot_download(
                model_id=model_id,
                local_dir=str(local_path),
                revision="master",
            )
            return local_path
        except ImportError:
            logger.warning("modelscope not installed, using httpx fallback")
            mirror = self._mirrors["modelscope"]
            return await self._download_via_httpx(
                f"{mirror}/api/v1/models/{model_id}/repo?Revision=master&FilePath=",
                local_path,
                on_progress,
            )

    async def _download_via_httpx(
        self,
        base_url: str,
        dest: Path,
        on_progress=None,
    ) -> Path:
        """
        通过 HTTP 下载文件列表

        # TODO: 实现文件清单解析和批量下载
        """
        import httpx

        dest.mkdir(parents=True, exist_ok=True)
        logger.info(f"HTTP download to {dest}")

        # 简化实现：提示用户使用 huggingface_hub 或 modelscope
        logger.warning(
            "For full model download support, install: "
            "pip install huggingface_hub modelscope"
        )

        # 检测已有文件
        files_found = list(dest.rglob("*"))
        if files_found:
            logger.info(f"Found {len(files_found)} existing files in {dest}")
            return dest

        raise RuntimeError(
            "Cannot download model without huggingface_hub or modelscope. "
            f"Please install them or manually place model files in {dest}"
        )

    def _verify_model(self, path: Path) -> bool:
        """验证模型完整性"""
        if not path.exists():
            return False

        # 检查关键文件
        key_files = [
            "config.json",
            "tokenizer_config.json",
        ]
        has_config = any(path.joinpath(f).exists() for f in key_files)

        # 检查模型文件
        gguf_files = list(path.rglob("*.gguf"))
        safetensor_files = list(path.rglob("*.safetensors"))
        bin_files = list(path.rglob("*.bin"))
        pt_files = list(path.rglob("*.pt"))

        has_weights = any([gguf_files, safetensor_files, bin_files, pt_files])

        if has_config and has_weights:
            return True

        if gguf_files and not has_config:
            # GGUF 文件不需要 config.json 也能运行
            return True

        return False

    def get_model_info(self, local_path: Path) -> dict:
        """获取本地模型信息"""
        info = {
            "path": str(local_path),
            "exists": local_path.exists(),
            "format": None,
            "size_gb": 0,
            "files": [],
        }

        if not local_path.exists():
            return info

        # 计算大小
        total_bytes = 0
        gguf_files = []
        safetensor_files = []

        for f in local_path.rglob("*"):
            if f.is_file():
                size = f.stat().st_size
                total_bytes += size
                info["files"].append({
                    "name": f.name,
                    "size_mb": round(size / 1024 / 1024, 2),
                })

                if f.suffix == ".gguf":
                    gguf_files.append(f)
                elif f.suffix == ".safetensors":
                    safetensor_files.append(f)

        info["size_gb"] = round(total_bytes / 1024 / 1024 / 1024, 2)

        if gguf_files:
            info["format"] = "GGUF"
            info["gguf_files"] = [f.name for f in gguf_files]
        elif safetensor_files:
            info["format"] = "Safetensors"
        elif list(local_path.rglob("*.bin")):
            info["format"] = "PyTorch"

        return info

    def delete_model(self, model_id: str) -> bool:
        """删除本地模型"""
        local_path = self.resolve_path(model_id)
        if not local_path.exists():
            return False

        import shutil
        try:
            shutil.rmtree(local_path)
            logger.info(f"Deleted model: {local_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete model {local_path}: {e}")
            return False

    def list_local_models(self) -> list[dict]:
        """列出本地已下载的模型"""
        models = []
        if not self.models_dir.exists():
            return models

        for dir_name in os.listdir(self.models_dir):
            dir_path = self.models_dir / dir_name
            if dir_path.is_dir():
                info = self.get_model_info(dir_path)
                if info["exists"] and info["format"]:
                    models.append({
                        "name": dir_name,
                        **info,
                    })

        return models
