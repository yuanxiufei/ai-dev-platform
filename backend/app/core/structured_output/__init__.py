"""
结构化输出引擎 — GBNF 语法约束 + JSON Schema 转换 + OpenAI response_format 兼容层

借鉴 llama.cpp 的 GBNF (GGML BNF) 语法系统，为所有 LLM 提供商提供统一的
结构化输出能力。支持：
- JSON Schema → GBNF 自动转换
- OpenAI response_format 兼容接口
- 本地模型 grammar 注入
- 工具调用格式约束
"""

from app.core.structured_output.gbnf_grammar import (
    GBNFGrammar,
    json_schema_to_gbnf,
    validate_gbnf,
)
from app.core.structured_output.response_format import (
    ResponseFormat,
    ResponseFormatAdapter,
    apply_response_format,
)

__all__ = [
    "GBNFGrammar",
    "json_schema_to_gbnf",
    "validate_gbnf",
    "ResponseFormat",
    "ResponseFormatAdapter",
    "apply_response_format",
]
