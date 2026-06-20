"""
Agent Handoff — 子 Agent 委派机制

借鉴 AstrBot HandoffTool + SubAgentOrchestrator 模式:
- HandoffTool: 自动生成 transfer_to_<agent_name> 工具
- SubAgentOrchestrator: 从配置加载子 Agent，注册 handoff 工具到主 Agent
- 支持同步/后台两种 handoff 模式
- 支持子 Agent 使用独立 Provider/model

用法:
    orchestrator = SubAgentOrchestrator()
    orchestrator.register_subagent(
        name="weather",
        instructions="You are a weather expert...",
        tools=["web_search"],
    )
    # 主 Agent 将自动获得 transfer_to_weather 工具
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.tools.schema import FunctionTool, ToolParam, ToolSchema, ParamType

logger = logging.getLogger("agent.handoff")


# ── HandoffTool ─────────────────────────────────────────────


@dataclass
class HandoffTool(FunctionTool):
    """
    Handoff 工具 —— 将任务委派给子 Agent

    工具名自动生成为 transfer_to_{agent_name}。
    LLM 调用此工具后，由 AgentRunner 拦截并执行子 Agent。

    参数:
    - input (string, 必填): 委派的任务描述
    - background (boolean, 可选): 是否作为后台任务
    """

    agent_name: str = ""
    agent_instructions: str = ""
    agent_tools: list[str] = field(default_factory=list)
    provider_id: str | None = None
    max_turns: int = 5

    # metadata
    tool_description_override: str = ""

    def __post_init__(self):
        name = f"transfer_to_{self.agent_name}"
        description = self.tool_description_override or (
            f"Delegate tasks to the '{self.agent_name}' agent. "
            f"Use this when the user's request is best handled by a specialist."
        )

        self.schema = ToolSchema(
            name=name,
            description=description,
            parameters=[
                ToolParam(
                    name="input",
                    type=ParamType.STRING,
                    description="The task description to delegate",
                    required=True,
                ),
                ToolParam(
                    name="background",
                    type=ParamType.BOOLEAN,
                    description="Run as background task (default: false)",
                    required=False,
                    default=False,
                ),
            ],
            category="agent_handoff",
            tags=["handoff", self.agent_name],
        )
        self.tool_id = f"handoff:{self.agent_name}"
        self.timeout_seconds = 120.0
        self.func = self._make_stub()

    def _make_stub(self) -> Callable:
        """创建占位函数（实际执行由 AgentRunner 拦截）"""
        async def stub(**kwargs):
            return json.dumps({
                "status": "handoff",
                "agent": self.agent_name,
                "message": f"Delegating to agent '{self.agent_name}'...",
                "input": kwargs.get("input", ""),
                "background": kwargs.get("background", False),
            })
        return stub


# ── SubAgent 定义 ───────────────────────────────────────────


@dataclass
class SubAgentConfig:
    """子 Agent 配置"""
    name: str
    instructions: str                          # system prompt
    description: str = ""                      # 公开描述（显示给主 Agent）
    tools: list[str] | None = None            # None = 全部工具
    provider_id: str | None = None            # 覆盖 LLM provider
    max_turns: int = 5
    enabled: bool = True
    priority: int = 10                        # 数字越小越优先
    allow_background: bool = True             # 是否允许后台任务
    begin_dialogs: list[dict[str, str]] | None = None  # 预置对话

    def to_handoff_tool(self) -> HandoffTool:
        """转换为 HandoffTool"""
        return HandoffTool(
            agent_name=self.name,
            agent_instructions=self.instructions,
            agent_tools=self.tools or [],
            provider_id=self.provider_id,
            max_turns=self.max_turns,
            tool_description_override=self.description,
        )


# ── 子 Agent 编排器 ─────────────────────────────────────────


@dataclass
class HandoffResult:
    """Handoff 执行结果"""
    agent_name: str
    success: bool
    result: str = ""
    error: str = ""
    turns: int = 0
    tool_calls: int = 0
    latency_ms: float = 0
    background_task_id: str | None = None


class SubAgentOrchestrator:
    """
    子 Agent 编排器

    管理子 Agent 的注册、HandoffTool 生成和执行。

    用法:
        orch = SubAgentOrchestrator()

        # 注册子 Agent
        orch.register(SubAgentConfig(
            name="weather",
            instructions="You are a weather expert...",
            tools=["web_search", "calculate"],
        ))

        # 获取所有 handoff 工具（注入主 Agent 工具集）
        for tool in orch.handoffs:
            agent_runner.add_tool(tool)

        # 执行 handoff
        result = await orch.execute_handoff(
            "transfer_to_weather",
            {"input": "What's the weather in Beijing?"},
            router=get_model_router(),
        )
    """

    def __init__(self):
        self._subagents: dict[str, SubAgentConfig] = {}
        self._handoffs: list[HandoffTool] = []
        self._pending_bg_tasks: dict[str, asyncio.Task] = {}

    # ── 注册 ──────────────────────────────────────────

    def register(self, agent: SubAgentConfig) -> HandoffTool:
        """注册子 Agent"""
        if agent.name in self._subagents:
            logger.warning(
                "SubAgent '%s' already registered, replacing", agent.name
            )

        self._subagents[agent.name] = agent
        handoff = agent.to_handoff_tool()
        self._handoffs.append(handoff)

        logger.info(
            "SubAgent registered: %s (tools=%s, provider=%s)",
            agent.name,
            agent.tools or "all",
            agent.provider_id or "default",
        )
        return handoff

    def register_from_configs(self, configs: list[dict[str, Any]]) -> int:
        """从配置字典列表批量注册"""
        count = 0
        for cfg in configs:
            if not cfg.get("enabled", True):
                continue
            agent = SubAgentConfig(
                name=cfg["name"],
                instructions=cfg.get("instructions", cfg.get("system_prompt", "")),
                description=cfg.get("description", ""),
                tools=cfg.get("tools", None),
                provider_id=cfg.get("provider_id"),
                max_turns=cfg.get("max_turns", 5),
                enabled=True,
                allow_background=cfg.get("allow_background", True),
                begin_dialogs=cfg.get("begin_dialogs"),
            )
            self.register(agent)
            count += 1
        return count

    def unregister(self, name: str) -> bool:
        """移除子 Agent"""
        if name in self._subagents:
            del self._subagents[name]
            self._handoffs = [h for h in self._handoffs if h.agent_name != name]
            return True
        return False

    # ── 查询 ──────────────────────────────────────────

    @property
    def handoffs(self) -> list[HandoffTool]:
        """获取所有 handoff 工具"""
        return list(self._handoffs)

    @property
    def subagent_names(self) -> list[str]:
        """获取所有子 Agent 名称"""
        return list(self._subagents.keys())

    @property
    def count(self) -> int:
        """子 Agent 数量"""
        return len(self._subagents)

    def get_subagent(self, name: str) -> SubAgentConfig | None:
        """获取子 Agent 配置"""
        return self._subagents.get(name)

    def get_handoff_tool(self, tool_name: str) -> HandoffTool | None:
        """按工具名获取 handoff 工具"""
        for h in self._handoffs:
            if h.schema.name == tool_name:
                return h
        return None

    def get_router_system_prompt(self) -> str:
        """
        生成路由系统提示词（注入主 Agent）

        帮助主 LLM 决策何时委派给哪个子 Agent。
        """
        if not self._handoffs:
            return ""

        lines = [
            "\n## Available Specialist Agents",
            "You can delegate tasks to specialist agents using the `transfer_to_<agent>` tools:",
            "",
        ]
        for h in self._handoffs:
            agent = self._subagents.get(h.agent_name)
            if agent:
                lines.append(
                    f"- **{h.agent_name}**: {agent.description or agent.instructions[:100]}"
                )
        lines.append("")
        lines.append(
            "Use these agents when their expertise is needed. "
            "After delegation, use the results to formulate your response."
        )
        return "\n".join(lines)

    # ── 执行 Handoff ───────────────────────────────────

    async def execute_handoff(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        router=None,
        registry=None,
        session_id: str = "",
    ) -> HandoffResult:
        """
        执行 handoff 调用

        Args:
            tool_name: transfer_to_<agent> 工具名
            arguments: {"input": "...", "background": false}
            router: ModelRouter 实例
            registry: ToolRegistry 实例
            session_id: 会话 ID（用于支持跨轮次子 Agent 调用）

        Returns:
            HandoffResult
        """
        handoff = self.get_handoff_tool(tool_name)
        if not handoff:
            return HandoffResult(
                agent_name=tool_name,
                success=False,
                error=f"Handoff tool '{tool_name}' not found",
            )

        import time
        start = time.perf_counter()

        input_text = arguments.get("input", "")
        background = arguments.get("background", False)

        if background:
            task_id = str(uuid.uuid4())[:8]
            task = asyncio.create_task(
                self._run_subagent(handoff, input_text, router, registry, session_id)
            )
            self._pending_bg_tasks[task_id] = task

            return HandoffResult(
                agent_name=handoff.agent_name,
                success=True,
                result=f"Background task submitted (task_id: {task_id})",
                background_task_id=task_id,
                latency_ms=(time.perf_counter() - start) * 1000,
            )

        result = await self._run_subagent(
            handoff, input_text, router, registry, session_id,
        )

        result.latency_ms = (time.perf_counter() - start) * 1000
        return result

    async def _run_subagent(
        self,
        handoff: HandoffTool,
        input_text: str,
        router=None,
        registry=None,
        session_id: str = "",
    ) -> HandoffResult:
        """运行子 Agent 的工具循环"""
        from app.core.agent.agent_config import AgentConfig
        from app.core.agent.agent_runner import AgentRunner

        config = AgentConfig(
            name=f"subagent:{handoff.agent_name}",
            instructions=handoff.agent_instructions,
            tools=handoff.agent_tools if handoff.agent_tools else [],
            max_turns=handoff.max_turns,
            preferred_model=handoff.provider_id or "",
            stop_on_tool_error=True,
        )

        try:
            runner = AgentRunner()
            agent_result = await runner.run(
                config=config,
                user_message=input_text,
                model_router=router,
            )
            return HandoffResult(
                agent_name=handoff.agent_name,
                success=agent_result.success,
                result=agent_result.final_answer,
                error=agent_result.error,
                turns=agent_result.turns,
                tool_calls=agent_result.total_tool_calls,
            )
        except Exception as e:
            logger.error("Handoff '%s' failed: %s", handoff.agent_name, e)
            return HandoffResult(
                agent_name=handoff.agent_name,
                success=False,
                error=str(e)[:500],
            )

    async def get_background_result(self, task_id: str, timeout: float = 300) -> HandoffResult | None:
        """获取后台任务结果"""
        task = self._pending_bg_tasks.get(task_id)
        if not task:
            return None

        try:
            result = await asyncio.wait_for(task, timeout=timeout)
            del self._pending_bg_tasks[task_id]
            return result
        except asyncio.TimeoutError:
            return HandoffResult(
                agent_name="background",
                success=False,
                error=f"Background task {task_id} timed out",
            )


# ── 全局单例 ────────────────────────────────────────────────

_global_orchestrator: SubAgentOrchestrator | None = None


def init_orchestrator() -> SubAgentOrchestrator:
    """初始化全局子 Agent 编排器"""
    global _global_orchestrator
    _global_orchestrator = SubAgentOrchestrator()
    logger.info("SubAgentOrchestrator initialized")
    return _global_orchestrator


def get_orchestrator() -> SubAgentOrchestrator:
    """获取全局子 Agent 编排器"""
    global _global_orchestrator
    if _global_orchestrator is None:
        return init_orchestrator()
    return _global_orchestrator
