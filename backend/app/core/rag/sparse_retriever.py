"""
稀疏检索器 — FTS5 优先 / BM25 内存回退

借鉴 AstrBot SparseRetriever:
- 优先使用 SQLite FTS5（内置 BM25 评分）
- FTS5 不可用时回退到 rank-bm25 内存计算
- jieba 中文分词 + 去停用词
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("app.core.rag.sparse_retriever")

# 中文停用词（常用高频词）
STOPWORDS = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就",
    "不", "人", "都", "一", "一个", "上", "也", "很",
    "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "他", "她", "它", "们",
    "那", "什么", "怎么", "为", "因为", "所以", "但是",
    "the", "a", "an", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does",
    "did", "will", "would", "could", "should", "may",
    "might", "can", "shall", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into",
    "through", "during", "before", "after", "above",
    "below", "between", "and", "but", "or", "nor", "not",
    "so", "yet", "both", "either", "neither", "each",
    "every", "all", "any", "few", "more", "most", "other",
    "some", "such", "no", "only", "own", "same", "than",
    "too", "very", "just", "about", "also", "if", "then",
})


def tokenize_text(text: str, max_tokens: int = 20) -> list[str]:
    """中文分词 + 去停用词"""
    try:
        import jieba
        words = jieba.lcut(text.lower())
    except ImportError:
        words = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", text.lower())

    return [
        w for w in words
        if len(w) > 1 and w not in STOPWORDS and not w.isspace()
    ][:max_tokens]


def build_fts5_query(query: str) -> Optional[str]:
    """构建 FTS5 OR 查询"""
    tokens = tokenize_text(query)
    if not tokens:
        return None
    # 转义特殊字符
    safe = [t.replace('"', '""') for t in tokens]
    return " OR ".join(f'"{t}"' for t in safe)


class BM25SparseRetriever:
    """BM25 内存检索器（FTS5 回退）"""

    def __init__(self):
        self._corpus: list[str] = []
        self._doc_ids: list[str] = []
        self._bm25 = None
        self._dirty = True

    def index(self, chunks: list[dict]):
        """建立索引"""
        self._corpus = [ch["text"] for ch in chunks]
        self._doc_ids = [ch["metadata"].get("_doc_id", "") for ch in chunks]
        self._dirty = True

    def _ensure_bm25(self):
        if not self._dirty or not self._corpus:
            return
        try:
            from rank_bm25 import BM25Okapi
            tokenized = [tokenize_text(doc) for doc in self._corpus]
            self._bm25 = BM25Okapi(tokenized)
            self._dirty = False
        except ImportError:
            logger.warning("rank-bm25 not installed. Purely keyword fallback.")
            self._bm25 = None

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """BM25 检索"""
        self._ensure_bm25()
        if not self._bm25 or not self._corpus:
            return self._keyword_fallback(query, top_k)

        tokens = tokenize_text(query)
        scores = self._bm25.get_scores(tokens)

        # 归一化
        max_s = max(scores.max(), 1e-6)
        scored = sorted(
            [(i, float(s / max_s)) for i, s in enumerate(scores) if s > 0],
            key=lambda x: x[1], reverse=True,
        )[:top_k]

        return [
            {"doc_id": self._doc_ids[i], "score": s,
             "content": self._corpus[i], "metadata": {}}
            for i, s in scored
        ]

    def _keyword_fallback(self, query: str, top_k: int) -> list[dict]:
        """纯关键词匹配回退"""
        tokens = set(tokenize_text(query))
        if not tokens:
            return []

        scored = []
        for i, doc in enumerate(self._corpus):
            doc_lower = doc.lower()
            score = sum(1 for t in tokens if t.lower() in doc_lower)
            if score > 0:
                scored.append((i, score / len(tokens)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            {"doc_id": self._doc_ids[i], "score": s,
             "content": self._corpus[i], "metadata": {}}
            for i, s in scored[:top_k]
        ]
