"""
模型健康检查 (Model Health Checker)

借鉴 Agent-Reach 的 Channel.check() 设计：
- 定期对每个注册的模型后端进行健康探测
- 探测失败自动标记 is_available=False，从候选池移除
- 探测恢复自动标记 is_available=True，重新加入候选池
- 支持 HTTP ping / API key 有效性 / 模型列表探测 三种策略

设计原则（参考 Agent-Reach）：
- check() 返回 (status, message) 二元组，简洁明了
- 健康检查失败不抛异常，只改变 is_available 标志
- 使用后台线程定期执行，不阻塞主流程
- 首次运行立即检查，之后按 interval 周期性检查
"""

from __future__ import annotations

import asyncio
import logging
import threading as _th
import time as _time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("model.health")


# ── 健康状态 ──────────────────────────────────────────

class HealthStatus(str, Enum):
    """模型健康状态"""
    HEALTHY = "healthy"           # 探测成功
    DEGRADED = "degraded"        # 探测延迟高但可用
    UNHEALTHY = "unhealthy"      # 探测失败
    UNKNOWN = "unknown"          # 尚未探测
    DISABLED = "disabled"        # 被管理员手动禁用


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=_time.time)
    details: dict[str, Any] = field(default_factory=dict)


# ── 模型条目 ──────────────────────────────────────────

@dataclass
class MonitoredModel:
    """被监控的模型条目"""
    name: str                     # 模型名称（如 "ollama-qwen3-coder-30b"）
    provider: str                 # 提供商（如 "ollama" / "openai" / "anthropic"）
    api_model_id: str = ""        # API 上的实际 model_id
    endpoint: str = ""            # API 端点 URL
    api_key_env: str = ""         # API key 环境变量名
    priority: int = 50            # 原始优先级
    health: HealthCheckResult = field(default_factory=lambda: HealthCheckResult(status=HealthStatus.UNKNOWN))
    failure_count: int = 0        # 连续失败次数
    success_count: int = 0        # 连续成功次数
    model_adapter: Any = None     # 关联的 ICandidateModel 适配器引用（弱引用）

    @property
    def is_healthy(self) -> bool:
        return self.health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    def mark_healthy(self, latency_ms: float = 0.0) -> None:
        self.failure_count = 0
        self.success_count += 1
        self.health = HealthCheckResult(
            status=HealthStatus.HEALTHY,
            message="OK",
            latency_ms=latency_ms,
        )

    def mark_degraded(self, message: str, latency_ms: float = 0.0) -> None:
        self.health = HealthCheckResult(
            status=HealthStatus.DEGRADED,
            message=message,
            latency_ms=latency_ms,
        )

    def mark_unhealthy(self, message: str) -> None:
        self.failure_count += 1
        self.success_count = 0
        self.health = HealthCheckResult(
            status=HealthStatus.UNHEALTHY,
            message=message,
        )

    def mark_disabled(self) -> None:
        self.health = HealthCheckResult(status=HealthStatus.DISABLED, message="Manually disabled")


# ── ModelHealthChecker ────────────────────────────────

class ModelHealthChecker:
    """
    模型健康检查器（借鉴 Agent-Reach Channel.check() 设计）

    用法:
        checker = ModelHealthChecker(monitored_models=[...])
        checker.start(interval=60)
        # ... 后台自动探测 ...
        unhealthy = checker.get_unhealthy()
    """

    def __init__(
        self,
        monitored_models: list[MonitoredModel] | None = None,
        ping_timeout: float = 10.0,
        max_failures: int = 3,          # 连续失败 3 次才标记 unhealthy
        recovery_threshold: int = 2,    # 连续成功 2 次恢复
        degrded_latency_ms: float = 5000,  # 延迟超过 5s 标记 degraded
    ):
        self._models: list[MonitoredModel] = list(monitored_models or [])
        self._model_map: dict[str, MonitoredModel] = {m.name: m for m in self._models}
        self._ping_timeout = ping_timeout
        self._max_failures = max_failures
        self._recovery_threshold = recovery_threshold
        self._degraded_latency_ms = degrded_latency_ms
        self._thread: _th.Thread | None = None
        self._running = False
        self._interval = 60.0
        self._check_count = 0

    # ── 模型注册 ──

    def register(self, model: MonitoredModel) -> None:
        """注册一个待监控模型"""
        if model.name not in self._model_map:
            self._models.append(model)
            self._model_map[model.name] = model

    def register_batch(self, models: list[MonitoredModel]) -> int:
        """批量注册模型"""
        added = 0
        for m in models:
            if m.name not in self._model_map:
                self._models.append(m)
                self._model_map[m.name] = m
                added += 1
        return added

    def register_from_adapters(self, adapters: list[Any]) -> int:
        """从 ICandidateModel 适配器列表注册模型"""
        added = 0
        for adapter in adapters:
            name = getattr(adapter, "name", "")
            provider = getattr(adapter, "provider", "unknown")
            api_model_id = getattr(adapter, "api_model_id", name)
            if name and name not in self._model_map:
                self.register(MonitoredModel(
                    name=name,
                    provider=provider,
                    api_model_id=api_model_id,
                    priority=getattr(adapter, "priority", 50),
                    model_adapter=adapter,
                ))
                added += 1
        return added

    # ── 生命周期 ──

    def start(self, interval: float = 60.0) -> None:
        """启动后台健康检查"""
        if self._running:
            return
        self._running = True
        self._interval = interval
        self._thread = _th.Thread(target=self._health_loop, daemon=True, name="model-health")
        self._thread.start()
        logger.info("ModelHealthChecker started (interval=%.1fs, %d models)", interval, len(self._models))

    def stop(self) -> None:
        """停止后台健康检查"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("ModelHealthChecker stopped")

    def run_check_now(self) -> dict[str, HealthCheckResult]:
        """手动触发一次健康检查（同步）"""
        results = {}
        for model in list(self._models):
            result = self._check_model(model)
            results[model.name] = result
        self._check_count += 1
        return results

    # ── 查询 ──

    def get_model(self, name: str) -> MonitoredModel | None:
        return self._model_map.get(name)

    def get_all(self) -> list[MonitoredModel]:
        return list(self._models)

    def get_unhealthy(self) -> list[MonitoredModel]:
        """获取所有不健康的模型"""
        return [m for m in self._models if not m.is_healthy]

    def get_healthy(self) -> list[MonitoredModel]:
        """获取所有健康的模型"""
        return [m for m in self._models if m.is_healthy]

    def get_stats(self) -> dict:
        """获取统计信息"""
        total = len(self._models)
        healthy = len(self.get_healthy())
        return {
            "total": total,
            "healthy": healthy,
            "unhealthy": total - healthy,
            "check_count": self._check_count,
            "models": {m.name: m.health.status.value for m in self._models},
        }

    # ── 内部 ──

    def _health_loop(self) -> None:
        """后台健康检查循环"""
        # 首次立即检查
        self.run_check_now()
        while self._running:
            _time.sleep(self._interval)
            if self._running:
                try:
                    self.run_check_now()
                except Exception as e:
                    logger.warning("Health check cycle error: %s", e)

    def _check_model(self, model: MonitoredModel) -> HealthCheckResult:
        """对单个模型执行健康检查"""
        start = _time.perf_counter()

        try:
            # 策略选择
            if model.provider == "ollama":
                success, msg, latency = self._ping_ollama(model)
            elif model.provider in ("openai", "anthropic", "deepseek"):
                success, msg, latency = self._ping_http(model)
            elif model.provider == "local":
                # 本地模型检查文件存在性
                success, msg, latency = self._ping_local(model)
            else:
                success, msg, latency = self._ping_generic(model)

            elapsed = (_time.perf_counter() - start) * 1000

            if success:
                if elapsed > self._degraded_latency_ms:
                    model.mark_degraded(f"High latency ({elapsed:.0f}ms)", elapsed)
                    logger.warning("ModelHealth: %s degraded (%.0fms)", model.name, elapsed)
                else:
                    model.mark_healthy(elapsed)
            else:
                if model.failure_count >= self._max_failures:
                    model.mark_unhealthy(msg)
                    logger.warning("ModelHealth: %s unhealthy after %d failures: %s",
                                   model.name, model.failure_count, msg)
                else:
                    # 失败次数不足时保持之前的状态
                    model.failure_count += 1

            # 同步更新适配器的 is_available 标志
            if model.model_adapter:
                try:
                    model.model_adapter.is_available = model.is_healthy
                    if not model.is_healthy:
                        model.model_adapter.last_error = model.health.message
                except Exception:
                    pass

            return model.health

        except Exception as e:
            model.mark_unhealthy(str(e)[:200])
            if model.model_adapter:
                try:
                    model.model_adapter.is_available = False
                    model.model_adapter.last_error = str(e)[:200]
                except Exception:
                    pass
            return model.health

    # ── 探测策略 ──

    def _ping_ollama(self, model: MonitoredModel) -> tuple[bool, str, float]:
        """探测 Ollama 服务（HTTP GET /api/tags）"""
        try:
            import urllib.request
            import json
            import os

            # 优先使用端点配置 → 环境变量 OLLAMA_HOST → 默认 localhost:11434
            if model.endpoint:
                base_url = model.endpoint
            else:
                base_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            url = f"{base_url}/api/tags"
            req = urllib.request.Request(url)
            start = _time.perf_counter()
            with urllib.request.urlopen(req, timeout=self._ping_timeout) as resp:
                data = json.loads(resp.read().decode())
                latency = (_time.perf_counter() - start) * 1000

                # 检查目标模型是否存在
                models_list = data.get("models", [])
                target_id = model.api_model_id or model.name
                found = any(target_id in m.get("name", "") for m in models_list)
                if found:
                    return True, "Ollama reachable, model found", latency
                else:
                    return False, f"Ollama reachable but model '{target_id}' not found", latency
        except Exception as e:
            return False, f"Ollama unreachable: {e}", 0

    def _ping_http(self, model: MonitoredModel) -> tuple[bool, str, float]:
        """探测 HTTP API 模型（通过 API key 环境变量检查）"""
        import os

        api_key_var = model.api_key_env
        if not api_key_var:
            # 根据 provider 推断
            key_map = {
                "openai": "OPENAI_API_KEY",
                "anthropic": "ANTHROPIC_API_KEY",
                "deepseek": "DEEPSEEK_API_KEY",
            }
            api_key_var = key_map.get(model.provider, "")

        if api_key_var:
            has_key = bool(os.environ.get(api_key_var, ""))
            if has_key:
                return True, f"API key '{api_key_var}' configured", 0
            else:
                return False, f"API key '{api_key_var}' not set", 0
        else:
            return False, f"Unknown API key env for provider '{model.provider}'", 0

    def _ping_local(self, model: MonitoredModel) -> tuple[bool, str, float]:
        """探测本地文件模型"""
        import os

        # 检查模型文件/目录是否存在
        possible_paths = [
            f"models/{model.name}",
            f"ai_models/models/{model.name}",
            f"backend/ai_models/models/{model.name}",
        ]
        for path in possible_paths:
            if os.path.exists(path) and os.path.isdir(path):
                files = os.listdir(path)
                if any(f.endswith((".safetensors", ".gguf", ".bin", ".pt", ".pth")) for f in files):
                    return True, f"Local model files found at '{path}'", 0

        return False, "Local model files not found", 0

    def _ping_generic(self, model: MonitoredModel) -> tuple[bool, str, float]:
        """通用探测（保守乐观）"""
        # 对于无法确定探测方式的模型，默认标记为健康
        return True, "Generic model (not probed)", 0


# ── 全局单例 ──────────────────────────────────────────

_global_health_checker: ModelHealthChecker | None = None


def init_model_health(
    monitored_models: list[MonitoredModel] | None = None,
    auto_start: bool = True,
    interval: float = 60.0,
) -> ModelHealthChecker:
    """初始化全局模型健康检查器"""
    global _global_health_checker
    _global_health_checker = ModelHealthChecker(monitored_models=monitored_models)
    if auto_start:
        _global_health_checker.start(interval=interval)
    return _global_health_checker


def get_model_health() -> ModelHealthChecker | None:
    """获取全局模型健康检查器"""
    return _global_health_checker
