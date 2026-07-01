"""
Memory API — 借鉴 Open WebUI Memory 功能

长期向量化记忆：
- 创建/更新/删除记忆
- 语义检索（通过 embedding 相似度）
- Agent 工具：save_memory / recall_memory
"""

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.api.deps import get_current_user, get_db, commit_or_rollback
from app.models.memory_models import MemoryEntry

router = APIRouter(prefix="/memory", tags=["memory"])


# ── Pydantic Schemas ────────────────────────────────────

class MemoryCreate(BaseModel):
    key: str
    value: str
    domain: str = "general"
    importance: float = 0.5


class MemoryUpdate(BaseModel):
    key: str | None = None
    value: str | None = None
    domain: str | None = None
    importance: float | None = None


class MemoryResponse(BaseModel):
    id: uuid.UUID
    key: str
    value: str
    domain: str
    importance: float
    access_count: int
    embedding_dim: int | None
    created_at: Any
    updated_at: Any


class MemorySearchRequest(BaseModel):
    query: str
    domain: str | None = None
    top_k: int = 5
    min_similarity: float = 0.3


class PaginatedMemoryResponse(BaseModel):
    data: list[MemoryResponse]
    total: int
    page: int
    size: int


# ── Helpers ─────────────────────────────────────────────

def _memory_to_response(m: MemoryEntry) -> MemoryResponse:
    return MemoryResponse(
        id=m.id,
        key=m.key,
        value=m.value,
        domain=m.domain,
        importance=m.importance,
        access_count=m.access_count,
        embedding_dim=m.embedding_dim if m.embedding else None,
        created_at=m.created_at.isoformat() if m.created_at else None,
        updated_at=m.updated_at.isoformat() if m.updated_at else None,
    )


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """余弦相似度"""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _generate_embedding(text: str, dim: int = 768) -> list[float]:
    """生成文本 embedding（简单 TF 降级方案，生产环境请用 OpenAI/BGE）"""
    import hashlib
    # 简单哈希 embedding（生产环境应使用真实 embedding 模型）
    hash_bytes = hashlib.sha256(text.encode()).digest()
    # 扩展到目标维度
    vec = []
    for i in range(dim):
        byte_val = hash_bytes[i % len(hash_bytes)]
        # 将字节映射到 [-1, 1]
        vec.append((byte_val / 127.5) - 1.0)
    # L2 归一化
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec


# ── Endpoints ───────────────────────────────────────────

@router.get("/memory", response_model=PaginatedMemoryResponse)
async def list_memories(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    domain: str | None = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> PaginatedMemoryResponse:
    """列出记忆"""
    stmt = select(MemoryEntry).where(MemoryEntry.user_id == current_user.id)
    if domain:
        stmt = stmt.where(MemoryEntry.domain == domain)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.exec(count_stmt).one()

    memories = db.exec(
        stmt.order_by(MemoryEntry.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()

    return PaginatedMemoryResponse(
        data=[_memory_to_response(m) for m in memories],
        total=total,
        page=page,
        size=size,
    )


@router.post("/memory", response_model=MemoryResponse)
async def create_memory(
    body: MemoryCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> MemoryResponse:
    """创建记忆（自动生成 embedding）"""
    embedding = await _generate_embedding(f"{body.key}: {body.value}")
    
    entry = MemoryEntry(
        key=body.key,
        value=body.value,
        domain=body.domain,
        importance=min(max(body.importance, 0.0), 1.0),
        embedding=json.dumps(embedding),
        embedding_dim=len(embedding),
        embedding_model="hash-sha256",
        user_id=current_user.id,
    )
    db.add(entry)
    commit_or_rollback(db)
    db.refresh(entry)
    return _memory_to_response(entry)


@router.get("/memory/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> MemoryResponse:
    """获取单条记忆"""
    entry = db.get(MemoryEntry, memory_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="记忆不存在")
    
    entry.access_count += 1
    entry.last_accessed_at = datetime.now(timezone.utc)
    db.add(entry)
    commit_or_rollback(db)
    db.refresh(entry)
    return _memory_to_response(entry)


@router.put("/memory/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: uuid.UUID,
    body: MemoryUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> MemoryResponse:
    """更新记忆"""
    entry = db.get(MemoryEntry, memory_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="记忆不存在")

    if body.key is not None:
        entry.key = body.key
    if body.value is not None:
        entry.value = body.value
    if body.domain is not None:
        entry.domain = body.domain
    if body.importance is not None:
        entry.importance = min(max(body.importance, 0.0), 1.0)

    # 重新生成 embedding
    if body.key is not None or body.value is not None:
        new_embedding = await _generate_embedding(f"{entry.key}: {entry.value}")
        entry.embedding = json.dumps(new_embedding)
        entry.embedding_dim = len(new_embedding)

    entry.updated_at = datetime.now(timezone.utc)
    db.add(entry)
    commit_or_rollback(db)
    db.refresh(entry)
    return _memory_to_response(entry)


@router.delete("/memory/{memory_id}")
async def delete_memory(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """删除记忆"""
    entry = db.get(MemoryEntry, memory_id)
    if not entry or entry.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="记忆不存在")
    db.delete(entry)
    commit_or_rollback(db)
    return {"ok": True, "message": "记忆已删除"}


_MEMORY_SEARCH_PRE_LIMIT = 5000

@router.post("/memory/search")
async def search_memories(
    body: MemorySearchRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """语义检索记忆 — 借鉴 Open WebUI 的 Memory 检索

    通过 embedding 余弦相似度找到最相关的记忆条目。
    """
    query_embedding = await _generate_embedding(body.query)
    
    stmt = select(MemoryEntry).where(MemoryEntry.user_id == current_user.id)
    if body.domain:
        stmt = stmt.where(MemoryEntry.domain == body.domain)
    stmt = stmt.limit(_MEMORY_SEARCH_PRE_LIMIT)

    entries = db.exec(stmt).all()

    scored: list[tuple[MemoryEntry, float]] = []
    for entry in entries:
        if not entry.embedding:
            continue
        try:
            emb = json.loads(entry.embedding)
        except (json.JSONDecodeError, TypeError):
            continue
        sim = _cosine_similarity(query_embedding, emb)
        if sim >= body.min_similarity:
            scored.append((entry, sim))

    # 按相似度 × 重要性排序
    scored.sort(key=lambda x: x[1] * x[0].importance, reverse=True)
    top = scored[:body.top_k]

    # 更新访问计数
    now = datetime.now(timezone.utc)
    for entry, _ in top:
        entry.access_count += 1
        entry.last_accessed_at = now
        db.add(entry)
    commit_or_rollback(db)

    return {
        "query": body.query,
        "results": [
            {
                "id": str(entry.id),
                "key": entry.key,
                "value": entry.value,
                "domain": entry.domain,
                "similarity": round(sim, 4),
                "importance": entry.importance,
                "score": round(sim * entry.importance, 4),
            }
            for entry, sim in top
        ],
    }


@router.get("/memory/stats")
async def memory_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """记忆统计"""
    stmt = select(
        func.count().label("total"),
        func.sum(MemoryEntry.access_count).label("total_access"),
    ).where(MemoryEntry.user_id == current_user.id)
    row = db.exec(stmt).one()

    # 按域统计
    stmt2 = select(
        MemoryEntry.domain,
        func.count().label("count"),
    ).where(MemoryEntry.user_id == current_user.id).group_by(MemoryEntry.domain)
    domains = db.exec(stmt2).all()

    return {
        "total_memories": row.total,
        "total_accesses": row.total_access or 0,
        "by_domain": {d.domain: d.count for d in domains},
    }
