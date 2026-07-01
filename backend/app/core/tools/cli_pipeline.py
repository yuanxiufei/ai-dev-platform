"""
AutoCLI 流水线组合 — 借鉴 AutoCLI 的 YAML 适配器 + 流水线组合设计

功能：
  - 从 YAML 文件加载多步骤 CLI 工作流
  - 支持串行 / 并行 / 条件执行
  - 支持步骤间的变量传递（{{step.output.stdout}}）
  - 安全级别逐步提升（每步独立安全检查）
  - 嵌套子流水线引用

YAML 格式示例:
```yaml
name: setup-project
steps:
  - id: check-node
    command: node --version
    description: "Check Node.js version"
    
  - id: install-deps
    command: pnpm install
    description: "Install dependencies"
    depends_on: [check-node]
    cwd: ${WORKSPACE}
    
  - id: lint
    command: pnpm lint
    description: "Run linter"
    depends_on: [install-deps]
    parallel: [test]
    
  - id: test
    command: pnpm test
    description: "Run tests"
    depends_on: [install-deps]
    parallel: [lint]
    condition: "{{install-deps.exit_code}} == 0"
    max_retries: 2
    timeout: 120
```

执行模式:
  - serial: 顺序执行
  - parallel: 同时执行（无依赖关系）
  - depends_on: 等待上游步骤完成
  - condition: Jinja2 风格条件表达式
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import yaml

from app.core.tools.autocli import AutoCLI, CommandResult, SecurityLevel, get_autocli

logger = logging.getLogger("cli_pipeline")


# ── 步骤定义 ─────────────────────────────────────────────

class PipelineStep:
    """单个流水线步骤"""

    def __init__(
        self,
        step_id: str,
        command: str,
        description: str = "",
        depends_on: list[str] | None = None,
        parallel_with: list[str] | None = None,
        condition: str | None = None,
        cwd: str = "",
        timeout: float = 30.0,
        allow_unsafe: bool = False,
        max_retries: int = 0,
        retry_delay: float = 1.0,
        env: dict[str, str] | None = None,
        on_failure: str = "stop",  # stop | continue | retry
    ):
        self.id = step_id
        self.command = command
        self.description = description
        self.depends_on = depends_on or []
        self.parallel_with = parallel_with or []
        self.condition = condition
        self.cwd = cwd
        self.timeout = timeout
        self.allow_unsafe = allow_unsafe
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.env = env or {}
        self.on_failure = on_failure

        # 运行时状态
        self.result: CommandResult | None = None
        self.status: str = "pending"  # pending | running | success | failed | skipped
        self.error: str = ""
        self.retry_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command,
            "description": self.description,
            "status": self.status,
            "exit_code": self.result.exit_code if self.result else None,
            "stdout_preview": self.result.stdout[:200] if self.result else "",
            "stderr_preview": self.result.stderr[:200] if self.result else "",
            "latency_ms": round(self.result.latency_ms) if self.result else 0,
            "error": self.error,
            "retry_count": self.retry_count,
        }


# ── 管道执行上下文 ──────────────────────────────────────

class PipelineExecutionContext:
    """管道执行上下文 — 变量作用域和步骤输出存储"""

    def __init__(self, variables: dict[str, Any] | None = None):
        self.variables = variables or {}
        self.step_outputs: dict[str, dict[str, Any]] = {}
        self.start_time = time.perf_counter()

    def resolve(self, template: str) -> str:
        """
        解析模板字符串

        支持格式:
          {{step_id.stdout}} — 步骤的 stdout
          {{step_id.exit_code}} — 步骤的退出码
          {{$VARNAME}} — 上下文变量
          ${ENV_VAR} — 环境变量
        """
        # 解析 {{step.attribute}} 模式
        def _replace_step(match):
            full = match.group(1)
            if "." in full:
                step_id, attr = full.rsplit(".", 1)
            else:
                step_id = full
                attr = "stdout"

            output = self.step_outputs.get(step_id, {})
            value = output.get(attr, "")
            return str(value)

        result = re.sub(r"\{\{(.+?)\}\}", _replace_step, template)

        # 解析 ${VAR} 模式
        def _replace_var(match):
            var = match.group(1)
            if var.startswith("$"):
                return str(self.variables.get(var[1:], ""))
            return os.environ.get(var, match.group(0))

        result = re.sub(r"\$\{([^}]+)\}", _replace_var, result)

        return result

    def evaluate_condition(self, condition: str) -> bool:
        """
        评估条件表达式

        格式: "{{step_id.exit_code}} == 0" or "{{step_id.status}} == 'success'"
        """
        if not condition:
            return True

        try:
            # 先解析模板变量
            resolved = self.resolve(condition)

            # 安全的表达式评估：只支持 == 和 != 比较
            if "==" in resolved:
                left, right = resolved.split("==", 1)
                return left.strip() == right.strip()
            if "!=" in resolved:
                left, right = resolved.split("!=", 1)
                return left.strip() != right.strip()
            if resolved.strip().lower() in ("true", "1", "yes"):
                return True
            if resolved.strip().lower() in ("false", "0", "no"):
                return False

            # 默认：非空为 True
            return bool(resolved.strip())

        except Exception as e:
            logger.warning("Condition evaluation failed: '%s' — %s", condition, e)
            return True  # 默认通过


# ── CLI 管道加载器 ─────────────────────────────────────

class CLIPipelineLoader:
    """从 YAML 文件加载 CLI 管道"""

    @staticmethod
    def load(file_path: str) -> CLIPipeline:
        """
        从 YAML 文件加载管道

        Args:
            file_path: YAML 文件路径

        Returns:
            CLIPipeline 实例
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Pipeline YAML not found: {file_path}")

        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        name = config.get("name", path.stem)
        description = config.get("description", "")
        steps_config = config.get("steps", [])

        steps: list[PipelineStep] = []
        for i, sc in enumerate(steps_config):
            step = PipelineStep(
                step_id=sc.get("id", f"step_{i}"),
                command=sc["command"],
                description=sc.get("description", ""),
                depends_on=sc.get("depends_on", []),
                parallel_with=sc.get("parallel", []),
                condition=sc.get("condition"),
                cwd=sc.get("cwd", ""),
                timeout=sc.get("timeout", 30.0),
                allow_unsafe=sc.get("allow_unsafe", False),
                max_retries=sc.get("max_retries", 0),
                retry_delay=sc.get("retry_delay", 1.0),
                env=sc.get("env", {}),
                on_failure=sc.get("on_failure", "stop"),
            )
            steps.append(step)

        return CLIPipeline(
            name=name,
            description=description,
            steps=steps,
            variables=config.get("variables", {}),
            source_path=str(path),
        )

    @staticmethod
    def load_from_string(yaml_content: str, name: str = "inline") -> CLIPipeline:
        """从 YAML 字符串加载管道"""
        config = yaml.safe_load(yaml_content)
        return CLIPipeline(
            name=config.get("name", name),
            description=config.get("description", ""),
            steps=[
                PipelineStep(
                    step_id=sc.get("id", f"step_{i}"),
                    command=sc["command"],
                    description=sc.get("description", ""),
                    depends_on=sc.get("depends_on", []),
                    parallel_with=sc.get("parallel", []),
                    condition=sc.get("condition"),
                    cwd=sc.get("cwd", ""),
                    timeout=sc.get("timeout", 30.0),
                    allow_unsafe=sc.get("allow_unsafe", False),
                    max_retries=sc.get("max_retries", 0),
                    retry_delay=sc.get("retry_delay", 1.0),
                    env=sc.get("env", {}),
                    on_failure=sc.get("on_failure", "stop"),
                )
                for i, sc in enumerate(config.get("steps", []))
            ],
            variables=config.get("variables", {}),
            source_path=yaml_content,
        )


# ── CLI 管道执行器 ──────────────────────────────────────

class CLIPipeline:
    """
    CLI 管道 — 多步骤命令行工作流

    用法:
      # 从文件加载
      pipeline = CLIPipelineLoader.load("pipelines/setup.yaml")
      result = await pipeline.run()

      # 代码构建
      pipeline = CLIPipeline(name="build", steps=[
          PipelineStep("check", "node --version"),
          PipelineStep("build", "pnpm build", depends_on=["check"]),
      ])
      result = await pipeline.run()
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        steps: list[PipelineStep] | None = None,
        variables: dict[str, Any] | None = None,
        source_path: str = "",
        autocli: AutoCLI | None = None,
    ):
        self.name = name
        self.description = description
        self.steps = steps or []
        self.variables = variables or {}
        self.source_path = source_path
        self._autocli = autocli

        # 运行时状态
        self.ctx = PipelineExecutionContext(variables=variables)

    @property
    def autocli(self) -> AutoCLI:
        if self._autocli is None:
            self._autocli = get_autocli()
        return self._autocli

    async def run(self) -> PipelineResult:
        """
        执行所有步骤

        执行策略:
          1. 按 depends_on 拓扑排序
          2. parallel_with 批并行执行
          3. 步骤间的变量传递
        """
        self.ctx = PipelineExecutionContext(variables=self.variables)
        logger.info("CLI Pipeline '%s': starting execution (%d steps)", self.name, len(self.steps))

        if not self.steps:
            return PipelineResult(
                pipeline_name=self.name,
                steps=[],
            )

        # 拓扑排序（按依赖关系分组）
        execution_groups = self._topo_sort()

        for group_idx, group in enumerate(execution_groups):
            logger.info(
                "CLI Pipeline '%s': group %d/%d executing (%d steps)",
                self.name, group_idx + 1, len(execution_groups), len(group),
            )

            # 并行执行同组步骤
            tasks = [
                self._execute_step_with_retries(step)
                for step in group
            ]
            await asyncio.gather(*tasks)

            # 检查是否需要终止
            should_stop = False
            for step in group:
                if step.status == "failed" and step.on_failure == "stop":
                    should_stop = True
                    logger.error(
                        "CLI Pipeline '%s': stopping at step '%s' (on_failure=stop)",
                        self.name, step.id,
                    )

            if should_stop:
                # 标记剩余步骤为 skipped
                for remaining_group in execution_groups[group_idx + 1:]:
                    for step in remaining_group:
                        step.status = "skipped"
                        step.error = f"Skipped due to failure in group {group_idx}"
                break

        elapsed = time.perf_counter() - self.ctx.start_time
        step_results = [
            PipelineStepResult(
                step_id=s.id,
                command=s.command,
                description=s.description,
                status=s.status,
                exit_code=s.result.exit_code if s.result else -1,
                stdout=s.result.stdout if s.result else "",
                stderr=s.result.stderr if s.result else "",
                latency_ms=round(s.result.latency_ms) if s.result else 0,
                error=s.error,
                retry_count=s.retry_count,
            )
            for s in self.steps
        ]

        result = PipelineResult(
            pipeline_name=self.name,
            steps=step_results,
            total_latency_ms=round(elapsed * 1000),
        )

        logger.info(
            "CLI Pipeline '%s': completed. %d steps: %s",
            self.name,
            len(step_results),
            result.breakdown(),
        )

        return result

    async def _execute_step_with_retries(self, step: PipelineStep) -> None:
        """执行步骤（含重试逻辑）"""
        while step.retry_count <= step.max_retries:
            if step.retry_count > 0:
                logger.info(
                    "CLI Pipeline '%s': retrying step '%s' (%d/%d)",
                    self.name, step.id, step.retry_count, step.max_retries,
                )
                await asyncio.sleep(step.retry_delay)

            await self._execute_step(step)

            if step.status == "success":
                return
            if step.on_failure == "retry" and step.retry_count < step.max_retries:
                step.retry_count += 1
                continue
            break

    async def _execute_step(self, step: PipelineStep) -> None:
        """执行单个步骤"""

        # 1. 检查条件
        if step.condition:
            passes = self.ctx.evaluate_condition(step.condition)
            if not passes:
                logger.info(
                    "CLI Pipeline '%s': step '%s' skipped (condition not met: %s)",
                    self.name, step.id, step.condition,
                )
                step.status = "skipped"
                step.error = f"Condition not met: {step.condition}"
                return

        # 2. 检查依赖
        if step.depends_on:
            for dep_id in step.depends_on:
                dep_output = self.ctx.step_outputs.get(dep_id, {})
                if dep_output.get("status") != "success":
                    step.status = "skipped"
                    step.error = f"Dependency '{dep_id}' not completed successfully"
                    logger.warning(
                        "CLI Pipeline '%s': step '%s' skipped (dependency '%s' failed)",
                        self.name, step.id, dep_id,
                    )
                    return

        # 3. 解析命令
        resolved_cmd = self.ctx.resolve(step.command)
        logger.info(
            "CLI Pipeline '%s': step '%s' executing: %s",
            self.name, step.id, resolved_cmd,
        )
        step.status = "running"

        try:
            # 4. 设置工作目录
            if step.cwd:
                resolved_cwd = self.ctx.resolve(step.cwd)
                # 临时切换 workspace
                old_workspace = self._autocli._workspace
                self._autocli._workspace = resolved_cwd
                result = await self._autocli.execute(
                    resolved_cmd,
                    timeout=step.timeout,
                    allow_unsafe=step.allow_unsafe,
                )
                self._autocli._workspace = old_workspace
            else:
                result = await self._autocli.execute(
                    resolved_cmd,
                    timeout=step.timeout,
                    allow_unsafe=step.allow_unsafe,
                )

            step.result = result

            if result.success:
                step.status = "success"
                logger.info(
                    "CLI Pipeline '%s': step '%s' succeeded (exit=0, %.0fms)",
                    self.name, step.id, result.latency_ms,
                )
            else:
                step.status = "failed"
                step.error = result.stderr[:500] if result.stderr else f"exit_code={result.exit_code}"
                logger.warning(
                    "CLI Pipeline '%s': step '%s' failed (exit=%d): %s",
                    self.name, step.id, result.exit_code, step.error[:150],
                )

        except Exception as e:
            step.status = "failed"
            step.error = str(e)[:500]
            logger.error(
                "CLI Pipeline '%s': step '%s' exception: %s",
                self.name, step.id, str(e)[:300],
            )

        # 5. 保存结果到上下文
        self.ctx.step_outputs[step.id] = {
            "status": step.status,
            "stdout": step.result.stdout if step.result else "",
            "stderr": step.result.stderr if step.result else "",
            "exit_code": step.result.exit_code if step.result else -1,
            "latency_ms": round(step.result.latency_ms) if step.result else 0,
            "error": step.error,
        }

    def _topo_sort(self) -> list[list[PipelineStep]]:
        """
        拓扑排序 + 并行分组

        返回执行组列表，每组内的步骤可并行执行。
        """
        if not self.steps:
            return []

        step_map = {s.id: s for s in self.steps}
        in_degree: dict[str, int] = {s.id: 0 for s in self.steps}

        # 计算入度
        for s in self.steps:
            for dep in s.depends_on:
                if dep in in_degree:
                    in_degree[s.id] += 1

        # 也考虑 parallel 关系：若有 parallel，归入同一组
        # 但需要各自依赖满足才执行

        groups: list[list[PipelineStep]] = []
        remaining = set(step_map.keys())

        while remaining:
            # 找出当前可执行的步骤（入度为0）
            ready = {sid for sid in remaining if in_degree[sid] == 0}

            if not ready:
                # 循环依赖，剩余步骤为最后组
                last_group = [step_map[sid] for sid in remaining]
                groups.append(last_group)
                break

            group: list[PipelineStep] = []
            group_ids: set[str] = set()

            for sid in sorted(ready):
                step = step_map[sid]
                group.append(step)
                group_ids.add(sid)
                # 同一并行组的步骤
                for pid in step.parallel_with:
                    if pid in ready and pid not in group_ids:
                        pstep = step_map[pid]
                        group.append(pstep)
                        group_ids.add(pid)

            for sid in group_ids:
                remaining.discard(sid)
                # 减少依赖此步骤的后续步骤的入度
                for s in self.steps:
                    if sid in s.depends_on:
                        in_degree[s.id] -= 1

            groups.append(group)

        return groups

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "source_path": self.source_path,
        }


# ── Pipeline 结果 ─────────────────────────────────────────

class PipelineStepResult:
    def __init__(
        self,
        step_id: str,
        command: str,
        description: str,
        status: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        latency_ms: int,
        error: str = "",
        retry_count: int = 0,
    ):
        self.step_id = step_id
        self.command = command
        self.description = description
        self.status = status
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.latency_ms = latency_ms
        self.error = error
        self.retry_count = retry_count

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "command": self.command,
            "description": self.description,
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout_preview": self.stdout[:500],
            "stderr_preview": self.stderr[:500],
            "latency_ms": self.latency_ms,
            "error": self.error,
            "retry_count": self.retry_count,
        }


class PipelineResult:
    def __init__(
        self,
        pipeline_name: str,
        steps: list[PipelineStepResult],
        total_latency_ms: int = 0,
    ):
        self.pipeline_name = pipeline_name
        self.steps = steps
        self.total_latency_ms = total_latency_ms

    @property
    def success(self) -> bool:
        return all(s.status == "success" or s.status == "skipped" for s in self.steps)

    @property
    def failed_steps(self) -> list[PipelineStepResult]:
        return [s for s in self.steps if s.status == "failed"]

    def breakdown(self) -> str:
        statuses = ",".join(
            f"{s.step_id}={s.status}" for s in self.steps
        )
        return f"[{statuses}] total={self.total_latency_ms}ms"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pipeline_name": self.pipeline_name,
            "success": self.success,
            "total_latency_ms": self.total_latency_ms,
            "steps": [s.to_dict() for s in self.steps],
        }


# ── 工厂函数 ──────────────────────────────────────────────

def load_pipeline(file_path: str) -> CLIPipeline:
    """从 YAML 文件加载管道"""
    return CLIPipelineLoader.load(file_path)


def build_pipeline(
    name: str,
    steps: list[dict[str, Any]],
    variables: dict[str, Any] | None = None,
) -> CLIPipeline:
    """从字典构建管道（编程方式）"""
    pipeline_steps = [
        PipelineStep(
            step_id=s.get("id", f"step_{i}"),
            command=s["command"],
            description=s.get("description", ""),
            depends_on=s.get("depends_on", []),
            parallel_with=s.get("parallel", []),
            condition=s.get("condition"),
            cwd=s.get("cwd", ""),
            timeout=s.get("timeout", 30.0),
            allow_unsafe=s.get("allow_unsafe", False),
            max_retries=s.get("max_retries", 0),
            on_failure=s.get("on_failure", "stop"),
        )
        for i, s in enumerate(steps)
    ]
    return CLIPipeline(name=name, steps=pipeline_steps, variables=variables)
