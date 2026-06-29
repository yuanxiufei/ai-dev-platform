"""
多 Agent 协同调度器 — Planner → Coder → Reviewer → Tester 闭环

自主设计，借鉴 Agent-Reach 的 Planner/Coder/Reviewer/Tester 流水线模式
和 hermes-agent 的 think→act→observe→reflect 循环。

核心流程:
  Planner 分解任务 → Coder 生成代码 → Reviewer 审查
  → Coder 修复 → Tester 验证 → Memory 保存
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

    借鉴 Agent-Reach 的 Planner→Coder→Reviewer→Tester 流水线。

    用法:
        orchestrator = AgentOrchestrator(model_router)
        result = await orchestrator.orchestrate(
            task="Build a REST API for user management",
            mode="full",  # full | code_only | review_only
        )
    """

    def __init__(self, model_router=None):
        from app.core.model_router import get_model_router
        self._router = model_router or get_model_router()

    async def orchestrate(
        self,
        task: str,
        mode: str = "full",
        context: dict | None = None,
    ) -> OrchestrationResult:
        """
        执行完整的 Agent 协同流水线

        Args:
            task: 用户任务描述
            mode: full (完整流水线) | code_only (仅生成) | review_only (仅审查)
            context: 额外上下文（代码库信息、记忆等）
        """
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

            # Phase 2: Execute subtasks
            for subtask in plan.ordered_tasks:
                if mode == "review_only" and subtask.task_type != TaskType.TEST:
                    continue

                subtask.status = "running"
                try:
                    output = await self._execute_subtask(subtask, context or {})
                    subtask.result = output
                    subtask.status = "done"
                    result.results[subtask.id] = output
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

    async def _execute_subtask(self, subtask: SubTask, context: dict) -> str:
        """Coder: 执行子任务（调用模型生成）"""
        from app.core.model_router import ModelRequest, ModelCapability

        capability_map = {
            TaskType.CODE: ModelCapability.CODE_GENERATION,
            TaskType.FIX: ModelCapability.CODE_GENERATION,
            TaskType.REFACTOR: ModelCapability.CODE_GENERATION,
            TaskType.TEST: ModelCapability.CODE_GENERATION,
            TaskType.DESIGN: ModelCapability.TEXT_GENERATION,
            TaskType.ANALYZE: ModelCapability.TEXT_GENERATION,
            TaskType.DOCUMENT: ModelCapability.TEXT_GENERATION,
        }

        capability = capability_map.get(subtask.task_type, ModelCapability.TEXT_GENERATION)

        prompt = f"""Complete the following subtask:

Type: {subtask.task_type}
Description: {subtask.description}
Priority: {subtask.priority}

Context: {context.get('summary', '')}

Provide a thorough and complete response.
"""
        request = ModelRequest(
            capability=capability,
            prompt=prompt,
            max_tokens=4096,
            temperature=0.3,
        )
        response = await self._router.generate(request)
        return response.content or ""

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
