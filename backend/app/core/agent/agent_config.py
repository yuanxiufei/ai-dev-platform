"""
Agent 配置 — Agent 定义与生命周期钩子

借鉴 AstrBot agent/agent.py + agent/hooks.py 设计：
- AgentConfig: Agent 元数据（名称、系统指令、工具集、循环上限）
- AgentHook: 生命周期钩子（before_run / after_run / on_tool_error）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from app.core.tools.schema import ToolResult
from app.core.tools.registry import ToolRegistry

logger = logging.getLogger("agent.config")


@dataclass
class AgentHook:
    """
    Agent 生命周期钩子

    用法:
        AgentHook(
            before_run=lambda ctx: logger.info("Agent starting"),
            after_tool=lambda ctx, results: logger.info(f"Tools done: {len(results)}"),
            on_error=lambda ctx, err: logger.error(f"Agent error: {err}"),
        )
    """
    name: str = ""

    before_run: Callable[["AgentRunContext"], None] | None = None
    """Agent 开始运行前调用"""

    after_run: Callable[["AgentRunContext", "AgentRunResult"], None] | None = None
    """Agent 运行结束后调用"""

    before_tool: Callable[["AgentRunContext", list[dict[str, Any]]], None] | None = None
    """工具调用前调用（传入 tool_calls）"""

    after_tool: Callable[["AgentRunContext", list[ToolResult]], None] | None = None
    """工具调用后调用（传入执行结果）"""

    on_tool_error: Callable[["AgentRunContext", str, str], None] | None = None
    """工具执行出错时调用（传入 tool_name, error）"""

    on_max_turns: Callable[["AgentRunContext"], None] | None = None
    """达到最大循环轮次时调用"""


@dataclass
class AgentConfig:
    """
    Agent 定义 + 运行时配置

    借鉴 AstrBot Agent dataclass，定义 Agent 的：
    - 身份和行为指令
    - 可用工具集
    - 循环控制参数
    - 可选的生命周期钩子
    """
    # ── 基础标识 ──
    name: str = "default"
    description: str = ""

    # ── 行为指令 ──
    instructions: str = ""
    """系统提示词，定义 Agent 的行为规则和工具使用方式"""

    # ── 工具配置 ──
    tools: list[str] = field(default_factory=list)
    """允许使用的工具名称列表（空 = 所有已注册工具）"""
    tool_categories: list[str] = field(default_factory=list)
    """按分类筛选工具（如 ["code", "web"]）"""

    # ── 循环控制 ──
    max_turns: int = 10
    """最大 LLM 调用轮次（防止无限循环）"""
    tool_timeout: float = 30.0
    """单次工具调用超时（秒）"""
    max_context_tokens: int = 64000
    """最大上下文 token 数（超出时截断）"""

    # ── 路由配置 ──
    preferred_model: str = ""
    """首选模型名称（空 = 自动选择）"""

    # ── 钩子 ──
    hooks: list[AgentHook] = field(default_factory=list)

    # ── 高级配置 ──
    allow_parallel_tools: bool = True
    """是否允许 LLM 并行调用多个工具"""
    inject_tool_results: bool = True
    """工具结果是否注入到 LLM 消息中（关闭用于纯函数调用场景）"""
    stop_on_tool_error: bool = False
    """工具出错时是否停止 Agent 循环"""

    def get_toolset(self, registry: ToolRegistry) -> list[dict[str, Any]]:
        """
        从注册中心获取可用工具的 OpenAI schema

        返回可直接注入到 ModelRequest.tools 的列表。
        """
        # 按名称过滤
        if self.tools:
            toolset = [
                t for t in registry.get_toolset().tools
                if t.schema.name in self.tools
            ]
        else:
            toolset = list(registry.get_toolset().tools)

        # 按分类过滤
        if self.tool_categories:
            toolset = [
                t for t in toolset
                if t.schema.category in self.tool_categories
            ]

        return [t.to_openai() for t in toolset]

    def has_tools(self, registry: ToolRegistry) -> bool:
        """检查是否有可用工具"""
        return len(self.get_toolset(registry)) > 0


# ── Agent 运行上下文 ────────────────────────────────────────

@dataclass
class AgentRunContext:
    """
    Agent 运行上下文 — 在工具调用循环中持久化的状态

    借鉴 AstrBot ContextWrapper / RunContext 设计。
    """
    agent_id: str = ""
    request_id: str = ""
    turn: int = 0

    # 消息历史（包含 user/assistant/tool 所有角色）
    messages: list[dict[str, Any]] = field(default_factory=list)

    # 工具执行历史
    tool_results: list[ToolResult] = field(default_factory=list)

    # 元数据
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float = 0.0

    # 状态
    is_cancelled: bool = False
    cancel_reason: str = ""

    def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        self.messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str, tool_calls: list[dict] | None = None) -> None:
        """添加助手消息（可选带 tool_calls）"""
        msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.messages.append(msg)

    def add_tool_messages(self, results: list[ToolResult]) -> None:
        """批量添加工具结果消息"""
        from app.core.agent.tool_executor import ToolExecutor
        self.messages.extend(ToolExecutor.to_tool_messages(results))
        self.tool_results.extend(results)

    def cancel(self, reason: str = "") -> None:
        """取消 Agent 运行"""
        self.is_cancelled = True
        self.cancel_reason = reason

    def trim_context(self, max_tokens: int) -> int:
        """
        按 token 限制截断历史消息（保留越新越好）

        返回被移除的消息数。
        """
        if len(self.messages) <= 2:
            return 0

        # 简单估算：1 token ≈ 4 字符
        total_chars = sum(len(str(m.get("content", ""))) for m in self.messages)
        max_chars = max_tokens * 4

        if total_chars <= max_chars:
            return 0

        removed = 0
        # 从最早的消息开始移除（保留 system 消息）
        i = 1 if (self.messages and self.messages[0].get("role") == "system") else 0
        while i < len(self.messages) - 1:
            total_chars -= len(str(self.messages[i].get("content", "")))
            self.messages.pop(i)
            removed += 1
            if total_chars <= max_chars:
                break

        logger.info(
            "Context trimmed: %d messages removed, %d remaining",
            removed, len(self.messages),
        )
        return removed
