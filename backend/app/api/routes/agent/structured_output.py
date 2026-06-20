"""
结构化输出 API — JSON Schema → GBNF 转换 + response_format 预览

路径: /structured-output/*
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.structured_output.gbnf_grammar import (
    json_schema_to_gbnf,
    json_object_grammar,
    tool_call_grammar,
    validate_gbnf,
)
from app.core.structured_output.response_format import ResponseFormat, ResponseFormatAdapter

router = APIRouter(prefix="/structured-output", tags=["Structured Output"])


# ── Request Models ────────────────────────────────

class SchemaToGBNFRequest(BaseModel):
    """JSON Schema → GBNF 转换请求"""
    json_schema: dict[str, Any] = Field(..., description="JSON Schema 定义")
    root_name: str = Field(default="root", description="GBNF 根规则名称")


class GBNFValidateRequest(BaseModel):
    """GBNF 语法校验请求"""
    gbnf_string: str = Field(..., description="GBNF 语法字符串")


class ResponseFormatPreviewRequest(BaseModel):
    """response_format 预览请求"""
    response_format: dict[str, Any] = Field(..., description="OpenAI 格式的 response_format")
    provider_name: str = Field(default="openai", description="目标 Provider")


# ── Response Models ───────────────────────────────

class SchemaToGBNFResponse(BaseModel):
    """转换结果"""
    gbnf: str
    rules_count: int
    valid: bool


class GBNFValidateResponse(BaseModel):
    """校验结果"""
    valid: bool
    message: str


class ResponseFormatPreviewResponse(BaseModel):
    """预览结果"""
    openai_format: dict[str, Any]
    gbnf_grammar: str | None
    system_prompt_hint: str
    provider_name: str
    provider_params: dict[str, Any]


# ── 模板 ─────────────────────────────────────────

TEMPLATES: dict[str, str] = {
    "json_object": json_object_grammar(),
    "tool_call": tool_call_grammar(),
}


# ── Routes ────────────────────────────────────────

@router.post("/json-schema-to-gbnf", response_model=SchemaToGBNFResponse)
async def convert_schema_to_gbnf(req: SchemaToGBNFRequest) -> dict[str, Any]:
    """
    将 JSON Schema 转换为 GBNF 语法
    
    用于 llama.cpp / Ollama 的结构化输出约束
    """
    try:
        gbnf = json_schema_to_gbnf(req.json_schema, req.root_name)
        rules_count = len([l for l in gbnf.split("\n") if "::=" in l])
        valid = validate_gbnf(gbnf)
        return {"gbnf": gbnf, "rules_count": rules_count, "valid": valid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"转换失败: {e}")


@router.post("/validate-gbnf", response_model=GBNFValidateResponse)
async def validate_gbnf_route(req: GBNFValidateRequest) -> dict[str, Any]:
    """校验 GBNF 语法合法性"""
    valid = validate_gbnf(req.gbnf_string)
    return {
        "valid": valid,
        "message": "语法合法" if valid else "语法不合法：缺少 root 规则或引用了未定义规则",
    }


@router.get("/templates", response_model=dict)
async def list_templates() -> dict[str, Any]:
    """列出内置 GBNF 语法模板"""
    return {"templates": {k: v for k, v in TEMPLATES.items()}}


@router.get("/templates/{name}", response_model=dict)
async def get_template(name: str) -> dict[str, Any]:
    """获取指定 GBNF 语法模板"""
    if name not in TEMPLATES:
        raise HTTPException(status_code=404, detail=f"模板 '{name}' 不存在")
    return {"name": name, "gbnf": TEMPLATES[name]}


@router.post("/preview-response-format", response_model=ResponseFormatPreviewResponse)
async def preview_response_format(req: ResponseFormatPreviewRequest) -> dict[str, Any]:
    """
    预览 response_format 在不同 Provider 上的表现
    
    返回 OpenAI 格式、GBNF grammar、system prompt 提示
    """
    try:
        rf_type = req.response_format.get("type", "text")
        if rf_type not in ("json_object", "json_schema"):
            return {
                "openai_format": req.response_format,
                "gbnf_grammar": None,
                "system_prompt_hint": "",
                "provider_name": req.provider_name,
                "provider_params": {},
            }

        rf = ResponseFormat(
            type=rf_type,
            json_schema=req.response_format.get("json_schema"),
        )
        adapter = ResponseFormatAdapter(rf)

        return {
            "openai_format": rf.to_openai_format(),
            "gbnf_grammar": adapter.get_grammar(),
            "system_prompt_hint": adapter.get_hint(),
            "provider_name": req.provider_name,
            "provider_params": adapter.for_provider(req.provider_name),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
