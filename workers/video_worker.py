"""
Video Generation Worker - Handles AI video generation tasks.

Uses:
  - CogVideoX for text/image-to-video generation
"""

import logging
from queue.celery_app import celery_app

logger = logging.getLogger(__name__)

# 延迟加载
_video_model = None


def _get_video_model():
    global _video_model
    if _video_model is None:
        from ai_models.video_model import get_video_model
        model = get_video_model()
        if model:
            model.load()
        _video_model = model
    return _video_model


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def generate_video(self, task_id: str, prompt: str,
                   num_frames: int = 48, fps: int = 8):
    """
    Generate video from text prompt using CogVideoX.

    流程: 文本 → CogVideoX → 视频文件
    """
    logger.info(f"[{task_id}] Video generation: '{prompt[:60]}...'")

    try:
        video = _get_video_model()
        if video and video.is_loaded:
            result = video.generate_video(
                prompt=prompt,
                num_frames=num_frames,
                fps=fps,
            )
        else:
            result = {
                "task_id": task_id,
                "status": "pending",
                "video_path": f"/output/videos/{task_id}.mp4",
                "duration": num_frames / fps,
                "resolution": "720x480",
            }
            logger.warning(f"[{task_id}] Video model not available, using placeholder")

        result["task_id"] = task_id
        result["status"] = result.get("status", "completed")
        logger.info(f"[{task_id}] Video generation done: {result.get('video_path')}")
        return result

    except Exception as exc:
        logger.error(f"[{task_id}] Video generation failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
def generate_ui_demo_video(self, task_id: str, code_snippet: str,
                            duration: float = 10.0):
    """
    Generate a demo video showing UI rendered from code.

    流程: UI代码 → 渲染 → CogVideoX 录屏 → 视频
    """
    logger.info(f"[{task_id}] UI demo video, duration={duration}s")

    try:
        video = _get_video_model()
        if video and video.is_loaded:
            result = video.generate_ui_demo(
                code_snippet=code_snippet,
                task_id=task_id,
                duration=duration,
            )
        else:
            result = {
                "task_id": task_id,
                "status": "pending",
                "video_path": f"/output/demos/{task_id}.mp4",
                "duration": duration,
            }
            logger.warning(f"[{task_id}] Video model not available")

        result["task_id"] = task_id
        logger.info(f"[{task_id}] UI demo video done")
        return result

    except Exception as exc:
        logger.error(f"[{task_id}] UI demo video failed: {exc}")
        raise self.retry(exc=exc)
