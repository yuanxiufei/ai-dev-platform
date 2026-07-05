"""
工作区符号搜索 API (Session 48)

对标 VSCode workspace/symbols + Go to Symbol in Workspace (Ctrl+T)。
利用 CodebaseMemory 知识图谱进行跨文件符号索引和搜索。
"""

from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/system/symbols", tags=["system-symbols"])


# ── 数据模型 ──

class SymbolItem(BaseModel):
    """符号条目"""
    name: str = Field(..., description="符号名称")
    kind: str = Field(..., description="符号类型: function/class/variable/method/module/interface/enum")
    container_name: Optional[str] = Field(default=None, description="所属容器 (类名/模块名)")
    file_path: str = Field(default="", description="文件路径")
    line: int = Field(default=1, description="起始行号 (1-based)")
    column: int = Field(default=1, description="起始列号 (1-based)")
    end_line: Optional[int] = Field(default=None)
    end_column: Optional[int] = Field(default=None)

class SearchRequest(BaseModel):
    """符号搜索请求"""
    query: str = Field(..., description="搜索关键词 (支持模糊匹配)")
    file_pattern: Optional[str] = Field(default=None, description="限制文件 glob, 如 '*.py'")
    kind_filter: Optional[str] = Field(default=None, description="符号类型过滤: function/class/variable/method/interface")
    max_results: int = Field(default=30, ge=1, le=200)

class SearchResponse(BaseModel):
    """符号搜索响应"""
    symbols: List[SymbolItem] = Field(default_factory=list)
    total: int = 0
    query: str = ""


# ── 符号提取逻辑 (纯正则方案, 不依赖外部解析器) ──

# 语言 → 符号提取器
SYMBOL_PATTERNS: dict[str, dict] = {
    "python": {
        "function": re.compile(r'^\s*def\s+(\w+)\s*\(', re.MULTILINE),
        "class": re.compile(r'^\s*class\s+(\w+)\s*[(:]', re.MULTILINE),
        "variable": re.compile(r'^\s*(\w+)\s*[:=]\s*', re.MULTILINE),
        "method": re.compile(r'^\s{4,}def\s+(\w+)\s*\(', re.MULTILINE),
        "module": re.compile(r'^(?:import|from)\s+(\w+)', re.MULTILINE),
    },
    "javascript": {
        "function": re.compile(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>|(\w+)\s*\([^)]*\)\s*{)', re.MULTILINE),
        "class": re.compile(r'class\s+(\w+)', re.MULTILINE),
        "variable": re.compile(r'(?:const|let|var)\s+(\w+)\s*=', re.MULTILINE),
        "method": re.compile(r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*{', re.MULTILINE),
        "interface": re.compile(r'(?:interface|type)\s+(\w+)', re.MULTILINE),
    },
    "typescript": {
        "function": re.compile(r'(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*(?::\s*\w+)?\s*=>|(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*{)', re.MULTILINE),
        "class": re.compile(r'class\s+(\w+)', re.MULTILINE),
        "variable": re.compile(r'(?:const|let|var)\s+(\w+)\s*(?::\s*\w+(?:\[\])?)?\s*=', re.MULTILINE),
        "method": re.compile(r'(?:public|private|protected|async\s+)?(\w+)\s*\([^)]*\)\s*(?::\s*\w+)?\s*{', re.MULTILINE),
        "interface": re.compile(r'(?:interface|type|enum)\s+(\w+)', re.MULTILINE),
        "enum": re.compile(r'enum\s+(\w+)', re.MULTILINE),
    },
    "go": {
        "function": re.compile(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(', re.MULTILINE),
        "struct": re.compile(r'^type\s+(\w+)\s+struct\s*{', re.MULTILINE),
        "interface": re.compile(r'^type\s+(\w+)\s+interface\s*{', re.MULTILINE),
        "variable": re.compile(r'^(?:var\s+(\w+)|(?:const|let|var)\s*\(\s*$)', re.MULTILINE),
    },
    "rust": {
        "function": re.compile(r'^\s*(?:pub\s+)?fn\s+(\w+)\s*[<(]', re.MULTILINE),
        "struct": re.compile(r'^\s*(?:pub\s+)?struct\s+(\w+)', re.MULTILINE),
        "enum": re.compile(r'^\s*(?:pub\s+)?enum\s+(\w+)', re.MULTILINE),
        "trait": re.compile(r'^\s*(?:pub\s+)?trait\s+(\w+)', re.MULTILINE),
        "impl": re.compile(r'^\s*impl\s+(?:[\w<>,:\s]+\s+)?(?:for\s+)?(\w+)', re.MULTILINE),
    },
    "java": {
        "class": re.compile(r'(?:public\s+)?class\s+(\w+)', re.MULTILINE),
        "interface": re.compile(r'(?:public\s+)?interface\s+(\w+)', re.MULTILINE),
        "enum": re.compile(r'(?:public\s+)?enum\s+(\w+)', re.MULTILINE),
        "method": re.compile(r'(?:public|private|protected|static|\s)+\w+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+)?\s*{', re.MULTILINE),
    },
    "cpp": {
        "function": re.compile(r'^\s*(?:virtual\s+)?(?:static\s+)?\w+(?:<[^>]+>)?(?:\s*\*|\s*&)?\s+(\w+)\s*\([^)]*\)\s*(?:const\s*)?(?:override\s*)?{?', re.MULTILINE),
        "class": re.compile(r'(?:class|struct)\s+(\w+)', re.MULTILINE),
        "enum": re.compile(r'enum\s+(?:class\s+)?(\w+)', re.MULTILINE),
    },
}

# 扩展名 → 语言映射
EXT_TO_LANG_SYMBOL: dict[str, str] = {
    ".py": "python", ".pyw": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".mts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".h": "cpp", ".c": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin", ".kts": "kotlin",
    ".dart": "dart",
    ".vue": "javascript",  # Vue SFC → JS/TS 混合
}


def _extract_symbols_from_content(content: str, file_path: str) -> List[SymbolItem]:
    """从内容中提取符号"""
    ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
    lang = EXT_TO_LANG_SYMBOL.get(ext.lower(), "")
    if not lang or lang not in SYMBOL_PATTERNS:
        return []
    
    patterns = SYMBOL_PATTERNS[lang]
    symbols: List[SymbolItem] = []
    lines = content.split("\n")
    
    for kind, pattern in patterns.items():
        for match in pattern.finditer(content):
            name = next((g for g in match.groups() if g), None)
            if not name:
                continue
            # 过滤常见误匹配
            if name in ("if", "for", "while", "switch", "catch", "try", "return", "throw", "new", "else", "do", "case"):
                continue
            
            # 计算行号
            start_pos = match.start()
            line_num = content[:start_pos].count("\n") + 1
            col_num = start_pos - content[:start_pos].rfind("\n")
            
            # 查找容器
            container = None
            for i in range(line_num - 2, -1, -1):
                if i < len(lines):
                    cls_match = re.match(r'^\s*class\s+(\w+)', lines[i])
                    if cls_match:
                        container = cls_match.group(1)
                        break
            
            symbols.append(SymbolItem(
                name=name,
                kind=kind,
                container_name=container,
                file_path=file_path,
                line=line_num,
                column=col_num,
            ))
    
    return symbols


# ── API 路由 ──

@router.post("/search", response_model=SearchResponse)
async def search_symbols(req: SearchRequest) -> SearchResponse:
    """
    工作区符号搜索 (对标 VSCode Ctrl+T / Cmd+P #)
    
    在当前工作区搜索匹配的符号（函数/类/变量等），
    支持模糊匹配和类型过滤。
    """
    try:
        from app.core.codebase_memory.graph import CodeGraph
        from app.core.codebase_memory.indexer import FileIndexer
    except ImportError:
        return SearchResponse(symbols=[], total=0, query=req.query)

    # 加载知识图谱
    graph = CodeGraph()
    try:
        graph.load_from_db()
    except Exception:
        return SearchResponse(symbols=[], total=0, query=req.query)

    # 从图中搜索匹配节点
    query_lower = req.query.lower()
    all_symbols: List[SymbolItem] = []

    for node in graph.nodes.values():
        # 跳过非符号节点
        if node.node_type not in ("function", "class", "method", "variable", "module", "interface", "enum", "struct", "trait"):
            continue
        
        # 名称匹配（模糊）
        name_lower = node.name.lower() if node.name else ""
        if query_lower not in name_lower:
            continue
        
        # 文件过滤
        if req.file_pattern:
            # 简单的 glob 匹配
            glob_re = req.file_pattern.replace("*", ".*").replace("?", ".")
            if not re.search(glob_re, node.file_path or ""):
                continue
        
        # 类型过滤
        if req.kind_filter and node.node_type != req.kind_filter:
            continue
        
        all_symbols.append(SymbolItem(
            name=node.name or "unknown",
            kind=node.node_type,
            container_name=node.parent_name,
            file_path=node.file_path or "",
            line=node.start_line or 1,
            column=node.start_col or 1,
            end_line=node.end_line,
            end_column=node.end_col,
        ))

    # 限制结果
    total = len(all_symbols)
    symbols = sorted(all_symbols, key=lambda s: (s.file_path, s.line))[:req.max_results]

    return SearchResponse(symbols=symbols, total=total, query=req.query)


@router.post("/extract", response_model=List[SymbolItem])
async def extract_file_symbols(
    content: str = Query(..., description="文件内容"),
    file_path: str = Query(default="untitled", description="文件路径 (用于确定语言)"),
) -> list[SymbolItem]:
    """
    提取单个文件的符号列表 (对标 Document Symbols / Go to Symbol)
    
    从代码内容中提取函数、类、变量等符号，返回扁平列表。
    """
    return _extract_symbols_from_content(content, file_path)


@router.get("/languages", response_model=List[str])
async def get_supported_languages() -> list[str]:
    """获取支持符号提取的语言列表"""
    return sorted(SYMBOL_PATTERNS.keys())
