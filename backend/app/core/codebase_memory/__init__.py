"""
Codebase Memory — 原生 Python 代码库知识图谱

参照 codebase-memory-mcp 的功能设计，纯 Python 实现：
- AST 代码解析 (Python 内置 ast 模块)
- 知识图谱构建 (函数/类/调用关系/导入关系)
- SQLite 增量持久化
- 平台 Tool 注册
- 8 个查询工具

版权: 全部代码自主开发，不包含任何第三方代码拷贝
"""

from __future__ import annotations

import logging
from pathlib import Path

__version__ = "0.1.0"

from .graph import CodeGraph, Node, NodeType, EdgeType, Edge
from .indexer import FileIndexer
from .parser import parse_source
from .tools import TOOL_REGISTRY, call_tool, _indexers

logger = logging.getLogger("codebase_memory")


def init_codebase_memory(project_path: str | None = None) -> dict | None:
    """
    初始化原生 Codebase Memory 系统

    1. 扫描并索引项目代码库
    2. 构建知识图谱（函数/类/调用关系）
    3. 返回索引统计

    Args:
        project_path: 项目路径（默认自动检测）

    Returns:
        初始化结果字典
    """
    if not project_path:
        # __file__ -> .../backend/app/core/codebase_memory/__init__.py
        # go up 5 levels: __init__.py -> codebase_memory -> core -> app -> backend -> project_root
        project_path = str(Path(__file__).resolve().parent.parent.parent.parent.parent)

    indexer = FileIndexer(project_path)

    # 加载缓存图
    if indexer.load_graph():
        logger.info("Codebase Memory: loaded cached graph (%d nodes, %d edges)",
                     indexer.graph.node_count, indexer.graph.edge_count)
        result = {
            "name": "codebase-memory",
            "implementation": "native",
            "version": __version__,
            "project": indexer.project_name,
            "nodes": indexer.graph.node_count,
            "edges": indexer.graph.edge_count,
            "tools": len(TOOL_REGISTRY),
            "files_indexed": 0,  # 从缓存加载
        }
    else:
        logger.info("Indexing project...")
        result = indexer.index()
        indexer.save_graph()
        logger.info("Indexed: %d nodes, %d edges", indexer.graph.node_count, indexer.graph.edge_count)

    _indexers[indexer.project_name] = indexer

    return {
        "name": "codebase-memory",
        "implementation": "native",
        "version": __version__,
        "project": indexer.project_name,
        "nodes": indexer.graph.node_count,
        "edges": indexer.graph.edge_count,
        "tools": len(TOOL_REGISTRY),
        "files_indexed": 0,
    }