"""
Model Arena API — 借鉴 Open WebUI Arena（模型竞技场）

提供:
- 并排对比: 两个模型同时生成，返回响应供人工投票
- ELO 排行榜: 基于投票结果计算 ELO 排名
- 分类对比: 按 code / chat / vision 等维度评测
"""

import math
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.api.deps import get_current_user, get_db
from app.models.model_presets import ArenaComparison, ArenaVote, ModelEloRanking
from app.core.model_router import ModelRequest, ModelCapability, get_model_router

router = APIRouter(prefix="/arena", tags=["arena"])


# ── Pydantic Schemas ────────────────────────────────────

class ArenaRequest(BaseModel):
    prompt: str
    model_a: str = "openai-gpt4o"
    model_b: str = "claude-sonnet"
    system_prompt: str | None = None
    temperature: float = 0.7
    max_tokens: int = 2048
    category: str = "chat"  # chat / code / vision


class ArenaResponse(BaseModel):
    comparison_id: uuid.UUID
    prompt: str
    model_a: str
    response_a: str
    latency_a_ms: float | None
    tokens_a: int | None
    model_b: str
    response_b: str
    latency_b_ms: float | None
    tokens_b: int | None
    category: str


class VoteRequest(BaseModel):
    comparison_id: uuid.UUID
    winner: str  # "A" / "B" / "tie"


class EloRankingEntry(BaseModel):
    model_name: str
    elo: float
    wins: int
    losses: int
    ties: int
    total_comparisons: int
    category: str | None


class EloRankingResponse(BaseModel):
    rankings: list[EloRankingEntry]
    category: str | None


# ── ELO 计算（借鉴 Open WebUI Arena ELO 算法） ─────────

K_FACTOR = 32  # ELO K 因子


def _expected_score(elo_a: float, elo_b: float) -> float:
    """计算 A 对 B 的期望胜率"""
    return 1.0 / (1.0 + math.pow(10, (elo_b - elo_a) / 400))


def _update_elo(winner_elo: float, loser_elo: float) -> tuple[float, float]:
    """更新 ELO 分数，返回 (new_winner_elo, new_loser_elo)"""
    expected_win = _expected_score(winner_elo, loser_elo)
    new_winner = winner_elo + K_FACTOR * (1.0 - expected_win)
    new_loser = loser_elo + K_FACTOR * (0.0 - (1.0 - expected_win))
    return round(new_winner, 1), round(new_loser, 1)


def _get_or_create_elo(db: Session, model_name: str, category: str | None = None) -> ModelEloRanking:
    """获取或创建模型 ELO 记录"""
    stmt = select(ModelEloRanking).where(
        ModelEloRanking.model_name == model_name,
        (ModelEloRanking.category == category) if category else True,
    )
    ranking = db.exec(stmt).first()
    if not ranking:
        ranking = ModelEloRanking(
            model_name=model_name,
            category=category,
            elo=1500.0,
        )
        db.add(ranking)
        db.commit()
        db.refresh(ranking)
    return ranking


# ── Endpoints ───────────────────────────────────────────

@router.post("/arena/compare", response_model=ArenaResponse)
async def arena_compare(
    body: ArenaRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> ArenaResponse:
    """并排对比两个模型 — 借鉴 Open WebUI Arena"""
    import time

    model_router = get_model_router()
    capability = (
        ModelCapability.CODE_GENERATION if body.category == "code"
        else ModelCapability.VISION_LANGUAGE if body.category == "vision"
        else ModelCapability.TEXT_GENERATION
    )

    async def call_model(model_name: str) -> tuple[str, float, int | None]:
        t0 = time.perf_counter()
        req = ModelRequest(
            prompt=body.prompt,
            system_prompt=body.system_prompt,
            capability=capability,
            preferred_model=model_name,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
        resp = await model_router.generate(req)
        latency = (time.perf_counter() - t0) * 1000
        return resp.content, latency, resp.tokens_used

    resp_a, lat_a, tok_a = await call_model(body.model_a)
    resp_b, lat_b, tok_b = await call_model(body.model_b)

    comparison = ArenaComparison(
        prompt=body.prompt,
        model_a=body.model_a,
        response_a=resp_a,
        latency_a_ms=lat_a,
        tokens_a=tok_a,
        model_b=body.model_b,
        response_b=resp_b,
        latency_b_ms=lat_b,
        tokens_b=tok_b,
        category=body.category,
        voter_id=current_user.id,
    )
    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    return ArenaResponse(
        comparison_id=comparison.id,
        prompt=body.prompt,
        model_a=comparison.model_a,
        response_a=comparison.response_a,
        latency_a_ms=comparison.latency_a_ms,
        tokens_a=comparison.tokens_a,
        model_b=comparison.model_b,
        response_b=comparison.response_b,
        latency_b_ms=comparison.latency_b_ms,
        tokens_b=comparison.tokens_b,
        category=comparison.category or "chat",
    )


@router.post("/arena/vote")
async def arena_vote(
    body: VoteRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """为对比结果投票 — ELO 算法更新排名"""
    comparison = db.get(ArenaComparison, body.comparison_id)
    if not comparison:
        raise HTTPException(status_code=404, detail="对比记录不存在")
    if comparison.winner is not None:
        raise HTTPException(status_code=400, detail="该对比已有投票结果")

    winner_orig = body.winner.upper()
    if winner_orig not in ("A", "B", "TIE"):
        raise HTTPException(status_code=400, detail="winner 必须是 A / B / tie")

    # 更新 comparison 记录
    comparison.winner = winner_orig
    comparison.voter_id = current_user.id
    db.add(comparison)

    # ELO 更新
    if winner_orig == "TIE":
        # 平局 — 双方小幅调整
        elo_a = _get_or_create_elo(db, comparison.model_a, comparison.category)
        elo_b = _get_or_create_elo(db, comparison.model_b, comparison.category)
        elo_a_before, elo_b_before = elo_a.elo, elo_b.elo

        expected_a = _expected_score(elo_a.elo, elo_b.elo)
        new_a = elo_a.elo + K_FACTOR * (0.5 - expected_a)
        new_b = elo_b.elo + K_FACTOR * (0.5 - (1 - expected_a))

        elo_a.elo = round(new_a, 1)
        elo_a.ties += 1
        elo_a.total_comparisons += 1
        elo_b.elo = round(new_b, 1)
        elo_b.ties += 1
        elo_b.total_comparisons += 1

        db.add_all([elo_a, elo_b])

        vote = ArenaVote(
            comparison_id=body.comparison_id,
            model_won="",
            model_lost="",
            elo_before_winner=elo_a_before,
            elo_before_loser=elo_b_before,
            elo_after_winner=new_a,
            elo_after_loser=new_b,
            voter_id=current_user.id,
        )

    else:
        won_model = comparison.model_a if winner_orig == "A" else comparison.model_b
        lost_model = comparison.model_b if winner_orig == "A" else comparison.model_a

        elo_w = _get_or_create_elo(db, won_model, comparison.category)
        elo_l = _get_or_create_elo(db, lost_model, comparison.category)

        w_before, l_before = elo_w.elo, elo_l.elo
        new_w, new_l = _update_elo(w_before, l_before)

        elo_w.elo = new_w
        elo_w.wins += 1
        elo_w.total_comparisons += 1
        elo_l.elo = new_l
        elo_l.losses += 1
        elo_l.total_comparisons += 1

        db.add_all([elo_w, elo_l])

        vote = ArenaVote(
            comparison_id=body.comparison_id,
            model_won=won_model,
            model_lost=lost_model,
            elo_before_winner=w_before,
            elo_before_loser=l_before,
            elo_after_winner=new_w,
            elo_after_loser=new_l,
            voter_id=current_user.id,
        )

    db.add(vote)
    db.commit()

    return {
        "ok": True,
        "winner": winner_orig,
        "message": "投票已记录，ELO 已更新",
    }


@router.get("/arena/rankings", response_model=EloRankingResponse)
async def arena_rankings(
    category: str | None = Query(None, description="分类筛选: chat / code / vision"),
    db: Session = Depends(get_db),
) -> EloRankingResponse:
    """获取 ELO 排行榜 — 借鉴 Open WebUI Arena Leaderboard"""
    stmt = select(ModelEloRanking)
    if category:
        stmt = stmt.where(ModelEloRanking.category == category)
    stmt = stmt.order_by(ModelEloRanking.elo.desc()).limit(50)

    rankings = db.exec(stmt).all()
    return EloRankingResponse(
        rankings=[
            EloRankingEntry(
                model_name=r.model_name,
                elo=r.elo,
                wins=r.wins,
                losses=r.losses,
                ties=r.ties,
                total_comparisons=r.total_comparisons,
                category=r.category,
            )
            for r in rankings
        ],
        category=category,
    )


@router.get("/arena/history")
async def arena_history(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    category: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """获取对比历史记录"""
    stmt = select(ArenaComparison).where(ArenaComparison.winner.isnot(None))
    if category:
        stmt = stmt.where(ArenaComparison.category == category)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.exec(count_stmt).one()

    comparisons = db.exec(
        stmt.order_by(ArenaComparison.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return {
        "data": [
            {
                "id": str(c.id),
                "prompt": c.prompt,
                "model_a": c.model_a,
                "model_b": c.model_b,
                "winner": c.winner,
                "category": c.category,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comparisons
        ],
        "total": total,
        "page": page,
        "size": size,
    }
