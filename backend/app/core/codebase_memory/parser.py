"""
代码解析器 — AST 解析 Python，Regex 解析其他语言

纯 Python 实现，使用内置 ast 模块。
"""

from __future__ import annotations

import ast
import re
import logging
from pathlib import Path
from typing import Callable

from .graph import Node, NodeType, EdgeType, CodeGraph

logger = logging.getLogger("cbm.parser")

# ── 语言检测 ──────────────────────────────────────

EXT_LANG_MAP = {
    ".py": "Python",
    ".pyi": "Python",
    ".vue": "Vue",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".sql": "SQL",
    ".sh": "Bash",
    ".bat": "Bash",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C",
    ".hpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
}

# ── Python AST 解析 ──────────────────────────────

class PythonParser:
    """Python 代码 AST 解析器"""

    def parse(self, file_path: str, source: str, graph: CodeGraph) -> str:
        """解析 Python 文件，返回文件节点 ID"""
        file_node = Node(
            name=Path(file_path).name,
            node_type=NodeType.FILE,
            file_path=file_path,
            language="Python",
        )
        file_id = graph.add_node(file_node)

        try:
            tree = ast.parse(source, filename=file_path)
        except SyntaxError as e:
            logger.debug("Syntax error in %s: %s", file_path, e)
            return file_id

        # 第一遍：收集顶级定义
        collector: dict[str, str] = {}  # name -> node_id
        for item in ast.iter_child_nodes(tree):
            if isinstance(item, ast.FunctionDef):
                fid = self._add_function(graph, item, file_path, file_id, "")
                if fid:
                    collector[item.name] = fid
            elif isinstance(item, ast.AsyncFunctionDef):
                fid = self._add_function(graph, item, file_path, file_id, "", is_async=True)
                if fid:
                    collector[item.name] = fid
            elif isinstance(item, ast.ClassDef):
                cid = self._add_class(graph, item, file_path, file_id, "")
                if cid:
                    collector[item.name] = cid
                    # 类内方法
                    for body_item in item.body:
                        if isinstance(body_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            mid = self._add_function(
                                graph, body_item, file_path, file_id,
                                f"{item.name}.", is_async=isinstance(body_item, ast.AsyncFunctionDef),
                            )
                            if mid:
                                graph.add_edge(mid, cid, EdgeType.DEFINES)
                    # 类继承
                    for base in item.bases:
                        base_name = ast.unparse(base) if hasattr(ast, 'unparse') else self._name_of(base)
                        graph.add_edge(cid, cid, EdgeType.INHERITS)
            elif isinstance(item, ast.Assign):
                # 模块级变量
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        vid = graph.add_node(Node(
                            name=target.id,
                            node_type=NodeType.VARIABLE,
                            file_path=file_path,
                            line_start=item.lineno or 0,
                            qualified_name=target.id,
                            language="Python",
                        ))
                        graph.add_edge(file_id, vid, EdgeType.DEFINES)
                        collector[target.id] = vid
            elif isinstance(item, ast.Import):
                for alias in item.names:
                    import_id = graph.add_node(Node(
                        name=alias.name,
                        node_type=NodeType.IMPORT,
                        file_path=file_path,
                        line_start=item.lineno or 0,
                        qualified_name=alias.name,
                        language="Python",
                    ))
                    graph.add_edge(file_id, import_id, EdgeType.IMPORTS)
            elif isinstance(item, ast.ImportFrom):
                module = item.module or ""
                for alias in item.names:
                    full_name = f"{module}.{alias.name}" if module else alias.name
                    import_id = graph.add_node(Node(
                        name=full_name,
                        node_type=NodeType.IMPORT,
                        file_path=file_path,
                        line_start=item.lineno or 0,
                        qualified_name=full_name,
                        language="Python",
                    ))
                    graph.add_edge(file_id, import_id, EdgeType.IMPORTS)

        # 第二遍：解析调用关系
        self._resolve_calls(graph, tree, collector, file_id)

        return file_id

    def _add_function(self, graph: CodeGraph, func: ast.FunctionDef | ast.AsyncFunctionDef,
                      file_path: str, file_id: str, prefix: str, is_async: bool = False) -> str:
        """添加函数/方法节点"""
        qname = f"{prefix}{func.name}"
        sig = self._build_signature(func)
        node_type = NodeType.METHOD if prefix else NodeType.FUNCTION

        fid = graph.add_node(Node(
            name=func.name,
            node_type=node_type,
            file_path=file_path,
            line_start=func.lineno or 0,
            line_end=func.end_lineno or 0,
            qualified_name=qname,
            signature=sig,
            language="Python",
            extra={"is_async": is_async, "decorators": [
                self._name_of(d) for d in func.decorator_list
            ] if func.decorator_list else []},
        ))
        graph.add_edge(file_id, fid, EdgeType.DEFINES)

        # 装饰器
        for dec in func.decorator_list:
            dec_name = self._name_of(dec)
            dec_id = graph.add_node(Node(
                name=dec_name,
                node_type=NodeType.DECORATOR,
                file_path=file_path,
                line_start=dec.lineno if hasattr(dec, 'lineno') else 0,
                language="Python",
            ))
            graph.add_edge(dec_id, fid, EdgeType.DECORATES)

        return fid

    def _add_class(self, graph: CodeGraph, cls: ast.ClassDef,
                   file_path: str, file_id: str, prefix: str) -> str:
        """添加类节点"""
        qname = f"{prefix}{cls.name}"
        sig = f"class {cls.name}"
        if cls.bases:
            bases = ", ".join(self._name_of(b) for b in cls.bases)
            sig += f"({bases})"

        cid = graph.add_node(Node(
            name=cls.name,
            node_type=NodeType.CLASS,
            file_path=file_path,
            line_start=cls.lineno or 0,
            line_end=cls.end_lineno or 0,
            qualified_name=qname,
            signature=sig,
            language="Python",
        ))
        graph.add_edge(file_id, cid, EdgeType.DEFINES)
        return cid

    def _resolve_calls(self, graph: CodeGraph, tree: ast.Module,
                       collector: dict[str, str], file_id: str) -> None:
        """解析调用关系"""
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._name_of(node.func)
                if func_name and func_name in collector:
                    # 找到最近的函数作用域
                    caller = self._enclosing_function(tree, node)
                    if caller and caller in collector:
                        graph.add_edge(collector[caller], collector[func_name], EdgeType.CALLS)

    def _enclosing_function(self, tree: ast.Module, target: ast.AST) -> str | None:
        """查找 target 所在的最近函数/类"""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if hasattr(node, 'body'):
                    for child in ast.walk(node):
                        if child is target:
                            return node.name
        return None

    def _build_signature(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """构建函数签名"""
        prefix = "async def" if isinstance(func, ast.AsyncFunctionDef) else "def"
        args = []
        for arg in func.args.args:
            arg_str = arg.arg
            if arg.annotation:
                if hasattr(ast, 'unparse'):
                    arg_str += f": {ast.unparse(arg.annotation)}"
            args.append(arg_str)
        sig = f"{prefix} {func.name}({', '.join(args)})"
        if func.returns and hasattr(ast, 'unparse'):
            sig += f" -> {ast.unparse(func.returns)}"
        return sig

    @staticmethod
    def _name_of(node: ast.expr) -> str:
        """提取表达式的名称"""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return PythonParser._name_of(node.value) + "." + node.attr
        if isinstance(node, ast.Call):
            return PythonParser._name_of(node.func)
        if isinstance(node, ast.Subscript):
            return PythonParser._name_of(node.value)
        if hasattr(ast, 'unparse'):
            try:
                return ast.unparse(node)
            except Exception:
                pass
        return str(type(node).__name__)


# ── 通用解析 ──────────────────────────────────────

# 函数定义 regex 模式（多语言）
FUNC_PATTERNS = {
    "Python": [
        (r"^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)\s*(?:->\s*(\S+))?", NodeType.FUNCTION),
    ],
    "TypeScript": [
        (r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", NodeType.FUNCTION),
        (r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*\w+)?\s*=>", NodeType.FUNCTION),
        (r"^\s*(\w+)\s*\(([^)]*)\)\s*:\s*\w+\s*\{", NodeType.METHOD),
    ],
    "JavaScript": [
        (r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", NodeType.FUNCTION),
        (r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*=>", NodeType.FUNCTION),
    ],
    "Vue": [
        (r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)", NodeType.FUNCTION),
        (r"const\s+(\w+)\s*=\s*defineComponent", NodeType.CLASS),
    ],
    "Rust": [
        (r"^\s*(?:pub\s+)?fn\s+(\w+)\s*\(([^)]*)\)", NodeType.FUNCTION),
    ],
    "Go": [
        (r"^\s*func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(([^)]*)\)", NodeType.FUNCTION),
    ],
}

CLASS_PATTERNS = {
    "Python": [(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?", NodeType.CLASS)],
    "TypeScript": [(r"^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)", NodeType.CLASS)],
    "JavaScript": [(r"^(?:export\s+)?class\s+(\w+)", NodeType.CLASS)],
}


class GenericParser:
    """通用正则解析器 — 适用于非 Python 语言"""

    def parse(self, file_path: str, source: str, graph: CodeGraph, language: str) -> str:
        file_node = Node(
            name=Path(file_path).name,
            node_type=NodeType.FILE,
            file_path=file_path,
            language=language,
        )
        file_id = graph.add_node(file_node)

        # 解析函数
        func_patterns = FUNC_PATTERNS.get(language, [])
        for pattern, ntype in func_patterns:
            for match in re.finditer(pattern, source, re.MULTILINE):
                name = match.group(1)
                graph.add_node(Node(
                    name=name,
                    node_type=ntype,
                    file_path=file_path,
                    line_start=source[:match.start()].count('\n') + 1,
                    qualified_name=name,
                    language=language,
                ))

        # 解析类
        class_patterns = CLASS_PATTERNS.get(language, [])
        for pattern, ntype in class_patterns:
            for match in re.finditer(pattern, source, re.MULTILINE):
                name = match.group(1)
                cid = graph.add_node(Node(
                    name=name,
                    node_type=ntype,
                    file_path=file_path,
                    line_start=source[:match.start()].count('\n') + 1,
                    qualified_name=name,
                    language=language,
                ))
                graph.add_edge(file_id, cid, EdgeType.DEFINES)

        # 解析 import 语句
        self._parse_imports(file_path, source, graph, file_id, language)

        return file_id

    def _parse_imports(self, file_path: str, source: str, graph: CodeGraph,
                       file_id: str, language: str) -> None:
        """解析导入语句"""
        if language in ("TypeScript", "JavaScript", "Vue"):
            for match in re.finditer(r"(?:import|require)\s*(?:{[^}]*})?\s*(?:from\s+)?['\"]([^'\"]+)['\"]", source):
                import_name = match.group(1)
                if import_name:
                    graph.add_node(Node(
                        name=import_name, node_type=NodeType.IMPORT,
                        file_path=file_path, qualified_name=import_name, language=language,
                    ))
        elif language == "Python":
            for match in re.finditer(r"^(?:from|import)\s+([\w.]+)", source, re.MULTILINE):
                import_name = match.group(1)
                if import_name:
                    graph.add_node(Node(
                        name=import_name, node_type=NodeType.IMPORT,
                        file_path=file_path, qualified_name=import_name, language=language,
                    ))


# ── Tree-Sitter 增强解析器 ─────────────────────

# tree-sitter 语言名映射（合并自 CKG）
TS_LANG_MAP: dict[str, str] = {
    "Python": "python",
    "TypeScript": "typescript",
    "JavaScript": "javascript",
    "Vue": "typescript",
    "Java": "java",
    "C++": "cpp",
    "C": "cpp",
    "Go": "go",
    "Rust": "rust",
    "Ruby": "ruby",
    "PHP": "php",
    "C#": "c_sharp",
    "Kotlin": "kotlin",
}


class TreeSitterParser:
    """
    Tree-Sitter AST 精确解析器（合并自 CKG）

    三层回退策略：
    1. tree-sitter AST 解析（精确）
    2. 正则表达式回退（tree-sitter 不可用或语言不支持时）
    3. 跳过（语言完全不支持时）

    使用 tree-sitter 时按文件解析为字节级 AST，提取函数/类/方法定义
    并构建 CodeGraph 节点/边。
    """

    def __init__(self) -> None:
        self._has_tree_sitter = self._check_tree_sitter()

    @staticmethod
    def _check_tree_sitter() -> bool:
        try:
            import tree_sitter
            return True
        except ImportError:
            logger.info("tree-sitter not installed, using regex fallback")
            return False

    def parse(self, file_path: str, source: str, graph: CodeGraph,
              language: str) -> str:
        """解析文件，优先使用 tree-sitter，回退到正则"""
        if self._has_tree_sitter and language in TS_LANG_MAP:
            result = self._parse_with_tree_sitter(file_path, source, graph, language)
            if result:
                return result

        return _generic_parser.parse(file_path, source, graph, language)

    def _parse_with_tree_sitter(self, file_path: str, source: str,
                                 graph: CodeGraph, language: str) -> str | None:
        """使用 tree-sitter 解析"""
        try:
            from tree_sitter import Language, Parser

            lang_name = TS_LANG_MAP[language]
            try:
                ts_lang = Language(f"tree_sitter_{lang_name}.so", lang_name)
            except Exception as e:
                logger.debug("tree-sitter language load failed for %s: %s", language, e)
                return None

            parser = Parser()
            parser.set_language(ts_lang)

            tree = parser.parse(bytes(source, "utf-8"))
            root_node = tree.root_node

            file_node = Node(
                name=Path(file_path).name,
                node_type=NodeType.FILE,
                file_path=file_path,
                language=language,
            )
            file_id = graph.add_node(file_node)
            source_bytes = source.encode("utf-8")

            def _walk(node, parent_class: str = ""):
                # 函数/方法定义
                if node.type in ("function_definition", "function_declaration",
                                 "method_definition", "function_item",
                                 "arrow_function"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
                        body = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                        kind = NodeType.METHOD if parent_class else NodeType.FUNCTION
                        sym = Node(
                            name=name,
                            node_type=kind,
                            file_path=file_path,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                            qualified_name=f"{parent_class}.{name}" if parent_class else name,
                            signature=body.split('\n')[0][:200] if body else "",
                            language=language,
                        )
                        sid = graph.add_node(sym)
                        graph.add_edge(file_id, sid, EdgeType.DEFINES)
                        if parent_class:
                            # 查找父类节点并建立关系
                            for n in graph._nodes.values():
                                if (n.file_path == file_path and
                                        n.name == parent_class and
                                        n.node_type == NodeType.CLASS):
                                    graph.add_edge(n.id, sid, EdgeType.DEFINES)
                                    break

                # 类定义
                if node.type in ("class_definition", "class_declaration", "class_item"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
                        body = source_bytes[node.start_byte:node.end_byte].decode("utf-8")
                        sym = Node(
                            name=name,
                            node_type=NodeType.CLASS,
                            file_path=file_path,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                            qualified_name=name,
                            signature=body.split('\n')[0][:200] if body else "",
                            language=language,
                        )
                        cid = graph.add_node(sym)
                        graph.add_edge(file_id, cid, EdgeType.DEFINES)
                        # 递归遍历类成员
                        for child in node.children:
                            _walk(child, parent_class=name)
                        return

                # 接口
                if node.type in ("interface_declaration", "interface_item"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
                        sym = Node(
                            name=name,
                            node_type=NodeType.TYPE,
                            file_path=file_path,
                            line_start=node.start_point[0] + 1,
                            qualified_name=name,
                            language=language,
                        )
                        graph.add_node(sym)
                        graph.add_edge(file_id, graph._nodes[next(reversed(graph._nodes))].id if graph._nodes else file_id, EdgeType.DEFINES)

                # 枚举
                if node.type == "enum_declaration":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = source_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
                        sym = Node(
                            name=name,
                            node_type=NodeType.ENUM,
                            file_path=file_path,
                            line_start=node.start_point[0] + 1,
                            qualified_name=name,
                            language=language,
                        )
                        graph.add_node(sym)

                for child in node.children:
                    _walk(child, parent_class)

            _walk(root_node)
            return file_id

        except Exception as e:
            logger.debug("tree-sitter parse failed for %s: %s", file_path, e)
            return None


# ── 工厂函数 ──────────────────────────────────────

_py_parser = PythonParser()
_generic_parser = GenericParser()
_ts_parser = TreeSitterParser()


def parse_file(file_path: str, graph: CodeGraph) -> str | None:
    """解析单个文件，返回文件节点 ID（读取文件）"""
    path = Path(file_path)
    ext = path.suffix.lower()
    language = EXT_LANG_MAP.get(ext, "Unknown")

    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    return parse_source(file_path, source, graph, ext)


def parse_source(file_path: str, source: str, graph: CodeGraph,
                 ext: str = "") -> str | None:
    """解析源码内容，返回文件节点 ID（使用预读内容）"""
    if not ext:
        ext = Path(file_path).suffix.lower()
    language = EXT_LANG_MAP.get(ext, "Unknown")

    if language == "Python":
        return _py_parser.parse(file_path, source, graph)
    elif language in TS_LANG_MAP:
        # 优先 tree-sitter，回退正则
        return _ts_parser.parse(file_path, source, graph, language)
    elif language in EXT_LANG_MAP.values():
        return _generic_parser.parse(file_path, source, graph, language)
    return None
