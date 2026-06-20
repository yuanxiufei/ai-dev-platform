"""
Replicate Provider — 适配 Replicate API（视频/图片生成）

支持的模型: cogvideox-5b, stable-video-diffusion, meta/llama 等
"""

from __future__ import annotations

import json
import logging

from app.core.model_router import ModelCapability, ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.replicate")


class ReplicateProvider(BaseProvider):
    """Replicate API 适配器"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        if request.capability == ModelCapability.VIDEO_GENERATION:
            return await self._generate_video(request)
        return await self._generate_text(request)

    async def _generate_video(self, request: ModelRequest) -> ModelResponse:
        model_ref = request.extra_params.get("replicate_model", "lucataco/cogvideox-5b:xxx")

        resp = await self.client.post("/v1/predictions", json={
            "version": model_ref,
            "input": {
                "prompt": request.prompt,
                "num_frames": request.extra_params.get("num_frames", 49),
                "fps": request.extra_params.get("fps", 8),
                "num_inference_steps": request.extra_params.get("num_inference_steps", 50),
            },
        })
        resp.raise_for_status()
        data = resp.json()

        return ModelResponse(
            content=json.dumps({
                "type": "video_generation",
                "prediction_id": data.get("id"),
                "status": data.get("status"),
                "output_url": data.get("output"),
            }),
            model_used=model_ref,
            provider="replicate",
            finish_reason="pending" if data.get("status") == "processing" else "stop",
            metadata={"prediction_id": data.get("id")},
        )

    async def _generate_text(self, request: ModelRequest) -> ModelResponse:
        model_ref = request.extra_params.get("replicate_model", "meta/llama-3-70b-instruct")

        resp = await self.client.post("/v1/predictions", json={
            "version": model_ref,
            "input": {
                "prompt": request.prompt,
                "system_prompt": request.system_prompt or "",
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
        })
        resp.raise_for_status()
        data = resp.json()

        return ModelResponse(
            content="".join(data.get("output", [])),
            model_used=model_ref,
            provider="replicate",
            finish_reason="stop",
        )

    def _build_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
