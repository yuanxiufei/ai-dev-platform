"""
Code Generation Worker — 代码生成异步任务

自动按 priority 选择最优代码生成模型（safetensors 或 GGUF 均可）。
"""

import logging
from queue.celery_app import celery_app
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
                                  include_backend: bool = True):
    """文本 → Coder → 前端 + 后端代码"""
    logger.info(f"[{task_id}] Fullstack: '{description[:80]}...'")

    try:
        coder = _get_coder_model()
        if coder and coder.is_loaded:
            output = coder.generate_fullstack(
                description,
                framework="react",
                include_backend=include_backend,
            )
        else:
            output = {"frontend": {}, "backend": {} if include_backend else None}

        return {
            "task_id": task_id,
            "status": "completed",
            "coder": repr(coder) if coder else "none",
            "frontend": output.get("frontend"),
            "backend": output.get("backend"),
        }
    except Exception as exc:
        logger.error(f"[{task_id}] Failed: {exc}")
        raise self.retry(exc=exc)


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
