"""
知识库管理器 — 多 KB 生命周期管理

借鉴 AstrBot KnowledgeBaseManager:
- 全局单例，管理多个知识库实例
- 文档上传全流程: 解析 → 分块 → 嵌入 → 索引
- 每个 KB 独立的 HybridStorage (FAISS + FTS5)
- 进度追踪 + 错误恢复
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.rag.config import get_rag_config
from app.core.rag.chunking import get_chunker
from app.core.rag.embedder import get_embedding_provider
from app.core.rag.filters import build_filter_chain
from app.core.rag.parsers import select_parser, ParseResult
from app.core.rag.retrieval_manager import get_retrieval_manager
from app.core.rag.vector_store import HybridStorage

logger = logging.getLogger("app.core.rag.knowledge_base")

ErrorHandler = Callable[[str, Exception], None]
ProgressHandler = Callable[[str, float], None]  # (stage, progress 0-100)


@dataclass
class KnowledgeBase:
    """单个知识库数据"""
    name: str
    kb_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    chunk_strategy: str = "recursive"
    chunk_size: int = 1024
    chunk_overlap: int = 200
    storage: Optional[HybridStorage] = None
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

        # 初始化存储
        kb_path = os.path.join(self._config.kb_dir, kb.kb_id)
        kb.storage = HybridStorage(kb_path, self._embedder.get_dim())

        self._kbs[kb.kb_id] = kb
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

    def delete(self, kb_id: str):
        kb = self._kbs.pop(kb_id, None)
        if kb and kb.storage:
            kb.storage.clear()
        logger.info("Knowledge base deleted: %s", kb_id)

    # ── 文档上传 ─────────────────────────────────────────

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
          2. 选择分块器 → 文本分块
          3. Embedding → 向量化
          4. 写入 HybridStorage (FAISS + FTS5)
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

        # 2. 分块
        chunker = get_chunker(
            strategy=kb.chunk_strategy,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
        )
        chunks = chunker.chunk(
            parsed.text,
            metadata={
                "source": filepath,
                "title": parsed.title,
                "parser": parser.name,
                **parsed.metadata,
            },
        )

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

        chunker = get_chunker(
            strategy=kb.chunk_strategy,
            chunk_size=kb.chunk_size,
            chunk_overlap=kb.chunk_overlap,
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

        logger.info("Text uploaded: %d chunks (KB: %s)", len(chunks), kb.name)
        return len(chunks)

    # ── 查询 ────────────────────────────────────────────

    async def query(
        self,
        kb: KnowledgeBase,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """查询知识库（混合检索）"""
        if not kb.storage:
            return []
        return await self._retriever.search(
            query, kb.storage, top_k=top_k,
        )

    async def query_multi(
        self,
        kb_ids: list[str],
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """跨多知识库检索"""
        storages = {}
        for kid in kb_ids:
            kb = self._kbs.get(kid)
            if kb and kb.storage:
                storages[kb.name] = kb.storage
        return await self._retriever.search_multi(query, storages, top_k=top_k)

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
