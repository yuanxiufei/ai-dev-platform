"""
Video — 生成 API

提供视频生成的完整管理：
  - 发起生成任务（文本→视频）
  - 查询任务状态
  - WebSocket 实时进度推送

生成流程：
  1. 用户提交文本提示词
  2. 通过 ModelRouter 调度最优视频生成模型
  3. 本地 CogVideoX → Replicate API → 内置兜底
  4. 异步执行 + 实时进度反馈
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models.video_models import VideoTask, TaskStatus

router = APIRouter(prefix="/videos/generate", tags=["video-generate"])


# ── Schemas ──────────────────────────────────────────────

class GenerateRequest(BaseModel):
    """视频生成请求"""
    prompt: str = Field(..., min_length=10, max_length=5000)
    model_name: str | None = None
    num_frames: int = Field(default=49, ge=8, le=200)
    fps: int = Field(default=8, ge=4, le=30)
    num_inference_steps: int = Field(default=50, ge=10, le=100)
    seed: int | None = None
    style: str = "cinematic"  # cinematic | animation | product_demo | tutorial


# ── 生成 ────────────────────────────────────────────────

@router.post("", status_code=202)
async def generate_video(
    gen_in: GenerateRequest,
    session: SessionDep,
    user: CurrentUser,
):
    """
    发起视频生成任务

    返回 task_id 用于后续查询状态
    """
    # 确定使用的模型
    model_name = gen_in.model_name

    if not model_name:
        # 自动选择最优视频生成模型
        from app.core.model_router import get_model_router, ModelRequest, ModelCapability

        try:
            router = get_model_router()
            # 使用调度器查询最优模型
            from ai_models.scheduler import get_scheduler
            scheduler = get_scheduler()
            model_name = scheduler.get_best_model("video_gen") or "cogvideox-5b"
        except Exception:
            model_name = "cogvideox-5b"

    # 创建任务记录
    task = VideoTask(
        prompt=gen_in.prompt,
        model_name=model_name,
        params={
            "num_frames": gen_in.num_frames,
            "fps": gen_in.fps,
            "num_inference_steps": gen_in.num_inference_steps,
            "seed": gen_in.seed,
            "style": gen_in.style,
        },
        status=TaskStatus.PENDING,
        owner_id=user.id,
    )
    session.add(task)
    session.commit()
    session.refresh(task)

    # 异步执行生成
    import asyncio
    asyncio.create_task(
        _execute_generation(task.id, gen_in, session)
    )

    return {
        "task_id": str(task.id),
        "status": "pending",
        "model_name": model_name,
        "prompt": gen_in.prompt[:100],
    }


async def _execute_generation(
    task_id: uuid.UUID,
    gen_in: GenerateRequest,
    db_session: Any,
):
    """后台执行视频生成"""
    import time

    task = db_session.get(VideoTask, task_id)
    if not task:
        return

    try:
        # 更新状态
        task.status = TaskStatus.GENERATING
        task.progress = 10
        db_session.add(task)
        db_session.commit()

        # 通过 ModelRouter 调度
        from app.core.model_router import get_model_router, ModelRequest, ModelCapability

        request = ModelRequest(
            capability=ModelCapability.VIDEO_GENERATION,
            prompt=gen_in.prompt,
            extra_params={
                "num_frames": gen_in.num_frames,
                "fps": gen_in.fps,
                "num_inference_steps": gen_in.num_inference_steps,
                "seed": gen_in.seed,
                "style": gen_in.style,
            },
        )

        router = get_model_router()
        response = await router.generate(request)

        # 更新进度
        task.progress = 80
        db_session.add(task)
        db_session.commit()

        # 模拟输出路径（实际应由模型返回）
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.output_path = f"/videos/{task_id}.mp4"
        task.thumbnail_path = f"/thumbnails/{task_id}.jpg"
        task.duration = (gen_in.num_frames / gen_in.fps)
        db_session.add(task)
        db_session.commit()

    except Exception as e:
        task = db_session.get(VideoTask, task_id)
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            db_session.add(task)
            db_session.commit()


@router.get("/{task_id}")
def get_task_status(
    task_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
):
    """查询生成任务状态"""
    task = session.get(VideoTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return {
        "task_id": str(task.id),
        "prompt": task.prompt[:200],
        "model_name": task.model_name,
        "status": task.status.value,
        "progress": task.progress,
        "output_path": task.output_path,
        "thumbnail_path": task.thumbnail_path,
        "duration": task.duration,
        "error_message": task.error_message,
        "created_at": task.created_at.isoformat(),
    }


# ── WebSocket 实时进度 ──────────────────────────────────

@router.websocket("/{task_id}/ws")
async def task_progress_ws(
    websocket: WebSocket,
    task_id: uuid.UUID,
):
    """WebSocket 实时推送生成进度"""
    await websocket.accept()

    try:
        import asyncio

        last_progress = -1
        while True:
            # 从数据库读取最新状态
            from app.core.db import engine
            from sqlmodel import Session

            with Session(engine) as session:
                task = session.get(VideoTask, task_id)
                if not task:
                    await websocket.send_json({"error": "Task not found"})
                    break

                current_progress = task.progress

                if current_progress != last_progress:
                    await websocket.send_json({
                        "task_id": str(task.id),
                        "status": task.status.value,
                        "progress": task.progress,
                        "output_path": task.output_path,
                        "error_message": task.error_message,
                    })
                    last_progress = current_progress

                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    await websocket.send_json({
                        "task_id": str(task.id),
                        "status": task.status.value,
                        "done": True,
                        "output_path": task.output_path,
                    })
                    break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"error": str(e)})
