"""
多 Agent 协同调度器 — Planner -> Coder -> Reviewer -> Tester 闭环

自主设计，借鉴 Agent-Reach 的 Planner/Coder/Reviewer/Tester 流水线模式
和 hermes-agent 的 think->act->observe->reflect 循环。

核心流程:
  Planner 分解任务 -> Coder 生成代码 -> Reviewer 审查
  -> Coder 修复 -> Tester 验证 -> Memory 保存
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger("agent.orchestrator")


# ── 子任务定义 ────────────────────────────────────

class TaskType(StrEnum):
    """任务类型"""
    ANALYZE = "analyze"       # 分析现有代码
    DESIGN = "design"         # 架构设计
    CODE = "code"            # 编码
    REFACTOR = "refactor"    # 重构
    FIX = "fix"              # 修复
    TEST = "test"            # 测试
    DOCUMENT = "document"    # 文档
    DEPLOY = "deploy"        # 部署


class TaskPriority(StrEnum):
    """任务优先级"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class SubTask:
    """子任务"""
    id: str
    task_type: TaskType
    description: str
    priority: TaskPriority = TaskPriority.MEDIUM
    depends_on: list[str] = field(default_factory=list)
    assignee: str = ""         # 分配的 Agent
    status: str = "pending"    # pending | running | done | failed
    result: str = ""
    error: str = ""


@dataclass
class Plan:
    """任务计划"""
    original_task: str
    subtasks: list[SubTask]
    context: dict = field(default_factory=dict)

    @property
    def ordered_tasks(self) -> list[SubTask]:
        """按依赖关系排序"""
        done: set[str] = set()
        ordered: list[SubTask] = []
        remaining = list(self.subtasks)

        while remaining:
            for task in list(remaining):
                if all(dep in done for dep in task.depends_on):
                    ordered.append(task)
                    done.add(task.id)
                    remaining.remove(task)
                    break
            else:
                # 循环依赖处理
                ordered.extend(remaining)
                break

        return ordered


# ── 调度结果 ──────────────────────────────────────

@dataclass
class OrchestrationResult:
    """协同调度结果"""
    success: bool
    plan: Plan | None = None
    results: dict[str, str] = field(default_factory=dict)
    review_issues: list[str] = field(default_factory=list)
    test_results: dict[str, Any] = field(default_factory=dict)
    total_latency_ms: float = 0
    error: str = ""

    def summary(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "task_count": len(self.plan.subtasks) if self.plan else 0,
            "completed": len(self.results),
            "issues_found": len(self.review_issues),
            "latency_ms": round(self.total_latency_ms),
            "error": self.error,
        }


# ── AgentOrchestrator ──────────────────────────────

class AgentOrchestrator:
    """
    多 Agent 协同调度器

    借鉴 Agent-Reach 的 Planner->Coder->Reviewer->Tester 流水线。
    通过 AgentRunner 运行每个子任务，复用 Middleware/Sandbox/TrajectoryRecorder。

    用法:
        orchestrator = AgentOrchestrator(model_router)
        result = await orchestrator.orchestrate(
            task="Build a REST API for user management",
            mode="full",  # full | code_only | review_only
        )

        # WorkflowGraph 引擎 (声明式状态图)
        await orchestrator.orchestrate(
            task="...",
            engine="workflow",  # 使用 LangGraph 风格声明式图
        )
    """

    # ── 支持的引擎 ──
    ENGINE_DIRECT = "direct"      # 直接执行 (传统流水线)
    ENGINE_WORKFLOW = "workflow"   # WorkflowGraph 声明式图

    def __init__(self, model_router=None):
        from app.core.model_router import get_model_router
        self._router = model_router or get_model_router()
        self._agent_runner = None  # 懒加载

    def _get_runner(self):
        """懒加载 AgentRunner（复用 Sandbox + Middleware + TrajectoryRecorder）"""
        if self._agent_runner is None:
            from app.core.agent.agent_runner import AgentRunner
            self._agent_runner = AgentRunner()
        return self._agent_runner

    async def orchestrate(
        self,
        task: str,
        mode: str = "full",
        context: dict | None = None,
        engine: str = ENGINE_DIRECT,
        human_input_mode: str = "terminate",
        git_auto_commit: bool = True,
    ) -> OrchestrationResult:
        """
        执行完整的 Agent 协同流水线

        Args:
            task: 用户任务描述
            mode: full (完整流水线) | code_only (仅生成) | review_only (仅审查)
            context: 额外上下文（代码库信息、记忆等）
            engine: direct (传统流水线) | workflow (声明式状态图)
            human_input_mode: never | terminate | always (借鉴 AutoGen)
            git_auto_commit: 是否自动 git add + commit (借鉴 Aider)
        """
        if engine == self.ENGINE_WORKFLOW:
            return await self._orchestrate_workflow(task, mode, context or {})
        start_time = time.perf_counter()
        result = OrchestrationResult(success=False)

        try:
            # Phase 1: Plan
            plan = await self._plan(task, context or {})
            result.plan = plan

            if not plan or not plan.subtasks:
                result.error = "Failed to create plan"
                return result

            logger.info("Orchestrator planned %d subtasks for: %s",
                        len(plan.subtasks), task[:80])

            # Phase 2: Execute subtasks (with context chain propagation)
            # 借鉴 CrewAI: 每个子任务执行时注入前置任务的输出作为上下文
            task_context_map: dict[str, str] = {}  # subtask_id -> result

            for subtask in plan.ordered_tasks:
                if mode == "review_only" and subtask.task_type != TaskType.TEST:
                    continue

                # 构建依赖上下文 (CrewAI context=[prev_task] 风格)
                stage_context = dict(context or {})
                stage_context["completed_tasks"] = {
                    dep_id: task_context_map[dep_id]
                    for dep_id in subtask.depends_on
                    if dep_id in task_context_map
                }
                # 注入上一阶段摘要 (如果有)
                if result.results:
                    prev_results = {
                        tid: (output[:200] + "..." if len(output) > 200 else output)
                        for tid, output in result.results.items()
                    }
                    stage_context["previous_stages"] = prev_results

                # 变量插值 (CrewAI {task_id.output} 风格)
                description = subtask.description
                for dep_id, dep_output in stage_context.get("completed_tasks", {}).items():
                    placeholder = f"{{{dep_id}}}"
                    if placeholder in description:
                        description = description.replace(
                            placeholder, dep_output[:500]
                        )

                subtask.status = "running"
                try:
                    output = await self._execute_subtask(
                        subtask, stage_context, description
                    )
                    subtask.result = output
                    subtask.status = "done"
                    result.results[subtask.id] = output
                    task_context_map[subtask.id] = output
                    logger.info("Subtask %s completed: %s",
                               subtask.id, subtask.description[:60])
                except Exception as e:
                    subtask.status = "failed"
                    subtask.error = str(e)
                    logger.error("Subtask %s failed: %s", subtask.id, e)

            # Phase 3: Review (if mode is full or review_only)
            if mode != "code_only":
                code_subtasks = [
                    s for s in plan.subtasks
                    if s.task_type in (TaskType.CODE, TaskType.FIX, TaskType.REFACTOR)
                    and s.status == "done"
                ]
                if code_subtasks:
                    review_issues = await self._review(
                        [s.result for s in code_subtasks], context or {}
                    )
                    result.review_issues = review_issues

                    if review_issues:
                        # 修复循环
                        fixed = await self._fix(review_issues, context or {})
                        result.results["fix_iteration"] = fixed

            # Phase 4: Save to Memory
            await self._save_to_memory(task, result)

            # 🆕 Git Auto-Commit (借鉴 Aider Git-Native 编辑)
            if git_auto_commit and result.success:
                try:
                    commit_msg, changed_files = await self._git_auto_commit(task)
                    if changed_files:
                        logger.info(
                            "Orchestrator: auto-committed %d files — %s",
                            len(changed_files), commit_msg,
                        )
                        result.results["git_commit"] = {
                            "message": commit_msg,
                            "files": changed_files,
                        }
                except Exception as e:
                    logger.warning("Orchestrator git auto-commit failed: %s", e)

            result.success = not result.error
            result.total_latency_ms = (time.perf_counter() - start_time) * 1000
            logger.info("Orchestration done in %.0fms, success=%s",
                       result.total_latency_ms, result.success)

        except Exception as e:
            result.error = f"Orchestration error: {e}"
            result.total_latency_ms = (time.perf_counter() - start_time) * 1000
            logger.exception("Orchestration failed")

        return result

    # ── Phase 实现 ──────────────────────────────────

    async def _plan(self, task: str, context: dict) -> Plan:
        """Planner: 将任务分解为子任务列表"""
        from app.core.model_router import ModelRequest, ModelCapability

        prompt = f"""You are a task planner. Decompose the following task into subtasks.

Task: {task}

Context: {context.get('summary', 'No context available')}

Respond with a JSON array of subtasks, each with:
- id: unique short identifier (e.g. "analyze_1", "code_1")
- type: one of [analyze, design, code, refactor, fix, test, document]
- description: what needs to be done
- priority: high/medium/low
- depends_on: list of subtask ids this depends on

Only include necessary tasks. Keep it concise.

Example response:
[
  {{"id": "analyze_1", "type": "analyze", "description": "Analyze existing codebase structure", "priority": "high", "depends_on": []}},
  {{"id": "code_1", "type": "code", "description": "Implement main feature", "priority": "high", "depends_on": ["analyze_1"]}}
]
"""
        request = ModelRequest(
            capability=ModelCapability.TEXT_GENERATION,
            prompt=prompt,
            max_tokens=2048,
            temperature=0.3,
        )
        response = await self._router.generate(request)

        subtasks = self._parse_plan_response(response.content or "", task)
        return Plan(original_task=task, subtasks=subtasks, context=context)

    def _parse_plan_response(self, response: str, task: str) -> list[SubTask]:
        """解析 Planner 的 JSON 响应"""
        import json
        import re

        # 尝试提取 JSON 数组
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if not match:
            # 回退：创建单个默认任务
            return [SubTask(
                id="task_1",
                task_type=TaskType.CODE,
                description=task,
                priority=TaskPriority.HIGH,
            )]

        try:
            items = json.loads(match.group())
            subtasks = []
            for i, item in enumerate(items):
                subtasks.append(SubTask(
                    id=item.get("id", f"task_{i+1}"),
                    task_type=TaskType(item.get("type", "code")),
                    description=item.get("description", str(item)),
                    priority=TaskPriority(item.get("priority", "medium")),
                    depends_on=item.get("depends_on", []),
                ))
            return subtasks
        except Exception:
            return [SubTask(
                id="task_1",
                task_type=TaskType.CODE,
                description=task,
                priority=TaskPriority.HIGH,
            )]

    async def _execute_subtask(
        self,
        subtask: SubTask,
        context: dict,
        description: str | None = None,
    ) -> str:
        """Coder: 通过 AgentRunner 执行子任务（复用 Middleware/Sandbox/TrajectoryRecorder）

        Args:
            subtask: 要执行的子任务
            context: 当前阶段的上下文（含 completed_tasks / previous_stages）
            description: 已插值后的任务描述 (CrewAI context chain 风格)
        """
        from app.core.agent.agent_config import AgentConfig

        # 根据任务类型确定 Agent 配置
        code_types = {TaskType.CODE, TaskType.FIX, TaskType.REFACTOR, TaskType.TEST}

        if subtask.task_type in code_types:
            config = AgentConfig(
                name=f"orchestrator-{subtask.task_type.value}",
                description=f"Orchestrator {subtask.task_type.value} agent",
                instructions=(
                    "You are a coding agent in a multi-agent orchestration pipeline. "
                    f"Your task type is: {subtask.task_type.value}.\n"
                    "Complete the assigned subtask thoroughly. "
                    "Use available tools to search code, read files, and verify your work."
                ),
                max_turns=5,
                enable_memory=False,
            )
        else:
            config = AgentConfig(
                name=f"orchestrator-{subtask.task_type.value}",
                description=f"Orchestrator {subtask.task_type.value} agent",
                instructions=(
                    "You are an analysis agent in a multi-agent orchestration pipeline. "
                    f"Your task type is: {subtask.task_type.value}.\n"
                    "Provide thorough analysis and clear responses."
                ),
                max_turns=3,
                enable_memory=False,
            )

        # CrewAI 风格: 构建含依赖任务结果的上下文
        desc = description or subtask.description
        context_parts = [f"Type: {subtask.task_type}",
                         f"Description: {desc}",
                         f"Priority: {subtask.priority}"]

        # 注入已完成的前置任务结果 (CrewAI context chain)
        if context.get("completed_tasks"):
            context_parts.append("\nResults from dependent tasks:")
            for dep_id, dep_result in context["completed_tasks"].items():
                context_parts.append(
                    f"  [{dep_id}]: {dep_result[:300]}"
                    + ("..." if len(dep_result) > 300 else "")
                )

        # 注入上一阶段摘要
        if context.get("previous_stages"):
            context_parts.append("\nPrevious stage summaries:")
            for stage_id, stage_result in context["previous_stages"].items():
                context_parts.append(f"  [{stage_id}]: {stage_result}")

        # 全局上下文
        if context.get("summary"):
            context_parts.append(f"\nContext: {context['summary']}")

        task_message = "\n".join(context_parts)
        task_message += "\n\nProvide a thorough and complete response."

        runner = self._get_runner()
        result = await runner.run(
            config=config,
            user_message=task_message,
            model_router=self._router,
        )

        if result.error:
            raise RuntimeError(f"Subtask {subtask.id} failed: {result.error}")

        return result.final_answer

    async def _review(self, code_outputs: list[str], context: dict) -> list[str]:
        """Reviewer: 审查生成的代码"""
        from app.core.model_router import ModelRequest, ModelCapability

        if not code_outputs:
            return []

        code_snippets = "\n---\n".join(code_outputs)
        prompt = f"""Review the following code for issues:

{code_snippets}

Focus on:
1. Security vulnerabilities
2. Performance issues
3. Code quality / best practices
4. Edge cases and error handling

Respond with a list of specific issues found. If no issues, say "No issues found."
"""
        request = ModelRequest(
            capability=ModelCapability.TEXT_GENERATION,
            prompt=prompt,
            max_tokens=2048,
            temperature=0.3,
        )
        response = await self._router.generate(request)
        content = response.content or ""

        if "no issues" in content.lower():
            return []

        # 按行分割问题
        issues = []
        for line in content.split("\n"):
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith("-") or line.startswith("*")):
                # 清理编号前缀
                cleaned = line.lstrip("0123456789.-* ").strip()
                if len(cleaned) > 10:
                    issues.append(cleaned)

        return issues if issues else [content.strip()]

    async def _fix(self, issues: list[str], context: dict) -> str:
        """根据审查意见修复代码"""
        from app.core.model_router import ModelRequest, ModelCapability

        issue_text = "\n".join(f"- {i}" for i in issues)
        prompt = f"""Fix the following issues found during code review:

{issue_text}

Provide corrected code or instructions for fixing each issue.
"""
        request = ModelRequest(
            capability=ModelCapability.CODE_GENERATION,
            prompt=prompt,
            max_tokens=4096,
            temperature=0.3,
        )
        response = await self._router.generate(request)
        return response.content or ""

    @staticmethod
    def _git_auto_commit(task: str) -> tuple[str, list[str]]:
        """
        Git 自动提交 (借鉴 Aider Git-Native 编辑)

        Returns:
            (commit_message, changed_files) — 如果没有变更返回 ("", [])
        """
        import subprocess

        # 检查是否在 git 仓库中
        try:
            r = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode != 0:
                logger.debug("Not a git repo, skip orchestrator auto-commit")
                return "", []
        except Exception:
            return "", []

        # git add -A
        try:
            subprocess.run(["git", "add", "-A"], capture_output=True, text=True, timeout=10, check=True)
        except subprocess.CalledProcessError as e:
            logger.warning("Orchestrator git add failed: %s", e.stderr.strip())
            return "", []

        # 获取变更文件
        try:
            dr = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True, text=True, timeout=10, check=True,
            )
            changed_files = [f.strip() for f in dr.stdout.strip().split("\n") if f.strip()]
        except subprocess.CalledProcessError:
            changed_files = []

        if not changed_files:
            subprocess.run(["git", "reset", "HEAD"], capture_output=True, text=True, timeout=5)
            return "", []

        # 生成 commit message
        safe_task = task.replace("\n", " ").strip()[:120]
        commit_msg = f"AI orchestrator: {safe_task}"

        try:
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                capture_output=True, text=True, timeout=10, check=True,
            )
            logger.info("Orchestrator git commit: %d files — %s", len(changed_files), commit_msg)
        except subprocess.CalledProcessError as e:
            logger.warning("Orchestrator git commit failed: %s", e.stderr.strip())
            subprocess.run(["git", "reset", "HEAD"], capture_output=True, text=True, timeout=5)
            return "", []

        return commit_msg, changed_files

    async def _save_to_memory(self, task: str, result: OrchestrationResult) -> None:
        """将执行结果保存到长期记忆"""
        try:
            from app.core.memory.memory_store import (
                MemoryNode, MemoryType, get_memory_store,
            )
            store = get_memory_store()

            # 保存任务为决策记忆
            node = MemoryNode(
                content=f"Executed task: {task}",
                memory_type=MemoryType.DECISION,
                importance=0.6,
                source="agent_orchestrator",
                tags=["orchestration"],
                metadata=result.summary(),
            )
            store.save(node)

            # 如果发现问题，保存为教训
            if result.review_issues:
                for issue in result.review_issues:
                    lesson = MemoryNode(
                        content=f"Review issue: {issue}",
                        memory_type=MemoryType.LESSON,
                        importance=0.5,
                        source="agent_orchestrator",
                        tags=["review", "lesson"],
                    )
                    store.save(lesson)
                    store.add_edge(node.id, lesson.id, "CAUSED_BY")

        except Exception as e:
            logger.warning("Failed to save orchestration to memory: %s", e)

    # ── WorkflowGraph 引擎 (借鉴 LangGraph) ─────────

    async def _orchestrate_workflow(
        self,
        task: str,
        mode: str,
        context: dict,
    ) -> OrchestrationResult:
        """
        使用 WorkflowGraph 声明式图执行流水线

        借鉴 LangGraph 的 StateGraph 模式:
        - 节点 = 处理阶段 (Planner/Coder/Reviewer/Fixer)
        - 边 = 固定流转 (Planner -> Coder -> Reviewer)
        - 条件边 = 动态路由 (Reviewer 通过 -> 结束, 不通过 -> Fix -> Coder)
        """
        from app.core.agent.workflow_graph import (
            CompiledWorkflow,
            WorkflowGraph,
            WorkflowState,
            create_default_workflow,
        )

        start_time = time.perf_counter()
        result = OrchestrationResult(success=False)

        # 定义各节点函数 (每个节点返回 partial state)
        async def planner_node(state: WorkflowState) -> dict:
            plan = await self._plan(state.task, state.context)
            return {"plan": [self._subtask_to_dict(s) for s in plan.subtasks]}

        async def coder_node(state: WorkflowState) -> dict:
            # 从 plan 中构建 subtask 并逐个执行
            outputs: list[str] = []
            for task_dict in state.plan:
                subtask = self._dict_to_subtask(task_dict)
                stage_ctx = dict(state.context)
                if state.review_issues:
                    stage_ctx["review_issues"] = state.review_issues
                try:
                    output = await self._execute_subtask(subtask, stage_ctx)
                    outputs.append(output)
                except Exception as e:
                    return {"coder_error": str(e)}

            return {"code_outputs": outputs}

        async def reviewer_node(state: WorkflowState) -> dict:
            if not state.code_outputs:
                return {"review_passed": True, "review_issues": []}

            issues = await self._review(state.code_outputs, state.context)
            passed = len(issues) == 0
            return {"review_issues": issues, "review_passed": passed}

        async def fixer_node(state: WorkflowState) -> dict:
            if not state.review_issues:
                return {"fix_output": "No issues to fix"}

            fix_content = await self._fix(state.review_issues, state.context)
            return {"fix_output": fix_content}

        # 构建 WorkflowGraph
        graph = create_default_workflow(
            planner_fn=planner_node,
            coder_fn=coder_node,
            reviewer_fn=reviewer_node,
            fixer_fn=fixer_node,
        )

        # 编译并执行
        workflow = graph.compile()
        logger.info(
            "Orchestrator executing workflow graph:\n%s", workflow.mermaid
        )

        state = WorkflowState(task=task, context=context)

        try:
            async for event in workflow.stream(state):
                event_type = event.get("event", "")
                if event_type == "node_start":
                    logger.info("Workflow node started: %s", event["node"])
                elif event_type == "node_end":
                    logger.info("Workflow node done: %s (output keys: %s)",
                               event["node"],
                               list(event.get("output", {}).keys()))
                elif event_type == "error":
                    logger.error("Workflow error: %s", event.get("error"))
                elif event_type == "workflow_end":
                    logger.info("Workflow completed")

            # 构建结果
            final_state = state
            plan = Plan(
                original_task=task,
                subtasks=[
                    self._dict_to_subtask(d)
                    for d in final_state.plan
                ] if final_state.plan else [],
                context=context,
            )
            result.plan = plan
            result.results = {
                f"code_{i}": output
                for i, output in enumerate(final_state.code_outputs)
            } if final_state.code_outputs else {}
            result.review_issues = final_state.review_issues
            result.success = not final_state.error

        except Exception as e:
            result.error = f"Workflow error: {e}"
            logger.exception("Workflow orchestration failed")

        result.total_latency_ms = (time.perf_counter() - start_time) * 1000
        await self._save_to_memory(task, result)
        return result

    @staticmethod
    def _subtask_to_dict(subtask: SubTask) -> dict[str, Any]:
        return {
            "id": subtask.id,
            "type": subtask.task_type.value,
            "description": subtask.description,
            "priority": subtask.priority.value,
            "depends_on": subtask.depends_on,
        }

    @staticmethod
    def _dict_to_subtask(data: dict[str, Any]) -> SubTask:
        return SubTask(
            id=data.get("id", ""),
            task_type=TaskType(data.get("type", "code")),
            description=data.get("description", ""),
            priority=TaskPriority(data.get("priority", "medium")),
            depends_on=data.get("depends_on", []),
        )


# ── 全局单例 ──────────────────────────────────────

_global_orchestrator: AgentOrchestrator | None = None


def init_orchestrator(model_router=None) -> AgentOrchestrator:
    """初始化全局调度器"""
    global _global_orchestrator
    _global_orchestrator = AgentOrchestrator(model_router)
    logger.info("AgentOrchestrator initialized")
    return _global_orchestrator


def get_orchestrator() -> AgentOrchestrator:
    """获取全局调度器"""
    global _global_orchestrator
    if _global_orchestrator is None:
        return init_orchestrator()
    return _global_orchestrator
