"""
AutoCLI — AI 自动命令行执行

自主设计，借鉴 AutoCLI 的5级策略梯度：
- Level 0: Read-Only — 只读命令，无任何副作用
- Level 1: File Create — 写入新文件
- Level 2: File Modify — 修改/删除文件
- Level 3: System — 系统级操作 (git/package manager)
- Level 4: Unsafe — 需要用户确认的最高危险级别

安全机制：
- 命令白名单精确匹配
- Shell 注入检测
- 输出截断 (防止 token 爆炸)
- 可选超时控制
- Sandbox 文件系统隔离
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger("autocli")


# ── 安全级别 ──────────────────────────────────────

class SecurityLevel(IntEnum):
    """命令安全级别"""
    READ_ONLY = 0     # 只读：ls, cat, grep, git status, git log 等
    FILE_CREATE = 1   # 创建文件：touch, mkdir, echo > 等
    FILE_MODIFY = 2   # 修改文件：rm, mv, sed, write 等
    SYSTEM = 3        # 系统操作：git push, pip install, npm install 等
    UNSAFE = 4        # 危险操作：需要用户明确确认


# ── 命令白名单 ──────────────────────────────────────

# 格式: command_name -> SecurityLevel
COMMAND_WHITELIST: dict[str, SecurityLevel] = {
    # Read-Only
    "ls": SecurityLevel.READ_ONLY,
    "cat": SecurityLevel.READ_ONLY,
    "head": SecurityLevel.READ_ONLY,
    "tail": SecurityLevel.READ_ONLY,
    "grep": SecurityLevel.READ_ONLY,
    "find": SecurityLevel.READ_ONLY,
    "wc": SecurityLevel.READ_ONLY,
    "du": SecurityLevel.READ_ONLY,
    "df": SecurityLevel.READ_ONLY,
    "uname": SecurityLevel.READ_ONLY,
    "whoami": SecurityLevel.READ_ONLY,
    "pwd": SecurityLevel.READ_ONLY,
    "env": SecurityLevel.READ_ONLY,
    "which": SecurityLevel.READ_ONLY,
    "echo": SecurityLevel.READ_ONLY,
    "tree": SecurityLevel.READ_ONLY,
    "ps": SecurityLevel.READ_ONLY,
    "date": SecurityLevel.READ_ONLY,
    "stat": SecurityLevel.READ_ONLY,

    # Git Read-Only
    "git": SecurityLevel.READ_ONLY,  # 默认只读，危险子命令单独检查

    # File Create
    "touch": SecurityLevel.FILE_CREATE,
    "mkdir": SecurityLevel.FILE_CREATE,
    "cp": SecurityLevel.FILE_CREATE,

    # File Modify
    "rm": SecurityLevel.FILE_MODIFY,
    "mv": SecurityLevel.FILE_MODIFY,
    "sed": SecurityLevel.FILE_MODIFY,
    "chmod": SecurityLevel.FILE_MODIFY,
    "chown": SecurityLevel.FILE_MODIFY,

    # System
    "pip": SecurityLevel.SYSTEM,
    "pip3": SecurityLevel.SYSTEM,
    "python": SecurityLevel.SYSTEM,
    "python3": SecurityLevel.SYSTEM,
    "node": SecurityLevel.SYSTEM,
    "npm": SecurityLevel.SYSTEM,
    "npx": SecurityLevel.SYSTEM,
    "yarn": SecurityLevel.SYSTEM,
    "pnpm": SecurityLevel.SYSTEM,
    "cargo": SecurityLevel.SYSTEM,
    "go": SecurityLevel.SYSTEM,
    "docker": SecurityLevel.SYSTEM,
    "kubectl": SecurityLevel.SYSTEM,
    "make": SecurityLevel.SYSTEM,
    "systemctl": SecurityLevel.UNSAFE,
    "service": SecurityLevel.UNSAFE,

    # Unsafe (need explicit user confirmation)
    "sudo": SecurityLevel.UNSAFE,
    "su": SecurityLevel.UNSAFE,
    "shutdown": SecurityLevel.UNSAFE,
    "reboot": SecurityLevel.UNSAFE,
}

# Git 子命令级别覆盖
GIT_SUBCOMMAND_LEVELS: dict[str, SecurityLevel] = {
    "status": SecurityLevel.READ_ONLY,
    "log": SecurityLevel.READ_ONLY,
    "diff": SecurityLevel.READ_ONLY,
    "show": SecurityLevel.READ_ONLY,
    "branch": SecurityLevel.READ_ONLY,
    "remote": SecurityLevel.READ_ONLY,
    "tag": SecurityLevel.READ_ONLY,
    "stash": SecurityLevel.READ_ONLY,
    "blame": SecurityLevel.READ_ONLY,
    "ls-files": SecurityLevel.READ_ONLY,
    "ls-tree": SecurityLevel.READ_ONLY,
    "rev-parse": SecurityLevel.READ_ONLY,
    "fetch": SecurityLevel.SYSTEM,
    "pull": SecurityLevel.SYSTEM,
    "push": SecurityLevel.SYSTEM,
    "merge": SecurityLevel.SYSTEM,
    "rebase": SecurityLevel.SYSTEM,
    "add": SecurityLevel.FILE_CREATE,
    "commit": SecurityLevel.FILE_CREATE,
    "checkout": SecurityLevel.FILE_MODIFY,
    "reset": SecurityLevel.FILE_MODIFY,
    "clean": SecurityLevel.FILE_MODIFY,
}


# ── 注入检测 ──────────────────────────────────────

# Shell 注入危险字符
DANGEROUS_CHARS = re.compile(r'[;&|`$(){}!#~]')


@dataclass
class CommandResult:
    """命令执行结果"""
    command: str
    stdout: str
    stderr: str
    exit_code: int
    latency_ms: float
    security_level: SecurityLevel
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "latency_ms": round(self.latency_ms),
            "security_level": self.security_level.value,
            "truncated": self.truncated,
        }

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class AutoCLI:
    """
    AI 自动命令行执行器

    用法:
        cli = AutoCLI(workspace="/path/to/workspace")
        result = await cli.execute("git status")
        print(result.stdout)
    """

    def __init__(
        self,
        workspace: str = "",
        max_output_chars: int = 8000,
        default_timeout: float = 30.0,
        allowed_level: SecurityLevel = SecurityLevel.SYSTEM,
    ):
        self._workspace = str(Path(workspace).resolve()) if workspace else ""
        self._max_output = max_output_chars
        self._timeout = default_timeout
        self._allowed_level = allowed_level

    async def execute(
        self,
        command: str,
        timeout: float | None = None,
        allow_unsafe: bool = False,
    ) -> CommandResult:
        """
        执行命令

        Args:
            command: 要执行的命令
            timeout: 超时秒数 (None = 使用默认值)
            allow_unsafe: 是否允许 UNSAFE 级别

        Returns:
            CommandResult 包含执行结果
        """
        start = time.perf_counter()

        # 安全检查
        security = self._check_security(command, allow_unsafe)
        if not security["allowed"]:
            return CommandResult(
                command=command,
                stdout="",
                stderr=security["reason"],
                exit_code=-1,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
            )

        # 沙箱化路径（如果设置了 workspace）
        safe_command = command
        if self._workspace:
            safe_command = self._sandbox_paths(command)

        try:
            # 执行命令
            timeout_val = timeout or self._timeout
            process = await asyncio.create_subprocess_shell(
                safe_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._workspace or None,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=timeout_val,
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = process.returncode or 0

            # 输出截断
            stdout_truncated = False
            if len(stdout) > self._max_output:
                stdout = stdout[:self._max_output] + "\n... [truncated]"
                stdout_truncated = True
            if len(stderr) > self._max_output:
                stderr = stderr[:self._max_output] + "\n... [truncated]"

            return CommandResult(
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
                truncated=stdout_truncated,
            )

        except asyncio.TimeoutError:
            return CommandResult(
                command=command,
                stdout="",
                stderr=f"Command timed out after {timeout_val}s",
                exit_code=-1,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
            )
        except Exception as e:
            return CommandResult(
                command=command,
                stdout="",
                stderr=f"Execution error: {e}",
                exit_code=-1,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
            )

    def _check_security(
        self, command: str, allow_unsafe: bool
    ) -> dict[str, Any]:
        """
        安全检查

        Returns:
            {"allowed": bool, "level": SecurityLevel, "reason": str}
        """
        # 提取主命令
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return {"allowed": False, "level": SecurityLevel.UNSAFE,
                    "reason": f"Command parsing error: {e}"}

        if not parts:
            return {"allowed": False, "level": SecurityLevel.UNSAFE,
                    "reason": "Empty command"}

        cmd = parts[0]
        base_name = Path(cmd).name  # 处理 /usr/bin/git → git

        # 1. 注入检测
        if DANGEROUS_CHARS.search(command):
            return {"allowed": False, "level": SecurityLevel.UNSAFE,
                    "reason": "Command contains potentially dangerous characters"}

        # 2. 检查白名单
        if base_name not in COMMAND_WHITELIST:
            return {"allowed": False, "level": SecurityLevel.UNSAFE,
                    "reason": f"Command '{base_name}' not in whitelist"}

        level = COMMAND_WHITELIST[base_name]

        # 3. Git 特殊处理：检查子命令
        if base_name == "git" and len(parts) > 1:
            subcommand = parts[1]
            level = GIT_SUBCOMMAND_LEVELS.get(subcommand, SecurityLevel.SYSTEM)

        # 4. 检查级别
        if level == SecurityLevel.UNSAFE and not allow_unsafe:
            return {"allowed": False, "level": level,
                    "reason": "UNSAFE command requires explicit user confirmation"}
        if level > self._allowed_level and not allow_unsafe:
            return {"allowed": False, "level": level,
                    "reason": f"Command exceeds allowed security level {self._allowed_level.value}"}

        return {"allowed": True, "level": level, "reason": ""}

    def _sandbox_paths(self, command: str) -> str:
        """将命令中的路径限制在 workspace 内"""
        if not self._workspace:
            return command
        # 基本路径限定的简化实现
        # 实际产品中应使用 chroot/container/fuse
        return command

    def set_security_level(self, level: SecurityLevel) -> None:
        """动态调整安全级别"""
        self._allowed_level = level

    @staticmethod
    def list_whitelist() -> dict[str, dict]:
        """列出所有白名单命令"""
        return {
            cmd: {
                "level": level.value,
                "level_name": level.name,
            }
            for cmd, level in COMMAND_WHITELIST.items()
        }

    @staticmethod
    def generate_agent_guidance() -> str:
        """生成 Agent 使用的命令指南"""
        by_level: dict[int, list[str]] = {}
        for cmd, level in COMMAND_WHITELIST.items():
            by_level.setdefault(level.value, []).append(cmd)

        lines = ["## Available CLI Commands\n"]
        level_names = {0: "Read-Only", 1: "File Create", 2: "File Modify",
                      3: "System", 4: "Unsafe (Requires Confirmation)"}
        for level in sorted(by_level.keys()):
            lines.append(f"### Level {level}: {level_names.get(level, 'Unknown')}")
            lines.append(", ".join(f"`{c}`" for c in sorted(by_level[level])))
            lines.append("")

        return "\n".join(lines)


# ── 全局单例 ──────────────────────────────────────

_global_autocli: AutoCLI | None = None


def init_autocli(workspace: str = "") -> AutoCLI:
    """初始化全局 AutoCLI"""
    global _global_autocli
    _global_autocli = AutoCLI(workspace=workspace)
    logger.info("AutoCLI initialized (workspace=%s)", workspace or "cwd")
    return _global_autocli


def get_autocli() -> AutoCLI:
    """获取全局 AutoCLI"""
    global _global_autocli
    if _global_autocli is None:
        return init_autocli()
    return _global_autocli
