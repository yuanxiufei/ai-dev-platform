"""
Agent 预算感知循环 (Budget-Aware Loop)

借鉴 hermes-agent 的预算感知设计：
- 追踪每次 LLM 调用的 token 消耗和成本
- 预算耗尽时自动优雅终止（非硬中断）
- 支持三层预算：token / cost / time
- 预算剩余不足时触发降级策略（缩短回答/跳过工具）

设计原则（参考 hermes-agent）：
- 预算检查在每个循环轮次开始前进行
- 预算耗尽不是"立即终止"而是"发出警告并给出最后一轮"
- 成本模型可插拔（支持按模型定价）
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

logger = logging.getLogger("agent.budget")


# ── 定价表（USD / 1M tokens）───────────────────────────

@dataclass
class PricingTier:
    """模型定价层"""
    input_price_per_1m: float = 0.0   # 输入 token 单价 (USD/百万)
    output_price_per_1m: float = 0.0  # 输出 token 单价 (USD/百万)


# 参考定价（2026 年市场均价，粗略估计）
DEFAULT_PRICING: dict[str, PricingTier] = {
    # OpenAI
    "gpt-4o": PricingTier(2.50, 10.00),
    "gpt-4o-mini": PricingTier(0.15, 0.60),
    "gpt-4-turbo": PricingTier(10.00, 30.00),
    "o3-mini": PricingTier(1.10, 4.40),
    # Anthropic
    "claude-sonnet-4-20250514": PricingTier(3.00, 15.00),
    "claude-3-5-sonnet": PricingTier(3.00, 15.00),
    "claude-3-5-haiku": PricingTier(0.80, 4.00),
    # DeepSeek
    "deepseek-chat": PricingTier(0.27, 1.10),
    "deepseek-reasoner": PricingTier(0.55, 2.19),
    # Ollama (本地免费)
    **{f"ollama-{name}": PricingTier(0.0, 0.0) for name in [
        "qwen3-coder-30b", "deepseek-r1-32b", "gemma4-31b",
        "qwen25-coder-14b", "codellama-34b", "llama3.1-70b",
    ]},
}


# ── 预算状态 ──────────────────────────────────────────

class BudgetStatus(str, Enum):
    """预算状态"""
    HEALTHY = "healthy"          # 预算充足（>30% 剩余）
    WARNING = "warning"          # 预算紧张（15-30% 剩余）
    CRITICAL = "critical"        # 预算不足（<15% 剩余）
    EXHAUSTED = "exhausted"      # 预算耗尽


# ── 预算消耗记录 ──────────────────────────────────────

@dataclass
class BudgetConsumption:
    """单次消耗记录"""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    model: str = ""


# ── BudgetTracker ─────────────────────────────────────

@dataclass
class BudgetTracker:
    """
    Agent 预算追踪器（借鉴 hermes-agent 预算感知循环）

    三层预算：
    - token_budget: 最大 cumulative tokens（输入+输出）
    - cost_budget_usd: 最大累计成本（美元）
    - time_budget_ms: 最大运行时间（毫秒）

    用法:
        tracker = BudgetTracker(
            token_budget=100000,
            cost_budget_usd=0.50,
            time_budget_ms=120000,
        )
        tracker.record(input_tokens=2000, output_tokens=500, model="gpt-4o")
        if tracker.status == BudgetStatus.EXHAUSTED:
            raise BudgetExceededError(tracker)
    """

    # ── 预算上限 ──
    token_budget: int = 200000       # 默认 200K tokens
    cost_budget_usd: float = 5.0     # 默认 $5.00
    time_budget_ms: float = 300000   # 默认 5 分钟

    # ── 累计消耗 ──
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost_usd: float = 0.0
    total_time_ms: float = 0.0

    # ── 历史记录 ──
    history: list[BudgetConsumption] = field(default_factory=list)

    # ── 配置 ──
    pricing: dict[str, PricingTier] = field(default_factory=lambda: dict(DEFAULT_PRICING))
    start_time: float = field(default_factory=time.perf_counter)
    warn_threshold: float = 0.30     # 30% 剩余时进入 WARNING
    critical_threshold: float = 0.15  # 15% 剩余时进入 CRITICAL

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def token_remaining(self) -> int:
        return max(0, self.token_budget - self.total_tokens)

    @property
    def cost_remaining(self) -> float:
        return max(0.0, self.cost_budget_usd - self.total_cost_usd)

    @property
    def time_remaining_ms(self) -> float:
        elapsed = (time.perf_counter() - self.start_time) * 1000
        return max(0.0, self.time_budget_ms - elapsed)

    @property
    def status(self) -> BudgetStatus:
        """计算当前预算状态（取最差的维度）"""
        if self._is_exhausted:
            return BudgetStatus.EXHAUSTED

        # 各维度剩余比例
        ratios = []
        if self.token_budget > 0:
            ratios.append(self.token_remaining / self.token_budget)
        if self.cost_budget_usd > 0:
            ratios.append(self.cost_remaining / self.cost_budget_usd)
        if self.time_budget_ms > 0:
            ratios.append(self.time_remaining_ms / self.time_budget_ms)

        if not ratios:
            return BudgetStatus.HEALTHY

        worst = min(ratios)

        if worst <= 0:
            return BudgetStatus.EXHAUSTED
        if worst <= self.critical_threshold:
            return BudgetStatus.CRITICAL
        if worst <= self.warn_threshold:
            return BudgetStatus.WARNING
        return BudgetStatus.HEALTHY

    @property
    def _is_exhausted(self) -> bool:
        """检查是否任一维度预算耗尽"""
        if self.token_budget > 0 and self.total_tokens >= self.token_budget:
            return True
        if self.cost_budget_usd > 0 and self.total_cost_usd >= self.cost_budget_usd:
            return True
        if self.time_budget_ms > 0:
            elapsed = (time.perf_counter() - self.start_time) * 1000
            if elapsed >= self.time_budget_ms:
                return True
        return False

    def record(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        model: str = "",
        latency_ms: float = 0.0,
    ) -> None:
        """记录一次 LLM 调用的消耗"""
        cost = self._estimate_cost(model, input_tokens, output_tokens)

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_cost_usd += cost
        self.total_time_ms += latency_ms

        consumption = BudgetConsumption(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            model=model,
        )
        self.history.append(consumption)

    def _estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """根据模型名估算成本"""
        # 精确匹配
        if model in self.pricing:
            tier = self.pricing[model]
        else:
            # 模糊匹配：找 provider 前缀
            tier = self._fuzzy_match_pricing(model)

        input_cost = (input_tokens / 1_000_000) * tier.input_price_per_1m
        output_cost = (output_tokens / 1_000_000) * tier.output_price_per_1m
        return round(input_cost + output_cost, 6)

    def _fuzzy_match_pricing(self, model: str) -> PricingTier:
        """模糊匹配定价（按模型名关键字）"""
        model_lower = model.lower()
        if "gpt-4" in model_lower:
            return self.pricing.get("gpt-4o", PricingTier(2.50, 10.00))
        if "gpt-3.5" in model_lower:
            return PricingTier(0.50, 1.50)
        if "claude" in model_lower and "sonnet" in model_lower:
            return PricingTier(3.00, 15.00)
        if "claude" in model_lower and "haiku" in model_lower:
            return PricingTier(0.80, 4.00)
        if "claude" in model_lower and "opus" in model_lower:
            return PricingTier(15.00, 75.00)
        if "deepseek" in model_lower:
            return PricingTier(0.27, 1.10)
        if "ollama" in model_lower or "local" in model_lower:
            return PricingTier(0.0, 0.0)
        if "gemini" in model_lower:
            return PricingTier(1.25, 5.00)
        if "qwen" in model_lower:
            return PricingTier(0.0, 0.0)  # Ollama 本地

        # 默认：保守估计
        return PricingTier(2.00, 8.00)

    def summary(self) -> dict:
        """生成预算摘要"""
        return {
            "status": self.status.value,
            "total_tokens": self.total_tokens,
            "token_budget": self.token_budget,
            "token_remaining": self.token_remaining,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "cost_budget_usd": self.cost_budget_usd,
            "cost_remaining": round(self.cost_remaining, 4),
            "total_time_ms": round(self.total_time_ms),
            "time_budget_ms": self.time_budget_ms,
            "time_remaining_ms": round(self.time_remaining_ms),
            "consumptions_count": len(self.history),
            "models_used": list(set(c.model for c in self.history if c.model)),
        }

    def should_continue(self) -> tuple[bool, str]:
        """
        判断是否应该继续下一轮循环

        Returns:
            (是否继续, 阻止原因)
        """
        if self.status == BudgetStatus.EXHAUSTED:
            reasons = []
            if self.token_budget > 0 and self.total_tokens >= self.token_budget:
                reasons.append(f"token budget exhausted ({self.total_tokens}/{self.token_budget})")
            if self.cost_budget_usd > 0 and self.total_cost_usd >= self.cost_budget_usd:
                reasons.append(f"cost budget exhausted (${self.total_cost_usd:.4f}/${self.cost_budget_usd:.2f})")
            if self.time_budget_ms > 0 and self.time_remaining_ms <= 0:
                reasons.append(f"time budget exhausted ({self.total_time_ms:.0f}ms/{self.time_budget_ms:.0f}ms)")
            return False, "; ".join(reasons)
        return True, ""


# ── 预算异常 ──────────────────────────────────────────

class BudgetExceededError(Exception):
    """预算超限异常"""

    def __init__(self, tracker: BudgetTracker):
        self.tracker = tracker
        self.status = tracker.status
        self.summary = tracker.summary()
        super().__init__(
            f"Agent budget exceeded: {self.status.value}. "
            f"Tokens: {self.summary['total_tokens']}/{self.summary['token_budget']}, "
            f"Cost: ${self.summary['total_cost_usd']}/{self.summary['cost_budget_usd']}"
        )


# ── 工厂函数 ──────────────────────────────────────────

def create_default_budget() -> BudgetTracker:
    """创建默认预算追踪器（宽松限制）"""
    return BudgetTracker(
        token_budget=200000,
        cost_budget_usd=5.0,
        time_budget_ms=300000,
    )


def create_dev_budget() -> BudgetTracker:
    """创建开发模式预算追踪器（无限制）"""
    return BudgetTracker(
        token_budget=0,       # 0 = 不限制
        cost_budget_usd=0.0,  # 0 = 不限制
        time_budget_ms=0.0,   # 0 = 不限制
    )


def create_tight_budget() -> BudgetTracker:
    """创建紧缩预算追踪器（适用于单次简单查询）"""
    return BudgetTracker(
        token_budget=50000,
        cost_budget_usd=1.0,
        time_budget_ms=120000,
    )
