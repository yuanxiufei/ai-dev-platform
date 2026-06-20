"""
Model Analytics API — 借鉴 Open WebUI Analytics Dashboard

提供:
- Token 使用量统计
- 模型调用延迟分析
- 成本估算（按各 Provider 公开定价）
- 使用趋势图（按天/按小时）
- 模型排行榜（使用次数 / 成功率）
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func, text

from app.api.deps import get_db, get_current_user
from app.models.model_presets import ModelUsageLog

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ── Pydantic Schemas ────────────────────────────────────


# ── 各 Provider 定价（USD / 1M tokens） ─────────────────
PRICING = {
    "openai":   {"input": 2.50, "output": 10.00, "model": "gpt-4o"},
    "anthropic":{"input": 3.00, "output": 15.00, "model": "claude-sonnet-4"},
    "deepseek": {"input": 0.14, "output": 0.28, "model": "deepseek-v3"},
    "ollama":   {"input": 0.0,  "output": 0.0,   "model": "local"},
    "llama_cpp":{"input": 0.0,  "output": 0.0,   "model": "local"},
    "zhipu":    {"input": 0.10, "output": 0.10, "model": "glm-4"},
    "qwen":     {"input": 0.55, "output": 0.55, "model": "qwen-max"},
    "replicate":{"input": 0.0,  "output": 0.0,   "model": "replicate"},
}


def _estimate_cost(provider: str, prompt_tokens: int, completion_tokens: int) -> float:
    """估算单次调用的成本（USD）"""
    pricing = PRICING.get(provider, {"input": 0, "output": 0})
    cost = (prompt_tokens / 1_000_000) * pricing["input"] + (completion_tokens / 1_000_000) * pricing["output"]
    return round(cost, 6)


# ── Endpoints ───────────────────────────────────────────

@router.get("/analytics/overview")
async def analytics_overview(
    days: int = Query(7, ge=1, le=90, description="统计天数"),
    db: Session = Depends(get_db),
) -> dict:
    """整体概览 — 借鉴 Open WebUI Dashboard"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 总调用次数 & 成功率
    total_stmt = select(
        func.count().label("total"),
        func.sum(ModelUsageLog.success.cast(int)).label("success_count"),
    ).where(ModelUsageLog.created_at >= since)
    totals = db.exec(total_stmt).one()

    # Token 统计
    token_stmt = select(
        func.sum(ModelUsageLog.prompt_tokens).label("prompt_total"),
        func.sum(ModelUsageLog.completion_tokens).label("completion_total"),
        func.sum(ModelUsageLog.total_tokens).label("total"),
    ).where(ModelUsageLog.created_at >= since)
    tokens = db.exec(token_stmt).one()

    # 成本统计
    cost_stmt = select(func.sum(ModelUsageLog.estimated_cost_usd)).where(ModelUsageLog.created_at >= since)
    total_cost = db.exec(cost_stmt).one() or 0

    # 平均延迟
    latency_stmt = select(func.avg(ModelUsageLog.latency_ms)).where(
        ModelUsageLog.created_at >= since,
        ModelUsageLog.success == True,
    )
    avg_latency = db.exec(latency_stmt).one() or 0

    total_calls = totals.total or 0
    success_count = totals.success_count or 0

    return {
        "period_days": days,
        "total_calls": total_calls,
        "success_rate": round(success_count / total_calls * 100, 1) if total_calls > 0 else 0,
        "total_prompt_tokens": tokens.prompt_total or 0,
        "total_completion_tokens": tokens.completion_total or 0,
        "total_tokens": tokens.total or 0,
        "estimated_cost_usd": round(total_cost, 4),
        "avg_latency_ms": round(avg_latency, 1),
    }


@router.get("/analytics/by-model")
async def analytics_by_model(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict:
    """按模型统计 — 调用次数/Token/成本/延迟"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(
        ModelUsageLog.model_name,
        ModelUsageLog.provider,
        func.count().label("calls"),
        func.sum(ModelUsageLog.total_tokens).label("total_tokens"),
        func.avg(ModelUsageLog.latency_ms).label("avg_latency"),
        func.sum(ModelUsageLog.estimated_cost_usd).label("total_cost"),
        func.sum(ModelUsageLog.success.cast(int)).label("success_count"),
    ).where(ModelUsageLog.created_at >= since).group_by(
        ModelUsageLog.model_name, ModelUsageLog.provider
    ).order_by(func.count().desc())

    rows = db.exec(stmt).all()
    return {
        "period_days": days,
        "models": [
            {
                "model_name": r.model_name,
                "provider": r.provider,
                "calls": r.calls,
                "total_tokens": r.total_tokens or 0,
                "avg_latency_ms": round(r.avg_latency, 1) if r.avg_latency else 0,
                "total_cost_usd": round(r.total_cost, 4) if r.total_cost else 0,
                "success_rate": round(r.success_count / r.calls * 100, 1) if r.calls > 0 else 0,
            }
            for r in rows
        ],
    }


@router.get("/analytics/trends")
async def analytics_trends(
    days: int = Query(7, ge=1, le=90),
    granularity: str = Query("day", regex="^(hour|day)$"),
    db: Session = Depends(get_db),
) -> dict:
    """使用趋势 — 按小时/天聚合"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    if granularity == "hour":
        # SQLite: strftime; PostgreSQL: to_char
        date_trunc = func.strftime("%Y-%m-%d %H:00", ModelUsageLog.created_at).label("bucket")
    else:
        date_trunc = func.strftime("%Y-%m-%d", ModelUsageLog.created_at).label("bucket")

    stmt = select(
        date_trunc,
        func.count().label("calls"),
        func.sum(ModelUsageLog.total_tokens).label("tokens"),
    ).where(ModelUsageLog.created_at >= since).group_by("bucket").order_by("bucket")

    rows = db.exec(stmt).all()
    return {
        "period_days": days,
        "granularity": granularity,
        "trends": [
            {
                "time": r.bucket,
                "calls": r.calls,
                "total_tokens": r.tokens or 0,
            }
            for r in rows
        ],
    }


@router.get("/analytics/by-capability")
async def analytics_by_capability(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
) -> dict:
    """按能力分类统计"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(
        ModelUsageLog.capability,
        func.count().label("calls"),
        func.sum(ModelUsageLog.total_tokens).label("tokens"),
        func.avg(ModelUsageLog.latency_ms).label("avg_latency"),
    ).where(ModelUsageLog.created_at >= since).group_by(ModelUsageLog.capability)

    rows = db.exec(stmt).all()
    return {
        "period_days": days,
        "capabilities": [
            {
                "capability": r.capability,
                "calls": r.calls,
                "total_tokens": r.tokens or 0,
                "avg_latency_ms": round(r.avg_latency, 1) if r.avg_latency else 0,
            }
            for r in rows
        ],
    }


@router.get("/analytics/top-prompts")
async def analytics_top_prompts(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """最常用提示词（脱敏，仅返回频次）"""
    # 仅返回频次，不返回原始 prompt 文本（安全）
    since = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(func.count()).where(ModelUsageLog.created_at >= since)
    total = db.exec(stmt).one()

    stmt2 = select(
        ModelUsageLog.model_name,
        func.count().label("calls"),
    ).where(ModelUsageLog.created_at >= since).group_by(
        ModelUsageLog.model_name
    ).order_by(func.count().desc()).limit(limit)

    rows = db.exec(stmt2).all()
    return {
        "period_days": days,
        "total_prompts": total,
        "top_models": [
            {"model_name": r.model_name, "calls": r.calls}
            for r in rows
        ],
    }
