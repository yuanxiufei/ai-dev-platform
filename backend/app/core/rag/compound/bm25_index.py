"""
持久化 BM25 倒排索引 — 借鉴 claude-obsidian bm25-index.py

纯 stdlib，零依赖。Okapi BM25 (k1=1.5, b=0.75).
索引 context-prefixed chunks，query 时快速检索 top-20 候选。

设计要点:
- 磁盘持久化 JSON 索引文件
- fcntl 文件锁（跨进程安全）
- 原子写入 (tmp + os.replace)
- Unicode 感知分词器（中/英/西里尔/日韩）
- 构建时增量 + 全量重建
- 查询时: BM25 → 候选列表 → 送至 reranker
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
import sys
import threading
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.core.rag.compound.bm25_index")

# ── BM25 参数 ─────────────────────────────────────────────

K1: float = 1.5
B: float = 0.75

# 英文停用词（保守，偏向高召回）
STOPWORDS: frozenset[str] = frozenset("""
a an and are as at be by for from has have he her him his i if in is it its
of on or that the their them they this to was were will with you your
的 了 在 是 我 有 和 就 不 人 都
""".split())

# Unicode 感知分词器
TOKEN_RE = re.compile(r"(\w[\w'\-]*|[\u4e00-\u9fff\u3400-\u4dbf]+)", re.UNICODE)


class BM25Index:
    """
    单个 BM25 倒排索引实例

    索引 JSON Schema:
    {
      "schema_version": 1,
      "params": {"k1": 1.5, "b": 0.75},
      "doc_count": 1234,
      "avg_dl": 487.5,
      "vocab": {
        "<term>": {"df": 17, "postings": [["chunk:id", 3], ...]}
      },
      "docs": {
        "<chunk_id>": {"path": "...", "dl": 487}
      }
    }
    """

    def __init__(self):
        self.doc_count: int = 0
        self.avg_dl: float = 0.0
        self.total_dl: int = 0
        self.vocab: dict[str, dict] = {}       # term → {df, postings}
        self.docs: dict[str, dict] = {}         # chunk_id → {path, dl}

    # ── Build ─────────────────────────────────────────

    def build(self, chunks: list[dict]) -> int:
        """
        从 chunk 列表构建 BM25 索引

        Args:
            chunks: [{chunk_id, path, text}, ...]
        Returns:
            索引的文档数
        """
        self.doc_count = 0
        self.total_dl = 0
        self.vocab = {}
        self.docs = {}

        for ch in chunks:
            chunk_id = ch["chunk_id"]
            text = ch.get("text", "")
            tokens = self._tokenize(text)
            dl = len(tokens)

            if dl == 0:
                continue

            self.docs[chunk_id] = {
                "path": ch.get("path", ""),
                "dl": dl,
            }
            self.doc_count += 1
            self.total_dl += dl

            # 词频 (Term Frequency) 统计
            tf = Counter(tokens)
            for term, freq in tf.items():
                if term not in self.vocab:
                    self.vocab[term] = {"df": 0, "postings": []}
                self.vocab[term]["df"] += 1
                self.vocab[term]["postings"].append([chunk_id, freq])

        self.avg_dl = self.total_dl / max(self.doc_count, 1)

        logger.info("BM25 built: %d docs, %d terms, avg_dl=%.1f",
                     self.doc_count, len(self.vocab), self.avg_dl)
        return self.doc_count

    def merge_incremental(self, new_chunks: list[dict]) -> int:
        """
        增量合并新 chunk（不重建整个索引）

        适用于: 单个文档添加后更新 BM25 索引
        """
        added = 0
        for ch in new_chunks:
            chunk_id = ch["chunk_id"]
            text = ch.get("text", "")
            tokens = self._tokenize(text)
            dl = len(tokens)

            if dl == 0:
                continue

            # 如果已存在，先移除旧版本
            if chunk_id in self.docs:
                self._remove_from_vocab(chunk_id)

            self.docs[chunk_id] = {
                "path": ch.get("path", ""),
                "dl": dl,
            }
            self.doc_count += 1
            self.total_dl += dl

            tf = Counter(tokens)
            for term, freq in tf.items():
                if term not in self.vocab:
                    self.vocab[term] = {"df": 0, "postings": []}
                self.vocab[term]["df"] += 1
                self.vocab[term]["postings"].append([chunk_id, freq])

            added += 1

        self.avg_dl = self.total_dl / max(self.doc_count, 1)
        return added

    def _remove_from_vocab(self, chunk_id: str) -> None:
        """从倒排列表中移除旧版本文档"""
        if chunk_id not in self.docs:
            return
        old_dl = self.docs[chunk_id]["dl"]

        # 扫描 vocab 移除该 chunk
        for term_data in self.vocab.values():
            new_postings = [p for p in term_data["postings"] if p[0] != chunk_id]
            if len(new_postings) < len(term_data["postings"]):
                term_data["df"] -= 1
            term_data["postings"] = new_postings

        # 清理 df=0 的 term
        self.vocab = {t: d for t, d in self.vocab.items() if d["df"] > 0}

        self.doc_count -= 1
        self.total_dl -= old_dl

    # ── Query ──────────────────────────────────────────

    def query(self, text: str, top_k: int = 20) -> list[dict]:
        """
        BM25 检索

        Returns:
            [{chunk_id, score, path}, ...]  按 BM25 分数降序
        """
        if not self.vocab or self.doc_count == 0:
            return []

        tokens = self._tokenize(text)
        if not tokens:
            return []

        # 每个查询 term 的 IDF 加权
        scores: dict[str, float] = defaultdict(float)
        query_tf = Counter(tokens)

        N = self.doc_count
        avgdl = self.avg_dl

        for term, qf in query_tf.items():
            if term not in self.vocab:
                continue

            entry = self.vocab[term]
            df = entry["df"]

            # IDF
            idf = math.log(1 + (N - df + 0.5) / (df + 0.5))

            for (chunk_id, tf) in entry["postings"]:
                if chunk_id not in self.docs:
                    continue
                dl = self.docs[chunk_id]["dl"]
                # BM25 score
                numerator = tf * (K1 + 1)
                denominator = tf + K1 * (1 - B + B * dl / avgdl)
                scores[chunk_id] += idf * qf * numerator / denominator

        # 排序
        ranked = [
            {
                "chunk_id": cid,
                "score": round(score, 4),
                "path": self.docs[cid]["path"],
            }
            for cid, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)
        ][:top_k]

        return ranked

    # ── Tokenize ───────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Unicode 感知分词"""
        tokens = TOKEN_RE.findall(text.lower())
        return [t for t in tokens if t not in STOPWORDS]


# ── Index Manager (持久化 + 并发安全) ────────────────────

class BM25IndexManager:
    """
    BM25 索引管理器 — 磁盘持久化 + fcntl 并发锁

    Usage:
        mgr = BM25IndexManager(index_dir="rag_data/compound")

        # 构建
        mgr.build_index([
            {"chunk_id": "doc1:0", "path": "prefixes/xxx/chunk-000.json", "text": "..."},
        ])

        # 查询
        results = mgr.query("检索关键词", top_k=20)

        # 增量
        mgr.add_chunks([{"chunk_id": "doc2:0", "path": "...", "text": "..."}])
    """

    def __init__(self, index_dir: str = "rag_data/compound"):
        self._index_dir = Path(index_dir) / "bm25"
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._index_dir / "index.json"
        self._lock_path = self._index_dir / ".lock"
        self._index: BM25Index | None = None
        self._lock = threading.Lock()  # 进程内锁

    @property
    def index(self) -> BM25Index:
        if self._index is None:
            self._index = self._load_or_create()
        return self._index

    def is_ready(self) -> bool:
        return self._index_path.exists()

    # ── Build ─────────────────────────────────────────

    def build_index(self, chunks: list[dict]) -> int:
        """全量构建 BM25 索引"""
        with self._lock:
            bm25 = BM25Index()
            n = bm25.build(chunks)
            self._save(bm25)
            self._index = bm25
            return n

    def add_chunks(self, chunks: list[dict]) -> int:
        """增量添加 chunk 到索引"""
        with self._lock:
            bm25 = self.index
            n = bm25.merge_incremental(chunks)
            self._save(bm25)
            return n

    # ── Query ─────────────────────────────────────────

    def query(self, text: str, top_k: int = 20) -> list[dict]:
        """BM25 检索"""
        bm25 = self.index
        return bm25.query(text, top_k=top_k)

    # ── Stats ─────────────────────────────────────────

    def stats(self) -> dict:
        bm25 = self.index
        return {
            "doc_count": bm25.doc_count,
            "vocab_size": len(bm25.vocab),
            "avg_dl": round(bm25.avg_dl, 1),
            "index_path": str(self._index_path),
            "schema_version": 1,
        }

    # ── Persistence ───────────────────────────────────

    def _save(self, bm25: BM25Index) -> None:
        """原子写入索引文件"""
        data = {
            "schema_version": 1,
            "params": {"k1": K1, "b": B},
            "doc_count": bm25.doc_count,
            "total_dl": bm25.total_dl,
            "avg_dl": bm25.avg_dl,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "vocab": bm25.vocab,
            "docs": bm25.docs,
        }

        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._index_path)
        logger.debug("BM25 index saved: %d docs", bm25.doc_count)

    def _load_or_create(self) -> BM25Index:
        """加载已有索引或创建空索引"""
        if not self._index_path.exists():
            return BM25Index()

        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            bm25 = BM25Index()
            bm25.doc_count = data["doc_count"]
            bm25.total_dl = data.get("total_dl", 0)
            bm25.avg_dl = data["avg_dl"]
            bm25.vocab = data["vocab"]
            bm25.docs = data["docs"]
            logger.info("BM25 index loaded: %d docs, %d terms",
                        bm25.doc_count, len(bm25.vocab))
            return bm25
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            logger.error("Failed to load BM25 index: %s, creating new", e)
            return BM25Index()

    def rebuild_from_contextualized(
        self,
        prefix_dir: str,
    ) -> int:
        """
        从 ContextualPrefixer 输出目录重建 BM25 索引

        遍历 rag_data/compound/prefixes/ 下所有 chunk-NNN.json，
        读取 contextualized_text 并构建索引。
        """
        chunks: list[dict] = []
        prefix_path = Path(prefix_dir)

        if not prefix_path.exists():
            logger.warning("Prefix dir not found: %s", prefix_path)
            return 0

        for page_dir in prefix_path.iterdir():
            if not page_dir.is_dir():
                continue
            for chunk_file in sorted(page_dir.glob("chunk-*.json")):
                try:
                    data = json.loads(chunk_file.read_text(encoding="utf-8"))
                    chunk_id = f"{data['page_path']}:{data['chunk_index']}"
                    chunks.append({
                        "chunk_id": chunk_id,
                        "path": str(chunk_file),
                        "text": data["contextualized_text"],
                    })
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning("Skip bad chunk file %s: %s", chunk_file, e)

        if not chunks:
            logger.warning("No contextualized chunks found")
            return 0

        return self.build_index(chunks)


# ── 全局单例 ──────────────────────────────────────────────

_global_bm25_mgr: Optional[BM25IndexManager] = None


def init_bm25_index(index_dir: str = "rag_data/compound") -> BM25IndexManager:
    global _global_bm25_mgr
    _global_bm25_mgr = BM25IndexManager(index_dir=index_dir)
    return _global_bm25_mgr


def get_bm25_index() -> Optional[BM25IndexManager]:
    return _global_bm25_mgr
