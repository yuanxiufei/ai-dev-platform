"""
Call Hierarchy + Type Hierarchy API — 代码层次结构分析

基于 CodebaseMemory CodeGraph 的 CALLS / INHERITS 边关系，
提供 LSP 对标的能力:
- prepareCallHierarchy: 在指定位置准备调用层次结构根节点
- provideIncomingCalls: 谁调用了当前符号？
- provideOutgoingCalls: 当前符号调用了谁？
- prepareTypeHierarchy: 在指定位置准备类型层次结构根节点
- provideSupertypes: 父类型 / 超类
- provideSubtypes: 子类型 / 派生类

借鉴: VSCode workbench/contrib/callHierarchy/ + typeHierarchy/
Session 50: 替换前端 useCallHierarchyStore / useTypeHierarchyStore 的 JS 正则 hack
"""

from __future__ import annotations

import ast
import logging
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.codebase_memory.graph import CodeGraph, NodeType, EdgeType

logger = logging.getLogger("api.hierarchy")

router = APIRouter(prefix="/system/hierarchy", tags=["Code Hierarchy"])

# ── DTO 模型 ─────────────────────────────────────

class RangeModel(BaseModel):
    """行/列范围"""
    start_line: int = 1
    start_column: int = 1
    end_line: int = 1
    end_column: int = 1

class HierarchyItem(BaseModel):
    """层次结构项 — 对标 VSCode CallHierarchyItem / TypeHierarchyItem"""
    name: str
    kind: str  # class / method / function / interface / field / constructor / variable
    uri: str = ""  # file_path
    range: RangeModel = RangeModel()
    selection_range: RangeModel = RangeModel()
    detail: str = ""
    tags: list[str] = []

class IncomingCall(BaseModel):
    """传入调用 — 谁调用了这个符号"""
    from_item: HierarchyItem
    from_ranges: list[RangeModel] = []

class OutgoingCall(BaseModel):
    """传出调用 — 这个符号调用了谁"""
    to_item: HierarchyItem
    from_ranges: list[RangeModel] = []

# ── 符号种类映射 ──────────────────────────────────

SYMBOL_KIND_MAP: dict[str, str] = {
    "Class": "class", "Interface": "interface", "Enum": "enum",
    "Function": "function", "Method": "method", "Constructor": "constructor",
    "Variable": "variable", "Field": "field", "Property": "property",
    "Module": "module", "Type": "interface",
}

# ── CodebaseMemory 辅助 ────────────────────────────

def _load_graph(project_path: str) -> CodeGraph | None:
    """加载已有索引图"""
    from app.core.codebase_memory.indexer import FileIndexer
    indexer = FileIndexer(project_path)
    if not indexer.load_graph():
        return None
    return indexer.graph

def _node_to_item(node: Any) -> HierarchyItem:
    """Graph Node → HierarchyItem DTO"""
    kind_str = str(node.node_type) if hasattr(node, 'node_type') else "variable"
    kind = SYMBOL_KIND_MAP.get(kind_str, "variable")
    return HierarchyItem(
        name=node.name if hasattr(node, 'name') else str(node),
        kind=kind,
        uri=node.file_path if hasattr(node, 'file_path') else "",
        range=RangeModel(
            start_line=node.line_start if hasattr(node, 'line_start') else 1,
            start_column=0,
            end_line=node.line_end if hasattr(node, 'line_end') else 1,
            end_column=0,
        ),
        selection_range=RangeModel(
            start_line=node.line_start if hasattr(node, 'line_start') else 1,
            start_column=0,
            end_line=node.line_start if hasattr(node, 'line_start') else 1,
            end_column=len(node.name) if hasattr(node, 'name') else 0,
        ),
        detail=node.signature if hasattr(node, 'signature') else "",
    )

def _from_indexed_calls(node_id: str, graph: CodeGraph, direction: str) -> list:
    """从索引图中获取调用关系"""
    results = []
    if direction == "incoming":
        callers = graph.get_callers(node_id)
        for caller in callers:
            results.append(IncomingCall(
                from_item=_node_to_item(caller),
                from_ranges=[RangeModel(
                    start_line=caller.line_start,
                    start_column=0,
                    end_line=caller.line_end,
                    end_column=0,
                )],
            ))
    else:
        callees = graph.get_callees(node_id)
        for callee in callees:
            results.append(OutgoingCall(
                to_item=_node_to_item(callee),
                from_ranges=[RangeModel(
                    start_line=callee.line_start,
                    start_column=0,
                    end_line=callee.line_end,
                    end_column=0,
                )],
            ))
    return results

# ── 正则回退解析（无索引图时）───────────────────────

PY_CALL_PATTERN = re.compile(r'(\w+(?:\.\w+)*)\s*\(')
PY_DEF_PATTERN = re.compile(
    r'(?:async\s+)?def\s+(\w+)\s*\([^)]*\)(?:\s*->.*?)?\s*:'
)
PY_CLASS_PATTERN = re.compile(
    r'class\s+(\w+)\s*(?:\((.*?)\))?\s*:'
)

JS_TS_DEF_PATTERN = re.compile(
    r'(?:function\s+(\w+)|(?:class|interface)\s+(\w+)|'
    r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\('
)
JS_CALL_PATTERN = re.compile(r'(?:(?:await\s+)?(\w+(?:\.\w+)*)\s*\()')

def _parse_calls_from_text(code: str, symbol_name: str, language: str,
                            direction: str) -> list:
    """正则回退：从纯文本解析调用关系"""
    lines = code.split('\n')
    results = []

    # 查找符号定义所在函数
    current_func = ""
    func_ranges: list[dict] = []
    for i, line in enumerate(lines):
        m = PY_DEF_PATTERN.match(line.strip()) if language == "Python" else \
            JS_TS_DEF_PATTERN.search(line.strip())
        if m:
            func_name = m.group(1) or m.group(2) or m.group(3) or ""
            if func_name:
                current_func = func_name
                func_ranges.append({"name": func_name, "start": i, "end": i + 30})

    if direction == "outgoing":
        # 找到符号定义，扫描其函数体中的调用
        in_func = False
        func_end = 0
        for i, line in enumerate(lines):
            if re.search(rf'\bdef\s+{re.escape(symbol_name)}\b', line) or \
               re.search(rf'\bfunction\s+{re.escape(symbol_name)}\b', line):
                in_func = True
                func_end = i + 100
            if in_func and i < func_end:
                calls = re.findall(r'(\w+)\s*\(', line)
                for call in calls:
                    if call != symbol_name and not call.startswith('_') and \
                       call not in {'if', 'for', 'while', 'print', 'return',
                                     'raise', 'assert', 'isinstance', 'hasattr',
                                     'getattr', 'setattr', 'len', 'str', 'int',
                                     'float', 'bool', 'dict', 'list', 'tuple'}:
                        if not any(getattr(r, 'name', '') == call for r in results
                                   if isinstance(r, OutgoingCall)):
                            results.append(OutgoingCall(
                                to_item=HierarchyItem(
                                    name=call, kind="function",
                                    range=RangeModel(start_line=i+1, end_line=i+1),
                                    selection_range=RangeModel(start_line=i+1, end_line=i+1),
                                ),
                                from_ranges=[RangeModel(start_line=i+1, start_column=line.index(call) if call in line else 0)],
                            ))
    else:
        # 扫描所有函数体，找谁调用了 symbol_name
        call_regex = re.compile(rf'\b{re.escape(symbol_name)}\s*\(')
        for i, line in enumerate(lines):
            if call_regex.search(line):
                # 向上找所在函数
                caller = ""
                for j in range(i, max(i - 50, -1), -1):
                    m = PY_DEF_PATTERN.match(lines[j].strip()) if language == "Python" else \
                        JS_TS_DEF_PATTERN.search(lines[j].strip())
                    if m:
                        caller = m.group(1) or m.group(2) or m.group(3) or ""
                        break
                if caller and caller != symbol_name:
                    if not any(getattr(r, 'from_item', HierarchyItem(name="")).name == caller
                               for r in results if isinstance(r, IncomingCall)):
                        results.append(IncomingCall(
                            from_item=HierarchyItem(
                                name=caller, kind="function",
                                range=RangeModel(start_line=i+1, end_line=i+1),
                                selection_range=RangeModel(start_line=i+1, end_line=i+1),
                            ),
                            from_ranges=[RangeModel(start_line=i+1)],
                        ))
    return results

def _parse_type_hierarchy_from_text(code: str, symbol_name: str,
                                     language: str, direction: str) -> list[HierarchyItem]:
    """正则回退：从纯文本解析类型层次关系"""
    lines = code.split('\n')
    results: list[HierarchyItem] = []

    class_pattern = re.compile(
        r'(?:class|interface|enum)\s+(\w+)'
        r'(?:\s*:\s*(?:public|private|protected)?\s*(\w+(?:,\s*\w+)*))?'
        r'(?:\s+extends\s+(\w+(?:,\s*\w+)*))?'
        r'(?:\s+implements\s+(\w+(?:,\s*\w+)*))?'
    )

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('//') or stripped.startswith('/*'):
            continue
        m = class_pattern.search(stripped)
        if not m:
            continue
        name = m.group(1)

        if direction == "supertypes":
            # 找到 symbol_name，提取其父类
            if name == symbol_name:
                parents = []
                if m.group(2):
                    parents.extend(s.strip() for s in m.group(2).split(',') if s.strip())
                if m.group(3):
                    parents.extend(s.strip() for s in m.group(3).split(',') if s.strip())
                if m.group(4):
                    parents.extend(s.strip() for s in m.group(4).split(',') if s.strip())
                for p in parents:
                    if p not in {'public', 'private', 'protected', 'virtual', 'abstract'}:
                        results.append(HierarchyItem(
                            name=p, kind="class",
                            range=RangeModel(start_line=i+1, end_line=i+1),
                            selection_range=RangeModel(start_line=i+1, end_line=i+1),
                            detail=f"父类型"
                        ))
        else:
            # 找到继承/实现 symbol_name 的类
            parent_names = []
            if m.group(2): parent_names.extend(s.strip() for s in m.group(2).split(',') if s.strip())
            if m.group(3): parent_names.extend(s.strip() for s in m.group(3).split(',') if s.strip())
            if m.group(4): parent_names.extend(s.strip() for s in m.group(4).split(',') if s.strip())

            if symbol_name in parent_names:
                kind = "class"
                if 'interface' in stripped: kind = "interface"
                elif 'enum' in stripped: kind = "enum"
                results.append(HierarchyItem(
                    name=name, kind=kind,
                    range=RangeModel(start_line=i+1, end_line=i+1),
                    selection_range=RangeModel(start_line=i+1, end_line=i+1),
                    detail=f"继承自 {symbol_name}"
                ))

    return results

# ── API 路由 ──────────────────────────────────────

@router.post("/call/prepare")
async def prepare_call_hierarchy(req: dict) -> dict:
    """
    准备调用层次结构 — 对标 VSCode prepareCallHierarchy

    请求体:
      - file_path: str         — 文件路径
      - line: int              — 光标所在行 (1-based)
      - column: int            — 光标所在列 (1-based, 默认 1)
      - project_path: str      — 项目根路径 (用于加载 CodebaseMemory 图)
      - content: str (可选)    — 文件内容 (无索引图时用于正则回退)
      - language: str (可选)   — 文件语言
    """
    file_path = req.get("file_path", "")
    line = req.get("line", 1)
    column = req.get("column", 1)
    project_path = req.get("project_path", ".")
    content = req.get("content", "")
    language = req.get("language", "")
    symbol_name = req.get("symbol_name", "")  # 可选：直接指定符号名

    roots: list[HierarchyItem] = []

    # 1. 尝试从 CodebaseMemory 图加载
    graph = _load_graph(project_path)
    if graph:
        # 按名称查找节点
        if symbol_name:
            nodes = graph.find_by_name(symbol_name)
        else:
            # 从文件+位置查找
            all_nodes = [n for n in graph._nodes.values()
                         if n.file_path and file_path in n.file_path]
            for node in all_nodes:
                if node.line_start <= line <= node.line_end + 5:
                    symbol_name = node.name
                    nodes = [node]
                    break
            else:
                nodes = []

        for node in nodes:
            roots.append(_node_to_item(node))
        if roots:
            return {"roots": [r.model_dump() for r in roots], "provider": "codebase-memory"}

    # 2. 正则回退
    if content:
        roots = _extract_symbols_from_text(content, line, language)
        if roots:
            return {"roots": [r.model_dump() for r in roots], "provider": "regex-fallback"}

    return {"roots": [], "provider": "none"}


def _extract_symbols_from_text(content: str, line: int, language: str) -> list[HierarchyItem]:
    """从文本内容中提取光标位置的符号"""
    lines = content.split('\n')
    if line < 1 or line > len(lines):
        return []
    target_line = lines[line - 1]

    results: list[HierarchyItem] = []
    if language == "Python":
        for m in PY_DEF_PATTERN.finditer('\n'.join(lines[max(0,line-5):line+5])):
            results.append(HierarchyItem(
                name=m.group(1), kind="function",
                range=RangeModel(start_line=line, end_line=line),
                selection_range=RangeModel(start_line=line, end_line=line),
            ))
        for m in PY_CLASS_PATTERN.finditer('\n'.join(lines[max(0,line-5):line+5])):
            results.append(HierarchyItem(
                name=m.group(1), kind="class",
                range=RangeModel(start_line=line, end_line=line),
                selection_range=RangeModel(start_line=line, end_line=line),
            ))
    else:
        for m in JS_TS_DEF_PATTERN.finditer('\n'.join(lines[max(0,line-5):line+5])):
            name = m.group(1) or m.group(2) or ""
            if name:
                results.append(HierarchyItem(
                    name=name, kind="function",
                    range=RangeModel(start_line=line, end_line=line),
                    selection_range=RangeModel(start_line=line, end_line=line),
                ))
    return results


@router.post("/call/incoming")
async def provide_incoming_calls(req: dict) -> dict:
    """
    获取传入调用 — 谁调用了指定符号？

    请求体:
      - symbol_name: str       — 符号名
      - file_path: str         — 文件路径
      - project_path: str      — 项目路径
      - content: str (可选)    — 文件内容
      - language: str (可选)   — 语言
    """
    symbol_name = req.get("symbol_name", "")
    project_path = req.get("project_path", ".")
    content = req.get("content", "")
    language = req.get("language", "")

    if not symbol_name:
        raise HTTPException(status_code=400, detail="symbol_name is required")

    # 1. 从 CodebaseMemory 图
    graph = _load_graph(project_path)
    if graph:
        nodes = graph.find_by_name(symbol_name)
        if nodes:
            all_calls = []
            for node in nodes:
                all_calls.extend(_from_indexed_calls(node.id, graph, "incoming"))
            if all_calls:
                return {"incoming_calls": [c.model_dump() for c in all_calls], "provider": "codebase-memory"}

    # 2. 正则回退
    if content:
        calls = _parse_calls_from_text(content, symbol_name, language, "incoming")
        return {"incoming_calls": [c.model_dump() for c in calls], "provider": "regex-fallback"}

    return {"incoming_calls": [], "provider": "none"}


@router.post("/call/outgoing")
async def provide_outgoing_calls(req: dict) -> dict:
    """
    获取传出调用 — 指定符号调用了谁？

    请求体: 同 incoming
    """
    symbol_name = req.get("symbol_name", "")
    project_path = req.get("project_path", ".")
    content = req.get("content", "")
    language = req.get("language", "")

    if not symbol_name:
        raise HTTPException(status_code=400, detail="symbol_name is required")

    graph = _load_graph(project_path)
    if graph:
        nodes = graph.find_by_name(symbol_name)
        if nodes:
            all_calls = []
            for node in nodes:
                all_calls.extend(_from_indexed_calls(node.id, graph, "outgoing"))
            if all_calls:
                return {"outgoing_calls": [c.model_dump() for c in all_calls], "provider": "codebase-memory"}

    if content:
        calls = _parse_calls_from_text(content, symbol_name, language, "outgoing")
        return {"outgoing_calls": [c.model_dump() for c in calls], "provider": "regex-fallback"}

    return {"outgoing_calls": [], "provider": "none"}


@router.post("/type/prepare")
async def prepare_type_hierarchy(req: dict) -> dict:
    """
    准备类型层次结构

    请求体:
      - symbol_name: str       — 类型名
      - file_path: str         — 文件路径
      - project_path: str      — 项目路径
      - content: str (可选)
      - language: str (可选)
    """
    symbol_name = req.get("symbol_name", "")
    project_path = req.get("project_path", ".")
    content = req.get("content", "")
    language = req.get("language", "")
    line = req.get("line", 1)

    roots: list[HierarchyItem] = []

    # 1. CodebaseMemory 图
    graph = _load_graph(project_path)
    if graph and symbol_name:
        nodes = graph.find_by_name(symbol_name, NodeType.CLASS)
        if not nodes:
            nodes = graph.find_by_name(symbol_name)
        for node in nodes:
            roots.append(_node_to_item(node))
        if roots:
            return {"roots": [r.model_dump() for r in roots], "provider": "codebase-memory"}

    # 2. 正则回退
    if content and symbol_name:
        lines = content.split('\n')
        for m in PY_CLASS_PATTERN.finditer(content) if language == "Python" else \
                re.finditer(r'(?:class|interface)\s+(\w+)', content):
            if m.group(1) == symbol_name:
                roots.append(HierarchyItem(
                    name=symbol_name, kind="class",
                    range=RangeModel(start_line=line),
                    selection_range=RangeModel(start_line=line),
                ))
                break

    return {"roots": [r.model_dump() for r in roots], "provider": "regex-fallback" if not graph else "none"}


@router.post("/type/supertypes")
async def provide_supertypes(req: dict) -> dict:
    """
    获取父类型 — 当前类的父类/接口

    请求体:
      - symbol_name: str
      - project_path: str
      - content: str (可选)
      - language: str (可选)
    """
    symbol_name = req.get("symbol_name", "")
    project_path = req.get("project_path", ".")
    content = req.get("content", "")
    language = req.get("language", "")

    if not symbol_name:
        raise HTTPException(status_code=400, detail="symbol_name is required")

    results: list[HierarchyItem] = []

    # 1. CodebaseMemory 图 — INHERITS 边
    graph = _load_graph(project_path)
    if graph:
        nodes = graph.find_by_name(symbol_name, NodeType.CLASS)
        if not nodes:
            nodes = graph.find_by_name(symbol_name)
        for node in nodes:
            # 查找 INHERITS 出边
            out_edges = [e for e in graph._edges
                         if e.source_id == node.id and e.edge_type == EdgeType.INHERITS]
            for edge in out_edges:
                parent = graph.get_node(edge.target_id)
                if parent:
                    results.append(_node_to_item(parent))
        if results:
            return {"supertypes": [r.model_dump() for r in results], "provider": "codebase-memory"}

    # 2. 正则回退
    if content:
        results = _parse_type_hierarchy_from_text(content, symbol_name, language, "supertypes")
        return {"supertypes": [r.model_dump() for r in results], "provider": "regex-fallback"}

    return {"supertypes": [], "provider": "none"}


@router.post("/type/subtypes")
async def provide_subtypes(req: dict) -> dict:
    """
    获取子类型 — 继承当前类的子类

    请求体: 同 supertypes
    """
    symbol_name = req.get("symbol_name", "")
    project_path = req.get("project_path", ".")
    content = req.get("content", "")
    language = req.get("language", "")

    if not symbol_name:
        raise HTTPException(status_code=400, detail="symbol_name is required")

    results: list[HierarchyItem] = []

    # 1. CodebaseMemory 图
    graph = _load_graph(project_path)
    if graph:
        nodes = graph.find_by_name(symbol_name, NodeType.CLASS)
        if not nodes:
            nodes = graph.find_by_name(symbol_name)
        for node in nodes:
            in_edges = [e for e in graph._edges
                        if e.target_id == node.id and e.edge_type == EdgeType.INHERITS]
            for edge in in_edges:
                child = graph.get_node(edge.source_id)
                if child:
                    results.append(_node_to_item(child))
        if results:
            return {"subtypes": [r.model_dump() for r in results], "provider": "codebase-memory"}

    # 2. 正则回退
    if content:
        results = _parse_type_hierarchy_from_text(content, symbol_name, language, "subtypes")
        return {"subtypes": [r.model_dump() for r in results], "provider": "regex-fallback"}

    return {"subtypes": [], "provider": "none"}
