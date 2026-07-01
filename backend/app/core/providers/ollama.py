"""
Ollama Provider — 适配本地 Ollama 推理服务

支持的模型: 所有 ollama pull 的模型（如 gemma, llama, qwen 等）
Ollama 本地运行无需 API 密钥，base_url 指向本地服务即可。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import httpx

from app.core.model_router import ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.ollama")


class OllamaProvider(BaseProvider):
    """Ollama 本地推理服务适配器"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self._get_model_name(request)
        messages = self._build_messages(request)

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }

        # 传递 tools（如果请求中包含）
        if request.tools:
            payload["tools"] = request.tools

        try:
            resp = await self.client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            msg = choice["message"]
            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls", [])

            # 有 tool_calls 时强制 finish_reason = "tool_calls"
            finish_reason = "tool_calls" if tool_calls else choice.get("finish_reason", "stop")

            return ModelResponse(
                content=content,
                model_used=data.get("model", model_name),
                provider="ollama",
                tokens_used=data.get("usage", {}).get("total_tokens"),
                finish_reason=finish_reason,
                tool_calls=tool_calls,
            )
        except httpx.ConnectError as e:
            detail = (
                f"Ollama 服务未启动或不可达 ({self.config.base_url})。"
                f"请确保 Ollama 已安装并运行：ollama serve"
            )
            logger.error("Ollama CONNECT FAILED: %s → %s", e, detail)
            raise RuntimeError(detail) from e
        except httpx.TimeoutException as e:
            raise RuntimeError(
                f"Ollama 响应超时 ({self.config.base_url})。可能是模型加载中或硬件不足。"
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Ollama 返回 HTTP {e.response.status_code}: {e.response.text[:200]}"
            ) from e

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """流式推理 — token-by-token 产出"""
        model_name = self._get_model_name(request)
        messages = self._build_messages(request)

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            payload["tools"] = request.tools

        async for token in self._parse_openai_sse_stream("/v1/chat/completions", payload):
            yield token

    def _build_headers(self) -> dict[str, str]:
        # Ollama 本地运行无需认证
        return {"Content-Type": "application/json"}

    async def health_check(self) -> bool:
        """检查 Ollama 服务是否可达"""
        try:
            resp = await self.client.get("/v1/models")
            self.is_available = resp.status_code == 200
            return self.is_available
        except Exception:
            self.is_available = False
            return False
