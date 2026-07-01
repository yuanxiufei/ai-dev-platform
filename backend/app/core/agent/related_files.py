"""
多文件关系感知上下文 Provider — 借鉴 Zed multi-buffer editing

借鉴 Zed multi-buffer + co-editing 设计：
- 追踪最近打开/查看的文件列表
- 检测文件间的 import 引用关系
- 为 Agent 提供「当前工作集」上下文

使用方式:
    provider = RelatedFilesProvider(workspace_root=".")
    text = await provider.provide(config, user_message, context)
    # → "## Related Files\n- app/core/agent/agent_runner.py (opened 3m ago, imports: config.py, handoff.py)"
"""

from __future__ import annotations

import logging
import os
import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

from app.core.agent.context_provider import ContextProvider

logger = logging.getLogger("agent.related_files")


# ══════════════════════════════════════════════════════════════
# 文件关系追踪器
# ══════════════════════════════════════════════════════════════


class FileRelationshipTracker:
    """文件间关系追踪器

    借鉴 Zed 的 buffer manager — 追踪最近访问文件和文件间 import 关系。
    """

    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self._recent_files: OrderedDict[str, float] = OrderedDict()  # path → last_access
        self._import_graph: dict[str, set[str]] = {}  # file → set of imported files
        self._max_recent: int = 20

    def record_access(self, file_path: str) -> None:
        """记录文件被访问"""
        rel = self._rel_path(file_path)
        if rel:
            # OrderedDict: 移到末尾（最近）
            self._recent_files.pop(rel, None)
            self._recent_files[rel] = time.time()
            # 保持最大数量
            while len(self._recent_files) > self._max_recent:
                self._recent_files.popitem(last=False)

    def record_import(self, from_file: str, import_path: str) -> None:
        """记录文件间 import 关系"""
        rel_from = self._rel_path(from_file)
        if not rel_from:
            return
        if rel_from not in self._import_graph:
            self._import_graph[rel_from] = set()
        self._import_graph[rel_from].add(import_path)

    def get_related_files(
        self,
        current_file: str | None = None,
        max_files: int = 8,
    ) -> list[dict[str, Any]]:
        """获取与当前文件相关的工作集

        Returns:
            文件列表，每项含 path/relation/distance/time_since_access
        """
        rel_current = self._rel_path(current_file) if current_file else None
        results: dict[str, dict[str, Any]] = {}

        # 1. 当前文件的 import 目标（直接依赖）
        if rel_current and rel_current in self._import_graph:
            for imp in self._import_graph[rel_current]:
                resolved = self._resolve_import(imp)
                if resolved:
                    results[resolved] = {
                        "path": resolved,
                        "relation": "imported-by-current",
                        "distance": 1,
                    }

        # 2. 引入当前文件的文件（反向依赖）
        for f, imports in self._import_graph.items():
            if rel_current:
                for imp in imports:
                    resolved = self._resolve_import(imp)
                    if resolved == rel_current:
                        results[f] = {
                            "path": f,
                            "relation": "imports-current",
                            "distance": 1,
                        }

        # 3. 同目录文件（共现上下文）
        if rel_current:
            current_dir = str(Path(rel_current).parent)
            for f in self._recent_files:
                if f == rel_current:
                    continue
                if f.startswith(current_dir) and f not in results:
                    results[f] = {
                        "path": f,
                        "relation": "same-directory",
                        "distance": 2,
                    }

        # 4. 最近访问文件
        for f, last_access in reversed(self._recent_files.items()):
            if f not in results and f != rel_current:
                results[f] = {
                    "path": f,
                    "relation": "recently-opened",
                    "distance": 3,
                }

        # 排序（距离优先 + 最近访问优先），限制数量
        sorted_results = sorted(
            results.values(),
            key=lambda r: (r["distance"], not self._recent_files.get(r["path"], 0)),
        )
        return sorted_results[:max_files]

    def analyze_file(self, file_path: str) -> list[str]:
        """分析文件的 import 语句，返回导入的模块路径列表"""
        full_path = self.workspace_root / file_path
        if not full_path.exists():
            return []

        imports: list[str] = []
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            imports = self._parse_imports(content, file_path)
        except Exception as e:
            logger.debug("Failed to analyze imports in %s: %s", file_path, e)

        return imports

    def build_import_graph(self, file_paths: list[str]) -> None:
        """批量构建 import 关系图"""
        for fp in file_paths:
            imports = self.analyze_file(fp)
            rel = self._rel_path(fp)
            if rel:
                self._import_graph[rel] = set(imports)
                for imp in imports:
                    resolved = self._resolve_import(imp)
                    if resolved and resolved != rel:
                        if resolved not in self._import_graph:
                            self._import_graph[resolved] = set()
        logger.debug(
            "Import graph: %d files, %d edges",
            len(self._import_graph),
            sum(len(v) for v in self._import_graph.values()),
        )

    # ── 内部方法 ──

    def _rel_path(self, path_str: str) -> str | None:
        """转为相对于 workspace 的路径"""
        try:
            p = Path(path_str)
            if not p.is_absolute():
                return str(p).replace("\\", "/")
            return str(p.relative_to(self.workspace_root)).replace("\\", "/")
        except (ValueError, OSError):
            return None

    def _resolve_import(self, import_path: str) -> str | None:
        """将 Python import 路径解析为相对文件路径

        "app.core.agent.runner" → "app/core/agent/runner.py"
        "react" → None (外部包)
        """
        # 跳过外部包
        if import_path in EXTERNAL_PACKAGES:
            return None

        # Python: 点分转换为路径
        candidate = import_path.replace(".", "/")
        # 尝试 .py
        full = self.workspace_root / f"{candidate}.py"
        if full.exists():
            return f"{candidate}.py"
        # 尝试 __init__.py
        full = self.workspace_root / candidate / "__init__.py"
        if full.exists():
            return f"{candidate}/__init__.py"
        return None

    @staticmethod
    def _parse_imports(content: str, file_path: str) -> list[str]:
        """从文件内容中提取 import 语句"""
        imports: list[str] = []
        ext = Path(file_path).suffix.lower()

        if ext == ".py":
            # Python: from X import Y, import X
            for match in re.finditer(
                r'^(?:from\s+(\S+)\s+import|import\s+(\S+))',
                content,
                re.MULTILINE,
            ):
                mod = match.group(1) or match.group(2)
                if mod and not mod.startswith("."):
                    imports.append(mod)
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            # TypeScript/JavaScript: import X from 'Y', require('Y')
            for match in re.finditer(
                r'''(?:from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))''',
                content,
            ):
                mod = match.group(1) or match.group(2)
                if mod and not mod.startswith(".") and not mod.startswith("@"):
                    imports.append(mod)
        elif ext == ".vue":
            # Vue: 提取 <script> 块中的 import
            script_match = re.search(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
            if script_match:
                for match in re.finditer(
                    r'''(?:from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))''',
                    script_match.group(1),
                ):
                    mod = match.group(1) or match.group(2)
                    if mod and not mod.startswith(".") and not mod.startswith("@"):
                        imports.append(mod)
        elif ext == ".go":
            # Go: import "path"
            for match in re.finditer(r'import\s+"([^"]+)"', content):
                imports.append(match.group(1))
        elif ext == ".rs":
            # Rust: use path::to::module
            for match in re.finditer(r'^use\s+([\w:]+)', content, re.MULTILINE):
                imports.append(match.group(1))

        return imports


# 常见外部包（不需要解析为本地文件）
EXTERNAL_PACKAGES: set[str] = {
    # Python
    "os", "sys", "re", "json", "time", "asyncio", "typing", "logging",
    "pathlib", "collections", "dataclasses", "itertools", "functools",
    "abc", "io", "math", "random", "uuid", "hashlib", "subprocess",
    "datetime", "enum", "textwrap", "shutil", "tempfile",
    "numpy", "pandas", "torch", "tensorflow",
    "flask", "fastapi", "django", "sqlalchemy",
    "requests", "httpx", "aiohttp",
    "pydantic", "rich", "click",
    # JavaScript/TypeScript
    "react", "vue", "angular", "next", "nuxt",
    "axios", "lodash", "moment", "express",
    "typescript", "node", "fs", "path", "crypto", "http", "stream",
    # Go
    "fmt", "net", "context", "io", "strings", "errors",
    # Rust
    "std", "serde", "tokio", "actix",
}


# ══════════════════════════════════════════════════════════════
# ContextProvider 实现
# ══════════════════════════════════════════════════════════════


class RelatedFilesProvider(ContextProvider):
    """多文件关系上下文 Provider

    优先级: 35（在 FileContext 之后，Memory 之前）

    为 Agent 提供当前编辑文件的相关文件列表，帮助 Agent 理解代码上下文。
    """

    name: str = "related-files"
    priority: int = 35

    def __init__(self, workspace_root: str | None = None):
        self.tracker = FileRelationshipTracker(
            workspace_root or str(Path.cwd()),
        )

    async def provide(self, config, user_message: str, context=None) -> str | None:
        from app.core.agent.mention_parser import parse_mentions

        # 尝试从用户消息中提取当前关注的文件
        mention_result = parse_mentions(user_message)
        current_file: str | None = None

        if mention_result.mentions:
            # 取第一个 @file: mention
            for m in mention_result.mentions:
                p = Path(m.path)
                if p.exists() and p.is_file():
                    current_file = str(p)
                    break

        if not current_file:
            return None

        # 记录访问 + 分析 imports
        self.tracker.record_access(current_file)
        self.tracker.analyze_file(current_file)

        # 获取相关文件
        related = self.tracker.get_related_files(current_file, max_files=8)
        if not related:
            return None

        parts = ["## Related Files (Multi-Buffer Context)"]

        for rf in related:
            relation_icon = {
                "imported-by-current": "📥",
                "imports-current": "📤",
                "same-directory": "📂",
                "recently-opened": "🕐",
            }.get(rf["relation"], "📄")

            parts.append(
                f"- {relation_icon} `{rf['path']}` ({rf['relation']})"
            )

        parts.append(
            "\nThese files are related to the current context. "
            "Consider their contents when making changes."
        )

        return "\n".join(parts)

    def track_file(self, file_path: str) -> None:
        """供外部调用：追踪文件访问"""
        self.tracker.record_access(file_path)
        self.tracker.analyze_file(file_path)


# ══════════════════════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════════════════════

_related_provider: RelatedFilesProvider | None = None


def get_related_files_provider() -> RelatedFilesProvider:
    """获取全局 RelatedFilesProvider"""
    global _related_provider
    if _related_provider is None:
        _related_provider = RelatedFilesProvider()
    return _related_provider


def init_related_files_provider(workspace_root: str | None = None) -> RelatedFilesProvider:
    """初始化全局 RelatedFilesProvider"""
    global _related_provider
    _related_provider = RelatedFilesProvider(workspace_root=workspace_root)
    return _related_provider
