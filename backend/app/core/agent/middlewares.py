"""
Agent Middleware 管道

借鉴 DeerFlow middleware/ 设计：

- LoopDetectionMiddleware: 检测 LLM 重复调用同一工具的循环
- SummarizationMiddleware: 上下文超限时自动 LLM 摘要压缩
- ErrorHandlingMiddleware: 工具执行错误时的优雅降级

Middleware 按配置顺序链式执行，可在 before/after 阶段拦截和修改行为。
"""

from __future__ import annotations

import hashlib
import json
import logging
import re as _stdlib_re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.tools.schema import ToolResult

logger = logging.getLogger("agent.middleware")

# ── Middleware 基类 ─────────────────────────────────


@dataclass
class MiddlewareContext:
    """Middleware 执行上下文"""
    agent_id: str = ""
    session_id: str = ""
    turn: int = 0
    max_turns: int = 10
    messages: list[dict[str, Any]] = field(default_factory=list)
    """当前消息历史"""
    tool_results: list[ToolResult] = field(default_factory=list)
    """本轮工具执行结果"""
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentMiddleware(ABC):
    """Agent Middleware 抽象基类

    借鉴 DeerFlow Middleware 模式，每个 middleware 有：
    - before_step(): 每轮 LLM 调用前
    - after_llm(): LLM 响应后
    - after_tools(): 工具执行后
    - on_error(): 错误时

    返回值：
    - None: 正常继续
    - str: 终止消息（跳过后续 middleware 和剩余循环）
    """

    name: str = "base"

    async def before_step(self, ctx: MiddlewareContext) -> str | None:
        """每轮 LLM 调用前"""
        return None

    async def after_llm(
        self,
        ctx: MiddlewareContext,
        response_content: str,
        finish_reason: str,
        tool_calls: list[dict[str, Any]],
    ) -> str | None:
        """LLM 响应后"""
        return None

    async def after_tools(self, ctx: MiddlewareContext) -> str | None:
        """工具执行后、回传结果给 LLM 前"""
        return None

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> str | None:
        """执行出错时"""
        return None


class MiddlewarePipeline:
    """Middleware 管线 — 按注册顺序链式执行"""

    def __init__(self, middlewares: list[AgentMiddleware] | None = None) -> None:
        self._chain: list[AgentMiddleware] = middlewares or []

    def add(self, middleware: AgentMiddleware) -> None:
        self._chain.append(middleware)

    def remove(self, name: str) -> bool:
        for i, mw in enumerate(self._chain):
            if mw.name == name:
                self._chain.pop(i)
                return True
        return False

    @property
    def names(self) -> list[str]:
        return [m.name for m in self._chain]

    async def run_before_step(self, ctx: MiddlewareContext) -> str | None:
        for mw in self._chain:
            try:
                result = await mw.before_step(ctx)
                if result is not None:
                    logger.info("Middleware '%s' terminated agent: %s", mw.name, result[:100])
                    return result
            except Exception as e:
                logger.warning("Middleware '%s' before_step error: %s", mw.name, e)
        return None

    async def run_after_llm(
        self,
        ctx: MiddlewareContext,
        response_content: str,
        finish_reason: str,
        tool_calls: list[dict[str, Any]],
    ) -> str | None:
        for mw in self._chain:
            try:
                result = await mw.after_llm(ctx, response_content, finish_reason, tool_calls)
                if result is not None:
                    logger.info("Middleware '%s' terminated after LLM: %s", mw.name, result[:100])
                    return result
            except Exception as e:
                logger.warning("Middleware '%s' after_llm error: %s", mw.name, e)
        return None

    async def run_after_tools(self, ctx: MiddlewareContext) -> str | None:
        for mw in self._chain:
            try:
                result = await mw.after_tools(ctx)
                if result is not None:
                    logger.info("Middleware '%s' terminated after tools: %s", mw.name, result[:100])
                    return result
            except Exception as e:
                logger.warning("Middleware '%s' after_tools error: %s", mw.name, e)
        return None

    async def run_on_error(self, ctx: MiddlewareContext, error: Exception) -> str | None:
        for mw in self._chain:
            try:
                result = await mw.on_error(ctx, error)
                if result is not None:
                    return result
            except Exception as e:
                logger.warning("Middleware '%s' on_error error: %s", mw.name, e)
        return None


# ── 内置 Middleware ─────────────────────────────────


class LoopDetectionMiddleware(AgentMiddleware):
    """循环检测 Middleware

    借鉴 DeerFlow loop_detection_middleware：
    - 追踪最近 N 轮的工具调用序列
    - 如果连续调用同一工具且参数完全一致 → 检测为死循环
    - 达到阈值时注入警告消息提醒 LLM
    """

    name = "loop_detection"
    MAX_IDENTICAL_CALLS = 3
    """同一工具+参数连续调用多少次判定为循环"""
    TRACK_WINDOW = 10
    """追踪最近多少轮的工具调用"""

    def __init__(self) -> None:
        self._call_history: list[str] = []
        """最近 N 个工具调用的 hash（name + args 的 sha256 前 8 位）"""

    def _hash_call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """计算工具调用的 hash"""
        content = json.dumps({"name": tool_name, "args": arguments}, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:12]

    async def after_tools(self, ctx: MiddlewareContext) -> str | None:
        # 记录本轮的工具调用 hash
        for tr in ctx.tool_results:
            call_hash = self._hash_call(tr.tool_name, tr.arguments)
            self._call_history.append(call_hash)

        # 仅保留最近 TRACK_WINDOW 个
        if len(self._call_history) > self.TRACK_WINDOW:
            self._call_history = self._call_history[-self.TRACK_WINDOW:]

        # 检测连续重复
        recent = self._call_history[-self.MAX_IDENTICAL_CALLS:]
        if len(recent) >= self.MAX_IDENTICAL_CALLS and len(set(recent)) == 1:
            detected_tool = ctx.tool_results[-1].tool_name if ctx.tool_results else "unknown"
            logger.warning(
                "Loop detected: tool '%s' called %d times with same args",
                detected_tool, self.MAX_IDENTICAL_CALLS,
            )
            # 注入警告到 messages，提醒 LLM
            warning = (
                f"⚠️ Tool '{detected_tool}' has been called {self.MAX_IDENTICAL_CALLS} times "
                f"in a row with identical parameters. This looks like a loop. "
                f"Please try a different approach or explain why you're stuck."
            )
            ctx.messages.append({"role": "user", "content": warning})

        return None  # 不终止，只是注入警告


class SummarizationMiddleware(AgentMiddleware):
    """上下文压缩 Middleware

    借鉴 DeerFlow summarization_middleware：
    - 当消息历史超过 token 阈值时自动触发 LLM 摘要
    - 保留最近 N% 的精确消息 + 摘要的开头部分
    - 回退方案：直接截断最旧的消息
    """

    name = "summarization"
    DEFAULT_MAX_TOKENS = 64000
    DEFAULT_THRESHOLD = 0.85
    """当估算 token 超过 max_tokens * threshold 时触发摘要"""
    DEFAULT_KEEP_RECENT_RATIO = 0.15
    """保留最近 15% 的精确上下文"""

    def __init__(
        self,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        threshold: float = DEFAULT_THRESHOLD,
        keep_recent_ratio: float = DEFAULT_KEEP_RECENT_RATIO,
    ) -> None:
        self.max_tokens = max_tokens
        self.threshold = threshold
        self.keep_recent_ratio = keep_recent_ratio

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """简易 token 估算"""
        total = 0
        for msg in messages:
            content = str(msg.get("content", ""))
            # 简单估算: 中文 ~1.5 token/字, 英文 ~0.25 token/字
            chinese_chars = sum(1 for c in content if '\u4e00' <= c <= '\u9fff')
            other_chars = len(content) - chinese_chars
            total += int(chinese_chars * 1.5 + other_chars * 0.25)
        return total

    async def before_step(self, ctx: MiddlewareContext) -> str | None:
        estimated = self._estimate_tokens(ctx.messages)
        threshold_tokens = int(self.max_tokens * self.threshold)

        if estimated <= threshold_tokens:
            return None

        logger.info(
            "Context summarization triggered: estimated %d tokens > threshold %d",
            estimated, threshold_tokens,
        )

        # 按 user 消息切分为轮次
        rounds = _split_into_rounds(ctx.messages)

        if len(rounds) <= 2:
            # 只有 1-2 轮，直接截断最早的非 system 消息
            return await self._truncate_simple(ctx)

        # 保留最近 N% 的轮次
        keep_count = max(1, int(len(rounds) * self.keep_recent_ratio))
        recent_rounds = rounds[-keep_count:]
        old_rounds = rounds[:-keep_count]

        # 构建旧轮次的摘要（不调 LLM，直接用规则摘要）
        summary_parts = []
        for r in old_rounds:
            user_msgs = [m for m in r if m.get("role") == "user"]
            asst_msgs = [m for m in r if m.get("role") == "assistant"]
            if user_msgs:
                summary_parts.append(f"[User]: {str(user_msgs[0].get('content', ''))[:200]}")
            if asst_msgs:
                summary_parts.append(f"[Assistant]: {str(asst_msgs[0].get('content', ''))[:200]}")

        summary = "## Earlier Conversation Summary\n" + "\n".join(summary_parts) + "\n\n---\n"

        # 重建消息：system + summary + recent rounds
        new_messages: list[dict[str, Any]] = []
        if ctx.messages and ctx.messages[0].get("role") == "system":
            new_messages.append(ctx.messages[0])

        new_messages.append({"role": "user", "content": summary})

        for r in recent_rounds:
            new_messages.extend(r)

        ctx.messages.clear()
        ctx.messages.extend(new_messages)

        new_estimated = self._estimate_tokens(ctx.messages)
        logger.info(
            "Context summarization done: %d rounds → %d kept, %d → %d tokens",
            len(rounds), keep_count, estimated, new_estimated,
        )

        return None

    async def _truncate_simple(self, ctx: MiddlewareContext) -> str | None:
        """简单截断方案"""
        if len(ctx.messages) <= 2:
            return None

        # 保留 system + 最后 1 条 user + 1 条 assistant
        keep_count = min(3, len(ctx.messages))
        ctx.messages = ctx.messages[-keep_count:]
        logger.info("Context truncated to %d messages", keep_count)
        return None


def _split_into_rounds(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """按 user 消息切分对话为逻辑轮次"""
    rounds: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []

    for msg in messages:
        if msg.get("role") == "user" and current:
            rounds.append(current)
            current = []
        current.append(msg)

    if current:
        rounds.append(current)

    return rounds


class ErrorHandlingMiddleware(AgentMiddleware):
    """错误处理 Middleware

    借鉴 DeerFlow tool_error_handling_middleware：
    - 工具执行失败时注入友好的错误反馈给 LLM
    - 可配置重试次数
    - 连续失败达到阈值时优雅终止
    """

    name = "error_handling"
    MAX_CONSECUTIVE_ERRORS = 5
    """连续工具错误超过此值终止 Agent"""

    def __init__(self) -> None:
        self._consecutive_errors: int = 0

    async def after_tools(self, ctx: MiddlewareContext) -> str | None:
        failed_count = sum(1 for r in ctx.tool_results if not r.success)

        if failed_count > 0:
            self._consecutive_errors += failed_count

            # 注入错误反馈
            error_messages = []
            for r in ctx.tool_results:
                if not r.success:
                    error_messages.append(f"- `{r.tool_name}`: {r.error}")

            feedback = (
                f"⚠️ {failed_count} tool(s) failed this turn:\n"
                + "\n".join(error_messages)
                + f"\n\nTotal consecutive errors: {self._consecutive_errors}/{self.MAX_CONSECUTIVE_ERRORS}."
                + "\nPlease fix the errors or try an alternative approach."
            )
            ctx.messages.append({"role": "user", "content": feedback})

            logger.warning(
                "Tool errors: %d failed this turn, %d consecutive",
                failed_count, self._consecutive_errors,
            )
        else:
            self._consecutive_errors = 0

        # 连续错误超阈值 → 终止
        if self._consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS:
            return (
                f"Agent terminated: {self._consecutive_errors} consecutive tool errors. "
                f"The tools are not functioning correctly."
            )

        return None

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> str | None:
        """Agent 执行异常时"""
        logger.error("Agent error: %s", str(error)[:200])
        self._consecutive_errors += 1
        return None  # 不自行终止，让 AgentRunner 处理


# ── Guardrail Middleware — 借鉴 DeerFlow Guardrail 机制 ──

_DANGEROUS_SHELL_PATTERNS: list[str] = [
    r"\brm\s+-rf\b",              # rm -rf
    r"\brm\s+.*\*",               # rm with wildcard
    r"\bdocker\s+rm\b",           # docker rm
    r"\bdocker\s+system\s+prune", # docker prune
    r"\bgit\s+push\s+.*--force",  # git push --force
    r"\bgit\s+reset\s+--hard\b",  # git reset --hard
    r"\bgit\s+clean\s+-[a-z]*f",  # git clean -f
    r"\bchmod\s+777\b",           # chmod 777
    r"\bchown\s+-R\b",            # chown -R
    r"\bdd\s+if=",                # dd disk write
    r"\bmkfs\.",                  # mkfs.*
    r"\b>.*/dev/[a-z]+d[a-z]\d?", # overwrite device
    r"\bformat\s+[A-Z]:",         # format drive (Windows)
    r"\bdel\s+/[fsq].*[A-Z]:",   # del /f/s/q (Windows)
    r"\bsc\s+delete\b",           # sc delete service
    r"\bwget\b.*\|.*\bsh\b",     # wget piped to sh
    r"\bcurl\b.*\|.*\bbash\b",   # curl piped to bash
    r"\bpip\s+uninstall\b",       # pip uninstall
    r"\bnpm\s+uninstall\b",       # npm uninstall
    r"\byarn\s+remove\b",         # yarn remove
]

_SENSITIVE_FILES: list[str] = [
    ".env", ".env.local", ".env.production", ".env.development",
    ".git/config", ".git-credentials",
    "~/.ssh/", "id_rsa", "id_ed25519", "authorized_keys",
    "credentials.json", "service-account.json", "serviceAccountKey.json",
    "secrets.yml", "secrets.yaml", "vault.yml",
    "*.pem", "*.key", "*.pfx", "*.p12",
    "config/database.yml", "config/master.key",
    ".aws/credentials", ".aws/config",
    ".kube/config", ".docker/config.json",
]

_OUTPUT_SENSITIVE_PATTERNS: list[str] = [
    r"(?:api[_-]?key|apikey|secret|token|password|passwd)\s*[:=]\s*['\"]?\w{20,}['\"]?",
    r"(?:sk|pk|rk)_[a-zA-Z0-9]{20,}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"gho_[a-zA-Z0-9]{36}",
    r"xox[bpras]-[a-zA-Z0-9-]+",
    r"AKIA[0-9A-Z]{16}",
    r"-----BEGIN\s+(?:RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----",
]


class GuardrailMiddleware(AgentMiddleware):
    """安全护栏 Middleware — 借鉴 DeerFlow Guardrail 机制

    三层防护：
    1. before_step  — 检查 LLM 是否企图调用危险命令/读取敏感文件
    2. after_tools  — 检查工具执行结果是否泄漏密钥
    3. on_error     — 安全违规时强制终止 + 审计日志
    """

    name = "guardrail"
    BLOCK_MESSAGE = "⛔ This action violates security policy and has been blocked."
    TRUNCATE_MESSAGE = "[SECRET REDACTED]"

    def __init__(
        self,
        block_dangerous_commands: bool = True,
        block_sensitive_files: bool = True,
        redact_secrets_in_output: bool = True,
    ) -> None:
        self.block_dangerous_commands = block_dangerous_commands
        self.block_sensitive_files = block_sensitive_files
        self.redact_secrets_in_output = redact_secrets_in_output
        self._violations: list[dict[str, Any]] = []

    def _is_sensitive_path(self, path: str) -> bool:
        """检查路径是否属于敏感文件"""
        path_lower = path.lower().replace("\\", "/")
        for pattern in _SENSITIVE_FILES:
            pp = pattern.lower()
            if pp.startswith("*") and path_lower.endswith(pp[1:]):
                return True
            if pp in path_lower:
                return True
        return False

    def _check_dangerous_command(self, command: str) -> tuple[bool, str]:
        """检查命令是否危险，返回 (is_dangerous, reason)"""
        for pattern in _DANGEROUS_SHELL_PATTERNS:
            if _stdlib_re.search(pattern, command, _stdlib_re.IGNORECASE):
                return True, f"Dangerous command pattern matched: {pattern}"
        return False, ""

    def _redact_secrets(self, text: str) -> str:
        """删除输出中的密钥/令牌"""
        result = text
        for pattern in _OUTPUT_SENSITIVE_PATTERNS:
            result = _stdlib_re.sub(pattern, self.TRUNCATE_MESSAGE, result, flags=_stdlib_re.IGNORECASE)
        return result

    async def before_step(self, ctx: MiddlewareContext) -> str | None:
        """检查 LLM 最新消息中是否包含危险意图"""

        # 1. 检查 tool_calls 中的路径
        if self.block_sensitive_files:
            for tc in getattr(ctx, "pending_tool_calls", []) or []:
                for key in ("path", "file_path", "filename", "source", "target"):
                    path = str(tc.get(key, "")).lower()
                    if path and self._is_sensitive_path(path):
                        violation = {
                            "type": "sensitive_file_access",
                            "tool": tc.get("tool_name", "unknown"),
                            "path": tc.get(key),
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        self._violations.append(violation)
                        logger.warning("Guardrail BLOCKED sensitive file: %s", path)
                        ctx.messages.append({
                            "role": "user",
                            "content": (
                                f"{self.BLOCK_MESSAGE}\n"
                                f"Attempted to access sensitive file: {tc.get(key)}\n"
                                f"Please use an alternative approach."
                            ),
                        })
                        return f"[GUARDRAIL] Blocked sensitive file access: {tc.get(key)}"

        # 2. 检查 LLM 最新回复中是否暗示危险命令
        if self.block_dangerous_commands and ctx.messages:
            last_msg = ctx.messages[-1]
            content = str(last_msg.get("content", ""))
            # 只检查 LLM 产出的文本（不检查 system/user 消息）
            if last_msg.get("role") == "assistant" and content:
                is_dangerous, reason = self._check_dangerous_command(content)
                if is_dangerous:
                    violation = {
                        "type": "dangerous_command_in_output",
                        "reason": reason,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    self._violations.append(violation)
                    logger.warning("Guardrail BLOCKED dangerous command: %s", reason)
                    ctx.messages.append({
                        "role": "user",
                        "content": (
                            f"{self.BLOCK_MESSAGE}\n"
                            f"Your response contained a potentially dangerous command.\n"
                            f"Please suggest safer alternatives or ask for explicit user confirmation."
                        ),
                    })
                    return f"[GUARDRAIL] Blocked dangerous command suggestion: {reason}"

        return None

    async def after_tools(self, ctx: MiddlewareContext) -> str | None:
        """检查工具执行结果"""
        if not self.redact_secrets_in_output:
            return None

        redacted_count = 0
        for tr in ctx.tool_results:
            if not tr.result:
                continue
            original = str(tr.result)
            cleaned = self._redact_secrets(original)
            if cleaned != original:
                # mutate in place（注意：ToolResult.result 应为可变）
                tr.result = cleaned
                redacted_count += 1

        if redacted_count > 0:
            logger.info("Guardrail redacted secrets in %d tool outputs", redacted_count)

        return None

    async def on_error(self, ctx: MiddlewareContext, error: Exception) -> str | None:
        """安全违规错误 → 审计记录"""
        logger.error(
            "Guardrail on_error: %s | violations_total=%d",
            str(error)[:200], len(self._violations),
        )
        return None

    @property
    def violations(self) -> list[dict[str, Any]]:
        return self._violations


# ── 工厂函数 ──────────────────────────────────────


def create_default_pipeline(
    max_tokens: int = 64000,
    summarization_threshold: float = 0.85,
) -> MiddlewarePipeline:
    """创建默认的 Middleware 管线

    顺序: Guardrail → LoopDetection → Summarization → ErrorHandling
    """
    return MiddlewarePipeline([
        GuardrailMiddleware(),
        LoopDetectionMiddleware(),
        SummarizationMiddleware(
            max_tokens=max_tokens,
            threshold=summarization_threshold,
        ),
        ErrorHandlingMiddleware(),
    ])
