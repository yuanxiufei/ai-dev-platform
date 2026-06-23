"""
OpenAI Provider — 适配 OpenAI Chat Completions API

支持的模型: gpt-4o, gpt-4-turbo, gpt-3.5-turbo, o1, o3
"""

from __future__ import annotations

import base64
import logging

from app.core.model_router import ModelCapability, ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.openai")


class OpenAIProvider(BaseProvider):
    """OpenAI API 适配器 —— 支持 Function Calling"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self._get_model_name(request)
        msgs: list[dict] = self._build_messages(request)

        # 处理视觉输入
        if request.images and request.capability == ModelCapability.VISION_LANGUAGE:
            msgs = self._build_vision_messages(request)

        body: dict = {
            "model": model_name,
            "messages": msgs,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }

        # ── 工具/Function Calling ──
        if request.tools:
            body["tools"] = request.tools
            if request.tool_choice:
                body["tool_choice"] = request.tool_choice

        resp = await self.client.post("/v1/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")

        # ── 解析 tool_calls ──
        tool_calls: list[dict] = []
        if finish_reason == "tool_calls" and "tool_calls" in message:
            tool_calls = [
                {
                    "id": tc["id"],
                    "type": tc.get("type", "function"),
                    "function": {
                        "name": tc["function"]["name"],
                        "arguments": tc["function"]["arguments"],
                    },
                }
                for tc in message["tool_calls"]
            ]
            logger.info(
                "OpenAI tool_calls returned: %s",
                [tc["function"]["name"] for tc in tool_calls],
            )

        return ModelResponse(
            content=message.get("content") or "",
            model_used=data.get("model", model_name),
            provider="openai",
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    def _build_vision_messages(self, request: ModelRequest) -> list[dict]:
        """构建多模态消息（视觉理解）"""
        msgs: list[dict] = []
        if request.system_prompt:
            msgs.append({"role": "system", "content": request.system_prompt})

        content: list[dict] = [{"type": "text", "text": request.prompt}]
        for img in (request.images or []):
            b64 = base64.b64encode(img).decode()
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64}",
                    "detail": "high",
                },
            })
        msgs.append({"role": "user", "content": content})

        if request.history:
            msgs.extend(request.history)
        return msgs
