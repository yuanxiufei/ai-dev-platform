"""
SearchTrace — 搜索全链路追踪与可视化

借鉴 SAG search-service.ts 的 SearchTrace 类型:
  - 记录每步耗时 (timings)
  - 记录中间实体 ID 列表
  - 记录事件快照 (eventSnapshots)
  - 降级路径追踪 (fallbackReason)
  - 同时支持现有的 TrajectoryRecorder 集成

用法:
    from app.core.rag.search_trace import SearchTracer

    tracer = SearchTracer()
    with tracer.step("step1"):
        entities = await extract_entities(query)
        tracer.record_entities(entities)

    print(tracer.report())  # 人类可读报告
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.rag.graph_rag.models import SearchTrace, SearchTraceStep, SearchTraceEvent

logger = logging.getLogger("app.core.rag.search_trace")


@dataclass
class TraceStep:
    """可记录的追踪步骤"""
    key: str
    title: str = ""
    start_time: float = 0
    end_time: float = 0
    detail: str = ""
    payload: Any = None
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0

    @property
    def status(self) -> str:
        if self.error:
            return "failed"
        if self.end_time:
            return "done"
        return "running"


class SearchTracer:
    """
    搜索全链路追踪器

    特性:
      - 步骤计时 (context manager / 手动 start/end)
      - 实体/事件/切片中间结果记录
      - 降级路径追踪
      - 导出: dict | JSON | SearchTrace 模型
      - 集成: 可同步写入 TrajectoryRecorder
    """

    def __init__(self, query: str = "", search_mode: str = "standard"):
        self.query = query
        self.search_mode = search_mode
        self.trace_id: str = ""
        self._steps: dict[str, TraceStep] = {}
        self._current_step: Optional[str] = None
        self._entities: list[dict] = []
        self._events: list[SearchTraceEvent] = []
        self._sections: list[dict] = []
        self._fallback_reason: str = ""
        self._start_time: float = time.monotonic()
        self._trajectory: Optional[Any] = None  # TrajectoryRecorder 引用

    # ── 步骤管理 ─────────────────────────────────────────

    @contextmanager
    def step(self, key: str, title: str = ""):
        """上下文管理器: 自动计时"""
        self.start_step(key, title)
        try:
            yield self
        except Exception as e:
            self._steps[key].error = str(e)
            raise
        finally:
            self.end_step(key)

    def start_step(self, key: str, title: str = ""):
        """开始一个步骤"""
        self._current_step = key
        self._steps[key] = TraceStep(
            key=key, title=title or key,
            start_time=time.monotonic(),
        )

    def end_step(self, key: str, detail: str = "", payload: Any = None):
        """结束一个步骤"""
        if key in self._steps:
            step = self._steps[key]
            step.end_time = time.monotonic()
            if detail:
                step.detail = detail
            if payload is not None:
                step.payload = payload
            logger.debug(
                "SearchTrace [%s] %s: %.1fms %s",
                self.trace_id or "-", key, step.duration_ms, detail[:80] if detail else ""
            )
        self._current_step = None

    def record_error(self, key: str, error: str):
        """记录步骤错误"""
        if key in self._steps:
            self._steps[key].error = error

    # ── 数据记录 ─────────────────────────────────────────

    def record_entities(self, entities: list[dict]):
        """记录召回实体"""
        self._entities = entities

    def record_events(self, events: list[SearchTraceEvent]):
        """记录事件快照 (追加模式)"""
        by_id = {e.id: e for e in self._events}
        for e in events:
            by_id[e.id] = e
        self._events = list(by_id.values())

    def record_sections(self, sections: list[dict]):
        """记录最终切片"""
        self._sections = sections

    def set_fallback(self, reason: str):
        """设置降级原因"""
        self._fallback_reason = reason
        logger.info("SearchTrace fallback: %s", reason)

    # ── 连接 TrajectoryRecorder ─────────────────────────

    def bind_trajectory(self, recorder):
        """绑定到 TrajectoryRecorder，同步写入"""
        self._trajectory = recorder
        if recorder and hasattr(recorder, "record_event"):
            recorder.record_event("search_trace_start", {
                "query": self.query,
                "search_mode": self.search_mode,
            })

    async def flush_to_trajectory(self, trace_id: str):
        """将追踪结果刷入 TrajectoryRecorder"""
        if not self._trajectory:
            return
        try:
            report = self.report()
            self._trajectory.record_event("search_trace_end", {
                "trace_id": trace_id,
                "steps": len(self._steps),
                "total_entities": len(self._entities),
                "total_events": len(self._events),
                "total_sections": len(self._sections),
                "total_duration_ms": self.total_duration_ms,
                "fallback": self._fallback_reason or None,
                "steps_detail": [
                    {"key": k, "title": s.title, "duration_ms": s.duration_ms, "status": s.status}
                    for k, s in self._steps.items()
                ],
            })
        except Exception as e:
            logger.warning("Failed to flush trace to trajectory: %s", e)

    # ── 导出 ─────────────────────────────────────────────

    @property
    def total_duration_ms(self) -> float:
        return (time.monotonic() - self._start_time) * 1000

    def to_model(self) -> SearchTrace:
        """导出为 SearchTrace 数据模型"""
        return SearchTrace(
            trace_id=self.trace_id,
            query=self.query,
            search_mode=self.search_mode,
            query_entities=[e.get("name", "") for e in self._entities],
            recalled_entities=self._entities,
            event_snapshots=self._events,
            timings={k: s.duration_ms for k, s in self._steps.items()},
            fallback_reason=self._fallback_reason,
            steps=[
                SearchTraceStep(
                    key=s.key, title=s.title, detail=s.detail,
                    status=s.status, duration_ms=s.duration_ms,
                    payload=s.payload,
                )
                for s in self._steps.values()
            ],
        )

    def report(self) -> dict:
        """生成结构化报告"""
        return {
            "query": self.query,
            "search_mode": self.search_mode,
            "trace_id": self.trace_id,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "fallback": self._fallback_reason or None,
            "steps": [
                {
                    "key": s.key,
                    "title": s.title,
                    "duration_ms": round(s.duration_ms, 2),
                    "status": s.status,
                    "detail": s.detail[:200] if s.detail else "",
                    "error": s.error,
                }
                for s in self._steps.values()
            ],
            "summary": {
                "entities_recalled": len(self._entities),
                "events_snapshotted": len(self._events),
                "sections_returned": len(self._sections),
            },
        }

    def report_text(self) -> str:
        """生成人类可读报告"""
        r = self.report()
        lines = [
            f"SearchTrace: {r['query'][:80]}",
            f"  模式: {r['search_mode']}  总耗时: {r['total_duration_ms']}ms",
        ]
        if r["fallback"]:
            lines.append(f"  ⚠ 降级: {r['fallback']}")

        lines.append("  步骤:")
        for s in r["steps"]:
            icon = "✓" if s["status"] == "done" else "✗" if s["status"] == "failed" else "…"
            lines.append(
                f"    {icon} {s['title']:30s} {s['duration_ms']:>8.1f}ms"
                + (f"  [{s['status']}]" if s["status"] != "done" else "")
            )
            if s["error"]:
                lines.append(f"         错误: {s['error']}")

        lines.append(
            f"  统计: 实体={r['summary']['entities_recalled']} "
            f"事件={r['summary']['events_snapshotted']} "
            f"切片={r['summary']['sections_returned']}"
        )
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        """导出 JSON"""
        r = self.report()
        # 处理不可序列化对象
        for s in r["steps"]:
            if s.get("payload") and not isinstance(s["payload"], (str, int, float, bool, list, dict, type(None))):
                s["payload"] = str(s["payload"])[:500]
        return json.dumps(r, ensure_ascii=False, indent=indent)


# ── 全局追踪器工厂 ──────────────────────────────────────────

_tracers: dict[str, SearchTracer] = {}


def get_tracer(session_id: str = "__default__", query: str = "") -> SearchTracer:
    """获取或创建追踪器"""
    if session_id not in _tracers:
        _tracers[session_id] = SearchTracer(query=query)
    return _tracers[session_id]


def clear_tracer(session_id: str):
    """清除追踪器"""
    _tracers.pop(session_id, None)
