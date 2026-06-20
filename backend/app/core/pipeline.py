"""
流水线调度器 (PipelineScheduler) — 可插拔的消息/请求处理流水线

借鉴 AstrBot 的流水线架构，将模型请求处理拆分为独立的阶段：
每个阶段可独立配置、热插拔，执行后可选择继续下一阶段或短路返回。

设计原则：
1. 阶段化：每个 PipelineStage 是独立的功能单元
2. 上下文传递：PipelineContext 在阶段间传递，累积结果
3. 短路机制：任何阶段可决定中断流水线并直接返回
4. 可观测：每个阶段的耗时/成功/失败都有记录
5. 类型安全：使用 dataclass 和 Enum 确保类型正确

v2.0 新增 洋葱模型：
- OnionPipelineStage: 支持 AsyncGenerator pre/post 处理
- OnionPipelineScheduler: 检测 AsyncGenerator，递归嵌套执行

使用方式：
  scheduler = OnionPipelineScheduler()
  scheduler.add_stage(MyPreProcessStage())      # 前置：返回 AsyncGenerator
  scheduler.add_stage(ModelInferenceStage())   # 核心：普通 PipelineStage
  scheduler.add_stage(MyPostProcessStage())    # 后置：sync
  result = await scheduler.execute(context)
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger("pipeline")


# ── 阶段结果 ──────────────────────────────────────────────


class StageDecision(str, Enum):
    """阶段决策"""
    CONTINUE = "continue"           # 继续下一阶段
    SHORT_CIRCUIT = "short_circuit" # 短路，直接返回
    SKIP_REMAINING = "skip_remaining"  # 跳过后续阶段但返回当前上下文
    ERROR = "error"                 # 错误但可恢复（记录后继续）


@dataclass
class StageResult:
    """单个阶段执行结果"""
    stage_name: str
    decision: StageDecision = StageDecision.CONTINUE
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: int = 0


# ── 流水线上下文 ──────────────────────────────────────────


@dataclass
class PipelineContext:
    """
    流水线上下文 —— 在阶段间传递的共享状态

    核心字段：
    - request_data: 原始请求数据（任意类型，由调用方定义）
    - metadata: 元数据字典（阶段间共享的信息）
    - stage_results: 所有已执行阶段的结果列表
    - final_output: 最终输出（如果有）
    - is_cancelled: 是否被取消
    """
    request_data: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)
    stage_results: list[StageResult] = field(default_factory=list)
    final_output: Any = None
    is_cancelled: bool = False
    start_time: float = field(default_factory=time.perf_counter)

    @property
    def total_latency_ms(self) -> int:
        """总耗时（毫秒）"""
        return int((time.perf_counter() - self.start_time) * 1000)

    def set_output(self, output: Any) -> None:
        """设置最终输出"""
        self.final_output = output

    def cancel(self, reason: str = "") -> None:
        """取消流水线"""
        self.is_cancelled = True
        self.metadata["cancel_reason"] = reason


# ── 抽象阶段基类 ──────────────────────────────────────────


class PipelineStage(ABC):
    """
    流水线阶段抽象基类

    子类实现 execute() 方法，返回 StageResult。

    可选重写：
    - stage_name: 阶段名称（默认使用类名）
    - priority: 阶段优先级（数字越小越先执行，默认 100）
    - enabled: 是否启用（默认 True）
    """

    stage_name: str = ""
    priority: int = 100
    enabled: bool = True

    @abstractmethod
    async def execute(self, context: PipelineContext) -> StageResult:
        """执行阶段逻辑，返回执行结果"""
        ...

    async def on_error(self, context: PipelineContext, error: Exception) -> StageResult:
        """阶段异常时的默认处理（可重写）"""
        logger.error(
            "Pipeline stage '%s' error: %s",
            self.stage_name or self.__class__.__name__,
            str(error)[:200],
        )
        return StageResult(
            stage_name=self.stage_name or self.__class__.__name__,
            decision=StageDecision.CONTINUE,
            error=str(error)[:200],
        )


# ── 流水线调度器 ──────────────────────────────────────────


class PipelineScheduler:
    """
    流水线调度器 —— 管理阶段注册和流水线执行

    特性：
    - 阶段按 priority 排序执行
    - 支持运行中动态添加/移除阶段
    - 每个阶段的耗时自动记录
    - 全局预/后置钩子
    - 可观测性：完整执行日志
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._stages: list[PipelineStage] = []
        self._pre_hooks: list[Callable[[PipelineContext], None]] = []
        self._post_hooks: list[Callable[[PipelineContext], None]] = []

    # ── 阶段管理 ───────────────────────────────────────

    def add_stage(self, stage: PipelineStage) -> PipelineScheduler:
        """添加流水线阶段（支持链式调用）"""
        self._stages.append(stage)
        self._stages.sort(key=lambda s: s.priority)
        logger.debug("Pipeline '%s': added stage '%s' (priority=%d)", self.name, stage.stage_name, stage.priority)
        return self

    def remove_stage(self, stage_name: str) -> bool:
        """按名称移除阶段"""
        before = len(self._stages)
        self._stages = [s for s in self._stages if s.stage_name != stage_name]
        return len(self._stages) < before

    def get_stage(self, stage_name: str) -> PipelineStage | None:
        """按名称获取阶段"""
        for s in self._stages:
            if s.stage_name == stage_name:
                return s
        return None

    def set_stage_enabled(self, stage_name: str, enabled: bool) -> bool:
        """启用/禁用一个阶段"""
        stage = self.get_stage(stage_name)
        if stage:
            stage.enabled = enabled
            logger.info("Pipeline '%s': stage '%s' %s", self.name, stage_name, "enabled" if enabled else "disabled")
            return True
        return False

    @property
    def stages(self) -> list[PipelineStage]:
        """获取所有已注册的阶段"""
        return list(self._stages)

    @property
    def enabled_stages(self) -> list[PipelineStage]:
        """获取所有已启用的阶段"""
        return [s for s in self._stages if s.enabled]

    # ── 钩子管理 ───────────────────────────────────────

    def add_pre_hook(self, hook: Callable[[PipelineContext], None]) -> PipelineScheduler:
        """添加前置钩子（在所有阶段执行前调用）"""
        self._pre_hooks.append(hook)
        return self

    def add_post_hook(self, hook: Callable[[PipelineContext], None]) -> PipelineScheduler:
        """添加后置钩子（在所有阶段执行后调用）"""
        self._post_hooks.append(hook)
        return self

    # ── 执行 ───────────────────────────────────────────

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """
        执行完整流水线

        流程：
          1. 执行前置钩子
          2. 按优先级依次执行已启用的阶段
          3. 处理阶段决策：CONTINUE → 下一阶段 / SHORT_CIRCUIT → 停止
          4. 执行后置钩子
          5. 返回最终的 PipelineContext
        """
        logger.info("Pipeline '%s': starting execution (stages: %d)", self.name, len(self.enabled_stages))

        # 前置钩子
        for hook in self._pre_hooks:
            try:
                hook(context)
            except Exception as e:
                logger.warning("Pipeline '%s': pre-hook error: %s", self.name, e)

        # 执行阶段序列
        for stage in self.enabled_stages:
            if context.is_cancelled:
                logger.info("Pipeline '%s': cancelled, skipping remaining stages", self.name)
                break

            stage_start = time.perf_counter()

            try:
                result = await stage.execute(context)
            except Exception as e:
                result = await stage.on_error(context, e)

            result.latency_ms = int((time.perf_counter() - stage_start) * 1000)
            context.stage_results.append(result)

            logger.debug(
                "Pipeline '%s': stage '%s' → %s (%dms)",
                self.name,
                result.stage_name,
                result.decision.value,
                result.latency_ms,
            )

            # 处理阶段决策
            if result.decision == StageDecision.SHORT_CIRCUIT:
                logger.info("Pipeline '%s': short-circuited by stage '%s'", self.name, result.stage_name)
                break
            elif result.decision == StageDecision.SKIP_REMAINING:
                logger.info("Pipeline '%s': remaining stages skipped by '%s'", self.name, result.stage_name)
                break
            elif result.decision == StageDecision.ERROR and result.error:
                logger.warning(
                    "Pipeline '%s': stage '%s' error (recoverable): %s",
                    self.name,
                    result.stage_name,
                    result.error,
                )
            # CONTINUE: 继续下一阶段

        # 后置钩子
        for hook in self._post_hooks:
            try:
                hook(context)
            except Exception as e:
                logger.warning("Pipeline '%s': post-hook error: %s", self.name, e)

        logger.info(
            "Pipeline '%s': completed in %dms (%d stages executed)",
            self.name,
            context.total_latency_ms,
            len(context.stage_results),
        )

        return context

    def get_execution_summary(self, context: PipelineContext) -> dict[str, Any]:
        """获取执行摘要（用于日志/监控）"""
        return {
            "pipeline": self.name,
            "total_latency_ms": context.total_latency_ms,
            "stages_executed": len(context.stage_results),
            "short_circuited": any(
                r.decision == StageDecision.SHORT_CIRCUIT for r in context.stage_results
            ),
            "errors": [
                {"stage": r.stage_name, "error": r.error}
                for r in context.stage_results
                if r.error
            ],
            "stage_details": [
                {
                    "name": r.stage_name,
                    "decision": r.decision.value,
                    "latency_ms": r.latency_ms,
                    "has_error": r.error is not None,
                }
                for r in context.stage_results
            ],
        }


# ── 洋葱模型阶段 ──────────────────────────────────────────

class OnionPipelineStage(PipelineStage):
    """
    洋葱模型阶段 —— 支持 pre/post 两部分处理

    借鉴 AstrBot 的 AsyncGenerator 模式：
    - process_async() 返回 AsyncGenerator
    - yield 之前 = 前置处理（pre-processing）
    - yield 之后 = 后置处理（post-processing）
    - 调度器在 yield 点暂停，递归进入后续阶段，完成后回到后置处理

    用法:
        class MyStage(OnionPipelineStage):
            stage_name = "my_stage"
            priority = 50

            async def process_async(self, context):
                # ── 前置：校验/增强上下文 ──
                context.metadata["checked"] = True
                yield  # ← 暂停点，后续所有阶段在此执行
                # ── 后置：清理/格式化 ──
                context.metadata["cleaned"] = True
    """

    stage_name: str = "onion_stage"

    async def process_async(self, context: PipelineContext) -> AsyncGenerator[None]:
        """洋葱模型处理（yield 前 = 前置，yield 后 = 后置）"""
        yield

    async def execute(self, context: PipelineContext) -> StageResult:
        """由调度器内部处理，不应直接调用"""
        return StageResult(
            stage_name=self.stage_name or self.__class__.__name__,
            decision=StageDecision.CONTINUE,
        )


# ── 洋葱模型调度器 ────────────────────────────────────────

class OnionPipelineScheduler(PipelineScheduler):
    """
    洋葱模型流水线调度器

    与 PipelineScheduler 的区别：
    - PipelineScheduler: 按顺序 await 每个阶段（线性执行）
    - OnionPipelineScheduler: 检测 AsyncGenerator，支持 pre/post 嵌套执行

    核心逻辑：
      for stage in enabled:
          if isinstance(stage, OnionPipelineStage):
              gen = stage.process_async(context)
              if gen is AsyncGenerator:
                  async for _ in gen:
                      # 前置已执行 → 递归执行后续阶段
                      await self._execute_onion(context, next_idx)
                      # 后续已完成 → 回到后置处理
              else:
                  await stage.execute(context)
          else:
              result = await stage.execute(context)
    """

    async def execute(self, context: PipelineContext) -> PipelineContext:
        """洋葱模型执行入口"""
        logger.info(
            "OnionPipeline '%s': starting execution (stages: %d)",
            self.name, len(self.enabled_stages),
        )

        # 前置钩子
        for hook in self._pre_hooks:
            try:
                hook(context)
            except Exception as e:
                logger.warning("OnionPipeline '%s': pre-hook error: %s", self.name, e)

        # 洋葱模型执行
        await self._execute_onion(context)

        # 后置钩子
        for hook in self._post_hooks:
            try:
                hook(context)
            except Exception as e:
                logger.warning("OnionPipeline '%s': post-hook error: %s", self.name, e)

        logger.info(
            "OnionPipeline '%s': completed in %dms (%d stages executed)",
            self.name, context.total_latency_ms, len(context.stage_results),
        )
        return context

    async def _execute_onion(
        self,
        context: PipelineContext,
        start_from: int = 0,
    ) -> None:
        """
        洋葱模型递归执行器

        借鉴 AstrBot PipelineScheduler._process_stages() 的递归模式。

        Args:
            context: 流水线上下文
            start_from: 起始阶段索引（支持从中间开始执行）
        """
        enabled = self.enabled_stages

        i: int = start_from
        while i < len(enabled):
            if context.is_cancelled:
                break

            stage = enabled[i]
            stage_start = time.perf_counter()

            try:
                if isinstance(stage, OnionPipelineStage):
                    gen = stage.process_async(context)
                    if isinstance(gen, AsyncGenerator):
                        # ── 洋葱路径：前置 → yield → 后续 → 后置 ──
                        async for _ in gen:
                            if not context.is_cancelled:
                                await self._execute_onion(context, start_from=i + 1)
                        result = StageResult(
                            stage_name=stage.stage_name,
                            decision=StageDecision.CONTINUE,
                        )
                    else:
                        result = await stage.execute(context)
                else:
                    # ── 普通路径：直接执行 ──
                    result = await stage.execute(context)

            except Exception as e:
                result = await stage.on_error(context, e)

            result.latency_ms = int((time.perf_counter() - stage_start) * 1000)
            context.stage_results.append(result)

            logger.debug(
                "OnionPipeline '%s': stage '%s' → %s (%dms)",
                self.name, result.stage_name, result.decision.value, result.latency_ms,
            )

            # 处理阶段决策
            if result.decision == StageDecision.SHORT_CIRCUIT:
                logger.info(
                    "OnionPipeline '%s': short-circuited by '%s'",
                    self.name, result.stage_name,
                )
                break
            elif result.decision == StageDecision.SKIP_REMAINING:
                logger.info(
                    "OnionPipeline '%s': remaining skipped by '%s'",
                    self.name, result.stage_name,
                )
                break

            i += 1


# ── 全局流水线单例 ────────────────────────────────────────


_pipelines: dict[str, PipelineScheduler] = {}
_onion_pipelines: dict[str, OnionPipelineScheduler] = {}


def get_pipeline(name: str = "default") -> PipelineScheduler:
    """获取或创建一个命名的流水线调度器"""
    global _pipelines
    if name not in _pipelines:
        _pipelines[name] = PipelineScheduler(name=name)
    return _pipelines[name]


def get_onion_pipeline(name: str = "default") -> OnionPipelineScheduler:
    """获取或创建一个命名的洋葱模型流水线调度器"""
    global _onion_pipelines
    if name not in _onion_pipelines:
        _onion_pipelines[name] = OnionPipelineScheduler(name=name)
    return _onion_pipelines[name]
