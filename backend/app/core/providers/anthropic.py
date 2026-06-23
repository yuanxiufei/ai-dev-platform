"""
Anthropic Provider — 适配 Claude Messages API

支持的模型: claude-sonnet-4-20250514, claude-3-opus-20240229
"""

from __future__ import annotations

import json
import logging

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
