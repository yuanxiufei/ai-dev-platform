"""
知识库管理器 v2 — 完整 KB 生命周期 + 持久化

借鉴 AstrBot KnowledgeBaseManager + KBHelper:
- SQLite 元数据持久化 (kb_store)
- 多 KB 联合检索 + 格式化上下文
- URL 上传 + LLM 文本修复
- 文档级追踪 (KBDocument/KBMedia)
- 进度回调
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.rag.kb_store import KBSQLiteStore, get_kb_store
from app.core.rag.models import KnowledgeBase as KBModel, KBDocument, KBMedia
from app.core.rag.embedder import get_embedding_provider
from app.core.rag.retrieval_manager import get_retrieval_manager
from app.core.rag.vector_store import HybridStorage
from app.core.rag.parsers import select_parser, select_parser as discover_parser
from app.core.rag.chunking import get_chunker
from app.core.rag.kb_repair import repair_chunk_with_retry, should_repair
from app.core.rag.config import get_rag_config

logger = logging.getLogger("app.core.rag.kb_manager")

ProgressHandler = Callable[[str, float], None]


@dataclass
class KBInstance:
    """知识库运行时实例"""
    model: KBModel
    storage: Optional[HybridStorage] = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def kb_id(self) -> str:
        return self.model.kb_id

    @property
    def name(self) -> str:
        return self.model.kb_name


class KnowledgeBaseManagerV2:
    """
    知识库管理器 v2

    Usage:
        mgr = KnowledgeBaseManagerV2(store)
        await mgr.initialize()
        kb = await mgr.create("my_kb", "技术文档")
        await mgr.upload_file(kb_id=kb.kb_id, filepath="doc.pdf")
        results = await mgr.retrieve(query="如何使用？", kb_names=["my_kb"])
    """

    def __init__(
        self,
        store: Optional[KBSQLiteStore] = None,
        repair_llm: Optional[callable] = None,
    ):
        self._store = store or get_kb_store()
        self._config = get_rag_config()
        self._embedder = get_embedding_provider()
        self._retriever = get_retrieval_manager()
        self._instances: dict[str, KBInstance] = {}
        self._repair_llm = repair_llm  # async (system_prompt, user_prompt) -> str

    # ── 生命周期 ────────────────────────────────

    async def initialize(self) -> None:
        """初始化存储并加载已有 KB"""
        await self._store.initialize()
        await self._load_kbs()
        os.makedirs(self._config.kb_dir, exist_ok=True)

    async def _load_kbs(self) -> None:
        """从数据库加载所有 KB 为运行时实例"""
        kbs = await self._store.list_kbs()
        for kb_model in kbs:
            inst = KBInstance(model=kb_model)
            # 初始化向量存储
            kb_path = os.path.join(self._config.kb_dir, kb_model.kb_id)
            inst.storage = HybridStorage(kb_path, self._embedder.get_dim())
            self._instances[kb_model.kb_id] = inst
        logger.info("Loaded %d knowledge bases from store", len(kbs))

    async def terminate(self) -> None:
        """优雅关闭"""
        for inst in self._instances.values():
            if inst.storage:
                inst.storage.close()
        self._instances.clear()
        await self._store.close()

    # ── KB CRUD ────────────────────────────────

    async def create(
        self,
        name: str,
        description: str = "",
        emoji: str = "",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        top_k_dense: int = 50,
        top_k_sparse: int = 50,
        top_m_final: int = 5,
    ) -> KBInstance:
        """创建新知识库"""
        # 检查重名
        existing = await self._store.get_kb_by_name(name)
        if existing:
            raise ValueError(f"Knowledge base '{name}' already exists")

        model = KBModel(
            kb_name=name,
            description=description,
            emoji=emoji,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k_dense=top_k_dense,
            top_k_sparse=top_k_sparse,
            top_m_final=top_m_final,
        )
        model = await self._store.create_kb(model)

        inst = KBInstance(model=model)
        kb_path = os.path.join(self._config.kb_dir, model.kb_id)
        inst.storage = HybridStorage(kb_path, self._embedder.get_dim())
        self._instances[model.kb_id] = inst

        logger.info("Created KB: %s (id=%s)", name, model.kb_id)
        return inst

    def get(self, kb_id: str) -> Optional[KBInstance]:
        return self._instances.get(kb_id)

    async def get_by_name(self, name: str) -> Optional[KBInstance]:
        model = await self._store.get_kb_by_name(name)
        if model and model.kb_id in self._instances:
            return self._instances[model.kb_id]
        return None

    async def list_all(self) -> list[KBInstance]:
        return list(self._instances.values())

    async def delete(self, kb_id: str) -> None:
        inst = self._instances.pop(kb_id, None)
        if inst:
            if inst.storage:
                inst.storage.clear()
                inst.storage.close()
            await self._store.delete_kb(kb_id)
            logger.info("Deleted KB: %s", kb_id)

    async def update(self, kb_id: str, **kwargs) -> KBInstance:
        """更新 KB 配置"""
        inst = self._instances.get(kb_id)
        if not inst:
            raise ValueError(f"KB not found: {kb_id}")
        for k, v in kwargs.items():
            if hasattr(inst.model, k):
                setattr(inst.model, k, v)
        inst.model = await self._store.update_kb(inst.model)
        return inst

    # ── 文档上传 ────────────────────────────────

    async def upload_file(
        self,
        kb_id: str,
        filepath: str,
        progress_callback: Optional[ProgressHandler] = None,
        repair: bool = True,
    ) -> int:
        """上传文档到知识库 (解析 → 清洗 → 分块 → 嵌入 → 存储)"""
        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            raise ValueError(f"KB {kb_id} not found or not initialized")

        async with inst._lock:
            self._report(progress_callback, "parsing", 5)

            # 1. 选择解析器
            parser = discover_parser(filepath)
            if parser is None:
                raise ValueError(f"No parser for: {filepath}")

            # 判断是否是 URL
            url_mode = filepath.startswith("http://") or filepath.startswith("https://")
            file_name = os.path.basename(filepath) if not url_mode else filepath
            file_ext = os.path.splitext(file_name)[1].lower() if not url_mode else "url"
            file_size = os.path.getsize(filepath) if not url_mode and os.path.isfile(filepath) else 0

            logger.debug("Parsing %s with %s", file_name, parser.name)
            parsed = await parser.parse(filepath)

            self._report(progress_callback, "chunking", 30)

            # 2. 可选 LLM 文本修复
            raw_text = parsed.text
            if repair and self._repair_llm and should_repair(raw_text):
                self._report(progress_callback, "repairing", 35)
                try:
                    repaired_list = await repair_chunk_with_retry(
                        raw_text, self._repair_llm,
                    )
                    if repaired_list:
                        raw_text = "\n\n".join(repaired_list)
                        logger.debug("Repaired text: %d chars → %d chars",
                                     len(parsed.text), len(raw_text))
                except Exception as e:
                    logger.warning("Text repair failed: %s", e)

            # 3. 分块
            # Markdown 文件用 MarkdownChunker
            strategy = inst.model.chunk_size
            chunk_size = inst.model.chunk_size
            chunk_overlap = inst.model.chunk_overlap

            # 检测是否为 Markdown
            if file_ext in (".md", ".markdown", ".rst", ".adoc"):
                strategy = "markdown"

            chunker = get_chunker(
                strategy=strategy,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            chunks = chunker.chunk(
                raw_text,
                metadata={
                    "source": filepath,
                    "title": parsed.title or file_name,
                    "parser": parser.name,
                    **parsed.metadata,
                },
            )

            if not chunks:
                logger.warning("No chunks from: %s", filepath)
                return 0

            self._report(progress_callback, "embedding", 50)

            # 4. Embedding
            texts = [c["text"] for c in chunks]
            embeddings = await self._embedder.embed_batch(texts)

            self._report(progress_callback, "indexing", 85)

            # 5. 写入向量存储
            inst.storage.add_chunks(chunks, embeddings)

            # 6. 创建文档记录
            doc = KBDocument(
                kb_id=kb_id,
                doc_name=parsed.title or file_name,
                file_type=file_ext,
                file_size=file_size,
                file_path=filepath,
                chunk_count=len(chunks),
                media_count=len(parsed.images) if parsed.images else 0,
            )
            doc = await self._store.create_document(doc)

            # 7. 保存媒体文件
            if parsed.images:
                await self._save_media(inst, doc.doc_id, parsed.images, file_name)

            # 8. 更新统计
            await self._sync_stats(kb_id)

            self._report(progress_callback, "done", 100)

            logger.info("Uploaded %s → %d chunks (KB: %s, doc: %s)",
                         file_name, len(chunks), inst.name, doc.doc_id)
            return len(chunks)

    async def upload_text(
        self,
        kb_id: str,
        text: str,
        title: str = "",
        metadata: Optional[dict] = None,
    ) -> int:
        """直接上传文本"""
        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            raise ValueError(f"KB {kb_id} not found")

        chunker = get_chunker(
            strategy="recursive",
            chunk_size=inst.model.chunk_size,
            chunk_overlap=inst.model.chunk_overlap,
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
        inst.storage.add_chunks(chunks, embeddings)

        doc = KBDocument(
            kb_id=kb_id,
            doc_name=title or "text_input",
            file_type="text",
            file_size=len(text),
            chunk_count=len(chunks),
        )
        await self._store.create_document(doc)
        await self._sync_stats(kb_id)

        logger.info("Text uploaded: %d chunks (KB: %s)", len(chunks), inst.name)
        return len(chunks)

    # ── 检索 ────────────────────────────────

    async def retrieve(
        self,
        query: str,
        kb_names: Optional[list[str]] = None,
        kb_ids: Optional[list[str]] = None,
        top_k_fusion: int = 20,
        top_m_final: int = 5,
    ) -> dict:
        """
        跨多知识库检索

        Returns:
            {"context_text": str, "results": list[dict]}
        """
        targets: dict[str, HybridStorage] = {}

        if kb_ids:
            for kid in kb_ids:
                inst = self._instances.get(kid)
                if inst and inst.storage:
                    targets[inst.name] = inst.storage

        if kb_names:
            for name in kb_names:
                inst = await self.get_by_name(name)
                if inst and inst.storage:
                    targets[name] = inst.storage

        if not targets:
            return {"context_text": "", "results": []}

        results = await self._retriever.search_multi(
            query, targets, top_k=top_m_final,
        )
        context_text = self._format_context(results)

        return {
            "context_text": context_text,
            "results": results,
        }

    # ── 文档管理 ────────────────────────────────

    async def list_documents(self, kb_id: str) -> list[KBDocument]:
        return await self._store.list_documents_by_kb(kb_id)

    async def delete_document(self, kb_id: str, doc_id: str) -> None:
        inst = self._instances.get(kb_id)
        doc = await self._store.get_document_by_id(doc_id)
        if doc and inst and inst.storage:
            # 从向量存储中移除该文档的 chunks
            inst.storage.delete_by_metadata({"source": doc.file_path})
            inst.storage.delete_by_metadata({"doc_id": doc.doc_id})

        await self._store.delete_document_by_id(doc_id)
        await self._sync_stats(kb_id)

    # ── 工具方法 ────────────────────────────────

    @staticmethod
    def _format_context(results: list[dict]) -> str:
        """将检索结果格式化为上下文文本"""
        if not results:
            return ""
        lines = ["## Retrieved Knowledge\n"]
        for i, r in enumerate(results, 1):
            src = r.get("metadata", {}).get("source", "unknown")
            text = r.get("text", "").strip()
            lines.append(f"**[{i}]** (source: {src})")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)

    async def _save_media(
        self,
        inst: KBInstance,
        doc_id: str,
        images: list[bytes],
        file_name: str,
    ) -> None:
        """保存文档中的多媒体资源"""
        kb_dir = os.path.join(self._config.kb_dir, inst.model.kb_id)
        media_dir = os.path.join(kb_dir, "media")
        os.makedirs(media_dir, exist_ok=True)

        for i, img_data in enumerate(images):
            ext = self._detect_image_format(img_data)
            media_name = f"{file_name}_{i}.{ext}"
            media_path = os.path.join(media_dir, media_name)

            with open(media_path, "wb") as f:
                f.write(img_data)

            media = KBMedia(
                doc_id=doc_id,
                kb_id=inst.model.kb_id,
                media_type="image",
                file_name=media_name,
                file_path=media_path,
                file_size=len(img_data),
                mime_type=f"image/{ext}",
            )
            await self._store.create_media(media)

    @staticmethod
    def _detect_image_format(data: bytes) -> str:
        if data[:4] == b"\x89PNG":
            return "png"
        if data[:2] == b"\xff\xd8":
            return "jpg"
        if data[:4] == b"GIF8":
            return "gif"
        if data[:4] == b"RIFF":
            return "webp"
        return "png"

    async def _sync_stats(self, kb_id: str) -> None:
        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            return
        doc_count = await self._store.count_documents_by_kb(kb_id)
        chunk_count = inst.storage.count()
        await self._store.update_kb_stats(kb_id, doc_count, chunk_count)
        inst.model.doc_count = doc_count
        inst.model.chunk_count = chunk_count

    @staticmethod
    def _report(cb: Optional[ProgressHandler], stage: str, pct: float):
        if cb:
            try:
                cb(stage, pct)
            except Exception:
                pass


# ── 全局单例 ─────────────────────────────────

_global_kb_manager_v2: Optional[KnowledgeBaseManagerV2] = None


def init_kb_manager_v2(store: Optional[KBSQLiteStore] = None) -> KnowledgeBaseManagerV2:
    global _global_kb_manager_v2
    _global_kb_manager_v2 = KnowledgeBaseManagerV2(store=store)
    return _global_kb_manager_v2


def get_kb_manager_v2() -> KnowledgeBaseManagerV2:
    if _global_kb_manager_v2 is None:
        return init_kb_manager_v2()
    return _global_kb_manager_v2
