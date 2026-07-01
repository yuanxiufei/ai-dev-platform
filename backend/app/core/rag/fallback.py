"""
降级机制 — 借鉴 SAG 的优雅降级策略

SAG 降级场景:
  1. 无 API key → 本地 embedding + BM25
  2. 无 seed events → 回退纯向量搜索
  3. Rerank 失败 → 跳过 Rerank，用粗排结果
  4. LLM 超时 → 降级到 fast 模式
  5. Embedding 失败 → 仅 BM25

增强:
  - FallbackChain: 链式降级策略
  - 自动降级日志
  - 降级后的结果质量标记
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger("app.core.rag.fallback")


class FallbackReason(str, Enum):
    """降级原因"""
    NO_API_KEY = "no_api_key"
    NO_SEED_EVENTS = "no_seed_events"
    EMBED_FAILED = "embed_failed"
    LLM_TIMEOUT = "llm_timeout"
    RERANK_FAILED = "rerank_failed"
    VECTOR_STORE_UNAVAILABLE = "vector_store_unavailable"
    GRAPH_NOT_BUILT = "graph_not_built"
    ZERO_RESULTS = "zero_results"


@dataclass
class FallbackResult:
    """降级执行结果"""
    success: bool = False
    reason: FallbackReason = FallbackReason.ZERO_RESULTS
    degraded: bool = False  # 是否降级了
    original_method: str = ""
    actual_method: str = ""
    result: Any = None
    error: Optional[str] = None
    latency_ms: float = 0


class FallbackChain:
    """
    链式降级执行器

    依次尝试策略链，直到某个策略成功。

    用法:
        chain = FallbackChain()
        chain.add("graph_rag", graph_search_fn, FallbackReason.NO_SEED_EVENTS)
        chain.add("vector", vector_search_fn, FallbackReason.VECTOR_STORE_UNAVAILABLE)
        chain.add("bm25", bm25_search_fn, FallbackReason.ZERO_RESULTS)

        result = await chain.execute(query="优化数据库", kb_ids=["kb_1"])
    """

    def __init__(self, default_error_reason: FallbackReason = FallbackReason.ZERO_RESULTS):
        self._strategies: list[tuple[str, Callable, FallbackReason]] = []
        self._default_reason = default_error_reason

    def add(self, name: str, fn: Callable, fallback_reason: FallbackReason):
        """添加一个策略到降级链"""
        self._strategies.append((name, fn, fallback_reason))

    async def execute(self, **kwargs) -> FallbackResult:
        """按顺序执行策略，成功即返回"""
        import time

        for i, (name, fn, reason) in enumerate(self._strategies):
            is_degraded = i > 0
            start = time.monotonic()

            try:
                r = fn(**kwargs)
                if asyncio.iscoroutine(r):
                    r = await r

                # 检查空结果
                if r is None:
                    logger.info("Fallback: %s returned None, trying next...", name)
                    continue
                if hasattr(r, "sections") and not r.sections:
                    logger.info("Fallback: %s returned empty sections, trying next...", name)
                    continue
                if isinstance(r, list) and not r:
                    continue

                elapsed = (time.monotonic() - start) * 1000
                logger.info(
                    "Fallback: %s succeeded%s (%.0fms)",
                    name, " (degraded)" if is_degraded else "", elapsed,
                )
                return FallbackResult(
                    success=True,
                    reason=reason if is_degraded else FallbackReason.ZERO_RESULTS,
                    degraded=is_degraded,
                    original_method=self._strategies[0][0] if self._strategies else "",
                    actual_method=name,
                    result=r,
                    latency_ms=elapsed,
                )

            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                logger.warning(
                    "Fallback: %s failed (%s), trying next... (%.0fms)",
                    name, str(e)[:100], elapsed,
                )

        # 全部失败
        return FallbackResult(
            success=False,
            reason=self._default_reason,
            degraded=True,
            original_method=self._strategies[0][0] if self._strategies else "",
            error="All strategies exhausted",
        )


# ── 预构建的降级函数工厂 ───────────────────────────────────

def make_embed_fallback(embed_api_fn, embed_local_fn=None):
    """
    创建 embedding 降级函数

    策略: API Embedding → 本地 Embedding → 零向量
    """

    async def _fallback(text: str) -> list[float]:
        # 1. 尝试 API
        if embed_api_fn:
            try:
                r = embed_api_fn(text)
                if asyncio.iscoroutine(r):
                    r = await r
                if r:
                    return r
            except Exception as e:
                logger.warning("Embed API fallback: %s", e)

        # 2. 尝试本地模型
        if embed_local_fn:
            try:
                r = embed_local_fn(text)
                if asyncio.iscoroutine(r):
                    r = await r
                if r:
                    return r
            except Exception as e:
                logger.warning("Embed local fallback: %s", e)

        # 3. 零向量回退
        logger.warning("Embedding: all strategies failed, using zero vector")
        return [0.0] * 1024

    return _fallback


def make_llm_fallback(openai_fn, local_fn=None, ollama_fn=None):
    """
    创建 LLM 调用降级函数

    策略: OpenAI → Ollama → 本地模型 → 默认响应
    """

    async def _fallback(prompt: str, default_response: Any = None) -> Any:
        for name, fn in [("openai", openai_fn), ("ollama", ollama_fn), ("local", local_fn)]:
            if not fn:
                continue
            try:
                r = fn(prompt)
                if asyncio.iscoroutine(r):
                    r = await r
                if r:
                    return r
            except Exception as e:
                logger.warning("LLM %s fallback: %s", name, e)

        logger.warning("LLM: all strategies failed, using default response")
        return default_response

    return _fallback


def make_rerank_fallback(model_fn, llm_fn=None):
    """
    创建 Rerank 降级函数

    策略: Rerank 模型 → LLM Rerank → 原始顺序
    """

    async def _fallback(query: str, candidates: list, top_k: int) -> list:
        # 1. Rerank 模型
        if model_fn:
            try:
                r = model_fn(query=query, candidates=candidates, top_k=top_k)
                if asyncio.iscoroutine(r):
                    r = await r
                if r:
                    return r
            except Exception as e:
                logger.warning("Rerank model fallback: %s", e)

        # 2. LLM Rerank
        if llm_fn:
            try:
                r = llm_fn(query=query, candidates=candidates, top_k=top_k)
                if asyncio.iscoroutine(r):
                    r = await r
                if r:
                    return r
            except Exception as e:
                logger.warning("LLM rerank fallback: %s", e)

        # 3. 原始顺序
        ids = [c.get("id", c.get("chunk_id", "")) for c in candidates[:top_k]]
        logger.info("Rerank: using original order (%d candidates → %d)", len(candidates), len(ids))
        return ids

    return _fallback


# ── 降级状态标记 ───────────────────────────────────────────

@dataclass
class DegradationState:
    """当前降级状态"""
    embed_api_available: bool = True
    llm_api_available: bool = True
    rerank_model_available: bool = True
    vector_store_available: bool = True
    graph_available: bool = False
    total_degradations: int = 0
    history: list[str] = field(default_factory=list)

    def record(self, reason: str):
        """记录一次降级"""
        self.total_degradations += 1
        self.history.append(reason)
        logger.info("Degradation #%d: %s", self.total_degradations, reason)

    @property
    def is_fully_degraded(self) -> bool:
        """是否已完全降级"""
        return (
            not self.embed_api_available
            and not self.llm_api_available
            and not self.vector_store_available
        )

    def summary(self) -> dict:
        return {
            "total_degradations": self.total_degradations,
            "embed_api_available": self.embed_api_available,
            "llm_api_available": self.llm_api_available,
            "rerank_model_available": self.rerank_model_available,
            "vector_store_available": self.vector_store_available,
            "graph_available": self.graph_available,
            "fully_degraded": self.is_fully_degraded,
        }


# 全局降级状态
_global_degradation = DegradationState()


def get_degradation_state() -> DegradationState:
    return _global_degradation
