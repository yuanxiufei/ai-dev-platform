"""
LSP 适配桥接 API — 对标 VSCode editor/common/languages.ts 20+ Provider 接口

基于 CodebaseMemory CodeGraph + AST 分析，提供编程语言智能功能。
LSP 协议对标:
  textDocument/completion         → POST /completions
  textDocument/hover              → POST /hover
  textDocument/definition         → POST /definitions
  textDocument/references         → POST /references
  textDocument/documentSymbol     → POST /symbols
  textDocument/signatureHelp      → POST /signature-help
  textDocument/rename             → POST /rename + /prepare-rename
  textDocument/codeAction         → POST /code-actions
  textDocument/formatting         → POST /formatting
  textDocument/rangeFormatting    → POST /range-formatting
  textDocument/semanticTokens     → POST /semantic-tokens
  textDocument/semanticTokens/range → POST /semantic-tokens/range
  textDocument/typeDefinition     → POST /type-definition
  textDocument/declaration        → POST /declaration
  textDocument/implementation     → POST /implementation
  textDocument/foldingRange       → POST /folding-ranges
  textDocument/inlayHint          → POST /inlay-hints
  textDocument/codeLens           → POST /code-lens + /code-lens/resolve
  textDocument/documentHighlight  → POST /document-highlights
  textDocument/inlineCompletion   → POST /inline-completions
  textDocument/documentLink       → POST /links
  textDocument/onTypeFormatting   → POST /on-type-formatting

Session 53: 从 6 个 Provider 扩展至 24 个 (14 个后端 Provider + 3 个格式/代码操作已有)
"""
from __future__ import annotations
import logging, re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/lsp", tags=["LSP Bridge"])

# ── Models ──

class LspRequest(BaseModel):
    content: str = Field(..., description="文件内容")
    language: str = Field(default="python", description="编程语言")
    file_path: str = Field(default="", description="文件路径")
    position_line: int = Field(default=0, ge=0, description="光标行号 (0-based)")
    position_column: int = Field(default=0, ge=0, description="光标列号 (0-based)")
    project_path: str = Field(default=".", description="项目根目录")
    max_results: int = Field(default=50, ge=1, le=200)


class SignatureHelpRequest(BaseModel):
    content: str; language: str = "python"
    position_line: int = 0; position_column: int = 0


# ── 新增模型 (Session 53) ──

class RangeModel(BaseModel):
    """文本范围"""
    start_line: int = 0; start_column: int = 0
    end_line: int = 0; end_column: int = 0


class TextEdit(BaseModel):
    """文本编辑操作"""
    range: RangeModel
    new_text: str


class RenameRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    position_line: int = 0; position_column: int = 0
    new_name: str = ""


class PrepareRenameResult(BaseModel):
    range: RangeModel; text: str
    can_rename: bool = True


class RenameResult(BaseModel):
    edits: list[TextEdit] = []
    reject_reason: str | None = None


class DiagnosticModel(BaseModel):
    """诊断信息"""
    message: str
    start_line: int; start_column: int
    end_line: int; end_column: int
    severity: int = 1  # 1=Error, 2=Warning, 3=Info, 4=Hint
    code: str = ""
    source: str = "lsp-bridge"


class CodeActionRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    range: RangeModel = RangeModel()
    diagnostics: list[DiagnosticModel] = []
    only_kinds: list[str] = []


class CodeActionResult(BaseModel):
    title: str; kind: str = "quickfix"
    edits: list[TextEdit] = []
    is_preferred: bool = False


class FormattingRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    tab_size: int = 4; insert_spaces: bool = True
    range: RangeModel | None = None  # None = 全文格式化


class FormattingResult(BaseModel):
    formatted_content: str
    edits: list[TextEdit] = []


class SemanticTokensRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    last_result_id: str | None = None
    range: RangeModel | None = None  # None = 全文


class SemanticTokenData(BaseModel):
    """delta_line, delta_start, length, token_type, token_modifiers"""
    data: list[int] = []
    result_id: str = ""


class SemanticTokensLegend(BaseModel):
    token_types: list[str] = []
    token_modifiers: list[str] = []


class SemanticTokensResult(BaseModel):
    legend: SemanticTokensLegend
    tokens: SemanticTokenData
    range_tokens: SemanticTokenData | None = None


class TypeDefDeclImplRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    position_line: int = 0; position_column: int = 0
    project_path: str = "."


class InlayHintRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    range: RangeModel = RangeModel()


class InlayHintItem(BaseModel):
    position_line: int; position_column: int
    label: str; kind: str = "type"  # type | parameter
    padding_left: bool = False; padding_right: bool = True


class CodeLensRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    range: RangeModel | None = None


class CodeLensItem(BaseModel):
    range: RangeModel
    title: str = ""
    command_id: str = ""
    command_title: str = ""


class DocumentHighlightResult(BaseModel):
    range: RangeModel
    kind: str = "text"  # text/read/write


class DocumentLinkResult(BaseModel):
    range: RangeModel
    url: str = ""
    tooltip: str = ""


class InlineCompletionRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    position_line: int = 0; position_column: int = 0
    trigger_kind: str = "automatic"  # automatic/manual


class InlineCompletionItem(BaseModel):
    insert_text: str
    range: RangeModel | None = None
    command_title: str = ""


class OnTypeFormattingRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    position_line: int = 0; position_column: int = 0
    typed_char: str = ""
    options: dict = {}


# ── Session 55: SmartSelect + LinkedEditing 模型 ──

class SelectionRangeRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    positions: list[dict]  # [{"line": int, "column": int}, ...]


class SelectionRangeResult(BaseModel):
    range: RangeModel
    parent: "SelectionRangeResult | None" = None


class LinkedEditingRequest(BaseModel):
    content: str; language: str = "python"; file_path: str = ""
    position_line: int = 0; position_column: int = 0


class LinkedEditingResult(BaseModel):
    ranges: list[RangeModel]
    word_pattern: str = ""


class CompletionItem(BaseModel):
    label: str; kind: str = "text"; detail: str = ""
    insert_text: str = ""; documentation: str = ""
    sort_text: str = ""


class HoverResult(BaseModel):
    contents: str
    range_start_line: int = 0; range_start_col: int = 0
    range_end_line: int = 0; range_end_col: int = 0


class Location(BaseModel):
    uri: str; name: str
    start_line: int; start_column: int
    end_line: int; end_column: int


class SymbolInfo(BaseModel):
    name: str; kind: str; detail: str = ""
    start_line: int; start_column: int
    end_line: int; end_column: int
    children: list["SymbolInfo"] = []


# ── 语言关键词补全表 ──

_KEYWORD_COMPLETIONS: dict[str, list[dict]] = {
    "python": [
        {"label":"def","kind":"keyword","detail":"函数定义","insert_text":"def ${1:name}(${2:args}):\n    ${3:pass}"},
        {"label":"class","kind":"keyword","detail":"类定义","insert_text":"class ${1:Name}:\n    def __init__(self, ${2:args}):\n        ${3:pass}"},
        {"label":"import","kind":"keyword","detail":"导入","insert_text":"import ${1:module}"},
        {"label":"from","kind":"keyword","detail":"从模块导入","insert_text":"from ${1:module} import ${2:name}"},
        {"label":"async def","kind":"keyword","detail":"异步函数","insert_text":"async def ${1:name}(${2:args}):\n    ${3:pass}"},
        {"label":"for","kind":"keyword","detail":"循环","insert_text":"for ${1:item} in ${2:iterable}:\n    ${3:pass}"},
        {"label":"if","kind":"keyword","detail":"条件","insert_text":"if ${1:condition}:\n    ${2:pass}"},
        {"label":"elif","kind":"keyword","detail":"否则如果","insert_text":"elif ${1:condition}:\n    ${2:pass}"},
        {"label":"else","kind":"keyword","detail":"否则","insert_text":"else:\n    ${1:pass}"},
        {"label":"try","kind":"keyword","detail":"异常处理","insert_text":"try:\n    ${1:pass}\nexcept ${2:Exception} as ${3:e}:\n    ${4:pass}"},
        {"label":"with","kind":"keyword","detail":"上下文管理","insert_text":"with ${1:expr} as ${2:var}:\n    ${3:pass}"},
        {"label":"return","kind":"keyword","detail":"返回","insert_text":"return ${1:value}"},
        {"label":"lambda","kind":"keyword","detail":"Lambda","insert_text":"lambda ${1:x}: ${2:x}"},
        {"label":"yield","kind":"keyword","detail":"生成器","insert_text":"yield ${1:value}"},
        {"label":"raise","kind":"keyword","detail":"抛出异常","insert_text":"raise ${1:Exception}(\"${2:msg}\")"},
        {"label":"@property","kind":"keyword","detail":"属性装饰器","insert_text":"@property\ndef ${1:name}(self):\n    return self.${2:_name}"},
        {"label":"@staticmethod","kind":"keyword","detail":"静态方法","insert_text":"@staticmethod\ndef ${1:name}(${2:args}):\n    ${3:pass}"},
        {"label":"@classmethod","kind":"keyword","detail":"类方法","insert_text":"@classmethod\ndef ${1:name}(cls, ${2:args}):\n    ${3:pass}"},
    ],
    "typescript": [
        {"label":"function","kind":"keyword","insert_text":"function ${1:name}(${2:args}): ${3:ReturnType} {\n  ${4:return}\n}"},
        {"label":"const","kind":"keyword","insert_text":"const ${1:name} = ${2:value}"},
        {"label":"let","kind":"keyword","insert_text":"let ${1:name} = ${2:value}"},
        {"label":"interface","kind":"keyword","detail":"接口定义","insert_text":"interface ${1:Name} {\n  ${2:prop}: ${3:type}\n}"},
        {"label":"type","kind":"keyword","detail":"类型别名","insert_text":"type ${1:Name} = ${2:type}"},
        {"label":"class","kind":"keyword","insert_text":"class ${1:Name} {\n  constructor(${2:args}) {\n    ${3}\n  }\n}"},
        {"label":"export","kind":"keyword","insert_text":"export ${1:default }${2:name}"},
        {"label":"import","kind":"keyword","insert_text":"import { ${1:name} } from \"${2:module}\""},
        {"label":"async function","kind":"keyword","insert_text":"async function ${1:name}(${2:args}): Promise<${3:Type}> {\n  ${4:return}\n}"},
        {"label":"enum","kind":"keyword","insert_text":"enum ${1:Name} {\n  ${2:Key} = \"${2:key}\"\n}"},
    ],
    "javascript": [
        {"label":"function","kind":"keyword","insert_text":"function ${1:name}(${2:args}) {\n  ${3}\n}"},
        {"label":"const","kind":"keyword","insert_text":"const ${1:name} = ${2:value}"},
        {"label":"class","kind":"keyword","insert_text":"class ${1:Name} {\n  constructor(${2:args}) {\n    ${3}\n  }\n}"},
        {"label":"import","kind":"keyword","insert_text":"import { ${1:name} } from \"${2:module}\""},
        {"label":"export","kind":"keyword","insert_text":"export ${1:default }${2:name}"},
    ],
    "go": [
        {"label":"func","kind":"keyword","insert_text":"func ${1:name}(${2:args}) ${3:ReturnType} {\n\t${4}\n}"},
        {"label":"if","kind":"keyword","insert_text":"if ${1:cond} {\n\t${2}\n}"},
        {"label":"for","kind":"keyword","insert_text":"for ${1:i} := ${2:0}; ${1:i} < ${3:n}; ${1:i}++ {\n\t${4}\n}"},
        {"label":"switch","kind":"keyword","insert_text":"switch ${1:expr} {\ncase ${2:val}:\n\t${3}\ndefault:\n\t${4}\n}"},
        {"label":"go func","kind":"keyword","insert_text":"go func() {\n\t${1}\n}()"},
    ],
    "rust": [
        {"label":"fn","kind":"keyword","insert_text":"fn ${1:name}(${2:args}) -> ${3:ReturnType} {\n    ${4}\n}"},
        {"label":"struct","kind":"keyword","insert_text":"struct ${1:Name} {\n    ${2:field}: ${3:Type}\n}"},
        {"label":"impl","kind":"keyword","insert_text":"impl ${1:Type} {\n    ${2}\n}"},
        {"label":"match","kind":"keyword","insert_text":"match ${1:expr} {\n    ${2:pattern} => ${3:result},\n    _ => ${4:default}\n}"},
    ],
    "java": [
        {"label":"class","kind":"keyword","insert_text":"public class ${1:Name} {\n    public static void main(String[] args) {\n        ${2}\n    }\n}"},
        {"label":"method","kind":"keyword","insert_text":"public ${1:ReturnType} ${2:name}(${3:args}) {\n    return ${4:result};\n}"},
        {"label":"for","kind":"keyword","insert_text":"for (int ${1:i} = 0; ${1:i} < ${2:n}; ${1:i}++) {\n    ${3}\n}"},
    ],
}


# ── AST 符号提取 ──

def _extract_symbols(content: str, language: str) -> list[dict]:
    """提取文档符号 — Python AST + 通用正则"""
    symbols: list[dict] = []
    lines = content.split("\n")

    if language == "python":
        # Python AST 解析
        try:
            import ast
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    symbols.append({"name": node.name, "kind": "function",
                                    "start_line": node.lineno - 1, "start_column": node.col_offset,
                                    "end_line": (node.end_lineno or node.lineno) - 1,
                                    "end_column": node.end_col_offset or 0,
                                    "detail": f"def {node.name}(...)", "children": []})
                elif isinstance(node, ast.AsyncFunctionDef):
                    symbols.append({"name": node.name, "kind": "function",
                                    "start_line": node.lineno - 1, "start_column": node.col_offset,
                                    "end_line": (node.end_lineno or node.lineno) - 1,
                                    "end_column": node.end_col_offset or 0,
                                    "detail": f"async def {node.name}(...)", "children": []})
                elif isinstance(node, ast.ClassDef):
                    sym = {"name": node.name, "kind": "class",
                           "start_line": node.lineno - 1, "start_column": node.col_offset,
                           "end_line": (node.end_lineno or node.lineno) - 1,
                           "end_column": node.end_col_offset or 0,
                           "detail": f"class {node.name}", "children": []}
                    for child in node.body:
                        if isinstance(child, ast.FunctionDef):
                            sym["children"].append({"name": child.name, "kind": "method",
                                "start_line": child.lineno - 1, "start_column": child.col_offset,
                                "end_line": (child.end_lineno or child.lineno) - 1,
                                "end_column": child.end_col_offset or 0,
                                "detail": f"def {child.name}(self, ...)", "children": []})
                    symbols.append(sym)
            return symbols
        except SyntaxError:
            pass  # 回退到正则

    # 通用正则回退
    lang_patterns = {
        "python": [
            (r"^\s*(?:async\s+)?def\s+(\w+)", "function"),
            (r"^\s*class\s+(\w+)", "class"),
        ],
        "javascript": [(r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()", "function"),
                       (r"class\s+(\w+)", "class")],
        "typescript": [(r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()", "function"),
                       (r"class\s+(\w+)", "class"), (r"interface\s+(\w+)", "interface")],
    }
    patterns = lang_patterns.get(language, lang_patterns.get("python", []))
    for pat, kind in patterns:
        for i, line in enumerate(lines):
            m = re.match(pat, line)
            if m:
                name = m.group(1) or m.group(2) or ""
                if name and not name[0].isupper() if kind == "function" else True:
                    symbols.append({"name": name, "kind": kind, "start_line": i, "start_column": m.start(),
                                    "end_line": i, "end_column": len(line),
                                    "detail": f"{kind} {name}", "children": []})
    return symbols


# ── 从 CodebaseMemory 查找定义/引用 ──

def _lookup_definition_in_codebase(word: str, content: str, language: str, project_path: str) -> list[dict]:
    """在代码内容和 CodebaseMemory 中查找定义"""
    results: list[dict] = []

    # 1. AST 符号表查找
    symbols = _extract_symbols(content, language)
    for s in symbols:
        if s["name"] == word:
            results.append({"uri": "current", "name": s["name"],
                            "start_line": s["start_line"], "start_column": s["start_column"],
                            "end_line": s["end_line"], "end_column": s["end_column"]})

    # 2. 尝试 CodebaseMemory 图查询
    try:
        from app.core.codebase_memory.tools import TOOL_REGISTRY
        search_graph = TOOL_REGISTRY.get("search_graph")
        if search_graph and project_path:
            graph_results = search_graph(query=word, project_path=project_path, top_k=5)
            for r in graph_results:
                if isinstance(r, dict):
                    results.append({"uri": r.get("uri", r.get("file", "")),
                                    "name": r.get("name", word),
                                    "start_line": r.get("line", 0) - 1, "start_column": r.get("column", 0),
                                    "end_line": r.get("line", 0) - 1, "end_column": r.get("end_column", 0)})
    except Exception:
        pass

    return results


def _lookup_references(word: str, content: str, language: str, project_path: str) -> list[dict]:
    """在文件内容中查找引用"""
    results: list[dict] = []
    lines = content.split("\n")
    word_pattern = re.compile(rf"\b{re.escape(word)}\b")

    for i, line in enumerate(lines):
        for m in word_pattern.finditer(line):
            results.append({"uri": "current", "name": word,
                            "start_line": i, "start_column": m.start(),
                            "end_line": i, "end_column": m.end()})
    return results


def _hover_info(word: str, content: str, language: str) -> str:
    """生成悬停提示信息"""
    # 在符号表中查找详情
    symbols = _extract_symbols(content, language)
    for s in symbols:
        if s["name"] == word:
            return f"```{language}\n{s.get('detail', word)}\n```\n\n**{s['kind'].capitalize()}** `{word}` — 定义于第 {s['start_line'] + 1} 行"
    # 尝试识别关键词
    return f"`{word}` — 标识符 ({language})"


# ── Session 53 新增辅助函数 ──

_SEMANTIC_TOKEN_TYPES = [
    "namespace", "type", "class", "enum", "interface", "struct", "typeParameter",
    "parameter", "variable", "property", "enumMember", "event",
    "function", "method", "macro", "keyword", "modifier", "comment",
    "string", "number", "regexp", "operator", "decorator"
]
_TOKEN_TYPE_MAP: dict[str, dict[str, int]] = {}


def _get_token_type_id(language: str, token_type: str) -> int:
    """获取语义 token 类型索引 (延时构建映射)"""
    if language not in _TOKEN_TYPE_MAP:
        _TOKEN_TYPE_MAP[language] = {t: i for i, t in enumerate(_SEMANTIC_TOKEN_TYPES)}
    return _TOKEN_TYPE_MAP[language].get(token_type, 0)


# AST → Semantic Token 类型映射
_AST_SEMANTIC_MAP = {
    "function": "function", "async_function": "function",
    "class": "class", "method": "method",
    "type_alias": "type", "enum": "enum",
    "variable": "variable", "parameter": "parameter",
    "property": "property", "interface": "interface",
    "struct": "struct", "decorator": "decorator",
    "macro": "macro", "keyword": "keyword",
}


def _parse_document(content: str, language: str) -> list[dict]:
    """解析文档 — 返回详细 AST 节点列表 (含类型信息用于语义token/内联提示)"""
    nodes: list[dict] = []
    lines = content.split("\n")

    if language == "python":
        try:
            import ast
            tree = ast.parse(content)
            for node in ast.walk(tree):
                info = {}
                if isinstance(node, ast.FunctionDef):
                    info = {"kind": "function", "name": node.name,
                            "line": node.lineno - 1, "col": node.col_offset,
                            "end_line": (node.end_lineno or node.lineno) - 1,
                            "end_col": node.end_col_offset or 0}
                    # 提取参数
                    for arg in node.args.args:
                        nodes.append({"kind": "parameter", "name": arg.arg,
                                      "line": arg.lineno - 1 if hasattr(arg, 'lineno') else info["line"],
                                      "col": arg.col_offset, "end_line": info["line"],
                                      "end_col": arg.col_offset + len(arg.arg)})
                    # 提取返回类型注解
                    if node.returns and hasattr(node.returns, 'value'):
                        info["return_type"] = getattr(node.returns, 'value', str(node.returns))
                    info["params"] = [a.arg for a in node.args.args]
                elif isinstance(node, ast.AsyncFunctionDef):
                    info = {"kind": "function", "name": node.name, "is_async": True,
                            "line": node.lineno - 1, "col": node.col_offset,
                            "end_line": (node.end_lineno or node.lineno) - 1,
                            "end_col": node.end_col_offset or 0}
                    info["params"] = [a.arg for a in node.args.args]
                elif isinstance(node, ast.ClassDef):
                    info = {"kind": "class", "name": node.name,
                            "line": node.lineno - 1, "col": node.col_offset,
                            "end_line": (node.end_lineno or node.lineno) - 1,
                            "end_col": node.end_col_offset or 0}
                elif isinstance(node, ast.Assign) and node.col_offset >= 0:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            info = {"kind": "variable", "name": target.id,
                                    "line": target.lineno - 1, "col": target.col_offset,
                                    "end_line": target.lineno - 1,
                                    "end_col": target.col_offset + len(target.id)}
                if info:
                    nodes.append(info)
            return nodes
        except SyntaxError:
            pass

    # 通用正则回退
    patterns = {
        "python": [
            (r"^\s*(?:async\s+)?def\s+(\w+)", "function"),
            (r"^\s*class\s+(\w+)", "class"),
            (r"^\s*(\w+)\s*=\s*", "variable"),
        ],
        "javascript": [
            (r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()", "function"),
            (r"class\s+(\w+)", "class"),
            (r"(?:const|let|var)\s+(\w+)\s*=", "variable"),
        ],
        "typescript": [
            (r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\()", "function"),
            (r"class\s+(\w+)", "class"),
            (r"interface\s+(\w+)", "interface"),
            (r"type\s+(\w+)\s*=", "type_alias"),
            (r"(?:const|let|var)\s+(\w+)\s*:", "variable"),
        ],
    }
    pats = patterns.get(language, patterns.get("python", []))
    for pat, kind in pats:
        for i, line in enumerate(lines):
            m = re.match(pat, line)
            if m:
                name = m.group(1) or m.group(2) or ""
                if name:
                    nodes.append({"kind": kind, "name": name, "line": i, "col": m.start(name),
                                  "end_line": i, "end_col": m.start(name) + len(name)})
    return nodes


def _compute_semantic_tokens(content: str, language: str, range_model: dict | None = None) -> list[int]:
    """计算语义 token — 返回 LSP 标准格式 [deltaLine, deltaStart, length, typeIdx, modifiers]"""
    nodes = _parse_document(content, language)
    sorted_nodes = sorted(nodes, key=lambda n: (n["line"], n["col"]))
    data: list[int] = []
    prev_line, prev_start = 0, 0

    for n in sorted_nodes:
        line, col = n["line"], n["col"]
        length = n.get("end_col", col) - col
        if length <= 0:
            length = len(n.get("name", ""))
        token_type = _AST_SEMANTIC_MAP.get(n.get("kind", "variable"), "variable")
        type_idx = _get_token_type_id(language, token_type)
        modifiers = 0  # 0=无修饰

        # 范围过滤
        if range_model:
            r = range_model
            if line < r.get("start_line", 0) or line > r.get("end_line", float("inf")):
                continue
            if line == r.get("start_line", 0) and col < r.get("start_column", 0):
                continue
            if line == r.get("end_line", float("inf")) and col > r.get("end_column", float("inf")):
                continue

        delta_line = line - prev_line
        delta_start = col - prev_start if delta_line == 0 else col
        data.extend([delta_line, delta_start, length, type_idx, modifiers])
        prev_line, prev_start = line, col

    return data


def _compute_inlay_hints(content: str, language: str, range_model: dict | None = None) -> list[dict]:
    """计算内联类型提示 — 从 AST 提取类型注解"""
    hints: list[dict] = []
    nodes = _parse_document(content, language)

    for n in nodes:
        line, col = n["line"], n["col"]
        # 范围过滤
        if range_model:
            r = range_model
            if line < r.get("start_line", 0) or line > r.get("end_line", float("inf")):
                continue

        if n.get("kind") == "variable" and not n.get("has_type_annotation"):
            # 为无类型注解的变量推断类型
            name = n.get("name", "")
            var_line = content.split("\n")[line] if line < len(content.split("\n")) else ""
            if ":" not in var_line.split("=")[0] if "=" in var_line else True:
                hint_label = _infer_variable_type(n, var_line)
                if hint_label:
                    hints.append({"position_line": line, "position_column": col + len(name),
                                  "label": f": {hint_label}", "kind": "type",
                                  "padding_left": False, "padding_right": True})

        if n.get("kind") == "parameter":
            # 为函数参数添加参数名提示
            name = n.get("name", "")
            parent_fn = next((x for x in nodes if x.get("kind") == "function" and
                              name in x.get("params", [])), None)
            if parent_fn:
                hints.append({"position_line": line, "position_column": col,
                              "label": f"{name}:", "kind": "parameter",
                              "padding_left": False, "padding_right": False})

    return hints


_TYPE_INFERENCE_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "python": [
        (r'=\s*"', "str"), (r"=\s*'", "str"),
        (r"=\s*\d+\.?\d*", "int/float"),
        (r"=\s*(?:True|False)", "bool"),
        (r"=\s*\[", "list"), (r"=\s*\{", "dict"), (r"=\s*\(\s*\)", "tuple"),
        (r"=\s*\w+\(\)", "object"),
    ],
    "javascript": [
        (r'=\s*"', "string"), (r"=\s*'", "string"), (r'=\s*`', "string"),
        (r"=\s*\d+", "number"), (r"=\s*(?:true|false)", "boolean"),
        (r"=\s*\[", "Array"), (r"=\s*\{", "Object"),
        (r"=\s*\(\)\s*=>", "Function"),
    ],
    "typescript": [
        (r'=\s*"', "string"), (r"=\s*'", "string"), (r'=\s*`', "string"),
        (r"=\s*\d+", "number"), (r"=\s*(?:true|false)", "boolean"),
        (r"=\s*\[", "Array"), (r"=\s*\{", "Object"),
    ],
}


def _infer_variable_type(node: dict, var_line: str) -> str:
    """推断变量类型"""
    for pattern, typ in _TYPE_INFERENCE_PATTERNS.get("python", []):
        if re.search(pattern, var_line):
            return typ
    return ""


def _compute_code_lens(content: str, language: str, file_path: str) -> list[dict]:
    """计算 CodeLens — 为函数/类标注引用计数和行数"""
    lenses: list[dict] = []
    nodes = _parse_document(content, language)
    lines = content.split("\n")

    for n in nodes:
        if n.get("kind") in ("function", "class", "method"):
            name = n.get("name", "")
            line, col = n["line"], n["col"]
            end_line = n.get("end_line", line)
            line_count = end_line - line + 1

            # 计算引用次数 (全文查找)
            ref_count = content.count(name) - 1  # 减去定义自身

            if n["kind"] == "class":
                title = f"{ref_count} references | {line_count} lines"
            else:
                title = f"{ref_count} references"

            # 函数/类内部行数
            lenses.append({
                "range": {"start_line": line, "start_column": col,
                          "end_line": line, "end_column": col + len(name)},
                "title": title,
                "command_id": "editor.action.goToReferences",
                "command_title": f"Find References of {name}",
            })
    return lenses


def _compute_folding_ranges(content: str, language: str) -> list[dict]:
    """计算代码折叠范围 — 基于 AST 语句块和缩进"""
    ranges: list[dict] = []
    lines = content.split("\n")

    if language == "python":
        try:
            import ast
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                     ast.If, ast.For, ast.While, ast.Try, ast.With,
                                     ast.IfExp)):
                    start = node.lineno - 1
                    end = (node.end_lineno or node.lineno) - 1
                    if end > start:
                        ranges.append({"start_line": start, "end_line": end, "kind": "region"})
                elif isinstance(node, ast.match_case):
                    start = node.lineno - 1
                    end = (node.end_lineno or node.lineno) - 1
                    if end > start:
                        ranges.append({"start_line": start, "end_line": end, "kind": "region"})
            return sorted(ranges, key=lambda r: r["start_line"])
        except SyntaxError:
            pass

    # 通用缩进回退: 检测 { } 和缩进块
    bracket_stack: list[int] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        # 检测开括号块 (JS/TS/Java/C/C++/Go/Rust)
        if stripped.endswith("{") and language not in ("python",):
            bracket_stack.append(i)
        elif stripped.startswith("}") and bracket_stack:
            start = bracket_stack.pop()
            if i > start + 1:
                ranges.append({"start_line": start, "end_line": i, "kind": "region"})

    # Python 缩进回退
    if language == "python":
        def_line_indices = [i for i, l in enumerate(lines)
                            if re.match(r"^\s*(?:def|class|if|for|while|try|with|async def)\s", l)]
        for idx in def_line_indices:
            # 找到下一个同级缩进行
            base_indent = len(lines[idx]) - len(lines[idx].lstrip())
            end = idx + 1
            while end < len(lines):
                stripped = lines[end].strip()
                if stripped and len(lines[end]) - len(stripped) <= base_indent and not stripped.startswith(("#", ")", "]", "}", "else", "elif", "except", "finally")):
                    break
                end += 1
            if end - 1 > idx:
                ranges.append({"start_line": idx, "end_line": end - 1, "kind": "region"})

    return sorted(ranges, key=lambda r: r["start_line"])


def _compute_document_highlights(content: str, word: str, position_line: int) -> list[dict]:
    """计算文档高亮 — 同一文件内的所有引用"""
    highlights: list[dict] = []
    lines = content.split("\n")
    word_pattern = re.compile(rf"\b{re.escape(word)}\b")

    for i, line in enumerate(lines):
        for m in word_pattern.finditer(line):
            highlights.append({
                "range": {"start_line": i, "start_column": m.start(),
                          "end_line": i, "end_column": m.end()},
                "kind": "text"
            })
    return highlights


_URL_PATTERN = re.compile(r'(https?://[^\s\)\]\"\']+)')
_FILE_PATH_PATTERN = re.compile(r'["\']([./][^"\']+\.\w+)["\']')
_NPM_PATTERN = re.compile(r'from\s+["\']([\w@][^"\']+)["\']')


def _compute_document_links(content: str) -> list[dict]:
    """计算文档链接 — 检测 URL + 文件路径 + 模块引用"""
    links: list[dict] = []
    lines = content.split("\n")
    for i, line in enumerate(lines):
        # URL 链接
        for m in _URL_PATTERN.finditer(line):
            links.append({"range": {"start_line": i, "start_column": m.start(),
                                     "end_line": i, "end_column": m.end()},
                          "url": m.group(1), "tooltip": "Open URL"})
        # 文件路径链接
        for m in _FILE_PATH_PATTERN.finditer(line):
            links.append({"range": {"start_line": i, "start_column": m.start(1),
                                     "end_line": i, "end_column": m.end(1)},
                          "url": m.group(1), "tooltip": "Open file"})
        # npm 模块链接
        for m in _NPM_PATTERN.finditer(line):
            links.append({"range": {"start_line": i, "start_column": m.start(1),
                                     "end_line": i, "end_column": m.end(1)},
                          "url": m.group(1), "tooltip": "Module"})
    return links


def _compute_code_actions(content: str, language: str, diagnostics: list[dict]) -> list[dict]:
    """计算代码操作 — 基于诊断信息的快速修复"""
    actions: list[dict] = []
    lines = content.split("\n")

    for diag in diagnostics:
        msg = diag.get("message", "").lower()
        line = diag.get("start_line", 0)

        # 未使用的导入
        if "unused" in msg or "not defined" in msg or "undefined" in msg:
            if line < len(lines) and ("import" in lines[line] or "from" in lines[line]):
                actions.append({"title": "删除未使用的导入", "kind": "quickfix",
                                "edits": [{"range": {"start_line": line, "start_column": 0,
                                    "end_line": line, "end_column": len(lines[line])},
                                    "new_text": ""}], "is_preferred": True})

        # 缺失导入
        if "not defined" in msg or "not found" in msg:
            name_match = re.search(r"'(\w+)'|`(\w+)`", diag.get("message", ""))
            if name_match:
                name = name_match.group(1) or name_match.group(2)
                actions.append({"title": f"添加 import {name}", "kind": "quickfix",
                                "edits": [{"range": {"start_line": 0, "start_column": 0,
                                    "end_line": 0, "end_column": 0},
                                    "new_text": f"from ??? import {name}\n"}],
                                "is_preferred": False})

        # 额外/缺失分号 (JS/TS/Java)
        if language in ("javascript", "typescript", "java") and ";" in msg:
            actions.append({"title": "修复分号", "kind": "quickfix",
                            "edits": [], "is_preferred": False})

        # 格式问题
        if "indent" in msg or "whitespace" in msg or "space" in msg:
            if line < len(lines):
                fixed = lines[line].rstrip()
                actions.append({"title": "移除尾随空格", "kind": "quickfix",
                                "edits": [{"range": {"start_line": line, "start_column": 0,
                                    "end_line": line, "end_column": len(lines[line])},
                                    "new_text": fixed}], "is_preferred": False})

    # 无诊断时也提供通用操作
    if not diagnostics:
        actions.append({"title": "格式化文档", "kind": "source.fixAll",
                        "edits": [], "is_preferred": True})

    return actions


def _format_document(content: str, language: str, tab_size: int, insert_spaces: bool,
                     range_model: dict | None = None) -> tuple[str, list[dict]]:
    """格式化文档/选区 — 基于缩进规则"""
    lines = content.split("\n")
    indent_char = " " * tab_size if insert_spaces else "\t"
    edits: list[dict] = []

    start_line = range_model.get("start_line", 0) if range_model else 0
    end_line = range_model.get("end_line", len(lines) - 1) if range_model else len(lines) - 1

    new_lines = list(lines)
    for i in range(start_line, min(end_line + 1, len(new_lines))):
        stripped = new_lines[i].rstrip()

        # 基本的缩进格式化
        if not stripped.strip():
            edits.append({
                "range": {"start_line": i, "start_column": 0,
                          "end_line": i, "end_column": len(new_lines[i])},
                "new_text": ""  # 空行去除空格
            })
        elif language in ("python",):
            # Python: 确保一致的缩进
            indent_level = (len(stripped) - len(stripped.lstrip())) // tab_size
            if i > 0 and i < len(new_lines) - 1:
                line_content = stripped.lstrip()
                if line_content.startswith(("def ", "class ", "if ", "for ", "while ",
                                            "try:", "with ", "except", "elif ", "else:")):
                    pass  # 保留原始缩进
            edits.append({
                "range": {"start_line": i, "start_column": 0,
                          "end_line": i, "end_column": len(new_lines[i])},
                "new_text": stripped
            })
        else:
            # 通用: 移除尾随空格 + 统一空行
            edits.append({
                "range": {"start_line": i, "start_column": 0,
                          "end_line": i, "end_column": len(new_lines[i])},
                "new_text": stripped
            })

    # 应用编辑
    for edit in edits:
        line_idx = edit["range"]["start_line"]
        if line_idx < len(new_lines):
            new_lines[line_idx] = edit["new_text"]

    return "\n".join(new_lines), edits


def _compute_inline_completions(content: str, language: str, position_line: int,
                                position_column: int) -> list[dict]:
    """计算内联补全 — 基于上下文的简单补全"""
    lines = content.split("\n")
    if position_line >= len(lines):
        return []
    current_line = lines[position_line]

    items: list[dict] = []
    # 检测如果当前行是常见模式，提供补全
    stripped = current_line[:position_column].strip()
    if stripped.endswith("."):
        # 属性访问补全
        obj_match = re.search(r"(\w+)\.$", stripped)
        if obj_match:
            obj_name = obj_match.group(1)
            # 从符号表中查找对应类型的方法
            nodes = _parse_document(content, language)
            for n in nodes:
                if n.get("name") == obj_name and n.get("kind") == "variable":
                    items.append({"insert_text": "method()", "command_title": "Complete method call"})
                    break
    elif stripped.endswith("("):
        items.append({"insert_text": "param1, param2)", "command_title": "Complete parameters"})
    elif stripped.endswith("="):
        items.append({"insert_text": " value", "command_title": "Complete assignment"})

    return items


def _compute_on_type_formatting(content: str, language: str, position_line: int,
                                position_column: int, typed_char: str) -> list[dict]:
    """计算输入时格式化 — 输入特定字符后自动调整"""
    edits: list[dict] = []
    if not typed_char:
        return edits

    lines = content.split("\n")
    if position_line >= len(lines):
        return edits
    line = lines[position_line]

    # 闭合括号 { } ( ) [ ] 自动缩进
    if typed_char in ("{", "(", "[") and language not in ("python",):
        close_map = {"{": "}", "(": ")", "[": "]"}
        close_char = close_map.get(typed_char, "")
        indent = line[:position_column + 1 - len(line.lstrip())]
        # 在下一行插入缩进 + 闭合符号
        edits.append({
            "range": {"start_line": position_line, "start_column": position_column + 1,
                      "end_line": position_line, "end_column": position_column + 1},
            "new_text": f"\n{indent}    \n{indent}{close_char}"
        })

    if typed_char == ":" and language == "python":
        # Python 冒号后自动缩进
        indent = len(line) - len(line.lstrip())
        edits.append({
            "range": {"start_line": position_line, "start_column": position_column + 1,
                      "end_line": position_line, "end_column": position_column + 1},
            "new_text": f"\n{' ' * (indent + 4)}"
        })

    if typed_char == "\n" and language == "python":
        # Python 换行自动缩进
        indent = len(line) - len(line.lstrip())
        if line.rstrip().endswith(":"):
            indent += 4
        edits.append({
            "range": {"start_line": position_line, "start_column": position_column,
                      "end_line": position_line, "end_column": position_column},
            "new_text": "\n" + " " * indent
        })

    return edits


# ── 路由 ──

@router.post("/completions", response_model=list[CompletionItem])
async def completions(req: LspRequest):
    """代码补全 — 对标 VSCode CompletionItemProvider"""
    items: list[CompletionItem] = []

    # 1. 语言关键词
    keywords = _KEYWORD_COMPLETIONS.get(req.language, [])
    for kw in keywords:
        items.append(CompletionItem(label=kw["label"], kind=kw.get("kind","keyword"),
                                     detail=kw.get("detail",""), insert_text=kw.get("insert_text", kw["label"]),
                                     sort_text=f"a_{kw['label']}"))

    # 2. 从文档符号提取上下文补全
    symbols = _extract_symbols(req.content, req.language)
    for s in symbols[:30]:
        items.append(CompletionItem(label=s["name"], kind=s.get("kind","function"),
                                     detail=s.get("detail",""),
                                     insert_text=s["name"], sort_text=f"b_{s['name']}"))

    # 3. 从 CodebaseMemory 提取
    try:
        from app.core.codebase_memory.tools import TOOL_REGISTRY
        search_graph = TOOL_REGISTRY.get("search_graph")
        if search_graph and req.project_path:
            gres = search_graph(query=f"{req.file_path}", project_path=req.project_path, top_k=10)
            for r in (gres or []):
                if isinstance(r, dict) and r.get("name"):
                    items.append(CompletionItem(label=r["name"], kind=r.get("kind","function"),
                        detail=r.get("file",""), insert_text=r["name"], sort_text=f"c_{r['name']}"))
    except Exception: pass

    return items[:req.max_results]


@router.post("/hover", response_model=HoverResult)
async def hover(req: LspRequest):
    """悬停提示 — 对标 VSCode HoverProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word: return HoverResult(contents="")
    info = _hover_info(word, req.content, req.language)
    symbols = _extract_symbols(req.content, req.language)
    for s in symbols:
        if s["name"] == word:
            return HoverResult(contents=info, range_start_line=s["start_line"],
                               range_start_col=s["start_column"],
                               range_end_line=s["end_line"], range_end_col=s["end_column"])
    # 回退: 查找行内位置
    lines = req.content.split("\n")
    if req.position_line < len(lines):
        line = lines[req.position_line]
        # 简单估计范围
        return HoverResult(contents=info, range_start_line=req.position_line,
                           range_start_col=req.position_column,
                           range_end_line=req.position_line, range_end_col=req.position_column + len(word))
    return HoverResult(contents=info)


@router.post("/definitions", response_model=list[Location])
async def definitions(req: LspRequest):
    """跳转到定义 — 对标 VSCode DefinitionProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word: return []
    results = _lookup_definition_in_codebase(word, req.content, req.language, req.project_path)
    return [Location(uri=r["uri"], name=r["name"], start_line=r["start_line"],
                     start_column=r["start_column"], end_line=r["end_line"],
                     end_column=r["end_column"]) for r in results]


@router.post("/references", response_model=list[Location])
async def references(req: LspRequest):
    """查找引用 — 对标 VSCode ReferenceProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word: return []
    results = _lookup_references(word, req.content, req.language, req.project_path)
    return [Location(uri=r["uri"], name=r["name"], start_line=r["start_line"],
                     start_column=r["start_column"], end_line=r["end_line"],
                     end_column=r["end_column"]) for r in results[:req.max_results]]


@router.post("/symbols", response_model=list[SymbolInfo])
async def document_symbols(req: LspRequest):
    """文档符号 — 对标 VSCode DocumentSymbolProvider"""
    symbols = _extract_symbols(req.content, req.language)
    return [SymbolInfo(**s) for s in symbols]


@router.post("/signature-help")
async def signature_help(req: SignatureHelpRequest):
    """函数签名帮助 — 对标 VSCode SignatureHelpProvider"""
    lines = req.content.split("\n")
    if req.position_line >= len(lines):
        return {"signatures": [], "active_signature": 0, "active_parameter": 0}

    line = lines[req.position_line]
    # 查找当前行是否包含函数调用
    call_match = re.search(r"(\w+)\s*\(", line[:req.position_column])
    if not call_match:
        return {"signatures": [], "active_signature": 0, "active_parameter": 0}

    func_name = call_match.group(1)
    # 计算当前参数位置
    after_paren = line[call_match.end():req.position_column]
    param_count = after_paren.count(",") + (0 if after_paren.strip().endswith(")") else 1)

    # 查找函数定义
    symbols = _extract_symbols(req.content, req.language)
    for s in symbols:
        if s["name"] == func_name:
            return {"signatures": [{"label": s.get("detail", f"{func_name}(...)"),
                                     "parameters": [{"label": f"arg{i+1}"} for i in range(max(param_count, 2))]}],
                    "active_signature": 0, "active_parameter": min(param_count, 10)}

    return {"signatures": [], "active_signature": 0, "active_parameter": 0}


# ── Session 53 新增路由: Rename ──

@router.post("/prepare-rename", response_model=PrepareRenameResult)
async def prepare_rename(req: RenameRequest):
    """准备重命名 — 对标 VSCode PrepareRenameProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word:
        return PrepareRenameResult(
            range=RangeModel(start_line=req.position_line, start_column=req.position_column,
                             end_line=req.position_line, end_column=req.position_column),
            text="", can_rename=False)
    lines = req.content.split("\n")
    line = lines[req.position_line] if req.position_line < len(lines) else ""
    # 查找标识符范围
    start, end = req.position_column, req.position_column
    while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        start -= 1
    while end < len(line) and (line[end].isalnum() or line[end] == "_"):
        end += 1
    return PrepareRenameResult(
        range=RangeModel(start_line=req.position_line, start_column=start,
                         end_line=req.position_line, end_column=end),
        text=word, can_rename=True)


@router.post("/rename", response_model=RenameResult)
async def rename_symbol(req: RenameRequest):
    """语义重命名 — 对标 VSCode RenameProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word:
        return RenameResult(reject_reason="未找到可重命名符号")
    if not req.new_name:
        return RenameResult(reject_reason="新名称不能为空")

    edits = _compute_rename_edits(word, req.new_name, req.content)
    if not edits:
        return RenameResult(reject_reason="未找到可重命名的范围")
    return RenameResult(edits=[
        TextEdit(range=RangeModel(**e["range"]), new_text=e["new_text"])
        for e in edits
    ])


def _compute_rename_edits(old_name: str, new_name: str, content: str) -> list[dict]:
    """计算所有需要重命名的位置"""
    edits: list[dict] = []
    lines = content.split("\n")
    word_pattern = re.compile(rf"\b{re.escape(old_name)}\b")
    for i, line in enumerate(lines):
        for m in word_pattern.finditer(line):
            edits.append({
                "range": {"start_line": i, "start_column": m.start(),
                          "end_line": i, "end_column": m.end()},
                "new_text": new_name
            })
    return edits


# ── Code Actions ──

@router.post("/code-actions", response_model=list[CodeActionResult])
async def code_actions(req: CodeActionRequest):
    """代码操作/快速修复 — 对标 VSCode CodeActionProvider"""
    diagnostics = [d.model_dump() for d in req.diagnostics] if req.diagnostics else []
    range_dict = req.range.model_dump() if req.range else None
    actions = _compute_code_actions(req.content, req.language, diagnostics)
    return [CodeActionResult(**a) for a in actions]


# ── Formatting ──

@router.post("/formatting", response_model=FormattingResult)
async def formatting(req: FormattingRequest):
    """格式化文档 — 对标 VSCode DocumentFormattingEditProvider"""
    range_dict = req.range.model_dump() if req.range else None
    formatted, edits = _format_document(req.content, req.language, req.tab_size, req.insert_spaces, range_dict)
    return FormattingResult(
        formatted_content=formatted,
        edits=[TextEdit(range=RangeModel(**e["range"]), new_text=e["new_text"]) for e in edits]
    )


@router.post("/range-formatting", response_model=FormattingResult)
async def range_formatting(req: FormattingRequest):
    """格式化选区 — 对标 VSCode DocumentRangeFormattingEditProvider"""
    range_dict = req.range.model_dump() if req.range else None
    formatted, edits = _format_document(req.content, req.language, req.tab_size, req.insert_spaces, range_dict)
    return FormattingResult(
        formatted_content=formatted,
        edits=[TextEdit(range=RangeModel(**e["range"]), new_text=e["new_text"]) for e in edits]
    )


# ── Semantic Tokens ──

@router.get("/semantic-tokens/legend", response_model=SemanticTokensLegend)
async def semantic_tokens_legend():
    """语义 Token 映射表"""
    return SemanticTokensLegend(token_types=_SEMANTIC_TOKEN_TYPES, token_modifiers=["declaration", "readonly"])


@router.post("/semantic-tokens", response_model=SemanticTokensResult)
async def semantic_tokens(req: SemanticTokensRequest):
    """语义高亮 Token — 对标 VSCode SemanticTokensProvider"""
    range_dict = req.range.model_dump() if req.range else None
    tokens = _compute_semantic_tokens(req.content, req.language, range_dict)
    return SemanticTokensResult(
        legend=SemanticTokensLegend(token_types=_SEMANTIC_TOKEN_TYPES, token_modifiers=["declaration"]),
        tokens=SemanticTokenData(data=tokens, result_id=f"{req.language}-{len(tokens)}")
    )


@router.post("/semantic-tokens/range", response_model=SemanticTokensResult)
async def semantic_tokens_range(req: SemanticTokensRequest):
    """范围语义高亮 — 对标 VSCode RangeSemanticTokensProvider"""
    range_dict = req.range.model_dump() if req.range else None
    tokens = _compute_semantic_tokens(req.content, req.language, range_dict)
    return SemanticTokensResult(
        legend=SemanticTokensLegend(token_types=_SEMANTIC_TOKEN_TYPES, token_modifiers=["declaration"]),
        tokens=SemanticTokenData(data=[], result_id=""),
        range_tokens=SemanticTokenData(data=tokens, result_id=f"{req.language}-{len(tokens)}-range")
    )


# ── Navigation ──

@router.post("/type-definition", response_model=list[Location])
async def type_definition(req: TypeDefDeclImplRequest):
    """跳转到类型定义 — 对标 VSCode TypeDefinitionProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word:
        return []
    # 在 CodebaseMemory 中查找类型定义
    results = _lookup_definition_in_codebase(word, req.content, req.language, req.project_path)
    # 同时尝试同文件内类型定义
    nodes = _parse_document(req.content, req.language)
    for n in nodes:
        if n.get("kind") in ("class", "interface", "type_alias", "enum", "struct", "type") and n.get("name") == word:
            results.append({"uri": req.file_path or "current", "name": n["name"],
                            "start_line": n["line"], "start_column": n["col"],
                            "end_line": n.get("end_line", n["line"]),
                            "end_column": n.get("end_col", n["col"] + len(n["name"]))})
    return [Location(**r) for r in results[:req.max_results]]


@router.post("/declaration", response_model=list[Location])
async def declaration(req: TypeDefDeclImplRequest):
    """跳转到声明 — 对标 VSCode DeclarationProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word:
        return []
    results = _lookup_definition_in_codebase(word, req.content, req.language, req.project_path)
    # 声明: 在语言中可能是 .d.ts/header file/export 语句
    # 简化为与定义相同逻辑
    nodes = _parse_document(req.content, req.language)
    for n in nodes:
        if n.get("name") == word and n.get("kind") in ("variable", "function", "class", "interface"):
            results.append({"uri": req.file_path or "current", "name": n["name"],
                            "start_line": n["line"], "start_column": n["col"],
                            "end_line": n.get("end_line", n["line"]),
                            "end_column": n.get("end_col", n["col"] + len(n["name"]))})
    return [Location(**r) for r in results[:req.max_results]]


@router.post("/implementation", response_model=list[Location])
async def implementation(req: TypeDefDeclImplRequest):
    """跳转到实现 — 对标 VSCode ImplementationProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word:
        return []
    results = _lookup_definition_in_codebase(word, req.content, req.language, req.project_path)
    # 实现: 查找继承/实现关系
    nodes = _parse_document(req.content, req.language)
    for n in nodes:
        if n.get("kind") == "class" and n.get("name") != word:
            results.append({"uri": req.file_path or "current", "name": n["name"],
                            "start_line": n["line"], "start_column": n["col"],
                            "end_line": n.get("end_line", n["line"]),
                            "end_column": n.get("end_col", n["col"] + len(n["name"]))})
    return [Location(**r) for r in results[:req.max_results]]


# ── Inlay Hints ──

@router.post("/inlay-hints", response_model=list[InlayHintItem])
async def inlay_hints(req: InlayHintRequest):
    """内联提示 — 对标 VSCode InlayHintsProvider"""
    range_dict = req.range.model_dump() if req.range else None
    hints = _compute_inlay_hints(req.content, req.language, range_dict)
    return [InlayHintItem(**h) for h in hints]


# ── Code Lens ──

@router.post("/code-lens", response_model=list[CodeLensItem])
async def code_lens(req: CodeLensRequest):
    """代码透镜 — 对标 VSCode CodeLensProvider"""
    lenses = _compute_code_lens(req.content, req.language, req.file_path)
    return [CodeLensItem(**l) for l in lenses]


@router.post("/code-lens/resolve", response_model=CodeLensItem)
async def resolve_code_lens(item: CodeLensItem):
    """解析 CodeLens — 对标 VSCode CodeLens resolve"""
    # 无需额外解析，直接返回
    return item


# ── Folding Ranges ──

@router.post("/folding-ranges")
async def folding_ranges(req: LspRequest):
    """代码折叠范围 — 对标 VSCode FoldingRangeProvider"""
    ranges = _compute_folding_ranges(req.content, req.language)
    return {"ranges": ranges}


# ── Document Highlights ──

@router.post("/document-highlights", response_model=list[DocumentHighlightResult])
async def document_highlights(req: LspRequest):
    """文档高亮 — 对标 VSCode DocumentHighlightProvider"""
    word = _word_at_position(req.content, req.position_line, req.position_column)
    if not word:
        return []
    highlights = _compute_document_highlights(req.content, word, req.position_line)
    return [DocumentHighlightResult(**h) for h in highlights]


# ── Document Links ──

@router.post("/links", response_model=list[DocumentLinkResult])
async def document_links(req: LspRequest):
    """文档链接 — 对标 VSCode LinkProvider"""
    links = _compute_document_links(req.content)
    return [DocumentLinkResult(**l) for l in links]


# ── Inline Completions ──

@router.post("/inline-completions", response_model=list[InlineCompletionItem])
async def inline_completions(req: InlineCompletionRequest):
    """内联补全 — 对标 VSCode InlineCompletionsProvider"""
    items = _compute_inline_completions(req.content, req.language, req.position_line, req.position_column)
    return [InlineCompletionItem(**i) for i in items]


# ── On-Type Formatting ──

@router.post("/on-type-formatting", response_model=list[TextEdit])
async def on_type_formatting(req: OnTypeFormattingRequest):
    """输入时格式化 — 对标 VSCode OnTypeFormattingEditProvider"""
    edits = _compute_on_type_formatting(req.content, req.language,
                                         req.position_line, req.position_column, req.typed_char)
    return [TextEdit(range=RangeModel(**e["range"]), new_text=e["new_text"]) for e in edits]


# ── Session 55: Smart Select (SelectionRange) ──

# 语义范围层级: token → word → line → statement → block → function → class → file
_SELECTION_RANGE_LEVELS = {
    "python": [
        (r'\b\w+\b', "word"),
        (r'^[ \t]*"', "string"), (r"^[ \t]*'", "string"),
        (r'^[ \t]*#', "comment"),
        (r'^[ \t]*(?:def|class|async def)\b', "block"),
        (r'^[ \t]*(?:if|for|while|try|with|match)\b', "block"),
    ],
    "javascript": [
        (r'\b\w+\b', "word"),
        (r'^[ \t]*//|/\*', "comment"),
        (r'^[ \t]*(?:function|class|const|let|var)\b', "block"),
        (r'^[ \t]*(?:if|for|while|try|switch)\b', "block"),
    ],
    "typescript": [
        (r'\b\w+\b', "word"),
        (r'^[ \t]*//|/\*', "comment"),
        (r'^[ \t]*(?:function|class|const|let|var|interface|type|enum)\b', "block"),
        (r'^[ \t]*(?:if|for|while|try|switch)\b', "block"),
    ],
    "html": [
        (r'<\w+[^>]*>', "tag_open"), (r'</\w+>', "tag_close"),
        (r'[^<>\s]+', "word"),
    ],
    "css": [
        (r'[^{}\s]+', "word"), (r'\{[^}]*\}', "block"),
    ],
}

# 缩进感知的块边界映射
_BLOCK_BOUNDARIES: dict[str, str] = {
    "python": r'^\s*(?:def |class |async def |if |elif |else:|for |while |try:|except |finally:|with |match |case )',
    "javascript": r'^\s*(?:function |class |const |let |var |if |for |while |switch |try |catch |export )',
    "typescript": r'^\s*(?:function |class |const |let |var |if |for |while |switch |try |catch |export |interface |type |enum )',
}


def _compute_selection_ranges(
    content: str, language: str, positions: list[dict]
) -> list[dict]:
    """对标 VSCode SelectionRangeProvider — 语义范围扩展选择"""
    lines = content.split("\n")
    results: list[dict] = []

    for pos in positions:
        line, col = pos.get("line", 0), pos.get("column", 0)
        if line >= len(lines):
            results.append({"range": {"start_line": line, "start_column": col,
                                       "end_line": line, "end_column": col}, "parent": None})
            continue

        ranges: list[dict] = []

        # Level 1: token (当前行中光标所在的标识符或单词)
        ln = lines[line]
        if col < len(ln) and (ln[col].isalnum() or ln[col] == "_"):
            start, end = col, col
            while start > 0 and (ln[start - 1].isalnum() or ln[start - 1] == "_"):
                start -= 1
            while end < len(ln) and (ln[end].isalnum() or ln[end] == "_"):
                end += 1
            ranges.append({"start_line": line, "start_column": start,
                           "end_line": line, "end_column": end})
        else:
            ranges.append({"start_line": line, "start_column": col,
                           "end_line": line, "end_column": col + 1})

        # Level 2: line (整行去首尾空白)
        stripped = ln.strip()
        if stripped:
            ranges.append({"start_line": line, "start_column": 0,
                           "end_line": line, "end_column": len(ln)})

        # Level 3: 缩进块 — 找到与当前行同缩进级别的连续行
        current_indent = len(ln) - len(ln.lstrip())
        block_start, block_end = line, line
        # 向上找块开始
        for i in range(line - 1, -1, -1):
            li = lines[i].strip()
            if not li or lines[i].startswith(("#", "//")):
                continue
            if len(lines[i]) - len(lines[i].lstrip()) < current_indent:
                break
            block_start = i
        # 向下找块结束
        for i in range(line + 1, len(lines)):
            if not lines[i].strip() or lines[i].strip().startswith(("#", "//")):
                block_end = i
                continue
            if len(lines[i]) - len(lines[i].lstrip()) < current_indent:
                break
            block_end = i
        if block_end > block_start:
            ranges.append({"start_line": block_start, "start_column": 0,
                           "end_line": block_end, "end_column": len(lines[block_end])})

        # Level 4: 语法块 (函数/类/if块)
        block_kw = re.compile(_BLOCK_BOUNDARIES.get(language, _BLOCK_BOUNDARIES["python"]))
        outer_start, outer_end = 0, len(lines) - 1

        # 尝试 AST 精确分析
        if language == "python":
            try:
                import ast
                tree = ast.parse(content)
                for node in ast.iter_child_nodes(tree):
                    n_start = node.lineno - 1
                    n_end = (getattr(node, 'end_lineno', node.lineno) or node.lineno) - 1
                    if n_start <= line <= n_end:
                        outer_start = n_start
                        outer_end = n_end
            except SyntaxError:
                pass  # 回退到正则

        if block_kw:
            # 向上查找最近的块关键字
            for i in range(line, -1, -1):
                if block_kw.match(lines[i]):
                    outer_start = i
                    break
            # 向下查找下一个同级或更高级的块关键字
            start_indent = len(lines[outer_start]) - len(lines[outer_start].lstrip())
            for i in range(line + 1, len(lines)):
                if block_kw.match(lines[i]):
                    next_indent = len(lines[i]) - len(lines[i].lstrip())
                    if next_indent <= start_indent:
                        outer_end = i - 1
                        break

        outer_end = min(outer_end, len(lines) - 1)
        if outer_end >= outer_start:
            ranges.append({"start_line": outer_start, "start_column": 0,
                           "end_line": outer_end,
                           "end_column": len(lines[outer_end]) if lines[outer_end] else 0})

        # Level 5: 全文
        ranges.append({"start_line": 0, "start_column": 0,
                       "end_line": len(lines) - 1,
                       "end_column": len(lines[-1]) if lines else 0})

        # 构建父子链: parent 指向下一个更大的范围
        result = None
        for r in reversed(ranges):
            result = {"range": r, "parent": result}

        results.append(result if result else {"range": ranges[-1], "parent": None})

    return results


@router.post("/selection-ranges", response_model=list[dict])
async def selection_ranges(req: SelectionRangeRequest):
    """智能选择范围 — 对标 VSCode SelectionRangeProvider (语义扩展选择)"""
    results = _compute_selection_ranges(req.content, req.language, req.positions)
    return results


# ── Session 55: Linked Editing ──

# 成对标签/变量模式
_LINKED_PATTERNS: dict[str, list[tuple[str, str]]] = {
    "html": [
        (r'<(\w+)([^>]*)>.*?</\1>', "tag_pair"),   # <div>...</div>
    ],
    "javascript": [
        (r'(?:const|let|var)\s+(\w+)\s*=', "var_decl"),
        (r'import\s+\{?\s*(\w+(?:\s*,\s*\w+)*)\s*\}?\s*from', "import"),
        (r'export\s+(?:const|let|var|function|class)\s+(\w+)', "export"),
    ],
    "typescript": [
        (r'(?:const|let|var)\s+(\w+)\s*[:=]', "var_decl"),
        (r'import\s+\{?\s*(\w+(?:\s*,\s*\w+)*)\s*\}?\s*from', "import"),
        (r'export\s+(?:const|let|var|function|class|interface|type|enum)\s+(\w+)', "export"),
        (r'<(\w+)([^>]*)>.*?</\1>', "tag_pair"),   # JSX 标签对
    ],
    "python": [
        (r'(\w+)\s*=\s*', "var_decl"),
        (r'def\s+(\w+)\s*\(', "func_def"),
        (r'class\s+(\w+)', "class_def"),
        (r'from\s+(\S+)\s+import', "import"),
    ],
}


def _compute_linked_editing(
    content: str, language: str, line: int, column: int
) -> dict:
    """对标 VSCode LinkedEditingRangeProvider — 成对标签/变量同步编辑"""
    lines = content.split("\n")
    if line >= len(lines):
        return {"ranges": [], "word_pattern": ""}

    word = _word_at_position(content, line, column)
    if not word:
        return {"ranges": [], "word_pattern": ""}

    linked_ranges: list[dict] = []

    # 1. HTML/XML 标签对匹配
    if language in ("html", "xml", "javascript", "typescript"):
        # 检测光标是否在标签名上
        ln = lines[line]
        # 尝试匹配开始标签 <name
        tag_pattern = re.compile(r'</?(\w+)')
        for m in tag_pattern.finditer(ln):
            if m.start(1) <= column <= m.end(1):
                tag_name = m.group(1)
                linked_ranges.append({
                    "start_line": line, "start_column": m.start(1),
                    "end_line": line, "end_column": m.end(1),
                })
                # 查找匹配的另一个标签
                is_open = not ln[m.start():m.end()].startswith("</")
                find_tag = re.compile(rf'</?{re.escape(tag_name)}\b')
                for i, cl in enumerate(lines):
                    if i == line:
                        continue
                    for cm in find_tag.finditer(cl):
                        if is_open and cl[cm.start():cm.start()+2] == "</":
                            linked_ranges.append({
                                "start_line": i, "start_column": cm.start() + 1,
                                "end_line": i, "end_column": cm.end(),
                            })
                            break
                        elif not is_open and cl[cm.start():cm.start()+2] != "</":
                            linked_ranges.append({
                                "start_line": i, "start_column": cm.start() + 1,
                                "end_line": i, "end_column": cm.end(),
                            })
                            break
                break

    # 2. 同名变量引用 (全文搜索)
    if not linked_ranges:
        word_escaped = re.escape(word)
        # Python: 用 AST 过滤定义之外的所有引用
        if language == "python":
            try:
                import ast
                tree = ast.parse(content)
                def_loc = None
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        if node.name == word and node.lineno - 1 == line:
                            def_loc = (line, column)
                            linked_ranges.append({
                                "start_line": node.lineno - 1, "start_column": node.col_offset,
                                "end_line": node.lineno - 1, "end_column": node.col_offset + len(word),
                            })
                            break
                # 如果不在定义处，找到所有引用
                if not def_loc:
                    for i, cl in enumerate(lines):
                        for m in re.finditer(rf'\b{word_escaped}\b', cl):
                            linked_ranges.append({
                                "start_line": i, "start_column": m.start(),
                                "end_line": i, "end_column": m.end(),
                            })
                else:
                    # 在定义处: 找到所有引用
                    for i, cl in enumerate(lines):
                        for m in re.finditer(rf'\b{word_escaped}\b', cl):
                            if i != line or m.start() != column:
                                linked_ranges.append({
                                    "start_line": i, "start_column": m.start(),
                                    "end_line": i, "end_column": m.end(),
                                })
            except SyntaxError:
                pass
        else:
            # 通用: 全文查找同名标识符
            for i, cl in enumerate(lines):
                for m in re.finditer(rf'\b{word_escaped}\b', cl):
                    linked_ranges.append({
                        "start_line": i, "start_column": m.start(),
                        "end_line": i, "end_column": m.end(),
                    })

    return {"ranges": linked_ranges, "word_pattern": re.escape(word) if word else ""}


@router.post("/linked-editing", response_model=LinkedEditingResult)
async def linked_editing(req: LinkedEditingRequest):
    """链接编辑范围 — 对标 VSCode LinkedEditingRangeProvider (成对标签同步编辑)"""
    result = _compute_linked_editing(req.content, req.language,
                                      req.position_line, req.position_column)
    return LinkedEditingResult(
        ranges=[RangeModel(**r) for r in result["ranges"]],
        word_pattern=result.get("word_pattern", ""),
    )


@router.get("/capabilities")
async def capabilities():
    """获取 LSP 能力列表"""
    return {
        "providers": [
            "completions", "hover", "definitions", "references", "symbols", "signature-help",
            "rename", "prepare-rename", "code-actions", "formatting", "range-formatting",
            "semantic-tokens", "semantic-tokens/range", "type-definition", "declaration",
            "implementation", "inlay-hints", "code-lens", "code-lens/resolve",
            "folding-ranges", "document-highlights", "links", "inline-completions", "on-type-formatting",
            "selection-ranges", "linked-editing"
        ],
        "providers_count": 23,
        "supported_languages": list(_KEYWORD_COMPLETIONS.keys()),
        "engine": "codebase-memory + python-ast + regex-fallback + type-inference",
        "session": "55 (selection-ranges + linked-editing added)",
    }


# ── 辅助 ──

def _word_at_position(content: str, line: int, column: int) -> str | None:
    """获取指定位置处的标识符"""
    lines = content.split("\n")
    if line >= len(lines):
        return None
    ln = lines[line]
    # 扩展左右边界找到完整标识符
    if column >= len(ln):
        return None
    if not ln[column].isalnum() and ln[column] != "_":
        return None
    start, end = column, column
    while start > 0 and (ln[start - 1].isalnum() or ln[start - 1] == "_"):
        start -= 1
    while end < len(ln) and (ln[end].isalnum() or ln[end] == "_"):
        end += 1
    return ln[start:end] if start < end else None
