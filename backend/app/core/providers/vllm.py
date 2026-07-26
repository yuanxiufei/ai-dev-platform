"""
vLLM Provider — 适配 vLLM OpenAI 兼容 Server

Docker 服务（compose.shared.yml）：
  vllm 容器运行在 3080 端口，提供标准 /v1/chat/completions 端点
  加载模型: Qwen3.6-27B-int4-AutoRound (AutoRound 量化)

特点：
- 完全兼容 OpenAI Chat Completions API
- 无需认证（本地 Docker 服务）
- 支持 Function Calling / Tool Choice
- 可通过 /v1/models 查询已加载模型
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.core.model_router import ModelCapability, ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.vllm")


class VLLMProvider(BaseProvider):
    """vLLM Docker 推理适配器

    复用 OpenAI 兼容协议，默认基地址 http://localhost:3080
    无需 API Key，通过 env VLLM_BASE_URL 可自定义端点
    """

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self._get_model_name(request)
        msgs: list[dict] = self._build_messages(request)

        # 处理视觉输入
        if request.images and request.capability == ModelCapability.VISION_LANGUAGE:
            import base64
            msgs = []
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

        body: dict = {
            "model": model_name,
            "messages": msgs,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
        }

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

        return ModelResponse(
            content=message.get("content") or "",
            model_used=data.get("model", model_name),
            provider="vllm",
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """流式推理 — token-by-token 产出"""
        model_name = self._get_model_name(request)
        msgs: list[dict] = self._build_messages(request)

        body: dict[str, Any] = {
            "model": model_name,
            "messages": msgs,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            body["tools"] = request.tools
            if request.tool_choice:
                body["tool_choice"] = request.tool_choice

        async for token in self._parse_openai_sse_stream("/v1/chat/completions", body):
            yield token

    def _build_headers(self) -> dict[str, str]:
        """vLLM 本地服务无需 Authorization 头"""
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def health_check(self) -> bool:
        """检查 vLLM 服务是否可达"""
        try:
            resp = await self.client.get("/v1/models")
            self.is_available = resp.status_code == 200
            return self.is_available
        except Exception:
            self.is_available = False
            return False

    async def get_models(self) -> list[dict]:
        """获取 vLLM 当前加载的模型列表"""
        try:
            resp = await self.client.get("/v1/models")
            if resp.status_code == 200:
                return resp.json().get("data", [])
        except Exception:
            pass
        return []

    def sync_models_sync(self) -> list[str]:
        """同步拉取 vLLM 已加载模型列表（启动时自动发现用）"""
        try:
            import httpx
            resp = httpx.get(
                f"{self.config.base_url}/v1/models",
                timeout=5.0,
                trust_env=False,
            )
            if resp.status_code == 200:
                data = resp.json()
                models = [m["id"] for m in data.get("data", [])]
                if models:
                    self.config.models = models
                    logger.info("vLLM auto-discovered %d models: %s", len(models), models)
                    return models
            logger.debug("vLLM GET /v1/models returned %s, keeping hardcoded list", resp.status_code)
        except Exception as e:
            logger.debug("vLLM sync_models_sync() skipped (%s), keeping hardcoded list", e)
        return list(self.config.models)

    async def sync_models(self) -> list[str]:
        """异步拉取 vLLM 已加载模型列表（API 刷新用）"""
        models_data = await self.get_models()
        return [m["id"] for m in models_data] if models_data else list(self.config.models)

    async def get_health_details(self) -> dict:
        """获取详细健康信息"""
        result: dict = {"available": False, "models": []}
        try:
            resp = await self.client.get("/health")
            result["available"] = resp.status_code == 200
        except Exception:
            pass
        try:
            result["models"] = await self.get_models()
        except Exception:
            pass
        return result
