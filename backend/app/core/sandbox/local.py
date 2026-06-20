"""
LocalSandbox — 宿主机本地沙箱

借鉴 DeerFlow LocalSandbox + 安全策略：
- 路径白名单/黑名单校验
- 命令执行超时 + 输出截断
- 危险命令拦截（rm -rf /, mkfs, dd 等）
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
import re
import time
from typing import Any

from app.core.sandbox.base import CommandResult, FileInfo, Sandbox, SandboxConfig

logger = logging.getLogger("sandbox.local")

# 危险命令黑名单
_DANGEROUS_PATTERNS: list[re.Pattern] = [
    re.compile(r"\brm\s+-rf\s+/"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\b>:?\s*/dev/"),
    re.compile(r"\bchmod\s+777\s+/"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bcurl\b.*\|.*\bsh\b"),
    re.compile(r"\bwget\b.*\|.*\bsh\b"),
    re.compile(r"\bfork\s+bomb\b"),
    re.compile(r"\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\};?\s*:"),
]


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

    # ── 命令执行 ────────────────────────────────────

    async def execute_command(self, command: str, cwd: str | None = None) -> CommandResult:
        cwd = cwd or self.config.workspace_dir
        self._check_dangerous_command(command)

        start = time.perf_counter()
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_shell(
                    command,
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
        """检测危险命令"""
        for pattern in _DANGEROUS_PATTERNS:
            if pattern.search(command):
                raise PermissionError(
                    f"Dangerous command detected: '{command[:100]}' matches pattern '{pattern.pattern}'"
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
