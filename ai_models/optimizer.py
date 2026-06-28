"""
使用数据自动优化引擎

职责：
1. 分析模型使用数据，自动调整优先级
2. 检测异常模式（频繁失败、延迟飙升）
3. 生成优化建议并自动执行
4. 支持高峰期预加载策略

优化动作：
  - 降级 (DEMOTE):    成功率低于阈值 → 降低 priority
  - 升级 (PROMOTE):   表现优异 → 提升 priority
  - 移除 (DISABLE):   持续失败 → 标记不可用
  - 预加载 (PRELOAD): 高峰时段 → 提前加载热门模型
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger("ai_models.optimizer")


# ── 优化动作 ──────────────────────────────────────────────

class OptimizationAction(str, Enum):
    DEMOTE = "demote"     # 降低优先级
    PROMOTE = "promote"   # 提升优先级
    DISABLE = "disable"   # 标记不可用
    PRELOAD = "preload"   # 预加载
    NONE = "none"         # 无需操作


@dataclass
class OptimizationSuggestion:
    """优化建议"""
    model_name: str
    action: OptimizationAction
    reason: str
    current_priority: int
    suggested_priority: int
    metrics: dict[str, Any] = field(default_factory=dict)


# ── 异常检测 ──────────────────────────────────────────────

@dataclass
class AnomalyReport:
    """异常检测报告"""
    model_name: str
    anomaly_type: str         # high_error_rate | high_latency | pattern_change
    severity: str             # low | medium | high | critical
    description: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AnomalyDetector:
    """异常检测器"""

    def __init__(
        self,
        error_rate_threshold: float = 0.3,
        latency_spike_factor: float = 3.0,
        min_samples: int = 10,
    ):
        self.error_rate_threshold = error_rate_threshold
        self.latency_spike_factor = latency_spike_factor
        self.min_samples = min_samples

    def detect(self, records: list, baseline_latency_ms: float = 3000) -> list[AnomalyReport]:
        """检测异常"""
        anomalies = []

        if len(records) < self.min_samples:
            return anomalies

        # 1. 错误率检测
        recent = records[-self.min_samples:]
        error_rate = sum(1 for r in recent if not r.success) / len(recent)

        if error_rate > self.error_rate_threshold:
            anomalies.append(AnomalyReport(
                model_name=recent[0].model_name if recent else "unknown",
                anomaly_type="high_error_rate",
                severity="critical" if error_rate > 0.5 else "high",
                description=(
                    f"Error rate {error_rate:.1%} exceeds threshold "
                    f"{self.error_rate_threshold:.1%}"
                ),
            ))

        # 2. 延迟飙升检测
        recent_latency = sum(r.latency_ms for r in recent) / len(recent)
        if recent_latency > baseline_latency_ms * self.latency_spike_factor:
            anomalies.append(AnomalyReport(
                model_name=recent[0].model_name if recent else "unknown",
                anomaly_type="high_latency",
                severity="medium",
                description=(
                    f"Avg latency {recent_latency:.0f}ms is "
                    f"{recent_latency / baseline_latency_ms:.1f}x baseline"
                ),
            ))

        return anomalies


# ── AutoOptimizer 核心 ────────────────────────────────────

class AutoOptimizer:
    """
    自动优化引擎

    使用方式：
      optimizer = AutoOptimizer(scheduler)
      suggestions = optimizer.analyze(days=7)
      optimizer.apply(suggestions)
    """

    def __init__(
        self,
        scheduler=None,  # ModelScheduler 实例
        usage_stats_repo=None,  # 使用统计数据库仓库
    ):
        self.scheduler = scheduler
        self.usage_stats_repo = usage_stats_repo
        self.detector = AnomalyDetector()

        # 优化配置
        self.min_priority = 10
        self.max_priority = 100
        self.demote_step = 10
        self.promote_step = 5
        self.demote_threshold_error_rate = 0.3
        self.promote_threshold_success_rate = 0.9
        self.disable_threshold_error_rate = 0.1

    def analyze(self, days: int = 7) -> list[OptimizationSuggestion]:
        """
        分析最近 N 天的使用数据

        返回优化建议列表
        """
        suggestions: list[OptimizationSuggestion] = []

        # 获取统计快照
        status = self.scheduler.get_status_report() if self.scheduler else {}
        models = status.get("models", {})

        for model_name, info in models.items():
            priority = info.get("priority", 50)
            score = info.get("score", 0)
            metrics = info.get("metrics", {})

            success_rate = metrics.get("success_rate", 1.0)
            total_calls = metrics.get("total_calls", 0)

            # 调用数太少，不分析
            if total_calls < 10:
                continue

            # === 禁用检测（最严重，优先检查）===
            if success_rate < self.disable_threshold_error_rate and total_calls > 20:
                suggestions.append(OptimizationSuggestion(
                    model_name=model_name,
                    action=OptimizationAction.DISABLE,
                    reason=f"Critical error rate {success_rate:.1%} (threshold {self.disable_threshold_error_rate:.1%})",
                    current_priority=priority,
                    suggested_priority=0,
                    metrics={"success_rate": success_rate, "total_calls": total_calls},
                ))

            # === 降级检测 ===
            elif success_rate < self.demote_threshold_error_rate:
                new_priority = max(self.min_priority, priority - self.demote_step)
                suggestions.append(OptimizationSuggestion(
                    model_name=model_name,
                    action=OptimizationAction.DEMOTE,
                    reason=f"Success rate {success_rate:.1%} below threshold {self.demote_threshold_error_rate:.1%}",
                    current_priority=priority,
                    suggested_priority=new_priority,
                    metrics={"success_rate": success_rate, "total_calls": total_calls},
                ))

            # === 升级检测 ===
            elif success_rate > self.promote_threshold_success_rate and total_calls > 50:
                new_priority = min(self.max_priority, priority + self.promote_step)
                if new_priority > priority:
                    suggestions.append(OptimizationSuggestion(
                        model_name=model_name,
                        action=OptimizationAction.PROMOTE,
                        reason=f"Excellent success rate {success_rate:.1%} — promoting",
                        current_priority=priority,
                        suggested_priority=new_priority,
                        metrics={"success_rate": success_rate, "total_calls": total_calls},
                    ))

            # === 异常检测 ===
            if self.scheduler:
                history = self.scheduler._usage_history.get(model_name, [])
                anomalies = self.detector.detect(history)
                for anomaly in anomalies:
                    logger.warning(
                        "Anomaly detected: %s — %s (%s)",
                        anomaly.model_name,
                        anomaly.anomaly_type,
                        anomaly.severity,
                    )

        return suggestions

    def apply(self, suggestions: list[OptimizationSuggestion]) -> list[dict]:
        """应用优化建议"""
        applied = []

        for suggestion in suggestions:
            result = {
                "model": suggestion.model_name,
                "action": suggestion.action.value,
                "success": False,
            }

            try:
                if suggestion.action == OptimizationAction.DEMOTE:
                    self._update_priority(
                        suggestion.model_name, suggestion.suggested_priority
                    )
                    result["success"] = True
                    logger.info(
                        f"Demoted {suggestion.model_name}: "
                        f"{suggestion.current_priority} → {suggestion.suggested_priority}"
                    )

                elif suggestion.action == OptimizationAction.PROMOTE:
                    self._update_priority(
                        suggestion.model_name, suggestion.suggested_priority
                    )
                    result["success"] = True
                    logger.info(
                        f"Promoted {suggestion.model_name}: "
                        f"{suggestion.current_priority} → {suggestion.suggested_priority}"
                    )

                elif suggestion.action == OptimizationAction.DISABLE:
                    if self.scheduler:
                        self.scheduler.set_available(suggestion.model_name, False)
                    self._update_priority(suggestion.model_name, 0)
                    result["success"] = True
                    logger.info(f"Disabled {suggestion.model_name}")

                applied.append(result)

            except Exception as e:
                logger.error(f"Failed to apply {suggestion.action} for {suggestion.model_name}: {e}")
                result["error"] = str(e)
                applied.append(result)

        return applied

    def _update_priority(self, model_name: str, new_priority: int):
        """更新模型优先级（同步到 scheduler 和 registry）"""
        if self.scheduler:
            self.scheduler._model_priorities[model_name] = new_priority
            self.scheduler._recalc_score(model_name)

    def auto_tune(self, days: int = 7) -> dict:
        """一键自动分析和优化"""
        suggestions = self.analyze(days=days)
        if not suggestions:
            return {"status": "ok", "changes": 0, "details": "No optimization needed"}

        applied = self.apply(suggestions)
        return {
            "status": "ok",
            "changes": len(applied),
            "details": [
                {
                    "model": r["model"],
                    "action": r["action"],
                    "success": r["success"],
                }
                for r in applied
            ],
        }

    def get_optimal_model(self, capability: str) -> str | None:
        """根据历史数据推荐当前最优模型"""
        if not self.scheduler:
            return None
        return self.scheduler.get_best_model(capability)

    def predict_peak_models(self, hour: int | None = None) -> list[str]:
        """
        高峰期模型预加载建议

        返回：应在当前时段预加载的模型列表
        """
        if hour is None:
            hour = datetime.now(timezone.utc).hour

        # 基于时段的使用模式
        # 工作日 9-12, 14-18 为代码生成高峰
        # 晚间 19-23 为视频生成高峰
        peak_hours = {
            "code_generation": [9, 10, 11, 14, 15, 16, 17],
            "video_generation": [19, 20, 21, 22],
            "text_generation": [10, 11, 14, 15, 20, 21],
        }

        preload_models = []

        for capability, hours in peak_hours.items():
            if hour in hours:
                best = self.get_optimal_model(capability)
                if best:
                    preload_models.append(best)

        return preload_models


# ── 全局优化器单例 ────────────────────────────────────────

_global_optimizer: AutoOptimizer | None = None


def get_optimizer() -> AutoOptimizer:
    """获取全局优化器"""
    global _global_optimizer
    if _global_optimizer is None:
        _global_optimizer = AutoOptimizer()
    return _global_optimizer


def init_optimizer(
    scheduler=None,
    usage_stats_repo=None,
) -> AutoOptimizer:
    """初始化全局优化器"""
    global _global_optimizer
    _global_optimizer = AutoOptimizer(
        scheduler=scheduler,
        usage_stats_repo=usage_stats_repo,
    )
    return _global_optimizer
