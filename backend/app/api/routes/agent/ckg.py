"""
代码知识图谱 API 路由 — 自研 CodebaseMemory 系统

合并原 CKG 路由，统一使用 CodebaseMemory 作为单一代码分析后端。

端点：
- POST /agent/ckg/index    — 索引项目
- GET  /agent/ckg/search   — 搜索代码符号
- GET  /agent/ckg/stats    — 索引统计
- DELETE /agent/ckg/{project} — 清除项目索引
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.codebase_memory import (
    FileIndexer,
    _indexers as _global_indexers,
)

router = APIRouter(prefix="/agent/ckg", tags=["CKG"])


def _get_indexer(project_path: str | None = None) -> FileIndexer:
    """获取或创建索引器实例"""
    if not project_path:
        # 使用第一个已索引的项目
        if _global_indexers:
            return next(iter(_global_indexers.values()))
        raise HTTPException(status_code=404, detail="No indexed projects found")

    from pathlib import Path
    path = str(Path(project_path).resolve())
    if path in _global_indexers:
        return _global_indexers[path]

    indexer = FileIndexer(project_path)
    if not indexer.load_graph():
        raise HTTPException(status_code=404, detail=f"Project not indexed: {project_path}")
    _global_indexers[indexer.project_name] = indexer
    return indexer


@router.post("/index")
async def index_project(
    project_path: str = Query(..., description="项目目录路径"),
    force: bool = Query(False, description="强制重建索引"),
) -> dict[str, Any]:
    """索引项目代码结构"""
    try:
        from pathlib import Path
        path = str(Path(project_path).resolve())
        indexer = FileIndexer(path)
        result = indexer.index(force=force)
        _global_indexers[indexer.project_name] = indexer
        return {
            "status": "ok",
            "project": indexer.project_name,
            **result,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_symbols(
    query: str = Query(..., description="搜索关键词"),
    kind: str | None = Query(None, description="类型: File/Class/Function/Method/Route/Enum"),
    file_pattern: str | None = Query(None, description="文件名过滤"),
    project_path: str | None = Query(None, description="限定项目路径"),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """搜索代码符号"""
    try:
        indexer = _get_indexer(project_path)

        from app.core.codebase_memory.graph import NodeType
        node_type = NodeType(kind) if kind else None

        results = []
        for node in indexer.graph._nodes.values():
            if query.lower() not in node.name.lower() and query.lower() not in node.qualified_name.lower():
                continue
            if node_type and node.node_type != node_type:
                continue
            if file_pattern:
                import fnmatch
                if not fnmatch.fnmatch(node.file_path, file_pattern):
                    continue
            results.append({
                "name": node.name,
                "kind": str(node.node_type),
                "file_path": node.file_path,
                "line_number": node.line_start,
                "qualified_name": node.qualified_name,
                "signature": node.signature,
                "language": node.language,
            })
            if len(results) >= limit:
                break

        return {
            "status": "ok",
            "symbols": results,
            "total_found": len(results),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(project_path: str | None = Query(None)) -> dict[str, Any]:
    """获取索引统计"""
    try:
        if project_path:
            indexer = _get_indexer(project_path)
            status = indexer.get_status()
            return {"status": "ok", **status}

        # 汇总所有项目
        total_nodes = sum(i.graph.node_count for i in _global_indexers.values())
        total_edges = sum(i.graph.edge_count for i in _global_indexers.values())
        projects = [idx.project_name for idx in _global_indexers.values()]

        return {
            "status": "ok",
            "total_nodes": total_nodes,
            "total_edges": total_edges,
            "projects_count": len(projects),
            "projects": projects,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{project_name}")
async def clear_project(project_name: str) -> dict[str, Any]:
    """清除指定项目的索引"""
    try:
        if project_name in _global_indexers:
            del _global_indexers[project_name]
            return {"status": "ok", "deleted": 1, "project": project_name}
        return {"status": "ok", "deleted": 0, "project": project_name, "message": "Not found"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/")
async def clear_all() -> dict[str, Any]:
    """清除所有索引"""
    try:
        count = len(_global_indexers)
        _global_indexers.clear()
        return {"status": "ok", "deleted": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
