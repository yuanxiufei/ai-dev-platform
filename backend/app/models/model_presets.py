"""
Model Preset 数据模型 — 借鉴 Open WebUI Model Presets

ModelPreset — 将 system_prompt + tools + knowledge_bases + 参数打包为可复用预设
ArenaComparison — 多模型并排对比记录（借鉴 Open WebUI Arena）
ArenaVote — ELO 投票记录
ModelUsageLog — 模型调用日志（用于 Analytics 看板）
MemoryEntry — 长期向量化记忆
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Text, Float
from sqlmodel import Column, Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ── ModelPreset ──────────────────────────────────────────

class ModelPreset(SQLModel, table=True):
    """借鉴 Open WebUI 的 Model Preset 功能
    将 system_prompt、工具、知识库、参数等打包为可复用的预设配置。
    """
    __tablename__ = "model_presets"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, description="预设名称")
    description: str | None = Field(default=None, max_length=2000)

    # 核心配置
    model_name: str | None = Field(default=None, max_length=100, description="绑定的模型名")
    system_prompt: str | None = Field(default=None, sa_column=Column("system_prompt", Text))
    
    # 参数
    temperature: float | None = Field(default=None, description="温度，null 表示使用默认")
    max_tokens: int | None = Field(default=None)
    top_p: float | None = Field(default=None)

    # 工具绑定（借鉴 Open WebUI 的强制工具绑定）
    tools: list[str] | None = Field(default=None, sa_column=Column("tools", Text), description="绑定的工具名称列表(JSON)")
    force_tools: bool = Field(default=False, description="是否强制绑定工具")

    # 知识库关联
    knowledge_bases: list[str] | None = Field(default=None, sa_column=Column("knowledge_bases", Text), description="关联的知识库 ID 列表(JSON)")

    # 动态变量（借鉴 Open WebUI: {{ USER_NAME }}, {{ CURRENT_DATE }}）
    variables: dict | None = Field(default=None, sa_column=Column("variables", Text), description="动态变量映射(JSON)")

    # 访问控制
    is_public: bool = Field(default=False, description="是否公开")
    owner_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    usage_count: int = Field(default=0, description="使用次数")

    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── Arena (模型竞技场) ──────────────────────────────────

class ArenaComparison(SQLModel, table=True):
    """借鉴 Open WebUI Arena — 多模型并排对比记录"""
    __tablename__ = "arena_comparisons"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    prompt: str = Field(sa_column=Column("prompt", Text), description="用户输入提示")
    
    model_a: str = Field(max_length=100)
    response_a: str = Field(sa_column=Column("response_a", Text))
    latency_a_ms: float | None = Field(default=None)
    tokens_a: int | None = Field(default=None)

    model_b: str = Field(max_length=100)
    response_b: str = Field(sa_column=Column("response_b", Text))
    latency_b_ms: float | None = Field(default=None)
    tokens_b: int | None = Field(default=None)

    winner: str | None = Field(default=None, max_length=10, description="投票胜者: A / B / tie")
    voter_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    category: str | None = Field(default=None, max_length=50, description="评测分类: code / chat / vision")

    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


class ArenaVote(SQLModel, table=True):
    """ELO 投票记录"""
    __tablename__ = "arena_votes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    comparison_id: uuid.UUID = Field(foreign_key="arena_comparisons.id", nullable=False, ondelete="CASCADE")
    
    model_won: str = Field(max_length=100)
    model_lost: str = Field(max_length=100)
    elo_before_winner: float = Field(default=1500.0)
    elo_before_loser: float = Field(default=1500.0)
    elo_after_winner: float = Field(default=1500.0)
    elo_after_loser: float = Field(default=1500.0)

    voter_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


class ModelEloRanking(SQLModel, table=True):
    """模型 ELO 排行榜"""
    __tablename__ = "model_elo_rankings"

    model_name: str = Field(max_length=100, primary_key=True)
    elo: float = Field(default=1500.0)
    wins: int = Field(default=0)
    losses: int = Field(default=0)
    ties: int = Field(default=0)
    total_comparisons: int = Field(default=0)
    category: str | None = Field(default=None, max_length=50)

    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))


# ── 模型分析 ────────────────────────────────────────────

class ModelUsageLog(SQLModel, table=True):
    """借鉴 Open WebUI Analytics Dashboard — 模型调用日志"""
    __tablename__ = "model_usage_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    model_name: str = Field(max_length=100, index=True)
    provider: str = Field(max_length=50, index=True)
    capability: str = Field(max_length=50, index=True, description="CODE_GENERATION / TEXT_GENERATION / VISION / VIDEO")

    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)

    latency_ms: float = Field(default=0.0, sa_type=Float, description="响应延迟（毫秒）")
    success: bool = Field(default=True)
    error_message: str | None = Field(default=None, max_length=500)

    # 成本估算（USD, 按各 provider 公开定价计算）
    estimated_cost_usd: float = Field(default=0.0, sa_type=Float, description="估算成本（美元）")

    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True)
    session_id: uuid.UUID | None = Field(default=None, nullable=True)

    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True), index=True)


# ── 长期记忆 ────────────────────────────────────────────

class MemoryEntry(SQLModel, table=True):
    """借鉴 Open WebUI Memory + Obsidian Frontmatter — 向量化长期记忆

    把 key+value 嵌入到 embedding 向量中，
    后续通过语义相似度检索相关记忆注入到 prompt。

    Frontmatter 字段（借鉴 Obsidian Properties）:
    - frontmatter_tags: 标签列表（JSON）
    - frontmatter_aliases: 别名列表（JSON）
    - frontmatter_status: 状态（draft/in-progress/completed/archived）
    - frontmatter_priority: 优先级（low/medium/high/critical）
    - frontmatter_due_date: 截止日期
    - linked_from: 反向链接（JSON 数组）
    """
    __tablename__ = "memory_entries"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    key: str = Field(max_length=500, description="记忆键（简短摘要）")
    value: str = Field(sa_column=Column("value", Text), description="记忆内容（完整事实，支持 Obsidian 风格 Wikilinks + Callouts + Frontmatter）")

    # 向量存为 JSON 文本（跨数据库兼容）；生产环境建议用 pgvector
    embedding: str | None = Field(default=None, sa_column=Column("embedding", Text), description="embedding 向量 JSON")

    # 维度与模型
    embedding_dim: int = Field(default=768)
    embedding_model: str = Field(default="BAAI/bge-base-en-v1.5", max_length=100)

    # 域与权限
    domain: str = Field(default="general", max_length=50, description="记忆域: personal / project / code / general")
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")

    # 元数据
    importance: float = Field(default=0.5, sa_type=Float, description="记忆重要性 0-1")
    access_count: int = Field(default=0, description="被检索次数")
    last_accessed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    # ── Frontmatter 属性（借鉴 Obsidian Properties）───
    frontmatter_tags: str | None = Field(default=None, sa_column=Column("frontmatter_tags", Text), description="标签列表 JSON")
    frontmatter_aliases: str | None = Field(default=None, sa_column=Column("frontmatter_aliases", Text), description="别名列表 JSON")
    frontmatter_status: str | None = Field(default=None, max_length=50, description="状态: draft / in-progress / completed / archived")
    frontmatter_priority: str | None = Field(default=None, max_length=20, description="优先级: low / medium / high / critical")
    frontmatter_due_date: str | None = Field(default=None, max_length=30, description="截止日期")
    frontmatter_extra: str | None = Field(default=None, sa_column=Column("frontmatter_extra", Text), description="其他 frontmatter 属性 JSON")

    # ── 链接索引（服务端维护）───
    forward_links: str | None = Field(default=None, sa_column=Column("forward_links", Text), description="正向链接目标列表 JSON")
    linked_from: str | None = Field(default=None, sa_column=Column("linked_from", Text), description="反向链接来源列表 JSON")

    created_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(default_factory=_utc_now, sa_type=DateTime(timezone=True))
