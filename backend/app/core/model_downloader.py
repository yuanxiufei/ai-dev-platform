"""
模型下载管理器

职责：
1. 管理模型下载的完整生命周期（启动、暂停、取消、重试）
2. 支持 HuggingFace / ModelScope 双源自动切换
3. 断点续传（Resumable Downloads）
4. 完整性校验（SHA256）
5. 下载进度实时推送

"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import httpx

logger = logging.getLogger("model_downloader")


# ── 类型定义 ──────────────────────────────────────────────

class DownloadState(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class DownloadProgress:
    """下载进度信息"""
    task_id: str
    model_name: str
    state: DownloadState
    progress_pct: float = 0.0        # 0-100
    speed_mbps: float = 0.0          # 下载速度 MB/s
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    eta_seconds: int | None = None
    error_message: str | None = None


@dataclass
class DownloadSource:
    """下载源配置"""
    name: str                        # huggingface | modelscope
    base_url: str
    mirror_urls: list[str] = field(default_factory=list)
    token: str | None = None         # HF Token


# ── 下载源 ────────────────────────────────────────────────

HF_SOURCE = DownloadSource(
    name="huggingface",
    base_url="https://huggingface.co",
    mirror_urls=["https://hf-mirror.com"],  # 国内镜像
)

MODELSCOPE_SOURCE = DownloadSource(
    name="modelscope",
    base_url="https://modelscope.cn",
    mirror_urls=[],
)


# ── 文件下载器 ────────────────────────────────────────────

class FileDownloader:
    """单个文件的下载器，支持断点续传"""

    def __init__(
        self,
        url: str,
        dest_path: Path,
        expected_size: int | None = None,
        expected_sha256: str | None = None,
        chunk_size: int = 8 * 1024 * 1024,  # 8MB
        max_retries: int = 3,
    ):
        self.url = url
        self.dest_path = dest_path
        self.expected_size = expected_size
        self.expected_sha256 = expected_sha256
        self.chunk_size = chunk_size
        self.max_retries = max_retries

        self._downloaded = 0
        self._cancelled = False

    @property
    def downloaded(self) -> int:
        """已下载字节数（含断点续传的已有部分）"""
        if self.dest_path.exists():
            return self.dest_path.stat().st_size
        return self._downloaded

    @property
    def total(self) -> int | None:
        return self.expected_size

    def cancel(self):
        self._cancelled = True

    async def download(self) -> Path:
        """
        下载文件，支持断点续传

        返回：下载完成的文件路径
        """
        dest_path = Path(self.dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        # 如果文件已存在且大小匹配，跳过
        if dest_path.exists() and self.expected_size:
            actual_size = dest_path.stat().st_size
            if actual_size == self.expected_size:
                logger.info(f"File already exists: {dest_path} ({actual_size} bytes)")
                if self.expected_sha256:
                    if await self._verify_sha256(dest_path):
                        return dest_path
                    logger.warning("SHA256 mismatch, re-downloading")
                else:
                    return dest_path

        # 获取已下载大小（断点续传）
        resume_from = dest_path.stat().st_size if dest_path.exists() else 0
        self._downloaded = resume_from

        # 下载
        for attempt in range(self.max_retries):
            try:
                await self._do_download(resume_from)
                break
            except Exception as e:
                if attempt >= self.max_retries - 1:
                    raise
                logger.warning(
                    f"Download attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )
                await asyncio.sleep(2 ** attempt)

        # 验证
        if self.expected_sha256:
            if not await self._verify_sha256(dest_path):
                raise IOError(f"SHA256 verification failed for {dest_path}")
            logger.info(f"SHA256 verified: {dest_path}")

        return dest_path

    async def _do_download(self, resume_from: int):
        """执行下载"""
        headers = {}
        if resume_from > 0:
            headers["Range"] = f"bytes={resume_from}-"
            logger.info(f"Resuming download from byte {resume_from}")

        async with httpx.AsyncClient(timeout=httpx.Timeout(600, connect=30)) as client:
            async with client.stream("GET", self.url, headers=headers) as response:
                response.raise_for_status()

                # 获取文件总大小
                content_range = response.headers.get("content-range")
                if content_range:
                    total = int(content_range.split("/")[-1])
                    self.expected_size = total

                # 写入文件
                mode = "ab" if resume_from > 0 else "wb"
                with open(self.dest_path, mode) as f:
                    async for chunk in response.aiter_bytes(chunk_size=self.chunk_size):
                        if self._cancelled:
                            logger.info("Download cancelled")
                            return
                        f.write(chunk)
                        self._downloaded += len(chunk)

                logger.info(
                    f"Download completed: {self.dest_path} "
                    f"({self._downloaded / 1024 / 1024 / 1024:.2f} GB)"
                )

    async def _verify_sha256(self, file_path: Path) -> bool:
        """验证文件 SHA256"""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(self.chunk_size):
                if self._cancelled:
                    return False
                sha256.update(chunk)
        actual_hash = sha256.hexdigest()
        return actual_hash == self.expected_sha256


# ── 模型下载管理器 ────────────────────────────────────────

class ModelDownloadManager:
    """
    模型下载管理器

    使用方式：
      manager = ModelDownloadManager(models_dir="/models")
      task_id = await manager.start_download("qwen25-coder-7b")
      progress = manager.get_progress(task_id)
      manager.cancel_download(task_id)
    """

    def __init__(
        self,
        models_dir: str | Path = "models",
        max_concurrent: int = 2,
    ):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent

        # 待下载的模型配置
        self._model_configs: dict[str, dict] = self._build_model_configs()

        # 活跃下载任务
        self._tasks: dict[str, DownloadProgress] = {}
        self._downloaders: dict[str, FileDownloader] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

        # 进度回调
        self._on_progress: Callable[[DownloadProgress], None] | None = None

    def _build_model_configs(self) -> dict[str, dict]:
        """构建模型下载配置清单"""
        return {
            "qwen25-coder-7b": {
                "display_name": "Qwen2.5-Coder-7B-Instruct",
                "hf_id": "Qwen/Qwen2.5-Coder-7B-Instruct",
                "ms_id": "qwen/Qwen2.5-Coder-7B-Instruct",
                "files": [
                    {"filename": "model.safetensors", "required": True},
                    {"filename": "config.json", "required": True},
                    {"filename": "tokenizer.json", "required": True},
                    {"filename": "tokenizer_config.json", "required": True},
                ],
                "format": "safetensors",
                "capability": "code_gen",
                "approx_size_gb": 14.5,
            },
            "gemma-31b": {
                "display_name": "Gemma 4 31B IT QAT",
                "hf_id": "unsloth/gemma-4-31b-it-qat-GGUF",
                "ms_id": None,
                "files": [
                    {"filename": "gemma-4-31b-it-qat-Q4_K_M.gguf", "required": True},
                ],
                "format": "gguf",
                "capability": "code_gen",
                "approx_size_gb": 18.0,
            },
            "cogvideox-5b": {
                "display_name": "CogVideoX-5B",
                "hf_id": "THUDM/CogVideoX-5b",
                "ms_id": "ZhipuAI/CogVideoX-5b",
                "files": [
                    {"filename": "transformer/**", "required": True},
                    {"filename": "vae/**", "required": True},
                    {"filename": "scheduler/**", "required": True},
                    {"filename": "text_encoder/**", "required": True},
                    {"filename": "tokenizer/**", "required": True},
                ],
                "format": "safetensors",
                "capability": "video_gen",
                "approx_size_gb": 10.0,
            },
            "qwen25-vl-7b": {
                "display_name": "Qwen2.5-VL-7B-Instruct",
                "hf_id": "Qwen/Qwen2.5-VL-7B-Instruct",
                "ms_id": "qwen/Qwen2.5-VL-7B-Instruct",
                "files": [
                    {"filename": "model.safetensors", "required": True},
                    {"filename": "config.json", "required": True},
                ],
                "format": "safetensors",
                "capability": "vision",
                "approx_size_gb": 14.5,
            },
        }

    def get_model_list(self) -> list[dict]:
        """获取可下载的模型列表"""
        result = []
        for name, config in self._model_configs.items():
            is_downloaded = (self.models_dir / name).exists()
            result.append({
                "name": name,
                "display_name": config["display_name"],
                "capability": config["capability"],
                "format": config["format"],
                "size_gb": config["approx_size_gb"],
                "is_downloaded": is_downloaded,
                "sources": self._get_available_sources(name),
            })
        return result

    def _get_available_sources(self, model_name: str) -> list[str]:
        """获取模型的可用下载源"""
        config = self._model_configs.get(model_name, {})
        sources = []
        if config.get("hf_id"):
            sources.append("huggingface")
        if config.get("ms_id"):
            sources.append("modelscope")
        return sources

    async def start_download(
        self,
        model_name: str,
        source: str = "huggingface",
    ) -> str:
        """
        启动异步下载

        返回 task_id，可用于查询进度
        """
        if model_name not in self._model_configs:
            raise ValueError(f"Unknown model: {model_name}")

        config = self._model_configs[model_name]
        task_id = f"dl_{model_name}_{id(self)}"

        # 创建进度对象
        progress = DownloadProgress(
            task_id=task_id,
            model_name=model_name,
            state=DownloadState.DOWNLOADING,
        )
        self._tasks[task_id] = progress

        # 异步执行下载
        asyncio.create_task(self._execute_download(task_id, model_name, config, source))

        return task_id

    async def _execute_download(
        self,
        task_id: str,
        model_name: str,
        config: dict,
        source: str,
    ):
        """执行下载任务"""
        progress = self._tasks.get(task_id)
        if not progress:
            return

        async with self._semaphore:
            try:
                model_dir = self.models_dir / model_name
                model_dir.mkdir(parents=True, exist_ok=True)

                # 构建下载 URL
                files = config["files"]
                total_files = len(files)

                for idx, file_info in enumerate(files):
                    if progress.state == DownloadState.CANCELLED:
                        return

                    filename = file_info["filename"]
                    file_url = self._build_download_url(
                        config, source, filename
                    )

                    if not file_url:
                        logger.warning(f"No URL for {filename}, trying next source")
                        # 尝试备用源
                        alt_source = "modelscope" if source == "huggingface" else "huggingface"
                        file_url = self._build_download_url(
                            config, alt_source, filename
                        )
                        if not file_url:
                            if file_info["required"]:
                                raise ValueError(
                                    f"Cannot find download URL for required file: {filename}"
                                )
                            continue

                    dest = model_dir / filename
                    downloader = FileDownloader(
                        url=file_url,
                        dest_path=dest,
                    )
                    self._downloaders[task_id] = downloader

                    logger.info(
                        f"Downloading [{idx + 1}/{total_files}]: {filename}"
                    )
                    await downloader.download()

                    # 更新进度
                    progress.progress_pct = ((idx + 1) / total_files) * 100
                    self._notify_progress(progress)

                # 完成
                progress.state = DownloadState.COMPLETED
                progress.progress_pct = 100.0
                self._notify_progress(progress)
                logger.info(f"Model '{model_name}' downloaded successfully")

            except Exception as e:
                logger.error(f"Download failed for {model_name}: {e}")
                progress.state = DownloadState.FAILED
                progress.error_message = str(e)
                self._notify_progress(progress)

            finally:
                self._downloaders.pop(task_id, None)

    def _build_download_url(
        self, config: dict, source: str, filename: str
    ) -> str | None:
        """构建文件下载 URL"""
        if source == "huggingface":
            hf_id = config.get("hf_id")
            if not hf_id:
                return None
            # 优先使用镜像
            mirror = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
            return f"{mirror}/{hf_id}/resolve/main/{filename}"

        elif source == "modelscope":
            ms_id = config.get("ms_id")
            if not ms_id:
                return None
            return (
                f"https://modelscope.cn/api/v1/models/{ms_id}/repo"
                f"?Revision=master&FilePath={filename}"
            )

        return None

    def get_progress(self, task_id: str) -> DownloadProgress | None:
        """查询下载进度"""
        return self._tasks.get(task_id)

    def cancel_download(self, task_id: str):
        """取消下载"""
        progress = self._tasks.get(task_id)
        if progress:
            progress.state = DownloadState.CANCELLED

        downloader = self._downloaders.get(task_id)
        if downloader:
            downloader.cancel()

    def list_active_tasks(self) -> list[DownloadProgress]:
        """列出所有活跃的下载任务"""
        return [
            p for p in self._tasks.values()
            if p.state in (DownloadState.DOWNLOADING, DownloadState.VERIFYING)
        ]

    def on_progress(self, callback: Callable[[DownloadProgress], None]):
        """注册进度回调（用于 WebSocket 实时推送）"""
        self._on_progress = callback

    def _notify_progress(self, progress: DownloadProgress):
        """通知进度更新"""
        if self._on_progress:
            try:
                self._on_progress(progress)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")

    async def verify_model(self, model_name: str) -> bool:
        """验证已下载模型的完整性"""
        config = self._model_configs.get(model_name)
        if not config:
            return False

        model_dir = self.models_dir / model_name
        if not model_dir.exists():
            return False

        # 检查必需文件
        for file_info in config["files"]:
            if file_info["required"]:
                file_path = model_dir / file_info["filename"]
                if not file_path.exists():
                    logger.warning(f"Missing required file: {file_path}")
                    return False

        return True

    def delete_model(self, model_name: str) -> bool:
        """删除本地模型"""
        model_dir = self.models_dir / model_name
        if not model_dir.exists():
            return False

        import shutil
        shutil.rmtree(model_dir)
        logger.info(f"Deleted model: {model_name}")
        return True

    def get_disk_usage(self) -> dict[str, Any]:
        """获取模型存储磁盘使用情况"""
        total_bytes = 0
        models_detail = []

        for name in self._model_configs:
            model_dir = self.models_dir / name
            if model_dir.exists():
                size = sum(
                    f.stat().st_size
                    for f in model_dir.rglob("*")
                    if f.is_file()
                )
                total_bytes += size
                models_detail.append({
                    "name": name,
                    "size_bytes": size,
                    "size_gb": round(size / 1024 / 1024 / 1024, 2),
                })

        return {
            "total_bytes": total_bytes,
            "total_gb": round(total_bytes / 1024 / 1024 / 1024, 2),
            "models": models_detail,
        }


# ── 全局管理器单例 ────────────────────────────────────────

_global_downloader: ModelDownloadManager | None = None


def init_downloader(models_dir: str | Path = "models") -> ModelDownloadManager:
    """初始化全局下载管理器"""
    global _global_downloader
    _global_downloader = ModelDownloadManager(models_dir=models_dir)
    return _global_downloader


def get_downloader() -> ModelDownloadManager:
    """获取全局下载管理器"""
    global _global_downloader
    if _global_downloader is None:
        return init_downloader()
    return _global_downloader
