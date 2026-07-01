"""
Context Window Manager — 智能上下文窗口管理

借鉴 SWE-agent 的上下文窗口管理设计:
- 受控文件读取 (limit + offset, 默认 100 行)
- 三层截断策略: 旧文件内容 → 旧对话历史 → 工具返回结果
- Token 估算 (按字符数快速估算, 避免调用 tokenizer 的延迟)
- 工具输出自动裁剪

核心概念:
  SmartReadConfig   — 受控读取配置 (limit, offset, hint)
  TruncationTier    — 截断层级
  ContextBudget     — Token 预算追踪

用法:
    manager = ContextWindowManager(max_tokens=128000)
    
    # 文件读取
    content = manager.smart_read(path, offset=0, limit=100)
    
    # 消息裁剪
    messages = manager.trim_messages(messages, reserve_tokens=8000)
    
    # 工具输出裁剪
    result = manager.trim_tool_output(output, max_chars=2000)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

logger = logging.getLogger("agent.context_window")


# ── 常量 ──────────────────────────────────────

# 字符到 token 的粗略换算 (中文 ~1.5 char/token, 英文 ~4 char/token)
CHARS_PER_TOKEN = 2.5
# 默认每次读取行数
DEFAULT_READ_LIMIT = 100
# 工具输出最大字符数
MAX_TOOL_OUTPUT_CHARS = 4000
# 消息缓存清理时的保留条数
MIN_MESSAGE_RETAIN = 4


# ── 数据类型 ──────────────────────────────────

class TruncationTier(IntEnum):
    """截断层级 (借鉴 SWE-agent 三层策略)"""
    NONE = 0
    """不截断"""
    TRIM_TOOL_OUTPUT = 1
    """裁剪工具输出 (保留前 MAX_TOOL_OUTPUT_CHARS 字符)"""
    TRIM_OLD_FILES = 2
    """裁剪早期文件中读取的内容"""
    SUMMARIZE_HISTORY = 3
    """压缩历史对话 (保留最近 N 条完整, 更早的做摘要)"""
    TRUNCATE_ALL = 4
    """极端截断 (仅保留 system + 最后 user message)"""


@dataclass
class ContextBudget:
    """Token 预算"""
    max_tokens: int = 128000
    used_tokens: int = 0
    reserve_tokens: int = 8000  # 预留给 LLM 回复的空间
    tiers_applied: list[TruncationTier] = field(default_factory=list)

    @property
    def available(self) -> int:
        return max(0, self.max_tokens - self.used_tokens - self.reserve_tokens)

    @property
    def usage_pct(self) -> float:
        return (self.used_tokens / self.max_tokens * 100) if self.max_tokens else 0

    def summary(self) -> dict[str, Any]:
        return {
            "max_tokens": self.max_tokens,
            "used_tokens": self.used_tokens,
            "available": self.available,
            "usage_pct": round(self.usage_pct, 1),
            "tiers_applied": [t.name for t in self.tiers_applied],
        }


@dataclass
class SmartReadResult:
    """受控文件读取结果 (借鉴 SWE-agent smart_read)"""
    path: str
    content: str
    lines_read: int
    total_lines: int
    offset: int = 0
    has_more: bool = False
    hint: str = ""

    def to_content_with_hint(self) -> str:
        """带"还有更多"提示的内容 (SWE-agent 风格)"""
        result = self.content
        if self.has_more:
            remaining = self.total_lines - self.offset - self.lines_read
            result += (
                f"\n\n... ({remaining} more lines, "
                f"use offset={self.offset + self.lines_read} to read more)"
            )
        return result


# ── ContextWindowManager ────────────────────────

class ContextWindowManager:
    """
    智能上下文窗口管理

    三层截断策略 (借鉴 SWE-agent):
      1. TRIM_TOOL_OUTPUT — 裁剪过长的工具返回
      2. TRIM_OLD_FILES   — 裁剪早期读取的文件内容 (保留最近读取的)
      3. SUMMARIZE_HISTORY— 压缩对话历史 (保留最近消息)

    用法:
        manager = ContextWindowManager(max_tokens=128000)
        messages = manager.trim_messages(messages, reserve_tokens=8000)
        content = manager.smart_read(path, offset=0, limit=100)
    """

    def __init__(self, max_tokens: int = 128000, reserve_tokens: int = 8000):
        self.budget = ContextBudget(
            max_tokens=max_tokens,
            reserve_tokens=reserve_tokens,
        )
        # 缓存已读取的文件键 → SmartReadResult
        self._file_cache: dict[str, SmartReadResult] = {}

    # ── 工具输出裁剪 (Tier 1) ─────────────────

    def trim_tool_output(self, output: str, max_chars: int = MAX_TOOL_OUTPUT_CHARS) -> str:
        """
        裁剪过长的工具输出 (借鉴 SWE-agent ACI 设计)

        策略: 保留前 70% + 后 20% + 中间省略提示
        如果输出不超过限制，原样返回。
        """
        if len(output) <= max_chars:
            return output

        front_size = int(max_chars * 0.7)
        back_size = int(max_chars * 0.2)
        skipped = len(output) - front_size - back_size

        trimmed = (
            output[:front_size]
            + f"\n\n... ({skipped:,} chars omitted) ...\n\n"
            + output[-back_size:]
        )
        logger.debug(
            "Tool output trimmed: %d → %d chars (-%.0f%%)",
            len(output), len(trimmed),
            (1 - len(trimmed) / max(1, len(output))) * 100,
        )
        return trimmed

    # ── 受控文件读取 (Tier 2) ─────────────────

    def smart_read(
        self,
        path: str,
        content: str,
        offset: int = 0,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> SmartReadResult:
        """
        受控文件读取 (借鉴 SWE-agent smart_read)

        每次默认只返回 100 行，末尾提示还有更多。
        结果缓存到 _file_cache 供后续截断策略使用。
        """
        lines = content.split("\n")
        total_lines = len(lines)

        # 切片
        end = min(offset + limit, total_lines)
        selected = lines[offset:end]

        # 带行号的输出
        numbered = "\n".join(
            f"{i + offset + 1}: {line}" for i, line in enumerate(selected)
        )

        result = SmartReadResult(
            path=path,
            content=numbered,
            lines_read=len(selected),
            total_lines=total_lines,
            offset=offset,
            has_more=(end < total_lines),
        )

        # 缓存
        cache_key = f"{path}:{offset}:{limit}"
        self._file_cache[cache_key] = result

        logger.debug(
            "Smart read '%s': lines %d-%d/%d (has_more=%s)",
            path, offset + 1, end, total_lines, result.has_more,
        )
        return result

    # ── 消息裁剪 (Tier 3) ─────────────────────

    def trim_messages(
        self,
        messages: list[dict[str, Any]],
        reserve_tokens: int | None = None,
        min_retain: int = MIN_MESSAGE_RETAIN,
    ) -> tuple[list[dict[str, Any]], ContextBudget]:
        """
        裁剪消息列表以适应上下文窗口 (借鉴 SWE-agent ContextWindowManager)

        策略:
          1. 估算总 token 数
          2. 如果超出 → Tier 1: 裁剪工具返回结果
          3. 如果仍超出 → Tier 2: 移除最早的文件读取内容
          4. 如果仍超出 → Tier 3: 保留 system + 最近 N 条消息

        返回 (裁剪后的消息, 更新后的预算)
        """
        reserve = reserve_tokens or self.budget.reserve_tokens
        self.budget.tiers_applied = []

        if not messages:
            return messages, self.budget

        # 估算 token
        estimated = self._estimate_tokens(messages)
        self.budget.used_tokens = estimated

        if estimated <= self.budget.available:
            return messages, self.budget

        logger.warning(
            "Context window overflow: %d tokens used, %d available (%d max)",
            estimated, self.budget.available, self.budget.max_tokens,
        )

        trimmed = list(messages)

        # Tier 1: 裁剪工具输出
        trimmed = self._trim_tool_outputs_in_messages(trimmed)
        estimated = self._estimate_tokens(trimmed)
        if estimated <= self.budget.available:
            self.budget.tiers_applied.append(TruncationTier.TRIM_TOOL_OUTPUT)
            self.budget.used_tokens = estimated
            logger.info("Context trimmed via Tier 1: %d tokens", estimated)
            return trimmed, self.budget

        # Tier 2: 移除早期文件内容
        trimmed = self._trim_old_file_contents(trimmed, min_retain)
        estimated = self._estimate_tokens(trimmed)
        if estimated <= self.budget.available:
            self.budget.tiers_applied.append(TruncationTier.TRIM_OLD_FILES)
            self.budget.used_tokens = estimated
            logger.info("Context trimmed via Tier 2: %d tokens", estimated)
            return trimmed, self.budget

        # Tier 3: 保留 system + 最近 N 条
        trimmed = self._summarize_history(trimmed, min_retain)
        self.budget.tiers_applied.append(TruncationTier.SUMMARIZE_HISTORY)
        self.budget.used_tokens = self._estimate_tokens(trimmed)
        logger.info("Context trimmed via Tier 3: %d tokens", self.budget.used_tokens)

        return trimmed, self.budget

    # ── 辅助方法 ──────────────────────────────

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算消息列表占用的 token 数 (字符数 / CHARS_PER_TOKEN)"""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                # 多模态格式 (如 [{"type": "text", "text": "..."}])
                for part in content:
                    if isinstance(part, dict):
                        total_chars += len(part.get("text", ""))
        return int(total_chars / CHARS_PER_TOKEN)

    def _trim_tool_outputs_in_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Tier 1: 裁剪消息中的过长工具返回结果"""
        result: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and msg.get("role") == "tool":
                trimmed = self.trim_tool_output(content)
                result.append({**msg, "content": trimmed})
            else:
                result.append(msg)
        return result

    def _trim_old_file_contents(
        self,
        messages: list[dict[str, Any]],
        min_retain: int,
    ) -> list[dict[str, Any]]:
        """Tier 2: 移除早期读取的文件内容 (保留最近的消息)"""
        if len(messages) <= min_retain:
            return messages

        # 保留 system + 最近的消息
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        # 对非 system 消息，跳过带大量文件内容的消息
        trimmed_others: list[dict[str, Any]] = []
        for msg in other_msgs:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 5000:
                # 超长内容 → 保留摘要
                trimmed_others.append({
                    **msg,
                    "content": content[:2000] + f"\n... ({len(content) - 2000} chars trimmed)...",
                })
            else:
                trimmed_others.append(msg)

        return system_msgs + trimmed_others[-(len(trimmed_others) - len(system_msgs)):]

    def _summarize_history(
        self,
        messages: list[dict[str, Any]],
        min_retain: int,
    ) -> list[dict[str, Any]]:
        """Tier 3: 保留 system + 最近 N 条消息, 早期消息做标记"""
        system_msgs = [m for m in messages if m.get("role") == "system"]
        other_msgs = [m for m in messages if m.get("role") != "system"]

        if len(other_msgs) <= min_retain:
            return messages

        # 保留最近 min_retain 条
        recent = other_msgs[-min_retain:]
        skipped = len(other_msgs) - min_retain

        # 添加省略标记
        summary_msg = {
            "role": "system",
            "content": (
                f"[Context compressed: {skipped} earlier messages were truncated "
                f"to stay within token limits. Key context has been preserved.]"
            ),
        }

        return system_msgs + [summary_msg] + recent

    def get_budget_summary(self) -> dict[str, Any]:
        """获取预算使用摘要"""
        return self.budget.summary()


# ── 全局单例 ──────────────────────────────────

_global_context_manager: ContextWindowManager | None = None


def init_context_manager(
    max_tokens: int = 128000,
    reserve_tokens: int = 8000,
) -> ContextWindowManager:
    """初始化全局上下文管理器"""
    global _global_context_manager
    _global_context_manager = ContextWindowManager(
        max_tokens=max_tokens,
        reserve_tokens=reserve_tokens,
    )
    logger.info(
        "ContextWindowManager initialized: max=%d, reserve=%d",
        max_tokens, reserve_tokens,
    )
    return _global_context_manager


def get_context_manager() -> ContextWindowManager:
    """获取全局上下文管理器"""
    global _global_context_manager
    if _global_context_manager is None:
        return init_context_manager()
    return _global_context_manager
