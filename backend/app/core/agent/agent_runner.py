"""
AgentRunner — 多轮工具调用循环

借鉴 AstrBot ToolLoopAgentRunner 设计：

核心循环：
  1. 构建 messages（system + history + user）
  2. 构建 ModelRequest（含 tools schema）
  3. LLM 生成 → ModelResponse
  4. 如果 finish_reason == "tool_calls":
     a. ToolExecutor 执行 tool_calls（经过 Sandbox + Middleware）
     b. 将 tool_calls + tool_results 追加到 messages
     c. 回到步骤 2（下一轮 LLM 调用）
  5. 如果 finish_reason == "stop":
     a. 返回最终答案

特点：
  - 最多 max_turns 轮循环，防止无限循环
  - 支持并行工具调用（多个 tool_calls 同时执行）
  - 完整的钩子系统（before_run / after_tool / on_error）
  - 上下文自动截断（避免超出 token 限制）
  - 🆕 Sandbox 沙箱隔离（所有文件/Shell 操作经过沙箱）
  - 🆕 Middleware 管道（LoopDetection / Summarization / ErrorHandling）
  - 🆕 TrajectoryRecorder 轨迹记录（增量持久化）
  - 🆕 LakeviewSummarizer 步骤摘要（人类可读 + 上下文压缩）
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.core.agent.agent_config import AgentConfig, AgentHook, AgentRunContext
from app.core.agent.lakeview import LakeviewSummarizer, get_lakeview_summarizer
from app.core.agent.middlewares import MiddlewareContext, MiddlewarePipeline
from app.core.agent.tool_executor import ToolExecutor, get_tool_executor
from app.core.agent.trajectory_recorder import TrajectoryRecorder
from app.core.model_router import (
    ModelCapability,
    ModelRequest,
    ModelResponse,
)
from app.core.tools.schema import ToolResult

logger = logging.getLogger("agent.runner")


# ── Agent 运行结果 ──────────────────────────────────────────

class AgentRunResult:
    """
    Agent 运行结果

    包含最终答案和完整的运行统计信息。
    """

    def __init__(self):
        self.final_answer: str = ""
        self.turns: int = 0
        self.total_tool_calls: int = 0
        self.tool_results: list[ToolResult] = []
        self.total_latency_ms: float = 0
        self.final_model: str = ""
        self.final_provider: str = ""
        self.tokens_used: int = 0
        self.error: str = ""
        self.cancelled: bool = False

    @property
    def success(self) -> bool:
        return not self.error and not self.cancelled

    def summary(self) -> dict[str, Any]:
        """生成运行摘要"""
        return {
            "success": self.success,
            "final_answer": self.final_answer[:500] + ("..." if len(self.final_answer) > 500 else ""),
            "turns": self.turns,
            "total_tool_calls": self.total_tool_calls,
            "total_latency_ms": self.total_latency_ms,
            "final_model": self.final_model,
            "final_provider": self.final_provider,
            "tokens_used": self.tokens_used,
            "error": self.error,
            "cancelled": self.cancelled,
        }


# ── AgentRunner ─────────────────────────────────────────────

class AgentRunner:
    """
    Agent 多轮工具调用运行器

    用法:
        runner = AgentRunner()
        result = await runner.run(
            config=AgentConfig(instructions="你是一个助手，可使用工具获取信息"),
            user_message="北京今天天气怎么样？",
        )
        print(result.final_answer)
    """

    def __init__(
        self,
        executor: ToolExecutor | None = None,
        sandbox=None,
        middleware: MiddlewarePipeline | None = None,
        recorder: TrajectoryRecorder | None = None,
        lakeview: LakeviewSummarizer | None = None,
    ):
        self._executor = executor or get_tool_executor()
        self._sandbox = sandbox
        self._middleware = middleware
        self._recorder = recorder
        self._lakeview = lakeview

    @property
    def sandbox(self):
        """懒加载 Sandbox"""
        if self._sandbox is None:
            from app.core.sandbox import get_sandbox
            self._sandbox = get_sandbox()
        return self._sandbox

    @property
    def middleware(self) -> MiddlewarePipeline:
        """懒加载 Middleware"""
        if self._middleware is None:
            from app.core.agent.middlewares import create_default_pipeline
            self._middleware = create_default_pipeline()
        return self._middleware

    async def run(
        self,
        config: AgentConfig,
        user_message: str,
        model_router=None,
        initial_context: AgentRunContext | None = None,
    ) -> AgentRunResult:
        """
        运行 Agent 主循环（集成 Sandbox + Middleware + TrajectoryRecorder）

        流程：
          LLM generate → 检查 tool_calls → Sandbox 执行工具 → Middleware 干预 → 反馈结果 → LLM generate → ...
        """
        from app.core.model_router import get_model_router
        from app.core.tools.registry import get_tool_registry

        router = model_router or get_model_router()
        registry = get_tool_registry()
        context = initial_context or AgentRunContext(
            agent_id=config.name,
            start_time=time.perf_counter(),
        )
        result = AgentRunResult()

        # ── TrajectoryRecorder 初始化 ──
        if self._recorder is None:
            self._recorder = TrajectoryRecorder(
                agent_id=config.name,
                session_id=context.request_id or str(int(time.time())),
            )
        recorder = self._recorder

        # ── Lakeview 初始化 ──
        if self._lakeview is None:
            self._lakeview = get_lakeview_summarizer()
        self._lakeview.start_run(
            agent_id=config.name,
            session_id=context.request_id or str(int(time.time())),
        )

        # ── 前置钩子 ──
        self._fire_hooks(config.hooks, "before_run", context)

        try:
            # 构建 system 消息（Agent 指令 + 工具使用指导）
            system_content = self._build_system_prompt(config, registry)

            # 添加用户消息
            if not context.messages:
                if system_content:
                    context.messages.append({"role": "system", "content": system_content})

                # 将历史 system 消息替换
                for i, msg in enumerate(context.messages):
                    if msg.get("role") == "system":
                        context.messages[i] = {"role": "system", "content": system_content}
                        break

            context.add_user_message(user_message)

            # ── 工具 Schema ──
            tools_schema = config.get_toolset(registry)
            has_tools = len(tools_schema) > 0

            if has_tools:
                logger.info(
                    "Agent '%s': %d tools available: %s",
                    config.name,
                    len(tools_schema),
                    [t["function"]["name"] for t in tools_schema],
                )

            # ── 主循环 ──
            for turn in range(1, config.max_turns + 1):
                if context.is_cancelled:
                    result.cancelled = True
                    result.error = context.cancel_reason or "Agent cancelled"
                    break

                context.turn = turn

                # 🆕 Middleware: before_step
                mw_ctx = MiddlewareContext(
                    agent_id=config.name,
                    turn=turn,
                    max_turns=config.max_turns,
                    messages=context.messages,
                )
                mw_result = await self.middleware.run_before_step(mw_ctx)
                if mw_result is not None:
                    result.final_answer = mw_result
                    result.turns = turn
                    break

                # 上下文截断
                context.trim_context(config.max_context_tokens)

                # 构建请求
                request = ModelRequest(
                    capability=ModelCapability.TOOL_USE if has_tools else ModelCapability.TEXT_GENERATION,
                    prompt=user_message,
                    max_tokens=4096,
                    temperature=0.7,
                    preferred_model=config.preferred_model or None,
                    history=context.messages,
                    tools=tools_schema if has_tools else [],
                    tool_choice="auto" if has_tools else None,
                )

                # 🆕 Trajectory: 记录 LLM 请求
                recorder.new_step(turn)
                recorder.record_llm_request(
                    model=config.preferred_model or "auto",
                    provider="auto",
                    prompt_snapshot=user_message,
                )

                turn_start = time.perf_counter()
                response = await router.generate(request)
                turn_latency = (time.perf_counter() - turn_start) * 1000

                result.tokens_used += response.tokens_used or 0
                result.final_model = response.model_used
                result.final_provider = response.provider

                # 🆕 Trajectory: 记录 LLM 响应
                recorder.record_llm_response(
                    content=response.content or "",
                    finish_reason=response.finish_reason,
                    tokens_used=response.tokens_used or 0,
                    latency_ms=turn_latency,
                )

                # 🆕 Lakeview: 记录 LLM 推理步骤
                if self._lakeview and response.finish_reason == "stop":
                    self._lakeview.record_llm_step(
                        turn=turn,
                        content=response.content or "",
                        tokens_used=response.tokens_used or 0,
                        latency_ms=turn_latency,
                    )

                logger.info(
                    "Agent '%s' turn %d/%d: model=%s provider=%s finish=%s latency=%dms",
                    config.name, turn, config.max_turns,
                    response.model_used, response.provider,
                    response.finish_reason, int(turn_latency),
                )

                # ── 检查是否需要调用工具 ──
                if response.finish_reason == "tool_calls" and response.tool_calls:
                    # 将 assistant tool_calls 加入历史
                    context.messages.append({
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": response.tool_calls,
                    })

                    # 钩子：before_tool
                    self._fire_hooks(
                        config.hooks, "before_tool", context,
                        response.tool_calls,
                    )

                    # 🆕 Trajectory: 记录工具调用
                    recorder.record_tool_calls(response.tool_calls)

                    # 🆕 通过 Sandbox 执行工具调用
                    tools_start = time.perf_counter()
                    tool_results = await self._executor.execute(
                        response.tool_calls,
                        timeout=config.tool_timeout,
                        sandbox=self.sandbox,  # 🆕 注入 Sandbox
                    )
                    tools_latency = (time.perf_counter() - tools_start) * 1000
                    result.total_tool_calls += len(tool_results)

                    # 🆕 Lakeview: 记录工具步骤
                    if self._lakeview:
                        for tc, tr in zip(response.tool_calls, tool_results):
                            func_info = tc.get("function", {})
                            self._lakeview.record_step(
                                turn=turn,
                                tool_name=func_info.get("name", "unknown"),
                                tool_args=func_info.get("arguments", {}),
                                result=tr.result if tr.success else None,
                                success=tr.success,
                                latency_ms=tr.latency_ms,
                                error=tr.error if not tr.success else "",
                            )

                    # 🆕 Trajectory: 记录工具结果
                    recorder.record_tool_results(tool_results, latency_ms=tools_latency)

                    # 将工具结果加入历史
                    context.add_tool_messages(tool_results)

                    # 钩子：after_tool
                    self._fire_hooks(
                        config.hooks, "after_tool", context,
                        tool_results,
                    )

                    # 🆕 Middleware: after_tools
                    mw_ctx.tool_results = list(tool_results)
                    mw_ctx.messages = context.messages
                    mw_result = await self.middleware.run_after_tools(mw_ctx)
                    if mw_result is not None:
                        result.final_answer = mw_result
                        result.turns = turn
                        recorder.record_error(mw_result)
                        recorder.complete_step()
                        break

                    # 检查是否因工具错误应停止
                    if config.stop_on_tool_error:
                        for tr in tool_results:
                            if not tr.success:
                                self._fire_hooks(
                                    config.hooks, "on_tool_error", context,
                                    tr.tool_name, tr.error,
                                )
                                result.error = f"Tool '{tr.tool_name}' failed: {tr.error}"
                                break

                    if result.error:
                        recorder.record_error(result.error)
                        recorder.complete_step()
                        break

                    # 🆕 完成当前步骤记录
                    recorder.complete_step()

                    # 继续下一轮
                    continue

                # ── 正常结束（无工具调用） ──
                result.final_answer = response.content
                context.messages.append({
                    "role": "assistant",
                    "content": response.content,
                })
                result.turns = turn
                recorder.complete_step()
                break

            else:
                # 达到最大轮次
                result.final_answer = (
                    f"⚠️ Agent 达到最大轮次 ({config.max_turns}) 但未完成。"
                    f"最后一轮模型: {result.final_model}"
                )
                result.turns = turn
                self._fire_hooks(config.hooks, "on_max_turns", context)

        except Exception as e:
            logger.error(
                "Agent '%s' run error (turn %d): %s",
                config.name, context.turn, str(e)[:300],
            )
            result.error = str(e)[:500]

            # 🆕 Middleware + Trajectory: 错误处理
            mwe_ctx = MiddlewareContext(agent_id=config.name, messages=context.messages)
            await self.middleware.run_on_error(mwe_ctx, e)
            recorder.record_error(str(e)[:500])
            recorder.complete_step()

            self._fire_hooks(
                config.hooks, "on_error" if hasattr(AgentHook, "on_error") else "after_run",
                context,
            )

        # ── 后置钩子 ──
        result.tool_results = list(context.tool_results)
        result.total_latency_ms = (time.perf_counter() - context.start_time) * 1000
        self._fire_hooks(config.hooks, "after_run", context, result)

        # 🆕 Trajectory: 最终化
        recorder.finalize(
            total_turns=result.turns,
            total_tool_calls=result.total_tool_calls,
            total_tokens=result.tokens_used,
            total_latency_ms=result.total_latency_ms,
            final_model=result.final_model,
            final_provider=result.final_provider,
            error=result.error,
            cancelled=result.cancelled,
        )

        # 🆕 Lakeview: 生成运行摘要（注入到 result）
        if self._lakeview:
            lakeview_run = self._lakeview.get_run_summary(
                total_tokens=result.tokens_used,
                error=result.error,
                final_answer=result.final_answer,
            )
            result.metadata["lakeview"] = {
                "tags_summary": lakeview_run.tags_summary,
                "compact_summary": self._lakeview.get_compact_summary(),
            }

        logger.info(
            "Agent '%s' completed: %d turns, %d tool calls, %.0fms, model=%s",
            config.name,
            result.turns,
            result.total_tool_calls,
            result.total_latency_ms,
            result.final_model,
        )

        return result

    # ── 内部方法 ──────────────────────────────────────────

    def _build_system_prompt(
        self,
        config: AgentConfig,
        registry,
    ) -> str:
        """构建包含工具使用指导的系统提示词"""
        parts: list[str] = []

        if config.instructions:
            parts.append(config.instructions)

        # 工具使用说明
        tools = config.get_toolset(registry)
        if tools:
            tool_names = [t["function"]["name"] for t in tools]
            tool_descs = [f"- `{t['function']['name']}`: {t['function']['description']}" for t in tools]
            parts.append(
                "\n## Available Tools\n"
                "You have access to the following tools:\n\n"
                + "\n".join(tool_descs)
                + "\n\nUse these tools when needed. "
                + f"You can call multiple tools in parallel. "
                + "After receiving tool results, use them to formulate your response."
            )

        return "\n\n".join(parts)

    @staticmethod
    def _fire_hooks(
        hooks: list[AgentHook],
        hook_name: str,
        context: AgentRunContext,
        *args,
    ) -> None:
        """触发指定名称的钩子"""
        for hook in hooks:
            hook_method = getattr(hook, hook_name, None)
            if hook_method and callable(hook_method):
                try:
                    hook_method(context, *args)
                except Exception as e:
                    logger.warning(
                        "Hook '%s.%s' error: %s",
                        hook.name or "unnamed", hook_name, e,
                    )


# ── 流式 AgentRunner（WebSocket 友好） ──────────────────────

class StreamingAgentRunner(AgentRunner):
    """
    支持流式输出的 AgentRunner

    适用于 WebSocket / SSE 场景，每轮 LLM 调用和工具调用
    都通过 yield 方式推送给前端。
    """

    async def run_stream(
        self,
        config: AgentConfig,
        user_message: str,
        model_router=None,
    ):
        """
        流式执行 Agent 并 yield 进度事件

        Yields:
            {"type": "turn_start"|"tool_call"|"tool_result"|"final_answer"|"error", ...}
        """
        from app.core.model_router import get_model_router
        from app.core.tools.registry import get_tool_registry

        router = model_router or get_model_router()
        registry = get_tool_registry()
        context = AgentRunContext(agent_id=config.name, start_time=time.perf_counter())

        system_content = self._build_system_prompt(config, registry)
        if system_content:
            context.messages.append({"role": "system", "content": system_content})
        context.add_user_message(user_message)

        tools_schema = config.get_toolset(registry)
        has_tools = len(tools_schema) > 0

        for turn in range(1, config.max_turns + 1):
            if context.is_cancelled:
                yield {"type": "cancelled", "reason": context.cancel_reason}
                break

            context.turn = turn
            context.trim_context(config.max_context_tokens)

            request = ModelRequest(
                capability=ModelCapability.TOOL_USE if has_tools else ModelCapability.TEXT_GENERATION,
                prompt=user_message,
                max_tokens=4096,
                temperature=0.7,
                preferred_model=config.preferred_model or None,
                history=context.messages,
                tools=tools_schema if has_tools else [],
                tool_choice="auto" if has_tools else None,
            )

            yield {
                "type": "turn_start",
                "turn": turn,
                "max_turns": config.max_turns,
            }

            response = await router.generate(request)

            if response.finish_reason == "tool_calls" and response.tool_calls:
                yield {
                    "type": "tool_call",
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        }
                        for tc in response.tool_calls
                    ],
                }

                context.messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": response.tool_calls,
                })

                # 逐个执行工具并推送结果
                async for event in self._executor.execute_with_stream(
                    response.tool_calls, timeout=config.tool_timeout
                ):
                    if event["status"] == "executing":
                        yield {
                            "type": "tool_executing",
                            "tool_name": event["tool_name"],
                        }
                    else:
                        yield {
                            "type": "tool_result",
                            "tool_name": event["tool_name"],
                            "success": event["status"] == "completed",
                            "result": event.get("result"),
                            "error": event.get("error"),
                            "latency_ms": event.get("latency_ms"),
                        }

                continue

            # 最终答案
            yield {
                "type": "final_answer",
                "content": response.content,
                "model_used": response.model_used,
                "turns": turn,
                "total_latency_ms": (time.perf_counter() - context.start_time) * 1000,
            }
            break

        else:
            yield {
                "type": "max_turns",
                "turns": config.max_turns,
                "message": f"Reached max turns ({config.max_turns})",
            }
