"""
Agent 对话路由 — 同步 + 流式 Agent 对话

端点:
  POST /agent/chat       — 同步 Agent 对话（含工具调用循环）
  POST /agent/chat/stream — SSE 流式 Agent 对话（实时推送每轮进度）
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.core.agent.agent_config import AgentConfig, AgentHook, AgentRunContext
from app.core.agent.agent_runner import AgentRunner, StreamingAgentRunner
from app.core.model_router import get_model_router
from app.core.tools.registry import get_tool_registry
from app.models.agent_models import TraceDB

logger = logging.getLogger("api.agent.chat")


def _clean_answer(text: str) -> str:
    """去掉啰嗦前缀"""
    prefixes = ["根据工具返回的信息，","根据工具调用结果，","根据工具获取的数据，","根据工具获取的信息，","根据返回的数据，","基于工具结果，","根据API的输出结果，","根据获取的天气数据，","根据获取的数据，","根据工具结果，"]
    for p in prefixes:
        if text.startswith(p):
            return text[len(p):].lstrip()
    return text

router = APIRouter(prefix="/agent", tags=["agent"])


# ── 请求/响应模型 ──────────────────────────────────────────

class AgentChatRequest(BaseModel):
    """Agent 对话请求"""
    message: str = Field(..., description="用户消息")
    agent_name: str = Field(default="default", description="Agent 名称")
    instructions: str = Field(default="", description="Agent 系统指令")
    tools: list[str] = Field(default_factory=list, description="工具名称白名单（空=全部）")
    tool_categories: list[str] = Field(default_factory=list, description="工具分类筛选")
    max_turns: int = Field(default=10, ge=1, le=50, description="最大循环轮次")
    preferred_model: str = Field(default="", description="首选模型")
    session_id: str = Field(default="", description="会话 ID（用于多轮对话）")

    model_config = {"extra": "allow"}


class AgentChatResponse(BaseModel):
    """Agent 对话响应"""
    answer: str = Field(..., description="最终回答")
    turns: int = Field(default=0, description="循环轮次")
    tool_calls: int = Field(default=0, description="工具调用次数")
    model_used: str = Field(default="", description="最终使用的模型")
    provider: str = Field(default="", description="模型提供商")
    tokens_used: int = Field(default=0, description="总 token 消耗")
    latency_ms: float = Field(default=0, description="总耗时")
    error: str = Field(default="", description="错误信息")
    trace_id: str = Field(default="", description="Agent 执行轨迹 ID（可查询工具调用/文件变更详情）")


# ── 路由 ──────────────────────────────────────────────────

@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(payload: AgentChatRequest, request: Request) -> AgentChatResponse:
    """
    同步 Agent 对话 — 自动执行工具调用循环

    流程：
      User Message → LLM → [Tool Calls → Execute → Result → LLM] × N → Final Answer
    """
    registry = get_tool_registry()

    config = AgentConfig(
        name=payload.agent_name,
        instructions=payload.instructions or (
            "You are a helpful AI assistant with access to tools. "
            "Use tools when needed to answer user questions accurately. "
            "After receiving tool results, formulate a clear, concise response."
        ),
        tools=payload.tools,
        tool_categories=payload.tool_categories,
        max_turns=payload.max_turns,
        preferred_model=payload.preferred_model,
    )

    runner = AgentRunner(trace_db=TraceDB())
    result = await runner.run(
        config=config,
        user_message=payload.message,
    )

    return AgentChatResponse(
        answer=result.final_answer,
        turns=result.turns,
        tool_calls=result.total_tool_calls,
        model_used=result.final_model,
        provider=result.final_provider,
        tokens_used=result.tokens_used,
        latency_ms=result.total_latency_ms,
        error=result.error,
        trace_id=result.trace_id,
    )


@router.post("/chat/stream")
async def agent_chat_stream(payload: AgentChatRequest):
    """
    SSE 流式 Agent 对话 — 实时推送每轮进度

    事件格式：
      {"type":"turn_start","turn":1,"max_turns":10}
      {"type":"tool_call","tool_calls":[{"id":"...","name":"web_search","arguments":"..."}]}
      {"type":"tool_executing","tool_name":"web_search"}
      {"type":"tool_result","tool_name":"web_search","success":true,"result":"...","latency_ms":123}
      {"type":"final_answer","content":"...","model_used":"gpt-4o","turns":3}
    """
    registry = get_tool_registry()

    config = AgentConfig(
        name=payload.agent_name,
        instructions=payload.instructions or (
            "You are a helpful AI assistant with access to tools."
        ),
        tools=payload.tools,
        tool_categories=payload.tool_categories,
        max_turns=payload.max_turns,
        preferred_model=payload.preferred_model,
    )

    runner = StreamingAgentRunner()

    async def event_generator():
        async for event in runner.run_stream(
            config=config,
            user_message=payload.message,
        ):
            yield {"event": event.get("type", "message"), "data": json.dumps(event, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


# ── 轻量对话（不走 Agent 循环，直接调用） ─────────────────

@router.post("/chat/simple")
async def agent_chat_simple(payload: AgentChatRequest) -> dict[str, Any]:
    """
    轻量对话 — 跳过工具循环，仅做单次 LLM 调用

    适用于不需要工具调用的快速问答场景。
    """
    from app.core.model_router import ModelCapability, ModelRequest

    router = get_model_router()

    # 诊断信息
    api_candidates = router._get_api_candidates() if hasattr(router, '_get_api_candidates') else []
    chain_diag = {}
    for node in router._fallback_chain:
        chain_diag[node.name] = [
            {"name": m.name, "provider": getattr(m, "provider", "?"), "available": m.is_available}
            for m in node.models
        ]

    logger.info(
        "agent_chat_simple: preferred=%s, local_models=%d, api_candidates=%d, chain=%s",
        payload.preferred_model or "auto",
        len(router.local_models),
        len(api_candidates),
        {k: len(v) for k, v in chain_diag.items()},
    )
    logger.debug("fallback_chain detail: %s", chain_diag)

    request = ModelRequest(
        capability=ModelCapability.TEXT_GENERATION,
        prompt=payload.message,
        system_prompt=payload.instructions or "You are a helpful assistant.",
        max_tokens=4096,
        preferred_model=payload.preferred_model or None,
    )

    response = await router.generate(request)

    logger.debug(
        "fallback_chain errors: %s",
        {
            node.name: [
                {"name": m.name, "available": m.is_available, "error": getattr(m, "last_error", None)}
                for m in node.models
            ]
            for node in router._fallback_chain
        },
    )

    # 网络连通性诊断（仅 DEBUG 日志级别，避免无谓的 TCP 连接开销）
    if logger.isEnabledFor(logging.DEBUG):
        import asyncio
        from urllib.parse import urlparse
        import socket as _socket

        async def _check_tcp(host: str, port: int) -> str:
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=2.0,
                )
                writer.close()
                await writer.wait_closed()
                return "OK"
            except asyncio.TimeoutError:
                return "timeout (2s)"
            except _socket.gaierror:
                return "DNS failed"
            except OSError as e:
                return f"{e.strerror if hasattr(e, 'strerror') else e}"

        net_diag: dict[str, str] = {}
        for node in router._fallback_chain:
            for m in node.models:
                base_url = getattr(getattr(m, "config", None), "base_url", None)
                if not base_url:
                    continue
                host = urlparse(base_url).hostname or base_url
                port = urlparse(base_url).port or (443 if base_url.startswith("https") else 80)
                result = await _check_tcp(host, port)
                net_diag[m.name] = f"{result} {host}:{port}"
        logger.debug("fallback_chain network: %s", net_diag)

    return {
        "answer": _clean_answer(response.content),
        "model_used": response.model_used,
        "provider": response.provider,
        "tokens_used": response.tokens_used,
    }
