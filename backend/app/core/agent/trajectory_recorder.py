"""
TrajectoryRecorder — Agent 轨迹记录系统

借鉴 Trae Agent trajectory_recorder.py 设计：
- 增量记录每个 Agent 步骤（LLM 交互 + 工具调用 + 状态转换）
- 每步后立即持久化（防止崩溃丢失）
- 结构化 JSON 输出（完整可重放）

用法:
    recorder = TrajectoryRecorder(agent_id="my-agent", output_dir="trajectories/")
    recorder.record_step(step_data)
    recorder.save()  # 增量写入

输出格式:
    {
      "agent_id": "...",
      "session_id": "...",
      "started_at": "...",
      "steps": [
        {
          "step_number": 1,
          "state": "THINKING",
          "llm_request": {...},
          "llm_response": {...},
          "tool_calls": [...],
          "tool_results": [...],
          "latency_ms": 1234,
          "tokens_used": 567
        }
      ],
      "summary": {...}
    }
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.tools.schema import ToolResult

logger = logging.getLogger("agent.trajectory")


@dataclass
class TrajectoryStep:
    """单步轨迹记录"""
    step_number: int = 0
    state: str = ""  # THINKING | CALLING_TOOL | REFLECTING | COMPLETED | ERROR
    started_at: str = ""
    completed_at: str = ""

    # LLM 交互
    llm_model: str = ""
    llm_provider: str = ""
    llm_request_prompt: str = ""
    """截断后的用户提示词快照"""
    llm_response_content: str = ""
    llm_finish_reason: str = ""
    llm_tokens_used: int = 0

    # 工具调用
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    """[{"id": ..., "function": {"name": ..., "arguments": ...}}, ...]"""
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    """[{"tool_name": ..., "success": ..., "result": ..., "error": ...}, ...]"""

    # 性能
    llm_latency_ms: float = 0.0
    """LLM 调用耗时"""
    tools_latency_ms: float = 0.0
    """工具执行总耗时"""
    total_latency_ms: float = 0.0

    # 元数据
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrajectorySummary:
    """轨迹摘要"""
    total_steps: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    final_model: str = ""
    final_provider: str = ""
    error: str = ""
    cancelled: bool = False
    completed_at: str = ""

    @property
    def success(self) -> bool:
        return not self.error and not self.cancelled


class TrajectoryRecorder:
    """Agent 轨迹记录器 — 增量保存 + 结构化 JSON"""

    def __init__(
        self,
        agent_id: str = "default",
        session_id: str = "",
        output_dir: str = "trajectories/",
    ) -> None:
        self.agent_id = agent_id
        self.session_id = session_id
        self.output_dir = output_dir

        self.started_at = datetime.now(timezone.utc).isoformat()
        self.steps: list[TrajectoryStep] = []
        self.summary = TrajectorySummary()
        self._current_step: TrajectoryStep | None = None
        self._saved_count: int = 0

        os.makedirs(self.output_dir, exist_ok=True)

    def new_step(self, step_number: int) -> TrajectoryStep:
        """创建新步骤"""
        step = TrajectoryStep(
            step_number=step_number,
            state="THINKING",
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._current_step = step
        self.steps.append(step)
        return step

    def record_llm_request(
        self,
        model: str,
        provider: str,
        prompt_snapshot: str,
    ) -> None:
        """记录 LLM 请求"""
        if self._current_step:
            self._current_step.llm_model = model
            self._current_step.llm_provider = provider
            self._current_step.llm_request_prompt = prompt_snapshot[:1000]

    def record_llm_response(
        self,
        content: str,
        finish_reason: str,
        tokens_used: int = 0,
        latency_ms: float = 0.0,
    ) -> None:
        """记录 LLM 响应"""
        if self._current_step:
            self._current_step.state = "CALLING_TOOL" if finish_reason == "tool_calls" else "COMPLETED"
            self._current_step.llm_response_content = content[:2000]
            self._current_step.llm_finish_reason = finish_reason
            self._current_step.llm_tokens_used = tokens_used
            self._current_step.llm_latency_ms = latency_ms

    def record_tool_calls(self, tool_calls: list[dict[str, Any]]) -> None:
        """记录工具调用"""
        if self._current_step:
            self._current_step.tool_calls = [
                {
                    "id": tc.get("id", ""),
                    "function": {
                        "name": tc.get("function", {}).get("name", "unknown"),
                        "arguments": tc.get("function", {}).get("arguments", "{}"),
                    },
                }
                for tc in tool_calls
            ]

    def record_tool_results(
        self,
        results: list[ToolResult],
        latency_ms: float = 0.0,
    ) -> None:
        """记录工具执行结果"""
        if self._current_step:
            self._current_step.state = "REFLECTING"
            self._current_step.tool_results = [
                {
                    "tool_name": r.tool_name,
                    "success": r.success,
                    "result": str(r.result)[:1000] if r.success else "",
                    "error": r.error or "",
                    "latency_ms": r.latency_ms,
                }
                for r in results
            ]
            self._current_step.tools_latency_ms = latency_ms

    def record_error(self, error: str) -> None:
        """记录错误"""
        if self._current_step:
            self._current_step.state = "ERROR"
            self._current_step.error = error[:500]

    def complete_step(self) -> None:
        """完成当前步骤"""
        if self._current_step:
            self._current_step.completed_at = datetime.now(timezone.utc).isoformat()
            if self._current_step.llm_latency_ms and self._current_step.tools_latency_ms:
                self._current_step.total_latency_ms = (
                    self._current_step.llm_latency_ms + self._current_step.tools_latency_ms
                )

        # 增量保存
        self._incremental_save()

    def finalize(
        self,
        total_turns: int = 0,
        total_tool_calls: int = 0,
        total_tokens: int = 0,
        total_latency_ms: float = 0.0,
        final_model: str = "",
        final_provider: str = "",
        error: str = "",
        cancelled: bool = False,
    ) -> None:
        """完成整体轨迹"""
        self.summary = TrajectorySummary(
            total_steps=total_turns,
            total_tool_calls=total_tool_calls,
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
            final_model=final_model,
            final_provider=final_provider,
            error=error,
            cancelled=cancelled,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        self.save()

    def _incremental_save(self) -> None:
        """增量保存：仅写入新增的步骤"""
        new_steps = self.steps[self._saved_count:]
        if not new_steps:
            return

        filepath = os.path.join(self.output_dir, f"{self.agent_id}_{self.session_id}.jsonl")
        with open(filepath, "a", encoding="utf-8") as f:
            for step in new_steps:
                f.write(json.dumps(self._step_to_dict(step), ensure_ascii=False) + "\n")

        self._saved_count = len(self.steps)

    def save(self, filename: str | None = None) -> str:
        """完整保存轨迹为 JSON 文件，返回文件路径"""
        if filename is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{self.agent_id}_{self.session_id}_{timestamp}.json"

        filepath = os.path.join(self.output_dir, filename)

        data = self.to_dict()
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info(
            "Trajectory saved: %s (%d steps, %d KB)",
            filepath, len(self.steps), os.path.getsize(filepath) // 1024,
        )
        return filepath

    def to_dict(self) -> dict[str, Any]:
        """序列化为完整字典"""
        return {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "started_at": self.started_at,
            "steps": [self._step_to_dict(s) for s in self.steps],
            "summary": asdict(self.summary),
        }

    @staticmethod
    def _step_to_dict(step: TrajectoryStep) -> dict[str, Any]:
        return {
            "step_number": step.step_number,
            "state": step.state,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
            "llm_model": step.llm_model,
            "llm_provider": step.llm_provider,
            "llm_request_prompt": step.llm_request_prompt[:500],
            "llm_response_content": step.llm_response_content[:500],
            "llm_finish_reason": step.llm_finish_reason,
            "llm_tokens_used": step.llm_tokens_used,
            "tool_calls": step.tool_calls,
            "tool_results": step.tool_results,
            "llm_latency_ms": step.llm_latency_ms,
            "tools_latency_ms": step.tools_latency_ms,
            "total_latency_ms": step.total_latency_ms,
            "error": step.error,
            "metadata": step.metadata,
        }
