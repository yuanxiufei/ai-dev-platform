"""
对话上下文压缩器 — LLM 摘要压缩 + 轮次截断

借鉴 AstrBot agent/context 的压缩策略：
- TruncateByTurnsCompressor: 按轮次截断最早的消息
- LLMSummaryCompressor: 用 LLM 摘要旧轮次，保留最近精确上下文
- ContextConfig: 压缩配置 dataclass
- 两种压缩器自动回退（LLM 失败 → 轮次截断）

核心算法：
1. 按 user 消息切分对话为轮次（rounds）
2. LLM 压缩：保留 15% token 预算的最近精确上下文，其余用 LLM 摘要
3. 轮次截断：直接删除最早 N 轮
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

logger = logging.getLogger("agent.context_compressor")

if TYPE_CHECKING:
    from app.core.model_router import ModelRouter


# ── Token 估算器 ──────────────────────────────────────────


class EstimateTokenCounter:
    """简易 Token 估算器 — 按字符数估算（中文 ~1.5 token/字，英文 ~0.25 token/字）"""

    def count_tokens(self, messages: list[dict[str, Any]]) -> int:
        """估算消息列表的总 token 数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "") or ""
            total += self._estimate(content)
        return max(total, 1)

    @staticmethod
    def _estimate(text: str) -> int:
        """按字符比例估算 token 数"""
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars * 1.5 + other_chars * 0.25)


# ── 对话轮次工具 ──────────────────────────────────────────


def split_into_rounds(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """将扁平的对话列表切分为逻辑轮次

    每轮以 user 消息开始，包含后续 assistant/tool 消息，直到下一个 user。
    """
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


def rounds_to_text(rounds: list[list[dict[str, Any]]]) -> str:
    """将轮次渲染为纯文本（供 LLM 摘要）"""
    lines: list[str] = []
    for i, rnd in enumerate(rounds, 1):
        lines.append(f"--- Round {i} ---")
        for seg in rnd:
            role = seg.get("role", "?")
            content = seg.get("content", "") or "[tool_calls]" if seg.get("tool_calls") else ""
            if isinstance(content, list):
                content = str(content)
            lines.append(f"[{role}] {content}")
    return "\n".join(lines)


def _extract_system_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """提取前置 system 消息"""
    result = []
    for msg in messages:
        if msg.get("role") == "system":
            result.append(msg)
        else:
            break
    return result


# ── 上下文截断器 ──────────────────────────────────────────


class ContextTruncator:
    """上下文轮次截断器"""

    @staticmethod
    def truncate_by_dropping_oldest_turns(
        messages: list[dict[str, Any]],
        drop_turns: int = 1,
    ) -> list[dict[str, Any]]:
        """删除最早 N 轮对话"""
        if drop_turns <= 0:
            return messages

        system_msgs = _extract_system_messages(messages)
        non_system = messages[len(system_msgs):]

        # 找到需要保留的起始位置（每轮 = user + assistant）
        drop_count = drop_turns * 2
        if len(non_system) <= drop_count:
            return system_msgs

        truncated = non_system[drop_count:]

        # 确保第一条非 system 消息是 user
        while truncated and truncated[0].get("role") != "user":
            truncated = truncated[1:]

        return system_msgs + truncated

    @staticmethod
    def truncate_by_turns(
        messages: list[dict[str, Any]],
        keep_most_recent_turns: int,
    ) -> list[dict[str, Any]]:
        """保留最近 N 轮"""
        if keep_most_recent_turns <= 0 or keep_most_recent_turns == -1:
            return messages

        system_msgs = _extract_system_messages(messages)
        non_system = messages[len(system_msgs):]

        if len(non_system) // 2 <= keep_most_recent_turns:
            return messages

        truncated = non_system[-(keep_most_recent_turns * 2):]

        # 确保第一条非 system 消息是 user
        while truncated and truncated[0].get("role") != "user":
            truncated = truncated[1:]

        return system_msgs + truncated


# ── 压缩协议 ──────────────────────────────────────────────


@runtime_checkable
class ContextCompressor(Protocol):
    """上下文压缩器协议"""

    def should_compress(
        self, messages: list[dict[str, Any]], current_tokens: int, max_tokens: int,
    ) -> bool:
        """判断是否需要压缩"""
        ...

    async def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """执行压缩"""
        ...


# ── 轮次截断压缩器 ────────────────────────────────────────


class TruncateByTurnsCompressor:
    """按轮次截断压缩器 — 最简单的方式：删除最早轮次"""

    def __init__(
        self,
        truncate_turns: int = 2,
        compression_threshold: float = 0.82,
    ) -> None:
        self.truncate_turns = truncate_turns
        self.compression_threshold = compression_threshold

    def should_compress(
        self, messages: list[dict[str, Any]], current_tokens: int, max_tokens: int,
    ) -> bool:
        if max_tokens <= 0 or current_tokens <= 0:
            return False
        return (current_tokens / max_tokens) > self.compression_threshold

    async def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        truncator = ContextTruncator()
        return truncator.truncate_by_dropping_oldest_turns(
            messages, drop_turns=self.truncate_turns,
        )


# ── LLM 摘要压缩器 ────────────────────────────────────────


class LLMSummaryCompressor:
    """LLM 摘要压缩器

    核心策略：
    1. 保留 15% token 预算的最近精确上下文
    2. 其余旧轮次交给 LLM 生成摘要
    3. LLM 失败时返回原消息（调用方应回退到 TruncateByTurns）
    """

    SUMMARY_INSTRUCTION = (
        "Based on our full conversation history, produce a concise summary of key "
        "takeaways and project progress.\n"
        "The primary goal is to enable seamless continuation of the work that follows.\n"
        "1. Cover all core topics discussed and the final conclusion for each.\n"
        "2. Keep the summary concise. Focus on what can help continue the work.\n"
        "3. If there was an initial user goal, state it first and describe progress.\n"
        "4. Write the summary in the user's language.\n"
        "Respond ONLY with the summary content."
    )

    TASK_CONTINUATION = (
        "If a task appears to be in progress, end the summary with the latest "
        "known result and the concrete next step to continue the task."
    )

    def __init__(
        self,
        router: "ModelRouter | None" = None,
        keep_recent_ratio: float = 0.15,
        instruction_text: str | None = None,
        compression_threshold: float = 0.82,
        token_counter: EstimateTokenCounter | None = None,
    ) -> None:
        self.router = router
        self.keep_recent_ratio = min(max(float(keep_recent_ratio), 0.0), 0.3)
        self.compression_threshold = compression_threshold
        self.token_counter = token_counter or EstimateTokenCounter()
        self.instruction_text = instruction_text or self.SUMMARY_INSTRUCTION

    def should_compress(
        self, messages: list[dict[str, Any]], current_tokens: int, max_tokens: int,
    ) -> bool:
        if max_tokens <= 0 or current_tokens <= 0:
            return False
        return (current_tokens / max_tokens) > self.compression_threshold

    def _split_recent_rounds_by_token_ratio(
        self,
        rounds: list[list[dict[str, Any]]],
        total_tokens: int,
    ) -> tuple[list[list[dict[str, Any]]], list[list[dict[str, Any]]]]:
        """按 token 比例分割旧轮次和最近轮次"""
        if not rounds or self.keep_recent_ratio <= 0 or total_tokens <= 0:
            return rounds, []

        budget = max(1, int(total_tokens * self.keep_recent_ratio))
        used = 0
        recent_start = len(rounds)

        for idx in range(len(rounds) - 1, -1, -1):
            round_tokens = self.token_counter.count_tokens(rounds[idx])
            if used > 0 and used + round_tokens > budget:
                break
            used += round_tokens
            recent_start = idx

        return rounds[:recent_start], rounds[recent_start:]

    async def __call__(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """使用 LLM 生成对话摘要"""
        rounds = split_into_rounds(messages)
        message_rounds = [[seg for seg in rnd] for rnd in rounds]
        total_tokens = self.token_counter.count_tokens(messages)
        old_rounds, recent_rounds = self._split_recent_rounds_by_token_ratio(
            message_rounds, total_tokens,
        )

        # 确保最新的 user 消息始终保留在 recent 中
        if messages and messages[-1].get("role") == "user" and old_rounds:
            latest_old = old_rounds[-1]
            if latest_old and latest_old[-1] is messages[-1]:
                old_rounds = old_rounds[:-1]
                recent_rounds = [latest_old, *recent_rounds]

        if not old_rounds:
            return messages

        # 构建摘要请求
        summary_contexts = [msg for rnd in old_rounds for msg in rnd]
        if not any(msg.get("role") != "system" for msg in summary_contexts):
            return messages

        if summary_contexts[-1].get("role") != "assistant":
            summary_contexts.append({
                "role": "assistant",
                "content": "Acknowledged.",
            })

        summary_contexts.append({
            "role": "user",
            "content": (
                "Generate a summary of our previous conversation history.\n"
                f"<instruction>\n{self.instruction_text}\n{self.TASK_CONTINUATION}\n</instruction>\n"
                "Respond ONLY with the summary content."
            ),
        })

        if not self.router:
            logger.warning("LLMSummaryCompressor: no router configured, returning original")
            return messages

        # 调用 LLM 生成摘要
        try:
            from app.core.model_router import ModelCapability, ModelRequest

            request = ModelRequest(
                prompt=summary_contexts[-1]["content"],
                capability=ModelCapability.CODE_GENERATION,
                context=summary_contexts[:-1],
            )
            response = await self.router.generate(request)
            summary_content = (response.content or "").strip()
        except Exception as e:
            logger.error("LLMSummaryCompressor: summary generation failed: %s", e)
            return messages

        if not summary_content:
            logger.warning("LLMSummaryCompressor: empty summary, returning original")
            return messages

        # 构建最终结果：system + 摘要轮次 + 最近精确轮次
        result = _extract_system_messages(messages)

        result.append({
            "role": "user",
            "content": f"[Previous conversation summary]\n{summary_content}",
        })
        result.append({
            "role": "assistant",
            "content": "Acknowledged the summary of our previous conversation.",
        })

        for rnd in recent_rounds:
            result.extend(rnd)

        logger.info(
            "LLMSummaryCompressor: compressed %d rounds → summary (%d chars) + %d recent rounds",
            len(old_rounds), len(summary_content), len(recent_rounds),
        )
        return result


# ── 压缩器工厂 ────────────────────────────────────────────


@dataclass
class ContextConfig:
    """上下文压缩配置"""

    max_context_tokens: int = 0
    """最大上下文 token 数。<= 0 表示不限制"""

    enforce_max_turns: int = -1
    """最大保留轮次。-1 表示不限制。在压缩前执行"""

    truncate_turns: int = 2
    """轮次截断时每次删除的轮次数"""

    llm_compress_keep_recent_ratio: float = 0.15
    """LLM 压缩时保留的最近精确上下文比例 (0-0.3)"""

    llm_compress_instruction: str | None = None
    """自定义压缩指令"""

    compression_threshold: float = 0.82
    """触发压缩的 token 使用率阈值"""


def create_compressors(
    config: ContextConfig,
    router: "ModelRouter | None" = None,
) -> tuple[TruncateByTurnsCompressor, LLMSummaryCompressor]:
    """创建压缩器对（截断 + 摘要，依次回退）

    Returns:
        (truncate_compressor, llm_compressor)
    """
    truncate = TruncateByTurnsCompressor(
        truncate_turns=config.truncate_turns,
        compression_threshold=config.compression_threshold,
    )
    llm = LLMSummaryCompressor(
        router=router,
        keep_recent_ratio=config.llm_compress_keep_recent_ratio,
        instruction_text=config.llm_compress_instruction,
        compression_threshold=config.compression_threshold,
    )
    return truncate, llm
