"""
Guardrails API — 工具调用授权护栏管理
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.guardrails import get_guardrails, GuardrailConfig, InterventionLevel

router = APIRouter(prefix="/system/guardrails", tags=["guardrails"])


class GuardrailCheckRequest(BaseModel):
    tool_name: str
    tool_params: dict[str, str]


class GuardrailDecisionResponse(BaseModel):
    level: str
    reason: str
    blocked_params: list[str]
    suggestions: list[str]


class GuardrailConfigResponse(BaseModel):
    enabled: bool
    default_level: str
    file_path_whitelist: list[str]
    file_path_blacklist: list[str]
    sensitive_commands: list[str]
    blocked_domains: list[str]
    max_file_size_mb: float
    max_command_length: int


@router.post("/check")
def check_tool_call(req: GuardrailCheckRequest) -> GuardrailDecisionResponse:
    """检查工具调用是否安全"""
    mgr = get_guardrails()
    decision = mgr.check_tool_call(req.tool_name, req.tool_params)
    return GuardrailDecisionResponse(
        level=decision.level.value,
        reason=decision.reason,
        blocked_params=decision.blocked_params,
        suggestions=decision.suggestions,
    )


@router.get("/config")
def get_guardrail_config() -> GuardrailConfigResponse:
    """获取护栏配置"""
    cfg = get_guardrails().config
    return GuardrailConfigResponse(
        enabled=cfg.enabled,
        default_level=cfg.default_level.value,
        file_path_whitelist=cfg.file_path_whitelist,
        file_path_blacklist=cfg.file_path_blacklist,
        sensitive_commands=cfg.sensitive_commands,
        blocked_domains=cfg.blocked_domains,
        max_file_size_mb=cfg.max_file_size_mb,
        max_command_length=cfg.max_command_length,
    )
