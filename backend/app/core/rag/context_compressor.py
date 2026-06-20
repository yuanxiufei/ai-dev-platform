"""
上下文压缩器 — 检索结果裁剪 + 去重 + Token 感知截断

借鉴 AstrBot 的上下文窗口管理：
1. Token 计数（tiktoken 优先 → 字符估算回退）
2. 得分加权截断（高分文档保留更多内容）
3. 语义去重（高重叠 chunk 合并）
4. 多种压缩策略：truncate | head | hybrid
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger("app.core.rag.compress")


# ── Token 计数器 ────────────────────────────────────────────


class TokenCounter:
    """
    Token 计数器 — tiktoken 优先，字符估算回退

    借鉴 AstrBot 的 token 计数策略：
    - 有 tiktoken → 精确计数
    - 无 tiktoken → 字符数 / 4（中英文混合估算）
    """

    def __init__(self, encoding_name: str = "cl100k_base"):
        self._encoding = None
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding(encoding_name)
            logger.debug("TokenCounter: using tiktoken (%s)", encoding_name)
        except ImportError:
            logger.debug("TokenCounter: tiktoken not found, using char/4 estimation")

    def count(self, text: str) -> int:
        """计数文本 token 数"""
        if self._encoding:
            return len(self._encoding.encode(text))
        # 回退：中英文混合约 4 字符/token
        return max(1, len(text) // 4)


# ── 压缩策略 ────────────────────────────────────────────────


class CompressStrategy(str, Enum):
    """压缩策略"""
    TRUNCATE = "truncate"          # 按得分权重截断每个文档
    HEAD = "head"                  # 仅保留每个文档的前 N token
    HYBRID = "hybrid"              # 高分完整 + 低分截头


@dataclass
class CompressConfig:
    """压缩配置"""
    max_tokens: int = 3000               # 上下文最大 token 数
    strategy: CompressStrategy = CompressStrategy.TRUNCATE
    min_chunk_tokens: int = 30           # 单 chunk 最少保留 token 数
    dedup_threshold: float = 0.85        # 去重相似度阈值 (Jaccard)
    preserve_high_score_ratio: float = 0.6  # hybrid 策略: 前 N% 的高分文档完整保留


# ── 压缩器 ──────────────────────────────────────────────────


class ContextCompressor:
    """
    上下文压缩器

    输入：检索结果列表 (含 score/content)
    输出：裁剪后的结果列表 + 最终上下文字符串

    流程：
      1. 去重（移除高文本重叠的 chunk）
      2. Token 统计（若未超限则直接返回）
      3. 按策略压缩（截断 / 保留头部 / hybrid）
      4. 重新格式化为上下文字符串
    """

    def __init__(self, config: Optional[CompressConfig] = None):
        self._config = config or CompressConfig()
        self._tokenizer = TokenCounter()

    def compress(self, results: list[dict]) -> tuple[list[dict], str]:
        """
        压缩检索结果

        Returns:
            (compressed_results, formatted_context)
        """
        if not results:
            return [], ""

        logger.debug(
            "Compressing %d results (max_tokens=%d, strategy=%s)",
            len(results), self._config.max_tokens, self._config.strategy.value,
        )

        # ── 1. 去重 ──
        deduped = self._deduplicate(results)
        removed = len(results) - len(deduped)
        if removed > 0:
            logger.debug("Dedup removed %d near-duplicate chunks", removed)

        # ── 2. Token 统计 ──
        full_context = self._format(deduped)
        total_tokens = self._tokenizer.count(full_context)

        if total_tokens <= self._config.max_tokens:
            logger.debug("Context fits in %d tokens (limit=%d), no compression needed",
                         total_tokens, self._config.max_tokens)
            return deduped, full_context

        # ── 3. 压缩 ──
        logger.info("Context too long: %d > %d tokens, compressing...",
                      total_tokens, self._config.max_tokens)

        if self._config.strategy == CompressStrategy.HEAD:
            compressed = self._compress_head(deduped)
        elif self._config.strategy == CompressStrategy.HYBRID:
            compressed = self._compress_hybrid(deduped)
        else:
            compressed = self._compress_truncate(deduped)

        return compressed, self._format(compressed)

    def estimate_tokens(self, results: list[dict]) -> int:
        """估算结果集的总 token 数（不修改结果）"""
        return self._tokenizer.count(self._format(results))

    # ── 内部方法 ─────────────────────────────────────────

    def _deduplicate(self, results: list[dict]) -> list[dict]:
        """Jaccard 相似度去重"""
        if len(results) <= 1:
            return results

        kept: list[dict] = []
        threshold = self._config.dedup_threshold

        for doc in results:
            content = doc.get("content", "")
            is_dup = False

            for existing in kept:
                sim = self._jaccard_similarity(content, existing.get("content", ""))
                if sim >= threshold:
                    is_dup = True
                    break

            if not is_dup:
                kept.append(doc)

        return kept

    def _compress_truncate(self, results: list[dict]) -> list[dict]:
        """
        按得分权重截断：高分文档保留更多内容

        算法：
          1. 计算每个文档的得分权重 (score_i / sum(scores))
          2. 按权重分配 token 预算
          3. 每个文档截断到分配的 token 数
        """
        scores = [r.get("score", r.get("rerank_score", r.get("rrf_score", 0.1)))
                  for r in results]
        total_score = sum(scores) or 1.0
        weights = [s / total_score for s in scores]

        # 扣除元数据开销（约 10%）
        usable_tokens = int(self._config.max_tokens * 0.9)

        compressed = []
        for i, doc in enumerate(results):
            budget = max(
                self._config.min_chunk_tokens,
                int(usable_tokens * weights[i]),
            )
            truncated = self._truncate_to_tokens(doc.get("content", ""), budget)
            compressed.append({
                **doc,
                "content": truncated,
                "original_length": len(doc.get("content", "")),
            })

        return compressed

    def _compress_head(self, results: list[dict]) -> list[dict]:
        """
        仅保留每个文档前 N token
        """
        usable = int(self._config.max_tokens * 0.9)
        per_doc = max(
            self._config.min_chunk_tokens,
            usable // max(1, len(results)),
        )

        return [
            {
                **doc,
                "content": self._truncate_to_tokens(doc.get("content", ""), per_doc),
                "original_length": len(doc.get("content", "")),
            }
            for doc in results
        ]

    def _compress_hybrid(self, results: list[dict]) -> list[dict]:
        """
        高分文档完整保留 + 低分文档截头

        借鉴 AstrBot：高相关度 chunk 优先保证完整性，
        低相关度 chunk 仅作为补充参考（截断到头部）。
        """
        if len(results) <= 1:
            return self._compress_truncate(results)

        # 按得分排序（高分在前）
        sorted_results = sorted(
            results,
            key=lambda r: r.get("score", r.get("rerank_score", r.get("rrf_score", 0))),
            reverse=True,
        )

        split_idx = max(1, int(len(sorted_results) * self._config.preserve_high_score_ratio))

        high_score_docs = sorted_results[:split_idx]
        low_score_docs = sorted_results[split_idx:]

        # 高分文档：完整保留
        # 低分文档：仅保留头部
        used_tokens = self._tokenizer.count(self._format(high_score_docs))
        remaining = max(
            self._config.min_chunk_tokens * len(low_score_docs),
            self._config.max_tokens - used_tokens - 200,  # 减去元数据开销
        )

        if remaining > 0 and low_score_docs:
            per_doc = max(self._config.min_chunk_tokens, remaining // len(low_score_docs))
            for doc in low_score_docs:
                doc["content"] = self._truncate_to_tokens(doc.get("content", ""), per_doc)

        return sorted_results

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """将文本截断到指定 token 数"""
        if self._tokenizer.count(text) <= max_tokens:
            return text

        # 二分查找截断点
        low, high = 0, len(text)
        while low < high:
            mid = (low + high + 1) // 2
            if self._tokenizer.count(text[:mid]) <= max_tokens:
                low = mid
            else:
                high = mid - 1

        return text[:low].rstrip() + "…"

    @staticmethod
    def _jaccard_similarity(text_a: str, text_b: str) -> float:
        """Jaccard 相似度（基于三字词 token 集合）"""
        def trigrams(s: str) -> set[str]:
            s = s.lower().replace("\n", " ")
            return {s[i:i + 3] for i in range(len(s) - 2)}

        set_a = trigrams(text_a)
        set_b = trigrams(text_b)

        if not set_a or not set_b:
            return 0.0

        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _format(results: list[dict]) -> str:
        """格式化结果集为字符串（用于 token 估算）"""
        parts = []
        for i, r in enumerate(results, 1):
            score = r.get("score", r.get("rerank_score", r.get("rrf_score", 0)))
            content = r.get("content", "").strip()
            meta = r.get("metadata", {})
            source = meta.get("source", meta.get("title", "未知"))
            parts.append(f"【知识 {i}】来源: {source} | 相关度: {score:.3f}\n{content}")
        return "\n\n---\n\n".join(parts)


# ── 全局单例 ────────────────────────────────────────────────

_global_compressor: Optional[ContextCompressor] = None


def init_compressor(config: Optional[CompressConfig] = None) -> ContextCompressor:
    """初始化全局压缩器"""
    global _global_compressor
    _global_compressor = ContextCompressor(config)
    logger.info("ContextCompressor initialized (strategy=%s, max_tokens=%d)",
                 _global_compressor._config.strategy.value,
                 _global_compressor._config.max_tokens)
    return _global_compressor


def get_compressor() -> ContextCompressor:
    """获取全局压缩器（延迟初始化）"""
    global _global_compressor
    if _global_compressor is None:
        return init_compressor()
    return _global_compressor
