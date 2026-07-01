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
- Sandbox 文件系统隔离 (Session 09: 打通 AutoCLI ↔ Sandbox)
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
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.sandbox.base import Sandbox

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

    Session 09 增强:
        - 注入 Sandbox 实例，将路径验证和命令执行委托给 Sandbox
        - 当 sandbox 可用时，_sandbox_paths() 通过 sandbox.validate_path() 验证
        - 可选 delegation: 将执行委托给 Sandbox.execute_command()
    """

    def __init__(
        self,
        workspace: str = "",
        max_output_chars: int = 8000,
        default_timeout: float = 30.0,
        allowed_level: SecurityLevel = SecurityLevel.SYSTEM,
        sandbox: "Sandbox | None" = None,
        delegate_to_sandbox: bool = False,
    ):
        self._workspace = str(Path(workspace).resolve()) if workspace else ""
        self._max_output = max_output_chars
        self._timeout = default_timeout
        self._allowed_level = allowed_level
        self._sandbox = sandbox
        self._delegate = delegate_to_sandbox

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
            result = CommandResult(
                command=command,
                stdout="",
                stderr=security["reason"],
                exit_code=-1,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
            )
            self._log_to_tracedb(result)
            return result

        # 沙箱化路径（如果设置了 workspace 且有 sandbox）
        safe_command = command
        if self._workspace:
            safe_command = self._sandbox_paths(command)

        # Session 09: 当 delegate_to_sandbox=True 时委托给 Sandbox 执行
        timeout_val = timeout or self._timeout
        if self._delegate and self._sandbox is not None:
            return await self._execute_via_sandbox(
                command=safe_command,
                original_command=command,
                security=security,
                timeout=timeout_val,
                start=start,
            )

        try:
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

            result = CommandResult(
                command=command,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
                truncated=stdout_truncated,
            )
            self._log_to_tracedb(result)
            return result

        except asyncio.TimeoutError:
            result = CommandResult(
                command=command,
                stdout="",
                stderr=f"Command timed out after {timeout_val}s",
                exit_code=-1,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
            )
            self._log_to_tracedb(result)
            return result
        except Exception as e:
            result = CommandResult(
                command=command,
                stdout="",
                stderr=f"Execution error: {e}",
                exit_code=-1,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
            )
            self._log_to_tracedb(result)
            return result

    async def _execute_via_sandbox(
        self,
        command: str,
        original_command: str,
        security: dict[str, Any],
        timeout: float,
        start: float,
    ) -> CommandResult:
        """Session 09: 通过 Sandbox 执行命令（统一安全层）"""
        try:
            sandbox_result = await asyncio.wait_for(
                self._sandbox.execute_command(command),  # type: ignore[union-attr]
                timeout=timeout,
            )
            stdout_truncated = False
            stdout = sandbox_result.stdout
            if len(stdout) > self._max_output:
                stdout = stdout[:self._max_output] + "\n... [truncated]"
                stdout_truncated = True

            result = CommandResult(
                command=original_command,
                stdout=stdout,
                stderr=sandbox_result.stderr,
                exit_code=sandbox_result.exit_code,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
                truncated=stdout_truncated or sandbox_result.truncated,
            )
            self._log_to_tracedb(result)
            return result
        except asyncio.TimeoutError:
            return self._timeout_result(original_command, timeout, security, start)
        except PermissionError as e:
            result = CommandResult(
                command=original_command,
                stdout="",
                stderr=f"Sandbox blocked: {e}",
                exit_code=-1,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
            )
            self._log_to_tracedb(result)
            return result
        except Exception as e:
            result = CommandResult(
                command=original_command,
                stdout="",
                stderr=f"Sandbox execution error: {e}",
                exit_code=-1,
                latency_ms=(time.perf_counter() - start) * 1000,
                security_level=security["level"],
            )
            self._log_to_tracedb(result)
            return result

    def _timeout_result(
        self, command: str, timeout: float, security: dict, start: float
    ) -> CommandResult:
        return CommandResult(
            command=command, stdout="",
            stderr=f"Command timed out after {timeout}s",
            exit_code=-1,
            latency_ms=(time.perf_counter() - start) * 1000,
            security_level=security["level"],
        )

    def _log_to_tracedb(self, result: CommandResult) -> None:
        """P2.9: 将 CLI 执行记录持久化到 JSONL 日志文件"""
        try:
            import json as _json
            log_entry = _json.dumps({
                "command": result.command,
                "exit_code": result.exit_code,
                "stdout_preview": result.stdout[:500] if result.stdout else "",
                "stderr_preview": result.stderr[:500] if result.stderr else "",
                "latency_ms": round(result.latency_ms),
                "security_level": result.security_level.value,
                "truncated": result.truncated,
                "workspace": self._workspace,
                "timestamp": time.time(),
            }, ensure_ascii=False) + "\n"

            log_dir = Path("data")
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / "cli_history.jsonl", "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception:
            pass  # 日志写入失败时静默跳过

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
        """将命令中的路径限制在 workspace 内。

        Session 09: 当沙箱可用时，通过 sandbox.validate_path() 验证每个路径参数；
        不可用时回退到基本路径拼接。
        """
        if not self._workspace:
            return command

        try:
            parts = shlex.split(command)
        except ValueError:
            # 解析失败则原样返回（安全检查层会拦截）
            return command

        if not parts:
            return command

        modified = False
        for i, arg in enumerate(parts):
            if not self._looks_like_path(arg):
                continue

            # 跳过显式选项（如 -o output、--output=file 的值）
            if i > 0 and parts[i - 1].startswith("-"):
                continue

            try:
                if self._sandbox is not None:
                    # Session 09: 委托给沙箱验证路径
                    translated = self._sandbox.validate_path(arg)
                    if translated != arg:
                        parts[i] = translated
                        modified = True
                else:
                    # 无沙箱时：工作区内路径限制
                    from pathlib import Path as _Path
                    p = _Path(arg)
                    if not p.is_absolute():
                        p = _Path(self._workspace) / p
                    resolved = str(p.resolve())
                    # 只允许 workspace 内的路径
                    workspace_abs = _Path(self._workspace).resolve()
                    if resolved.startswith(str(workspace_abs)):
                        if resolved != arg:
                            parts[i] = resolved
                            modified = True
                    else:
                        logger.warning(
                            "Path '%s' outside workspace '%s' — blocked",
                            arg, self._workspace,
                        )
                        parts[i] = str(workspace_abs)
                        modified = True
            except PermissionError:
                logger.warning("Path '%s' denied by sandbox — keeping original", arg)
            except Exception:
                pass

        if not modified:
            return command

        # 用 shlex.join 重建命令（Python 3.8+）
        try:
            return shlex.join(parts)  # type: ignore[attr-defined]
        except AttributeError:
            # Python < 3.8 回退
            return " ".join(
                shlex.quote(p) for p in parts
            )

    @staticmethod
    def _looks_like_path(arg: str) -> bool:
        """判断参数是否看起来像文件系统路径。"""
        if not arg or len(arg) < 1:
            return False
        # 绝对路径
        if arg.startswith("/") or (len(arg) > 2 and arg[1] == ":" and arg[2] in "/\\"):
            return True
        # 相对路径
        if arg.startswith("./") or arg.startswith("../") or arg.startswith(".\\"):
            return True
        # 包含路径分隔符但不含协议前缀
        if "/" in arg and "://" not in arg:
            return True
        return False

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


def init_autocli(
    workspace: str = "",
    sandbox: "Sandbox | None" = None,
    delegate_to_sandbox: bool = False,
) -> AutoCLI:
    """初始化全局 AutoCLI。

    Session 09: 可选注入 Sandbox 实例实现统一安全层。
    若未提供 sandbox，尝试从全局单例获取。
    """
    global _global_autocli

    # 自动连接全局 Sandbox 单例（若可用）
    if sandbox is None:
        try:
            from app.core.sandbox import get_sandbox as _get_sandbox
            sandbox = _get_sandbox()
        except Exception:
            pass

    _global_autocli = AutoCLI(
        workspace=workspace,
        sandbox=sandbox,
        delegate_to_sandbox=delegate_to_sandbox,
    )
    logger.info(
        "AutoCLI initialized (workspace=%s, sandbox=%s, delegate=%s)",
        workspace or "cwd",
        type(sandbox).__name__ if sandbox else "none",
        delegate_to_sandbox,
    )
    return _global_autocli


def get_autocli() -> AutoCLI:
    """获取全局 AutoCLI"""
    global _global_autocli
    if _global_autocli is None:
        return init_autocli()
    return _global_autocli
