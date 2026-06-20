"""
CKG API 路由 — 代码知识图谱管理

端点：
- POST /agent/ckg/index    — 索引项目
- GET  /agent/ckg/search   — 搜索代码符号
- GET  /agent/ckg/stats    — 索引统计
- DELETE /agent/ckg/{project} — 清除项目索引
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.ckg import CodeKnowledgeGraph, get_ckg

router = APIRouter(prefix="/agent/ckg", tags=["CKG"])


def _get_ckg() -> CodeKnowledgeGraph:
    """获取全局 CKG 实例"""
    from app.core.config import settings
    return get_ckg(db_path=settings.CKG_DB_PATH)


@router.post("/index")
async def index_project(
    project_path: str = Query(..., description="项目目录路径"),
    language: str | None = Query(None, description="仅索引指定语言 (python/typescript/java/...)"),
) -> dict[str, Any]:
    """索引项目代码结构"""
    try:
        ckg = _get_ckg()
        count = ckg.index_project(project_path, language_filter=language)
        return {
            "status": "ok",
            "symbols_indexed": count,
            "project_path": project_path,
            "language_filter": language,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_symbols(
    query: str = Query(..., description="搜索关键词"),
    kind: str | None = Query(None, description="类型: function | class | method"),
    file_pattern: str | None = Query(None, description="文件名通配符 (如 *.py)"),
    project_path: str | None = Query(None, description="限定项目路径"),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """搜索代码符号"""
    try:
        ckg = _get_ckg()
        result = ckg.search(
            query=query,
            kind=kind,
            file_pattern=file_pattern,
            project_path=project_path,
            limit=limit,
        )
        return {
            "status": "ok",
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind,
                    "file_path": s.file_path,
                    "line_number": s.line_number,
                    "body": s.body[:300] + ("..." if len(s.body) > 300 else ""),
                    "parent_class": s.parent_class,
                    "language": s.language,
                }
                for s in result.symbols
            ],
            "total_found": result.total_found,
            "time_ms": result.time_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/function/{name}")
async def search_function(
    name: str,
    project_path: str | None = Query(None),
) -> dict[str, Any]:
    """搜索函数定义"""
    try:
        ckg = _get_ckg()
        result = ckg.search_function(name, project_path=project_path)
        return {
            "status": "ok",
            "symbols": [
                {
                    "name": s.name,
                    "file_path": s.file_path,
                    "line_number": s.line_number,
                    "body": s.body[:200],
                    "language": s.language,
                }
                for s in result.symbols
            ],
            "total_found": result.total_found,
            "time_ms": result.time_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/class/{name}")
async def search_class(
    name: str,
    project_path: str | None = Query(None),
) -> dict[str, Any]:
    """搜索类定义"""
    try:
        ckg = _get_ckg()
        result = ckg.search_class(name, project_path=project_path)
        return {
            "status": "ok",
            "symbols": [
                {
                    "name": s.name,
                    "file_path": s.file_path,
                    "line_number": s.line_number,
                    "body": s.body[:200],
                    "language": s.language,
                }
                for s in result.symbols
            ],
            "total_found": result.total_found,
            "time_ms": result.time_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/method/{class_name}/{method_name}")
async def search_method(
    class_name: str,
    method_name: str,
    project_path: str | None = Query(None),
) -> dict[str, Any]:
    """搜索类方法"""
    try:
        ckg = _get_ckg()
        result = ckg.search_method(class_name, method_name, project_path=project_path)
        return {
            "status": "ok",
            "symbols": [
                {
                    "name": s.name,
                    "file_path": s.file_path,
                    "line_number": s.line_number,
                    "body": s.body[:200],
                    "language": s.language,
                }
                for s in result.symbols
            ],
            "total_found": result.total_found,
            "time_ms": result.time_ms,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats() -> dict[str, Any]:
    """获取索引统计"""
    try:
        ckg = _get_ckg()
        stats = ckg.get_stats()
        return {"status": "ok", **stats}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{project_name}")
async def clear_project(project_name: str) -> dict[str, Any]:
    """清除指定项目的索引"""
    try:
        ckg = _get_ckg()
        count = ckg.clear_project(project_name)
        return {"status": "ok", "deleted": count, "project": project_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/")
async def clear_all() -> dict[str, Any]:
    """清除所有索引"""
    try:
        ckg = _get_ckg()
        count = ckg.clear_all()
        return {"status": "ok", "deleted": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
