"""
Memory 可视化 API — 暴露 MemoryNode/MemoryEdge 图数据供前端渲染

端点:
- GET /api/v1/memory/graph-data  — 全量图数据（节点+边）
- GET /api/v1/memory/graph-stats — 记忆图统计
"""

from fastapi import APIRouter, Query, HTTPException
from app.core.memory.memory_store import get_memory_store, MemoryType

router = APIRouter(prefix="/memory", tags=["memory-viz"])


@router.get("/graph-data")
async def memory_graph_data(
    type: str = Query(default=None, description="按类型过滤: code/decision/lesson/fact/pattern"),
    min_importance: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> dict:
    """获取记忆图数据（节点+边），供前端知识图谱组件渲染"""
    try:
        store = get_memory_store()
        db = store._ensure_db()
        db.row_factory = None

        # 构建查询
        where_clauses = []
        params = []

        if type:
            where_clauses.append("memory_type = ?")
            params.append(type)
        if min_importance > 0:
            where_clauses.append("importance >= ?")
            params.append(min_importance)

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # 查询节点
        nodes_rows = db.execute(
            f"SELECT id, content, memory_type, importance, source, tags, metadata, created_at "
            f"FROM memory_nodes{where_sql} ORDER BY importance DESC LIMIT ?",
            params + [limit],
        ).fetchall()

        # 查询涉及这些节点的边
        node_ids = {r[0] for r in nodes_rows}
        if node_ids:
            placeholders = ",".join(["?"] * len(node_ids))
            edge_rows = db.execute(
                f"SELECT source_id, target_id, relation_type, weight "
                f"FROM memory_edges WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})",
                list(node_ids) + list(node_ids),
            ).fetchall()
        else:
            edge_rows = []

        # 构建节点列表
        import json as _json
        nodes = []
        for r in nodes_rows:
            tags = []
            metadata = {}
            try:
                tags = _json.loads(r[5]) if r[5] else []
            except Exception:
                pass
            try:
                metadata = _json.loads(r[6]) if r[6] else {}
            except Exception:
                pass

            nodes.append({
                "id": r[0],
                "label": r[1][:80] if r[1] else "",
                "content_preview": r[1][:200] if r[1] else "",
                "type": r[2],
                "importance": r[3],
                "source": r[4],
                "tags": tags,
                "metadata": metadata,
                "created_at": r[7],
            })

        # 构建边列表
        edges = [
            {"from": r[0], "to": r[1], "relation": r[2], "weight": r[3]}
            for r in edge_rows
        ]

        # 统计
        type_counts = {}
        for n in nodes:
            t = n["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "type_counts": type_counts,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Memory graph error: {e}")


@router.get("/graph-stats")
async def memory_graph_stats() -> dict:
    """获取记忆图统计摘要"""
    try:
        store = get_memory_store()
        return store.stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Memory stats error: {e}")
