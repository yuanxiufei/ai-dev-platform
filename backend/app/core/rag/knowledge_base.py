"""
知识库管理器 — 多 KB 生命周期管理

借鉴 AstrBot KnowledgeBaseManager:
- 全局单例，管理多个知识库实例
- 文档上传全流程: 解析 → 分块 → 嵌入 → 索引
- 每个 KB 独立的 SegmentManager (FAISS + tsvector)
- 进度追踪 + 错误恢复
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from app.core.rag.config import get_rag_config
from app.core.rag.chunking import get_chunker
from app.core.rag.embedder import get_embedding_provider
from app.core.rag.filters import build_filter_chain
from app.core.rag.kb_store import get_kb_store  # 元数据持久化 (kb_documents 表)
from app.core.rag.parsers import select_parser, ParseResult
from app.core.rag.retrieval_manager import get_retrieval_manager
from app.core.rag.segments import SegmentManager

logger = logging.getLogger("app.core.rag.knowledge_base")

ErrorHandler = Callable[[str, Exception], None]
ProgressHandler = Callable[[str, float], None]  # (stage, progress 0-100)


@dataclass
class KnowledgeBase:
    """单个知识库数据

    storage 统一使用 SegmentManager (Phase 3 Segment 抽象层)。
    它内部编排 Metadata/Vector/Record 三个 Segment 后端，
    提供与 SegmentManager 兼容的检索接口。
    """
    name: str
    kb_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    chunk_strategy: str = "recursive"
    chunk_size: int = 1024
    chunk_overlap: int = 200
    storage: Optional[SegmentManager] = None
    doc_count: int = 0
    chunk_count: int = 0
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            from datetime import datetime
            self.created_at = datetime.now().isoformat()

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "kb_id": self.kb_id,
            "description": self.description,
            "chunk_count": self.chunk_count,
            "doc_count": self.doc_count,
            "vector_count": self.storage.count() if self.storage else 0,
            "strategy": self.chunk_strategy,
            "segment_stats": self.storage.stats if self.storage else {},
        }


class KnowledgeBaseManager:
    """
    知识库管理器

    Usage:
        mgr = KnowledgeBaseManager()
        kb = await mgr.create("my_kb", description="技术文档")
        await mgr.upload_file(kb, "path/to/doc.pdf")
        results = await mgr.query(kb, "如何使用？", top_k=5)
    """

    def __init__(self):
        self._config = get_rag_config()
        self._kbs: dict[str, KnowledgeBase] = {}
        self._embedder = get_embedding_provider()
        self._retriever = get_retrieval_manager()
        os.makedirs(self._config.kb_dir, exist_ok=True)
        # psycopg 同步 PG DSN, 传给 MetadataSegment
        from app.core.config import settings as _app_settings
        self._pg_dsn = _app_settings.PG_DSN

    # ── KB CRUD ─────────────────────────────────────────

    async def create(
        self,
        name: str,
        description: str = "",
        chunk_strategy: str = "recursive",
        chunk_size: int = 1024,
        chunk_overlap: int = 200,
    ) -> KnowledgeBase:
        """创建新知识库"""
        kb = KnowledgeBase(
            name=name,
            description=description,
            chunk_strategy=chunk_strategy,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        # 初始化 Segment 抽象层存储 (Phase 3)
        # get_dim() 可能触发模型加载，放在 to_thread 中避免阻塞事件循环
        kb_path = os.path.join(self._config.kb_dir, kb.kb_id)
        dim = await asyncio.to_thread(self._embedder.get_dim)
        kb.storage = SegmentManager(kb_path=kb_path, dim=dim, pg_dsn=self._pg_dsn)

        self._kbs[kb.kb_id] = kb

        # 持久化知识库元数据到 SQLite/PostgreSQL (kb_store)
        try:
            _store = get_kb_store()
            await _store.create_kb(
                kb_id=kb.kb_id,
                name=name,
                description=description,
                chunk_strategy=chunk_strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            logger.debug("KB record persisted: %s (id=%s)", name, kb.kb_id)
        except RuntimeError:
            logger.warning("KB store not initialized, skipping KB record persistence")
        except Exception as e:
            logger.error("Failed to persist KB record %s: %s", kb.kb_id, e)

        logger.info("Knowledge base created: %s (id=%s, dim=%d)",
                     name, kb.kb_id, kb.storage.dim)
        return kb

    def get(self, kb_id: str) -> Optional[KnowledgeBase]:
        return self._kbs.get(kb_id)

    def get_by_name(self, name: str) -> Optional[KnowledgeBase]:
        for kb in self._kbs.values():
            if kb.name == name:
                return kb
        return None

    def list_all(self) -> list[KnowledgeBase]:
        return list(self._kbs.values())

    async def delete(self, kb_id: str) -> bool:
        """删除知识库及其所有索引，返回是否找到并删除"""
        kb = self._kbs.pop(kb_id, None)
        if kb is None:
            # 内存中没有，尝试从持久化存储删除
            try:
                _store = get_kb_store()
                await _store.delete_kb(kb_id)
            except Exception:
                pass
            return False
        if kb.storage:
            kb.storage.clear()
        # 同步删除持久化记录
        try:
            _store = get_kb_store()
            await _store.delete_kb(kb_id)
        except RuntimeError:
            pass
        except Exception as e:
            logger.error("Failed to delete KB record %s from store: %s", kb_id, e)
        logger.info("Knowledge base deleted: %s", kb_id)
        return True

    # ── 文档上传 ─────────────────────────────────────────

    def _build_context_header(
        self, title: str = "", source: str = "", doc_type: str = ""
    ) -> Optional[str]:
        """构建 chunkHeader 上下文头（借鉴 AnythingLLM chunkHeader）

        格式: "[Document: {title}]\n[Source: {source}]\n[Date: {date}]"
        注入到每个 chunk 文本前，让向量检索可感知文档来源。
        """
        parts = []
        if title:
            parts.append(f"[Document: {title}]")
        if source:
            parts.append(f"[Source: {source}]")
        if doc_type:
            parts.append(f"[Type: {doc_type}]")
        # 始终附加日期（检索时上下文时效性参考）
        parts.append(f"[Date: {datetime.now().strftime('%Y-%m-%d')}]")
        return "\n".join(parts) if parts else None

    async def upload_file(
        self,
        kb: KnowledgeBase,
        filepath: str,
        progress_callback: Optional[ProgressHandler] = None,
    ) -> int:
        """
        上传文档到知识库

        全流程:
          1. 选择解析器 → 解析文档
          2. 选择分块器 → 文本分块 (注入 chunkHeader)
          3. Embedding → 向量化
          4. 写入 SegmentManager (FAISS + tsvector)
        """
        if not kb.storage:
            raise RuntimeError(f"KB '{kb.name}' has no storage initialized")

        # 1. 解析
        self._report_progress(progress_callback, "parsing", 10)
        parser = select_parser(filepath)
        if parser is None:
            raise ValueError(f"No parser available for: {filepath}")

        logger.info("Parsing %s with %s", os.path.basename(filepath), parser.name)
        parsed = await parser.parse(filepath)

        # 1.5. Text filtering (借鉴 obsidian-clipper filter chain)
        self._report_progress(progress_callback, "filtering", 20)
        parsed = self._apply_text_filters(parsed)

        self._report_progress(progress_callback, "chunking", 30)

        # 2. 分块 — 注入 chunkHeader 上下文
        context_header = self._build_context_header(
            title=parsed.title or os.path.basename(filepath),
            source=filepath,
            doc_type="file",
        )
        chunker = get_chunker(
            strategy=kb.chunk_strategy,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
            context_header=context_header,
            embedder=self._embedder,  # 自适应 token 预算
        )
        chunk_metadata = {
            "source": filepath,
            "title": parsed.title,
            "parser": parser.name,
            **parsed.metadata,
        }

        # LazyImage (Phase 2): 将图片引用注入 chunk 元数据
        # 检索命中时可懒加载图片，避免解析阶段全量加载到内存
        if parsed.image_refs:
            chunk_metadata["_image_refs"] = [
                ref.to_dict() for ref in parsed.image_refs
            ]
            logger.debug("Injected %d image refs into chunk metadata", len(parsed.image_refs))

        chunks = chunker.chunk(parsed.text, metadata=chunk_metadata)

        if not chunks:
            logger.warning("No chunks extracted from: %s", filepath)
            return 0

        self._report_progress(progress_callback, "embedding", 50)

        # 3. Embedding
        texts = [c["text"] for c in chunks]
        embeddings = await self._embedder.embed_batch(
            texts,
            progress_callback=lambda done, total: self._report_progress(
                progress_callback, "embedding",
                50 + int(40 * done / total) if total else 90,
            ),
        )

        self._report_progress(progress_callback, "indexing", 90)

        # 4. 写入存储
        kb.storage.add_chunks(chunks, embeddings)
        kb.chunk_count += len(chunks)
        kb.doc_count += 1

        # 5. 持久化文档记录到 kb_documents 表
        try:
            _store = get_kb_store()
            await _store.create_doc(
                kb_id=kb.kb_id,
                doc_name=os.path.basename(filepath),
                file_path=filepath,
                file_type=os.path.splitext(filepath)[1].lstrip(".") or "text",
                chunk_count=len(chunks),
                embedding_status="completed",
            )
            logger.debug("Document record created: %s (kb=%s)", os.path.basename(filepath), kb.kb_id)
        except RuntimeError:
            logger.warning("KB store not initialized, skipping doc record creation")
        except Exception as e:
            logger.error("Failed to create doc record for %s: %s", os.path.basename(filepath), e)

        self._report_progress(progress_callback, "done", 100)

        logger.info("Uploaded: %s → %d chunks (KB: %s)",
                     os.path.basename(filepath), len(chunks), kb.name)
        return len(chunks)

    async def upload_text(
        self,
        kb: KnowledgeBase,
        text: str,
        title: str = "",
        metadata: Optional[dict] = None,
    ) -> int:
        """直接上传文本"""
        if not kb.storage:
            raise RuntimeError(f"KB '{kb.name}' has no storage initialized")

        context_header = self._build_context_header(
            title=title or "Text",
            source="text",
            doc_type="text",
        )
        chunker = get_chunker(
            strategy=kb.chunk_strategy,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
            context_header=context_header,
            embedder=self._embedder,
        )
        chunks = chunker.chunk(text, metadata={
            "source": "text",
            "title": title,
            **(metadata or {}),
        })

        if not chunks:
            return 0

        texts = [c["text"] for c in chunks]
        embeddings = await self._embedder.embed_batch(texts)
        kb.storage.add_chunks(chunks, embeddings)
        kb.chunk_count += len(chunks)
        kb.doc_count += 1

        # 持久化文档记录到 kb_documents 表
        try:
            _store = get_kb_store()
            await _store.create_doc(
                kb_id=kb.kb_id,
                doc_name=title or "Text",
                file_path="text:inline",
                file_type="text",
                chunk_count=len(chunks),
                embedding_status="completed",
            )
        except RuntimeError:
            logger.warning("KB store not initialized, skipping doc record creation")
        except Exception as e:
            logger.error("Failed to create doc record for text: %s", e)

        logger.info("Text uploaded: %d chunks (KB: %s)", len(chunks), kb.name)
        return len(chunks)

    async def upload_url(
        self,
        kb: KnowledgeBase,
        url: str,
        title: str = "",
        progress_callback: Optional[ProgressHandler] = None,
    ) -> int:
        """上传 URL 页面内容到知识库

        全流程与 upload_file 一致: URL 解析 → 过滤 → 分块 → 嵌入 → 索引
        """
        if not kb.storage:
            raise RuntimeError(f"KB '{kb.name}' has no storage initialized")

        self._report_progress(progress_callback, "fetching", 10)

        # 1. URL 解析
        parser = select_parser(url)
        if parser is None:
            raise ValueError(f"No parser available for URL: {url}")

        logger.info("Fetching URL %s with %s", url, parser.name)
        parsed = await parser.parse(url)

        # 2. 过滤
        self._report_progress(progress_callback, "filtering", 20)
        parsed = self._apply_text_filters(parsed)

        # 3. 分块 — 注入 chunkHeader 上下文
        self._report_progress(progress_callback, "chunking", 30)
        context_header = self._build_context_header(
            title=title or parsed.title or url,
            source=url,
            doc_type="url",
        )
        chunker = get_chunker(
            strategy=kb.chunk_strategy,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
            context_header=context_header,
            embedder=self._embedder,
        )
        chunks = chunker.chunk(parsed.text, metadata={
            "source": url,
            "title": title or parsed.title,
            "parser": parser.name,
            "doc_type": "url",
            **parsed.metadata,
        })

        if not chunks:
            logger.warning("No chunks extracted from URL: %s", url)
            return 0

        # 4. Embedding
        self._report_progress(progress_callback, "embedding", 50)
        texts = [c["text"] for c in chunks]
        embeddings = await self._embedder.embed_batch(texts)

        # 5. 写入存储
        self._report_progress(progress_callback, "indexing", 90)
        kb.storage.add_chunks(chunks, embeddings)
        kb.chunk_count += len(chunks)
        kb.doc_count += 1

        # 6. 持久化文档记录到 kb_documents 表
        try:
            _store = get_kb_store()
            await _store.create_doc(
                kb_id=kb.kb_id,
                doc_name=title or parsed.title or url,
                file_path=url,
                file_type="url",
                chunk_count=len(chunks),
                embedding_status="completed",
            )
        except RuntimeError:
            logger.warning("KB store not initialized, skipping doc record creation")
        except Exception as e:
            logger.error("Failed to create doc record for %s: %s", url, e)

        self._report_progress(progress_callback, "done", 100)
        logger.info("URL uploaded: %s → %d chunks (KB: %s)", url, len(chunks), kb.name)
        return len(chunks)

    # ── 查询 ────────────────────────────────────────────

    async def query(
        self,
        kb: KnowledgeBase,
        query: str,
        top_k: int = 5,
        filter_dict: dict | None = None,
    ) -> list[dict]:
        """查询知识库（混合检索），支持 WhereFilter 元数据过滤"""
        if not kb.storage:
            return []
        return await self._retriever.search(
            query, kb.storage, top_k=top_k, filter_dict=filter_dict,
        )

    async def query_multi(
        self,
        kb_ids: list[str],
        query: str,
        top_k: int = 5,
        filter_dict: dict | None = None,
    ) -> list[dict]:
        """跨多知识库检索，支持 WhereFilter 元数据过滤"""
        storages = {}
        for kid in kb_ids:
            kb = self._kbs.get(kid)
            if kb and kb.storage:
                storages[kb.name] = kb.storage
        return await self._retriever.search_multi(
            query, storages, top_k=top_k, filter_dict=filter_dict,
        )

    # ── 工具 ────────────────────────────────────────────

    def _apply_text_filters(self, parsed: ParseResult) -> ParseResult:
        """
        应用文本过滤链 (借鉴 obsidian-clipper filter chain)

        使用 RAGConfig.text_filter_names 中配置的过滤器列表
        """
        config = self._config
        if not config.text_filter_enabled or not config.text_filter_names:
            return parsed

        try:
            chain = build_filter_chain(config.text_filter_names)
            # 对 HTML 来源的文本使用更强的 sanitize
            is_html = parsed.metadata.get("method") == "http"
            kwargs = {}
            if is_html and config.html_sanitizer_enabled:
                kwargs["sanitize_level"] = config.html_sanitizer_level

            parsed.text = chain.apply(parsed.text, **kwargs)
            logger.debug(
                "Text filter chain applied (%d filters, is_html=%s)",
                len(chain.filters), is_html,
            )
        except Exception as e:
            logger.warning("Text filter chain failed, using raw text: %s", e)

        return parsed

    @staticmethod
    def _report_progress(
        cb: Optional[ProgressHandler], stage: str, progress: float,
    ):
        if cb:
            try:
                cb(stage, progress)
            except Exception:
                pass


# ── 全局单例 ──────────────────────────────────────────────

_global_kb_manager: Optional[KnowledgeBaseManager] = None


def init_knowledge_base() -> KnowledgeBaseManager:
    global _global_kb_manager
    _global_kb_manager = KnowledgeBaseManager()
    return _global_kb_manager


def get_knowledge_base() -> KnowledgeBaseManager:
    if _global_kb_manager is None:
        return init_knowledge_base()
    return _global_kb_manager
