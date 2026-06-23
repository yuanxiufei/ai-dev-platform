"""
DeepSeek Provider — 适配 DeepSeek Chat API（兼容 OpenAI 格式）

支持的模型: deepseek-chat, deepseek-coder
"""

from __future__ import annotations

import logging
import socket

import httpx

from app.core.model_router import ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.deepseek")


class DeepSeekProvider(BaseProvider):
    """DeepSeek API 适配器（OpenAI 兼容格式，支持 Function Calling）"""

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

        logger.info(
            "DeepSeek calling: base_url=%s model=%s key=%s",
            self.config.base_url,
            model_name,
            "***" + self.config.api_key[-4:] if len(self.config.api_key) > 4 else "(none)",
        )

        try:
            resp = await self.client.post("/v1/chat/completions", json=body)
            logger.info("DeepSeek response: status=%d", resp.status_code)
            resp.raise_for_status()
            data = resp.json()
        except httpx.ConnectError as e:
            detail = _describe_connect_error(e, self.config.base_url)
            logger.error("DeepSeek CONNECT FAILED: %s", detail)
            raise RuntimeError(detail) from e
        except httpx.TimeoutException as e:
            logger.error("DeepSeek TIMEOUT: %s", e)
            raise RuntimeError(f"DeepSeek API 超时（>60s），可能是网络延迟过高。目标: {self.config.base_url}") from e
        except httpx.HTTPStatusError as e:
            logger.error("DeepSeek HTTP %d: %s", e.response.status_code, e.response.text[:300])
            raise RuntimeError(f"DeepSeek API 返回 HTTP {e.response.status_code}") from e
        except Exception as e:
            logger.error("DeepSeek API call FAILED: %s", e)
            import traceback
            logger.error("DeepSeek traceback: %s", traceback.format_exc())
            raise

        choice = data["choices"][0]
        message = choice["message"]
        finish_reason = choice.get("finish_reason", "stop")

        tool_calls: list[dict] = []
        if finish_reason == "tool_calls" and "tool_calls" in message:
            tool_calls = message["tool_calls"]

        logger.info("DeepSeek success: content_len=%d tokens=%s", len(message.get("content") or ""), data.get("usage", {}).get("total_tokens", "?"))

        return ModelResponse(
            content=message.get("content") or "",
            model_used=data.get("model", model_name),
            provider="deepseek",
            tokens_used=data.get("usage", {}).get("total_tokens"),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )


def _describe_connect_error(err: httpx.ConnectError, base_url: str) -> str:
    """诊断连接错误，返回人类友好描述"""
    raw = str(err)
    base_url_lower = base_url.lower()

    # DNS 解析失败
    if "getaddrinfo" in raw.lower() or "name or service not known" in raw.lower():
        return (
            f"DNS 解析失败：无法解析目标地址。"
            f"请检查网络连接，或尝试 ping {base_url.split('://')[-1].split('/')[0]}"
        )

    # SSL/TLS 错误
    if "ssl" in raw.lower() or "certificate" in raw.lower():
        return (
            f"SSL/TLS 连接失败：证书验证错误。"
            f"目标: {base_url}。可能是系统时间错误或代{chr(150)}理拦截。"
        )

    # 连接被拒绝
    if "connection refused" in raw.lower():
        return (
            f"连接被拒绝：目标服务器 {base_url} 拒绝了连接请求。"
        )

    # 超时
    if "timed out" in raw.lower() or "timeout" in raw.lower():
        return (
            f"连接超时：无法在 10s 内连接到 {base_url}。"
            f"可能是防火墙拦截或需要配置 HTTP 代理（HTTP_PROXY/HTTPS_PROXY 环境变量）。"
        )

    # 通用网络不可达
    if "no route" in raw.lower() or "unreachable" in raw.lower():
        return (
            f"网络不可达：到 {base_url} 的路由不通。"
            f"需要检查 VPN/代理/防火墙设置。"
        )

    return f"无法连接到 {base_url}: {raw}"
