"""
Ollama Provider — 适配本地 Ollama 推理服务

支持的模型: 所有 ollama pull 的模型（如 gemma, llama, qwen 等）
Ollama 本地运行无需 API 密钥，base_url 指向本地服务即可。
"""

from __future__ import annotations

import logging

import httpx

from app.core.model_router import ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.ollama")


class OllamaProvider(BaseProvider):
    """Ollama 本地推理服务适配器"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self._get_model_name(request)
        messages = self._build_messages(request)

        try:
            resp = await self.client.post("/v1/chat/completions", json={
                "model": model_name,
                "messages": messages,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "stream": False,
            })
            resp.raise_for_status()
            data = resp.json()

            return ModelResponse(
                content=data["choices"][0]["message"]["content"],
                model_used=data.get("model", model_name),
                provider="ollama",
                tokens_used=data.get("usage", {}).get("total_tokens"),
                finish_reason=data["choices"][0].get("finish_reason", "stop"),
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
