"""
OpenAI response_format 兼容层 — 将 OpenAI response_format 注入到 ModelRequest

支持：
- response_format={"type": "json_object"} — 强制 JSON 输出
- response_format={"type": "json_schema", "json_schema": {...}} — JSON Schema 约束
- 自动转换为 GBNF grammar（llama.cpp）或 OpenAI 原生 response_format
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.structured_output.gbnf_grammar import json_schema_to_gbnf


@dataclass
class ResponseFormat:
    """OpenAI 兼容的 response_format 定义"""

    type: Literal["text", "json_object", "json_schema"] = "text"
    json_schema: dict[str, Any] | None = None  # {"name": "...", "schema": {...}, "strict": true}

    def is_structured(self) -> bool:
        """是否需要结构化输出"""
        return self.type in ("json_object", "json_schema")

    def to_gbnf(self) -> str | None:
        """转换为 GBNF 语法（用于 llama.cpp）"""
        if self.type == "json_object":
            from app.core.structured_output.gbnf_grammar import json_object_grammar
            return json_object_grammar()

        if self.type == "json_schema" and self.json_schema:
            schema = self.json_schema.get("schema", self.json_schema)
            return json_schema_to_gbnf(schema)

        return None

    def to_openai_format(self) -> dict[str, Any]:
        """转换为 OpenAI API 格式"""
        result: dict[str, Any] = {"type": self.type}
        if self.type == "json_schema" and self.json_schema:
            result["json_schema"] = self.json_schema
        return result

    def to_system_hint(self) -> str:
        """生成追加到 system_prompt 的格式提示（用于不支持原生 response_format 的 Provider）"""
        if self.type == "json_object":
            return "\n\nYou MUST respond with valid JSON only. No markdown, no explanations outside the JSON."
        if self.type == "json_schema" and self.json_schema:
            schema = self.json_schema.get("schema", self.json_schema)
            schema_name = self.json_schema.get("name", "response")
            import json
            schema_str = json.dumps(schema, ensure_ascii=False, indent=2)
            return (
                f"\n\nYou MUST respond with a JSON object that conforms to the following JSON Schema.\n"
                f"Schema name: {schema_name}\n"
                f"```json\n{schema_str}\n```\n"
                f"Do NOT include markdown code fences or any text outside the JSON object."
            )
        return ""


@dataclass
class ResponseFormatAdapter:
    """
    响应格式适配器 — 自动为不同 Provider 适配 response_format

    策略：
    - OpenAI/DeepSeek: 原生 response_format 支持
    - Anthropic Claude: 追加到 system prompt
    - llama.cpp: 转换为 GBNF grammar
    - 其他: system prompt 提示
    """

    response_format: ResponseFormat | None = None

    def for_provider(self, provider_name: str) -> dict[str, Any]:
        """为特定 Provider 返回适配后的配置"""
        if not self.response_format or not self.response_format.is_structured():
            return {}

        n = provider_name.lower()

        # OpenAI 原生支持
        if n in ("openai", "azure"):
            fmt = self.response_format.to_openai_format()
            return {"response_format": fmt}

        # DeepSeek 也支持（OpenAI 兼容）
        if n == "deepseek":
            fmt = self.response_format.to_openai_format()
            return {"response_format": fmt}

        # llama.cpp: 转换为 grammar
        if n in ("llama_cpp", "ollama"):
            gbnf = self.response_format.to_gbnf()
            if gbnf:
                return {"grammar": gbnf}

        # 其他 Provider: system prompt 注入
        hint = self.response_format.to_system_hint()
        return {"system_prompt_suffix": hint}

    def get_grammar(self) -> str | None:
        """直接获取 GBNF 语法"""
        if self.response_format:
            return self.response_format.to_gbnf()
        return None

    def get_hint(self) -> str:
        """获取 system prompt 追加提示"""
        if self.response_format:
            return self.response_format.to_system_hint()
        return ""


def apply_response_format(
    provider_name: str,
    response_format: ResponseFormat | None,
    system_prompt: str,
) -> tuple[str, dict[str, Any]]:
    """
    将 response_format 应用到请求中

    返回 (增强后的 system_prompt, provider 特定参数)
    """
    if not response_format or not response_format.is_structured():
        return system_prompt, {}

    adapter = ResponseFormatAdapter(response_format)
    provider_params = adapter.for_provider(provider_name)

    # 如果有 system_prompt_suffix，追加到 system_prompt
    suffix = provider_params.pop("system_prompt_suffix", "")
    if suffix:
        system_prompt = (system_prompt or "") + suffix

    return system_prompt, provider_params
