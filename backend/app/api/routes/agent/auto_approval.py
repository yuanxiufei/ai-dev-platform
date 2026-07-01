"""
Auto-Approval API — 智能工具审批引擎

借鉴 RooCode auto-approval/ + OpenInterpreter approval/ 设计：
  GET    /agent/approval/rules — 列出所有审批规则
  POST   /agent/approval/rules — 添加审批规则 (Always Allow/Deny)
  DELETE /agent/approval/rules/{tool_name} — 删除规则
  GET    /agent/approval/check — 检查工具是否需要审批
  GET    /agent/approval/risk-levels — 工具风险级别列表
  POST   /agent/approval/mode — 设置审批模式
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.core.agent.auto_approval import (
    ApprovalDecision,
    ApprovalRule,
    RiskLevel,
    TOOL_RISK_MAP,
    get_approval_engine,
)

logger = logging.getLogger("api.agent.approval")

router = APIRouter(prefix="/agent/approval", tags=["agent-approval"])


# ── Request Models ─────────────────────────────────────


class AddRuleRequest(BaseModel):
    tool_name: str = Field(..., description="工具名")
    allowed: bool = Field(default=True, description="True=Always Allow, False=Always Deny")
    path_pattern: str = Field(default="", description="可选的路径 glob 匹配")
    param_conditions: dict[str, Any] = Field(default_factory=dict, description="可选参数条件")

    model_config = {"extra": "allow"}


class CheckRequest(BaseModel):
    tool_name: str = Field(..., description="工具名")
    tool_args: dict[str, Any] = Field(default_factory=dict, description="工具参数")
    agent_name: str = Field(default="", description="Agent 名称")
    turn_number: int = Field(default=0, description="当前轮次")

    model_config = {"extra": "allow"}


class SetModeRequest(BaseModel):
    mode: str = Field(..., description="审批模式: safe-tools | custom | never | always")


# ── Routes ────────────────────────────────────────────


@router.get("/rules")
async def list_rules(user: CurrentUser) -> dict[str, Any]:
    """列出所有审批规则"""
    engine = get_approval_engine()
    rules = engine.list_rules()
    return {
        "data": rules,
        "total": len(rules),
        "mode": engine.mode,
    }


@router.post("/rules")
async def add_rule(
    payload: AddRuleRequest,
    user: CurrentUser,
) -> dict[str, Any]:
    """
    添加审批规则 (Always Allow / Always Deny)
    
    示例:
        {"tool_name": "write_file", "allowed": true, "path_pattern": "src/*.py"}
        — 总是允许 write_file 写入 src/*.py 文件
    """
    engine = get_approval_engine()
    rule = engine.add_rule(
        tool_name=payload.tool_name,
        allowed=payload.allowed,
        path_pattern=payload.path_pattern,
        param_conditions=payload.param_conditions,
    )
    return {
        "status": "ok",
        "rule": {
            "tool_name": rule.tool_name,
            "allowed": rule.allowed,
            "path_pattern": rule.path_pattern or "*",
        },
    }


@router.delete("/rules/{tool_name}")
async def remove_rule(
    tool_name: str,
    user: CurrentUser,
    path_pattern: str = "",
) -> dict[str, Any]:
    """
    删除审批规则
    
    Query:
        path_pattern: 指定路径模式删除特定规则
    """
    engine = get_approval_engine()
    removed = engine.remove_rule(tool_name, path_pattern)
    return {"status": "ok" if removed else "not_found", "removed": removed}


@router.post("/check")
async def check_approval(
    payload: CheckRequest,
    user: CurrentUser,
) -> dict[str, Any]:
    """
    检查工具调用是否需要用户审批
    
    Returns:
        {"approved": true/false, "reason": "...", "needs_user_confirmation": true/false, "risk_level": "safe"}
    """
    engine = get_approval_engine()
    decision = engine.check(
        tool_name=payload.tool_name,
        tool_args=payload.tool_args,
        agent_name=payload.agent_name,
        turn_number=payload.turn_number,
    )
    return {
        "approved": decision.approved,
        "reason": decision.reason,
        "needs_user_confirmation": decision.needs_user_confirmation,
        "risk_level": engine.get_risk_level(payload.tool_name).value,
        "tool_name": payload.tool_name,
    }


@router.get("/risk-levels")
async def list_risk_levels(user: CurrentUser) -> dict[str, Any]:
    """
    列出所有工具的风险级别
    
    Returns:
        {"safe": [...], "moderate": [...], "dangerous": [...]}
    """
    by_level: dict[str, list[str]] = {"safe": [], "moderate": [], "dangerous": []}
    for tool_name, level in TOOL_RISK_MAP.items():
        by_level[level.value].append(tool_name)
    
    return {
        "levels": by_level,
        "total_tools": len(TOOL_RISK_MAP),
    }


@router.post("/mode")
async def set_approval_mode(
    payload: SetModeRequest,
    user: CurrentUser,
) -> dict[str, Any]:
    """
    设置审批模式
    
    Modes:
        safe-tools — SAFE 工具自动批准，其他需确认 (默认)
        custom     — 仅匹配 Always Allow 规则的自动批准
        never      — 所有工具都需要确认
        always     — 所有工具自动批准 (高风险!)
    """
    engine = get_approval_engine()
    engine.set_mode(payload.mode)
    return {"status": "ok", "mode": engine.mode}
