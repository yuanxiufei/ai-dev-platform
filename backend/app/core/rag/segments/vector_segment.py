"""
向量 Segment — FAISS 稠密向量索引

借鉴 Chroma Vector Segment (HNSW 后端):
- FAISS IndexIDMap(IndexFlatIP) — 内积 / 余弦相似度
- 支持 save/load 持久化
- add_with_ids / search 标准接口
"""

from __future__ import annotations

import logging
import os
import json
import threading
from typing import Optional

import numpy as np

from app.core.rag.segments import Segment

logger = logging.getLogger("app.core.rag.segments.vector")


class VectorSegment(Segment):
    """FAISS 向量索引存储

    实现 Segment ABC:
    - add(ids, records)    → FAISS add_with_ids
    - get(ids)             → 不支持 (向量无查询语义)
    - delete(ids)          → FAISS remove_ids
    - query(vector, k)     → FAISS search
    """

    def __init__(self, kb_path: str, dim: int = 384, scope: str = "default"):
        super().__init__(name="vector", scope=scope)
        self._kb_path = kb_path.rstrip("/\\")
        self._dim = dim
        self._index_file = self._kb_path + "/faiss.index"
        self._id_map_file = self._kb_path + "/faiss.idmap.json"
        self._lock = threading.Lock()
        self._index = None
        self._id_to_idx: dict[str, int] = {}  # doc_id → FAISS 内部 idx
        self._idx_to_id: dict[int, str] = {}  # FAISS 内部 idx → doc_id
        self._next_idx = 0
        self._init_index()

    # ── FAISS 初始化 ─────────────────────────────────────

    def _init_index(self):
        """初始化或加载 FAISS 索引"""
        import faiss

        with self._lock:
            if os.path.exists(self._index_file) and os.path.exists(self._id_map_file):
                try:
                    self._index = faiss.read_index(self._index_file)
                    with open(self._id_map_file, "r") as f:
                        data = json.load(f)
                        self._next_idx = data["next_idx"]
                        # 重建双向映射
                        id_list = data["ids"]  # [(doc_id, idx), ...]
                        for doc_id, idx in id_list:
                            self._id_to_idx[doc_id] = idx
                            self._idx_to_id[idx] = doc_id
                    logger.info("VectorSegment loaded: %d vectors, dim=%d",
                                self._index.ntotal, self._dim)
                    return
                except Exception as e:
                    logger.warning("FAISS load failed: %s, creating new index", e)

            # 新建索引: IndexIDMap(IndexFlatIP) = 内积搜索
            base_index = faiss.IndexFlatIP(self._dim)
            self._index = faiss.IndexIDMap(base_index)
            self._next_idx = 0
            self._id_to_idx = {}
            self._idx_to_id = {}
            logger.info("VectorSegment created: dim=%d, type=%s",
                        self._dim, "IndexIDMap(IndexFlatIP)")

    # ── Segment ABC 实现 ─────────────────────────────────

    def add(self, ids: list[str], records: list[dict]) -> int:
        """批量添加向量"""
        if not ids or not records:
            return 0
        if self._index is None:
            self._init_index()

        vectors = []
        faiss_ids = []

        with self._lock:
            for rec_id, rec in zip(ids, records):
                embedding = rec.get("embedding", [])
                if not embedding or len(embedding) != self._dim:
                    logger.warning("VectorSegment.add: invalid embedding for %s, "
                                   "len=%d expected=%d, skip",
                                   rec_id, len(embedding), self._dim)
                    continue

                vectors.append(embedding)
                doc_id = rec.get("doc_id", rec_id)

                # 重用已有 idx 或分配新的
                if doc_id in self._id_to_idx:
                    faiss_idx = self._id_to_idx[doc_id]
                else:
                    faiss_idx = self._next_idx
                    self._next_idx += 1
                    self._id_to_idx[doc_id] = faiss_idx
                    self._idx_to_id[faiss_idx] = doc_id

                faiss_ids.append(faiss_idx)

            if vectors:
                np_vec = np.array(vectors, dtype=np.float32)
                np_ids = np.array(faiss_ids, dtype=np.int64)
                self._index.add_with_ids(np_vec, np_ids)
                self._save()
                logger.debug("VectorSegment.add: %d vectors", len(vectors))

            return len(vectors)

    def get(self, ids: list[str]) -> dict[str, dict]:
        """向量无 get 语义，返回空"""
        return {}

    def delete(self, ids: list[str]) -> int:
        """删除向量 (FAISS remove_ids)"""
        if not ids or self._index is None:
            return 0

        with self._lock:
            faiss_ids = []
            for doc_id in ids:
                if doc_id in self._id_to_idx:
                    faiss_ids.append(self._id_to_idx[doc_id])
                    idx = self._id_to_idx.pop(doc_id)
                    self._idx_to_id.pop(idx, None)

            if faiss_ids:
                np_ids = np.array(faiss_ids, dtype=np.int64)
                self._index.remove_ids(np_ids)
                self._save()
                return len(faiss_ids)
            return 0

    def count(self) -> int:
        return self._index.ntotal if self._index else 0

    def clear(self):
        """清空索引"""
        import faiss

        with self._lock:
            base_index = faiss.IndexFlatIP(self._dim)
            self._index = faiss.IndexIDMap(base_index)
            self._next_idx = 0
            self._id_to_idx = {}
            self._idx_to_id = {}
            self._save()

    def close(self):
        self._save()

    # ── 向量检索 ─────────────────────────────────────────

    def query(
        self, query_vec: list[float], k: int = 20,
    ) -> list[dict]:
        """FAISS 向量搜索

        Args:
            query_vec: 查询向量 [f1, f2, ...]
            k: top-k 返回数量

        Returns:
            [{"doc_id": ..., "score": ...}, ...]
        """
        if not query_vec or self._index is None or self._index.ntotal == 0:
            return []

        k = min(k, self._index.ntotal)
        np_vec = np.array([query_vec], dtype=np.float32)

        with self._lock:
            try:
                scores, indices = self._index.search(np_vec, k)
            except Exception as e:
                logger.error("FAISS search failed: %s", e)
                return []

        results = []
        for score, idx in zip(scores[0], indices[0]):
            idx_int = int(idx)
            if idx_int == -1:
                continue
            doc_id = self._idx_to_id.get(idx_int)
            if doc_id:
                # FAISS 内积归一化到 [0, 1] — L2 归一化后可视为余弦相似度
                results.append({
                    "doc_id": doc_id,
                    "score": max(0.0, min(1.0, float(score))),
                })

        return results

    # ── Ghost 向量统计（FAISS IndexIDMap 删除后残留） ────

    @property
    def ghost_count(self) -> int:
        """幽灵向量数量：FAISS 索引中存在但已从 ID 映射移除的向量"""
        if self._index is None:
            return 0
        return max(0, self._index.ntotal - len(self._id_to_idx))

    @property
    def ghost_ratio(self) -> float:
        """幽灵向量占比"""
        if self._index is None or self._index.ntotal == 0:
            return 0.0
        return self.ghost_count / self._index.ntotal

    def ghost_stats(self) -> dict:
        """返回 FAISS 索引健康状态"""
        total = self._index.ntotal if self._index else 0
        ghosts = self.ghost_count
        return {
            "index_total": total,
            "alive_in_map": total - ghosts,
            "ghost_count": ghosts,
            "ghost_ratio": round(self.ghost_ratio, 4),
            "needs_compact": self.is_dirty(threshold=0.2),
        }

    def is_dirty(self, threshold: float = 0.2) -> bool:
        """索引是否需要压缩（幽灵向量占比超过阈值）"""
        return self.ghost_ratio > threshold

    # ── 索引压缩 ─────────────────────────────────────────

    def rebuild_index(self, embedder, metadata_segment) -> int:
        """重建 FAISS 索引：重新嵌入所有有效 chunk

        删除幽灵向量，恢复检索性能。大规模删除后建议调用。

        Args:
            embedder: 嵌入器实例（需有 embed_batch 方法）
            metadata_segment: MetadataSegment 实例，用于获取 chunk 内容

        Returns:
            int: 重建后的有效向量数
        """
        import faiss

        if self._index is None:
            return 0

        # 收集所有有效 doc_id
        valid_ids = list(self._id_to_idx.keys())
        if not valid_ids:
            return 0

        # 批量获取文本
        texts = []
        batch_size = 200
        for i in range(0, len(valid_ids), batch_size):
            batch_ids = valid_ids[i:i + batch_size]
            meta_map = metadata_segment.get(batch_ids)
            for doc_id in batch_ids:
                doc = meta_map.get(doc_id, {})
                texts.append((doc_id, doc.get("content", "")))

        # 重新嵌入
        content_texts = [t[1] for t in texts]
        try:
            embeddings = embedder.embed_batch(content_texts)
        except AttributeError:
            # fallback: 单条 embed
            embeddings = [embedder.embed(t) for t in content_texts]

        # 重建索引
        with self._lock:
            base_index = faiss.IndexFlatIP(self._dim)
            new_index = faiss.IndexIDMap(base_index)

            new_id_map: dict[str, int] = {}
            new_idx_map: dict[int, str] = {}
            faiss_ids = []

            for idx, (doc_id, _) in enumerate(texts):
                faiss_ids.append(idx)
                new_id_map[doc_id] = idx
                new_idx_map[idx] = doc_id

            np_vec = np.array(embeddings, dtype=np.float32)
            np_ids = np.array(faiss_ids, dtype=np.int64)
            new_index.add_with_ids(np_vec, np_ids)

            self._index = new_index
            self._id_to_idx = new_id_map
            self._idx_to_id = new_idx_map
            self._next_idx = len(texts)
            self._save()

        logger.info(
            "VectorSegment.rebuild_index: %d vectors rebuilt (was %d total, %d ghosts)",
            len(texts), self._index.ntotal, self.ghost_count,
        )
        return len(texts)

    # ── 持久化 ───────────────────────────────────────────

    def _save(self):
        """保存 FAISS 索引 + ID 映射"""
        if self._index is None:
            return

        try:
            import faiss
            faiss.write_index(self._index, self._index_file)

            id_data = {
                "next_idx": self._next_idx,
                "ids": list(self._id_to_idx.items()),
                "dim": self._dim,
            }
            with open(self._id_map_file, "w") as f:
                json.dump(id_data, f)

        except Exception as e:
            logger.error("VectorSegment._save failed: %s", e)
