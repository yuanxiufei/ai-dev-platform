"""
通义千问 Provider — 适配阿里云 DashScope API（兼容 OpenAI 格式）

支持的模型: qwen-max, qwen-plus, qwen-turbo
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.core.model_router import ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.qwen")


class QwenProvider(BaseProvider):
    """通义千问 API 适配器（OpenAI 兼容格式，支持 Function Calling）"""

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
            provider="qwen",
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """流式推理 — token-by-token 产出（通义千问 OpenAI 兼容 SSE）"""
        model_name = self._get_model_name(request)
        messages = self._build_messages(request)

        body: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            body["tools"] = request.tools
            if request.tool_choice:
                body["tool_choice"] = request.tool_choice

        async for token in self._parse_openai_sse_stream("/chat/completions", body):
            yield token
