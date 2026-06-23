"""
Agent Data Layer — 4 张结构化持久化表

AgentTrace     — Agent 执行轨迹（每次 Agent 运行建一条记录）
AgentToolCall  — 工具调用日志（每次 tool_call 建一条记录）
AgentFileChange — 文件变更记录（由文件类工具触发的文件变更）
AgentExecLog   — 执行日志（DEBUG/INFO/WARNING/ERROR 级别日志）

数据流:
  AgentRunner.run()
    → _trace_db.start_trace(...)           # 创建 AgentTrace(PENDING)
    → for each turn:
        → LLM 调用后：_trace_db.update_trace_progress(...)
        → 工具执行后：_trace_db.log_tool_call(...)
          → 文件变更时：_trace_db.log_file_change(...)
        → 错误时：_trace_db.log_exec(ERROR, ...)
    → 结束时：_trace_db.finish_trace(...)  # 更新 AgentTrace(COMPLETED)

设计原则:
- DB 写入与 Agent 主逻辑解耦（通过 TraceDB facade）
- 不阻塞 Agent 循环（write-and-forget，错误容忍）
- 遵循现有 SQLModel 模式（UUID PK、DateTime(timezone=True)、JSON→Text）
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Text
from sqlmodel import Column, Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── 枚举常量 ──────────────────────────────────────────────

class TraceStatus:
    """Agent 轨迹状态"""
    PENDING = "PENDING"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    REFLECTING = "REFLECTING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class FileChangeType:
    """文件变更类型"""
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    DELETE = "DELETE"
    RENAME = "RENAME"


# ── AgentTrace ────────────────────────────────────────────

class AgentTrace(SQLModel, table=True):
    """Agent 单次执行轨迹 — 完整的运行过程记录"""
    __tablename__ = "agent_traces"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # 标识
    agent_id: str = Field(max_length=255, description="Agent 名称/标识")
    session_id: str = Field(default="", max_length=255, description="会话 ID")
    conversation_id: uuid.UUID | None = Field(default=None, nullable=True, description="关联对话 session")

    # 输入/输出
    user_message: str = Field(sa_column=Column("user_message", Text), description="用户消息")
    final_answer: str | None = Field(default=None, sa_column=Column("final_answer", Text), description="最终回答")
    plan: dict | None = Field(default=None, sa_column=Column("plan", Text), description="Agent 生成的计划(JSON)")

    # 状态
    status: str = Field(default=TraceStatus.PENDING, max_length=20, description="PENDING|PLANNING|EXECUTING|REFLECTING|COMPLETED|ERROR|CANCELLED")

    # 统计
    total_steps: int = Field(default=0, description="总轮次")
    total_tool_calls: int = Field(default=0, description="工具调用总次数")
    total_tokens: int = Field(default=0, description="总 Token 消耗")
    total_latency_ms: float = Field(default=0.0, description="总耗时(毫秒)")

    # 模型信息
    final_model: str = Field(default="", max_length=100, description="最终使用的模型")
    final_provider: str = Field(default="", max_length=50, description="模型提供商")

    # 错误
    error_message: str | None = Field(default=None, sa_column=Column("error_message", Text))
    cancelled: bool = Field(default=False)

    # 元数据
    extra_metadata: dict | None = Field(default=None, sa_column=Column("extra_metadata", Text), description="额外元数据(JSON)")

    # 用户
    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)

    # 时间
    started_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))

    @property
    def is_finished(self) -> bool:
        return self.status in (TraceStatus.COMPLETED, TraceStatus.ERROR, TraceStatus.CANCELLED)

    @property
    def is_success(self) -> bool:
        return self.status == TraceStatus.COMPLETED


# ── AgentToolCall ─────────────────────────────────────────

class AgentToolCall(SQLModel, table=True):
    """单次工具调用日志 — Agent 循环中每一次 tool_call 的完整记录"""
    __tablename__ = "agent_tool_calls"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    trace_id: uuid.UUID = Field(foreign_key="agent_traces.id", ondelete="CASCADE", description="所属轨迹")

    # 位置信息
    step_number: int = Field(default=1, description="Agent 循环中的第几步")
    sequence: int = Field(default=0, description="同一步内的调用序号")

    # 工具信息
    tool_name: str = Field(max_length=100, description="工具名称")
    tool_call_id: str = Field(default="", max_length=100, description="LLM 返回的 tool_call_id")

    # 输入/输出
    arguments: dict | None = Field(default=None, sa_column=Column("arguments", Text), description="调用参数(JSON)")
    result: str | None = Field(default=None, sa_column=Column("result", Text), description="执行结果(截断)")
    result_full: str | None = Field(default=None, sa_column=Column("result_full", Text), description="完整结果")

    # 状态
    success: bool = Field(default=True)
    error_message: str | None = Field(default=None, sa_column=Column("error_message", Text))

    # 性能
    latency_ms: float = Field(default=0.0, description="工具执行耗时(毫秒)")

    # 沙箱
    sandbox_mode: str | None = Field(default=None, max_length=20, description="local|docker|k8s")

    # 元数据
    extra_metadata: dict | None = Field(default=None, sa_column=Column("extra_metadata", Text))

    # 时间
    started_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    completed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))


# ── AgentFileChange ───────────────────────────────────────

class AgentFileChange(SQLModel, table=True):
    """文件变更记录 — 由文件类工具触发的代码/配置变更"""
    __tablename__ = "agent_file_changes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tool_call_id: uuid.UUID = Field(foreign_key="agent_tool_calls.id", ondelete="CASCADE", description="触发变更的工具调用")
    trace_id: uuid.UUID = Field(foreign_key="agent_traces.id", ondelete="CASCADE", description="所属轨迹(便于直接查询)")

    # 文件信息
    file_path: str = Field(max_length=2000, description="文件路径")
    change_type: str = Field(max_length=20, description="CREATE|MODIFY|DELETE|RENAME")
    language: str | None = Field(default=None, max_length=50, description="编程语言")

    # 内容
    content_before: str | None = Field(default=None, sa_column=Column("content_before", Text), description="变更前内容")
    content_after: str | None = Field(default=None, sa_column=Column("content_after", Text), description="变更后内容")
    diff: str | None = Field(default=None, sa_column=Column("diff", Text), description="unified diff")

    # 大小
    file_size_before: int | None = Field(default=None, description="变更前文件大小(字节)")
    file_size_after: int | None = Field(default=None, description="变更后文件大小(字节)")

    # 元数据
    extra_metadata: dict | None = Field(default=None, sa_column=Column("extra_metadata", Text))

    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── AgentExecLog ──────────────────────────────────────────

class AgentExecLog(SQLModel, table=True):
    """Agent 执行日志 — DEBUG/INFO/WARNING/ERROR 结构化日志"""
    __tablename__ = "agent_execution_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    trace_id: uuid.UUID | None = Field(default=None, foreign_key="agent_traces.id", ondelete="SET NULL", nullable=True, description="关联轨迹")
    tool_call_id: uuid.UUID | None = Field(default=None, foreign_key="agent_tool_calls.id", ondelete="SET NULL", nullable=True, description="关联工具调用")

    # 日志级别
    level: str = Field(default="INFO", max_length=10, description="DEBUG|INFO|WARNING|ERROR")

    # 内容
    message: str = Field(sa_column=Column("message", Text), description="日志消息")

    # 上下文
    step_number: int | None = Field(default=None, description="Agent 循环步骤号")
    stage: str | None = Field(default=None, max_length=30, description="PLANNING|TOOL_CALL|REFLECTION|MIDDLEWARE|LLM|ERROR")
    agent_id: str | None = Field(default=None, max_length=255)

    # 元数据
    exec_context: dict | None = Field(default=None, sa_column=Column("exec_context", Text), description="执行上下文(JSON)")
    extra_metadata: dict | None = Field(default=None, sa_column=Column("extra_metadata", Text))

    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── 序列化辅助 ────────────────────────────────────────────

def _json_dumps(obj: Any) -> str | None:
    """安全 JSON 序列化"""
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return json.dumps({"error": "serialization_failed", "type": type(obj).__name__})


def _json_loads(raw: str | None) -> dict | list | None:
    """安全 JSON 反序列化"""
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _str_truncate(s: str, limit: int = 10000) -> str:
    """截断字符串到指定长度"""
    if len(s) > limit:
        return s[:limit] + f"\n... [truncated at {limit} chars, total {len(s)}]"
    return s


# ── TraceDB — 统一的 DB 持久化 Facade ────────────────────

class TraceDB:
    """
    Agent 数据持久化门面 (Facade)

    封装所有 DB 写入 / 更新逻辑，使 AgentRunner 与具体表结构解耦。
    每个写操作独立开短 Session，防止长时间占用连接。

    用法:
        trace_db = TraceDB(db_session_factory=get_db_session)
        trace_id = trace_db.start_trace("my-agent", "say hello")
        tool_call_id = trace_db.log_tool_call(trace_id, step=1, seq=0, ...)
        trace_db.log_file_change(tool_call_id, trace_id, "src/main.py", ...)
        trace_db.finish_trace(trace_id, status="COMPLETED", ...)
    """

    def __init__(self, db_session_factory=None):
        """
        Args:
            db_session_factory: 可调用对象，每次调用返回一个新的 SQLModel Session。
                例如: lambda: next(get_db())
        """
        self._session_factory = db_session_factory or self._default_factory

    @staticmethod
    def _default_factory():
        from app.core.db import engine
        from sqlmodel import Session
        return Session(engine)

    def start_trace(
        self,
        agent_id: str,
        user_message: str,
        session_id: str = "",
        user_id: uuid.UUID | None = None,
        conversation_id: uuid.UUID | None = None,
        plan: dict | None = None,
    ) -> uuid.UUID:
        """创建一条新的 AgentTrace 记录，返回 trace_id"""
        trace = AgentTrace(
            agent_id=agent_id,
            session_id=session_id,
            user_message=user_message,
            status=TraceStatus.PENDING,
            user_id=user_id,
            conversation_id=conversation_id,
            plan=_json_dumps(plan) if plan else None,
        )
        with self._session_factory() as session:
            session.add(trace)
            session.commit()
            session.refresh(trace)
            return trace.id

    def update_trace_status(
        self,
        trace_id: uuid.UUID,
        status: str,
        **kwargs: Any,
    ) -> None:
        """更新 AgentTrace 状态（PLANNING→EXECUTING→...→COMPLETED）"""
        with self._session_factory() as session:
            trace = session.get(AgentTrace, trace_id)
            if trace is None:
                return
            trace.status = status
            for key, value in kwargs.items():
                if hasattr(trace, key):
                    setattr(trace, key, value)
            if status in (TraceStatus.COMPLETED, TraceStatus.ERROR, TraceStatus.CANCELLED):
                trace.completed_at = _utc_now()
            trace.updated_at = _utc_now()
            session.add(trace)
            session.commit()

    def log_tool_call(
        self,
        trace_id: uuid.UUID,
        tool_name: str,
        step_number: int,
        sequence: int = 0,
        tool_call_id: str = "",
        arguments: dict | None = None,
        result: Any = None,
        success: bool = True,
        error_message: str = "",
        latency_ms: float = 0.0,
        sandbox_mode: str | None = None,
        metadata: dict | None = None,
    ) -> uuid.UUID:
        """记录一次工具调用，返回 tool_call_id (DB 记录 ID)"""
        call = AgentToolCall(
            trace_id=trace_id,
            step_number=step_number,
            sequence=sequence,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=_json_dumps(arguments) if arguments else None,
            result=_str_truncate(str(result), 5000) if result else None,
            result_full=_str_truncate(str(result), 50000) if result else None,
            success=success,
            error_message=error_message[:500] if error_message else None,
            latency_ms=latency_ms,
            sandbox_mode=sandbox_mode,
            extra_metadata=_json_dumps(metadata) if metadata else None,
            completed_at=_utc_now() if success is not None else None,
        )
        with self._session_factory() as session:
            session.add(call)
            session.commit()
            session.refresh(call)
            return call.id

    def log_file_change(
        self,
        tool_call_id: uuid.UUID,
        trace_id: uuid.UUID,
        file_path: str,
        change_type: str = FileChangeType.MODIFY,
        content_before: str | None = None,
        content_after: str | None = None,
        diff: str | None = None,
        language: str | None = None,
        file_size_before: int | None = None,
        file_size_after: int | None = None,
        metadata: dict | None = None,
    ) -> uuid.UUID:
        """记录一次文件变更"""
        change = AgentFileChange(
            tool_call_id=tool_call_id,
            trace_id=trace_id,
            file_path=file_path,
            change_type=change_type,
            content_before=_str_truncate(content_before, 50000) if content_before else None,
            content_after=_str_truncate(content_after, 50000) if content_after else None,
            diff=_str_truncate(diff, 100000) if diff else None,
            language=language,
            file_size_before=file_size_before,
            file_size_after=file_size_after,
            extra_metadata=_json_dumps(metadata) if metadata else None,
        )
        with self._session_factory() as session:
            session.add(change)
            session.commit()
            session.refresh(change)
            return change.id

    def log_exec(
        self,
        message: str,
        level: str = "INFO",
        trace_id: uuid.UUID | None = None,
        tool_call_id: uuid.UUID | None = None,
        step_number: int | None = None,
        stage: str | None = None,
        agent_id: str | None = None,
        context: dict | None = None,
        metadata: dict | None = None,
    ) -> uuid.UUID:
        """记录一条执行日志"""
        entry = AgentExecLog(
            trace_id=trace_id,
            tool_call_id=tool_call_id,
            level=level,
            message=message[:2000],
            step_number=step_number,
            stage=stage,
            agent_id=agent_id,
            exec_context=_json_dumps(context) if context else None,
            extra_metadata=_json_dumps(metadata) if metadata else None,
        )
        with self._session_factory() as session:
            session.add(entry)
            session.commit()
            session.refresh(entry)
            return entry.id

    def finish_trace(
        self,
        trace_id: uuid.UUID,
        status: str = TraceStatus.COMPLETED,
        final_answer: str = "",
        total_steps: int = 0,
        total_tool_calls: int = 0,
        total_tokens: int = 0,
        total_latency_ms: float = 0.0,
        final_model: str = "",
        final_provider: str = "",
        error_message: str = "",
        cancelled: bool = False,
    ) -> None:
        """完成一条 AgentTrace"""
        self.update_trace_status(
            trace_id=trace_id,
            status=status,
            final_answer=final_answer[:10000],
            total_steps=total_steps,
            total_tool_calls=total_tool_calls,
            total_tokens=total_tokens,
            total_latency_ms=total_latency_ms,
            final_model=final_model,
            final_provider=final_provider,
            error_message=error_message[:1000] if error_message else None,
            cancelled=cancelled,
        )
