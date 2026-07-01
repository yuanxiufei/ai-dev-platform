"""
Agent Pipeline — 借鉴 cognee 的 @task 装饰器 + run_pipeline 延迟调用模式

核心设计：
  Level 1: @step 装饰器 → StepSpec（只定义，不执行）
  Level 2: 调用 StepSpec → BoundStep（绑定参数，不执行）
  Level 3: run_pipeline() → 按序执行 BoundStep 链

与 cognee 的对齐：
  - TaskSpec → StepSpec (定义步骤元数据)
  - Task → Step (具体执行单元)
  - BoundTask → BoundStep (绑定参数后的待执行状态)
  - run_pipeline → run_pipeline (编排器)

特点：
  - 每个 step 的 output 自动成为下一步 input
  - 支持 async function / coroutine / generator
  - 支持 batch_size 参数（批量处理上游数据）
  - 支持条件跳过（@step 的 condition 参数）
  - Pipeline 上下文传递（PipelineContext）
  - 与现有 AgentRunner 无缝集成
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, Union

logger = logging.getLogger("agent.pipeline")

T = TypeVar("T")


# ── 步骤定义 ─────────────────────────────────────────────

@dataclass
class StepSpec:
    """
    步骤规格 — 由 @step 装饰器创建

    借鉴 cognee TaskSpec：
      - name: 步骤名称
      - fn: 可执行函数
      - batch_size: 批量大小
      - enriches: 是否丰富上游数据（vs 替换）
      - condition: 条件函数（跳过此步骤时返回 False）
      - default_params: 默认参数（可被调用时覆盖）
    """
    name: str
    fn: Callable
    batch_size: int = 1
    enriches: bool = False
    condition: Callable[[PipelineContext], bool] | None = None
    default_params: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)

    def __call__(self, **kwargs) -> BoundStep:
        """
        调用 StepSpec 并不执行函数，而是返回 BoundStep

        借鉴 cognee TaskSpec.__call__ → BoundTask。
        """
        merged = {**self.default_params, **kwargs}
        return BoundStep(self, kwargs=merged)

    def with_config(self, **kwargs) -> StepSpec:
        """创建带有更新配置的新 StepSpec"""
        new = StepSpec(
            name=self.name,
            fn=self.fn,
            batch_size=kwargs.get("batch_size", self.batch_size),
            enriches=kwargs.get("enriches", self.enriches),
            condition=kwargs.get("condition", self.condition),
            default_params={**self.default_params, **kwargs.get("default_params", {})},
            dependencies=list(kwargs.get("dependencies", self.dependencies)),
        )
        return new


@dataclass
class BoundStep:
    """已绑定参数但尚未执行的步骤"""
    spec: StepSpec
    kwargs: dict[str, Any] = field(default_factory=dict)

    @property
    def name(self) -> str:
        return self.spec.name

    @property
    def fn(self) -> Callable:
        return self.spec.fn

    @property
    def condition(self) -> Callable | None:
        return self.spec.condition

    @property
    def dependencies(self) -> list[str]:
        return self.spec.dependencies

    @property
    def batch_size(self) -> int:
        return self.spec.batch_size


# ── Pipeline 上下文 ───────────────────────────────────────

@dataclass
class PipelineContext:
    """管道执行上下文"""
    pipeline_name: str = "default"
    data: Any = None
    step_outputs: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False

    def get_output(self, step_name: str, default: Any = None) -> Any:
        return self.step_outputs.get(step_name, default)

    def set_output(self, step_name: str, value: Any) -> None:
        self.step_outputs[step_name] = value


# ── @step 装饰器 ─────────────────────────────────────────

def step(
    fn=None,
    *,
    name: str | None = None,
    batch_size: int = 1,
    enriches: bool = False,
    condition: Callable[[PipelineContext], bool] | None = None,
    **default_params,
):
    """
    将函数标记为管道步骤

    用法：
      @step
      async def classify(data, ctx): ...

      @step(name="extract_entities", batch_size=10)
      async def extract(chunks, model=None): ...

      @step(condition=lambda ctx: ctx.data.get("mode") == "production")
      async def deploy(data): ...
    """
    def decorator(func):
        step_name = name or func.__name__
        return StepSpec(
            name=step_name,
            fn=func,
            batch_size=batch_size,
            enriches=enriches,
            condition=condition,
            default_params=default_params,
        )

    if fn is not None:
        return decorator(fn)
    return decorator


# ── Pipeline 类 ──────────────────────────────────────────

@dataclass
class PipelineResult:
    """Pipeline 执行结果"""
    pipeline_name: str
    outputs: dict[str, Any] = field(default_factory=dict)
    steps_executed: int = 0
    steps_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    final_data: Any = None

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> dict[str, Any]:
        return {
            "pipeline": self.pipeline_name,
            "success": self.success,
            "steps_executed": self.steps_executed,
            "steps_skipped": self.steps_skipped,
            "errors": self.errors,
        }


class Pipeline:
    """
    Pipeline 构建器 — 收集步骤并按序执行

    用法:
      pipeline = Pipeline(name="code_review")
      pipeline.add(classify)\
              .add(analyze, depth=3)\
              .add(report)

      result = await pipeline.run(data=code_diff)
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._steps: list[BoundStep] = []

    def add(self, step_or_spec, **kwargs) -> Pipeline:
        """添加步骤"""
        if isinstance(step_or_spec, StepSpec):
            bound = step_or_spec(**kwargs)
        elif isinstance(step_or_spec, BoundStep):
            bound = step_or_spec
        else:
            raise TypeError(f"Expected StepSpec or BoundStep, got {type(step_or_spec)}")
        self._steps.append(bound)
        return self

    def add_if(self, condition: bool, step_or_spec, **kwargs) -> Pipeline:
        """条件添加"""
        if condition:
            self.add(step_or_spec, **kwargs)
        return self

    def get_step(self, name: str) -> BoundStep | None:
        for s in self._steps:
            if s.name == name:
                return s
        return None

    async def run(self, data: Any = None) -> PipelineResult:
        """执行管道"""
        return await run_pipeline(self._steps, data=data, pipeline_name=self.name)


# ── run_pipeline — 步骤编排器 ─────────────────────────────

async def run_pipeline(
    steps: list[BoundStep],
    data: Any = None,
    pipeline_name: str = "pipeline",
) -> PipelineResult:
    """
    按序执行 BoundStep 列表

    借鉴 cognee run_pipeline:
      - 逐步传递数据 (output → next input)
      - 支持 condition 跳过
      - 记录每个步骤的输出
    """
    ctx = PipelineContext(pipeline_name=pipeline_name, data=data)
    result = PipelineResult(pipeline_name=pipeline_name)

    for i, step in enumerate(steps):
        if ctx.cancelled:
            break

        # 条件检查
        if step.condition and not step.condition(ctx):
            logger.info("Pipeline '%s': step '%s' skipped (condition=False)", pipeline_name, step.name)
            result.steps_skipped += 1
            continue

        logger.info(
            "Pipeline '%s': step %d/%d '%s' executing...",
            pipeline_name, i + 1, len(steps), step.name,
        )

        try:
            # 检查函数签名，确定传递方式
            sig = inspect.signature(step.fn)
            params = list(sig.parameters.keys())

            # 构建调用参数
            call_kwargs: dict[str, Any] = {}

            # 如果签名接受 data, ctx 参数
            if "data" in params:
                call_kwargs["data"] = ctx.data
            if "ctx" in params:
                call_kwargs["ctx"] = ctx

            # 合并绑定的 kwargs
            call_kwargs.update(step.kwargs)

            # 调用步骤函数
            output = step.fn(**call_kwargs)
            if inspect.isawaitable(output):
                output = await output

            # 处理 async generator
            if inspect.isasyncgen(output):
                collected = []
                async for item in output:
                    collected.append(item)
                output = collected if len(collected) > 1 else (collected[0] if collected else None)

            # recording output
            ctx.set_output(step.name, output)

            # 如果 step.enriches，保留原始 data 并附加步骤输出
            if step.enriches:
                if isinstance(ctx.data, dict):
                    ctx.data[step.name] = output
            else:
                ctx.data = output

            result.steps_executed += 1
            logger.info(
                "Pipeline '%s': step '%s' completed",
                pipeline_name, step.name,
            )

        except Exception as e:
            logger.error(
                "Pipeline '%s': step '%s' failed: %s",
                pipeline_name, step.name, str(e)[:300],
            )
            result.errors.append(f"{step.name}: {str(e)[:200]}")

    result.outputs = dict(ctx.step_outputs)
    result.final_data = ctx.data
    return result


# ── DSL 快捷构建 ─────────────────────────────────────────

def create_pipeline(name: str = "default") -> Pipeline:
    """创建新管道"""
    return Pipeline(name=name)


def define_pipeline(name: str, *steps: BoundStep | StepSpec, **step_kwargs) -> Pipeline:
    """
    快捷定义管道

    用法:
      p = define_pipeline("review",
        classify(threshold=0.8),
        analyze(depth=3),
        report,
      )
      result = await p.run(data=my_data)
    """
    p = Pipeline(name=name)
    for s in steps:
        if isinstance(s, StepSpec):
            p.add(s, **step_kwargs)
        else:
            p.add(s)
    return p


# ── 示例步骤函数 ─────────────────────────────────────────

@step(name="noop")
async def noop_step(data: Any = None, **kwargs) -> Any:
    """空操作步骤 — 直接传递数据"""
    return data


@step(name="log_data")
async def log_data_step(data: Any = None, **kwargs) -> Any:
    """记录数据内容"""
    preview = str(data)[:200] if data else "None"
    logger.info("Pipeline data: %s", preview)
    return data
