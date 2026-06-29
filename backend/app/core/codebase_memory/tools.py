"""
MCP 工具实现 — 为 codebase-memory 提供标准 MCP 接口

实现 8 个核心工具：
- search_graph: BM25 风格关键词搜索
- search_code: 代码内容搜索
- get_code_snippet: 获取函数源代码
- get_architecture: 架构总览
- trace_path: 调用链追踪
- index_repository: 索引仓库
- list_projects: 列出项目
- index_status: 索引状态
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .graph import CodeGraph, NodeType, EdgeType
from .indexer import FileIndexer

logger = logging.getLogger("cbm.tools")

# 全局索引器实例
_indexers: dict[str, FileIndexer] = {}


def _get_indexer(project_path: str) -> FileIndexer:
    """获取或创建索引器"""
    path = str(Path(project_path).resolve())
    if path not in _indexers:
        _indexers[path] = FileIndexer(path)
    return _indexers[path]


# ── 工具实现 ──────────────────────────────────

def tool_index_repository(args: dict) -> dict:
    """索引仓库"""
    repo_path = args.get("repo_path") or args.get("path", "")
    if not repo_path:
        return {"error": "repo_path is required"}
    indexer = _get_indexer(repo_path)
    indexer.graph = CodeGraph()  # 重新构建
    return indexer.index(force=True)


def tool_search_graph(args: dict) -> dict:
    """BM25 风格搜索知识图谱"""
    query = args.get("query", "").lower()
    project = args.get("project", "")
    limit = min(args.get("limit", 20), 200)
    label = args.get("label")

    indexer = _find_by_project(project)
    if not indexer:
        return {"error": f"Project '{project}' not indexed", "results": []}

    graph = indexer.graph

    # 分词 + 得分
    terms = query.split()
    scored: list[tuple[float, dict]] = []

    for node in graph._nodes.values():
        if label and str(node.node_type) != label:
            continue

        text = f"{node.name} {node.qualified_name} {node.signature}".lower()
        score = 0.0

        # BM25 简化版：TF + IDF 启发式
        for term in terms:
            count = text.count(term)
            if count > 0:
                tf = 1 + (0.5 * min(count, 5) / 5)
                # IDF 启发式：稀有词权重更高
                df = sum(1 for n in graph._nodes.values()
                         if term in f"{n.name} {n.qualified_name}".lower())
                idf = max(0.1, len(graph._nodes) / max(1, df))
                score += tf * idf

        # 类型加权
        type_bonus = {
            NodeType.FUNCTION: 10,
            NodeType.METHOD: 8,
            NodeType.CLASS: 5,
            NodeType.ROUTE: 8,
        }.get(node.node_type, 1)
        score += type_bonus

        if score > 0:
            scored.append((score, node.to_dict()))

    scored.sort(key=lambda x: -x[0])
    results = [r for _, r in scored[:limit]]

    return {
        "results": results,
        "total": len(scored),
        "has_more": len(scored) > limit,
        "query": query,
    }


def tool_search_code(args: dict) -> dict:
    """grep 风格代码搜索（图增强排序）"""
    pattern = args.get("pattern", "")
    project = args.get("project", "")
    limit = min(args.get("limit", 20), 100)
    file_filter = args.get("file_pattern")

    if not pattern:
        return {"error": "pattern is required", "results": []}

    indexer = _find_by_project(project)
    if not indexer:
        return {"error": f"Project '{project}' not indexed", "results": []}

    graph = indexer.graph
    results: list[dict] = []

    # 在已索引文件中搜索
    for node in graph._nodes.values():
        if node.node_type != NodeType.FILE:
            continue
        if file_filter:
            import fnmatch
            if not fnmatch.fnmatch(Path(node.file_path).name, file_filter):
                continue

        try:
            source = Path(node.file_path).read_text(encoding="utf-8", errors="ignore")
            lines = source.split('\n')
            for i, line in enumerate(lines):
                if pattern.lower() in line.lower():
                    results.append({
                        "file": node.file_path,
                        "line": i + 1,
                        "line_content": line.strip()[:200],
                    })
        except Exception:
            continue

    # 按节点重要性排序
    total_grep = len(results)
    if len(results) > limit:
        results = results[:limit]

    return {
        "results": results[:limit],
        "total_grep_matches": total_grep,
        "total_results": len(results),
        "has_more": total_grep > limit,
    }


def tool_get_code_snippet(args: dict) -> dict:
    """获取函数/类的源代码"""
    qualified_name = args.get("qualified_name", "")
    project = args.get("project", "")

    if not qualified_name:
        return {"error": "qualified_name is required"}

    indexer = _find_by_project(project)
    if not indexer:
        return {"error": f"Project '{project}' not indexed"}

    # 精确匹配
    for node in indexer.graph._nodes.values():
        if node.qualified_name == qualified_name:
            return _read_node_source(node)
        if node.name == qualified_name and node.node_type in (NodeType.FUNCTION, NodeType.METHOD):
            return _read_node_source(node)

    # 模糊匹配建议
    suggestions = []
    for node in indexer.graph._nodes.values():
        if qualified_name.lower() in node.qualified_name.lower():
            suggestions.append(node.qualified_name)
        if len(suggestions) >= 5:
            break

    return {
        "error": f"'{qualified_name}' not found",
        "suggestions": suggestions,
    }


def _read_node_source(node) -> dict:
    """读取节点的源代码"""
    try:
        source = Path(node.file_path).read_text(encoding="utf-8", errors="ignore")
        lines = source.split('\n')
        start = max(0, node.line_start - 1)
        end = min(len(lines), node.line_end or (start + 50))
        snippet = '\n'.join(lines[start:end])
        return {
            "qualified_name": node.qualified_name,
            "file": node.file_path,
            "line_start": node.line_start,
            "line_end": node.line_end,
            "source_code": snippet,
            "language": node.language,
        }
    except Exception as e:
        return {"error": str(e)}


def tool_get_architecture(args: dict) -> dict:
    """获取架构总览"""
    project = args.get("project", "")
    indexer = _find_by_project(project)
    if not indexer:
        return {"error": f"Project '{project}' not indexed"}

    graph = indexer.graph

    # 聚合包/目录结构
    packages: dict[str, dict] = {}
    for node in graph._nodes.values():
        if node.node_type == NodeType.FILE:
            pkg = str(Path(node.file_path).parent)
            if pkg not in packages:
                packages[pkg] = {"name": pkg, "file_count": 0, "function_count": 0}
            packages[pkg]["file_count"] += 1

    for node in graph._nodes.values():
        if node.node_type in (NodeType.FUNCTION, NodeType.METHOD):
            pkg = str(Path(node.file_path).parent)
            if pkg in packages:
                packages[pkg]["function_count"] += 1

    return {
        "project": project,
        "total_nodes": graph.node_count,
        "total_edges": graph.edge_count,
        "node_labels": [
            {"label": k, "count": v}
            for k, v in sorted(graph.node_type_counts().items())
        ],
        "edge_types": [
            {"type": k, "count": v}
            for k, v in sorted(graph.edge_type_counts().items())
        ],
        "languages": [
            {"language": k, "file_count": v}
            for k, v in sorted(graph.language_counts().items())
        ],
        "packages": [
            {"name": k, "node_count": v["file_count"], "fan_in": 0, "fan_out": 0}
            for k, v in sorted(packages.items())
        ],
    }


def tool_trace_path(args: dict) -> dict:
    """追踪调用链路径"""
    function_name = args.get("function_name", "")
    project = args.get("project", "")
    direction = args.get("direction", "both")
    depth = min(args.get("depth", 3), 10)

    indexer = _find_by_project(project)
    if not indexer:
        return {"error": f"Project '{project}' not indexed"}

    # 查找起始节点
    start_nodes = indexer.graph.find_by_name(function_name)
    if not start_nodes:
        return {"error": f"'{function_name}' not found", "hops": []}

    start = start_nodes[0]
    hops: list[dict] = []

    # 出站（被调用者）
    if direction in ("outbound", "both"):
        _trace_hops(indexer.graph, start.id, "outbound", depth, hops, set())

    # 入站（调用者）
    if direction in ("inbound", "both"):
        _trace_hops(indexer.graph, start.id, "inbound", depth, hops, set())

    return {
        "function": start.qualified_name,
        "direction": direction,
        "total_hops": len(hops),
        "hops": hops[:50],  # 限制返回
    }


def _trace_hops(graph: CodeGraph, node_id: str, direction: str,
                depth: int, hops: list, visited: set) -> None:
    """递归追踪调用链"""
    if depth <= 0 or node_id in visited:
        return
    visited.add(node_id)

    edges = graph.get_outbound(node_id) if direction == "outbound" else graph.get_inbound(node_id)
    for edge in edges:
        if edge.edge_type != EdgeType.CALLS:
            continue
        target_id = edge.target_id if direction == "outbound" else edge.source_id
        target = graph.get_node(target_id)
        if target:
            hops.append({
                "from": graph.get_node(node_id).qualified_name if graph.get_node(node_id) else "?",
                "to": target.qualified_name,
                "direction": direction,
            })
            _trace_hops(graph, target_id, direction, depth - 1, hops, visited)


def tool_list_projects(args: dict) -> dict:
    """列出所有已索引项目"""
    return {"projects": list(_indexers.keys()), "count": len(_indexers)}


def tool_index_status(args: dict) -> dict:
    """获取索引状态"""
    project = args.get("project", "")
    indexer = _find_by_project(project)
    if not indexer:
        return {"indexed": False, "project": project, "hint": "Use index_repository to index this project"}
    return indexer.get_status()


# ── 辅助函数 ──────────────────────────────────

def _find_by_project(project_name: str) -> FileIndexer | None:
    """通过项目名查找索引器"""
    for path, indexer in _indexers.items():
        if indexer.project_name == project_name:
            return indexer
        if project_name in path:
            return indexer
    return None


# ── 工具路由 ──────────────────────────────────

TOOL_REGISTRY: dict[str, callable] = {
    "index_repository": tool_index_repository,
    "search_graph": tool_search_graph,
    "search_code": tool_search_code,
    "get_code_snippet": tool_get_code_snippet,
    "get_architecture": tool_get_architecture,
    "trace_path": tool_trace_path,
    "list_projects": tool_list_projects,
    "index_status": tool_index_status,
}


def call_tool(tool_name: str, arguments: dict) -> str:
    """调用工具并返回 JSON 字符串"""
    func = TOOL_REGISTRY.get(tool_name)
    if not func:
        return json.dumps({"error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    try:
        result = func(arguments)
        return json.dumps(result, ensure_ascii=False, default=str)
    except Exception as e:
        logger.exception("Tool %s failed", tool_name)
        return json.dumps({"error": str(e)}, ensure_ascii=False)
