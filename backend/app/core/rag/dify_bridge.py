"""
Dify 知识桥接模块 — 将 Dify 训练的知识库导入主项目 RAG

设计原则:
- Dify 负责训练（文档上传、分块、标注、质量检查）
- 主项目负责检索（FAISS + PostgreSQL tsvector + BGE MiniLM）
- 桥接层只传递 **文本 + 元数据**，不做向量直传（维度不匹配）
  Dify: text-embedding-ada-002 (1536dim)
  主项目: BGE MiniLM all-MiniLM-L6-v2 (384dim)

支持三种导入方式:
1. Weaviate 直连 — 直接读 Dify 的 Weaviate 向量库提取 chunks
2. Dify API — 通过 Dify 知识库 REST API 拉取文档
3. 文件导入 — 读取 knowledge-data/documents/ 下的原始文档走主项目 pipeline

Usage:
    bridge = DifyKnowledgeBridge()
    await bridge.import_from_weaviate(
        kb_name="技术文档",
        weaviate_url="http://localhost:8080",
        weaviate_class="DifyDocument",
    )
    # 或
    await bridge.import_from_files(
        kb_name="技术文档",
        doc_dir="knowledge-data/documents/",
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.rag.embedder import get_embedding_provider
from app.core.rag.kb_manager import KBInstance, get_kb_manager_v2
from app.core.rag.chunking import get_chunker
from app.core.rag.parsers import select_parser as discover_parser
from app.core.rag.config import get_rag_config

logger = logging.getLogger("app.core.rag.dify_bridge")

ProgressHandler = Callable[[str, float], None]


# ── 数据模型 ──────────────────────────────────────────────


@dataclass
class DifyChunk:
    """从 Dify 提取的文档块（仅文本 + 元数据，不含向量）"""
    text: str
    document_name: str = ""
    dataset_name: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    metadata: dict = field(default_factory=dict)

    def to_kb_chunk(self) -> dict:
        meta = {
            "source": f"dify:{self.dataset_name}/{self.document_name}",
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "document_name": self.document_name,
            "dataset_name": self.dataset_name,
            **self.metadata,
        }
        return {"text": self.text, "metadata": meta}


@dataclass
class ImportStats:
    """导入统计"""
    kb_name: str = ""
    total_documents: int = 0
    total_chunks: int = 0
    total_embedded: int = 0
    errors: list[str] = field(default_factory=list)
    duration_sec: float = 0.0


# ── Weaviate 提取器 ────────────────────────────────────────


class WeaviateExtractor:
    """从 Dify 的 Weaviate 向量库提取文档块"""

    def __init__(self, url: str, api_key: Optional[str] = None):
        self._url = url.rstrip("/")
        self._api_key = api_key
        self._client = None

    def _get_client(self):
        """延迟加载 weaviate-client"""
        if self._client is not None:
            return self._client
        try:
            import weaviate
            import weaviate.classes as wvc

            if self._api_key:
                self._client = weaviate.connect_to_local(
                    host=self._url.replace("http://", "").replace("https://", "").split(":")[0],
                    port=int(self._url.split(":")[-1]) if ":" in self._url.split("//")[-1] else 8080,
                    auth_credentials=wvc.init.Auth.api_key(self._api_key),
                )
            else:
                self._client = weaviate.connect_to_local(
                    host=self._url.replace("http://", "").replace("https://", "").split(":")[0],
                    port=int(self._url.split(":")[-1]) if ":" in self._url.split("//")[-1] else 8080,
                )
            return self._client
        except ImportError:
            raise ImportError(
                "weaviate-client not installed. "
                "Run: pip install weaviate-client"
            )

    def extract_chunks(
        self,
        class_name: str = "DifyDocument",
        limit: int = 10000,
        batch_size: int = 100,
        progress_cb: Optional[ProgressHandler] = None,
    ) -> list[DifyChunk]:
        """
        从 Weaviate 提取所有文档块

        Dify 在 Weaviate 中的典型 class 名: DifyDocument_{dataset_id}
        每个对象包含: text, doc_id, document_name, dataset_id, document_hash 等
        """
        client = self._get_client()
        collection = client.collections.get(class_name)

        chunks: list[DifyChunk] = []
        offset = 0

        while True:
            response = collection.query.fetch_objects(
                limit=batch_size,
                offset=offset,
                include_vector=False,  # 不拉向量数据，维度不兼容
            )

            batch = []
            for obj in response.objects:
                props = obj.properties
                chunks.append(DifyChunk(
                    text=props.get("text", "") or props.get("content", ""),
                    document_name=props.get("document_name", props.get("doc_id", "unknown")),
                    dataset_name=props.get("dataset_id", class_name),
                    chunk_index=props.get("chunk_index", offset),
                    total_chunks=props.get("total_chunks", 0),
                    metadata={
                        k: v for k, v in props.items()
                        if k not in ("text", "content", "document_name", "doc_id",
                                     "dataset_id", "chunk_index", "total_chunks")
                    },
                ))

            if not response.objects:
                break

            offset += len(response.objects)
            if progress_cb:
                progress_cb("extracting", min(95, offset / max(limit, 1) * 95))

            if len(response.objects) < batch_size:
                break

        logger.info("Extracted %d chunks from Weaviate class '%s'",
                     len(chunks), class_name)
        return chunks

    def close(self):
        if self._client:
            self._client.close()
            self._client = None


# ── Dify API 提取器 ─────────────────────────────────────────


class DifyAPIExtractor:
    """通过 Dify Knowledge Base API 提取文档"""

    def __init__(self, api_base: str, api_key: str):
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        import httpx
        url = f"{self._api_base}/v1{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
            resp.raise_for_status()
            return resp.json()

    async def list_datasets(self, page: int = 1, limit: int = 50) -> list[dict]:
        """列出所有知识库"""
        data = await self._request("GET", "/datasets", params={"page": page, "limit": limit})
        return data.get("data", [])

    async def list_documents(
        self,
        dataset_id: str,
        page: int = 1,
        limit: int = 50,
    ) -> list[dict]:
        """列出知识库中的所有文档"""
        data = await self._request(
            "GET",
            f"/datasets/{dataset_id}/documents",
            params={"page": page, "limit": limit},
        )
        return data.get("data", [])

    async def extract_chunks(
        self,
        dataset_id: str,
        progress_cb: Optional[ProgressHandler] = None,
    ) -> list[DifyChunk]:
        """通过 API 提取知识库的所有文档块"""
        chunks: list[DifyChunk] = []

        # 1. 获取知识库信息
        dataset_info = await self._request("GET", f"/datasets/{dataset_id}")
        dataset_name = dataset_info.get("name", dataset_id)

        # 2. 获取所有文档
        documents = await self.list_documents(dataset_id)
        total_docs = len(documents)

        for doc_idx, doc in enumerate(documents):
            doc_id = doc.get("id", "")
            doc_name = doc.get("name", "unknown")

            if progress_cb:
                progress_cb("extracting", (doc_idx / max(total_docs, 1)) * 90)

            # 3. 获取文档的分段列表（Dify API 支持分段查询）
            try:
                segments = await self._get_segments(dataset_id, doc_id)
                for seg_idx, seg in enumerate(segments):
                    chunks.append(DifyChunk(
                        text=seg.get("content", ""),
                        document_name=doc_name,
                        dataset_name=dataset_name,
                        chunk_index=seg.get("position", seg_idx),
                        total_chunks=len(segments),
                        metadata={
                            "doc_id": doc_id,
                            "segment_id": seg.get("id", ""),
                            "word_count": seg.get("word_count", 0),
                            "hit_count": seg.get("hit_count", 0),
                            "status": seg.get("status", ""),
                        },
                    ))
            except Exception as e:
                logger.warning("Failed to extract segments for doc %s: %s", doc_id, e)

        logger.info("Extracted %d chunks from Dify API (dataset: %s)",
                     len(chunks), dataset_name)
        return chunks

    async def _get_segments(
        self,
        dataset_id: str,
        document_id: str,
        page: int = 1,
        limit: int = 100,
    ) -> list[dict]:
        """获取文档分段"""
        all_segments: list[dict] = []
        while True:
            data = await self._request(
                "GET",
                f"/datasets/{dataset_id}/documents/{document_id}/segments",
                params={"page": page, "limit": limit},
            )
            segments = data.get("data", [])
            all_segments.extend(segments)
            if len(segments) < limit:
                break
            page += 1
        return all_segments


# ── 文件导入器 ──────────────────────────────────────────────


class FileImporter:
    """直接读取文档文件，走主项目 pipeline（最简单可靠）"""

    def __init__(self, doc_dir: str):
        self._doc_dir = doc_dir

    def list_files(self, extensions: Optional[list[str]] = None) -> list[str]:
        """列出所有可解析的文档文件"""
        if extensions is None:
            extensions = [".md", ".txt", ".pdf", ".docx",
                          ".html", ".htm", ".csv", ".json"]

        files: list[str] = []
        if not os.path.isdir(self._doc_dir):
            logger.warning("Document dir not found: %s", self._doc_dir)
            return files

        for root, _, filenames in os.walk(self._doc_dir):
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                if ext in extensions:
                    files.append(os.path.join(root, fn))

        return sorted(files)

    async def parse_and_chunk(
        self,
        filepath: str,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> list[dict]:
        """解析文件并分块（不嵌入）"""
        parser = discover_parser(filepath)
        if parser is None:
            raise ValueError(f"No parser for: {filepath}")

        parsed = await parser.parse(filepath)
        text = parsed.text
        doc_title = parsed.title or os.path.basename(filepath)
        file_ext = os.path.splitext(filepath)[1].lower()

        # 选择分块策略
        strategy = "markdown" if file_ext in (".md", ".markdown", ".rst") else "recursive"
        chunker = get_chunker(
            strategy=strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        chunks = chunker.chunk(text, metadata={
            "source": filepath,
            "title": doc_title,
            "parser": parser.name,
            **parsed.metadata,
        })
        return chunks


# ── 知识桥接器 ──────────────────────────────────────────────


class DifyKnowledgeBridge:
    """
    Dify → 主项目 知识桥接器

    核心流程:
    Dify 训练知识库 → 提取纯文本 chunks → BGE 重嵌入 → 主项目 FAISS + tsvector 存储

    使用方式:
        bridge = DifyKnowledgeBridge()

        # 方式1: 从 Weaviate 直连导入
        # stats = await bridge.import_from_weaviate(kb_name="技术文档", ...)

        # 方式2: 从 Dify API 导入
        # stats = await bridge.import_from_dify_api(kb_name="技术文档", ...)

        # 方式3: 从文件目录导入（最推荐）
        # stats = await bridge.import_from_files(kb_name="技术文档", doc_dir="knowledge-data/documents/")
    """

    def __init__(self):
        self._kb_mgr = get_kb_manager_v2()
        self._embedder = get_embedding_provider()
        self._config = get_rag_config()

    # ── 方式1: Weaviate 直连 ────────────────────────────────

    async def import_from_weaviate(
        self,
        kb_name: str,
        kb_description: str = "",
        weaviate_url: str = "http://localhost:8080",
        weaviate_api_key: Optional[str] = None,
        weaviate_class: str = "DifyDocument",
        re_chunk: bool = False,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        progress_cb: Optional[ProgressHandler] = None,
    ) -> ImportStats:
        """
        从 Dify 的 Weaviate 向量库导入知识库

        Args:
            kb_name: 主项目中创建的知识库名称
            weaviate_url: Weaviate 服务地址
            weaviate_class: Dify 在 Weaviate 中的 class 名称
            re_chunk: 是否重新分块（否则保留 Dify 的分块结果）
        """
        import time
        start = time.monotonic()
        stats = ImportStats(kb_name=kb_name)

        try:
            # 1. 创建/获取主项目知识库
            self._report(progress_cb, "init_kb", 0)
            kb = await self._get_or_create_kb(
                kb_name, kb_description,
                chunk_size=chunk_size or 512,
                chunk_overlap=chunk_overlap or 50,
            )
            stats.kb_name = kb.name

            # 2. 从 Weaviate 提取 chunks
            self._report(progress_cb, "extract", 5)
            extractor = WeaviateExtractor(weaviate_url, weaviate_api_key)
            try:
                dify_chunks = extractor.extract_chunks(
                    class_name=weaviate_class,
                    progress_cb=lambda s, p: self._report(progress_cb, f"extract:{s}", 5 + p * 0.3),
                )
            finally:
                extractor.close()

            if not dify_chunks:
                stats.errors.append("No chunks extracted from Weaviate")
                return stats

            stats.total_chunks = len(dify_chunks)
            self._report(progress_cb, "embedding", 40)

            # 3. 重嵌入 + 存入主项目
            if re_chunk:
                await self._re_chunk_and_embed(kb, dify_chunks, chunk_size or 512,
                                               chunk_overlap or 50, progress_cb, stats)
            else:
                await self._embed_and_store(
                    kb, [c.to_kb_chunk() for c in dify_chunks],
                    progress_cb, stats,
                )

        except Exception as e:
            logger.exception("Weaviate import failed")
            stats.errors.append(str(e))

        stats.duration_sec = time.monotonic() - start
        self._report(progress_cb, "done", 100)
        logger.info("Weaviate import complete: %s", stats)
        return stats

    # ── 方式2: Dify API ────────────────────────────────────

    async def import_from_dify_api(
        self,
        kb_name: str,
        kb_description: str = "",
        dify_api_base: str = "http://localhost:5001",
        dify_api_key: str = "",
        dataset_id: str = "",
        progress_cb: Optional[ProgressHandler] = None,
    ) -> ImportStats:
        """
        通过 Dify API 导入知识库

        Args:
            dify_api_base: Dify API 地址 (如 http://localhost:5001)
            dify_api_key: Dify API Key (Dataset 权限)
            dataset_id: Dify 知识库 ID
        """
        import time
        start = time.monotonic()
        stats = ImportStats(kb_name=kb_name)

        try:
            kb = await self._get_or_create_kb(kb_name, kb_description)
            stats.kb_name = kb.name

            self._report(progress_cb, "extract", 5)
            extractor = DifyAPIExtractor(dify_api_base, dify_api_key)
            dify_chunks = await extractor.extract_chunks(
                dataset_id=dataset_id,
                progress_cb=lambda s, p: self._report(progress_cb, s, 5 + p * 0.3),
            )

            if not dify_chunks:
                stats.errors.append("No chunks extracted from Dify API")
                return stats

            stats.total_chunks = len(dify_chunks)
            self._report(progress_cb, "embedding", 40)

            await self._embed_and_store(
                kb, [c.to_kb_chunk() for c in dify_chunks],
                progress_cb, stats,
            )

        except Exception as e:
            logger.exception("Dify API import failed")
            stats.errors.append(str(e))

        stats.duration_sec = time.monotonic() - start
        self._report(progress_cb, "done", 100)
        return stats

    # ── 方式3: 文件导入（推荐）──────────────────────────────

    async def import_from_files(
        self,
        kb_name: str,
        kb_description: str = "",
        doc_dir: Optional[str] = None,
        file_patterns: Optional[list[str]] = None,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        progress_cb: Optional[ProgressHandler] = None,
    ) -> ImportStats:
        """
        从文档目录导入知识库（推荐方式）

        读取原始文档 → 走主项目 pipeline（解析→分块→嵌入→存储）
        这是最可靠的方式，不依赖 Dify 内部格式。

        Args:
            kb_name: 知识库名称
            doc_dir: 文档目录，默认 'knowledge-data/documents/'
            file_patterns: 文件扩展名过滤，默认 ['*.md', '*.txt', '*.pdf', '*.docx']
        """
        import time
        start = time.monotonic()
        stats = ImportStats(kb_name=kb_name)

        try:
            if doc_dir is None:
                # 容器内默认路径，与 compose.shared.yml 中的卷挂载一致
                doc_dir = os.environ.get("KNOWLEDGE_DATA_DIR", "/app/knowledge-data")
                doc_dir = os.path.join(doc_dir, "documents")

            # 确保路径存在
            if not os.path.isabs(doc_dir):
                doc_dir = os.path.join(os.getcwd(), doc_dir)

            kb = await self._get_or_create_kb(
                kb_name, kb_description,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            stats.kb_name = kb.name

            # 列出文件
            self._report(progress_cb, "scanning", 0)
            importer = FileImporter(doc_dir)
            file_paths = importer.list_files()

            if file_patterns:
                import fnmatch
                filtered: list[str] = []
                for fp in file_paths:
                    for pat in file_patterns:
                        if fnmatch.fnmatch(fp.lower(), pat.lower()):
                            filtered.append(fp)
                            break
                file_paths = filtered

            if not file_paths:
                stats.errors.append(f"No files found in {doc_dir}")
                return stats

            stats.total_documents = len(file_paths)
            logger.info("Found %d documents to import", len(file_paths))

            # 逐文件处理
            all_chunks: list[dict] = []
            for idx, fp in enumerate(file_paths):
                try:
                    self._report(progress_cb, f"parsing {os.path.basename(fp)}",
                                 (idx / len(file_paths)) * 40)

                    chunks = await importer.parse_and_chunk(
                        fp,
                        chunk_size=chunk_size,
                        chunk_overlap=chunk_overlap,
                    )
                    all_chunks.extend(chunks)
                    logger.debug("  %s → %d chunks", os.path.basename(fp), len(chunks))
                except Exception as e:
                    logger.warning("Failed to parse %s: %s", fp, e)
                    stats.errors.append(f"Parse error: {fp}: {e}")

            stats.total_chunks = len(all_chunks)
            if not all_chunks:
                stats.errors.append("No chunks produced from any document")
                return stats

            # 嵌入 + 存储
            self._report(progress_cb, "embedding", 50)
            await self._embed_and_store(kb, all_chunks, progress_cb, stats)

        except Exception as e:
            logger.exception("File import failed")
            stats.errors.append(str(e))

        stats.duration_sec = time.monotonic() - start
        self._report(progress_cb, "done", 100)
        logger.info("File import complete: %s", stats)
        return stats

    # ── 内部方法 ────────────────────────────────────────────

    async def _get_or_create_kb(
        self,
        name: str,
        description: str = "",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ) -> KBInstance:
        """获取或创建知识库"""
        existing = await self._kb_mgr.get_by_name(name)
        if existing:
            logger.info("Using existing KB: %s", name)
            return existing

        kb = await self._kb_mgr.create(
            name=name,
            description=description,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        return kb

    async def _embed_and_store(
        self,
        kb: KBInstance,
        chunks: list[dict],
        progress_cb: Optional[ProgressHandler],
        stats: ImportStats,
    ) -> None:
        """批量嵌入 + 存储到主项目 KB"""
        if not kb.storage:
            raise ValueError(f"KB {kb.name} storage not initialized")

        embed_dim = self._embedder.get_dim()
        logger.info("Embedding %d chunks (dim=%d)...", len(chunks), embed_dim)

        # 分批嵌入
        batch_size = self._config.embed_batch_size
        total_embedded = 0

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            texts = [c["text"] for c in batch]

            try:
                embeddings = await self._embedder.embed_batch(texts)
                kb.storage.add_chunks(batch, embeddings)
                total_embedded += len(batch)
            except Exception as e:
                logger.error("Embed batch %d failed: %s", i // batch_size, e)
                stats.errors.append(f"Embed error batch {i // batch_size}: {e}")
                continue

            if progress_cb:
                pct = 50 + (i / max(len(chunks), 1)) * 45
                self._report(progress_cb, "embedding", pct)

        stats.total_embedded = total_embedded

        # 同步元数据统计
        from app.core.rag.kb_store import get_kb_store
        store = get_kb_store()
        doc_count = await store.count_documents_by_kb(kb.kb_id)
        chunk_count = kb.storage.count()
        await store.update_kb_stats(kb.kb_id, doc_count, chunk_count)

        logger.info("Stored %d/%d chunks into KB '%s'",
                     total_embedded, len(chunks), kb.name)

    async def _re_chunk_and_embed(
        self,
        kb: KBInstance,
        dify_chunks: list[DifyChunk],
        chunk_size: int,
        chunk_overlap: int,
        progress_cb: Optional[ProgressHandler],
        stats: ImportStats,
    ) -> None:
        """重新分块后再嵌入（当 Dify 分块不满足需求时）"""
        # 合并所有文本
        full_text = "\n\n".join(c.text for c in dify_chunks)

        chunker = get_chunker(
            strategy="recursive",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        source = dify_chunks[0].dataset_name if dify_chunks else "dify"
        new_chunks = chunker.chunk(full_text, metadata={"source": f"dify:{source}"})

        logger.info("Re-chunked: %d → %d chunks", len(dify_chunks), len(new_chunks))
        stats.total_chunks = len(new_chunks)

        self._report(progress_cb, "embedding", 50)
        await self._embed_and_store(kb, new_chunks, progress_cb, stats)

    @staticmethod
    def _report(cb: Optional[ProgressHandler], stage: str, pct: float):
        if cb:
            try:
                cb(stage, pct)
            except Exception:
                pass


# ── 便捷函数 ──────────────────────────────────────────────


async def import_dify_to_kb(
    kb_name: str,
    doc_dir: str = "knowledge-data/documents/",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    progress_cb: Optional[ProgressHandler] = None,
) -> ImportStats:
    """
    一行导入：将 Dify 训练目录的文档导入主项目知识库

    这是最推荐的使用方式，直接读取 knowledge-data/documents/ 下的原始文件。

    Usage:
        stats = await import_dify_to_kb("我的知识库")
        print(f"Imported {stats.total_chunks} chunks")
    """
    bridge = DifyKnowledgeBridge()
    return await bridge.import_from_files(
        kb_name=kb_name,
        doc_dir=doc_dir,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        progress_cb=progress_cb,
    )
