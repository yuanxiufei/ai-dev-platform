"""
图像生成 API — DALL-E / Stability / ComfyUI 三引擎统一接口

借鉴 Open WebUI Images 集成
路径: /image-gen/*
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.providers.image_gen import (
    ImageGenOrchestrator,
    ImageGenRequest,
    ImageGenResponse,
    ImageSize,
    ImageStyle,
)

router = APIRouter(prefix="/image-gen", tags=["Image Generation"])


# ── Request Models ────────────────────────────────

class GenerateImageRequest(BaseModel):
    """图像生成请求"""
    prompt: str = Field(..., description="图像描述文本", min_length=1, max_length=4000)
    negative_prompt: str = Field(default="", description="负面提示词")
    size: ImageSize = Field(default=ImageSize.S_1024, description="图像尺寸")
    style: ImageStyle = Field(default=ImageStyle.NATURAL, description="图像风格")
    n: int = Field(default=1, ge=1, le=4, description="生成数量")
    quality: str = Field(default="standard", description="质量级别 (standard|hd)")
    seed: int | None = Field(default=None, description="随机种子")
    steps: int = Field(default=30, ge=10, le=100, description="SD 采样步数")
    cfg_scale: float = Field(default=7.0, ge=1.0, le=20.0, description="SD CFG scale")
    engine: str = Field(default="", description="指定引擎: dalle | stability | comfyui（留空自动选择）")
    model: str = Field(default="", description="引擎指定模型名")


class BatchGenerateRequest(BaseModel):
    """批量图像生成请求"""
    prompts: list[str] = Field(..., min_length=1, max_length=10, description="多个 prompt")
    size: ImageSize = Field(default=ImageSize.S_1024)
    engine: str = ""


# ── 全局 orchestartor ────────────────────────────

_orchestrator: ImageGenOrchestrator | None = None


def get_orchestrator() -> ImageGenOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ImageGenOrchestrator(
            dalle_key=settings.OPENAI_API_KEY,
            stability_key=getattr(settings, 'STABILITY_API_KEY', ''),
            comfyui_url=getattr(settings, 'COMFYUI_BASE_URL', ''),
        )
    return _orchestrator


# ── Routes ────────────────────────────────────────

@router.get("/providers")
async def list_providers() -> dict[str, Any]:
    """列出可用的图像生成 Provider"""
    orch = get_orchestrator()
    return {"providers": orch.get_available_providers()}


@router.post("/generate")
async def generate_image(req: GenerateImageRequest) -> dict[str, Any]:
    """生成图像"""
    orch = get_orchestrator()
    gen_req = ImageGenRequest(
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        size=req.size,
        style=req.style,
        n=req.n,
        quality=req.quality,
        seed=req.seed,
        steps=req.steps,
        cfg_scale=req.cfg_scale,
        extra={"model": req.model} if req.model else {},
    )

    try:
        result = await orch.generate(gen_req, preferred_engine=req.engine)
        return {
            "images": [
                {
                    "url": img.url,
                    "b64_json": img.b64_json,
                    "local_path": img.local_path,
                    "revised_prompt": img.revised_prompt,
                    "seed": img.seed,
                    "width": img.width,
                    "height": img.height,
                }
                for img in result.images
            ],
            "provider_used": result.provider_used,
            "latency_ms": result.latency_ms,
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/batch-generate")
async def batch_generate(req: BatchGenerateRequest) -> dict[str, Any]:
    """批量生成图像（最多10个 prompt）"""
    orch = get_orchestrator()
    results: list[dict[str, Any]] = []

    for prompt in req.prompts:
        gen_req = ImageGenRequest(prompt=prompt, size=req.size, n=1)
        try:
            result = await orch.generate(gen_req, preferred_engine=req.engine)
            results.append({
                "prompt": prompt,
                "success": True,
                "image": {
                    "url": result.images[0].url if result.images else "",
                    "b64_json": result.images[0].b64_json if result.images else "",
                },
                "provider_used": result.provider_used,
            })
        except Exception as e:
            results.append({"prompt": prompt, "success": False, "error": str(e)})

    return {"results": results, "total": len(req.prompts), "successful": sum(1 for r in results if r["success"])}
