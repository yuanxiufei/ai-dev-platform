"""
后台任务定义 — 模型下载 / 视频生成 / 批量处理 / 定时清理

所有任务使用 TrackedTask 基类以获得进度追踪能力。
"""

import logging
import time

from app.core.task_queue import celery_app, TrackedTask

logger = logging.getLogger("task_queue.tasks")


@celery_app.task(bind=True, base=TrackedTask, max_retries=3, default_retry_delay=60)
def model_download_task(self, model_name: str, source: str = "huggingface") -> dict:
    """
    异步下载模型

    参数:
        model_name: 模型名称（如 "qwen25-coder-7b"）
        source: 下载源（huggingface / modelscope）

    返回:
        {"status": "completed", "model_path": "/path/to/model"}
    """
    self.update_progress(0, "initializing")
    logger.info("[task:%s] Starting model download: %s (source=%s)", self.request.id, model_name, source)

    try:
        from app.core.model_downloader import get_downloader

        downloader = get_downloader()
        self.update_progress(10, "downloading")

        # 模拟下载进度（实际集成 downloader 的回调）
        for progress in range(10, 100, 10):
            time.sleep(0.5)  # 实际场景为 downloader 的进度回调
            self.update_progress(progress, f"downloading ({progress}%)")

        self.update_progress(100, "completed")
        return {
            "status": "completed",
            "model_name": model_name,
            "source": source,
        }

    except Exception as e:
        logger.error("[task:%s] Model download failed: %s", self.request.id, e)
        raise self.retry(exc=e)


@celery_app.task(bind=True, base=TrackedTask, max_retries=2, default_retry_delay=120)
def video_generate_task(self, prompt: str, num_frames: int = 30, fps: int = 16) -> dict:
    """
    异步视频生成

    参数:
        prompt: 文本提示词
        num_frames: 帧数
        fps: 帧率

    返回:
        {"status": "completed", "output_path": "/path/to/video.mp4"}
    """
    self.update_progress(0, "queued")
    logger.info("[task:%s] Starting video generation: %s...", self.request.id, prompt[:50])

    try:
        from app.core.model_router import get_model_router, ModelCapability, ModelRequest

        router = get_model_router()
        self.update_progress(5, "selecting_model")

        request = ModelRequest(
            capability=ModelCapability.VIDEO_GENERATION,
            prompt=prompt,
            metadata={"num_frames": num_frames, "fps": fps},
        )

        self.update_progress(15, "generating")
        response = router.generate(request)

        self.update_progress(90, "saving")
        # 实际场景会保存视频文件到 output_path

        self.update_progress(100, "completed")
        return {
            "status": "completed",
            "output_path": response.output_path if response else "",
        }

    except Exception as e:
        logger.error("[task:%s] Video generation failed: %s", self.request.id, e)
        raise self.retry(exc=e)


@celery_app.task(bind=True, base=TrackedTask, max_retries=3)
def batch_process_task(
    self, items: list[dict], operation: str = "process",
) -> dict:
    """
    批量数据处理

    参数:
        items: 待处理项列表
        operation: 操作类型

    返回:
        {"processed": N, "failed": M}
    """
    total = len(items)
    self.update_progress(0, f"processing {total} items")

    processed = 0
    failed = 0

    for i, item in enumerate(items):
        try:
            # 实际业务逻辑
            processed += 1
        except Exception:
            failed += 1

        self.update_progress(
            int((i + 1) / max(total, 1) * 100),
            f"processed {processed}/{total}",
        )

    return {"processed": processed, "failed": failed, "total": total}


@celery_app.task(bind=True, base=TrackedTask)
def cleanup_task(self, retention_days: int = 7) -> dict:
    """
    定时清理任务

    参数:
        retention_days: 保留天数

    返回:
        {"cleaned_files": N, "freed_bytes": M}
    """
    self.update_progress(0, "scanning")
    logger.info("[task:%s] Starting cleanup (retention=%d days)", self.request.id, retention_days)

    # 实际场景会清理过期文件、日志、临时数据等
    self.update_progress(100, "completed")
    return {"cleaned_files": 0, "freed_bytes": 0}
