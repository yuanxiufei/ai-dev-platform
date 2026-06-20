"""
代码感知分块器 — AST 级 + 多语言正则

支持：
- Python AST 函数/类边界分块（保留语法完整性）
- 通用多语言正则分块（function/class/def/fn/func 等）
- 保留代码行号和文件名元数据
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from . import BaseChunker

logger = __import__("logging").getLogger("app.core.rag.chunking.code")

# 多语言函数/类边界正则
CODE_BOUNDARY_PATTERNS = {
    # Python: def xxx(...) 或 class xxx
    "python": re.compile(
        r"(?:^|\n)(?:(?:async\s+)?(?:def|class)\s+\w+)", re.MULTILINE
    ),
    # JavaScript/TypeScript: function, class, export, const xxx = (...) =>
    "javascript": re.compile(
        r"(?:^|\n)(?:(?:export\s+)?(?:async\s+)?(?:function|class|const|let|var)\s+\w+)",
        re.MULTILINE,
    ),
    # Java/C#: public/private/protected class/method
    "java": re.compile(
        r"(?:^|\n)(?:(?:public|private|protected|static)\s+)+(?:class|void|\w+\s+\w+\s*\()",
        re.MULTILINE,
    ),
    # Go: func xxx(...)
    "go": re.compile(r"(?:^|\n)(?:func\s+(?:\(.*?\)\s*)?\w+\s*\()", re.MULTILINE),
    # Rust: fn xxx, impl xxx, struct xxx, enum xxx
    "rust": re.compile(
        r"(?:^|\n)(?:(?:pub\s+)?(?:fn|impl|struct|enum|trait)\s+\w+)", re.MULTILINE,
    ),
    # C/C++: function definitions
    "c": re.compile(
        r"(?:^|\n)(?:\w+\s+\w+\s*\([^)]*\)\s*(?:\{|$))", re.MULTILINE,
    ),
    # 通用: 匹配常见的函数定义模式
    "generic": re.compile(
        r"(?:^|\n)(?:(?:async\s+)?(?:function|def|fn|func)\s+\w+)", re.MULTILINE,
    ),
}


def detect_language(filepath: str) -> str:
    """通过扩展名检测语言"""
    ext = Path(filepath).suffix.lower()
    lang_map = {
        ".py": "python",
        ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript",
        ".ts": "javascript", ".tsx": "javascript", ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".c": "c", ".cpp": "c", ".h": "c", ".hpp": "c", ".cc": "c",
    }
    return lang_map.get(ext, "generic")


class CodeChunker(BaseChunker):
    """代码感知分块器 — 优先使用 AST，回退到正则"""

    def __init__(self, chunk_size: int = 2048, chunk_overlap: int = 300):
        super().__init__(chunk_size, chunk_overlap)

    @property
    def name(self) -> str:
        return "code"

    def chunk(self, text: str, metadata: Optional[dict] = None) -> list[dict]:
        if not text.strip():
            return []

        meta = metadata or {}
        filepath = meta.get("filepath", "")
        language = detect_language(filepath)

        # 尝试 Python AST 分块
        if language == "python" and filepath.endswith(".py"):
            try:
                return self._chunk_python_ast(text, meta)
            except Exception:
                logger.debug("AST chunking failed, fallback to regex")

        # 正则边界分块
        return self._chunk_by_boundary(text, language, meta)

    def _chunk_python_ast(
        self, text: str, metadata: dict
    ) -> list[dict]:
        """Python AST 智能分块（函数/类边界）"""
        import ast

        tree = ast.parse(text)
        chunks: list[dict] = []
        idx = 0

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                try:
                    start_line = node.lineno
                    end_line = node.end_lineno or start_line
                    code_lines = text.splitlines()
                    code = "\n".join(code_lines[start_line - 1:end_line])

                    if len(code) > self.chunk_size:
                        # 大函数/类还需要再分
                        sub = self._split_long_code(code)
                        for s in sub:
                            chunks.append({
                                "text": s,
                                "index": idx,
                                "metadata": {
                                    **metadata,
                                    "chunk_index": idx,
                                    "symbol": node.name,
                                    "type": type(node).__name__,
                                    "lines": f"{start_line}-{end_line}",
                                },
                            })
                            idx += 1
                    else:
                        chunks.append({
                            "text": code,
                            "index": idx,
                            "metadata": {
                                **metadata,
                                "chunk_index": idx,
                                "symbol": node.name,
                                "type": type(node).__name__,
                                "lines": f"{start_line}-{end_line}",
                            },
                        })
                        idx += 1
                except Exception:
                    continue

        return chunks

    def _chunk_by_boundary(
        self, text: str, language: str, metadata: dict
    ) -> list[dict]:
        """正则边界分块（通用回退）"""
        pattern = CODE_BOUNDARY_PATTERNS.get(
            language, CODE_BOUNDARY_PATTERNS["generic"]
        )

        # 找分界点
        boundaries = [m.start() for m in pattern.finditer(text)]
        if not boundaries or boundaries[0] != 0:
            boundaries.insert(0, 0)

        chunks: list[dict] = []
        idx = 0
        buffer = ""
        start_line = 0

        for i, pos in enumerate(boundaries):
            if i == 0:
                buffer = ""
                start_line = text[:pos].count("\n") + 1
                continue

            segment = text[boundaries[i - 1]:pos]
            if len(buffer) + len(segment) <= self.chunk_size:
                buffer += segment
            else:
                if buffer:
                    chunks.append(self._make_code_chunk(
                        buffer, idx, metadata, start_line
                    ))
                    idx += 1
                buffer = segment[-self.chunk_overlap:] if self.chunk_overlap else ""
                start_line = text[:pos].count("\n") - len(buffer.split("\n")) + 1

        # 最后一段
        final = text[boundaries[-1]:]
        if len(buffer) + len(final) <= self.chunk_size:
            buffer += final
        elif final:
            if buffer:
                chunks.append(self._make_code_chunk(buffer, idx, metadata, start_line))
                idx += 1
            buffer = final

        if buffer.strip():
            chunks.append(self._make_code_chunk(buffer, idx, metadata, start_line))

        return chunks

    @staticmethod
    def _make_code_chunk(
        text: str, idx: int, metadata: dict, start_line: int
    ) -> dict:
        end_line = start_line + text.count("\n")
        return {
            "text": text,
            "index": idx,
            "metadata": {
                **metadata,
                "chunk_index": idx,
                "lines": f"{start_line}-{end_line}",
            },
        }

    @staticmethod
    def _split_long_code(code: str) -> list[str]:
        """按逻辑段落分割大代码块"""
        blocks = re.split(r"\n\s*\n", code)
        result: list[str] = []
        buf = ""
        for b in blocks:
            if len(buf) + len(b) <= 2048:
                buf += "\n\n" + b if buf else b
            else:
                if buf:
                    result.append(buf)
                buf = b
        if buf:
            result.append(buf)
        return result or [code]
