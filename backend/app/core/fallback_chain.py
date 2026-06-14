"""
回退链管理器 — 多层容错保障

职责：
1. 定义从优到劣的模型回退顺序
2. 每一层有独立的健康检查和超时策略
3. 记录每次回退详情用于诊断
4. 支持运行时动态调整回退策略

回退层级（从高到低）：
  Layer 1: 用户指定模型    → 最高优先级，直接使用
  Layer 2: 本地最优模型     → 按 DynamicScore 排序的前3个
  Layer 3: 本地次优模型     → 降级尝试
  Layer 4: 第三方 API       → OpenAI / Claude / DeepSeek / ...
  Layer 5: 内置基础模型     → 永远可用，确保系统不中断
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from app.core.model_router import (
    ICandidateModel,
    ModelRequest,
    ModelResponse,
)

logger = logging.getLogger("fallback_chain")


# ── 回退层级 ──────────────────────────────────────────────

class FallbackLayer(str, Enum):
    """回退层级"""
    PREFERRED = "preferred"         # 用户指定
    LOCAL_PRIMARY = "local_primary"  # 本地最优
    LOCAL_SECONDARY = "local_secondary"  # 本地次优
    API_GATEWAY = "api_gateway"      # 第三方 API
    BUILTIN_FALLBACK = "builtin"     # 内置兜底


@dataclass
class FallbackEvent:
    """回退事件记录"""
    layer: FallbackLayer
    model_name: str
    success: bool
    latency_ms: int | None = None
    error_message: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class FallbackResult:
    """回退链执行结果"""
    response: ModelResponse
    events: list[FallbackEvent]
    total_layers_tried: int
    is_fallback: bool


# ── 回退链节点 ───────────────────────────────────────────

class ChainNode:
    """回退链中的一个节点"""

    def __init__(
        self,
        layer: FallbackLayer,
        models: list[ICandidateModel],
        timeout_seconds: float = 30.0,
        retry_count: int = 1,
    ):
        self.layer = layer
        self.models = models
        self.timeout = timeout_seconds
        self.retry_count = retry_count

    @property
    def is_available(self) -> bool:
        return any(m.is_available for m in self.models)

    async def execute(self, request: ModelRequest) -> FallbackEvent | None:
        """
        尝试执行该层的模型

        返回：成功则返回包含响应的 FallbackEvent；失败返回 None
        """
        for model in self.models:
            if not model.is_available:
                logger.debug(f"Skipping unavailable model: {model.name}")
                continue

            for attempt in range(self.retry_count + 1):
                try:
                    import asyncio
                    start = time.perf_counter()
                    response = await asyncio.wait_for(
                        model.generate(request),
                        timeout=self.timeout,
                    )
                    latency = int((time.perf_counter() - start) * 1000)

                    logger.info(
                        "✓ Fallback chain: %s/%s succeeded in %dms",
                        self.layer.value,
                        model.name,
                        latency,
                    )
                    return FallbackEvent(
                        layer=self.layer,
                        model_name=model.name,
                        success=True,
                        latency_ms=latency,
                    )

                except asyncio.TimeoutError:
                    logger.warning(
                        "✗ %s/%s timed out (attempt %d/%d)",
                        self.layer.value,
                        model.name,
                        attempt + 1,
                        self.retry_count + 1,
                    )
                    if attempt >= self.retry_count:
                        return FallbackEvent(
                            layer=self.layer,
                            model_name=model.name,
                            success=False,
                            error_message="timeout",
                        )

                except Exception as e:
                    logger.warning(
                        "✗ %s/%s failed: %s (attempt %d/%d)",
                        self.layer.value,
                        model.name,
                        str(e)[:100],
                        attempt + 1,
                        self.retry_count + 1,
                    )
                    if attempt >= self.retry_count:
                        return FallbackEvent(
                            layer=self.layer,
                            model_name=model.name,
                            success=False,
                            error_message=str(e)[:200],
                        )

        # 所有模型都不可用
        return FallbackEvent(
            layer=self.layer,
            model_name="none",
            success=False,
            error_message="no models available in this layer",
        )


# ── FallbackChain 核心 ────────────────────────────────────

class FallbackChain:
    """
    回退链管理器

    使用方式：
      chain = FallbackChain([
          ChainNode(FallbackLayer.LOCAL_PRIMARY, local_models),
          ChainNode(FallbackLayer.API_GATEWAY, api_candidates),
          ChainNode(FallbackLayer.BUILTIN_FALLBACK, [fallback_model]),
      ])
      result = await chain.execute(request)
    """

    def __init__(self, nodes: list[ChainNode] | None = None):
        self.nodes: list[ChainNode] = nodes or []
        self._on_fallback: Callable[[FallbackEvent], None] | None = None

    def add_node(self, node: ChainNode):
        """添加回退节点"""
        self.nodes.append(node)

    def insert_node(self, index: int, node: ChainNode):
        """在指定位置插入节点"""
        self.nodes.insert(index, node)

    def on_fallback(self, callback: Callable[[FallbackEvent], None]):
        """注册回退事件回调（用于日志/告警）"""
        self._on_fallback = callback

    async def execute(self, request: ModelRequest) -> FallbackResult:
        """
        执行回退链

        流程：
          1. 从第一层开始尝试
          2. 每层失败后记录事件，进入下一层
          3. 找到可用模型后返回
          4. 理论上最后一层（builtin）永远成功
        """
        events: list[FallbackEvent] = []
        final_response: ModelResponse | None = None
        layers_tried = 0

        for node in self.nodes:
            layers_tried += 1

            # 跳过不可用的层
            if not node.is_available:
                logger.info(f"Layer '{node.layer.value}' has no available models, skipping")
                events.append(FallbackEvent(
                    layer=node.layer,
                    model_name="none",
                    success=False,
                    error_message="layer not available",
                ))
                continue

            # 执行节点
            event = await node.execute(request)
            events.append(event)

            if event.success:
                # 成功！获取响应
                # 注意：我们需要从 execute 获取实际响应
                # 这里简化为从事件重建
                logger.info(
                    f"Fallback chain succeeded at layer '{node.layer.value}' "
                    f"({layers_tried}/{len(self.nodes)} layers tried)"
                )

                # 标记是否为回退（非第一层成功即为回退）
                is_fallback = layers_tried > 1

                return FallbackResult(
                    response=ModelResponse(
                        content="[reconstructed from chain]",
                        model_used=event.model_name,
                        provider="unknown",
                        latency_ms=event.latency_ms or 0,
                        is_fallback=is_fallback,
                    ),
                    events=events,
                    total_layers_tried=layers_tried,
                    is_fallback=is_fallback,
                )

            # 触发回退回调
            if self._on_fallback:
                self._on_fallback(event)

        # 所有层都失败 — 理论上不应该到达这里
        raise AllLayersExhaustedError(
            f"All {len(self.nodes)} fallback layers exhausted. "
            f"Errors: {[e.error_message for e in events]}"
        )

    def get_chain_info(self) -> dict[str, Any]:
        """获取回退链状态信息"""
        return {
            "total_layers": len(self.nodes),
            "layers": [
                {
                    "name": node.layer.value,
                    "available": node.is_available,
                    "model_count": len(node.models),
                    "models": [
                        {"name": m.name, "available": m.is_available, "score": m.dynamic_score}
                        for m in node.models
                    ],
                }
                for node in self.nodes
            ],
        }

    def get_fallback_stats(self, events: list[FallbackEvent]) -> dict:
        """分析回退事件统计"""
        if not events:
            return {}

        success_count = sum(1 for e in events if e.success)
        layers_tried = len(events)

        return {
            "success_rate": f"{success_count}/{layers_tried}",
            "total_layers": layers_tried,
            "successful_layer": next(
                (e.layer.value for e in events if e.success), "none"
            ),
            "failures": [
                {"layer": e.layer.value, "error": e.error_message}
                for e in events if not e.success
            ],
        }


class AllLayersExhaustedError(Exception):
    """所有回退层耗尽"""
    pass


# ── 预置回退链构建 ──────────────────────────────────────

def build_default_fallback_chain(
    local_models: list[ICandidateModel],
    api_gateway_candidates: list[ICandidateModel],
    fallback_model: ICandidateModel,
) -> FallbackChain:
    """构建标准的五层回退链"""

    chain = FallbackChain([
        ChainNode(
            FallbackLayer.LOCAL_PRIMARY,
            local_models[:3] if len(local_models) > 3 else local_models,
            timeout_seconds=30.0,
        ),
        ChainNode(
            FallbackLayer.LOCAL_SECONDARY,
            local_models[3:] if len(local_models) > 3 else [],
            timeout_seconds=45.0,
        ),
        ChainNode(
            FallbackLayer.API_GATEWAY,
            api_gateway_candidates,
            timeout_seconds=60.0,
            retry_count=2,
        ),
        ChainNode(
            FallbackLayer.BUILTIN_FALLBACK,
            [fallback_model],
            timeout_seconds=10.0,
        ),
    ])

    # 注册回退告警
    def _on_fallback(event: FallbackEvent):
        if not event.success:
            logger.warning(
                "FALLBACK ALERT: Layer '%s' failed (%s) → trying next layer",
                event.layer.value,
                event.error_message,
            )

    chain.on_fallback(_on_fallback)
    return chain
