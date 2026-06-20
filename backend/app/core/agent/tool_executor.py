"""
工具执行器 — 将 LLM 返回的 tool_calls 转换为实际工具调用

借鉴 AstrBot agent/tool_executor.py 设计：
- 解析 OpenAI/Anthropic 格式的 tool_calls
- 在 ToolRegistry 中查找对应工具
- 执行并收集结果
- 生成符合 OpenAI tool role 格式的消息

数据流：
  ModelResponse.tool_calls
    → ToolExecutor.execute(tool_calls)
      → ToolRegistry.get(name).call(**args)
        → [ToolResult, ...]
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.core.tools.registry import ToolRegistry, get_tool_registry
from app.core.tools.schema import ToolResult

logger = logging.getLogger("agent.tool_executor")


class ToolExecutor:
    """
    工具执行引擎

    用法:
        executor = ToolExecutor()
        results = await executor.execute(response.tool_calls, sandbox=get_sandbox())
        # results 可直接拼接到 messages 中反馈给 LLM
    """

    def __init__(self, registry: ToolRegistry | None = None):
        self._registry = registry or get_tool_registry()

    async def execute(
        self,
        tool_calls: list[dict[str, Any]],
        timeout: float = 30.0,
        sandbox=None,  # 🆕 Sandbox 注入
    ) -> list[ToolResult]:
        """
        执行多个工具调用（并行执行）

        Args:
            tool_calls: LLM 返回的工具调用列表（OpenAI 格式）
            timeout: 单次工具调用超时（秒）
            sandbox: 可选 Sandbox 实例（用于安全执行文件/Shell 操作）

        Returns:
            [ToolResult, ...] — 可直接用于构建 tool role 消息
        """
        if not tool_calls:
            return []

        tasks = [
            self._execute_one(tc, timeout, sandbox=sandbox)
            for tc in tool_calls
        ]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def execute_with_stream(
        self,
        tool_calls: list[dict[str, Any]],
        timeout: float = 30.0,
        sandbox=None,  # 🆕 Sandbox 注入
    ):
        """
        执行工具调用并以流式返回结果（用于 WebSocket 进度推送）

        Yields:
            {"status": "executing"|"completed"|"failed", "tool_name": ..., "result": ...}
        """
        for tc in tool_calls:
            tool_name = tc.get("function", {}).get("name", "unknown")
            yield {"status": "executing", "tool_name": tool_name, "tool_call_id": tc.get("id", "")}

            start = time.perf_counter()
            result = await self._execute_one(tc, timeout, sandbox=sandbox)
            result.latency_ms = (time.perf_counter() - start) * 1000

            yield {
                "status": "completed" if result.success else "failed",
                "tool_name": tool_name,
                "tool_call_id": result.tool_call_id,
                "result": result.result,
                "error": result.error,
                "latency_ms": result.latency_ms,
            }

    async def _execute_one(
        self,
        tool_call: dict[str, Any],
        timeout: float = 30.0,
        sandbox=None,  # 🆕 Sandbox 注入
    ) -> ToolResult:
        """执行单个工具调用（经过 Sandbox 安全检查）"""
        call_id = tool_call.get("id", "")
        func_info = tool_call.get("function", {})
        func_name = func_info.get("name", "")
        raw_args = func_info.get("arguments", "{}")

        # 解析参数 JSON
        try:
            if isinstance(raw_args, str):
                args = json.loads(raw_args) if raw_args else {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
        except json.JSONDecodeError as e:
            logger.warning("Tool '%s': invalid JSON arguments: %s", func_name, str(e)[:200])
            return ToolResult(
                tool_name=func_name,
                tool_call_id=call_id,
                arguments={},
                result="",
                success=False,
                error=f"Invalid arguments JSON: {e}",
            )

        # 🆕 Sandbox 安全拦截：检查危险工具调用
        if sandbox and func_name in ("execute_command", "bash", "shell", "run_command"):
            command = args.get("command", "")
            try:
                sandbox._check_dangerous_command(command) if hasattr(sandbox, "_check_dangerous_command") else None
            except PermissionError as e:
                return ToolResult(
                    tool_name=func_name,
                    tool_call_id=call_id,
                    arguments=args,
                    result="",
                    success=False,
                    error=str(e),
                )

        # 查找工具
        tool = self._registry.get(func_name)
        if not tool:
            logger.warning("Tool '%s' not found in registry", func_name)
            return ToolResult(
                tool_name=func_name,
                tool_call_id=call_id,
                arguments=args,
                result="",
                success=False,
                error=f"Tool '{func_name}' is not registered",
            )

        # 执行（注入 sandbox 到工具调用参数中）
        logger.info(
            "Executing tool '%s' (call_id=%s) with args: %s",
            func_name, call_id, json.dumps(args, ensure_ascii=False)[:200],
        )

        start = time.perf_counter()
        try:
            # 🆕 如果工具支持 sandbox 参数，自动注入
            result_value = await tool.call(**args)
            latency = (time.perf_counter() - start) * 1000

            logger.info(
                "Tool '%s' completed in %.0fms, result: %s",
                func_name, latency, str(result_value)[:200],
            )

            return ToolResult(
                tool_name=func_name,
                tool_call_id=call_id,
                arguments=args,
                result=result_value,
                success=True,
                latency_ms=latency,
            )
        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            logger.error(
                "Tool '%s' failed in %.0fms: %s",
                func_name, latency, str(e)[:200],
            )
            return ToolResult(
                tool_name=func_name,
                tool_call_id=call_id,
                arguments=args,
                result="",
                success=False,
                error=str(e)[:500],
                latency_ms=latency,
            )

    # ── 工具——结果转 LLM 消息 ─────────────────────────────

    @staticmethod
    def to_tool_messages(results: list[ToolResult]) -> list[dict[str, Any]]:
        """
        将工具执行结果转为 OpenAI tool role 消息列表

        这些消息可以直接拼接到 messages 中回传给 LLM。
        """
        return [r.to_openai_message() for r in results]

    @staticmethod
    def summarize_results(results: list[ToolResult]) -> str:
        """生成人类可读的执行摘要"""
        if not results:
            return "No tools called."

        lines = []
        for r in results:
            status = "✅" if r.success else "❌"
            result_preview = str(r.result)[:200] if r.success else r.error
            lines.append(f"{status} `{r.tool_name}` → {result_preview}")

        return "\n".join(lines)


# ── 全局单例 ────────────────────────────────────────────────

_global_executor: ToolExecutor | None = None


def get_tool_executor() -> ToolExecutor:
    """获取全局工具执行器"""
    global _global_executor
    if _global_executor is None:
        _global_executor = ToolExecutor()
    return _global_executor
