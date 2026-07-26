"""
向量存储层 — FAISS 稠密索引 + PostgreSQL tsvector 全文索引

借鉴 AstrBot FaissVecDB：
- 每个知识库独立 FAISS 索引 (IndexFlatIP，内积=余弦相似度)
- PostgreSQL 存储文档元数据 + tsvector 全文索引
- 支持增删查 + 持久化
- 文件命名与 VectorSegment 统一: faiss.index + faiss.idmap.json
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import psycopg

logger = logging.getLogger("app.core.rag.vector_store")

# ── 文档元数据存储 (PostgreSQL + tsvector) ────────────────────────

_DOCSTORE_DDL_EXECUTED: set[str] = set()  # 模块级 DDL 去重


class DocumentStore:
    """文档元数据 PostgreSQL 存储 + tsvector 全文索引"""

    def __init__(self, pg_dsn: str):
        self._pg_dsn = pg_dsn
        self._lock = threading.Lock()
        self._fts_available = True
        self._init_db()

    def _get_conn(self):
        conn = psycopg.connect(self._pg_dsn, autocommit=False)
        return conn

    def _init_db(self):
        global _DOCSTORE_DDL_EXECUTED
        if self._pg_dsn in _DOCSTORE_DDL_EXECUTED:
            return
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id SERIAL PRIMARY KEY,
                        doc_id TEXT UNIQUE NOT NULL,
                        content TEXT NOT NULL,
                        search_text TEXT,
                        tsv tsvector GENERATED ALWAYS AS (
                            to_tsvector('simple', COALESCE(search_text, ''))
                        ) STORED,
                        metadata JSONB DEFAULT '{}',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_doc_id ON documents(doc_id)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_tsv ON documents USING GIN(tsv)"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_documents_metadata "
                    "ON documents USING GIN(metadata)"
                )
                conn.commit()
                _DOCSTORE_DDL_EXECUTED.add(self._pg_dsn)
                logger.info("DocumentStore DDL ensured (PG: %s...)", self._pg_dsn[:50])
            except Exception as e:
                logger.warning("DocumentStore DDL failed: %s", e)
                self._fts_available = False
            finally:
                conn.close()

    @classmethod
    def _tokenize_for_tsv(cls, text: str) -> str:
        """分词后用空格连接，供 PostgreSQL to_tsvector('simple', ...) 使用"""
        tokens = cls._tokenize(text)
        return " ".join(tokens)

    def insert(self, doc_id: str, content: str, metadata: dict = None):
        search_text = DocumentStore._tokenize_for_tsv(content)
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute(
                    "INSERT INTO documents (doc_id, content, search_text, metadata) "
                    "VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (doc_id) DO UPDATE SET "
                    "content = EXCLUDED.content, "
                    "search_text = EXCLUDED.search_text, "
                    "metadata = EXCLUDED.metadata",
                    (doc_id, content, search_text, json.dumps(metadata or {})),
                )
                conn.commit()
            except Exception as e:
                logger.warning("DocumentStore.insert failed for %s: %s", doc_id, e)
                try:
                    conn.rollback()
                except Exception:
                    pass
            finally:
                conn.close()

    def delete(self, doc_id: str):
        with self._lock:
            conn = self._get_conn()
            try:
                conn.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
                conn.commit()
            finally:
                conn.close()

    def get(self, doc_id: str) -> Optional[dict]:
        with self._lock:
            conn = self._get_conn()
            try:
                row = conn.execute(
                    "SELECT doc_id, content, metadata FROM documents WHERE doc_id = %s",
                    (doc_id,),
                ).fetchone()
            finally:
                conn.close()
        if row:
            meta = row[2]
            if isinstance(meta, str):
                meta = json.loads(meta)
            return {"doc_id": row[0], "content": row[1], "metadata": meta}
        return None

    def get_all_ids(self) -> list[str]:
        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute("SELECT doc_id FROM documents").fetchall()
                return [r[0] for r in rows]
            finally:
                conn.close()

    def list_chunks_paginated(
        self, doc_filter_id: str = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[list[dict], int]:
        """分页列表 + 总数（按 KBDocument.doc_id 过滤 metadata）"""
        with self._lock:
            conn = self._get_conn()
            try:
                if doc_filter_id:
                    where = "WHERE metadata->>'_doc_id' = %s"
                    params: list = [doc_filter_id]
                else:
                    where = ""
                    params = []
                total = conn.execute(
                    f"SELECT COUNT(*) FROM documents {where}", params
                ).fetchone()[0]
                rows = conn.execute(
                    f"SELECT doc_id, content, metadata FROM documents {where} "
                    f"ORDER BY id LIMIT %s OFFSET %s",
                    params + [limit, skip],
                ).fetchall()
            finally:
                conn.close()

        chunks = [
            {
                "doc_id": r[0],
                "content": r[1],
                "metadata": r[2] if isinstance(r[2], dict) else json.loads(str(r[2])),
            }
            for r in rows
        ]
        return chunks, total

    def delete_chunk(self, doc_id: str) -> bool:
        """删除单个 chunk"""
        with self._lock:
            conn = self._get_conn()
            try:
                existing = conn.execute(
                    "SELECT 1 FROM documents WHERE doc_id = %s", (doc_id,)
                ).fetchone()
                if not existing:
                    return False
                conn.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
                conn.commit()
                return True
            finally:
                conn.close()

    def ft_search(
        self, query: str, limit: int = 20, filter_dict: dict | None = None,
    ) -> list[dict]:
        """tsvector 全文搜索，支持 WhereFilter 元数据过滤"""
        if not self._fts_available:
            return self._fallback_like_search(query, limit, filter_dict)

        tokens = self._tokenize(query)
        if not tokens:
            return []

        # 构建 tsquery：token1 | token2 | token3 (OR 语义)
        escaped = [t.replace("'", "''").replace("\\", "\\\\") for t in tokens]
        ts_query_str = " | ".join(escaped)

        where_sql, where_params = self._build_filter_clause(filter_dict)

        sql = (
            "SELECT d.doc_id, d.content, d.metadata, "
            "ts_rank(d.tsv, to_tsquery('simple', %s)) AS rank "
            "FROM documents d "
            "WHERE d.tsv @@ to_tsquery('simple', %s)"
        )
        params: list = [ts_query_str, ts_query_str]

        if where_sql:
            sql += f" AND {where_sql}"
            params.extend(where_params)

        sql += " ORDER BY rank DESC LIMIT %s"
        params.append(limit)

        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(sql, params).fetchall()
            except Exception as e:
                logger.warning("tsquery search failed: %s, fallback to LIKE", e)
                conn.close()
                return self._fallback_like_search(query, limit, filter_dict)
            finally:
                conn.close()

        results = []
        ranks = [r[3] for r in rows if r[3] is not None]
        max_rank = max(ranks) if ranks else 1

        for r in rows:
            score = r[3] / (max_rank + 1e-6) if r[3] and max_rank > 0 else 0.5
            meta = r[2]
            if isinstance(meta, str):
                meta = json.loads(meta)
            results.append({
                "doc_id": r[0],
                "content": r[1],
                "metadata": meta if meta else {},
                "score": round(score, 4),
            })
        return results

    def _fallback_like_search(
        self, query: str, limit: int = 20, filter_dict: dict | None = None,
    ) -> list[dict]:
        """ILIKE 降级搜索"""
        where_sql, where_params = self._build_filter_clause(filter_dict)
        pattern = f"%{query}%"
        params: list = [pattern]
        if where_sql:
            params.extend(where_params)

        sql = "SELECT doc_id, content, metadata FROM documents WHERE content ILIKE %s"
        if where_sql:
            sql += f" AND {where_sql}"
        sql += " LIMIT %s"
        params.append(limit)

        with self._lock:
            conn = self._get_conn()
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()

        return [
            {
                "doc_id": r[0],
                "content": r[1],
                "metadata": r[2] if isinstance(r[2], dict) else (json.loads(str(r[2])) if r[2] else {}),
                "score": 0.3,
            }
            for r in rows
        ]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中文分词 + 去停用词"""
        try:
            import jieba
            stopwords = {
                "的", "了", "在", "是", "我", "有", "和", "就",
                "不", "人", "都", "一", "一个", "上", "也", "很",
                "到", "说", "要", "去", "你", "会", "着", "没有",
                "看", "好", "自己", "这",
            }
            words = jieba.lcut(text)
            return [w for w in words if len(w) > 1 and w not in stopwords][:20]
        except ImportError:
            return text.lower().split()[:20]

    @staticmethod
    def _build_filter_clause(filter_dict: dict | None) -> tuple[str, list]:
        """将 WhereFilter DSL 转为 SQL WHERE 片段（不含 WHERE 关键字）"""
        if not filter_dict:
            return "", []
        from app.core.rag.filters import WhereFilter
        full_where, params = WhereFilter.to_sql(filter_dict)
        if not full_where:
            return "", []
        return full_where[6:], params


# ── FAISS 向量存储 ────────────────────────────────────────


class VectorStore:
    """FAISS 向量索引 (IndexFlatIP) + ID 映射持久化

    与 VectorSegment 统一使用 faiss.index + faiss.idmap.json 文件命名。
    IndexFlatIP 配合 L2 归一化等效于余弦相似度，不再需 L2→相似度转换。
    """

    INDEX_FILE = "faiss.index"
    IDMAP_FILE = "faiss.idmap.json"

    def __init__(self, store_dir: str, dim: int):
        self._store_dir = store_dir
        self._index_path = os.path.join(store_dir, self.INDEX_FILE)
        self._idmap_path = os.path.join(store_dir, self.IDMAP_FILE)
        self._dim = dim
        self._index = None
        self._id_to_doc_id: dict[int, str] = {}
        self._next_id = 0
        self._load_or_create()

    def _load_or_create(self):
        """加载已有索引或创建新索引，同时恢复 ID 映射"""
        try:
            import faiss

            # 兼容旧文件名 index.faiss → 迁移至 faiss.index
            _old_path = os.path.join(self._store_dir, "index.faiss")
            if os.path.exists(_old_path) and not os.path.exists(self._index_path):
                os.rename(_old_path, self._index_path)
                logger.warning("Migrated old index.faiss → faiss.index (old index may use L2 metric, "
                               "re-indexing recommended for IP compatibility)")

            if os.path.exists(self._index_path):
                self._index = faiss.read_index(self._index_path)
                self._next_id = self._index.ntotal
                # 恢复 ID 映射
                if os.path.exists(self._idmap_path):
                    with open(self._idmap_path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                        self._id_to_doc_id = {int(k): v for k, v in raw.items()}
                logger.info("Loaded FAISS index: %d vectors, %d id mappings",
                            self._next_id, len(self._id_to_doc_id))
            else:
                # IndexFlatIP：内积（配合 L2 归一化 = 余弦相似度）
                index = faiss.IndexFlatIP(self._dim)
                self._index = faiss.IndexIDMap(index)
                logger.info("Created new FAISS index (IndexFlatIP, dim=%d)", self._dim)
        except ImportError:
            raise ImportError("faiss-cpu not installed. Run: pip install faiss-cpu")

    def add(self, embeddings: list[list[float]], doc_ids: list[str]):
        """添加向量"""
        import faiss
        if not embeddings:
            return

        vecs = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vecs)  # L2 归一化 → 内积 = 余弦相似度

        indices = list(range(self._next_id, self._next_id + len(embeddings)))
        self._index.add_with_ids(vecs, np.array(indices, dtype=np.int64))

        for idx, did in zip(indices, doc_ids):
            self._id_to_doc_id[idx] = did

        self._next_id += len(embeddings)
        self._save()

    def remove(self, doc_id: str):
        """移除向量（FAISS 不支持直接删除，标记并持久化）"""
        idx_to_remove = [
            i for i, d in self._id_to_doc_id.items() if d == doc_id
        ]
        for i in idx_to_remove:
            del self._id_to_doc_id[i]
        self._save()

    def search(self, query_vec: list[float], k: int = 20) -> list[dict]:
        """搜索 top-k 相似向量（IP 内积 = 余弦相似度，分数直接使用）"""
        import faiss
        vec = np.array([query_vec], dtype=np.float32)
        faiss.normalize_L2(vec)

        scores, indices = self._index.search(vec, k)

        results: list[dict] = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx not in self._id_to_doc_id:
                continue
            # IndexFlatIP: 归一化后分数即为余弦相似度 [0, 1]
            similarity = max(0.0, min(1.0, float(score)))
            results.append({
                "doc_id": self._id_to_doc_id[idx],
                "score": similarity,
            })

        return results

    def count(self) -> int:
        return self._index.ntotal if self._index else 0

    @property
    def ghost_count(self) -> int:
        """FAISS 索引中存在但已从 ID 映射中删除的幽灵向量数量

        FAISS IndexIDMap 不支持单向量物理删除，remove() 仅清理映射。
        这些向量仍参与全表扫描，影响检索性能。
        """
        ntotal = self._index.ntotal if self._index else 0
        return ntotal - len(self._id_to_doc_id)

    @property
    def ghost_ratio(self) -> float:
        """幽灵向量占比（0~1），>0.2 建议执行 compact/rebuild"""
        ntotal = self._index.ntotal if self._index else 0
        if ntotal == 0:
            return 0.0
        return self.ghost_count / ntotal

    def is_dirty(self, threshold: float = 0.2) -> bool:
        """是否需要重建索引"""
        return self.ghost_ratio > threshold

    def rebuild_index(self, embedder, doc_store: "DocumentStore") -> int:
        """重建 FAISS 索引：只保留 ID 映射中的有效向量

        步骤：
        1. 从 DocumentStore 取出所有仍在 id_map 中的文本
        2. 重新嵌入
        3. 用新 vectors 创建全新的 FAISS 索引
        4. 替换旧索引并持久化

        Args:
            embedder: 嵌入器实例（需有 embed_batch(texts) -> list[list[float]] 方法）
            doc_store: DocumentStore 实例（获取剩余 chunk 文本）

        Returns:
            int: 重建后的向量数量
        """
        import faiss

        valid_ids = list(self._id_to_doc_id.values())
        if not valid_ids:
            # 空映射 → 创建全新空索引
            index = faiss.IndexFlatIP(self._dim)
            self._index = faiss.IndexIDMap(index)
            self._next_id = 0
            self._save()
            logger.info("Rebuilt FAISS index: empty (all chunks deleted)")
            return 0

        # 从 DocumentStore 拉取所有有效文本（分批避免 OOM）
        batch_size = 256
        all_texts = []
        all_doc_ids = []
        for i in range(0, len(valid_ids), batch_size):
            batch_ids = valid_ids[i : i + batch_size]
            for did in batch_ids:
                doc = doc_store.get(did)
                if doc and doc.get("content"):
                    all_texts.append(doc["content"])
                    all_doc_ids.append(did)

        if not all_texts:
            index = faiss.IndexFlatIP(self._dim)
            self._index = faiss.IndexIDMap(index)
            self._next_id = 0
            self._save()
            logger.warning("Rebuilt FAISS index: all valid IDs missing from doc_store")
            return 0

        # 重新嵌入
        embeddings = embedder.embed_batch(all_texts)

        # 创建全新索引
        index = faiss.IndexFlatIP(self._dim)
        self._index = faiss.IndexIDMap(index)
        self._id_to_doc_id.clear()
        self._next_id = 0

        vecs = np.array(embeddings, dtype=np.float32)
        faiss.normalize_L2(vecs)

        indices = list(range(len(all_doc_ids)))
        self._index.add_with_ids(vecs, np.array(indices, dtype=np.int64))
        for idx, did in enumerate(all_doc_ids):
            self._id_to_doc_id[idx] = did
        self._next_id = len(all_doc_ids)

        self._save()
        logger.info(
            "Rebuilt FAISS index: %d vectors (cleaned %d ghost vectors, ratio was %.1f%%)",
            len(all_doc_ids), self.ghost_count, self.ghost_ratio * 100,
        )
        return len(all_doc_ids)

    def _save(self):
        """持久化 FAISS 索引 + ID 映射"""
        import faiss
        faiss.write_index(self._index, self._index_path)
        # 持久化 ID 映射（与 VectorSegment 的 faiss.idmap.json 一致）
        with open(self._idmap_path, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in self._id_to_doc_id.items()}, f)


# ── 合并存储（FAISS + DocumentStore）───────────────────────


class HybridStorage:
    """组合向量索引 + 文档元数据 + PostgreSQL tsvector"""

    def __init__(self, kb_path: str, dim: int, pg_dsn: str):
        os.makedirs(kb_path, exist_ok=True)
        self._doc_store = DocumentStore(pg_dsn)
        self._vec_store = VectorStore(kb_path, dim)
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

    def dense_search(self, query_vec: list[float], k: int = 20, filter_dict: dict | None = None) -> list[dict]:
        """稠密向量检索（支持 WhereFilter 后过滤）"""
        results = self._vec_store.search(query_vec, k)
        # 填充文档内容
        for r in results:
            doc = self._doc_store.get(r["doc_id"])
            if doc:
                r["content"] = doc["content"]
                r["metadata"] = doc["metadata"]
        # 后过滤：向量检索拿 k 条，再用 WhereFilter 筛选
        if filter_dict:
            from app.core.rag.filters import WhereFilter
            results = [r for r in results if WhereFilter.match(filter_dict, r.get("metadata", {}))]
        return results

    def sparse_search(self, query: str, limit: int = 20, filter_dict: dict | None = None) -> list[dict]:
        """稀疏关键词检索（支持 WhereFilter）"""
        return self._doc_store.ft_search(query, limit, filter_dict=filter_dict)

    def count(self) -> int:
        return self._vec_store.count()

    def list_chunks(
        self, doc_filter_id: str = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[list[dict], int]:
        """分页列出 chunk（按 KBDocument.doc_id 过滤）"""
        return self._doc_store.list_chunks_paginated(
            doc_filter_id=doc_filter_id, skip=skip, limit=limit,
        )

    def delete_chunk(self, doc_id: str) -> bool:
        """删除单个 chunk（同步清理文档存储 + FAISS 向量）"""
        # FAISS 不支持直接删除，标记并从 ID 映射移除
        self._vec_store.remove(doc_id)
        return self._doc_store.delete_chunk(doc_id)

    def clear(self):
        """清空索引"""
        for doc_id in self._doc_store.get_all_ids():
            self.remove_by_doc_id(doc_id)

    @property
    def ghost_ratio(self) -> float:
        """幽灵向量占比（FAISS 索引中存在但已从 ID 映射移除的向量比例）"""
        return self._vec_store.ghost_ratio

    @property
    def ghost_count(self) -> int:
        """幽灵向量数量"""
        return self._vec_store.ghost_count

    def ghost_stats(self) -> dict:
        """返回 FAISS 索引健康状态"""
        return {
            "index_total": self._vec_store.count(),
            "alive_in_map": self._vec_store.count() - self._vec_store.ghost_count,
            "ghost_count": self._vec_store.ghost_count,
            "ghost_ratio": round(self._vec_store.ghost_ratio, 4),
            "needs_compact": self._vec_store.is_dirty(threshold=0.2),
        }

    def compact(self, embedder) -> int:
        """压缩 FAISS 索引：重新嵌入所有有效 chunk 并重建索引

        删除幽灵向量，恢复检索性能。大规模删除后建议调用。
        如需保留原有向量避免重新嵌入，直接在 kb_manager 层操作。

        Args:
            embedder: 嵌入器实例（需有 embed_batch 方法）

        Returns:
            int: 重建后的有效向量数
        """
        return self._vec_store.rebuild_index(embedder, self._doc_store)
