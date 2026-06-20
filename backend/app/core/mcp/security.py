"""
MCP 安全验证 —— 命令白名单 + Shell 注入防护 + 参数安全

借鉴 AstrBot MCP Client 安全机制:
1. 命令白名单: 只允许安全的运行时（python/node/npx 等）
2. 命令黑名单: 永远禁止 shell 解释器和危险命令
3. Shell 元字符检测: 阻止注入攻击
4. 参数级别验证: 禁止内联执行标志
5. Docker 危险参数拦截: 防止容器逃逸
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path, PureWindowsPath
from typing import Any

logger = logging.getLogger("mcp.security")

# ── Shell 元字符正则 ─────────────────────────────────────────

_SHELL_META_RE = re.compile(r"[\r\n\x00;&|<>`$]")


# ── 默认命令白名单 ──────────────────────────────────────────

_DEFAULT_STDIO_COMMAND_ALLOWLIST: frozenset[str] = frozenset({
    "python", "python3", "py",
    "node", "npx", "npm", "pnpm", "yarn",
    "bun", "bunx", "deno",
    "uv", "uvx",
})


# ── 命令黑名单（永不解除） ──────────────────────────────────

_DENIED_STDIO_COMMANDS: frozenset[str] = frozenset({
    # Shell 解释器
    "bash", "sh", "zsh", "fish", "cmd", "cmd.exe",
    "powershell", "powershell.exe", "pwsh", "pwsh.exe",
    # 脚本执行
    "osascript",
    # 文件/URL 操作
    "open", "curl", "wget",
    # 网络工具
    "nc", "netcat", "telnet", "ssh", "scp",
    # 文件系统危险操作
    "rm", "mv", "cp", "dd", "mkfs",
    # 权限提升
    "sudo", "su", "chmod", "chown",
    # 进程终止
    "kill", "killall",
    # 系统关机
    "shutdown", "reboot", "poweroff", "halt",
})


# ── Docker 危险参数 ──────────────────────────────────────────

_DENIED_DOCKER_ARGS: frozenset[str] = frozenset({
    "--privileged",
    "--pid=host", "--network=host", "--net=host", "--ipc=host",
})

# Docker 不带值的参数名（需要检查下一个参数）
_DENIED_DOCKER_ARG_NAMES: frozenset[str] = frozenset({
    "--pid", "--network", "--net", "--ipc",
})


# ── Python/JS 危险标志 ──────────────────────────────────────

_DENIED_PYTHON_FLAGS: frozenset[str] = frozenset({"-c", "-m popen"})
_DENIED_JS_FLAGS: frozenset[str] = frozenset({"-e", "--eval", "-p", "--print"})


# ── 验证函数 ────────────────────────────────────────────────


def validate_mcp_stdio_config(
    command: str,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    allowlist_override: list[str] | None = None,
) -> list[str]:
    """
    验证 MCP Stdio 配置的安全性

    Args:
        command: 要执行的命令
        args: 命令参数
        env: 环境变量
        allowlist_override: 覆盖默认白名单（通过环境变量注入）

    Returns:
        空列表 = 安全，非空 = 错误信息列表

    Raises:
        不抛异常，始终返回错误列表
    """
    errors: list[str] = []

    if not isinstance(command, str) or not command.strip():
        errors.append("Command must be a non-empty string")
        return errors

    # 1. Shell 元字符检测
    if _SHELL_META_RE.search(command):
        errors.append(
            f"Command contains shell metacharacters: "
            f"{_SHELL_META_RE.findall(command)}"
        )

    # 2. 规范化命令名
    normalized = _normalize_command_name(command)

    # 3. 黑名单检查（先于白名单）
    if normalized in _DENIED_STDIO_COMMANDS:
        errors.append(
            f"Command '{normalized}' is permanently denied (dangerous command)"
        )

    # 4. 白名单检查
    allowlist = _get_allowlist(allowlist_override)
    if normalized not in allowlist:
        errors.append(
            f"Command '{normalized}' is not in the allowlist. "
            f"Allowed: {sorted(allowlist)}"
        )

    # 5. 参数安全检查
    if args and isinstance(args, list):
        arg_errors = _validate_stdio_args(command, args)
        errors.extend(arg_errors)

    # 6. 环境变量类型检查
    if env is not None:
        if not isinstance(env, dict):
            errors.append("env must be a dict or None")
        else:
            for k, v in env.items():
                if not isinstance(k, str):
                    errors.append(f"env key must be str, got {type(k).__name__}: {k}")
                if not isinstance(v, str):
                    errors.append(f"env value must be str, got {type(v).__name__}: {k}={v}")

    return errors


def validate_mcp_command_safe(command: str) -> bool:
    """快速检查命令是否安全（不检查 args）"""
    errors = validate_mcp_stdio_config(command, args=[], env=None)
    return len(errors) == 0


# ── 内部辅助 ────────────────────────────────────────────────


def _normalize_command_name(command: str) -> str:
    """规范化命令名"""
    cmd = command.strip()

    # 去除路径，提取纯文件名
    try:
        cmd = PureWindowsPath(cmd).name
    except Exception:
        pass

    try:
        cmd = Path(cmd).name
    except Exception:
        pass

    # 去除可执行文件后缀
    for ext in (".exe", ".cmd", ".bat"):
        if cmd.lower().endswith(ext):
            cmd = cmd[:-len(ext)]

    return cmd.lower()


def _get_allowlist(override: list[str] | None = None) -> frozenset[str]:
    """获取命令白名单"""
    if override:
        return frozenset(_normalize_command_name(c) for c in override if c.strip())

    env_override = os.getenv("MCP_STDIO_ALLOWED_COMMANDS", "")
    if env_override:
        commands = [c.strip() for c in env_override.split(",") if c.strip()]
        if commands:
            return frozenset(_normalize_command_name(c) for c in commands)

    return _DEFAULT_STDIO_COMMAND_ALLOWLIST


def _validate_stdio_args(command: str, args: list[str]) -> list[str]:
    """验证命令行参数的安全性"""
    errors: list[str] = []
    normalized = _normalize_command_name(command)

    # 控制字符检测
    for i, arg in enumerate(args):
        if not isinstance(arg, str):
            errors.append(f"Arg[{i}] must be str, got {type(arg).__name__}")
            continue
        if "\x00" in arg or "\r" in arg or "\n" in arg:
            errors.append(f"Arg[{i}] contains control characters")

    # Python 内联代码拦截
    if normalized in ("python", "python3", "py"):
        for i, arg in enumerate(args):
            arg_lower = arg.lower()
            if arg_lower in _DENIED_PYTHON_FLAGS or arg_lower == "-c":
                errors.append(
                    f"Arg[{i}]='{arg}': inline Python execution (-c) is forbidden. "
                    "MCP servers must be started from modules or scripts."
                )
            # 检查单破折号短标志包含 c
            if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:]:
                errors.append(
                    f"Arg[{i}]='{arg}': inline Python execution flags forbidden"
                )

    # JavaScript 内联执行拦截
    if normalized in ("node", "deno", "bun"):
        for i, arg in enumerate(args):
            arg_lower = arg.lower()
            if arg_lower in _DENIED_JS_FLAGS:
                errors.append(
                    f"Arg[{i}]='{arg}': inline JS execution is forbidden. "
                    "MCP servers must be started from packages or scripts."
                )
            if arg_lower == "eval":
                errors.append(
                    f"Arg[{i}]='eval': eval parameter is forbidden"
                )
            if arg.startswith("-") and not arg.startswith("--"):
                short = arg[1:]
                if "e" in short or "p" in short:
                    errors.append(
                        f"Arg[{i}]='{arg}': inline JS execution flags forbidden"
                    )

    # Docker 危险参数拦截
    if normalized == "docker":
        for i, arg in enumerate(args):
            if arg in _DENIED_DOCKER_ARGS:
                errors.append(
                    f"Arg[{i}]='{arg}': dangerous Docker parameter is forbidden"
                )
        for i, arg in enumerate(args):
            if arg in _DENIED_DOCKER_ARG_NAMES:
                if i + 1 < len(args) and args[i + 1] == "host":
                    errors.append(
                        f"Args[{i}:{i+1}]='{arg} {args[i+1]}': "
                        "dangerous Docker host sharing is forbidden"
                    )

    return errors


# ── 安全 URL 验证 ──────────────────────────────────────────


_SAFE_URL_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_BLOCKED_HOSTS: frozenset[str] = frozenset({
    "localhost", "127.0.0.1", "0.0.0.0",
    "169.254.0.0/16", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
})


def validate_mcp_url(url: str) -> list[str]:
    """
    验证 MCP HTTP 连接的安全性

    Args:
        url: MCP 服务器的 URL

    Returns:
        错误信息列表（空 = 安全）
    """
    errors: list[str] = []

    if not url:
        errors.append("URL must not be empty")
        return errors

    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)

        if parsed.scheme.lower() not in _SAFE_URL_SCHEMES:
            errors.append(
                f"URL scheme '{parsed.scheme}' not allowed. "
                f"Only {sorted(_SAFE_URL_SCHEMES)} are supported."
            )

        if parsed.hostname and parsed.hostname in ("localhost", "127.0.0.1"):
            logger.warning(
                "MCP URL points to localhost: %s (ensure this is intentional)", url
            )

    except Exception as e:
        errors.append(f"Invalid URL: {e}")

    return errors


# ── 完整配置验证 ────────────────────────────────────────────


def validate_mcp_server_config(config: dict[str, Any]) -> list[str]:
    """
    验证完整的 MCP 服务器配置

    Args:
        config: MCP 服务器配置字典

    Returns:
        错误信息列表
    """
    errors: list[str] = []

    name = config.get("name", "unknown")
    transport = config.get("transport", "sse")

    if not config.get("name"):
        errors.append("Server 'name' is required")

    if transport == "stdio":
        command = config.get("command", "")
        args = config.get("args", [])
        env = config.get("env", None)
        stdio_errors = validate_mcp_stdio_config(command, args, env)
        for e in stdio_errors:
            errors.append(f"[{name}] {e}")

    elif transport in ("sse", "streamable_http"):
        url = config.get("url", "")
        url_errors = validate_mcp_url(url)
        for e in url_errors:
            errors.append(f"[{name}] {e}")

    return errors
