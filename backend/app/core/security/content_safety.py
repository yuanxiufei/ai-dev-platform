"""
可插拔内容安全策略链 — Strategy 模式双向检查

借鉴 AstrBot 的 content_safety 策略链设计：
- StrategySelector 按配置动态组装策略链
- 任意策略失败即短路拦截
- 支持双向检查：用户输入 + LLM 输出
- 可扩展：Keywords、LLM-as-Judge、第三方 API

用法:
    selector = StrategySelector(config={"keywords_enable": True, "extra_keywords": [...]})
    ok, reason = selector.check("用户输入内容")
    if not ok:
        raise HTTPException(400, detail=reason)
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger("security.content_safety")


# ── 抽象策略 ──────────────────────────────────────────────


class ContentSafetyStrategy(ABC):
    """内容安全策略抽象基类"""

    @abstractmethod
    async def check(self, content: str) -> tuple[bool, str]:
        """检查内容是否安全。

        Returns:
            (is_safe, reason): is_safe=True 表示通过，False 表示拦截
        """
        ...


# ── 关键词策略 ────────────────────────────────────────────


class KeywordsStrategy(ContentSafetyStrategy):
    """基于正则关键词的内容安全检查"""

    def __init__(self, extra_keywords: list[str] | None = None) -> None:
        self.keywords: list[str] = list(extra_keywords or [])
        # 内置不安全关键词
        self._builtin: list[str] = [
            r"hack\s*into",
            r"illegal\s*access",
            r"exploit\s+vulnerability",
            r"generate\s+malware",
            r"create\s+phishing",
            r"bypass\s+security",
            r"ddos\s+attack",
            r"ransomware",
            r"keylogger",
            r"botnet",
            r"zero\s*day\s*exploit",
            r"sql\s*injection",
            r"cross\s*site\s*scripting",
            r"remote\s*code\s*execution",
            r"privilege\s+escalation",
        ]

    async def check(self, content: str) -> tuple[bool, str]:
        all_keywords = self._builtin + self.keywords
        content_lower = content.lower()
        for keyword in all_keywords:
            if re.search(keyword, content_lower):
                logger.warning("Content blocked by keyword: '%s'", keyword)
                return False, "内容安全检查不通过，匹配到不安全关键词。"
        return True, ""


# ── LLM-as-Judge 策略 ─────────────────────────────────────


class LLMJudgeStrategy(ContentSafetyStrategy):
    """使用 LLM 作为内容安全裁判

    当关键词策略无法覆盖复杂场景时，交给 LLM 判断。
    """

    JUDGE_PROMPT = """You are a content safety classifier.
Analyze the following user message and determine if it contains harmful content.

Harmful categories:
- violence/hate speech
- self-harm/suicide
- sexual content involving minors
- illegal activities
- personal information disclosure

Reply with ONLY one word: SAFE or UNSAFE.

Message: {content}
"""

    def __init__(self, provider_callable: Any = None) -> None:
        """初始化 LLM 裁判策略

        Args:
            provider_callable: 异步函数，接受 prompt 返回文本
        """
        self._provider = provider_callable

    async def check(self, content: str) -> tuple[bool, str]:
        if not self._provider:
            logger.debug("LLMJudgeStrategy: no provider configured, skipping")
            return True, ""

        try:
            prompt = self.JUDGE_PROMPT.format(content=content[:4000])
            result = await self._provider(prompt)
            verdict = (result or "").strip().upper()

            if "UNSAFE" in verdict:
                logger.warning("Content blocked by LLM judge")
                return False, "内容安全检查不通过（LLM 判定为不安全内容）。"
            return True, ""
        except Exception as e:
            logger.error("LLMJudgeStrategy error: %s", e)
            # LLM 判断失败时放行（避免误拦）
            return True, ""


# ── 策略选择器 ────────────────────────────────────────────


class StrategySelector:
    """策略选择器 —— 按配置动态组装策略链

    借鉴 AstrBot StrategySelector：
    - 按配置启用/禁用各类策略
    - 链式调用：任意策略失败即返回
    - 失败优先原则：第一个拦截的策略决定最终结果
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}
        self.enabled_strategies: list[ContentSafetyStrategy] = []

        # 关键词策略
        if cfg.get("keywords_enable", True):
            self.enabled_strategies.append(
                KeywordsStrategy(extra_keywords=cfg.get("extra_keywords", [])),
            )

        # LLM 裁判策略
        if cfg.get("llm_judge_enable", False):
            self.enabled_strategies.append(
                LLMJudgeStrategy(provider_callable=cfg.get("llm_judge_provider")),
            )

        logger.info(
            "StrategySelector initialized with %d strategies: %s",
            len(self.enabled_strategies),
            [s.__class__.__name__ for s in self.enabled_strategies],
        )

    async def check(self, content: str) -> tuple[bool, str]:
        """执行策略链检查

        Returns:
            (is_safe, reason)
        """
        if not content or not content.strip():
            return True, ""

        for strategy in self.enabled_strategies:
            ok, reason = await strategy.check(content)
            if not ok:
                return False, reason

        return True, ""

    async def check_bidirectional(
        self, user_input: str, assistant_output: str,
    ) -> tuple[bool, str]:
        """双向检查：用户输入 + 助手输出

        Returns:
            (is_safe, reason)
        """
        # 检查用户输入
        ok, reason = await self.check(user_input)
        if not ok:
            return False, f"[输入] {reason}"

        # 检查助手输出
        ok, reason = await self.check(assistant_output)
        if not ok:
            return False, f"[输出] {reason}"

        return True, ""


# ── 全局策略选择器 ────────────────────────────────────────

_selector: StrategySelector | None = None


def init_content_safety(config: dict[str, Any] | None = None) -> StrategySelector:
    """初始化全局内容安全检查器"""
    global _selector
    _selector = StrategySelector(config)
    return _selector


def get_content_safety() -> StrategySelector:
    """获取全局内容安全检查器"""
    global _selector
    if _selector is None:
        _selector = StrategySelector()
    return _selector
