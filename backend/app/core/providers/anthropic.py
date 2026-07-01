"""
Anthropic Provider — 适配 Claude Messages API

支持的模型: claude-sonnet-4-20250514, claude-3-opus-20240229
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from app.core.model_router import ModelRequest, ModelResponse
from app.core.providers.base import BaseProvider

logger = logging.getLogger("provider.anthropic")


class AnthropicProvider(BaseProvider):
    """Anthropic Claude API 适配器 —— 支持 Tool Use"""

    async def generate(self, request: ModelRequest) -> ModelResponse:
        model_name = self._get_model_name(request)

        messages: list[dict] = []
        if request.history:
            messages.extend(request.history)
        messages.append({"role": "user", "content": request.prompt})

        body: dict = {
            "model": model_name,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
        }
        if request.system_prompt:
            body["system"] = request.system_prompt

        # ── 工具/Tool Use（转换为 Anthropic 格式） ──
        if request.tools:
            anthropic_tools = self._to_anthropic_tools(request.tools)
            if anthropic_tools:
                body["tools"] = anthropic_tools
            # Anthropic 的 tool_choice: {"type": "auto"} | {"type": "any"} | {"type": "tool", "name": "..."}
            if request.tool_choice:
                body["tool_choice"] = self._to_anthropic_tool_choice(request.tool_choice)

        resp = await self.client.post("/v1/messages", json=body)
        resp.raise_for_status()
        data = resp.json()

        # ── 解析内容与工具调用 ──
        content_blocks = data.get("content", [])
        text_content = ""
        tool_calls: list[dict] = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content = block.get("text", "")
            elif block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })

        finish_reason = data.get("stop_reason", "stop")
        if finish_reason == "tool_use":
            finish_reason = "tool_calls"

        if tool_calls:
            logger.info(
                "Anthropic tool_use returned: %s",
                [tc["function"]["name"] for tc in tool_calls],
            )

        return ModelResponse(
            content=text_content,
            model_used=data.get("model", model_name),
            provider="anthropic",
            tokens_used=(data.get("usage", {}).get("input_tokens", 0)
                         + data.get("usage", {}).get("output_tokens", 0)),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
        )

    # ── 流式推理（Anthropic SSE 协议） ──────────────

    async def generate_stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """流式推理 — token-by-token 产出（Anthropic Messages SSE 协议）

        Anthropic 流式事件类型：
          content_block_delta.delta.text_delta → 文本增量
          其他事件（message_start/content_block_start/message_delta 等）跳过
        """
        model_name = self._get_model_name(request)

        messages: list[dict] = []
        if request.history:
            messages.extend(request.history)
        messages.append({"role": "user", "content": request.prompt})

        body: dict[str, Any] = {
            "model": model_name,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": messages,
            "stream": True,
        }
        if request.system_prompt:
            body["system"] = request.system_prompt

        if request.tools:
            anthropic_tools = self._to_anthropic_tools(request.tools)
            if anthropic_tools:
                body["tools"] = anthropic_tools
            if request.tool_choice:
                body["tool_choice"] = self._to_anthropic_tool_choice(request.tool_choice)

        async with self.client.stream("POST", "/v1/messages", json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                try:
                    event = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                event_type = event.get("type", "")
                if event_type == "content_block_delta":
                    delta = event.get("delta", {})
                    if delta.get("type") == "text_delta":
                        text = delta.get("text", "")
                        if text:
                            yield text

    def _build_headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.config.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

    # ── OpenAI → Anthropic 工具格式转换 ─────────────────

    @staticmethod
    def _to_anthropic_tools(openai_tools: list[dict]) -> list[dict]:
        """将 OpenAI Function Calling 格式转为 Anthropic Tool Use 格式"""
        tools: list[dict] = []
        for t in openai_tools:
            func = t.get("function", {})
            tools.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
            })
        return tools

    @staticmethod
    def _to_anthropic_tool_choice(tool_choice: str | dict) -> dict:
        """将 OpenAI tool_choice 转为 Anthropic 格式"""
        if isinstance(tool_choice, str):
            if tool_choice == "none":
                return {"type": "none"}
            return {"type": "auto"}
        if isinstance(tool_choice, dict):
            func = tool_choice.get("function", {})
            if func.get("name"):
                return {"type": "tool", "name": func["name"]}
            if tool_choice.get("type") == "function":
                return {"type": "tool", "name": func.get("name", "")}
        return {"type": "auto"}
