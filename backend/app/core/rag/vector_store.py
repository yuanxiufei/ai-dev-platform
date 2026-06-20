"""
向量存储层 — FAISS 稠密索引 + SQLite FTS5 稀疏索引

借鉴 AstrBot FaissVecDB：
- 每个知识库独立 FAISS 索引 (IndexFlatL2)
- SQLite 存储文档元数据 + FTS5 全文索引
- 支持增删查 + 持久化
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("app.core.rag.vector_store")

# ── 文档元数据存储 (SQLite + FTS5) ────────────────────────


class DocumentStore:
    """文档元数据 SQLite 存储 + FTS5 全文索引"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # FTS5 全文索引
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                    USING fts5(content, doc_id, tokenize='unicode61')
                """)
            except Exception as e:
                logger.warning("FTS5 creation failed: %s", e)
            conn.commit()
            conn.close()

    def insert(self, doc_id: str, content: str, metadata: dict = None):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR REPLACE INTO documents (doc_id, content, metadata) VALUES (?, ?, ?)",
                (doc_id, content, json.dumps(metadata or {})),
            )
            # FTS5 索引
            try:
                conn.execute(
                    "INSERT OR REPLACE INTO documents_fts (rowid, content, doc_id) "
                    "VALUES ((SELECT id FROM documents WHERE doc_id=?), ?, ?)",
                    (doc_id, content, doc_id),
                )
            except Exception:
                pass
            conn.commit()
            conn.close()

    def delete(self, doc_id: str):
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
            # 删除 FTS5 索引
            try:
                conn.execute(
                    "DELETE FROM documents_fts WHERE doc_id=?", (doc_id,)
                )
            except Exception:
                pass
            conn.commit()
            conn.close()

    def get(self, doc_id: str) -> Optional[dict]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT doc_id, content, metadata FROM documents WHERE doc_id=?",
                (doc_id,),
            ).fetchone()
            conn.close()
            if row:
                return {"doc_id": row[0], "content": row[1],
                         "metadata": json.loads(row[2])}
            return None

    def get_all_ids(self) -> list[str]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            rows = conn.execute("SELECT doc_id FROM documents").fetchall()
            conn.close()
            return [r[0] for r in rows]

    def ft_search(self, query: str, limit: int = 20) -> list[dict]:
        """FTS5 全文搜索"""
        with self._lock:
            try:
                conn = sqlite3.connect(self._db_path)
                # 构建 FTS5 查询（分词 + OR）
                tokens = self._tokenize(query)
                if not tokens:
                    conn.close()
                    return []
                fts_query = " OR ".join(tokens)

                rows = conn.execute(
                    "SELECT d.doc_id, d.content, d.metadata, rank "
                    "FROM documents_fts f "
                    "JOIN documents d ON f.doc_id = d.doc_id "
                    "WHERE documents_fts MATCH ? "
                    "ORDER BY rank LIMIT ?",
                    (fts_query, limit),
                ).fetchall()
                conn.close()

                # bm25(doc) = -rank — 转换为 0-1 分数
                results = []
                ranks = [abs(r[3]) for r in rows if r[3] is not None]
                max_rank = max(ranks) if ranks else 1
                for r in rows:
                    score = (1.0 - (abs(r[3]) / (max_rank + 1e-6))) if r[3] else 0.5
                    results.append({
                        "doc_id": r[0],
                        "content": r[1],
                        "metadata": json.loads(r[2]),
                        "score": max(0.0, min(1.0, score)),
                    })
                return results
            except Exception as e:
                logger.warning("FTS5 search failed: %s", e)
                conn.close()
                return []

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中文分词 + 去停用词"""
        try:
            import jieba
            stopwords = {"的", "了", "在", "是", "我", "有", "和", "就",
                         "不", "人", "都", "一", "一个", "上", "也", "很",
                         "到", "说", "要", "去", "你", "会", "着", "没有",
                         "看", "好", "自己", "这"}
            words = jieba.lcut(text)
            return [w for w in words if len(w) > 1 and w not in stopwords][:20]
        except ImportError:
            # 无 jieba 时用简单空格分割
            return text.lower().split()[:20]


# ── FAISS 向量存储 ────────────────────────────────────────


class VectorStore:
    """FAISS 向量索引 + 文档元数据"""

    def __init__(self, index_path: str, dim: int):
        self._index_path = index_path
        self._dim = dim
        self._index = None
        self._id_to_doc_id: dict[int, str] = {}
        self._next_id = 0
        self._load_or_create()

    def _load_or_create(self):
        """加载已有索引或创建新索引"""
        try:
            import faiss
            if os.path.exists(self._index_path):
                self._index = faiss.read_index(self._index_path)
                self._next_id = self._index.ntotal
                logger.info("Loaded FAISS index: %d vectors", self._next_id)
            else:
                # IndexFlatL2：精确 L2 距离
                index = faiss.IndexFlatL2(self._dim)
                self._index = faiss.IndexIDMap(index)
                logger.info("Created new FAISS index (dim=%d)", self._dim)
        except ImportError:
            raise ImportError("faiss-cpu not installed. Run: pip install faiss-cpu")

    def add(self, embeddings: list[list[float]], doc_ids: list[str]):
        """添加向量"""
        import faiss
        if not embeddings:
            return

        vecs = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vecs)  # L2 归一化

        indices = list(range(self._next_id, self._next_id + len(embeddings)))
        self._index.add_with_ids(vecs, np.array(indices, dtype=np.int64))

        for idx, did in zip(indices, doc_ids):
            self._id_to_doc_id[idx] = did

        self._next_id += len(embeddings)
        self._save()

    def remove(self, doc_id: str):
        """移除向量（FAISS 不支持直接删除，需重建）"""
        # 标记删除
        idx_to_remove = [
            i for i, d in self._id_to_doc_id.items() if d == doc_id
        ]
        for i in idx_to_remove:
            del self._id_to_doc_id[i]
        self._save()

    def search(self, query_vec: list[float], k: int = 20) -> list[dict]:
        """搜索 top-k 相似向量"""
        import faiss
        vec = np.array([query_vec], dtype=np.float32)
        faiss.normalize_L2(vec)

        distances, indices = self._index.search(vec, k)

        results: list[dict] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx not in self._id_to_doc_id:
                continue
            # L2 距离转相似度
            similarity = float(1.0 / (1.0 + dist))
            results.append({
                "doc_id": self._id_to_doc_id[idx],
                "score": similarity,
                "distance": float(dist),
            })

        return results

    def count(self) -> int:
        return self._index.ntotal if self._index else 0

    def _save(self):
        import faiss
        faiss.write_index(self._index, self._index_path)


# ── 合并存储（FAISS + DocumentStore）───────────────────────


class HybridStorage:
    """组合向量索引 + 文档元数据 + FTS5"""

    def __init__(self, kb_path: str, dim: int):
        os.makedirs(kb_path, exist_ok=True)
        self._doc_store = DocumentStore(os.path.join(kb_path, "docs.db"))
        self._vec_store = VectorStore(os.path.join(kb_path, "index.faiss"), dim)
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def add_chunks(self, chunks: list[dict], embeddings: list[list[float]]):
        """批量添加 chunks + 向量"""
        doc_ids = []
        for ch in chunks:
            doc_id = f"{ch['metadata'].get('chunk_index', '')}_{abs(hash(ch['text']))}"
            ch["metadata"]["_doc_id"] = doc_id
            self._doc_store.insert(doc_id, ch["text"], ch["metadata"])
            doc_ids.append(doc_id)

        self._vec_store.add(embeddings, doc_ids)

    def remove_by_doc_id(self, doc_id: str):
        self._doc_store.delete(doc_id)
        self._vec_store.remove(doc_id)

    def get_text(self, doc_id: str) -> Optional[str]:
        doc = self._doc_store.get(doc_id)
        return doc["content"] if doc else None

    def dense_search(self, query_vec: list[float], k: int = 20) -> list[dict]:
        """稠密向量检索"""
        results = self._vec_store.search(query_vec, k)
        # 填充文档内容
        for r in results:
            doc = self._doc_store.get(r["doc_id"])
            if doc:
                r["content"] = doc["content"]
                r["metadata"] = doc["metadata"]
        return results

    def sparse_search(self, query: str, limit: int = 20) -> list[dict]:
        """稀疏关键词检索"""
        return self._doc_store.ft_search(query, limit)

    def count(self) -> int:
        return self._vec_store.count()

    def clear(self):
        """清空索引"""
        for doc_id in self._doc_store.get_all_ids():
            self.remove_by_doc_id(doc_id)
