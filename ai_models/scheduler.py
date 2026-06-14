"""
多模型动态调度器

职责：
1. 为每个模型计算动态评分 DynamicScore
2. 按评分排序候选模型列表
3. 支持基于使用数据的实时调整
4. 提供"本地优先、API 回退"的排序策略

评分公式：
  DynamicScore = base_priority × availability_factor × performance_factor

其中：
  - base_priority: registry 中配置的静态优先级 (0-100)
  - availability_factor: 0=不可用, 0.5=降级, 1=完全可用
  - performance_factor: 基于最近 N 次调用的 成功率 × 速度因子
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ai_models.base import ModelType

logger = logging.getLogger("ai_models.scheduler")


# ── 数据类 ────────────────────────────────────────────────

@dataclass
class UsageRecord:
    """单次使用记录"""
    model_name: str
    capability: str          # 使用场景
    success: bool
    latency_ms: int
    token_count: int | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ModelScore:
    """模型的动态评分"""
    model_name: str
    base_priority: int         # 静态优先级 0-100
    availability_factor: float  # 可用性系数 0.0-1.0
    performance_factor: float   # 性能系数 0.0-1.0
    dynamic_score: float        # 最终综合评分
    metrics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.dynamic_score == 0.0 and self.metrics:
            self.dynamic_score = (
                self.base_priority
                * self.availability_factor
                * self.performance_factor
            )


@dataclass
class SchedulerConfig:
    """调度器配置"""
    # 性能计算窗口（最近 N 次调用）
    window_size: int = 100
    # 最低成功率阈值（低于则降低 performance_factor）
    min_success_rate: float = 0.5
    # 速度基准（毫秒），低于此值为快
    speed_baseline_ms: int = 3000
    # 成功率的权重（0-1），越接近1越看重成功率
    success_weight: float = 0.6
    # 速度的权重（0-1），越接近1越看重速度
    speed_weight: float = 0.4
    # 不可用扣分系数
    unavailable_penalty: float = 0.0


# ── ModelScheduler 核心 ───────────────────────────────────

class ModelScheduler:
    """
    多模型动态调度器

    使用方式：
      scheduler = ModelScheduler()
      scheduler.record_usage("gemma-31b", ModelType.CODER, success=True, latency_ms=1200)
      candidates = scheduler.rank_candidates(capability=ModelType.CODER)

    与 ModelRouter 的关系：
      ModelRouter 是入口，Scheduler 负责排序候选。
      ModelRouter → Scheduler.rank() → [Ranked candidates]
    """

    def __init__(self, config: SchedulerConfig | None = None):
        self.config = config or SchedulerConfig()

        # 模型基础信息（来自 registry）
        self._model_priorities: dict[str, int] = {}      # model_name → base_priority
        self._model_capabilities: dict[str, set[str]] = {}  # model_name → {capability, ...}

        # 使用记录（滑动窗口）
        self._usage_history: dict[str, list[UsageRecord]] = {}

        # 实时状态
        self._availability: dict[str, float] = {}        # model_name → factor
        self._last_scores: dict[str, ModelScore] = {}

    # ── 注册 ──────────────────────────────────────────

    def register_model(
        self,
        model_name: str,
        base_priority: int = 50,
        capabilities: list[str] | None = None,
    ):
        """注册一个模型到调度器"""
        self._model_priorities[model_name] = base_priority
        self._model_capabilities[model_name] = set(capabilities or [])
        self._availability[model_name] = 1.0
        self._usage_history.setdefault(model_name, [])
        logger.debug(
            f"Model registered: {model_name} (priority={base_priority}, "
            f"capabilities={capabilities})"
        )

    def register_from_registry(self, registry_models: dict[str, Any]):
        """从模型注册中心批量注册"""
        for name, config in registry_models.items():
            capability = config.get("model_type")
            if hasattr(capability, "value"):
                capability = [capability.value]
            else:
                capability = [str(capability)] if capability else []

            self.register_model(
                model_name=name,
                base_priority=config.get("priority", 50),
                capabilities=capability,
            )

    # ── 使用记录 ──────────────────────────────────────

    def record_usage(
        self,
        model_name: str,
        capability: str,
        success: bool,
        latency_ms: int,
        token_count: int | None = None,
    ):
        """记录一次模型调用"""
        record = UsageRecord(
            model_name=model_name,
            capability=str(capability),
            success=success,
            latency_ms=latency_ms,
            token_count=token_count,
        )

        history = self._usage_history.setdefault(model_name, [])
        history.append(record)

        # 保持滑动窗口大小
        if len(history) > self.config.window_size:
            self._usage_history[model_name] = history[-self.config.window_size:]

        # 更新可用性
        self._update_availability(model_name)
        # 更新评分
        self._recalc_score(model_name)

    def _update_availability(self, model_name: str):
        """更新模型可用性系数"""
        history = self._usage_history.get(model_name, [])

        if not history:
            self._availability[model_name] = 1.0
            return

        # 检查最近 10 次调用的成功率
        recent = history[-10:]
        success_count = sum(1 for r in recent if r.success)

        if success_count == 0:
            # 完全不可用
            self._availability[model_name] = self.config.unavailable_penalty
        elif success_count < len(recent):
            # 降级模式
            self._availability[model_name] = 0.5 + (success_count / len(recent)) * 0.5
        else:
            self._availability[model_name] = 1.0

    def _recalc_score(self, model_name: str):
        """重新计算模型动态评分"""
        history = self._usage_history.get(model_name, [])
        base_priority = self._model_priorities.get(model_name, 50)
        availability = self._availability.get(model_name, 1.0)

        # 计算性能因子
        if not history:
            performance = 1.0
        else:
            # 成功率
            window = history[-self.config.window_size:]
            success_rate = sum(1 for r in window if r.success) / len(window)

            # 速度因子（越接近 baseline 越快）
            avg_latency = sum(r.latency_ms for r in window) / len(window)
            if avg_latency > 0:
                speed_factor = min(1.0, self.config.speed_baseline_ms / avg_latency)
            else:
                speed_factor = 1.0

            # 综合性能因子
            performance = (
                self.config.success_weight * success_rate
                + self.config.speed_weight * speed_factor
            )

        dynamic_score = base_priority * availability * performance

        self._last_scores[model_name] = ModelScore(
            model_name=model_name,
            base_priority=base_priority,
            availability_factor=availability,
            performance_factor=performance,
            dynamic_score=dynamic_score,
            metrics={
                "success_rate": (
                    sum(1 for r in history[-self.config.window_size:] if r.success)
                    / max(1, len(history[-self.config.window_size:]))
                ) if history else 1.0,
                "avg_latency_ms": (
                    sum(r.latency_ms for r in history[-self.config.window_size:])
                    / max(1, len(history[-self.config.window_size:]))
                ) if history else 0,
                "total_calls": len(history),
            },
        )

    # ── 候选排序 ──────────────────────────────────────

    def rank_candidates(
        self,
        capability: str,
        candidate_names: list[str] | None = None,
        limit: int = 5,
    ) -> list[tuple[str, float]]:
        """
        按动态评分排序候选模型

        返回: [(model_name, dynamic_score), ...] 降序排列
        """
        candidates = []

        # 筛选匹配能力的模型
        if candidate_names is None:
            candidate_names = [
                name for name, caps in self._model_capabilities.items()
                if capability in caps
            ]

        for name in candidate_names:
            if name not in self._model_priorities:
                continue

            # 确保评分已计算
            if name not in self._last_scores:
                self._recalc_score(name)

            score = self._last_scores[name].dynamic_score
            candidates.append((name, score))

        # 降序排序
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:limit]

    def rank_for_router(
        self,
        capability: str,
        candidates: list,
    ) -> list:
        """
        为 ModelRouter 排序候选模型实例

        将 scheduler 计算的分数注入到候选模型的 dynamic_score 属性
        """
        ranked = self.rank_candidates(capability)

        # 创建 name → score 映射
        score_map = {name: score for name, score in ranked}

        # 对候选模型实例排序
        for candidate in candidates:
            if candidate.name in score_map:
                candidate.dynamic_score = score_map[candidate.name]

        candidates.sort(key=lambda c: c.dynamic_score, reverse=True)
        return candidates

    def get_best_model(self, capability: str) -> str | None:
        """获取指定能力下评分最高的模型名"""
        ranked = self.rank_candidates(capability, limit=1)
        return ranked[0][0] if ranked else None

    # ── 模型状态 ──────────────────────────────────────

    def get_model_score(self, model_name: str) -> ModelScore | None:
        """获取模型的当前评分"""
        if model_name not in self._last_scores:
            self._recalc_score(model_name)
        return self._last_scores.get(model_name)

    def get_all_scores(self) -> list[ModelScore]:
        """获取所有模型的当前评分"""
        return [
            self.get_model_score(name)
            for name in self._model_priorities
            if self._model_priorities[name] > 0
        ]

    def set_available(self, model_name: str, available: bool):
        """手动设置模型可用性"""
        self._availability[model_name] = 1.0 if available else 0.0
        self._recalc_score(model_name)

    def get_status_report(self) -> dict:
        """生成调度状态报告"""
        return {
            "total_models": len(self._model_priorities),
            "models": {
                name: {
                    "priority": self._model_priorities.get(name, 0),
                    "availability": self._availability.get(name, 0.0),
                    "score": (
                        self._last_scores[name].dynamic_score
                        if name in self._last_scores else 0.0
                    ),
                    "capabilities": list(self._model_capabilities.get(name, set())),
                }
                for name in self._model_priorities
            },
        }


# ── 全局调度器单例 ────────────────────────────────────────

_global_scheduler: ModelScheduler | None = None


def get_scheduler() -> ModelScheduler:
    """获取全局调度器"""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = ModelScheduler()
    return _global_scheduler


def init_scheduler() -> ModelScheduler:
    """初始化全局调度器"""
    global _global_scheduler
    _global_scheduler = ModelScheduler()
    return _global_scheduler
