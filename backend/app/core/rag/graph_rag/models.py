"""
GraphRAG 数据模型

借鉴 SAG types.ts + DB schema:
  - GraphEvent: 事件 (chunk 粒度的事件摘要)
  - GraphEntity: 实体 (跨文档归一化)
  - EventEntityLink: 事件-实体关联
  - SearchTrace: 搜索全链路追踪
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── 图数据模型 ──────────────────────────────────────────────

@dataclass
class GraphEvent:
    """事件记录 —— chunk 粒度的事件化表达"""
    id: str
    source_id: str          # 对应 KB ID
    document_id: Optional[str] = None
    chunk_id: Optional[str] = None
    title: str = ""
    summary: str = ""
    content: str = ""
    rank: int = 0
    score: Optional[float] = None
    entity_ids: list[str] = field(default_factory=list)


@dataclass
class GraphEntity:
    """实体记录 —— 跨文档归一化的命名实体"""
    id: str
    source_id: str
    type: str               # 实体类型: person, org, concept, technology, etc.
    name: str
    normalized_name: str = ""
    description: Optional[str] = None
    score: Optional[float] = None
    event_count: int = 0    # 关联事件数


@dataclass
class EventEntityLink:
    """事件-实体关联边"""
    event_id: str
    entity_id: str
    weight: float = 1.0


# ── 搜索追踪模型 ────────────────────────────────────────────

@dataclass
class SearchTraceStep:
    """单步追踪记录"""
    key: str                    # 步骤标识: step1ExtractEntities, step2RetrieveEntities, ...
    title: str                  # 人类可读标题
    detail: str                 # 描述信息
    status: str = "done"        # running | done | failed
    duration_ms: float = 0.0
    payload: Optional[object] = None  # 中间结果（可序列化）


@dataclass
class SearchTraceEvent:
    """追踪中的事件摘要"""
    id: str
    title: str
    summary: str = ""
    content_preview: str = ""
    score: Optional[float] = None


@dataclass
class SearchTrace:
    """完整搜索追踪"""
    trace_id: str
    query: str
    search_mode: str = "standard"
    query_entities: list[str] = field(default_factory=list)
    recalled_entities: list[dict] = field(default_factory=list)
    entity_event_ids: list[str] = field(default_factory=list)
    query_event_ids: list[str] = field(default_factory=list)
    expanded_event_ids: list[str] = field(default_factory=list)
    coarse_ranked_event_ids: list[str] = field(default_factory=list)
    reranked_event_ids: list[str] = field(default_factory=list)
    event_snapshots: list[SearchTraceEvent] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    fallback_reason: str = ""
    steps: list[SearchTraceStep] = field(default_factory=list)


# ── 搜索结果模型 ────────────────────────────────────────────

@dataclass
class SearchSection:
    """搜索结果切片"""
    chunk_id: str
    source_id: str
    content: str
    heading: Optional[str] = None
    document_id: Optional[str] = None
    rank: int = 0
    score: float = 0.0
    event_id: Optional[str] = None


@dataclass
class SearchResult:
    """完整搜索结果"""
    trace_id: str
    sections: list[SearchSection] = field(default_factory=list)
    trace: Optional[SearchTrace] = None


@dataclass
class MultiHopOptions:
    """多跳检索参数 (对应 SAG search.ts MultiOptions)"""
    sub_strategy: str = "multi"               # multi | hopllm
    entity_top_k: int = 20
    multi_top_k: int = 20
    key_similarity_threshold: float = 0.9
    similarity_threshold: float = 0.4
    max_hops: int = 1
    max_events: int = 100
    max_events_a: int = 100
    max_events_b: int = 0
    max_hop_retries: int = 3
    rerank_top_k: int = 10
    max_sections: int = 10
