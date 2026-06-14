"""
第三方 API 统一代理

职责：
1. 在 ai_models 层提供统一的 API 调用入口
2. 适配 OpenAI / Anthropic / DeepSeek 等多厂商格式
3. 支持自动重试和超时处理
4. 与 backend 层的 ApiGateway 协同工作

设计理念：
  backend/api_gateway.py  — 负责密钥管理和调度策略
  ai_models/api_proxy.py  — 负责具体的 API 调用和格式转换
  两者通过 ICandidateModel 接口解耦
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger("ai_models.api_proxy")


# ── 数据类 ────────────────────────────────────────────────

@dataclass
class ApiProxyConfig:
    """API 代理配置"""
    provider: str                # openai | anthropic | deepseek | ...
    api_key: str
    base_url: str
    model: str
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout_seconds: float = 60.0


@dataclass
class ProxyResponse:
    """代理响应"""
    content: str
    model: str
    tokens_prompt: int = 0
    tokens_completion: int = 0
    tokens_total: int = 0
    finish_reason: str = "stop"
    latency_ms: int = 0


# ── OpenAI 兼容代理 ───────────────────────────────────────

class OpenAiCompatibleProxy:
    """
    OpenAI 兼容 API 代理

    适用于 OpenAI、Azure OpenAI、DeepSeek、智谱 GLM-4、通义千问 等
    所有兼容 OpenAI chat/completions 格式的 API。
    """

    def __init__(self, config: ApiProxyConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> ProxyResponse:
        """发送对话请求"""
        import time
        start = time.perf_counter()

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        client = self._get_client()

        for attempt in range(self.config.max_retries):
            try:
                resp = await client.post("/chat/completions", json=payload)
                resp.raise_for_status()
                data = resp.json()

                choice = data["choices"][0]
                usage = data.get("usage", {})

                return ProxyResponse(
                    content=choice["message"]["content"],
                    model=data.get("model", self.config.model),
                    tokens_prompt=usage.get("prompt_tokens", 0),
                    tokens_completion=usage.get("completion_tokens", 0),
                    tokens_total=usage.get("total_tokens", 0),
                    finish_reason=choice.get("finish_reason", "stop"),
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )

            except Exception as e:
                logger.warning(
                    f"API call attempt {attempt + 1}/{self.config.max_retries} "
                    f"failed: {e}"
                )
                if attempt >= self.config.max_retries - 1:
                    raise
                import asyncio
                await asyncio.sleep(self.config.retry_delay * (2 ** attempt))

        raise RuntimeError("Unreachable")

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """SSE 流式对话"""
        client = self._get_client()

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    import json
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        if "content" in delta:
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── Anthropic 代理 ────────────────────────────────────────

class AnthropicProxy:
    """Anthropic Claude API 代理"""

    def __init__(self, config: ApiProxyConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url.rstrip("/"),
                headers={
                    "x-api-key": self.config.api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01",
                },
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    async def chat(
        self,
        messages: list[dict[str, str]],
        system: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> ProxyResponse:
        """发送对话请求"""
        import time
        start = time.perf_counter()

        # Anthropic 格式：system 独立，messages 只需 role+content
        payload: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": m.get("role", "user"), "content": m["content"]}
                for m in messages
            ],
        }
        if system:
            payload["system"] = system

        client = self._get_client()
        resp = await client.post("/v1/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()

        return ProxyResponse(
            content=data["content"][0]["text"],
            model=data.get("model", self.config.model),
            tokens_prompt=data.get("usage", {}).get("input_tokens", 0),
            tokens_completion=data.get("usage", {}).get("output_tokens", 0),
            tokens_total=(
                data.get("usage", {}).get("input_tokens", 0)
                + data.get("usage", {}).get("output_tokens", 0)
            ),
            finish_reason=data.get("stop_reason", "stop"),
            latency_ms=int((time.perf_counter() - start) * 1000),
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── Replicate 代理 ───────────────────────────────────────

class ReplicateProxy:
    """Replicate API 代理 — 视频/图片生成"""

    def __init__(self, config: ApiProxyConfig):
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is None:
            import httpx
            self._client = httpx.AsyncClient(
                base_url="https://api.replicate.com",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(self.config.timeout_seconds),
            )
        return self._client

    async def create_prediction(
        self,
        model_version: str,
        input_data: dict,
    ) -> dict:
        """创建预测任务"""
        client = self._get_client()
        resp = await client.post("/v1/predictions", json={
            "version": model_version,
            "input": input_data,
        })
        resp.raise_for_status()
        return resp.json()

    async def get_prediction(self, prediction_id: str) -> dict:
        """查询预测状态"""
        client = self._get_client()
        resp = await client.get(f"/v1/predictions/{prediction_id}")
        resp.raise_for_status()
        return resp.json()

    async def wait_prediction(
        self,
        prediction_id: str,
        poll_interval: float = 2.0,
        timeout: float = 600.0,
    ) -> dict:
        """等待预测完成"""
        import asyncio
        import time

        start = time.time()
        while time.time() - start < timeout:
            result = await self.get_prediction(prediction_id)
            status = result.get("status")
            if status in ("succeeded", "failed", "canceled"):
                return result
            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Prediction {prediction_id} timed out after {timeout}s")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ── 代理工厂 ──────────────────────────────────────────────

def create_proxy(
    provider: str,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
) -> OpenAiCompatibleProxy | AnthropicProxy | ReplicateProxy:
    """工厂函数：根据提供商创建对应的代理"""

    default_models = {
        "openai": "gpt-4o",
        "azure": "gpt-4o",
        "deepseek": "deepseek-chat",
        "zhipu": "glm-4-plus",
        "qwen": "qwen-max",
        "anthropic": "claude-sonnet-4-20250514",
        "replicate": "cogvideox-5b",
        "ollama": "hf.co/unsloth/gemma-4-26B-A4B-it-GGUF:UD-Q4_K_M",
    }

    default_urls = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "zhipu": "https://open.bigmodel.cn/api/paas/v4",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "anthropic": "https://api.anthropic.com",
        "ollama": "http://localhost:11434/v1",
    }

    config = ApiProxyConfig(
        provider=provider,
        api_key=api_key,
        base_url=base_url or default_urls.get(provider, ""),
        model=model or default_models.get(provider, "default"),
    )

    if provider == "anthropic":
        return AnthropicProxy(config)
    elif provider == "replicate":
        return ReplicateProxy(config)
    else:
        # OpenAI 兼容格式
        return OpenAiCompatibleProxy(config)
