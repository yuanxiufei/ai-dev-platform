"""
IDE 集成工具 — codebase_search / file_operation / terminal_exec

提供三个核心 IDE 级 Agent 工具：
- codebase_search: 代码库全文搜索 (ripgrep/grep，文件类型过滤，上下文行)
- file_operation: 文件系统 CRUD (创建/更新/删除/列表/移动，含安全防护)
- terminal_exec: 安全终端执行 (命令白名单 + 超时保护 + 输出截断)

遵循项目 @register_tool 装饰器注册模式，category="ide"。
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.tools.registry import register_tool
from app.core.tools.schema import ToolParam, ParamType


# ══════════════════════════════════════════════════════════════
# 安全配置
# ══════════════════════════════════════════════════════════════

# 允许的工作目录白名单（codebase_search / file_operation / terminal_exec 只能在此范围内操作）
_WORKSPACE_ROOT = Path(os.getenv("AGENT_WORKSPACE_ROOT", os.getcwd())).resolve()

# terminal_exec 允许的命令白名单
_TERMINAL_WHITELIST: set[str] = {
    # 文件系统
    "ls", "dir", "pwd", "tree", "find",
    "cat", "head", "tail", "wc", "du", "file", "stat",
    "mkdir", "touch", "cp", "mv", "rm",
    "chmod", "chown",
    # 版本控制 (只读)
    "git",
    # 开发工具
    "python", "python3", "pip", "node", "npm", "npx", "pnpm", "yarn",
    "go", "cargo", "rustc", "javac", "java",
    "make", "cmake", "ninja",
    # 文本处理
    "grep", "rg", "sed", "awk", "sort", "uniq",
    "echo", "printf",
    # 网络
    "curl", "wget",
    # 包管理 (不过滤参数)
    "poetry", "uv", "cargo",
}

# terminal_exec 禁止的命令（即使匹配白名单前缀也拒绝）
_TERMINAL_BLACKLIST: set[str] = {
    "rm -rf /", "rm -rf --no-preserve-root", "mkfs",
    "shutdown", "reboot", "halt", "poweroff",
    "dd", "fdisk", "mount", "umount",
    "chmod 777 /", "chown -R /",
    "> /dev/sda", ":(){ :|:& };:",  # fork bomb
}

# 终端输出最大行数
_MAX_OUTPUT_LINES = 500

# 文件操作最大大小 (10MB)
_MAX_FILE_SIZE = 10 * 1024 * 1024


# ══════════════════════════════════════════════════════════════
# 安全工具函数
# ══════════════════════════════════════════════════════════════

def _resolve_safe(target: str) -> Path:
    """解析路径并验证在工作区范围内"""
    p = Path(target)
    if not p.is_absolute():
        p = (_WORKSPACE_ROOT / p).resolve()
    else:
        p = p.resolve()

    # 防止路径穿越
    try:
        p.relative_to(_WORKSPACE_ROOT)
    except ValueError:
        raise PermissionError(
            f"Access denied: '{target}' is outside workspace "
            f"'{_WORKSPACE_ROOT}'. Only paths within the workspace are allowed."
        )
    return p


def _safe_cmd(command: str) -> list[str]:
    """解析命令并做白名单/黑名单检查"""
    try:
        args = shlex.split(command)
    except ValueError as e:
        raise ValueError(f"Invalid command syntax: {e}")

    if not args:
        raise ValueError("Empty command")

    cmd_name = os.path.basename(args[0])
    if cmd_name not in _TERMINAL_WHITELIST:
        raise PermissionError(
            f"Command '{cmd_name}' is not allowed. Whitelist: "
            f"{', '.join(sorted(_TERMINAL_WHITELIST))}"
        )

    # 黑名单检查（检查完整命令字符串）
    cmd_str = command.strip()
    for blocked in _TERMINAL_BLACKLIST:
        if blocked in cmd_str:
            raise PermissionError(f"Dangerous pattern detected: '{blocked}'")

    return args


# ══════════════════════════════════════════════════════════════
# Tool 1: codebase_search — 代码库搜索
# ══════════════════════════════════════════════════════════════

@register_tool(
    "codebase_search",
    "Search the entire codebase for text patterns using ripgrep/grep. "
    "Supports regex patterns, file type filtering, context lines, and path exclusions. "
    "Returns matching file paths with line numbers and content.",
    [
        ToolParam("pattern", ParamType.STRING,
                  description="Search pattern (regex supported with ripgrep, literal with grep)"),
        ToolParam("path", ParamType.STRING, required=False,
                  description="Subdirectory or file to search in (relative to workspace root). Default: entire workspace."),
        ToolParam("file_types", ParamType.STRING, required=False,
                  description="Comma-separated file extensions or globs, e.g. 'py,ts,vue' or '*.py,*.ts'"),
        ToolParam("context_lines", ParamType.INTEGER, required=False,
                  description="Number of context lines to show around matches (default: 2)"),
        ToolParam("max_results", ParamType.INTEGER, required=False,
                  description="Maximum number of results to return (default: 50)"),
        ToolParam("case_sensitive", ParamType.BOOLEAN, required=False,
                  description="Whether to do case-sensitive search (default: false)"),
        ToolParam("exclude_pattern", ParamType.STRING, required=False,
                  description="Glob pattern to exclude, e.g. '**/node_modules/**,**/.git/**'"),
    ],
    category="ide",
)
def _codebase_search(
    pattern: str,
    path: str = ".",
    file_types: str = "",
    context_lines: int = 2,
    max_results: int = 50,
    case_sensitive: bool = False,
    exclude_pattern: str = "",
) -> str:
    """在代码库中全文搜索文本模式"""
    import fnmatch

    try:
        search_root = _resolve_safe(path)
    except PermissionError as e:
        return json.dumps({"error": str(e)})

    if not search_root.exists():
        return json.dumps({"error": f"Path not found: {path}"})

    # 构建默认排除列表
    default_excludes = [
        "**/node_modules/**", "**/.git/**", "**/__pycache__/**",
        "**/dist/**", "**/build/**", "**/.venv/**", "**/venv/**",
        "**/.next/**", "**/.nuxt/**", "**/target/**",
        "**/*.pyc", "**/*.pyo", "**/*.class", "**/*.o",
        "**/*.min.js", "**/*.min.css", "**/pnpm-lock.yaml",
        "**/uv.lock", "**/package-lock.json", "**/yarn.lock",
        "**/*.lock", "**/*.sum",
    ]

    if exclude_pattern:
        custom_excludes = [e.strip() for e in exclude_pattern.split(",") if e.strip()]
        default_excludes.extend(custom_excludes)

    # 尝试使用 ripgrep，回退到纯 Python 搜索
    try:
        result = subprocess.run(
            ["rg", "--version"], capture_output=True, timeout=2
        )
        use_rg = result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        use_rg = False

    if use_rg:
        return _search_with_rg(
            pattern, search_root, file_types, context_lines,
            max_results, case_sensitive, default_excludes,
        )
    else:
        return _search_with_python(
            pattern, search_root, file_types, context_lines,
            max_results, case_sensitive, default_excludes,
        )


def _search_with_rg(
    pattern: str,
    search_root: Path,
    file_types: str,
    context_lines: int,
    max_results: int,
    case_sensitive: bool,
    excludes: list[str],
) -> str:
    """使用 ripgrep 搜索"""
    cmd = ["rg", "--no-heading", "--line-number", "--color=never"]

    if context_lines > 0:
        cmd.extend(["-C", str(context_lines)])

    if not case_sensitive:
        cmd.append("-i")

    if max_results:
        cmd.extend(["-m", str(max_results)])

    # 文件类型过滤
    if file_types:
        for ft in file_types.split(","):
            ft = ft.strip()
            if ft:
                if ft.startswith("*."):
                    cmd.extend(["-g", ft])
                else:
                    cmd.extend(["-g", f"*.{ft}"])

    # 排除模式
    for exc in excludes:
        cmd.extend(["-g", f"!{exc}"])

    cmd.append(pattern)
    cmd.append(str(search_root))

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            cwd=str(_WORKSPACE_ROOT),
        )
        output = proc.stdout.strip()
        if not output:
            return json.dumps({
                "pattern": pattern,
                "path": str(search_root),
                "match_count": 0,
                "results": [],
                "engine": "ripgrep",
                "hint": "No matches found. Try a broader pattern or different file types.",
            })

        # 解析 rg 输出，限制结果数
        lines = output.split("\n")[:max_results + context_lines * 2]
        results = _parse_rg_output(lines)

        return json.dumps({
            "pattern": pattern,
            "path": str(search_root),
            "match_count": len(results),
            "results": results,
            "engine": "ripgrep",
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Search timed out (30s). Try a narrower path or pattern."})
    except Exception as e:
        return json.dumps({"error": f"Search failed: {e}"})


def _parse_rg_output(lines: list[str]) -> list[dict[str, Any]]:
    """解析 ripgrep 输出行"""
    results: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        # rg 格式: file:line:content 或 file-line-content (context)
        if not line.strip():
            continue

        # 尝试匹配匹配行: filepath:lineno:content
        m = re.match(r"^(.+?):(\d+):(.*)$", line)
        if m:
            filepath = m.group(1)
            lineno = int(m.group(2))
            content = m.group(3)

            # 判断是匹配行还是上下文行
            is_match = content and not content.startswith("-")  # heuristic
            if current and filepath == current.get("file"):
                # 同一文件的连续上下文
                if "context" not in current:
                    current["context"] = []
                current["context"].append({"line": lineno, "content": content})
            else:
                if current:
                    results.append(current)
                current = {
                    "file": filepath,
                    "line": lineno,
                    "content": content,
                    "context": [],
                }
        elif current:
            # 可能是 context 的续行
            if "context" not in current:
                current["context"] = []
            current["context"].append({"line": -1, "content": line})

    if current:
        results.append(current)

    return results


def _search_with_python(
    pattern: str,
    search_root: Path,
    file_types: str,
    context_lines: int,
    max_results: int,
    case_sensitive: bool,
    excludes: list[str],
) -> str:
    """使用纯 Python 进行文件搜索（grep 回退）"""
    import fnmatch

    text_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".svelte",
        ".html", ".css", ".scss", ".less", ".json", ".yaml", ".yml",
        ".toml", ".xml", ".md", ".txt", ".sh", ".bash", ".zsh",
        ".c", ".cpp", ".h", ".hpp", ".java", ".go", ".rs", ".rb",
        ".php", ".swift", ".kt", ".scala", ".r", ".sql", ".graphql",
        ".env", ".cfg", ".ini", ".conf", ".dockerfile", "Dockerfile",
        ".makefile", "Makefile",
    }

    # 文件类型过滤
    if file_types:
        allowed_exts = set()
        for ft in file_types.split(","):
            ft = ft.strip()
            if ft.startswith("*."):
                allowed_exts.add(ft[1:])
            else:
                allowed_exts.add(f".{ft}")
        text_extensions = allowed_exts

    # 预编译正则
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return json.dumps({"error": f"Invalid regex pattern: {e}"})

    results: list[dict[str, Any]] = []
    searched = 0

    for file_path in sorted(search_root.rglob("*")):
        # 排除检查
        rel_path = str(file_path.relative_to(_WORKSPACE_ROOT))
        skip = False
        for exc in excludes:
            if fnmatch.fnmatch(rel_path, exc.replace("!", "")):
                skip = True
                break
        if skip:
            continue

        if not file_path.is_file():
            continue
        if file_path.suffix not in text_extensions:
            if file_path.name not in text_extensions:
                continue

        searched += 1
        try:
            size = file_path.stat().st_size
            if size > _MAX_FILE_SIZE:
                continue

            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                file_lines = f.readlines()

            for i, line in enumerate(file_lines):
                if regex.search(line):
                    entry: dict[str, Any] = {
                        "file": rel_path,
                        "line": i + 1,
                        "content": line.rstrip("\n\r"),
                        "context": [],
                    }
                    if context_lines > 0:
                        ctx_start = max(0, i - context_lines)
                        ctx_end = min(len(file_lines), i + context_lines + 1)
                        for j in range(ctx_start, ctx_end):
                            if j != i:
                                entry["context"].append({
                                    "line": j + 1,
                                    "content": file_lines[j].rstrip("\n\r"),
                                })
                    results.append(entry)
                    if len(results) >= max_results:
                        break
        except Exception:
            continue

        if len(results) >= max_results:
            break

    return json.dumps({
        "pattern": pattern,
        "path": str(search_root),
        "files_searched": searched,
        "match_count": len(results),
        "results": results,
        "engine": "python-grep",
    }, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════
# Tool 2: file_operation — 文件系统 CRUD
# ══════════════════════════════════════════════════════════════

@register_tool(
    "file_operation",
    "Perform file system operations: create, read, update, delete, list, move, copy, "
    "and check if a file exists. All operations are restricted to the workspace directory. "
    "For reading, use 'read'. For writing/updating, use 'write' or 'append'. "
    "For listing, use 'list'. For deletion, use 'delete'. "
    "For moving/renaming, use 'move'. For copying, use 'copy'.",
    [
        ToolParam("operation", ParamType.STRING,
                  description="Operation type: read | write | append | delete | list | move | copy | exists"),
        ToolParam("path", ParamType.STRING,
                  description="Target file or directory path (relative to workspace or absolute within workspace)"),
        ToolParam("content", ParamType.STRING, required=False,
                  description="Content to write (required for write/append operations)"),
        ToolParam("destination", ParamType.STRING, required=False,
                  description="Destination path for move/copy operations"),
        ToolParam("max_lines", ParamType.INTEGER, required=False,
                  description="Max lines to read (for 'read' operation, default: 500)"),
        ToolParam("encoding", ParamType.STRING, required=False,
                  description="File encoding (default: utf-8)"),
    ],
    category="ide",
)
def _file_operation(
    operation: str,
    path: str,
    content: str = "",
    destination: str = "",
    max_lines: int = 500,
    encoding: str = "utf-8",
) -> str:
    """文件系统 CRUD 操作"""
    try:
        op = operation.lower().strip()

        handle_map = {
            "read": _file_read,
            "write": _file_write,
            "append": _file_append,
            "delete": _file_delete,
            "list": _file_list,
            "move": _file_move,
            "copy": _file_copy,
            "exists": _file_exists,
        }

        handler = handle_map.get(op)
        if handler is None:
            return json.dumps({
                "error": f"Unknown operation '{operation}'. "
                         f"Valid: {', '.join(handle_map.keys())}"
            })

        return handler(path, content, destination, max_lines, encoding)

    except PermissionError as e:
        return json.dumps({"operation": operation, "path": path, "error": str(e)})
    except Exception as e:
        return json.dumps({"operation": operation, "path": path, "error": str(e)})


def _file_read(
    path: str, _content: str, _dest: str, max_lines: int, encoding: str,
) -> str:
    """读取文件"""
    p = _resolve_safe(path)
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}", "path": path})
    if not p.is_file():
        return json.dumps({"error": f"Not a file: {path}", "path": path})

    size = p.stat().st_size
    if size > _MAX_FILE_SIZE:
        return json.dumps({
            "error": f"File too large ({size} bytes, max {_MAX_FILE_SIZE})",
            "path": path, "size": size,
        })

    with open(p, "r", encoding=encoding, errors="replace") as f:
        lines = []
        for i, line in enumerate(f):
            if i >= max_lines:
                lines.append(f"... (truncated, total {size} bytes)")
                break
            lines.append(line.rstrip("\n\r"))

    return json.dumps({
        "operation": "read",
        "path": str(p),
        "lines": len(lines),
        "size_bytes": size,
        "content": "\n".join(lines),
    }, ensure_ascii=False)


def _file_write(
    path: str, content: str, _dest: str, _max_lines: int, encoding: str,
) -> str:
    """写入文件（创建或覆盖）"""
    p = _resolve_safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "w", encoding=encoding) as f:
        f.write(content)

    return json.dumps({
        "operation": "write",
        "path": str(p),
        "size_bytes": len(content.encode(encoding)),
        "chars": len(content),
    })


def _file_append(
    path: str, content: str, _dest: str, _max_lines: int, encoding: str,
) -> str:
    """追加内容到文件"""
    p = _resolve_safe(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    with open(p, "a", encoding=encoding) as f:
        f.write(content)

    return json.dumps({
        "operation": "append",
        "path": str(p),
        "appended_bytes": len(content.encode(encoding)),
        "appended_chars": len(content),
    })


def _file_delete(
    path: str, _content: str, _dest: str, _max_lines: int, _encoding: str,
) -> str:
    """删除文件或空目录"""
    p = _resolve_safe(path)
    if not p.exists():
        return json.dumps({"error": f"Not found: {path}", "path": path})

    if p.is_file():
        p.unlink()
        return json.dumps({"operation": "delete", "path": str(p), "type": "file", "deleted": True})
    elif p.is_dir():
        try:
            p.rmdir()
            return json.dumps({"operation": "delete", "path": str(p), "type": "directory", "deleted": True})
        except OSError:
            return json.dumps({
                "error": f"Directory not empty: {path}. Use list to see contents first.",
                "path": path,
            })
    return json.dumps({"error": f"Unknown type: {path}"})


def _file_list(
    path: str, _content: str, _dest: str, _max_lines: int, _encoding: str,
) -> str:
    """列出目录内容"""
    p = _resolve_safe(path)
    if not p.exists():
        return json.dumps({"error": f"Path not found: {path}"})
    if not p.is_dir():
        return json.dumps({"error": f"Not a directory: {path}"})

    entries = []
    try:
        for entry in sorted(p.iterdir()):
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "type": "directory" if entry.is_dir() else "file",
                "size_bytes": stat.st_size if entry.is_file() else None,
                "modified": stat.st_mtime,
            })

        return json.dumps({
            "operation": "list",
            "path": str(p),
            "entry_count": len(entries),
            "entries": entries,
        }, ensure_ascii=False)
    except PermissionError as e:
        return json.dumps({"error": str(e), "path": str(p)})


def _file_move(
    path: str, _content: str, dest: str, _max_lines: int, _encoding: str,
) -> str:
    """移动/重命名文件"""
    src = _resolve_safe(path)
    dst = _resolve_safe(dest)

    if not src.exists():
        return json.dumps({"error": f"Source not found: {path}"})

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))

    return json.dumps({
        "operation": "move",
        "source": str(src),
        "destination": str(dst),
    })


def _file_copy(
    path: str, _content: str, dest: str, _max_lines: int, _encoding: str,
) -> str:
    """复制文件"""
    src = _resolve_safe(path)
    dst = _resolve_safe(dest)

    if not src.exists():
        return json.dumps({"error": f"Source not found: {path}"})

    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(str(src), str(dst))
    else:
        shutil.copytree(str(src), str(dst), dirs_exist_ok=True)

    return json.dumps({
        "operation": "copy",
        "source": str(src),
        "destination": str(dst),
    })


def _file_exists(
    path: str, _content: str, _dest: str, _max_lines: int, _encoding: str,
) -> str:
    """检查文件/目录是否存在"""
    p = _resolve_safe(path)
    exists = p.exists()
    return json.dumps({
        "operation": "exists",
        "path": str(p),
        "exists": exists,
        "type": "file" if exists and p.is_file() else "directory" if exists and p.is_dir() else "none",
    })


# ══════════════════════════════════════════════════════════════
# Tool 3: terminal_exec — 安全终端执行
# ══════════════════════════════════════════════════════════════

@register_tool(
    "terminal_exec",
    "Execute a shell command safely within the workspace. "
    "Only whitelisted commands are allowed. Output is truncated after 500 lines. "
    "Commands run with a 60-second timeout. "
    "Use sparingly — prefer codebase_search and file_operation for most tasks.",
    [
        ToolParam("command", ParamType.STRING,
                  description="Shell command to execute (must be whitelisted). "
                              "Examples: 'ls -la', 'git status', 'python --version', "
                              "'npm run build', 'grep -r pattern ./src'"),
        ToolParam("workdir", ParamType.STRING, required=False,
                  description="Working directory relative to workspace (default: workspace root)"),
        ToolParam("timeout_seconds", ParamType.INTEGER, required=False,
                  description="Command timeout in seconds (default: 60, max: 120)"),
        ToolParam("env_vars", ParamType.STRING, required=False,
                  description="Additional environment variables as JSON object, e.g. '{\"NODE_ENV\":\"production\"}'"),
    ],
    category="ide",
)
def _terminal_exec(
    command: str,
    workdir: str = ".",
    timeout_seconds: int = 60,
    env_vars: str = "{}",
) -> str:
    """安全执行终端命令"""
    try:
        # 安全检查命令
        args = _safe_cmd(command)
    except (PermissionError, ValueError) as e:
        return json.dumps({"command": command, "error": str(e), "exit_code": -1})

    # 工作目录
    try:
        cwd = _resolve_safe(workdir)
        if not cwd.is_dir():
            cwd = _WORKSPACE_ROOT
    except PermissionError:
        cwd = _WORKSPACE_ROOT

    # 超时限制
    timeout = min(timeout_seconds, 120)

    # 环境变量
    extra_env = {}
    try:
        extra_env = json.loads(env_vars)
    except (json.JSONDecodeError, TypeError):
        pass
    env = {**os.environ, **extra_env}

    # 用 shlex.split 解析后的参数列表执行 — 避免 shell=True 注入风险
    try:
        proc = subprocess.run(
            args,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd),
            env=env,
        )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        # 截断输出
        stdout_lines = stdout.split("\n")
        stderr_lines = stderr.split("\n")

        stdout_truncated = len(stdout_lines) > _MAX_OUTPUT_LINES
        stderr_truncated = len(stderr_lines) > _MAX_OUTPUT_LINES

        if stdout_truncated:
            stdout = "\n".join(stdout_lines[:_MAX_OUTPUT_LINES])
            stdout += f"\n... (truncated, {len(stdout_lines)} lines total)"

        if stderr_truncated:
            stderr = "\n".join(stderr_lines[:_MAX_OUTPUT_LINES])
            stderr += f"\n... (truncated, {len(stderr_lines)} lines total)"

        return json.dumps({
            "command": command,
            "workdir": str(cwd),
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": stdout_truncated or stderr_truncated,
        }, ensure_ascii=False)

    except subprocess.TimeoutExpired:
        return json.dumps({
            "command": command,
            "error": f"Command timed out after {timeout}s",
            "exit_code": -1,
            "stdout": "",
            "stderr": f"Timeout after {timeout}s",
        })
    except Exception as e:
        return json.dumps({
            "command": command,
            "error": str(e),
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
        })
