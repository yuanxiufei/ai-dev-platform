"""
Reflection API — Agent 自省/反思端点

端点：
- POST /agent/reflection/reflect  — 触发反思评估
- POST /agent/reflection/self-critique — 自我批评（输入 → 检查 → 修正）
- GET  /agent/reflection/history — 历史反思记录
- GET  /agent/reflection/stats   — 反思统计
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.agent.reflection import (
    ReflectionConfig, ReflectionResult, ReflectionManager,
    AgentReflector,
    get_reflection_manager,
)

router = APIRouter(prefix="/reflection", tags=["reflection"])


# ── Pydantic Schemas ─────────────────────────────────


class ReflectRequest(BaseModel):
    task_description: str = ""
    agent_actions: str = ""
    final_output: str = ""
    question: str = "Evaluate the agent run quality."
    dimensions: list[str] | None = None
    """要评估的维度，默认使用全局配置"""


class SelfCritiqueRequest(BaseModel):
    original_output: str
    success_criteria: str


class ReflectionResponse(BaseModel):
    run_id: str
    score: float
    dimension_scores: dict[str, float]
    issues: list[str]
    suggestions: list[str]
    verdict: str
    model_used: str
    latency_ms: float

    @classmethod
    def from_result(cls, r: ReflectionResult) -> ReflectionResponse:
        # 根据分数判断 verdict
        if r.score >= 80:
            verdict = "PASS"
        elif r.score >= 50:
            verdict = "WARN"
        elif r.score >= 0:
            verdict = "FAIL"
        else:
            verdict = "ERROR"

        return cls(
            run_id=r.run_id,
            score=r.score,
            dimension_scores=r.dimension_scores,
            issues=r.issues,
            suggestions=r.suggestions,
            verdict=verdict,
            model_used=r.model_used,
            latency_ms=round(r.latency_ms, 2),
        )


class SelfCritiqueResponse(BaseModel):
    original_output: str
    fixed_output: str
    was_modified: bool
    issues_found: list[str]


class HistoryItem(BaseModel):
    run_id: str
    score: float
    issues: list[str]
    timestamp: str

    @classmethod
    def from_result(cls, r: ReflectionResult) -> HistoryItem:
        return cls(
            run_id=r.run_id,
            score=r.score,
            issues=r.issues,
            timestamp=r.timestamp,
        )


class StatsResponse(BaseModel):
    total_reflections: int
    average_score: float
    recent_scores: list[float]
    total_issues: int
    total_suggestions: int


# ── 端点 ─────────────────────────────────────────────


@router.post("/reflect", response_model=ReflectionResponse)
async def reflect_on_run(
    body: ReflectRequest,
    current_user=Depends(get_current_user),
) -> ReflectionResponse:
    """触发反思评估

    对 Agent 运行结果进行多维度评估（安全性、正确性、效率、完整性）。
    """
    mgr = get_reflection_manager()

    # 模拟一个简单的 run_result 用于反思
    run_result = type("FakeRunResult", (), {
        "success": True,
        "turns": 0,
        "total_tool_calls": 0,
        "final_answer": body.final_output,
        "run_id": str(uuid.uuid4()),
    })()

    result = await mgr.after_run(
        run_result=run_result,
        task_description=body.task_description,
        agent_actions=body.agent_actions,
    )

    if result is None:
        raise HTTPException(status_code=500, detail="Reflection failed")

    return ReflectionResponse.from_result(result)


@router.post("/self-critique", response_model=SelfCritiqueResponse)
async def self_critique(
    body: SelfCritiqueRequest,
    current_user=Depends(get_current_user),
) -> SelfCritiqueResponse:
    """自我批评 — 让 LLM 检查并修正自己的输出

    借鉴 Trae Agent self-critique 机制。
    """
    reflector = AgentReflector()
    fixed, modified = await reflector.self_critique(
        original_output=body.original_output,
        success_criteria=body.success_criteria,
    )

    issues: list[str] = []
    if modified:
        issues.append("Output was modified by self-critique")

    return SelfCritiqueResponse(
        original_output=body.original_output[:500],
        fixed_output=fixed,
        was_modified=modified,
        issues_found=issues,
    )


@router.get("/history", response_model=list[HistoryItem])
async def reflection_history(
    limit: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
) -> list[HistoryItem]:
    """历史反思记录"""
    mgr = get_reflection_manager()
    history = mgr._history[-limit:]
    return [HistoryItem.from_result(r) for r in history]


@router.get("/stats", response_model=StatsResponse)
async def reflection_stats(
    current_user=Depends(get_current_user),
) -> StatsResponse:
    """反思统计"""
    mgr = get_reflection_manager()
    history = mgr._history
    return StatsResponse(
        total_reflections=len(history),
        average_score=round(mgr.average_score, 2),
        recent_scores=[round(s, 2) for s in mgr.recent_scores[-10:]],
        total_issues=sum(len(r.issues) for r in history),
        total_suggestions=sum(len(r.suggestions) for r in history),
    )
