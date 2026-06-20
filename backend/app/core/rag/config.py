"""
RAG 全局配置
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RAGConfig:
    """RAG 系统配置"""

    # ── 路径 ──
    data_dir: str = field(default_factory=lambda: os.getenv("RAG_DATA_DIR", "rag_data"))
    kb_dir: str = ""  # 将在 __post_init__ 中设置

    # ── Embedding ──
    embedding_provider: str = "local"  # local | openai | ollama | bailian
    embedding_model: str = "BAAI/bge-large-zh-v1.5"  # 本地模型名
    embedding_dim: int = 1024
    embedding_device: str = "cpu"  # cpu | cuda

    # openai-compatible 配置
    embedding_api_base: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_api_model: str = "text-embedding-3-small"

    # ── 分块 ──
    chunk_size: int = 1024
    chunk_overlap: int = 200
    chunk_strategy: str = "recursive"  # recursive | markdown | code | fixed

    # ── 检索 ──
    dense_top_k: int = 20       # 稠密检索候选数
    sparse_top_k: int = 20      # 稀疏检索候选数
    fusion_top_k: int = 10      # RRF 融合后取 top-k
    final_top_k: int = 5        # Rerank 后最终返回数

    # RRF 参数
    rrf_k: int = 60             # RRF 平滑常数

    # ── Rerank ──
    rerank_enabled: bool = True
    rerank_provider: str = "local"  # local | openai | bailian | none
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_device: str = "cpu"
    rerank_top_k: int = 5

    # ── 检索混合权重 ──
    dense_weight: float = 0.6
    sparse_weight: float = 0.4

    # ── 性能 ──
    embed_batch_size: int = 32
    embed_max_concurrency: int = 4
    embed_max_retries: int = 3

    # ── Compound Vault (借鉴 claude-obsidian) ──
    compound_dir: str = "rag_data/compound"
    compound_enabled: bool = True

    # Contextual prefix
    contextual_prefix_enabled: bool = True
    contextual_prefix_tier: str = "synthetic"  # api | local | synthetic
    contextual_prefix_allow_egress: bool = False

    # Persistent BM25
    bm25_persistent_enabled: bool = True

    # Embedding cache
    embed_cache_enabled: bool = True
    embed_cache_max_mem: int = 5000

    # Hot cache (session continuity)
    hot_cache_enabled: bool = True

    # ── Text Filter Chain (借鉴 obsidian-clipper filters/) ──
    text_filter_enabled: bool = True
    text_filter_names: list[str] = field(default_factory=lambda: [
        "remove_boilerplate", "normalize_ws", "deduplicate_lines",
    ])
    text_filter_sanitize_level: str = "normal"  # normal | strict | minimal

    # ── HTML Sanitizer (借鉴 obsidian-clipper DOMPurify) ──
    html_sanitizer_enabled: bool = True
    html_sanitizer_level: str = "normal"  # normal | strict | minimal

    # ── LLM 生成 ──
    llm_provider: str = "local"  # local | openai | ollama
    llm_model: str = "Qwen/Qwen2.5-7B-Instruct-GGUF"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 2048

    def __post_init__(self):
        if not self.kb_dir:
            self.kb_dir = os.path.join(self.data_dir, "knowledge_bases")
        os.makedirs(self.kb_dir, exist_ok=True)

        # 加载环境变量
        if not self.embedding_api_key:
            self.embedding_api_key = os.getenv("OPENAI_API_KEY", "")


# 全局单例
_global_config: Optional[RAGConfig] = None


def get_rag_config() -> RAGConfig:
    """获取 RAG 全局配置单例"""
    global _global_config
    if _global_config is None:
        _global_config = RAGConfig()
    return _global_config
