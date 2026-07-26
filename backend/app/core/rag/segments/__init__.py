"""
Segment 抽象层 — 借鉴 Chroma 可替换存储后端

设计理念:
  Segment ABC 定义统一 CRUD 接口，三个后端可独立替换:
  - MetadataSegment → PostgreSQL (元数据 + tsvector 全文)
  - VectorSegment   → FAISS (稠密向量索引)
  - RecordSegment   → BlockFile (原始文档记录)

  SegmentManager 编排多 Segment 协同工作，已统一替代 HybridStorage。

  Usage:
    mgr = SegmentManager(kb_path="/data/kb_abc123", dim=384)
    ids = mgr.add_chunks(chunks, embeddings)
    results = mgr.search(query_vec, query_str, k=10)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional


# ── Segment 基类 ────────────────────────────────────────────

class Segment(ABC):
    """存储后端抽象基类 — 借鉴 Chroma Segment ABC

    每个 Segment 对应一种存储类型（元数据/向量/记录），
    使用 scope 隔离不同知识库的数据。
    """

    def __init__(self, name: str, scope: str = "default"):
        self.name = name
        self.scope = scope

    @abstractmethod
    def add(self, ids: list[str], records: list[dict]) -> int:
        """批量添加记录，返回写入数"""
        ...

    @abstractmethod
    def get(self, ids: list[str]) -> dict[str, dict]:
        """批量查询，返回 {id: record}"""
        ...

    @abstractmethod
    def delete(self, ids: list[str]) -> int:
        """批量删除，返回删除数"""
        ...

    @abstractmethod
    def count(self) -> int:
        """记录总数"""
        ...

    @abstractmethod
    def clear(self):
        """清空所有数据"""
        ...

    @abstractmethod
    def close(self):
        """释放资源（文件句柄/索引等）"""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} scope={self.scope} count={self.count()}>"


# ── Segment 注册表 ─────────────────────────────────────────

_SEGMENT_REGISTRY: dict[str, type[Segment]] = {}


def register_segment(name: str, cls: type[Segment]):
    """注册自定义 Segment 类型"""
    _SEGMENT_REGISTRY[name] = cls


def get_segment_class(name: str) -> Optional[type[Segment]]:
    """获取注册的 Segment 类型"""
    return _SEGMENT_REGISTRY.get(name)


def list_segment_types() -> list[str]:
    """列出所有已注册的 Segment 类型"""
    return list(_SEGMENT_REGISTRY.keys())


# ── SegmentManager ──────────────────────────────────────────

class SegmentManager:
    """编排多个 Segment 协同工作，已统一替代 HybridStorage

    Usage:
        from app.core.rag.segments import SegmentManager
        from app.core.rag.segments.metadata_segment import MetadataSegment
        from app.core.rag.segments.vector_segment import VectorSegment
        from app.core.rag.segments.record_segment import RecordSegment

        mgr = SegmentManager(kb_path="/data/kb_abc", dim=384, pg_dsn="postgresql:///studio")
        mgr.register_metadata(MetadataSegment(pg_dsn="postgresql:///studio"))
        mgr.register_vector(VectorSegment(base_path="/data/kb_abc", dim=384))
        mgr.register_record(RecordSegment(base_path="/data/kb_abc"))
    """

    def __init__(self, kb_path: str, dim: int = 384, pg_dsn: str = ""):
        import os
        os.makedirs(kb_path, exist_ok=True)
        self.kb_path = kb_path
        self.dim = dim
        self._pg_dsn = pg_dsn  # psycopg DSN, MetadataSegment 同步 PG 访问

        self._metadata: Optional[Segment] = None
        self._vector: Optional[Segment] = None
        self._record: Optional[Segment] = None

    # ── Segment 注册 ───────────────────────────────────

    def register_metadata(self, segment: Segment):
        self._metadata = segment

    def register_vector(self, segment: Segment):
        self._vector = segment

    def register_record(self, segment: Segment):
        self._record = segment

    @property
    def metadata(self) -> Segment:
        if self._metadata is None:
            from app.core.rag.segments.metadata_segment import MetadataSegment
            self._metadata = MetadataSegment(pg_dsn=self._pg_dsn)
        return self._metadata

    @property
    def vector(self) -> Segment:
        if self._vector is None:
            from app.core.rag.segments.vector_segment import VectorSegment
            self._vector = VectorSegment(kb_path=self.kb_path, dim=self.dim)
        return self._vector

    @property
    def record(self) -> Segment:
        if self._record is None:
            from app.core.rag.segments.record_segment import RecordSegment
            self._record = RecordSegment(kb_path=self.kb_path)
        return self._record

    # ── 批量操作 ───────────────────────────────────────

    def add_chunks(
        self,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> list[str]:
        """批量添加 chunks + 向量 → 写入三个 Segment

        Args:
            chunks: [{"text": ..., "metadata": {...}}, ...]
            embeddings: [[f1, f2, ...], ...]

        Returns:
            生成的 doc_id 列表
        """
        import logging
        logger = logging.getLogger("app.core.rag.segments")

        doc_ids = []
        meta_records = []
        vector_records = []
        record_records = []

        for idx, ch in enumerate(chunks):
            text = ch.get("text", "")
            meta = ch.get("metadata", {}) or {}
            doc_id = meta.get(
                "_doc_id",
                f"{meta.get('chunk_index', idx)}_{abs(hash(text))}",
            )
            meta["_doc_id"] = doc_id
            doc_ids.append(doc_id)

            # 元数据记录
            meta_records.append({
                "doc_id": doc_id,
                "content": text,
                "metadata": meta,
            })

            # 向量记录
            if idx < len(embeddings):
                vector_records.append({
                    "doc_id": doc_id,
                    "embedding": embeddings[idx],
                })

            # 原始 chunk 记录
            record_records.append({
                "doc_id": doc_id,
                "text": text,
                "metadata": meta,
            })

        # 并行写入三个 Segment
        n_meta = self.metadata.add(doc_ids, meta_records)
        n_vec = self.vector.add(doc_ids, vector_records) if vector_records else 0
        n_rec = self.record.add(doc_ids, record_records)

        logger.debug(
            "SegmentManager.add_chunks: meta=%d, vec=%d, rec=%d (total=%d)",
            n_meta, n_vec, n_rec, len(doc_ids),
        )
        return doc_ids

    def remove_by_doc_ids(self, doc_ids: list[str]):
        """删除关联的所有 segment 数据"""
        self.metadata.delete(doc_ids)
        self.vector.delete(doc_ids)
        self.record.delete(doc_ids)

    def remove_by_doc_id(self, doc_id: str):
        """删除单个 chunk（remove_by_doc_ids 的单数别名）"""
        self.remove_by_doc_ids([doc_id])

    def delete_chunk(self, doc_id: str) -> bool:
        """删除单个 chunk，返回是否成功删除"""
        before = self.metadata.count()
        self.remove_by_doc_ids([doc_id])
        return self.metadata.count() < before

    def list_chunks(
        self, doc_filter_id: str = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[list[dict], int]:
        """分页列出 chunk，可按 KBDocument.doc_id 过滤

        Returns:
            (chunks, total_count)
        """
        return self.metadata.list_chunks_paginated(
            doc_filter_id=doc_filter_id, skip=skip, limit=limit,
        )

    # ── 检索 ───────────────────────────────────────────

    def dense_search(
        self, query_vec: list[float], k: int = 20,
        filter_dict: dict | None = None,
    ) -> list[dict]:
        """稠密向量检索 (向量 → 回填元数据)，支持 WhereFilter 后过滤

        向量索引不支持原地元数据过滤，策略:
        1. 以较大 k (k×3) 先召回多路候选
        2. 回填元数据后内存过滤
        3. 截断至 k 条返回
        """
        import logging
        logger = logging.getLogger("app.core.rag.segments")

        # 有过滤时扩大召回以补偿过滤损失
        search_k = max(k, k * 3) if filter_dict else k
        vec_results = self.vector.query(query_vec, k=search_k)
        if not vec_results:
            return []

        # 批量回填元数据
        ids = [r["doc_id"] for r in vec_results]
        meta_map = self.metadata.get(ids)

        results = []
        for r in vec_results:
            doc = meta_map.get(r["doc_id"], {})
            results.append({
                "doc_id": r["doc_id"],
                "score": r.get("score", 0.0),
                "content": doc.get("content", ""),
                "metadata": doc.get("metadata", {}),
            })

        # 后过滤（向量索引不支持原地 metadata filter）
        if filter_dict:
            from app.core.rag.filters import WhereFilter
            results = [
                r for r in results
                if WhereFilter.match(r["metadata"], filter_dict)
            ]

        # 截断到 k
        results = results[:k]
        logger.debug(
            "dense_search: %d candidates → %d results (k=%d, filter=%s)",
            len(vec_results), len(results), k,
            "yes" if filter_dict else "no",
        )
        return results

    def sparse_search(
        self, query: str, limit: int = 20,
        filter_dict: dict | None = None,
    ) -> list[dict]:
        """稀疏关键词检索 (tsvector)，支持 WhereFilter 元数据过滤"""
        return self.metadata.query(query, limit=limit, filter_dict=filter_dict)

    def get_all_ids(self) -> list[str]:
        """获取所有 doc_id"""
        return self.metadata.get_all_ids()

    def get_text(self, doc_id: str) -> Optional[str]:
        """获取单个 chunk 文本"""
        results = self.metadata.get([doc_id])
        if doc_id in results:
            return results[doc_id].get("content")
        return None

    # ── 生命周期 ───────────────────────────────────────

    def count(self) -> int:
        return self.metadata.count()

    def clear(self):
        """清空所有 segment 数据"""
        self.metadata.clear()
        self.vector.clear()
        self.record.clear()

    def close(self):
        """释放所有 segment 资源"""
        for seg in (self._metadata, self._vector, self._record):
            if seg:
                try:
                    seg.close()
                except Exception:
                    pass

    # ── Ghost 与 Compact ────────────────────────────────

    def ghost_stats(self) -> dict:
        """返回 FAISS 索引中幽灵向量的统计信息"""
        return self.vector.ghost_stats()

    def compact(self, embedder) -> int:
        """压缩 FAISS 索引：重新嵌入所有有效向量，移除幽灵向量

        Args:
            embedder: 嵌入器实例（需有 embed_batch 或 embed 方法）

        Returns:
            int: 压缩后的有效向量数
        """
        return self.vector.rebuild_index(embedder, self.metadata)

    # ── 统计 ────────────────────────────────────────────

    @property
    def stats(self) -> dict:
        base = {
            "kb_path": self.kb_path,
            "dim": self.dim,
            "metadata_count": self.metadata.count(),
            "vector_count": self.vector.count(),
            "record_count": self.record.count(),
            "metadata_type": type(self._metadata).__name__ if self._metadata else "default",
            "vector_type": type(self._vector).__name__ if self._vector else "default",
            "record_type": type(self._record).__name__ if self._record else "default",
        }
        # 合并 ghost 统计
        try:
            base.update(self.ghost_stats())
        except Exception:
            pass
        return base


# ── 延迟导入以避免循环 ─────────────────────────────────────
from app.core.rag.segments.metadata_segment import MetadataSegment  # noqa: E402, F811
from app.core.rag.segments.vector_segment import VectorSegment  # noqa: E402, F811
from app.core.rag.segments.record_segment import RecordSegment  # noqa: E402, F811
