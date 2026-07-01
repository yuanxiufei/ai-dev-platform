"""
Agent Workflow Graph — 声明式状态图编排引擎

借鉴 LangGraph 的 StateGraph 设计:
- 声明式节点+边+条件路由，替代硬编码 if/else
- 共享 WorkflowState 在节点间自动传递
- Mermaid 图可视化导出
- 条件分支 (pass/fail/retry 路由)
- 节点执行钩子 (before_node / after_node)

核心概念:
  WorkflowState  — 共享状态字典 (类似 LangGraph 的 Annotated State)
  WorkflowNode    — 处理函数 f(state) -> partial_state
  Edge            — 节点间固定转移
  ConditionalEdge — 条件转移 f(state) -> target_node_name

用法:
    graph = WorkflowGraph()
    graph.add_node("planner", planner_fn)
    graph.add_node("coder", coder_fn)
    graph.add_node("reviewer", reviewer_fn)
    graph.set_entry("planner")
    graph.add_edge("planner", "coder")
    graph.add_edge("coder", "reviewer")
    graph.add_conditional("reviewer", review_router)
    # 编译后生成 Mermaid 图
    print(graph.to_mermaid())
    # 流式执行
    async for event in graph.stream(initial_state):
        ...
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, AsyncIterator, Callable, Protocol

logger = logging.getLogger("agent.workflow")


# ── 协议定义 ────────────────────────────────────

class NodeFunc(Protocol):
    """工作流节点处理函数"""
    async def __call__(self, state: "WorkflowState") -> dict[str, Any]:
        ...


class RouterFunc(Protocol):
    """条件路由器: 根据状态返回下一个节点名"""
    async def __call__(self, state: "WorkflowState") -> str:
        ...


# ── 工作流状态 ──────────────────────────────────

@dataclass
class WorkflowState:
    """工作流共享状态 (类似 LangGraph 的 TypedDict State)"""
    # 输入
    task: str = ""
    context: dict[str, Any] = field(default_factory=dict)

    # Planner 阶段
    plan: list[dict[str, Any]] = field(default_factory=list)
    plan_error: str = ""

    # Coder 阶段
    code_outputs: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    coder_error: str = ""

    # Reviewer 阶段
    review_issues: list[str] = field(default_factory=list)
    review_passed: bool = False

    # Fix 阶段
    fix_output: str = ""
    fix_iterations: int = 0

    # 元信息
    current_node: str = ""
    history: list[str] = field(default_factory=list)  # 节点执行历史
    error: str = ""
    stage_results: dict[str, Any] = field(default_factory=dict)

    MAX_FIX_ITERATIONS: int = 3  # 最大修复迭代次数
    END: str = "__end__"

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "task": self.task[:100],
            "plan_items": len(self.plan),
            "code_outputs": len(self.code_outputs),
            "files_modified": self.files_modified,
            "review_passed": self.review_passed,
            "review_issues": len(self.review_issues),
            "fix_iterations": self.fix_iterations,
            "error": self.error,
            "history": self.history,
        }


# ── 边类型 ──────────────────────────────────────

class EdgeType(StrEnum):
    FIXED = "fixed"
    CONDITIONAL = "conditional"


@dataclass
class Edge:
    """固定边: from -> to"""
    source: str
    target: str
    edge_type: EdgeType = EdgeType.FIXED


@dataclass
class ConditionalEdge:
    """条件边: from -> router_fn(state) -> target"""
    source: str
    router: RouterFunc
    edge_type: EdgeType = EdgeType.CONDITIONAL


# ── WorkflowGraph ────────────────────────────────

@dataclass
class _NodeDef:
    """内部节点定义"""
    name: str
    func: NodeFunc
    description: str = ""


class WorkflowGraph:
    """
    声明式 Agent 工作流图

    类似 LangGraph StateGraph，用节点+边定义 Agent Pipeline。
    支持条件路由、Mermaid 可视化、流式事件输出。
    """

    def __init__(self, name: str = "agent_workflow"):
        self.name = name
        self._nodes: dict[str, _NodeDef] = {}
        self._edges: list[Edge] = []
        self._conditionals: dict[str, ConditionalEdge] = {}
        self._entry: str | None = None

        # 钩子
        self._before: dict[str, NodeFunc] = {}
        self._after: dict[str, NodeFunc] = {}

    # ── 构建 API ─────────────────────────────────

    def add_node(
        self,
        name: str,
        func: NodeFunc,
        description: str = "",
    ) -> "WorkflowGraph":
        """添加节点"""
        self._nodes[name] = _NodeDef(name=name, func=func, description=description)
        logger.debug("WorkflowGraph[%s]: added node '%s'", self.name, name)
        return self

    def set_entry(self, name: str) -> "WorkflowGraph":
        """设置入口节点"""
        if name not in self._nodes:
            raise ValueError(f"Node '{name}' not found in graph")
        self._entry = name
        return self

    def add_edge(self, source: str, target: str) -> "WorkflowGraph":
        """添加固定边"""
        self._edges.append(Edge(source=source, target=target))
        return self

    def add_conditional(
        self,
        source: str,
        router: RouterFunc,
    ) -> "WorkflowGraph":
        """添加条件路由"""
        self._conditionals[source] = ConditionalEdge(source=source, router=router)
        return self

    def add_hook(
        self,
        node: str,
        before: NodeFunc | None = None,
        after: NodeFunc | None = None,
    ) -> "WorkflowGraph":
        """为节点添加前后钩子"""
        if before:
            self._before[node] = before
        if after:
            self._after[node] = after
        return self

    # ── 验证 ─────────────────────────────────────

    def validate(self) -> list[str]:
        """验证图结构，返回问题列表"""
        issues: list[str] = []

        if not self._entry:
            issues.append("No entry node set")
        elif self._entry not in self._nodes:
            issues.append(f"Entry node '{self._entry}' not found")

        for edge in self._edges:
            if edge.source not in self._nodes:
                issues.append(f"Edge source '{edge.source}' not found")
            if edge.target not in self._nodes:
                issues.append(f"Edge target '{edge.target}' not found")

        # 检查孤立节点
        connected = {self._entry} if self._entry else set()
        for edge in self._edges:
            connected.add(edge.source)
            connected.add(edge.target)
        for node_name in self._nodes:
            if node_name not in connected:
                issues.append(f"Disconnected node: '{node_name}'")

        return issues

    # ── Mermaid 可视化 ────────────────────────────

    def to_mermaid(self) -> str:
        """导出 Mermaid 流程图"""
        lines = [f"graph TD"]
        lines.append(f"    %% {self.name}")

        for node_name in self._nodes:
            display = self._nodes[node_name].description or node_name
            lines.append(f"    {node_name}[{display}]")

        for edge in self._edges:
            lines.append(f"    {edge.source} --> {edge.target}")

        for source, cond in self._conditionals.items():
            lines.append(f"    {source} --> |router| ???_{source}")
            lines.append(f"    ???_{source}"
                         + "{{ shape: diamond }}")

        return "\n".join(lines)

    # ── 编译 ─────────────────────────────────────

    def compile(self) -> "CompiledWorkflow":
        """编译为可执行工作流 (类似 LangGraph 的 graph.compile())"""
        issues = self.validate()
        if issues:
            raise ValueError(f"Graph validation failed: {', '.join(issues)}")
        return CompiledWorkflow(self)

    # ── 节点获取 ─────────────────────────────────

    def _next_node(self, current: str, state: WorkflowState) -> str | None:
        """确定下一个节点"""
        # 1. 检查条件边
        if current in self._conditionals:
            return None  # 由 CompiledWorkflow 处理路由

        # 2. 检查固定边
        for edge in self._edges:
            if edge.source == current:
                return edge.target

        # 3. 没有出边 -> 结束
        return state.END


# ── 编译后的工作流 ────────────────────────────────

class CompiledWorkflow:
    """可执行的工作流 (类似 LangGraph 的 CompiledGraph)"""

    def __init__(self, graph: WorkflowGraph):
        self._graph = graph

    @property
    def mermaid(self) -> str:
        return self._graph.to_mermaid()

    async def invoke(
        self,
        state: WorkflowState,
    ) -> WorkflowState:
        """同步执行完整工作流，返回最终状态"""
        result = state
        async for _ in self.stream(state):
            pass
        return result

    async def stream(
        self,
        state: WorkflowState,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        流式执行工作流，每个节点完成后 yield 事件

        事件格式:
        {
            "event": "node_start" | "node_end" | "workflow_end" | "error",
            "node": "planner" | "coder" | ...,
            "state": WorkflowState,
            "output": {...},  # 节点的 partial state
        }
        """
        if not self._graph._entry:
            yield {"event": "error", "error": "No entry node", "state": state}
            return

        current = self._graph._entry
        state.history = []

        while current and current != state.END:
            if current not in self._graph._nodes:
                yield {
                    "event": "error",
                    "error": f"Node '{current}' not found",
                    "state": state,
                }
                return

            node_def = self._graph._nodes[current]
            state.current_node = current

            # ── before hook ──
            if current in self._graph._before:
                try:
                    await self._graph._before[current](state)
                except Exception as e:
                    logger.warning("before hook for '%s' failed: %s", current, e)

            # ── 执行节点 ──
            yield {"event": "node_start", "node": current, "state": state}
            try:
                partial = await node_def.func(state)
                # 合并状态
                self._merge_state(state, partial)
                state.history.append(current)

                yield {
                    "event": "node_end",
                    "node": current,
                    "output": partial,
                    "state": state,
                }
            except Exception as e:
                logger.exception("Node '%s' failed", current)
                state.error = str(e)
                yield {
                    "event": "error",
                    "node": current,
                    "error": str(e),
                    "state": state,
                }
                break

            # ── after hook ──
            if current in self._graph._after:
                try:
                    await self._graph._after[current](state)
                except Exception as e:
                    logger.warning("after hook for '%s' failed: %s", current, e)

            # ── 确定下一节点 ──
            if current in self._graph._conditionals:
                cond = self._graph._conditionals[current]
                try:
                    next_node = await cond.router(state)
                except Exception as e:
                    logger.exception("Router for '%s' failed", current)
                    state.error = f"Router error: {e}"
                    yield {"event": "error", "error": state.error, "state": state}
                    break
                current = next_node
            else:
                current = self._graph._next_node(current, state)

        state.current_node = state.END
        yield {"event": "workflow_end", "state": state}

    def _merge_state(
        self,
        state: WorkflowState,
        partial: dict[str, Any],
    ) -> None:
        """合并节点输出到状态 (类似 LangGraph 的 Annotated state merge)"""
        for key, value in partial.items():
            if hasattr(state, key):
                existing = getattr(state, key)
                # 列表字段 -> 累加
                if isinstance(existing, list) and isinstance(value, list):
                    setattr(state, key, existing + value)
                # dict -> 合并
                elif isinstance(existing, dict) and isinstance(value, dict):
                    existing.update(value)
                # 其他 -> 覆盖
                else:
                    setattr(state, key, value)


# ── 预设工作流 ────────────────────────────────────

def create_default_workflow(
    planner_fn: NodeFunc,
    coder_fn: NodeFunc,
    reviewer_fn: NodeFunc,
    fixer_fn: NodeFunc | None = None,
) -> WorkflowGraph:
    """
    创建默认的 Planner -> Coder -> Reviewer <-> Fixer 工作流

    路由逻辑:
    - reviewer 通过 -> END
    - reviewer 发现问题 -> fixer -> coder -> reviewer (循环, 最多 3 次)
    """
    graph = WorkflowGraph(name="default_agent_pipeline")

    graph.add_node("planner", planner_fn, description="📋 任务规划")
    graph.add_node("coder", coder_fn, description="💻 代码生成")
    graph.add_node("reviewer", reviewer_fn, description="🔍 代码审查")

    if fixer_fn:
        graph.add_node("fixer", fixer_fn, description="🔧 修复问题")

        # 修复后路由回 coder 重新生成
        async def fix_then_code(state: WorkflowState) -> str:
            # fix 后直接去 coder (coder 会收到 review_issues 上下文)
            return "coder"
        graph.add_edge("fixer", "coder")

    graph.set_entry("planner")
    graph.add_edge("planner", "coder")
    graph.add_edge("coder", "reviewer")

    # Reviewer 条件路由
    async def review_router(state: WorkflowState) -> str:
        if state.review_passed or not state.review_issues:
            return state.END
        if state.fix_iterations >= state.MAX_FIX_ITERATIONS:
            logger.warning(
                "Max fix iterations (%d) reached, stopping",
                state.MAX_FIX_ITERATIONS,
            )
            return state.END
        state.fix_iterations += 1
        return "fixer" if fixer_fn else "coder"

    graph.add_conditional("reviewer", review_router)

    return graph
