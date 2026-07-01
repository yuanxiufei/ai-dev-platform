"""
LocalSandbox — 宿主机本地沙箱

借鉴 DeerFlow LocalSandbox + 安全策略：
- 路径白名单/黑名单校验
- 命令执行超时 + 输出截断
- 危险命令拦截（rm -rf /, mkfs, dd 等）
- Session 09: 进程资源限制 (ulimit 包装)
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import re
import sys
import time
from typing import Any

from app.core.sandbox.base import CommandResult, FileInfo, Sandbox, SandboxConfig

logger = logging.getLogger("sandbox.local")

# Session 09: 平台检测 — resource 模块仅在 Unix 可用
_is_unix = sys.platform != "win32"

# 危险命令黑名单 — 借鉴 Google Colab / Kaggle 沙箱安全策略
# 注：沙箱不采用命令白名单（对开发类命令不可行），
# 而是通过正则黑名单 + 路径白名单 + 超时 + 输出截断多层防御
_DANGEROUS_PATTERNS: list[re.Pattern] = [
    # 文件系统破坏
    re.compile(r"\brm\s+-rf\s+/"),
    re.compile(r"\brm\s+-rf\s+~"),
    re.compile(r"\brm\s+-rf\s+\*"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\b>:?\s*/dev/"),
    re.compile(r"\bchmod\s+777\s+/"),
    re.compile(r"\bchmod\s+-R\s+777"),
    re.compile(r"\bchown\s+-R\s+/"),
    # 系统关机
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bhalt\b"),
    re.compile(r"\bpoweroff\b"),
    re.compile(r"\binit\s+[06]"),
    # 远程代码执行
    re.compile(r"\bcurl\b.*\|.*\bsh\b"),
    re.compile(r"\bcurl\b.*\|.*\bbash\b"),
    re.compile(r"\bwget\b.*\|.*\bsh\b"),
    re.compile(r"\bwget\b.*\|.*\bbash\b"),
    re.compile(r"\bcurl\b.*-o.*&&.*\b(sh|bash|python)\b"),
    # Fork bomb
    re.compile(r"\bfork\s+bomb\b"),
    re.compile(r"\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\};?\s*:"),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"),
    # 危险挂载/内核
    re.compile(r"\bmount\s+-"),
    re.compile(r"\bumount\s+/"),
    re.compile(r"\binsmod\b"),
    re.compile(r"\brmmod\b"),
    re.compile(r"\bfdisk\b"),
    # 信息泄露
    re.compile(r"\bcat\s+/etc/(passwd|shadow)\b"),
    re.compile(r"\bcat\s+.*\.pem\b"),
    re.compile(r"\bfind\s+/etc\b"),
]

# Shell 元字符注入 — 在无白名单校验的上下文中检测
_SHELL_INJECTION_RE = re.compile(r'[;&|`$(){}\[\]!#~*?<>]')


class LocalSandbox(Sandbox):
    """宿主机本地沙箱

    路径限制在工作区内，命令有危险检测和超时控制。
    """

    def __init__(self, config: SandboxConfig | None = None) -> None:
        super().__init__(config)
        # 默认黑名单
        if not self.config.denied_paths:
            self.config.denied_paths = [
                "/etc", "/sys", "/proc", "/dev", "/boot",
                "/root", "/var/log", "/var/run",
                os.path.expanduser("~/.ssh"),
                os.path.expanduser("~/.gnupg"),
            ]
        # 确保工作区目录存在
        os.makedirs(self.config.workspace_dir, exist_ok=True)

    # ── 资源限制 ────────────────────────────────────

    def _wrap_resource_limits(self, command: str) -> str:
        """Session 09: 用 ulimit 包裹命令以施加进程资源限制。

        仅在 Unix 平台生效（Windows 跳过）。
        """
        if not _is_unix:
            return command

        cfg = self.config
        limits: list[str] = []

        # 虚拟内存限制 (KB)
        if cfg.resource_memory_limit_mb > 0:
            limits.append(f"ulimit -v {cfg.resource_memory_limit_mb * 1024}")

        # CPU 时间限制 (秒)
        if cfg.resource_cpu_limit_seconds > 0:
            limits.append(f"ulimit -t {cfg.resource_cpu_limit_seconds}")

        # 最大进程数
        if cfg.resource_max_processes > 0:
            limits.append(f"ulimit -u {cfg.resource_max_processes}")

        # 最大文件写入大小 (KB)
        if cfg.resource_max_file_size_mb > 0:
            limits.append(f"ulimit -f {cfg.resource_max_file_size_mb * 1024}")

        if not limits:
            return command

        return "; ".join(limits) + "; " + command

    # ── 命令执行 ────────────────────────────────────

    async def execute_command(self, command: str, cwd: str | None = None) -> CommandResult:
        cwd = cwd or self.config.workspace_dir
        self._check_dangerous_command(command)
        self._check_injection(command)

        # Session 09: 施加资源限制
        limited_command = self._wrap_resource_limits(command)

        start = time.perf_counter()
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    limited_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                ),
                timeout=10.0,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.config.command_timeout,
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            truncated = False
            if len(stdout) > self.config.max_output_bytes:
                stdout = stdout[:self.config.max_output_bytes] + "\n[OUTPUT TRUNCATED]"
                truncated = True
            if len(stderr) > self.config.max_output_bytes:
                stderr = stderr[:self.config.max_output_bytes] + "\n[OUTPUT TRUNCATED]"
                truncated = True

            latency = (time.perf_counter() - start) * 1000

            return CommandResult(
                stdout=stdout,
                stderr=stderr,
                exit_code=proc.returncode or 0,
                truncated=truncated,
                latency_ms=latency,
            )

        except asyncio.TimeoutError:
            latency = (time.perf_counter() - start) * 1000
            return CommandResult(
                stdout="",
                stderr=f"Command timed out after {self.config.command_timeout}s",
                exit_code=124,
                truncated=True,
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return CommandResult(
                stdout="",
                stderr=str(e),
                exit_code=1,
                latency_ms=latency,
            )

    def _check_dangerous_command(self, command: str) -> None:
        """检测危险命令模式"""
        for pattern in _DANGEROUS_PATTERNS:
            if pattern.search(command):
                raise PermissionError(
                    f"Dangerous command detected: '{command[:100]}' matches pattern '{pattern.pattern}'"
                )

    def _check_injection(self, command: str) -> None:
        """检测 Shell 元字符注入 — 仅允许简单命令"""
        if _SHELL_INJECTION_RE.search(command):
            raise PermissionError(
                f"Shell metacharacters detected in command: '{command[:100]}'"
            )

    # ── 文件操作 ────────────────────────────────────

    async def read_file(self, path: str, encoding: str = "utf-8") -> str:
        abs_path = self.validate_path(path)
        try:
            with open(abs_path, "r", encoding=encoding) as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {path}")

    async def write_file(self, path: str, content: str, encoding: str = "utf-8") -> None:
        abs_path = self.validate_path(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding=encoding) as f:
            f.write(content)

    async def file_exists(self, path: str) -> bool:
        try:
            abs_path = self.validate_path(path)
            return os.path.exists(abs_path)
        except PermissionError:
            return False

    async def list_dir(self, path: str, max_depth: int = 1) -> list[FileInfo]:
        abs_path = self.validate_path(path)
        result: list[FileInfo] = []

        def _walk(current: str, depth: int) -> None:
            if depth > max_depth:
                return
            try:
                for entry in os.scandir(current):
                    stat = entry.stat()
                    result.append(FileInfo(
                        path=os.path.relpath(entry.path, self.config.workspace_dir),
                        size=stat.st_size,
                        is_dir=entry.is_dir(),
                        modified_at=stat.st_mtime,
                    ))
                    if entry.is_dir() and depth < max_depth:
                        _walk(entry.path, depth + 1)
            except PermissionError:
                pass

        _walk(abs_path, 1)
        return result

    async def delete_file(self, path: str) -> None:
        abs_path = self.validate_path(path)
        if os.path.isdir(abs_path):
            import shutil
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)

    async def glob(self, path: str, pattern: str) -> tuple[list[str], bool]:
        import glob as glob_module
        abs_path = self.validate_path(path)
        search_pattern = os.path.join(abs_path, pattern)
        matches = glob_module.glob(search_pattern, recursive=True)
        rel_matches = [
            os.path.relpath(m, self.config.workspace_dir)
            for m in matches
        ]
        truncated = len(rel_matches) > 1000
        if truncated:
            rel_matches = rel_matches[:1000]
        return rel_matches, truncated

    async def grep(self, path: str, pattern: str) -> list[dict[str, Any]]:
        abs_path = self.validate_path(path)
        results: list[dict[str, Any]] = []
        try:
            regex = re.compile(pattern)
        except re.error:
            return results

        for root, _dirs, files in os.walk(abs_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for lineno, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append({
                                    "path": os.path.relpath(fpath, self.config.workspace_dir),
                                    "line_number": lineno,
                                    "line": line.rstrip(),
                                })
                except (PermissionError, OSError):
                    continue

                if len(results) >= 500:
                    results.append({"path": "...", "line_number": 0, "line": "[GREP TRUNCATED at 500 matches]"})
                    break
            if len(results) >= 500:
                break

        return results

    async def close(self) -> None:
        pass
