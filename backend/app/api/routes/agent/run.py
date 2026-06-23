"""
Agent Run 路由 — One-shot Agent 完整执行

端点:
  POST /agent/run       — 全量 Agent 执行（plan → execute → diff → result）
  POST /agent/run/stream — SSE 流式版本
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.agent.agent_config import AgentConfig
from app.core.agent.agent_runner import AgentRunner, AgentRunResult, StreamingAgentRunner
from app.core.diff.diff_engine import DiffEngine
from app.core.model_router import get_model_router
from app.core.tools.registry import get_tool_registry

logger = logging.getLogger("api.agent.run")

router = APIRouter(prefix="/agent", tags=["agent"])


# ── 请求/响应模型 ──────────────────────────────────────────

class AgentRunRequest(BaseModel):
    """一次性 Agent 执行请求"""
    task: str = Field(..., description="用户任务描述（如「在 src/ 下创建一个 FastAPI 健康检查路由」）")
    instructions: str = Field(
        default="",
        description="自定义系统指令（空=使用默认编程助手指令）"
    )
    tools: list[str] = Field(default_factory=list, description="工具白名单（空=全部）")
    tool_categories: list[str] = Field(default_factory=list, description="工具分类筛选")
    max_turns: int = Field(default=15, ge=1, le=50)
    preferred_model: str = Field(default="")
    workspace_root: str = Field(default=".", description="沙箱工作区根路径")


class StepItem(BaseModel):
    """单个执行步骤"""
    tool_name: str = ""
    tool_args: dict[str, Any] = Field(default_factory=dict)
    success: bool = False
    result: str = ""
    error: str = ""
    latency_ms: float = 0.0
    diff: dict[str, Any] | None = None


class AgentRunResponse(BaseModel):
    """一次性 Agent 执行响应"""
    success: bool
    task: str
    plan: str = ""          # LLM 生成的任务计划
    steps: list[StepItem] = Field(default_factory=list)
    diffs: list[dict[str, Any]] = Field(default_factory=list)
    final_answer: str = ""
    turns: int = 0
    total_tool_calls: int = 0
    total_latency_ms: float = 0
    model_used: str = ""
    provider: str = ""
    tokens_used: int = 0
    error: str = ""


# ── 路由 ──────────────────────────────────────────────────

@router.post("/run", response_model=AgentRunResponse)
async def agent_run(payload: AgentRunRequest) -> AgentRunResponse:
    """
    One-shot Agent 完整执行 — 一步到位返回 plan + steps + diffs + result

    与 /agent/chat 区别：
      - /agent/chat：交互式多轮对话
      - /agent/run：一次性任务（适合 CI/CD、批处理、API 调用）

    返回：
      - plan: LLM 拆解的步骤计划
      - steps: 每个步骤的工具调用详情（含 diff）
      - diffs: 所有文件变更的 diff 集合
      - final_answer: 最终执行摘要
    """
    registry = get_tool_registry()
    diff_engine = DiffEngine(workspace_root=payload.workspace_root or ".")

    default_instructions = (
        "You are an expert programmer. Your task is to plan, implement, and verify code changes.\n\n"
        "Workflow:\n"
        "1. **Plan**: Break the task into concrete steps\n"
        "2. **Read**: First read relevant files to understand the codebase\n"
        "3. **Implement**: Use str_replace / create_file to make changes\n"
        "4. **Verify**: Use terminal to run tests or check syntax\n"
        "5. **Report**: Summarize what was done\n\n"
        "CRITICAL: Before writing any file, read it first (if it exists). After changes, verify them."
        "Always use str_replace for existing files and create_file for new files."
    )

    config = AgentConfig(
        name="one-shot-run",
        instructions=payload.instructions or default_instructions,
        tools=payload.tools,
        tool_categories=payload.tool_categories,
        max_turns=payload.max_turns,
        preferred_model=payload.preferred_model,
        tool_timeout=60.0,
    )

    runner = AgentRunner()
    result: AgentRunResult = await runner.run(
        config=config,
        user_message=payload.task,
    )

    # ── 构建步骤 + diff 集合 ──
    steps: list[StepItem] = []
    diffs: list[dict[str, Any]] = []

    for tr in result.tool_results:
        step = StepItem(
            tool_name=tr.tool_name,
            tool_args=tr.metadata.get("arguments", {}) if tr.metadata else {},
            success=tr.success,
            result=tr.result[:2000] if tr.result else "",
            error=tr.error or "",
            latency_ms=tr.latency_ms or 0,
        )

        # 生成 diff
        if tr.success and tr.metadata:
            diff_data = diff_engine.generate_from_tool(
                tool_name=tr.tool_name,
                arguments=tr.metadata.get("arguments", {}) if isinstance(tr.metadata, dict) else {},
                result=tr.result,
            )
            if diff_data:
                step.diff = diff_data
                diffs.append(diff_data)

        steps.append(step)

    # ── 提取 plan（取 first assistant content 或工具调用作为计划） ──
    plan = ""
    if result.final_answer:
        # 尝试从 final_answer 中提取步骤列表
        plan = result.final_answer[:500]

    return AgentRunResponse(
        success=result.success,
        task=payload.task,
        plan=plan,
        steps=steps,
        diffs=diffs,
        final_answer=result.final_answer,
        turns=result.turns,
        total_tool_calls=result.total_tool_calls,
        total_latency_ms=result.total_latency_ms,
        model_used=result.final_model,
        provider=result.final_provider,
        tokens_used=result.tokens_used,
        error=result.error,
    )


@router.post("/run/stream")
async def agent_run_stream(payload: AgentRunRequest):
    """
    SSE 流式 Agent 一次性执行 — 实时推送 plan → steps → diffs → result

    事件类型：
      {"type":"plan","data":"..."}
      {"type":"step","tool_name":"str_replace",...}
      {"type":"diff","data":{...}}
      {"type":"result","data":AgentRunResponse}
    """
    registry = get_tool_registry()
    diff_engine = DiffEngine(workspace_root=payload.workspace_root or ".")

    default_instructions = (
        "You are an expert programmer. Your task is to plan, implement, and verify code changes.\n\n"
        "Workflow:\n"
        "1. **Plan**: Break the task into concrete steps\n"
        "2. **Read**: First read relevant files to understand the codebase\n"
        "3. **Implement**: Use str_replace / create_file to make changes\n"
        "4. **Verify**: Use terminal to run tests or check syntax\n"
        "5. **Report**: Summarize what was done\n\n"
        "CRITICAL: Before writing any file, read it first (if it exists). After changes, verify them."
    )

    config = AgentConfig(
        name="one-shot-run-stream",
        instructions=payload.instructions or default_instructions,
        tools=payload.tools,
        tool_categories=payload.tool_categories,
        max_turns=payload.max_turns,
        preferred_model=payload.preferred_model,
        tool_timeout=60.0,
    )

    runner = StreamingAgentRunner(diff_engine=diff_engine)

    async def event_generator():
        collected_steps: list[dict] = []
        collected_diffs: list[dict] = []
        start_time = time.perf_counter()

        async for event in runner.run_stream(
            config=config,
            user_message=payload.task,
        ):
            ev_type = event.get("type", "")

            if ev_type == "tool_result" and event.get("success"):
                collected_steps.append({
                    "tool_name": event.get("tool_name"),
                    "success": event.get("success"),
                    "result": str(event.get("result", ""))[:500],
                    "latency_ms": event.get("latency_ms"),
                })

            if ev_type == "diff":
                collected_diffs.append(event.get("data", {}))
                yield {
                    "event": "diff",
                    "data": json.dumps({"type": "diff", "data": event.get("data", {})}, ensure_ascii=False),
                }
                continue

            if ev_type == "step":
                yield {
                    "event": "step",
                    "data": json.dumps(event, ensure_ascii=False),
                }
                continue

            if ev_type == "final_answer":
                total_latency = (time.perf_counter() - start_time) * 1000
                summary = {
                    "type": "result",
                    "data": {
                        "success": True,
                        "task": payload.task,
                        "steps": collected_steps,
                        "diffs": collected_diffs,
                        "final_answer": event.get("content", ""),
                        "turns": event.get("turns", 0),
                        "total_tool_calls": len(collected_steps),
                        "total_latency_ms": total_latency,
                        "model_used": event.get("model_used", ""),
                    },
                }
                yield {
                    "event": "result",
                    "data": json.dumps(summary, ensure_ascii=False),
                }
                continue

            # 其他事件
            yield {
                "event": ev_type or "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
