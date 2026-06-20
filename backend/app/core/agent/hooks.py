"""
Agent 生命周期钩子系统

借鉴 AstrBot astr_agent_hooks.py 设计：
- 在 Agent 运行的各个阶段触发钩子
- 桥接到 EventBus 发布事件
- 支持多个钩子的链式调用

钩子阶段：
    on_agent_begin → on_step_begin → [on_tool_start → on_tool_end]* → on_step_end → ... → on_agent_done
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("platform.agent.hooks")


@dataclass
class HookContext:
    """钩子执行上下文"""

    agent_id: str = ""
    """Agent 实例 ID"""
    session_id: str = ""
    """关联会话 ID"""
    step_count: int = 0
    """当前步数"""
    max_steps: int = 10
    """最大步数"""
    metadata: dict[str, Any] = field(default_factory=dict)
    """额外的上下文数据"""


class AgentHooks(ABC):
    """Agent 生命周期钩子抽象基类。

    子类覆盖感兴趣的方法即可，未覆盖的方法默认空操作。
    """

    async def on_agent_begin(self, ctx: HookContext) -> None:
        """Agent 开始时调用"""

    async def on_agent_done(self, ctx: HookContext, final_output: str) -> None:
        """Agent 完成时调用"""

    async def on_step_begin(
        self, ctx: HookContext, messages: list[dict[str, Any]]
    ) -> None:
        """每一步开始前调用"""

    async def on_step_end(
        self, ctx: HookContext, response: dict[str, Any]
    ) -> None:
        """每一步结束后调用"""

    async def on_tool_start(
        self, ctx: HookContext, tool_name: str, tool_args: dict[str, Any]
    ) -> None:
        """工具调用开始前"""

    async def on_tool_end(
        self,
        ctx: HookContext,
        tool_name: str,
        result: Any,
        error: str | None = None,
        latency_ms: float = 0,
    ) -> None:
        """工具调用结束后"""

    async def on_llm_request(
        self,
        ctx: HookContext,
        provider_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """LLM 请求发送前"""

    async def on_llm_response(
        self,
        ctx: HookContext,
        provider_id: str,
        response: dict[str, Any],
        latency_ms: float = 0,
    ) -> None:
        """LLM 响应返回后"""

    async def on_error(
        self, ctx: HookContext, error: Exception
    ) -> None:
        """Agent 执行出错时"""


class EventBusAgentHooks(AgentHooks):
    """将 Agent 钩子桥接到 EventBus。

    每个钩子方法会将事件发布到 EventBus，供外部模块监听。
    """

    def __init__(
        self,
        session_id: str = "",
        agent_id: str = "",
    ) -> None:
        self._session_id = session_id
        self._agent_id = agent_id
        self._events: list[dict[str, Any]] = []
        """记录所有事件，可用于后续审计"""

    def _make_ctx(self) -> HookContext:
        return HookContext(
            agent_id=self._agent_id,
            session_id=self._session_id,
        )

    async def _publish(self, event_type: str, data: dict[str, Any]) -> None:
        """发布事件到 EventBus"""
        try:
            from app.core.event_bus import get_event_bus, PlatformEvent

            event = PlatformEvent(
                event_id=f"{event_type}_{self._agent_id}",
                event_type=event_type,
                source=self._agent_id,
                session_id=self._session_id,
                payload=data,
            )
            get_event_bus().publish_nowait(event)
        except RuntimeError:
            # EventBus 未初始化，静默跳过
            pass
        self._events.append({"type": event_type, "data": data})

    async def on_agent_begin(self, ctx: HookContext) -> None:
        await self._publish("agent.begin", {
            "session_id": ctx.session_id,
            "max_steps": ctx.max_steps,
        })

    async def on_agent_done(self, ctx: HookContext, final_output: str) -> None:
        await self._publish("agent.done", {
            "session_id": ctx.session_id,
            "steps": ctx.step_count,
            "output_length": len(final_output),
        })

    async def on_step_begin(
        self, ctx: HookContext, messages: list[dict[str, Any]]
    ) -> None:
        await self._publish("agent.step.begin", {
            "session_id": ctx.session_id,
            "step": ctx.step_count,
            "message_count": len(messages),
        })

    async def on_step_end(
        self, ctx: HookContext, response: dict[str, Any]
    ) -> None:
        await self._publish("agent.step.end", {
            "session_id": ctx.session_id,
            "step": ctx.step_count,
            "has_tool_calls": bool(response.get("tool_calls")),
        })

    async def on_tool_start(
        self, ctx: HookContext, tool_name: str, tool_args: dict[str, Any]
    ) -> None:
        await self._publish("agent.tool.start", {
            "session_id": ctx.session_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
        })

    async def on_tool_end(
        self,
        ctx: HookContext,
        tool_name: str,
        result: Any,
        error: str | None = None,
        latency_ms: float = 0,
    ) -> None:
        await self._publish("agent.tool.end", {
            "session_id": ctx.session_id,
            "tool_name": tool_name,
            "error": error,
            "latency_ms": latency_ms,
        })

    async def on_llm_request(
        self,
        ctx: HookContext,
        provider_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        await self._publish("agent.llm.request", {
            "session_id": ctx.session_id,
            "provider": provider_id,
            "message_count": len(messages),
        })

    async def on_llm_response(
        self,
        ctx: HookContext,
        provider_id: str,
        response: dict[str, Any],
        latency_ms: float = 0,
    ) -> None:
        await self._publish("agent.llm.response", {
            "session_id": ctx.session_id,
            "provider": provider_id,
            "latency_ms": latency_ms,
        })

    async def on_error(
        self, ctx: HookContext, error: Exception
    ) -> None:
        await self._publish("agent.error", {
            "session_id": ctx.session_id,
            "error": str(error),
            "error_type": type(error).__name__,
        })


class CompositeAgentHooks(AgentHooks):
    """组合多个钩子，按顺序链式调用"""

    def __init__(self, hooks: list[AgentHooks] | None = None) -> None:
        self._hooks: list[AgentHooks] = hooks or []

    def add(self, hook: AgentHooks) -> None:
        """添加钩子"""
        self._hooks.append(hook)

    async def on_agent_begin(self, ctx: HookContext) -> None:
        for h in self._hooks:
            await h.on_agent_begin(ctx)

    async def on_agent_done(self, ctx: HookContext, final_output: str) -> None:
        for h in self._hooks:
            await h.on_agent_done(ctx, final_output)

    async def on_step_begin(
        self, ctx: HookContext, messages: list[dict[str, Any]]
    ) -> None:
        for h in self._hooks:
            await h.on_step_begin(ctx, messages)

    async def on_step_end(
        self, ctx: HookContext, response: dict[str, Any]
    ) -> None:
        for h in self._hooks:
            await h.on_step_end(ctx, response)

    async def on_tool_start(
        self, ctx: HookContext, tool_name: str, tool_args: dict[str, Any]
    ) -> None:
        for h in self._hooks:
            await h.on_tool_start(ctx, tool_name, tool_args)

    async def on_tool_end(
        self,
        ctx: HookContext,
        tool_name: str,
        result: Any,
        error: str | None = None,
        latency_ms: float = 0,
    ) -> None:
        for h in self._hooks:
            await h.on_tool_end(ctx, tool_name, result, error, latency_ms)

    async def on_llm_request(
        self,
        ctx: HookContext,
        provider_id: str,
        messages: list[dict[str, Any]],
    ) -> None:
        for h in self._hooks:
            await h.on_llm_request(ctx, provider_id, messages)

    async def on_llm_response(
        self,
        ctx: HookContext,
        provider_id: str,
        response: dict[str, Any],
        latency_ms: float = 0,
    ) -> None:
        for h in self._hooks:
            await h.on_llm_response(ctx, provider_id, response, latency_ms)

    async def on_error(
        self, ctx: HookContext, error: Exception
    ) -> None:
        for h in self._hooks:
            await h.on_error(ctx, error)
