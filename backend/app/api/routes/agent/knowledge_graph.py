"""
Knowledge Graph API — 借鉴 Obsidian Wikilinks + JSON Canvas

端点：
- GET  /knowledge-graph/backlinks          — 反向链接索引
- GET  /knowledge-graph/links/{key}        — 单个记忆的链接
- GET  /knowledge-graph/parse              — 解析 memory value（wikilinks+frontmatter+callouts+tags）
- GET  /knowledge-graph/canvas              — 从所有记忆生成 JSON Canvas
- GET  /knowledge-graph/canvas/download     — 下载 .canvas 文件
- GET  /knowledge-graph/canvas/domain/{domain} — 按 domain 生成画布
- GET  /knowledge-graph/graph-data          — 图数据（节点+边）供前端渲染
- GET  /knowledge-graph/orphans             — 孤立节点
- GET  /knowledge-graph/stats               — 知识图谱统计
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from app.api.deps import get_current_user, get_db
from app.core.knowledge_graph import (
    CanvasGenerator,
    LinkIndex,
    parse_memory_value,
    WikiLink,
    ParsedFrontmatter,
    CalloutBlock,
    BacklinkIndex,
)

router = APIRouter(prefix="/knowledge-graph", tags=["knowledge-graph"])

# 全局内存实例（单次请求重建）
_g_link_index: Optional[LinkIndex] = None

# 知识图谱操作安全上限（保护图构建不被极端数据量拖垮）
_KG_MAX_MEMORIES = 50_000


def _get_link_index(db: Session, user_id: uuid.UUID) -> LinkIndex:
    """构建链接索引（惰性构建）"""
    from app.models.memory_models import MemoryEntry

    idx = LinkIndex()
    stmt = select(MemoryEntry).where(MemoryEntry.user_id == user_id).limit(_KG_MAX_MEMORIES)
    entries = db.exec(stmt).all()
    for e in entries:
        idx.index_memory(e.key, e.value or "")
    return idx


def _get_all_memories(db: Session, user_id: uuid.UUID) -> list[dict]:
    """获取所有记忆 dict"""
    from app.models.memory_models import MemoryEntry

    stmt = select(MemoryEntry).where(MemoryEntry.user_id == user_id).limit(_KG_MAX_MEMORIES)
    entries = db.exec(stmt).all()
    return [
        {
            "key": e.key,
            "value": e.value or "",
            "domain": e.domain,
            "importance": e.importance,
            "access_count": e.access_count,
            "created_at": e.created_at.isoformat() if e.created_at else "",
            "id": str(e.id),
        }
        for e in entries
    ]


# ── 反向链接 ───────────────────────────────────────────

@router.get("/knowledge-graph/backlinks")
async def list_backlinks(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """反向链接索引 — 谁链接了谁"""
    idx = _get_link_index(db, current_user.id)
    backlinks = idx.get_all_backlinks()

    return {
        "backlinks": [
            {
                "target_key": bl.target_key,
                "sources": bl.sources,
                "source_count": bl.count,
            }
            for bl in sorted(backlinks, key=lambda x: x.count, reverse=True)
        ],
        "total": len(backlinks),
    }


@router.get("/knowledge-graph/links/{key}")
async def get_memory_links(
    key: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """单个记忆的链接关系"""
    idx = _get_link_index(db, current_user.id)
    forward = idx.get_forward_links(key)
    back = idx.get_backlinks(key)

    return {
        "key": key,
        "forward_links": forward,
        "forward_count": len(forward),
        "backlinks": back,
        "backlink_count": len(back),
    }


@router.get("/knowledge-graph/orphans")
async def list_orphans(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """孤立节点 — 没有任何链接的记忆"""
    from app.models.memory_models import MemoryEntry

    stmt = select(MemoryEntry).where(MemoryEntry.user_id == current_user.id).limit(_KG_MAX_MEMORIES)
    entries = db.exec(stmt).all()
    all_keys = {e.key for e in entries}

    idx = _get_link_index(db, current_user.id)
    orphans = idx.get_orphans(all_keys)

    return {"orphans": orphans, "count": len(orphans), "total": len(all_keys)}


# ── 解析 ───────────────────────────────────────────────

@router.get("/knowledge-graph/parse")
async def parse_memory(
    key: str = Query(..., description="记忆 key"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """解析 memory value — wikilinks + frontmatter + callouts + tags"""
    from app.models.memory_models import MemoryEntry

    stmt = select(MemoryEntry).where(
        MemoryEntry.user_id == current_user.id,
        MemoryEntry.key == key,
    )
    entry = db.exec(stmt).first()
    if not entry:
        raise HTTPException(status_code=404, detail="记忆不存在")

    result = parse_memory_value(entry.value or "")
    fm: ParsedFrontmatter = result["frontmatter"]

    return {
        "key": entry.key,
        "value": entry.value,
        "domain": entry.domain,
        "wikilinks": [
            {"target": w.target, "display": w.display, "heading": w.heading, "block_id": w.block_id}
            for w in result["wikilinks"]
        ],
        "wikilink_count": len(result["wikilinks"]),
        "frontmatter": {
            "title": fm.title,
            "tags": fm.tags,
            "aliases": fm.aliases,
            "status": fm.status,
            "priority": fm.priority,
            "due_date": fm.due_date,
            "created": fm.created,
            "updated": fm.updated,
            "extra": fm.extra,
        },
        "callouts": [
            {"type": c.type, "title": c.title, "content": c.content[:300],
             "folded_default": c.folded_default}
            for c in result["callouts"]
        ],
        "callout_count": len(result["callouts"]),
        "tags": result["tags"],
        "plain_text": result["plain_text"][:500],
    }


# ── Canvas 生成 ────────────────────────────────────────

@router.get("/knowledge-graph/canvas")
async def generate_canvas(
    include_callouts: bool = Query(True, description="是否包含 Callout 作为独立节点"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """从所有记忆生成 JSON Canvas"""
    memories = _get_all_memories(db, current_user.id)
    if not memories:
        return {"canvas": {"nodes": [], "edges": []}, "node_count": 0, "edge_count": 0}

    gen = CanvasGenerator()
    canvas = gen.from_memories(memories, include_callouts=include_callouts)
    data = canvas.to_dict()

    return {
        "canvas": data,
        "node_count": len(data["nodes"]),
        "edge_count": len(data["edges"]),
        "version": "1.0",
        "spec": "https://jsoncanvas.org/spec/1.0/",
    }


@router.get("/knowledge-graph/canvas/download")
async def download_canvas(
    include_callouts: bool = Query(True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """下载 .canvas 文件（JSON 字符串）"""
    memories = _get_all_memories(db, current_user.id)
    gen = CanvasGenerator()
    canvas = gen.from_memories(memories, include_callouts=include_callouts)

    return {
        "filename": "knowledge-graph.canvas",
        "content_type": "application/json",
        "content": canvas.to_json(),
        "spec": "https://jsoncanvas.org/spec/1.0/",
    }


@router.get("/knowledge-graph/canvas/domain/{domain}")
async def generate_domain_canvas(
    domain: str,
    include_callouts: bool = Query(True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """按 domain 生成知识画布"""
    all_memories = _get_all_memories(db, current_user.id)
    domain_memories = [m for m in all_memories if m.get("domain") == domain]

    if not domain_memories:
        return {"canvas": {"nodes": [], "edges": []}, "node_count": 0, "edge_count": 0, "domain": domain}

    gen = CanvasGenerator()
    canvas = gen.from_memories(domain_memories, include_callouts=include_callouts)
    data = canvas.to_dict()

    return {
        "domain": domain,
        "canvas": data,
        "node_count": len(data["nodes"]),
        "edge_count": len(data["edges"]),
    }


@router.get("/knowledge-graph/graph-data")
async def get_graph_data(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """图数据（节点+边）供前端可视化渲染"""
    idx = _get_link_index(db, current_user.id)
    graph = idx.to_graph_data()

    # 丰富节点信息
    memories = {m["key"]: m for m in _get_all_memories(db, current_user.id)}
    enriched_nodes = []
    for node in graph["nodes"]:
        mem = memories.get(node["id"], {})
        enriched_nodes.append({
            "id": node["id"],
            "label": node["id"],
            "domain": mem.get("domain", ""),
            "importance": mem.get("importance", 0.5),
            "access_count": mem.get("access_count", 0),
        })

    return {
        "nodes": enriched_nodes,
        "edges": graph["edges"],
        "node_count": len(enriched_nodes),
        "edge_count": len(graph["edges"]),
    }


@router.get("/knowledge-graph/stats")
async def knowledge_graph_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """知识图谱统计"""
    from app.models.memory_models import MemoryEntry
    from sqlmodel import func

    stmt = select(MemoryEntry).where(MemoryEntry.user_id == current_user.id).limit(_KG_MAX_MEMORIES)
    entries = db.exec(stmt).all()

    idx = _get_link_index(db, current_user.id)
    all_keys = {e.key for e in entries}

    total_links = sum(
        len(idx.get_forward_links(k)) for k in all_keys
    )
    backlinks_list = idx.get_all_backlinks()
    orphans = idx.get_orphans(all_keys)

    # 统计 domains
    domains: dict[str, int] = {}
    for e in entries:
        domains[e.domain] = domains.get(e.domain, 0) + 1

    return {
        "total_memories": len(entries),
        "total_links": total_links,
        "total_backlinks": len(backlinks_list),
        "most_linked": [
            {"key": b.target_key, "count": b.count}
            for b in sorted(backlinks_list, key=lambda x: x.count, reverse=True)[:10]
        ],
        "orphans": len(orphans),
        "orphan_keys": orphans[:20],
        "domains": domains,
        "graph_density": round(
            total_links / max(len(entries) * (len(entries) - 1), 1), 4
        ),
    }
