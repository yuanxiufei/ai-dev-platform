"""
DiffEngine — 文件变更差异生成器

核心能力：
1. generate(path, new_content) → 读旧文件 + 对比新内容 → unified diff
2. get_hunks(path, new_content) → 结构化 hunks（前端逐段展示用）
3. detect_language(path) → 根据扩展名推断编程语言
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("diff.engine")

# 二进制文件扩展名（不生成 diff）
_BINARY_EXT = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".mp4", ".avi", ".mov", ".wmv", ".mp3", ".wav",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".exe", ".dll",
    ".so", ".dylib", ".wasm", ".bin", ".dat", ".pyc",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".o", ".obj", ".lib",
})

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".jsx": "jsx", ".mjs": "javascript",
    ".ts": "typescript", ".tsx": "tsx",
    ".vue": "vue", ".svelte": "svelte",
    ".go": "go",
    ".rs": "rust",
    ".java": "java", ".kt": "kotlin",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".c": "c", ".h": "c",
    ".css": "css", ".scss": "scss", ".less": "less",
    ".html": "html", ".htm": "html",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".md": "markdown", ".mdx": "markdown",
    ".sql": "sql",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".xml": "xml", ".svg": "xml",
    ".rb": "ruby", ".php": "php", ".swift": "swift",
    ".dart": "dart", ".lua": "lua", ".r": "r",
    ".tf": "hcl", ".hcl": "hcl",
    ".proto": "protobuf",
    ".graphql": "graphql", ".gql": "graphql",
}


@dataclass
class FileDiff:
    """结构化 diff 结果"""
    file_path: str               # 文件路径
    language: str = ""           # 编程语言
    change_type: str = "MODIFY"  # CREATE | MODIFY | DELETE
    is_new_file: bool = False    # 是否为新创建的文件
    old_content: str = ""        # 旧内容
    new_content: str = ""        # 新内容
    diff_text: str = ""          # unified diff 文本
    hunks: list[dict[str, Any]] = field(default_factory=list)  # 结构化 hunks
    old_line_count: int = 0      # 旧文件行数
    new_line_count: int = 0      # 新文件行数
    lines_added: int = 0         # 新增行数
    lines_removed: int = 0       # 删除行数


class DiffEngine:
    """
    文件变更差异引擎

    Usage:
        engine = DiffEngine(workspace_root=".")
        diff = engine.generate("src/app.py", new_content)
        # diff.diff_text → unified diff 字符串
        # diff.hunks → 结构化 hunks 列表（前端逐段展示）
    """

    # 文件写入工具名称集合
    FILE_WRITE_TOOLS: set[str] = {
        "str_replace", "text_editor", "file_write", "write_file",
        "create_file", "file_operation",
    }
    # 文件删除工具名称集合
    FILE_DELETE_TOOLS: set[str] = {"delete_file", "rename_file"}

    def __init__(self, workspace_root: str | None = None):
        self._workspace = Path(workspace_root).resolve() if workspace_root else None

    # ── 主入口 ──────────────────────────────────────────────

    def generate(
        self,
        path: str,
        new_content: str,
        change_type: str = "MODIFY",
        old_content: str | None = None,
    ) -> FileDiff:
        """
        生成文件变更 unified diff。

        Args:
            path: 文件路径（相对或绝对）
            new_content: 文件新内容
            change_type: "CREATE" | "MODIFY" | "DELETE"
            old_content: 旧内容（None=自动从文件系统读取）

        Returns:
            FileDiff 对象
        """
        file_path = str(Path(path).resolve())

        if _is_binary(file_path):
            return FileDiff(
                file_path=file_path,
                change_type=change_type,
                is_new_file=True,
                new_content="[binary file]",
                diff_text=f"Binary file: {path}",
            )

        # 读取旧内容
        if old_content is None:
            old_content = _read_file(file_path)

        is_new = not bool(old_content) or change_type == "CREATE"

        old_lines = old_content.splitlines(keepends=True) if old_content else []
        new_lines = new_content.splitlines(keepends=True) if new_content else []

        # 生成 unified diff
        if is_new:
            diff_text = _diff_new_file(file_path, new_content)
        else:
            diff_text = "\n".join(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{Path(file_path).name}",
                tofile=f"b/{Path(file_path).name}",
                lineterm="",
            ))

        hunks = _parse_hunks(diff_text)

        # 统计
        lines_added = sum(1 for line in new_lines if not old_content or line not in old_lines)
        lines_removed = sum(1 for line in old_lines if line not in new_lines)

        return FileDiff(
            file_path=file_path,
            language=detect_language(file_path),
            change_type=change_type,
            is_new_file=is_new,
            old_content=old_content if not is_new else "",
            new_content=new_content,
            diff_text=diff_text,
            hunks=hunks,
            old_line_count=len(old_lines),
            new_line_count=len(new_lines),
            lines_added=max(0, lines_added),
            lines_removed=max(0, lines_removed),
        )

    def generate_from_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> dict[str, Any] | None:
        """
        从工具调用信息检测文件变更并生成 diff。

        用于 StreamingAgentRunner 中的流式事件生成。

        Args:
            tool_name: 工具名称（如 "str_replace", "file_operation"）
            arguments: 工具调用参数
            result: 工具执行结果

        Returns:
            {"type": "diff", "data": FileDiff serialized} 或 None
        """
        if tool_name not in self.FILE_WRITE_TOOLS and tool_name not in self.FILE_DELETE_TOOLS:
            return None

        file_path = _extract_file_path(tool_name, arguments)
        if not file_path:
            return None

        change_type = "DELETE" if tool_name in self.FILE_DELETE_TOOLS else (
            "CREATE" if _is_create_tool(tool_name, arguments, result) else "MODIFY"
        )

        # 提取新内容
        new_content = _extract_new_content(tool_name, arguments, file_path)
        if new_content is None and change_type != "DELETE":
            return None

        try:
            diff = self.generate(
                path=file_path,
                new_content=new_content or "",
                change_type=change_type,
            )
            return diff.to_dict()
        except Exception as e:
            logger.warning("Diff generation failed for %s: %s", file_path, e)
            return None


# ── 辅助函数 ──────────────────────────────────────────────────

def _is_binary(path: str) -> bool:
    return Path(path).suffix.lower() in _BINARY_EXT


def _read_file(path: str) -> str:
    p = Path(path)
    if not p.exists() or not p.is_file():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        try:
            return p.read_text(encoding="latin-1", errors="replace")
        except Exception:
            return "[unable to read file]"


def _diff_new_file(path: str, content: str) -> str:
    """为新文件生成 diff（全部行标记为新增）"""
    lines = content.splitlines()
    header = f"--- /dev/null\n+++ b/{Path(path).name}"
    hunks = [f"@@ -0,0 +1,{len(lines)} @@"]
    for line in lines:
        hunks.append(f"+{line}")
    return "\n".join([header] + hunks)


def _parse_hunks(diff_text: str) -> list[dict[str, Any]]:
    """解析 unified diff 为结构化 hunks"""
    hunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in diff_text.splitlines():
        if line.startswith("@@"):
            if current:
                hunks.append(current)
            current = {"header": line, "lines": []}
        elif current is not None:
            current["lines"].append(line)

    if current:
        hunks.append(current)

    return hunks


def detect_language(path: str) -> str:
    """根据文件扩展名推断语言"""
    suffix = Path(path).suffix.lower()
    return _LANGUAGE_MAP.get(suffix, "")


def _extract_file_path(tool_name: str, args: dict[str, Any]) -> str:
    """从工具参数中提取文件路径"""
    if isinstance(args.get("path"), str):
        return args["path"]
    if isinstance(args.get("file_path"), str):
        return args["file_path"]
    if isinstance(args.get("filePath"), str):
        return args["filePath"]
    if isinstance(args.get("target"), str):
        return args["target"]
    return ""


def _is_create_tool(tool_name: str, args: dict[str, Any], result: Any) -> bool:
    """判断是否为创建文件操作"""
    if tool_name in ("create_file",):
        return True
    if tool_name == "file_operation" and args.get("operation") == "create":
        return True
    if tool_name == "str_replace" and args.get("command") == "create":
        return True
    # 如果没有旧文件，也视为创建
    path = _extract_file_path(tool_name, args)
    if path and not Path(path).exists():
        return True
    return False


def _extract_new_content(tool_name: str, args: dict[str, Any], file_path: str) -> str | None:
    """从工具参数中提取新内容"""
    # str_replace: old_str → new_str 替换
    if tool_name == "str_replace":
        if args.get("command") in ("create", None):
            return args.get("file_text") or args.get("content") or args.get("new_str") or ""
        if args.get("command") == "str_replace":
            old_str = args.get("old_str", "")
            new_str = args.get("new_str", "")
            try:
                current = _read_file(file_path)
                return current.replace(old_str, new_str, 1) if old_str else current
            except Exception:
                return new_str
        return args.get("new_str") or args.get("file_text") or ""

    # create_file
    if tool_name == "create_file":
        return args.get("content") or args.get("file_text") or ""

    # file_operation
    if tool_name == "file_operation":
        return args.get("content") or args.get("data") or ""

    # file_write / write_file
    if tool_name in ("file_write", "write_file"):
        return args.get("content") or args.get("data") or ""

    return None


# FileDiff.to_dict() monkey-patch
def _file_diff_to_dict(self: FileDiff) -> dict[str, Any]:
    return {
        "file_path": self.file_path,
        "file_name": Path(self.file_path).name,
        "language": self.language,
        "change_type": self.change_type,
        "is_new_file": self.is_new_file,
        "diff_text": self.diff_text,
        "hunks": self.hunks,
        "old_line_count": self.old_line_count,
        "new_line_count": self.new_line_count,
        "lines_added": self.lines_added,
        "lines_removed": self.lines_removed,
        "content_before": self.old_content[:3000] if len(self.old_content) > 3000 else self.old_content,
        "content_after": self.new_content[:3000] if len(self.new_content) > 3000 else self.new_content,
    }


FileDiff.to_dict = _file_diff_to_dict  # type: ignore[assignment]
