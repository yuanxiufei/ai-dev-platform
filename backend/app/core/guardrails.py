"""
Guardrails 护栏系统 — 工具调用前的授权审查

借鉴 Deer Flow GuardrailProvider + SafetyMiddleware 设计：
  1. 预工具调用授权护栏：检查工具参数/上下文是否安全
  2. 支持多种策略：文件路径白名单、敏感命令检测、网络限制
  3. 可配置的介入级别：warn → block → ask_user
  4. 单例模式 init_guardrails / get_guardrails
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("app.core.guardrails")


# ──────────────────────── 数据结构 ────────────────────────

class InterventionLevel(str, Enum):
    """护栏介入级别"""
    ALLOW = "allow"       # 允许执行
    WARN = "warn"         # 警告但允许
    ASK_USER = "ask_user" # 需要用户确认
    BLOCK = "block"       # 阻止执行


@dataclass
class GuardrailDecision:
    """护栏决策"""
    level: InterventionLevel = InterventionLevel.ALLOW
    reason: str = ""
    blocked_params: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class GuardrailConfig:
    """护栏配置"""
    enabled: bool = True
    default_level: InterventionLevel = InterventionLevel.WARN

    # ── 文件路径策略 ───────────────────────────
    file_path_whitelist: list[str] = field(default_factory=list)  # 允许的路径前缀
    file_path_blacklist: list[str] = field(default_factory=lambda: [
        "/etc/passwd", "/etc/shadow", "/etc/sudoers",
        "~/.ssh/", "~/.gnupg/", ".env", ".git/config",
        "C:\\Windows\\System32\\", "C:\\Windows\\SysWOW64\\",
    ])
    protected_extensions: list[str] = field(default_factory=lambda: [
        ".ssh", ".gnupg", ".pem", ".key", ".pfx", ".p12",
        ".env", ".secrets", ".credentials",
    ])

    # ── 命令策略 ───────────────────────────────
    sensitive_commands: list[str] = field(default_factory=lambda: [
        "rm -rf /", "rm -rf /*", "dd if=", "mkfs.",
        "shutdown", "reboot", "halt", "poweroff",
        ":(){ :|:& };:",  # fork bomb
        "chmod 777", "chown -R",
        "> /dev/sda", "> /dev/sdb",
        "wget.*| sh", "curl.*| bash",
    ])
    command_whitelist: list[str] = field(default_factory=list)

    # ── 网络策略 ───────────────────────────────
    blocked_domains: list[str] = field(default_factory=list)
    blocked_ip_ranges: list[str] = field(default_factory=list)

    # ── 大小限制 ───────────────────────────────
    max_file_size_mb: float = 100.0       # 操作文件最大大小
    max_command_length: int = 4096        # 命令最大长度


# ──────────────────────── 策略检查器 ────────────────────────

class FilePathGuard:
    """文件路径护栏"""

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config

    def check(self, file_path: str) -> GuardrailDecision:
        """检查文件路径是否安全"""
        normalized = str(Path(file_path).expanduser().resolve())

        # 黑名单检查
        for pattern in self._config.file_path_blacklist:
            if self._match_path(normalized, pattern):
                return GuardrailDecision(
                    level=InterventionLevel.BLOCK,
                    reason=f"File path blocked by blacklist: {pattern}",
                    blocked_params=[file_path],
                )

        # 受保护扩展名检查
        ext = Path(normalized).suffix
        if ext and ext.lower() in [e.lower() for e in self._config.protected_extensions]:
            return GuardrailDecision(
                level=InterventionLevel.WARN,
                reason=f"Protected file extension: {ext}",
                suggestions=["Verify this file operation is authorized"],
            )

        # 白名单检查（如果设置了白名单）
        if self._config.file_path_whitelist:
            allowed = False
            for pattern in self._config.file_path_whitelist:
                if self._match_path(normalized, pattern):
                    allowed = True
                    break
            if not allowed:
                return GuardrailDecision(
                    level=InterventionLevel.BLOCK,
                    reason="File path not in whitelist",
                    blocked_params=[file_path],
                    suggestions=["Add the path to the whitelist"],
                )

        # 大小检查
        try:
            size_mb = Path(normalized).stat().st_size / (1024 * 1024)
            if size_mb > self._config.max_file_size_mb:
                return GuardrailDecision(
                    level=InterventionLevel.WARN,
                    reason=f"File too large: {size_mb:.1f}MB > {self._config.max_file_size_mb}MB",
                )
        except OSError:
            pass  # 文件可能不存在，创建时检查

        return GuardrailDecision(level=InterventionLevel.ALLOW)

    @staticmethod
    def _match_path(path: str, pattern: str) -> bool:
        """路径模式匹配（支持通配符和主目录展开）"""
        expanded = str(Path(pattern).expanduser().resolve()) if "~" in pattern else pattern
        if expanded.endswith("/"):
            return path.startswith(expanded) or path == expanded.rstrip("/")
        if "*" in pattern or "?" in pattern:
            regex = re.escape(expanded).replace(r"\*", ".*").replace(r"\?", ".")
            return bool(re.match(f"^{regex}$", path)) or expanded in path
        return path == expanded or path.startswith(expanded + "/")


class CommandGuard:
    """命令安全护栏"""

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config
        self._compiled_sensitive = [
            re.compile(p, re.IGNORECASE) for p in config.sensitive_commands
        ]

    def check(self, command: str) -> GuardrailDecision:
        """检查命令是否安全"""
        if len(command) > self._config.max_command_length:
            return GuardrailDecision(
                level=InterventionLevel.WARN,
                reason=f"Command exceeds max length ({self._config.max_command_length} chars)",
            )

        for pattern in self._compiled_sensitive:
            if pattern.search(command):
                return GuardrailDecision(
                    level=InterventionLevel.BLOCK,
                    reason=f"Sensitive command pattern matched: {pattern.pattern}",
                    blocked_params=[command],
                    suggestions=["Refactor the command to avoid dangerous patterns"],
                )

        return GuardrailDecision(level=InterventionLevel.ALLOW)


class NetworkGuard:
    """网络安全护栏"""

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config

    def check(self, url: str) -> GuardrailDecision:
        """检查 URL/域名是否安全"""
        # 域名黑名单
        for domain in self._config.blocked_domains:
            if domain.lower() in url.lower():
                return GuardrailDecision(
                    level=InterventionLevel.BLOCK,
                    reason=f"Domain blocked: {domain}",
                    blocked_params=[url],
                )

        return GuardrailDecision(level=InterventionLevel.ALLOW)


# ──────────────────────── 护栏管理器 ────────────────────────

class GuardrailsManager:
    """护栏管理器 — 聚合所有策略检查器"""

    def __init__(self, config: GuardrailConfig | None = None) -> None:
        self._config = config or GuardrailConfig()
        self._file_guard = FilePathGuard(self._config)
        self._command_guard = CommandGuard(self._config)
        self._network_guard = NetworkGuard(self._config)

        # 自定义策略
        self._custom_guards: list[Callable[[str, dict[str, Any]], GuardrailDecision]] = []

    def register_custom_guard(
        self, guard_fn: Callable[[str, dict[str, Any]], GuardrailDecision],
    ) -> None:
        """注册自定义护栏策略"""
        self._custom_guards.append(guard_fn)

    def check_tool_call(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
    ) -> GuardrailDecision:
        """
        检查工具调用是否安全
        返回最严格的决策（BLOCK > ASK_USER > WARN > ALLOW）
        """
        if not self._config.enabled:
            return GuardrailDecision(level=InterventionLevel.ALLOW)

        decisions: list[GuardrailDecision] = []

        # 1. 文件路径检查
        for key, value in tool_params.items():
            if isinstance(value, str) and ("path" in key.lower() or "file" in key.lower() or "dir" in key.lower()):
                decisions.append(self._file_guard.check(value))

        # 2. 命令检查
        for key, value in tool_params.items():
            if isinstance(value, str) and ("command" in key.lower() or "cmd" in key.lower() or "shell" in key.lower()):
                decisions.append(self._command_guard.check(value))

        # 3. URL/域名检查
        for key, value in tool_params.items():
            if isinstance(value, str) and ("url" in key.lower() or "endpoint" in key.lower() or "host" in key.lower()):
                decisions.append(self._network_guard.check(value))

        # 4. 自定义护栏
        for guard_fn in self._custom_guards:
            try:
                d = guard_fn(tool_name, tool_params)
                if d:
                    decisions.append(d)
            except Exception as e:
                logger.warning("Custom guard check failed: %s", e)

        # 聚合所有决策，取最严格的
        if not decisions:
            return GuardrailDecision(level=InterventionLevel.ALLOW)

        level_priority: dict[InterventionLevel, int] = {
            InterventionLevel.ALLOW: 0,
            InterventionLevel.WARN: 1,
            InterventionLevel.ASK_USER: 2,
            InterventionLevel.BLOCK: 3,
        }

        strictest = max(decisions, key=lambda d: level_priority[d.level])
        return strictest

    @property
    def config(self) -> GuardrailConfig:
        return self._config


# ──────────────────────── 单例 ────────────────────────

_guardrails_manager: GuardrailsManager | None = None


def init_guardrails(config: GuardrailConfig | None = None) -> GuardrailsManager:
    """初始化护栏管理器"""
    global _guardrails_manager
    _guardrails_manager = GuardrailsManager(config)
    logger.info("GuardrailsManager initialized (%s)", "enabled" if _guardrails_manager._config.enabled else "disabled")
    return _guardrails_manager


def get_guardrails() -> GuardrailsManager:
    """获取护栏管理器单例"""
    global _guardrails_manager
    if _guardrails_manager is None:
        _guardrails_manager = GuardrailsManager()
    return _guardrails_manager
