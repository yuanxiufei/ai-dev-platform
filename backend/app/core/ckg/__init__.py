"""
CKG — Code Knowledge Graph 代码知识图谱

借鉴 Trae Agent ckg_tool + ckg/ 设计：
- 基于 tree-sitter 的代码结构索引
- SQLite 持久化，按 git hash 缓存失效
- 支持查询：search_function / search_class / search_class_method
- 支持语言：Python, TypeScript/JavaScript, Java, C/C++

轻量级替代 LSP，让 Agent 理解代码结构。
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ckg")

# 语言到 tree-sitter 语言和文件扩展名的映射
_LANGUAGE_CONFIG: dict[str, dict[str, Any]] = {
    "python": {"exts": [".py"], "tree_sitter_lang": "python"},
    "typescript": {"exts": [".ts", ".tsx"], "tree_sitter_lang": "typescript"},
    "javascript": {"exts": [".js", ".jsx", ".mjs"], "tree_sitter_lang": "javascript"},
    "java": {"exts": [".java"], "tree_sitter_lang": "java"},
    "cpp": {"exts": [".cpp", ".cc", ".cxx", ".hpp", ".h", ".c"], "tree_sitter_lang": "cpp"},
    "go": {"exts": [".go"], "tree_sitter_lang": "go"},
    "rust": {"exts": [".rs"], "tree_sitter_lang": "rust"},
}

# 正则回退方案（tree-sitter 不可用时使用）
_FUNCTION_PATTERNS: dict[str, re.Pattern] = {
    "python": re.compile(r"^\s*def\s+(\w+)\s*\([^)]*\)\s*(?:->\s*\S+)?\s*:", re.MULTILINE),
    "typescript": re.compile(r"(?:function\s+(\w+)\s*\([^)]*\)|(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)", re.MULTILINE),
    "javascript": re.compile(r"(?:function\s+(\w+)\s*\([^)]*\)|(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>)", re.MULTILINE),
    "java": re.compile(r"(?:public|private|protected)?\s*(?:static\s+)?\w+(?:<\w+>)?\s+(\w+)\s*\([^)]*\)\s*(?:throws[^{]*)?\{", re.MULTILINE),
    "cpp": re.compile(r"(?:\w+(?:::\w+)*\s+(\w+)\s*\([^)]*\)\s*(?:const\s*)?\{)", re.MULTILINE),
}

_CLASS_PATTERNS: dict[str, re.Pattern] = {
    "python": re.compile(r"^\s*class\s+(\w+)\s*(?:\([^)]*\))?\s*:", re.MULTILINE),
    "typescript": re.compile(r"(?:class\s+(\w+)|interface\s+(\w+))", re.MULTILINE),
    "javascript": re.compile(r"class\s+(\w+)", re.MULTILINE),
    "java": re.compile(r"(?:public\s+)?class\s+(\w+)", re.MULTILINE),
    "cpp": re.compile(r"class\s+(\w+)", re.MULTILINE),
}


@dataclass
class CodeSymbol:
    """代码符号"""
    name: str
    kind: str  # function | class | method
    file_path: str
    line_number: int
    body: str = ""
    """完整函数/类体（截断至 2000 字符）"""
    parent_class: str = ""
    """所属类名（仅 method）"""
    language: str = ""


@dataclass
class CKGQueryResult:
    """查询结果"""
    symbols: list[CodeSymbol]
    total_found: int
    time_ms: float = 0.0


class CodeKnowledgeGraph:
    """代码知识图谱

    三层回退索引策略：
    1. tree-sitter AST 精确解析（推荐）
    2. 正则表达式回退（tree-sitter 不可用时）
    3. 纯文本搜索（正则也失败时）
    """

    def __init__(self, db_path: str = "data/ckg.db") -> None:
        self.db_path = db_path
        self._db: sqlite3.Connection | None = None
        self._has_tree_sitter = self._check_tree_sitter()

    # ── 初始化 ──────────────────────────────────────

    def _check_tree_sitter(self) -> bool:
        """检查 tree-sitter 是否可用"""
        try:
            import tree_sitter  # noqa: F401
            return True
        except ImportError:
            logger.info("tree-sitter not installed, using regex fallback for CKG")
            return False

    def _ensure_db(self) -> sqlite3.Connection:
        if self._db is None:
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            self._db = sqlite3.connect(self.db_path)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
        return self._db

    def _init_schema(self) -> None:
        if self._db is None:
            return
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS ckg_symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                kind TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line_number INTEGER NOT NULL,
                body TEXT DEFAULT '',
                parent_class TEXT DEFAULT '',
                language TEXT DEFAULT '',
                project_path TEXT DEFAULT '',
                git_hash TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_ckg_name ON ckg_symbols(name, kind);
            CREATE INDEX IF NOT EXISTS idx_ckg_file ON ckg_symbols(file_path);
            CREATE INDEX IF NOT EXISTS idx_ckg_parent ON ckg_symbols(parent_class);
        """)
        self._db.commit()

    # ── 索引 ──────────────────────────────────────────

    def index_project(self, project_path: str, language_filter: str | None = None) -> int:
        """索引整个项目，返回索引的符号数"""
        import time
        start = time.perf_counter()

        db = self._ensure_db()
        total_symbols = 0

        # 计算 git hash 用于缓存失效
        git_hash = self._get_git_hash(project_path)

        # 清除旧索引
        db.execute("DELETE FROM ckg_symbols WHERE project_path = ?", (project_path,))

        for root, dirs, files in os.walk(project_path):
            # 跳过常见的非代码目录
            dirs[:] = [
                d for d in dirs
                if not d.startswith(".") and d not in (
                    "node_modules", "__pycache__", ".git", "dist", "build",
                    ".venv", "venv", ".next", "target",
                )
            ]

            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                lang = self._detect_language(ext)

                if lang is None:
                    continue
                if language_filter and lang != language_filter:
                    continue

                filepath = os.path.join(root, fname)
                rel_path = os.path.relpath(filepath, project_path)

                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                except Exception:
                    continue

                symbols = self._extract_symbols(content, lang, rel_path)
                for sym in symbols:
                    db.execute(
                        """INSERT INTO ckg_symbols
                           (name, kind, file_path, line_number, body, parent_class, language, project_path, git_hash)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (sym.name, sym.kind, sym.file_path, sym.line_number,
                         sym.body[:2000], sym.parent_class, lang, project_path, git_hash),
                    )
                    total_symbols += 1

        db.commit()
        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            "CKG indexed %s: %d symbols in %.0fms (langs=%s)",
            project_path, total_symbols, elapsed,
            language_filter or "all",
        )
        return total_symbols

    def _detect_language(self, ext: str) -> str | None:
        for lang, cfg in _LANGUAGE_CONFIG.items():
            if ext in cfg["exts"]:
                return lang
        return None

    def _extract_symbols(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> list[CodeSymbol]:
        """从文件内容中提取所有代码符号"""
        if self._has_tree_sitter:
            return self._extract_with_tree_sitter(content, language, file_path)

        # 正则回退
        return self._extract_with_regex(content, language, file_path)

    def _extract_with_tree_sitter(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> list[CodeSymbol]:
        """使用 tree-sitter 精确解析"""
        try:
            import tree_sitter
            from tree_sitter import Language, Parser

            lang_name = _LANGUAGE_CONFIG.get(language, {}).get("tree_sitter_lang")
            if not lang_name:
                return self._extract_with_regex(content, language, file_path)

            # 尝试加载语言 grammar
            try:
                tree_lang = Language(f"tree_sitter_{lang_name}.so", lang_name)
            except Exception:
                return self._extract_with_regex(content, language, file_path)

            parser = Parser()
            parser.set_language(tree_lang)

            tree = parser.parse(bytes(content, "utf-8"))
            root_node = tree.root_node

            symbols: list[CodeSymbol] = []
            content_bytes = content.encode("utf-8")

            def _walk(node, parent_class: str = ""):
                if node.type in ("function_definition", "function_declaration",
                                 "method_definition", "function_item"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = content_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
                        body = content_bytes[node.start_byte:node.end_byte].decode("utf-8")
                        line = node.start_point[0] + 1
                        kind = "method" if parent_class else "function"
                        symbols.append(CodeSymbol(
                            name=name, kind=kind, file_path=file_path,
                            line_number=line, body=body[:2000],
                            parent_class=parent_class, language=language,
                        ))

                if node.type in ("class_definition", "class_declaration", "class_item"):
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        name = content_bytes[name_node.start_byte:name_node.end_byte].decode("utf-8")
                        body = content_bytes[node.start_byte:node.end_byte].decode("utf-8")
                        line = node.start_point[0] + 1
                        symbols.append(CodeSymbol(
                            name=name, kind="class", file_path=file_path,
                            line_number=line, body=body[:2000],
                            parent_class="", language=language,
                        ))
                        # 递归遍历类成员
                        for child in node.children:
                            _walk(child, parent_class=name)
                        return

                for child in node.children:
                    _walk(child, parent_class)

            _walk(root_node)
            return symbols

        except Exception as e:
            logger.debug("tree-sitter extraction failed for %s: %s", file_path, e)
            return self._extract_with_regex(content, language, file_path)

    def _extract_with_regex(
        self,
        content: str,
        language: str,
        file_path: str,
    ) -> list[CodeSymbol]:
        """正则表达式回退提取"""
        symbols: list[CodeSymbol] = []
        lines = content.split("\n")

        # 提取函数
        func_pattern = _FUNCTION_PATTERNS.get(language)
        if func_pattern:
            for match in func_pattern.finditer(content):
                name = match.group(1) or match.group(2)
                if name:
                    line_no = content[:match.start()].count("\n") + 1
                    # 提取函数体（到下一个同级声明或文件尾）
                    start = match.start()
                    end = min(start + 2000, len(content))
                    body = content[start:end]
                    symbols.append(CodeSymbol(
                        name=name, kind="function", file_path=file_path,
                        line_number=line_no, body=body,
                        parent_class="", language=language,
                    ))

        # 提取类
        class_pattern = _CLASS_PATTERNS.get(language)
        if class_pattern:
            for match in class_pattern.finditer(content):
                name = match.group(1) or match.group(2)
                if name:
                    line_no = content[:match.start()].count("\n") + 1
                    start = match.start()
                    end = min(start + 2000, len(content))
                    body = content[start:end]
                    symbols.append(CodeSymbol(
                        name=name, kind="class", file_path=file_path,
                        line_number=line_no, body=body,
                        parent_class="", language=language,
                    ))

        return symbols

    def _get_git_hash(self, project_path: str) -> str:
        """获取 git HEAD hash"""
        head_path = os.path.join(project_path, ".git", "HEAD")
        if os.path.exists(head_path):
            try:
                # 尝试读取 packed-refs 或 HEAD
                head_dir = os.path.join(project_path, ".git")
                ref_path = os.path.join(head_dir, "refs", "heads", "main")
                if not os.path.exists(ref_path):
                    ref_path = os.path.join(head_dir, "refs", "heads", "master")
                if os.path.exists(ref_path):
                    with open(ref_path, "r") as f:
                        return f.read().strip()[:8]
            except Exception:
                pass
        # 回退：基于目录文件最近修改时间的 hash
        mtimes = []
        for root, _dirs, files in os.walk(project_path):
            for f in files:
                try:
                    mtimes.append(str(os.path.getmtime(os.path.join(root, f))))
                except Exception:
                    pass
        return hashlib.md5("".join(sorted(mtimes)).encode()).hexdigest()[:8]

    # ── 查询 ──────────────────────────────────────────

    def search_function(self, name: str, project_path: str | None = None) -> CKGQueryResult:
        """搜索函数定义"""
        return self._search(name, kind="function", project_path=project_path)

    def search_class(self, name: str, project_path: str | None = None) -> CKGQueryResult:
        """搜索类定义"""
        return self._search(name, kind="class", project_path=project_path)

    def search_method(self, class_name: str, method_name: str, project_path: str | None = None) -> CKGQueryResult:
        """搜索类方法"""
        import time
        start = time.perf_counter()
        db = self._ensure_db()

        query = "SELECT name, kind, file_path, line_number, body, parent_class, language FROM ckg_symbols WHERE kind='method' AND parent_class=? AND name LIKE ?"
        params: list[Any] = [class_name, f"%{method_name}%"]

        if project_path:
            query += " AND project_path = ?"
            params.append(project_path)

        rows = db.execute(query + " LIMIT 50", params).fetchall()

        symbols = [self._row_to_symbol(r) for r in rows]
        elapsed = (time.perf_counter() - start) * 1000
        return CKGQueryResult(symbols=symbols, total_found=len(symbols), time_ms=elapsed)

    def search(
        self,
        query: str,
        kind: str | None = None,
        file_pattern: str | None = None,
        project_path: str | None = None,
        limit: int = 50,
    ) -> CKGQueryResult:
        """通用搜索"""
        return self._search(
            name=query, kind=kind, file_pattern=file_pattern,
            project_path=project_path, limit=limit,
        )

    def _search(
        self,
        name: str,
        kind: str | None = None,
        file_pattern: str | None = None,
        project_path: str | None = None,
        limit: int = 50,
    ) -> CKGQueryResult:
        import time
        start = time.perf_counter()
        db = self._ensure_db()

        conditions = ["name LIKE ?"]
        params: list[Any] = [f"%{name}%"]

        if kind:
            conditions.append("kind = ?")
            params.append(kind)
        if project_path:
            conditions.append("project_path = ?")
            params.append(project_path)

        query = f"SELECT name, kind, file_path, line_number, body, parent_class, language FROM ckg_symbols WHERE {' AND '.join(conditions)} LIMIT ?"
        params.append(limit)

        rows = db.execute(query, params).fetchall()

        symbols = [self._row_to_symbol(r) for r in rows]

        # 文件模式过滤（内存中）
        if file_pattern:
            symbols = [s for s in symbols if fnmatch.fnmatch(s.file_path, file_pattern)]

        elapsed = (time.perf_counter() - start) * 1000
        return CKGQueryResult(symbols=symbols, total_found=len(symbols), time_ms=elapsed)

    def _row_to_symbol(self, row: tuple) -> CodeSymbol:
        return CodeSymbol(
            name=row[0], kind=row[1], file_path=row[2],
            line_number=row[3], body=row[4] or "",
            parent_class=row[5] or "", language=row[6] or "",
        )

    # ── 管理 ──────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """获取索引统计"""
        db = self._ensure_db()
        total = db.execute("SELECT COUNT(*) FROM ckg_symbols").fetchone()[0]
        by_kind = {
            row[0]: row[1]
            for row in db.execute(
                "SELECT kind, COUNT(*) FROM ckg_symbols GROUP BY kind"
            ).fetchall()
        }
        by_lang = {
            row[0]: row[1]
            for row in db.execute(
                "SELECT language, COUNT(*) FROM ckg_symbols GROUP BY language"
            ).fetchall()
        }
        projects = [
            row[0] for row in db.execute(
                "SELECT DISTINCT project_path FROM ckg_symbols"
            ).fetchall()
        ]
        return {
            "total_symbols": total,
            "by_kind": by_kind,
            "by_language": by_lang,
            "projects": projects,
            "db_path": self.db_path,
            "tree_sitter_available": self._has_tree_sitter,
        }

    def clear_project(self, project_path: str) -> int:
        """清除指定项目的索引"""
        db = self._ensure_db()
        cursor = db.execute("DELETE FROM ckg_symbols WHERE project_path = ?", (project_path,))
        db.commit()
        return cursor.rowcount

    def clear_all(self) -> int:
        """清除所有索引"""
        db = self._ensure_db()
        cursor = db.execute("DELETE FROM ckg_symbols")
        db.commit()
        return cursor.rowcount

    def close(self) -> None:
        if self._db:
            self._db.close()
            self._db = None


# ── 全局单例 ──────────────────────────────────────

_global_ckg: CodeKnowledgeGraph | None = None


def get_ckg(db_path: str = "data/ckg.db") -> CodeKnowledgeGraph:
    """获取全局 CKG 实例"""
    global _global_ckg
    if _global_ckg is None:
        _global_ckg = CodeKnowledgeGraph(db_path=db_path)
    return _global_ckg


def init_ckg(db_path: str = "data/ckg.db") -> CodeKnowledgeGraph:
    """初始化全局 CKG 实例"""
    global _global_ckg
    _global_ckg = CodeKnowledgeGraph(db_path=db_path)
    logger.info("CKG initialized: db=%s tree_sitter=%s", db_path, _global_ckg._has_tree_sitter)
    return _global_ckg
