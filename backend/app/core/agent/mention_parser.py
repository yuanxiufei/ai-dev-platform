"""
@mention 解析器 — 解析用户消息中的 @file:/@dir:/@symbol: 引用

参考项目：Continue (AtMentionProvider)

功能：
  1. 从用户消息中提取 @file:path、@dir:path、@symbol:name 引用
  2. 读取引用文件内容或目录结构，注入到 Agent 上下文中
  3. 计算引用文件上下文 token 预算，防止溢出
  4. 支持 workspace 相对路径和绝对路径
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("agent.mention_parser")


@dataclass
class ParsedMention:
    """解析后的 @mention 引用"""
    raw: str               # 原始文本，如 "@file:src/main.py"
    type: str              # "file" | "dir" | "symbol"
    path: str              # 解析后的路径/符号名
    content: str = ""      # 读取到的文件内容（或目录摘要）
    exists: bool = True    # 文件是否实际存在
    size_bytes: int = 0    # 文件大小
    language: str = ""     # 编程语言（通过扩展名推断）
    error: str = ""        # 读取错误信息


@dataclass
class MentionResult:
    """@mention 解析整体结果"""
    mentions: list[ParsedMention] = field(default_factory=list)
    context_text: str = ""          # 拼接后的上下文文本
    original_message: str = ""      # 剥离 @mention 后的纯净消息
    total_tokens_estimate: int = 0  # 上下文的 token 估算


# @mention 正则匹配（支持中文路径）
_MENTION_RE = re.compile(
    r"@(file|dir|symbol):([^\s]+?)(?=\s|$|，|。|！|？|；|：|\.|!|\?|;|,|@)",
)

# 扩展名 → 语言映射
EXT_LANG_MAP: dict[str, str] = {
    ".py": "python", ".ts": "typescript", ".tsx": "tsx", ".js": "javascript",
    ".jsx": "jsx", ".vue": "vue", ".go": "go", ".rs": "rust", ".java": "java",
    ".c": "c", ".cpp": "cpp", ".h": "c", ".hpp": "cpp", ".rb": "ruby",
    ".php": "php", ".swift": "swift", ".kt": "kotlin", ".scala": "scala",
    ".sql": "sql", ".sh": "bash", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".xml": "xml", ".html": "html", ".css": "css",
    ".md": "markdown", ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".dockerfile": "dockerfile", ".env": "dotenv", ".gitignore": "gitignore",
}

# 内容读取最大字节数（约 6000 tokens）
MAX_FILE_BYTES = 24_000


def parse_mentions(message: str, workspace_path: Optional[str] = None) -> MentionResult:
    """
    解析用户消息中的 @mention 引用，读取文件内容，构建上下文。

    Args:
        message: 用户原始消息
        workspace_path: 项目根目录（相对路径的基准）

    Returns:
        MentionResult 包含解析后的引用和上下文文本
    """
    result = MentionResult()

    # 1. 提取 @mention 匹配
    matches = list(_MENTION_RE.finditer(message))

    # 2. 收集已处理的路径，防止重复
    seen_paths: set[str] = set()

    # 3. 清理消息（移除 @mention 标签，保留其余文本）
    clean_msg = message
    for m in reversed(matches):
        clean_msg = clean_msg[:m.start()] + clean_msg[m.end():]
    result.original_message = " ".join(clean_msg.split())

    # 4. 解析每个 mention
    base = Path(workspace_path) if workspace_path else Path.cwd()

    for m in matches:
        mention_type = m.group(1)
        raw_path = m.group(2).rstrip(".,;:!?，。；：！？")

        # 解析路径
        resolved = _resolve_path(raw_path, base)

        mention = ParsedMention(
            raw=m.group(0),
            type=mention_type,
            path=resolved if resolved else raw_path,
            language=_infer_language(raw_path),
        )

        # 防止重复
        dedup_key = f"{mention_type}:{resolved or raw_path}"
        if dedup_key in seen_paths:
            continue
        seen_paths.add(dedup_key)

        # 读取内容
        if mention_type == "file":
            _read_file_content(mention, resolved)
        elif mention_type == "dir":
            _read_dir_content(mention, resolved)
        elif mention_type == "symbol":
            # 符号引用暂不解析文件，由代码知识图谱处理
            mention.content = f"[符号引用] {raw_path}"
            mention.exists = True

        result.mentions.append(mention)

    # 5. 构建上下文文本
    result.context_text = _build_context(result.mentions)

    # 6. 估算 token
    result.total_tokens_estimate = len(result.context_text) // 3

    return result


def _resolve_path(raw: str, base: Path) -> Optional[str]:
    """尝试将原始路径解析为实际文件路径"""
    candidates = [
        Path(raw),
        base / raw,
        base / raw.lstrip("/"),
    ]

    for p in candidates:
        try:
            resolved = p.resolve()
            if resolved.exists():
                return str(resolved)
        except (OSError, RuntimeError):
            continue

    # 如果文件不存在，返回基础路径拼接版本
    return str((base / raw).resolve())


def _read_file_content(mention: ParsedMention, path_str: Optional[str]) -> None:
    """读取文件内容到 mention 中"""
    if not path_str:
        mention.error = "路径解析失败"
        mention.exists = False
        return

    try:
        filepath = Path(path_str)
        if not filepath.is_file():
            mention.error = f"文件不存在: {path_str}"
            mention.exists = False
            return

        stat = filepath.stat()
        mention.size_bytes = stat.st_size

        # 超限截断
        content = filepath.read_text(encoding="utf-8", errors="replace")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            mention.content = content[:MAX_FILE_BYTES] + "\n... (文件过长，已截断)"
        else:
            mention.content = content

        mention.exists = True

        # 从扩展名推断语言
        if not mention.language:
            mention.language = _infer_language(filepath.name)

        logger.debug(f"@mention file loaded: {filepath.name} ({len(mention.content)} chars)")

    except PermissionError:
        mention.error = f"权限不足: {path_str}"
        mention.exists = False
        logger.warning(f"@mention permission denied: {path_str}")
    except UnicodeDecodeError:
        mention.error = f"无法解码（可能为二进制文件）: {path_str}"
        mention.exists = False
    except Exception as exc:
        mention.error = f"读取异常: {exc}"
        mention.exists = False
        logger.error(f"@mention read error for {path_str}: {exc}")


def _read_dir_content(mention: ParsedMention, path_str: Optional[str]) -> None:
    """读取目录摘要"""
    if not path_str:
        mention.error = "路径解析失败"
        mention.exists = False
        return

    try:
        dirpath = Path(path_str)
        if not dirpath.is_dir():
            mention.error = f"目录不存在: {path_str}"
            mention.exists = False
            return

        # 列出顶级目录结构
        lines = [f"目录: {dirpath.name}/"]
        entries = sorted(dirpath.iterdir(), key=lambda x: (x.is_file(), x.name))
        for entry in entries[:50]:
            prefix = "  📄" if entry.is_file() else "  📁"
            lines.append(f"{prefix} {entry.name}")

        if len(entries) > 50:
            lines.append(f"  ... 还有 {len(entries) - 50} 个条目")

        mention.content = "\n".join(lines)
        mention.exists = True

    except PermissionError:
        mention.error = f"权限不足: {path_str}"
        mention.exists = False
    except Exception as exc:
        mention.error = f"读取异常: {exc}"
        mention.exists = False


def _infer_language(filename: str) -> str:
    """从文件名推断语言"""
    name = filename.lower()
    for ext, lang in EXT_LANG_MAP.items():
        if name.endswith(ext):
            return lang
    # 特殊文件名
    if name in ("dockerfile",):
        return "dockerfile"
    if name in (".env", ".env.example"):
        return "dotenv"
    return ""


def _build_context(mentions: list[ParsedMention]) -> str:
    """构建上下文文本，准备注入到系统提示中"""
    if not mentions:
        return ""

    parts: list[str] = []

    file_mentions = [m for m in mentions if m.type == "file"]
    dir_mentions = [m for m in mentions if m.type == "dir"]
    symbol_mentions = [m for m in mentions if m.type == "symbol"]

    if file_mentions:
        parts.append("=== 用户引用的文件 ===")
        for m in file_mentions:
            if m.exists and m.content:
                lang_tag = f" ({m.language})" if m.language else ""
                parts.append(f"\n--- {m.path}{lang_tag} ---")
                parts.append(m.content)
            else:
                parts.append(f"\n--- {m.path} ---")
                parts.append(f"⚠️ 无法读取: {m.error or '文件不存在'}")

    if dir_mentions:
        parts.append("\n=== 用户引用的目录 ===")
        for m in dir_mentions:
            if m.content:
                parts.append(f"\n{m.content}")

    if symbol_mentions:
        parts.append("\n=== 用户引用的符号 ===")
        for m in symbol_mentions:
            parts.append(f"  {m.path}")

    return "\n".join(parts)


def inject_context_into_message(
    user_message: str,
    context_text: str,
    max_context_chars: int = 8000,
) -> str:
    """
    将 @mention 上下文注入到用户消息中。

    Args:
        user_message: 剥离 @mention 后的纯净消息
        context_text: 解析出的上下文文本
        max_context_chars: 上下文最大字符数（防止 token 溢出）

    Returns:
        增强后的用户消息
    """
    if not context_text:
        return user_message

    # 截断过长上下文
    if len(context_text) > max_context_chars:
        context_text = context_text[:max_context_chars] + "\n... (上下文已截断)"

    return f"{context_text}\n\n=== 用户请求 ===\n{user_message}"
