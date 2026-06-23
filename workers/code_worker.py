"""
Code Generation Worker — 代码生成异步任务

自动按 priority 选择最优代码生成模型（safetensors 或 GGUF 均可）。
"""

import logging
from task_queue.celery_app import celery_app
from ai_models.registry import list_by_type, ModelType
from ai_models.coder_model import CodeGenerationModel

logger = logging.getLogger(__name__)

# 延迟加载
_vl_model = None
_coder_model = None
_CODER_LOAD_ATTEMPTED = False


def _get_vl_model():
    global _vl_model
    if _vl_model is None:
        from ai_models.vl_model import get_vl_model
        model = get_vl_model()
        if model:
            model.load()
        _vl_model = model
    return _vl_model


def _get_coder_model():
    """按 priority 降序尝试加载，选第一个可用的。"""
    global _coder_model, _CODER_LOAD_ATTEMPTED
    if _coder_model is not None:
        return _coder_model
    if _CODER_LOAD_ATTEMPTED:
        return None

    _CODER_LOAD_ATTEMPTED = True
    coders = sorted(list_by_type(ModelType.CODE_GENERATION),
                    key=lambda c: c.priority, reverse=True)

    for cfg in coders:
        logger.info(f"Trying coder: {cfg.display_name} [{cfg.model_format.value}]")
        try:
            model = CodeGenerationModel(cfg)
            model.load()
            if model.is_loaded:
                _coder_model = model
                logger.info(f"✅ Using coder: {cfg.display_name}")
                return _coder_model
            else:
                logger.warning(f"⚠ Skipped {cfg.display_name} (load failed)")
        except Exception as e:
            logger.warning(f"⚠ Skipped {cfg.display_name}: {e}")

    logger.error("No code generation model available")
    return None


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_code_from_screenshot(self, task_id: str, image_url: str,
                                   target_framework: str = "vue"):
    """截图 → VL 分析布局 → Coder 生成代码"""
    logger.info(f"[{task_id}] Code generation from screenshot: {image_url}")

    try:
        # Step 1: VL 分析截图
        vl = _get_vl_model()
        if vl and vl.is_loaded:
            layout = vl.analyze_screenshot(image_url)
            logger.info(f"[{task_id}] Layout done, page={layout.get('page')}")
        else:
            layout = {"page": "placeholder", "layout": "flex", "components": []}

        # Step 2: 最优 Coder 生成代码
        coder = _get_coder_model()
        if coder and coder.is_loaded:
            files = coder.generate_code(layout, framework=target_framework)
        else:
            files = {"README.md": "# No coder model available"}

        return {
            "task_id": task_id,
            "status": "completed",
            "framework": target_framework,
            "coder": repr(coder) if coder else "none",
            "files": files,
        }
    except Exception as exc:
        logger.error(f"[{task_id}] Failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def generate_fullstack_from_text(self, task_id: str, description: str,
                                  include_backend: bool = True,
                                  framework: str = "react"):
    """文本 → Coder → 前端 + 后端代码 → 更新项目记录。

    task_id 对应 StudioProject.id，执行完成后会自动更新项目的
    generated_code 和 status 字段。
    """
    import json as _json
    import uuid
    from pathlib import Path
    import sys

    # 确保 backend 在 Python path 中
    backend_path = str(Path(__file__).resolve().parent.parent / "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    logger.info(f"[{task_id}] Fullstack: '{description[:80]}...' framework={framework}")

    try:
        coder = _get_coder_model()
        if coder and coder.is_loaded:
            output = coder.generate_fullstack(
                description,
                framework=framework,
                include_backend=include_backend,
            )
        else:
            # 回退：使用 model_router（API 网关）
            output = _generate_via_router(description, framework, include_backend)

        # 更新数据库中的项目记录
        try:
            _update_project_in_db(task_id, output, "completed")
        except Exception as db_err:
            logger.warning(f"[{task_id}] Failed to update project in DB: {db_err}")

        return {
            "task_id": task_id,
            "status": "completed",
            "coder": repr(coder) if coder else "fallback_router",
            "frontend": output.get("frontend"),
            "backend": output.get("backend"),
        }
    except Exception as exc:
        logger.error(f"[{task_id}] Failed: {exc}")
        try:
            _update_project_in_db(task_id, {}, "failed")
        except Exception:
            pass
        raise self.retry(exc=exc)


def _generate_via_router(description: str, framework: str, include_backend: bool) -> dict:
    """通过 ModelRouter (API 网关) 生成代码（不依赖本地模型）。"""
    import asyncio

    async def _run():
        from app.core.model_router import ModelRequest, ModelCapability, get_model_router

        stack = "fastapi+vue" if include_backend else framework
        request = ModelRequest(
            capability=ModelCapability.CODE_GENERATION,
            prompt=description,
            system_prompt=(
                f"你是一个全栈开发专家。请生成完整的 {stack} 项目。"
                f"前端使用 {framework}。"
                "返回 JSON 格式：{\"frontend\": \"前端代码\", \"backend\": \"后端代码\"}"
            ),
        )
        router = get_model_router()
        response = await router.generate(request)
        return {
            "frontend": response.content,
            "backend": response.content if include_backend else None,
        }

    return asyncio.run(_run())


def _update_project_in_db(project_id: str, output: dict, status: str) -> None:
    """更新数据库中的项目记录。"""
    import json as _json
    import uuid
    from sqlmodel import Session

    from app.core.db import engine
    from app.models.studio_models import StudioProject, ProjectStatus

    try:
        pid = uuid.UUID(project_id)
    except (ValueError, AttributeError):
        return

    with Session(engine) as session:
        project = session.get(StudioProject, pid)
        if not project:
            return

        if status == "completed":
            project.generated_code = _json.dumps({
                "files": {
                    "frontend/App.vue": output.get("frontend", ""),
                    "backend/main.py": output.get("backend", "") if output.get("backend") else "",
                }
            }, ensure_ascii=False)
            project.status = ProjectStatus.DRAFT
        elif status == "failed":
            project.status = ProjectStatus.FAILED
            project.build_log = "AI generation failed"

        session.add(project)
        session.commit()


@celery_app.task(bind=True)
def list_available_models(self):
    """返回所有已注册模型 + 当前使用的 coder"""
    models = []
    for mt in ModelType:
        configs = list_by_type(mt)
        models.extend([c.to_dict() for c in configs])
    coder = _coder_model
    return {
        "models": models,
        "count": len(models),
        "active_coder": repr(coder) if coder else None,
    }
