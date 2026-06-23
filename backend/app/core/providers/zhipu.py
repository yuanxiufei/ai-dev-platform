"""
智谱 GLM-4 Provider — 适配智谱大模型 API（兼容 OpenAI 格式）

支持的模型: glm-4-plus, glm-4v
"""

from __future__ import annotations

import logging

from app.core.model_router import ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.zhipu")


class ZhipuProvider(BaseProvider):
    """智谱 GLM-4 API 适配器（OpenAI 兼容格式，支持 Function Calling）"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self._get_model_name(request)
        messages = self._build_messages(request)

        body: dict = {
            "model": model_name,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }

        if request.tools:
            body["tools"] = request.tools
            if request.tool_choice:
                body["tool_choice"] = request.tool_choice

        resp = await self.client.post("/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")

        tool_calls: list[dict] = []
        if finish_reason == "tool_calls" and "tool_calls" in message:
            tool_calls = message["tool_calls"]

        return ModelResponse(
            content=message.get("content") or "",
            model_used=data.get("model", model_name),
            provider="zhipu",
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )
