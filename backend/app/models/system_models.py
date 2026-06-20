"""
System 域扩展模型 — Rules / Integrations / AgentConfig

Rule           — AI 行为规则（编码规范、安全检查等）
Integration    — 第三方服务集成配置（Supabase / CloudBase 等）
AgentConfig    — Agent 配置（模型 + System Prompt + 工具 + 模式）
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Text
from sqlmodel import Column, Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── Rule ──────────────────────────────────────────────────

class Rule(SQLModel, table=True):
    """AI 行为规则：控制代码生成、安全审查、编码规范等"""
    __tablename__ = "rules"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, description="规则名称")
    description: str | None = Field(default=None, max_length=2000, sa_column=Column("description", Text))
    rule_type: str = Field(default="always", max_length=20, description="alway s|requested|manual")
    scope: str = Field(default="project", max_length=20, description="project|user")
    content: str = Field(sa_column=Column("content", Text), description="规则内容 Markdown")
    enabled: bool = Field(default=True)

    triggers: list[str] | None = Field(default=None, sa_column=Column("triggers", Text), description="触发文件 glob 列表(JSON)")
    priority: float = Field(default=0.0, description="优先级，越高越先匹配")

    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── Integration ───────────────────────────────────────────

class Integration(SQLModel, table=True):
    """第三方服务集成配置：存储连接凭据和状态"""
    __tablename__ = "integrations"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=100, description="集成服务唯一标识 (supabase/tcb/cloudStudio...)")
    display_name: str = Field(max_length=255, description="显示名称")
    description: str | None = Field(default=None, max_length=2000, sa_column=Column("description", Text))
    category: str = Field(max_length=50, description="database|deploy|storage|service")

    # 连接配置 (JSON 加密存储)
    config: dict | None = Field(default=None, sa_column=Column("config", Text), description="连接配置 JSON")

    connected: bool = Field(default=False)
    last_connected_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    status: str = Field(default="disconnected", max_length=20, description="connected|disconnected|connecting|error")
    error_message: str | None = Field(default=None, sa_column=Column("error_message", Text))

    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── AgentConfig ───────────────────────────────────────────

class AgentConfig(SQLModel, table=True):
    """Agent 完整配置：模式 + 模型 + System Prompt + 工具 + 作用域"""
    __tablename__ = "agent_configs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, description="Agent 名称")
    description: str | None = Field(default=None, max_length=2000, sa_column=Column("description", Text))
    mode: str = Field(default="craft", max_length=20, description="craft|ask|plan")
    agentic_mode: str = Field(default="agentic", max_length=20, description="agentic|manual — Agent 自主运行模式")
    model: str = Field(default="auto", max_length=100, description="绑定模型名")
    system_prompt: str | None = Field(default=None, sa_column=Column("system_prompt", Text))

    tools: list[str] | None = Field(default=None, sa_column=Column("tools", Text), description="工具 ID 列表(JSON)")
    tool_categories: list[str] | None = Field(default=None, sa_column=Column("tool_categories", Text), description="启用的工具分类(JSON)")
    mcp_servers: list[str] | None = Field(default=None, sa_column=Column("mcp_servers", Text), description="启用的 MCP 服务器(JSON)")

    auto_run: bool = Field(default=True, description="是否自动运行")
    enabled: bool = Field(default=True)
    sort_order: int = Field(default=0)
    scope: str = Field(default="user", max_length=20, description="user|project — 作用域")
    project_id: uuid.UUID | None = Field(default=None, nullable=True)

    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
