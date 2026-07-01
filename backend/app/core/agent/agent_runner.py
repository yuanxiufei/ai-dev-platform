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
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any

from app.core.agent.agent_config import AgentConfig, AgentHook, AgentRunContext
from app.core.agent.lakeview import LakeviewSummarizer, get_lakeview_summarizer
from app.core.agent.middlewares import MiddlewareContext, MiddlewarePipeline
from app.core.agent.tool_executor import ToolExecutor, get_tool_executor
from app.core.agent.trajectory_recorder import TrajectoryRecorder
from app.core.diff.diff_engine import DiffEngine
from app.core.model_router import (
    ModelCapability,
    ModelRequest,
    ModelResponse,
)
from app.core.tools.schema import ToolResult
from app.models.agent_models import (
    TraceDB,
    TraceStatus,
    FileChangeType,
    AgentTrace,
    _str_truncate,
)

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
        self.trace_id: str = ""  # 🆕 TraceDB 记录 ID

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
        trace_db: TraceDB | None = None,
    ):
        self._executor = executor or get_tool_executor()
        self._sandbox = sandbox
        self._middleware = middleware
        self._recorder = recorder
        self._lakeview = lakeview
        self._trace_db = trace_db

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

        # ── TraceDB 持久化初始化 ──
        trace_id: uuid.UUID | None = None
        try:
            if self._trace_db is not None:
                trace_id = self._trace_db.start_trace(
                    agent_id=config.name,
                    user_message=user_message,
                    session_id=context.request_id or str(int(time.time())),
                )
                result.trace_id = str(trace_id)
        except Exception as e:
            logger.warning("TraceDB start_trace failed (non-blocking): %s", e)

        # ── Budget 初始化（借鉴 hermes-agent 预算感知循环）──
        budget_tracker = None
        if config.enable_budget:
            from app.core.agent.budget import BudgetTracker, BudgetStatus
            budget_tracker = BudgetTracker(
                token_budget=config.token_budget,
                cost_budget_usd=config.cost_budget_usd,
                time_budget_ms=config.time_budget_ms,
            )
            logger.info(
                "Agent '%s': budget tracking enabled (tokens=%s, cost=$%.2f, time=%ss)",
                config.name,
                f"{config.token_budget:,}" if config.token_budget else "unlimited",
                config.cost_budget_usd,
                f"{config.time_budget_ms/1000:.0f}",
            )

        # ── Memory 注入：运行前加载相关记忆上下文 ──
        memory_context = ""
        if config.enable_memory:
            try:
                from app.core.memory.memory_retriever import get_retriever
                retriever = get_retriever()
                memory_context = retriever.retrieve_as_context(
                    query=user_message,
                    max_items=10,
                )
                if memory_context:
                    logger.info(
                        "Agent '%s': injected memory context (%d chars)",
                        config.name, len(memory_context),
                    )
            except Exception as e:
                logger.warning("Memory retrieval failed (non-blocking): %s", e)

        # ── 前置钩子 ──
        self._fire_hooks(config.hooks, "before_run", context)

        # 存储 memory_context 供 after_run 复用
        config._memory_context = memory_context

        try:
            # 构建 system 消息（Agent 指令 + 工具使用指导 + 记忆上下文）
            system_content = self._build_system_prompt(config, registry)
            if memory_context:
                system_content = (
                    system_content
                    + "\n\n## Relevant Context from Memory\n"
                    + memory_context
                )

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

            # 🆕 TraceDB: 标记进入执行状态
            try:
                if trace_id and self._trace_db:
                    self._trace_db.update_trace_status(trace_id, TraceStatus.EXECUTING)
            except Exception as e:
                logger.warning("TraceDB status update failed: %s", e)

            # ── 主循环 ──
            for turn in range(1, config.max_turns + 1):
                if context.is_cancelled:
                    result.cancelled = True
                    result.error = context.cancel_reason or "Agent cancelled"
                    break

                # 🆕 预算检查（借鉴 hermes-agent 预算感知循环）
                if budget_tracker and not budget_tracker.should_continue()[0]:
                    logger.warning(
                        "Agent '%s': budget exhausted at turn %d: %s",
                        config.name, turn, budget_tracker.summary(),
                    )
                    result.final_answer = (
                        f"⚠️ Agent budget exhausted after {turn} turns. "
                        f"Tokens: {budget_tracker.total_tokens:,}/{budget_tracker.token_budget:,}. "
                        f"The best answer so far is provided below."
                    )
                    # 尝试提取最近一轮的内容作为最终答案
                    if context.messages:
                        for msg in reversed(context.messages):
                            if msg.get("role") == "assistant" and msg.get("content"):
                                result.final_answer = msg["content"]
                                break
                    result.turns = turn
                    result.error = f"Budget exhausted: {budget_tracker.summary()}"
                    break

                # 🆕 预算警告日志
                if budget_tracker and budget_tracker.status == BudgetStatus.CRITICAL:
                    logger.warning(
                        "Agent '%s': budget CRITICAL at turn %d: tokens %s/%s, cost $%.4f/$%.2f",
                        config.name, turn,
                        f"{budget_tracker.total_tokens:,}",
                        f"{budget_tracker.token_budget:,}",
                        budget_tracker.total_cost_usd,
                        budget_tracker.cost_budget_usd,
                    )

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

                # 🆕 Budget: 记录本轮 LLM 消耗
                if budget_tracker:
                    try:
                        # 估算 input tokens（粗略：字符数 / 4）
                        estimated_input = sum(
                            len(str(m.get("content", ""))) // 4
                            for m in context.messages[-5:]  # 最近 5 条
                        )
                        budget_tracker.record(
                            input_tokens=max(estimated_input, 500),
                            output_tokens=response.tokens_used or 0,
                            model=response.model_used,
                            latency_ms=turn_latency,
                        )
                    except Exception:
                        pass  # 预算记录失败不阻塞执行

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

                    # 🆕 TraceDB: 持久化每次工具调用 + 检测文件变更
                    if trace_id and self._trace_db:
                        try:
                            for seq, (tc, tr) in enumerate(
                                zip(response.tool_calls, tool_results)
                            ):
                                func_info = tc.get("function", {})
                                t_name = func_info.get("name", "unknown")
                                t_args = func_info.get("arguments", {})
                                if isinstance(t_args, str):
                                    try:
                                        import json as _json
                                        t_args = _json.loads(t_args) if t_args else {}
                                    except Exception:
                                        t_args = {}

                                tc_id = self._trace_db.log_tool_call(
                                    trace_id=trace_id,
                                    tool_name=t_name,
                                    step_number=turn,
                                    sequence=seq,
                                    tool_call_id=tc.get("id", ""),
                                    arguments=t_args if isinstance(t_args, dict) else {},
                                    result=tr.result if tr.success else None,
                                    success=tr.success,
                                    error_message=tr.error,
                                    latency_ms=tr.latency_ms,
                                )
                                # 检测文件变更
                                self._persist_file_changes(
                                    trace_db=self._trace_db,
                                    tool_call_id=tc_id,
                                    trace_id=trace_id,
                                    tool_name=t_name,
                                    arguments=t_args if isinstance(t_args, dict) else {},
                                    result=tr.result if tr.success else None,
                                )
                        except Exception as e:
                            logger.warning("TraceDB tool log failed (non-blocking): %s", e)

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

        # 🆕 Budget: 注入预算摘要到结果
        if budget_tracker:
            result.metadata = result.metadata or {}
            result.metadata["budget"] = budget_tracker.summary()

        self._fire_hooks(config.hooks, "after_run", context, result)

        # ── Memory 闭环：运行后提取并保存记忆 ──
        if config.enable_memory and result.success:
            try:
                from app.core.memory.memory_extractor import MemoryExtractor
                from app.core.memory.memory_store import get_memory_store
                store = get_memory_store()
                extractor = MemoryExtractor(store)
                await extractor.extract_from_conversation(
                    messages=context.messages,
                    session_id=context.request_id or str(uuid.uuid4()),
                )
                logger.info(
                    "Agent '%s': memory extracted and saved after run",
                    config.name,
                )
            except Exception as e:
                logger.warning("Memory extraction failed (non-blocking): %s", e)

        # 🆕 Git Auto-Commit (借鉴 Aider Git-Native 编辑)
        if config.git_auto_commit and result.success and not result.error:
            try:
                commit_msg, changed_files = await asyncio.to_thread(
                    self._git_auto_commit, user_message, config.name,
                )
                if changed_files:
                    logger.info(
                        "Agent '%s': auto-committed %d files — %s",
                        config.name, len(changed_files), commit_msg,
                    )
                    result.metadata["git_commit"] = {
                        "message": commit_msg,
                        "files": changed_files,
                    }
            except Exception as e:
                logger.warning("Git auto-commit failed (non-blocking): %s", e)

        # 🆕 TraceDB: 完成轨迹
        try:
            if trace_id and self._trace_db:
                final_status = (
                    TraceStatus.ERROR if result.error
                    else TraceStatus.CANCELLED if result.cancelled
                    else TraceStatus.COMPLETED
                )
                self._trace_db.finish_trace(
                    trace_id=trace_id,
                    status=final_status,
                    final_answer=result.final_answer,
                    total_steps=result.turns,
                    total_tool_calls=result.total_tool_calls,
                    total_tokens=result.tokens_used,
                    total_latency_ms=result.total_latency_ms,
                    final_model=result.final_model,
                    final_provider=result.final_provider,
                    error_message=result.error,
                    cancelled=result.cancelled,
                )
        except Exception as e:
            logger.warning("TraceDB finish_trace failed (non-blocking): %s", e)

        # 🆕 Checkpoint/Rollback (借鉴 RooCode checkpoints/)
        if config.enable_checkpoint and not result.cancelled:
            try:
                from app.core.agent.checkpoint import get_file_checkpoint_manager
                cpm = get_file_checkpoint_manager()
                modified_paths = list(result.file_changes.keys()) if result.file_changes else []
                await cpm.save(
                    agent_name=config.name,
                    user_message=user_message,
                    assistant_summary=result.final_answer[:200] if result.final_answer else "",
                    modified_files=modified_paths,
                    model_used=result.final_model or "",
                    tokens_used=result.tokens_used or 0,
                    tool_calls_count=result.total_tool_calls or 0,
                    turn_number=result.turns or 1,
                )
                logger.info(
                    "Agent '%s': checkpoint saved (%d files)",
                    config.name, len(modified_paths),
                )
            except Exception as e:
                logger.warning("Checkpoint save failed (non-blocking): %s", e)

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

        # 🆕 反思闭环：LLM 自省评估 + 保存 LESSON 记忆到图存储
        try:
            from app.core.agent.reflection import get_reflection_manager
            rm = get_reflection_manager()
            if rm.config.enabled:
                # 错误时仅当 reflect_on_error=True 才触发反思
                should_reflect = result.error == "" or rm.config.reflect_on_error
                if should_reflect:
                    actions_parts = [
                        f"Agent: {config.name}",
                        f"Turns: {result.turns}",
                        f"Tool calls: {result.total_tool_calls}",
                    ]
                    if result.tool_results:
                        tool_names = sorted(set(
                            tr.tool_name for tr in result.tool_results
                        ))
                        actions_parts.append(
                            f"Tools used: {', '.join(tool_names[:10])}"
                        )
                    if result.error:
                        actions_parts.append(
                            f"Error: {result.error[:200]}"
                        )
                    agent_actions = "\n".join(actions_parts)

                    await rm.after_run(
                        run_result=result,
                        task_description=user_message,
                        agent_actions=agent_actions,
                    )
        except Exception as e:
            logger.warning("Reflection after_run failed (non-blocking): %s", e)

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

    @staticmethod
    def _persist_file_changes(
        trace_db: Any,
        tool_call_id: uuid.UUID,
        trace_id: uuid.UUID,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> None:
        """检测文件类型工具调用并持久化文件变更记录"""
        # 确定该工具是否为文件操作类工具
        file_tools = {
            "file_write", "write_file", "file_operation", "create_file",
            "file_read", "read_file", "delete_file", "rename_file",
            "text_editor", "str_replace", "insert_content",
        }
        if tool_name not in file_tools:
            return

        file_path = arguments.get("path") or arguments.get("file_path") or arguments.get("filePath") or ""
        if not file_path:
            return

        # 推断 change_type
        create_types = {"file_write", "write_file", "create_file"}
        delete_types = {"delete_file"}
        rename_types = {"rename_file"}

        if tool_name in create_types:
            change_type = FileChangeType.CREATE
        elif tool_name in delete_types:
            change_type = FileChangeType.DELETE
        elif tool_name in rename_types:
            change_type = FileChangeType.RENAME
        else:
            change_type = FileChangeType.MODIFY

        # 提取内容
        content_after = None
        if change_type in (FileChangeType.CREATE, FileChangeType.MODIFY):
            content_after = arguments.get("content") or arguments.get("new_str") or arguments.get("new_content") or ""

        content_before = arguments.get("old_str") or arguments.get("content_before") or None

        # 推断语言
        language = None
        if file_path:
            ext_map = {
                ".py": "python", ".js": "javascript", ".ts": "typescript",
                ".vue": "vue", ".jsx": "jsx", ".tsx": "tsx",
                ".go": "go", ".rs": "rust", ".java": "java",
                ".cpp": "cpp", ".c": "c", ".css": "css", ".html": "html",
                ".json": "json", ".yaml": "yaml", ".yml": "yaml",
                ".md": "markdown", ".sql": "sql", ".sh": "shell",
            }
            for ext, lang in ext_map.items():
                if file_path.endswith(ext):
                    language = lang
                    break

        try:
            trace_db.log_file_change(
                tool_call_id=tool_call_id,
                trace_id=trace_id,
                file_path=file_path,
                change_type=change_type,
                content_before=content_before,
                content_after=content_after,
                language=language,
                file_size_before=len(content_before or ""),
                file_size_after=len(content_after or ""),
            )
        except Exception as e:
            logger.debug("File change persist skipped: %s", e)

    @staticmethod
    def _git_auto_commit(user_message: str, agent_name: str) -> tuple[str, list[str]]:
        """
        Git 自动提交 (借鉴 Aider Git-Native 编辑)

        每次 Agent 代码修改后自动:
        1. git add -A (暂存所有变更)
        2. git diff --cached --stat (查看变更概要)
        3. git commit -m "AI agent: {user_message} [{agent_name}]"

        Returns:
            (commit_message, changed_files) — 如果没有变更返回 ("", [])
        """
        # 检查是否在 git 仓库中
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                logger.debug("Not a git repository, skipping auto-commit")
                return "", []
        except Exception:
            return "", []

        # git add -A
        try:
            subprocess.run(
                ["git", "add", "-A"],
                capture_output=True, text=True, timeout=10,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning("git add -A failed: %s", e.stderr.strip())
            return "", []

        # git diff --cached --name-only 获取变更文件列表
        try:
            diff_result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True, text=True, timeout=10,
                check=True,
            )
            changed_files = [
                f.strip() for f in diff_result.stdout.strip().split("\n")
                if f.strip()
            ]
        except subprocess.CalledProcessError:
            changed_files = []

        if not changed_files:
            # 没有变更，回退 git add
            subprocess.run(
                ["git", "reset", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            return "", []

        # 生成 commit message
        safe_message = user_message.replace("\n", " ").strip()[:120]
        commit_msg = f"AI agent: {safe_message} [{agent_name}]"

        # git commit
        try:
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                capture_output=True, text=True, timeout=10,
                check=True,
            )
            logger.info(
                "Git auto-commit: %d files — %s",
                len(changed_files), commit_msg,
            )
        except subprocess.CalledProcessError as e:
            logger.warning("git commit failed: %s", e.stderr.strip())
            # 回退暂存区
            subprocess.run(
                ["git", "reset", "HEAD"],
                capture_output=True, text=True, timeout=5,
            )
            return "", []

        return commit_msg, changed_files


# ── 流式 AgentRunner（WebSocket 友好） ──────────────────────

class StreamingAgentRunner(AgentRunner):
    """
    支持流式输出的 AgentRunner

    适用于 WebSocket / SSE 场景，每轮 LLM 调用和工具调用
    都通过 yield 方式推送给前端。

    🆕 文件编辑工具执行后自动产出 diff 事件，供前端 diff-viewer 展示。
    """

    def __init__(self, diff_engine: DiffEngine | None = None, **kwargs):
        super().__init__(**kwargs)
        self._diff = diff_engine or DiffEngine()

    async def run_stream(
        self,
        config: AgentConfig,
        user_message: str,
        model_router=None,
    ):
        """
        流式执行 Agent 并 yield 进度事件

        Yields:
            {"type": "turn_start"|"tool_call"|"tool_result"|"diff"|"final_answer"|"error", ...}
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

            # ── 流式 LLM 推理：逐 token 推送 + 收集完整响应 ──
            streamed_content_parts: list[str] = []
            has_streamed = False

            try:
                async for token in router.generate_stream(request):
                    has_streamed = True
                    streamed_content_parts.append(token)
                    yield {
                        "type": "token",
                        "delta": token,
                        "turn": turn,
                    }
            except NotImplementedError:
                pass  # 模型不支持流式，回退到非流式

            if has_streamed:
                streamed_content = "".join(streamed_content_parts)
                # 流式之后做一次轻量 generate 获取 tool_calls/finish_reason
                # 仅当有工具且流式内容不像是完整工具调用结果时执行
                if has_tools and streamed_content.strip():
                    try:
                        response = await router.generate(request)
                    except Exception:
                        # 假响应：如果工具信息没获取到，假定不是 tool_calls
                        from app.core.model_router import ModelResponse
                        response = ModelResponse(
                            content=streamed_content,
                            model_used="stream",
                            provider="stream",
                            finish_reason="stop",
                        )
                else:
                    from app.core.model_router import ModelResponse
                    response = ModelResponse(
                        content=streamed_content,
                        model_used="stream",
                        provider="stream",
                        finish_reason="stop",
                    )
            else:
                # 回退到阻塞式
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

                # 构建 call_id → arguments 映射（供 diff 事件使用）
                tc_args_map: dict[str, dict[str, Any]] = {}
                for tc in response.tool_calls:
                    cid = tc.get("id", "")
                    func_info = tc.get("function", {})
                    raw_args = func_info.get("arguments", {})
                    if isinstance(raw_args, str):
                        try:
                            import json as _json
                            raw_args = _json.loads(raw_args) if raw_args else {}
                        except Exception:
                            raw_args = {}
                    tc_args_map[cid] = raw_args

                # 逐个执行工具并推送结果
                async for event in self._executor.execute_with_stream(
                    response.tool_calls, timeout=config.tool_timeout
                ):
                    call_id = event.get("tool_call_id", "")
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

                        # 🆕 文件编辑工具 → 生成 diff
                        if event["status"] == "completed":
                            diff_data = self._stream_diff(
                                tool_name=event["tool_name"],
                                arguments=tc_args_map.get(call_id, {}),
                                result=event.get("result"),
                            )
                            if diff_data:
                                yield diff_data

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

    # ── Diff 集成 ───────────────────────────────────────────

    def _stream_diff(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: Any,
    ) -> dict[str, Any] | None:
        """
        检测是否为文件编辑工具调用，若真则生成 diff 事件。

        Returns:
            {"type": "diff", "data": {...}} 或 None
        """
        diff = self._diff.generate_from_tool(tool_name, arguments, result)
        if diff:
            return {"type": "diff", "data": diff}
        return None
