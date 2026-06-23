"""
Qdrant 向量存储 — 生产级持久化向量检索

特性：
- Qdrant 云/自部署双模式（API Key 或本地 gRPC）
- 与现有 VectorStore (FAISS) 接口兼容
- 持久化存储（不丢失索引）
- 元数据过滤（按知识库/来源/时间范围）
- 批量操作 + 连接池复用
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Optional

import numpy as np

logger = logging.getLogger("app.core.rag.qdrant_store")

# ── Qdrant 向量存储 ────────────────────────────────────────


class QdrantVectorStore:
    """
    Qdrant 向量存储 — 生产环境替换 FAISS VectorStore

    用法:
        store = QdrantVectorStore(
            collection_name="my_kb",
            dim=1536,
            url="http://localhost:6333",
        )
        store.add(embeddings, doc_ids, payloads)
        results = store.search(query_vec, k=10)

    API 兼容性：
        - add(embeddings, doc_ids) ← 与 FAISS VectorStore 相同签名
        - search(query_vec, k) ← 返回同结构 [{"doc_id","score","distance"}]
        - remove(doc_id) ← Qdrant 原生支持，不需要重建
    """

    def __init__(
        self,
        collection_name: str,
        dim: int,
        url: str | None = None,
        api_key: str | None = None,
        host: str | None = None,
        port: int = 6333,
        prefer_grpc: bool = False,
    ):
        self._collection_name = collection_name
        self._dim = dim
        self._url = url
        self._api_key = api_key
        self._host = host or "localhost"
        self._port = port
        self._prefer_grpc = prefer_grpc
        self._client = None
        self._connected = False

    # ── 连接管理 ──────────────────────────────────────────

    @property
    def client(self):
        """懒加载 QdrantClient"""
        if self._client is None:
            self._connect()
        return self._client

    def _connect(self) -> None:
        """连接到 Qdrant（云 API 或本地实例）"""
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.http.exceptions import UnexpectedResponse

            if self._url:
                # 远程 Qdrant 云（如 Qdrant Cloud API）
                self._client = QdrantClient(
                    url=self._url,
                    api_key=self._api_key,
                    prefer_grpc=self._prefer_grpc,
                )
                logger.info(
                    "Connected to Qdrant Cloud: %s (collection=%s)",
                    self._url, self._collection_name,
                )
            elif self._api_key:
                # 本地 + API Key 模式
                self._client = QdrantClient(
                    host=self._host,
                    port=self._port,
                    api_key=self._api_key,
                    prefer_grpc=self._prefer_grpc,
                )
            else:
                # 本地无认证模式
                self._client = QdrantClient(
                    host=self._host,
                    port=self._port,
                )
                logger.info(
                    "Connected to Qdrant local: %s:%d (collection=%s)",
                    self._host, self._port, self._collection_name,
                )

            self._connected = True
            self._ensure_collection()

        except ImportError:
            raise ImportError(
                "qdrant-client not installed. Run: pip install qdrant-client"
            )
        except Exception as e:
            logger.error("Failed to connect to Qdrant: %s", e)
            self._connected = False
            raise

    def _ensure_collection(self) -> None:
        """创建集合（如不存在）"""
        from qdrant_client.models import Distance, VectorParams

        try:
            self._client.get_collection(self._collection_name)
            logger.debug(
                "Qdrant collection '%s' already exists, skip creation",
                self._collection_name,
            )
        except Exception:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(
                "Created Qdrant collection '%s' (dim=%d, distance=cosine)",
                self._collection_name, self._dim,
            )

    # ── CRUD ──────────────────────────────────────────────

    def add(
        self,
        embeddings: list[list[float]],
        doc_ids: list[str],
        payloads: list[dict[str, Any]] | None = None,
    ) -> None:
        """
        批量添加向量

        Args:
            embeddings: 向量列表 [N, dim]
            doc_ids: 文档 ID 列表 [N]
            payloads: 元数据列表 [N]，如 {"content": ..., "source": ..., "chunk_idx": ...}
        """
        from qdrant_client.models import PointStruct

        if not embeddings:
            return

        points: list[PointStruct] = []
        for i, (vec, did) in enumerate(zip(embeddings, doc_ids)):
            # Qdrant 需要 UUID 或正整数作为 point id
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, did))
            payload = payloads[i] if payloads and i < len(payloads) else {}
            payload["_doc_id"] = did
            points.append(PointStruct(
                id=point_id,
                vector=vec,
                payload=payload,
            ))

        self.client.upsert(
            collection_name=self._collection_name,
            points=points,
        )
        logger.debug("Qdrant: added %d vectors to '%s'", len(points), self._collection_name)

    def remove(self, doc_id: str) -> None:
        """
        Qdrant 原生支持删除 — 通过 payload 过滤删除

        注意：Qdrant 通过 payload 过滤删除（因为 point id 是 UUID 而非 doc_id）
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        try:
            self.client.delete(
                collection_name=self._collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="_doc_id",
                            match=MatchValue(value=doc_id),
                        )
                    ]
                ),
            )
            logger.debug("Qdrant: removed doc_id='%s'", doc_id)
        except Exception as e:
            logger.warning("Qdrant remove failed for '%s': %s", doc_id, e)

    def search(
        self,
        query_vec: list[float],
        k: int = 20,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        相似搜索

        Args:
            query_vec: 查询向量 [dim]
            k: top-k
            filter_conditions: 元数据过滤字段（如 {"kb_name": "python_docs"}）

        Returns:
            [{"doc_id": ..., "score": ..., "distance": ..., "content": ..., "metadata": {...}}]
        """
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        qdrant_filter = None
        if filter_conditions:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v))
                for k, v in filter_conditions.items()
            ]
            qdrant_filter = Filter(must=conditions)

        results = self.client.search(
            collection_name=self._collection_name,
            query_vector=query_vec,
            limit=k,
            query_filter=qdrant_filter,
            with_payload=True,
            with_vectors=False,
        )

        output: list[dict[str, Any]] = []
        for hit in results:
            payload = hit.payload or {}
            output.append({
                "doc_id": payload.get("_doc_id", str(hit.id)),
                "score": float(hit.score),
                "distance": float(1.0 - hit.score) if hit.score is not None else 1.0,
                "content": payload.get("content", ""),
                "metadata": {k: v for k, v in payload.items() if not k.startswith("_")},
            })

        return output

    def count(self) -> int:
        """返回向量总数"""
        try:
            info = self.client.get_collection(self._collection_name)
            return info.points_count or 0
        except Exception:
            return 0

    def clear(self) -> None:
        """清空集合（删除后重建）"""
        try:
            self.client.delete_collection(self._collection_name)
            self._ensure_collection()
            logger.info("Qdrant: cleared collection '%s'", self._collection_name)
        except Exception as e:
            logger.error("Qdrant clear failed: %s", e)

    def is_connected(self) -> bool:
        """检查连接状态"""
        if not self._connected:
            return False
        try:
            self.client.get_collection(self._collection_name)
            return True
        except Exception:
            return False


# ── Qdrant 混合存储（兼容 HybridStorage 接口）───────────────


class QdrantHybridStorage:
    """
    Qdrant 混合存储 — 替换 HybridStorage (FAISS + SQLite FTS5)

    实现与 HybridStorage 相同的 add_chunks / dense_search / sparse_search / remove_by_doc_id 接口。

    稀疏搜索依赖 SQLite FTS5（从 DocumentStore 继承），
    稠密搜索使用 QdrantVectorStore。
    """

    def __init__(
        self,
        kb_path: str,
        dim: int,
        collection_name: str | None = None,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
    ):
        import os as _os
        _os.makedirs(kb_path, exist_ok=True)

        self._dim = dim
        self._kb_name = collection_name or _os.path.basename(kb_path.rstrip("/\\"))

        # 文档元数据存储（SQLite + FTS5）
        from app.core.rag.vector_store import DocumentStore
        self._doc_store = DocumentStore(_os.path.join(kb_path, "docs.db"))

        # Qdrant 稠密向量存储
        self._vec_store = QdrantVectorStore(
            collection_name=self._kb_name,
            dim=dim,
            url=qdrant_url or os.getenv("QDRANT_URL"),
            api_key=qdrant_api_key or os.getenv("QDRANT_API_KEY"),
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )

    @property
    def dim(self) -> int:
        return self._dim

    def add_chunks(
        self,
        chunks: list[dict],
        embeddings: list[list[float]],
    ) -> None:
        """批量添加 chunks + 向量"""
        doc_ids: list[str] = []
        payloads: list[dict[str, Any]] = []

        for ch in chunks:
            doc_id = f"{ch['metadata'].get('chunk_index', '')}_{abs(hash(ch['text']))}"
            ch["metadata"]["_doc_id"] = doc_id
            self._doc_store.insert(doc_id, ch["text"], ch["metadata"])
            doc_ids.append(doc_id)
            payloads.append({
                "content": ch["text"],
                **{k: v for k, v in ch["metadata"].items() if k != "_doc_id"},
            })

        self._vec_store.add(embeddings, doc_ids, payloads)

    def remove_by_doc_id(self, doc_id: str) -> None:
        self._doc_store.delete(doc_id)
        self._vec_store.remove(doc_id)

    def dense_search(
        self,
        query_vec: list[float],
        k: int = 20,
        filter_conditions: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """稠密向量检索"""
        return self._vec_store.search(query_vec, k, filter_conditions)

    def sparse_search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """稀疏关键词检索"""
        return self._doc_store.ft_search(query, limit)

    def count(self) -> int:
        return self._vec_store.count()

    def clear(self) -> None:
        for doc_id in self._doc_store.get_all_ids():
            self.remove_by_doc_id(doc_id)


# ── 工厂函数 ──────────────────────────────────────────────


def create_qdrant_hybrid_storage(
    kb_path: str,
    dim: int,
    collection_name: str | None = None,
) -> QdrantHybridStorage:
    """
    工厂函数：从环境变量自动配置 QdrantHybridStorage

    环境变量：
      QDRANT_URL       — Qdrant Cloud URL（如 https://xyz.cloud.qdrant.io:6333）
      QDRANT_API_KEY   — Qdrant Cloud API Key
      QDRANT_HOST      — 本地 Qdrant 主机（默认 localhost）
      QDRANT_PORT      — 本地 Qdrant 端口（默认 6333）
    """
    return QdrantHybridStorage(
        kb_path=kb_path,
        dim=dim,
        collection_name=collection_name,
    )
