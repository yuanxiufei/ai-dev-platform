"""
llama.cpp Server Provider — 适配 llama.cpp 内置 HTTP Server

借鉴 llama.cpp tools/server 的 OpenAI 兼容 API：
- /v1/chat/completions (支持 function calling / JSON 模式 / 思考链)
- /v1/completions
- /v1/embeddings
- /v1/models

llama.cpp server 启动方式:
  ./llama-server -m models/7B/ggml-model.gguf -c 4096 --host 0.0.0.0 --port 18082

环境变量:
  LLAMA_CPP_BASE_URL=http://localhost:18082/v1
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from app.core.model_router import ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.llama_cpp")


class LlamaCppProvider(BaseProvider):
    """llama.cpp Server 本地推理适配器

    特性:
    - OpenAI 兼容 /v1/chat/completions
    - 支持 GGUF 量化模型
    - 支持 GPU 加速 (CUDA/Metal/Vulkan)
    - 支持连续批处理 (continuous batching)
    - 支持推测解码 (speculative decoding)
    - 支持 function calling / JSON 模式输出
    """

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self._get_model_name(request)
        messages = self._build_messages(request)

        payload: dict = {
            "model": model_name,
            "messages": messages,
            "max_tokens": request.max_tokens or 2048,
            "temperature": request.temperature or 0.7,
            "stream": False,
        }

        # ── Function Calling ──
        if request.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.get("name", ""),
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {}),
                    },
                }
                for t in request.tools
            ]
            if request.tool_choice:
                payload["tool_choice"] = request.tool_choice

        # ── JSON 模式输出 (llama.cpp 通过 grammar 支持) ──
        if request.response_format:
            payload["response_format"] = request.response_format

        resp = await self.client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()

        choice = data["choices"][0]
        msg = choice.get("message", {})

        return ModelResponse(
            content=msg.get("content", ""),
            model_used=data.get("model", model_name),
            provider="llama_cpp",
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=choice.get("finish_reason", "stop"),
            tool_calls=msg.get("tool_calls"),
        )

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """流式推理 — token-by-token 产出"""
        model_name = self._get_model_name(request)
        messages = self._build_messages(request)

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "max_tokens": request.max_tokens or 2048,
            "temperature": request.temperature or 0.7,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.tools:
            payload["tools"] = request.tools
            if request.tool_choice:
                payload["tool_choice"] = request.tool_choice

        async for token in self._parse_openai_sse_stream("/v1/chat/completions", payload):
            yield token

    def _build_headers(self) -> dict[str, str]:
        # llama.cpp server 默认无需认证，但支持可选 API key
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    async def health_check(self) -> bool:
        """检查 llama.cpp server 是否可达"""
        try:
            resp = await self.client.get("/v1/models")
            self.is_available = resp.status_code == 200
            return self.is_available
        except Exception:
            self.is_available = False
            return False

    async def get_models(self) -> list[dict]:
        """获取 llama.cpp server 当前加载的模型列表"""
        try:
            resp = await self.client.get("/v1/models")
            if resp.status_code == 200:
                return resp.json().get("data", [])
        except Exception:
            pass
        return []

    async def get_health_details(self) -> dict:
        """获取详细健康信息（含 slot 状态）"""
        result: dict = {"available": False, "models": [], "slots": None}
        try:
            resp = await self.client.get("/health")
            result["available"] = resp.status_code == 200
            result["health"] = resp.json() if resp.status_code == 200 else None
        except Exception:
            pass

        try:
            resp = await self.client.get("/slots")
            if resp.status_code == 200:
                result["slots"] = resp.json()
        except Exception:
            pass

        result["models"] = await self.get_models()
        return result

    async def get_metrics(self) -> dict | None:
        """获取 Prometheus 指标（需 llama-server --metrics）"""
        try:
            resp = await self.client.get("/metrics")
            if resp.status_code == 200:
                return {"raw": resp.text}
        except Exception:
            pass
        return None


class LlamaCppRerankerProvider:
    """llama.cpp Reranker — 利用 llama.cpp 的原生 /reranking 端点

    借鉴 llama.cpp 的 reranking API，需要 reranker 模型（如 bge-reranker）。
    """

    def __init__(self, base_url: str = "http://localhost:18082", api_key: str = ""):
        import httpx
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        )

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_n: int = 10,
    ) -> list[dict]:
        """调用 llama.cpp /reranking 进行重排序

        Returns:
            [{"index": int, "score": float, "text": str}, ...]
        """
        resp = await self.client.post("/reranking", json={
            "query": query,
            "documents": documents,
            "top_n": top_n,
        })
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        return [
            {
                "index": r["index"],
                "score": r["relevance_score"],
                "text": documents[r["index"]],
            }
            for r in sorted(results, key=lambda x: x["relevance_score"], reverse=True)[:top_n]
        ]

    async def close(self):
        await self.client.aclose()
