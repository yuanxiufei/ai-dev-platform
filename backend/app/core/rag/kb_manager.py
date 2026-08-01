"""
知识库管理器 v2 — 完整 KB 生命周期 + 持久化

借鉴 AstrBot KnowledgeBaseManager + KBHelper:
- PostgreSQL 元数据持久化 (kb_store)
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

from app.core.rag.kb_store import KBPGStore, KBSQLiteStore, get_kb_store
from app.core.rag.models import KnowledgeBase as KBModel, KBDocument, KBMedia, KBJob
from app.core.rag.embedder import get_embedding_provider
from app.core.rag.retrieval_manager import get_retrieval_manager
from app.core.rag.segments import SegmentManager
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
    storage: Optional[SegmentManager] = None
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
        store: Optional[KBPGStore] = None,
        repair_llm: Optional[callable] = None,
        pg_dsn: str = "",
    ):
        self._store = store or get_kb_store()
        self._config = get_rag_config()
        self._embedder = get_embedding_provider()
        self._retriever = get_retrieval_manager()
        self._instances: dict[str, KBInstance] = {}
        self._repair_llm = repair_llm  # async (system_prompt, user_prompt) -> str
        # psycopg 同步 PG DSN（MetadataSegment 直接连接用）
        if pg_dsn:
            self._pg_dsn = pg_dsn
        else:
            from app.core.config import settings as _app_settings
            self._pg_dsn = _app_settings.PG_DSN

    # ── 生命周期 ────────────────────────────────

    async def initialize(self) -> None:
        """初始化存储并加载已有 KB"""
        await self._store.initialize()
        await self._load_kbs()
        os.makedirs(self._config.kb_dir, exist_ok=True)

    async def _load_kbs(self) -> None:
        """从数据库加载所有 KB 为运行时实例"""
        kbs = await self._store.list_kbs()
        if not kbs:
            return
        dim = await asyncio.to_thread(self._embedder.get_dim)
        for kb_model in kbs:
            inst = KBInstance(model=kb_model)
            # 初始化向量存储（MetadataSegment 走 PG 同步路径）
            kb_path = os.path.join(self._config.kb_dir, kb_model.kb_id)
            inst.storage = SegmentManager(kb_path, dim, pg_dsn=self._pg_dsn)
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
        summary: str = "",
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
            summary=summary,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k_dense=top_k_dense,
            top_k_sparse=top_k_sparse,
            top_m_final=top_m_final,
        )
        model = await self._store.create_kb(model)

        inst = KBInstance(model=model)
        kb_path = os.path.join(self._config.kb_dir, model.kb_id)
        dim = await asyncio.to_thread(self._embedder.get_dim)
        inst.storage = SegmentManager(kb_path, dim, pg_dsn=self._pg_dsn)
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

            # 2. 提前创建文档记录 → 标记 embedding
            doc = KBDocument(
                kb_id=kb_id,
                doc_name=parsed.title or file_name,
                file_type=file_ext,
                file_size=file_size,
                file_path=filepath,
                chunk_count=0,
                media_count=len(parsed.images) if parsed.images else 0,
                embedding_status="embedding",
            )
            doc = await self._store.create_document(doc)

            try:
                self._report(progress_callback, "chunking", 30)

                # 3. 可选 LLM 文本修复
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

                # 4. 分块
                chunk_size = inst.model.chunk_size
                chunk_overlap = inst.model.chunk_overlap
                strategy = "markdown" if file_ext in (".md", ".markdown", ".rst", ".adoc") else "recursive"

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
                        "doc_id": doc.doc_id,
                        **parsed.metadata,
                    },
                )

                if not chunks:
                    logger.warning("No chunks from: %s", filepath)
                    await self._store.update_document_embedding(
                        doc.doc_id, status="completed", chunk_count=0)
                    return 0

                self._report(progress_callback, "embedding", 50)

                # 5. Embedding
                texts = [c["text"] for c in chunks]
                embeddings = await self._embedder.embed_batch(texts)

                self._report(progress_callback, "indexing", 85)

                # 6. 写入向量存储
                inst.storage.add_chunks(chunks, embeddings)

                # 7. 标记嵌入完成
                await self._store.update_document_embedding(
                    doc.doc_id, status="completed", chunk_count=len(chunks))

                # 8. 保存媒体文件
                if parsed.images:
                    await self._save_media(inst, doc.doc_id, parsed.images, file_name)

                # 9. 更新统计
                await self._sync_stats(kb_id)

                self._report(progress_callback, "done", 100)

                logger.info("Uploaded %s → %d chunks (KB: %s, doc: %s)",
                             file_name, len(chunks), inst.name, doc.doc_id)
                return len(chunks)

            except Exception:
                await self._store.update_document_embedding(doc.doc_id, status="failed")
                raise

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

        # 提前创建文档记录
        doc = KBDocument(
            kb_id=kb_id,
            doc_name=title or "text_input",
            file_type="text",
            file_size=len(text),
            chunk_count=0,
            embedding_status="embedding",
        )
        doc = await self._store.create_document(doc)
        doc_id = doc.doc_id  # 保存到局部变量，防止 session 分离后属性不可访问

        try:
            chunker = get_chunker(
                strategy="recursive",
                chunk_size=inst.model.chunk_size,
                chunk_overlap=inst.model.chunk_overlap,
            )
            chunks = chunker.chunk(text, metadata={
                "source": "text",
                "title": title,
                "doc_id": doc_id,
                **(metadata or {}),
            })
            if not chunks:
                await self._store.update_document_embedding(
                    doc_id, status="completed", chunk_count=0)
                return 0

            texts = [c["text"] for c in chunks]
            embeddings = await self._embedder.embed_batch(texts)
            inst.storage.add_chunks(chunks, embeddings)

            await self._store.update_document_embedding(
                doc_id, status="completed", chunk_count=len(chunks))
            await self._sync_stats(kb_id)

            logger.info("Text uploaded: %d chunks (KB: %s)", len(chunks), inst.name)
            return len(chunks)

        except Exception:
            await self._store.update_document_embedding(doc_id, status="failed")
            raise

    async def upload_url(
        self,
        kb_id: str,
        url: str,
        title: str = "",
        progress_callback: Optional[ProgressHandler] = None,
    ) -> int:
        """上传 URL 网页内容到知识库"""
        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            raise ValueError(f"KB {kb_id} not found")

        async with inst._lock:
            self._report(progress_callback, "fetching", 5)

            # 1. URL 解析
            parser = discover_parser(url)
            if parser is None:
                raise ValueError(f"No parser available for URL: {url}")

            logger.debug("Fetching URL %s with %s", url, parser.name)
            parsed = await parser.parse(url)

            # 2. 创建文档记录
            doc_name = title or parsed.title or url
            doc = KBDocument(
                kb_id=kb_id,
                doc_name=doc_name,
                file_type="url",
                file_path=url,
                file_size=len(parsed.text.encode("utf-8")) if parsed.text else 0,
                chunk_count=0,
                media_count=len(parsed.images) if parsed.images else 0,
                embedding_status="embedding",
            )
            doc = await self._store.create_document(doc)
            doc_id = doc.doc_id  # 保存到局部变量，防止 session 分离后属性不可访问

            try:
                self._report(progress_callback, "chunking", 30)

                # 3. 分块
                chunk_size = inst.model.chunk_size
                chunk_overlap = inst.model.chunk_overlap
                chunker = get_chunker(
                    strategy="recursive",
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
                chunks = chunker.chunk(
                    parsed.text,
                    metadata={
                        "source": url,
                        "title": doc_name,
                        "parser": parser.name,
                        "doc_id": doc_id,
                        "url": url,
                    },
                )

                if not chunks:
                    logger.warning("No chunks from URL: %s", url)
                    await self._store.update_document_embedding(
                        doc_id, status="completed", chunk_count=0)
                    return 0

                self._report(progress_callback, "embedding", 50)

                # 4. Embedding + 索引
                texts = [c["text"] for c in chunks]
                embeddings = await self._embedder.embed_batch(texts)

                self._report(progress_callback, "indexing", 85)
                inst.storage.add_chunks(chunks, embeddings)

                # 5. 标记完成
                await self._store.update_document_embedding(
                    doc_id, status="completed", chunk_count=len(chunks))

                # 6. 保存媒体
                if parsed.images:
                    await self._save_media(inst, doc_id, parsed.images, doc_name)

                # 7. 更新统计
                await self._sync_stats(kb_id)

                self._report(progress_callback, "done", 100)
                logger.info("URL uploaded: %s → %d chunks (KB: %s, doc: %s)",
                             url, len(chunks), inst.name, doc_id)
                return len(chunks)

            except Exception:
                await self._store.update_document_embedding(doc_id, status="failed")
                raise

    # ── 重新训练 ────────────────────────────────

    async def retrain_kb(
        self,
        kb_id: str,
        progress_callback: Optional[ProgressHandler] = None,
    ) -> dict:
        """重新嵌入知识库中所有文档（清空向量存储 → 逐个重新上传）

        Returns:
            {"kb_id": str, "total": int, "success": int, "failed": int, "errors": list[str]}
        """
        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            raise ValueError(f"KB {kb_id} not found or not initialized")

        # 1. 拉取所有文档
        docs = await self._store.list_documents_by_kb(kb_id)
        if not docs:
            return {"kb_id": kb_id, "total": 0, "success": 0, "failed": 0, "errors": []}

        total = len(docs)

        # 2. 清空向量存储（避免重复 chunk）
        inst.storage.clear()

        # 3. 重置所有文档状态
        await self._store.reset_embedding_status(kb_id)

        # 4. 逐个重新上传（需要 file_path 的文档）
        # 先删除旧文档（upload_file 会创建新的）
        success = 0
        failed = 0
        errors: list[str] = []

        for i, doc in enumerate(docs):
            pct_base = (i / total) * 100 if total > 0 else 0
            self._report(progress_callback, "retrain", pct_base)

            # 先删除旧文档避免重复
            await self._store.delete_document_by_id(doc.doc_id)

            # 跳过没有文件路径的文档（如纯文本）
            if not doc.file_path:
                logger.debug("Skipping doc %s: no file_path", doc.doc_id)
                continue

            if not os.path.isfile(doc.file_path) and not (
                doc.file_path.startswith("http://") or doc.file_path.startswith("https://")
            ):
                errors.append(f"{doc.doc_name}: file not found ({doc.file_path})")
                failed += 1
                continue

            try:
                await self.upload_file(
                    kb_id, doc.file_path, progress_callback=None, repair=False,
                )
                success += 1
            except Exception as e:
                errors.append(f"{doc.doc_name}: {e}")
                failed += 1
                logger.warning("Retrain failed for doc %s: %s", doc.doc_id, e)

        self._report(progress_callback, "done", 100)

        summary = {
            "kb_id": kb_id,
            "total": total,
            "success": success,
            "failed": failed,
            "errors": errors[:20],  # 最多 20 条错误信息
        }
        logger.info("Retrain KB %s: %s", kb_id, summary)
        return summary

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
        targets: dict[str, SegmentManager] = {}

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

    # ── Chunk 管理 ────────────────────────────────

    async def list_chunks(
        self, kb_id: str, doc_id: str = None,
        skip: int = 0, limit: int = 100,
    ) -> tuple[list[dict], int]:
        """分页列出知识库的 chunk（可选按文档过滤）

        返回 (chunks, total)，chunk 结构：
        {doc_id: str, content: str, metadata: dict}
        doc_id 为 SegmentManager 内部 _doc_id（可直接用于 delete_chunks）。
        """
        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            raise ValueError(f"KB {kb_id} not found or not initialized")
        return inst.storage.list_chunks(
            doc_filter_id=doc_id, skip=skip, limit=limit,
        )

    async def delete_chunks(
        self, kb_id: str, chunk_ids: list[str],
    ) -> dict:
        """按 _doc_id 列表删除 chunk

        返回 {"total": int, "deleted": int}。
        注意：FAISS 不支持直接删除向量，仅从 ID 映射中移除。
        大规模删除后建议执行 retrain 重建索引。
        """
        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            raise ValueError(f"KB {kb_id} not found or not initialized")

        deleted = 0
        for cid in chunk_ids:
            if inst.storage.delete_chunk(cid):
                deleted += 1

        await self._sync_stats(kb_id)
        logger.info("Deleted %d/%d chunks from KB: %s", deleted, len(chunk_ids), kb_id)
        return {"total": len(chunk_ids), "deleted": deleted}

    # ── Job 管理 ────────────────────────────────

    async def create_job(
        self, kb_id: str, job_type: str, payload: dict = None,
    ) -> KBJob:
        """创建异步后台任务（pending 状态，需执行器后续调度）

        job_type: retrain | batch_embed | health_check
        """
        import json as _json
        job = KBJob(
            kb_id=kb_id,
            job_type=job_type,
            status="pending",
            payload_json=_json.dumps(payload or {}, ensure_ascii=False),
        )
        job = await self._store.create_job(job)
        logger.info("Created %s job %s for KB %s", job_type, job.job_id, kb_id)
        return job

    async def run_job(self, job_id: str) -> KBJob:
        """执行一个 pending job（同步 blocking 操作，调用方需自行放到后台线程）

        当前支持的 job_type:
        - retrain: 调用 retrain_kb()
        """
        import json as _json

        job = await self._store.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status != "pending":
            raise ValueError(f"Job {job_id} is not pending (current: {job.status})")

        await self._store.update_job(job_id, status="running")

        try:
            if job.job_type == "retrain":
                payload = job.payload
                summary = await self.retrain_kb(
                    kb_id=job.kb_id,
                    progress_callback=None,
                )
                await self._store.update_job(
                    job_id, status="completed", progress=1.0,
                    result_json=_json.dumps(summary, ensure_ascii=False),
                )
            else:
                await self._store.update_job(
                    job_id, status="failed",
                    error_message=f"Unsupported job_type: {job.job_type}",
                )
        except Exception as e:
            await self._store.update_job(
                job_id, status="failed",
                error_message=str(e)[:2000],
            )
            logger.exception("Job %s failed", job_id)

        return await self._store.get_job(job_id)

    async def get_job(self, job_id: str) -> Optional[KBJob]:
        return await self._store.get_job(job_id)

    async def list_jobs(
        self, kb_id: str = None, limit: int = 100, offset: int = 0,
    ) -> list[KBJob]:
        if kb_id:
            return await self._store.list_jobs_by_kb(kb_id, limit, offset)
        return await self._store.list_jobs_by_status("pending", limit, offset)

    # ── 索引压缩（FAISS 幽灵向量清理）──────────────

    def get_ghost_stats(self, kb_id: str) -> Optional[dict]:
        """获取 FAISS 索引健康状态（幽灵向量比例等）"""
        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            return None
        return {
            "kb_id": kb_id,
            **inst.storage.ghost_stats(),
        }

    def compact_kb_sync(self, kb_id: str) -> dict:
        """compack_kb 的同步包装器，供 asyncio.to_thread 调用

        compact_kb 本身是 async（因为有 _sync_stats），在事件循环外部无法
        直接 await，所以把纯 CPU 逻辑放 sync，最后状态刷新在外面处理。
        """
        import time

        inst = self._instances.get(kb_id)
        if not inst or not inst.storage:
            raise ValueError(f"KB {kb_id} not found or not loaded")

        storage = inst.storage
        ghost_stats = storage.ghost_stats()
        if ghost_stats["ghost_count"] == 0:
            return {
                "status": "skipped",
                "reason": "no ghost vectors",
                "stats": ghost_stats,
            }

        start = time.time()
        embedder = get_embedding_provider()
        valid_count = storage.compact(embedder)
        elapsed = round(time.time() - start, 2)

        return {
            "status": "completed",
            "valid_vectors": valid_count,
            "cleaned_ghosts": ghost_stats["ghost_count"],
            "ghost_ratio_before": ghost_stats["ghost_ratio"],
            "elapsed_seconds": elapsed,
            "stats": storage.ghost_stats(),
        }

    async def compact_kb(self, kb_id: str) -> dict:
        """压缩 FAISS 索引：重新嵌入所有有效 chunk 并重建索引

        删除幽灵向量，恢复检索性能。大规模删除 chunk 后建议调用。
        此操作会重新嵌入所有剩余文本，耗时与 chunk 数量成正比。

        注意: API 端应使用 asyncio.to_thread(compact_kb_sync) 以
        避免阻塞事件循环。此 async 版本用于内部调用。
        """
        import asyncio as _asyncio

        result = await _asyncio.to_thread(self.compact_kb_sync, kb_id)

        # 刷新统计（sync 路径无法访问 _sync_stats）
        await self._sync_stats(kb_id)
        return result

    # ── 后台作业调度 ─────────────────────────────

    async def schedule_job_background(self, job_id: str) -> KBJob:
        """将作业放到后台线程执行（asyncio.to_thread）

        与 run_job() 的区别：
        - run_job() 是同步阻塞的 async 包装，会阻塞事件循环
        - schedule_job_background() 使用 asyncio.to_thread 卸载到线程池，
          避免阻塞主事件循环，适合 API 端触发

        Returns:
            KBJob: 启动后的作业（状态为 running）

        Raises:
            ValueError: job 不存在或非 pending 状态
        """
        import asyncio as _asyncio

        # 先改为 running 状态并返回
        job = await self._store.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status != "pending":
            raise ValueError(f"Job {job_id} is not pending (current: {job.status})")

        await self._store.update_job(job_id, status="running")

        # 在后台线程中执行（不阻塞事件循环）
        _asyncio.create_task(
            self._run_in_thread(job_id)
        )

        return await self._store.get_job(job_id)

    async def _run_in_thread(self, job_id: str):
        """内部：在 asyncio.to_thread 中执行 run_job"""
        import asyncio as _asyncio
        try:
            await _asyncio.to_thread(self._run_job_sync, job_id)
        except Exception:
            logger.exception("Background job %s failed", job_id)

    def _run_job_sync(self, job_id: str):
        """同步执行 job 逻辑（from asyncio.to_thread）"""
        import asyncio as _asyncio

        async def _inner():
            await self.run_job(job_id)

        _asyncio.run(_inner())

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


def init_kb_manager_v2(store: Optional[KBPGStore] = None) -> KnowledgeBaseManagerV2:
    global _global_kb_manager_v2
    _global_kb_manager_v2 = KnowledgeBaseManagerV2(store=store)
    return _global_kb_manager_v2


def get_kb_manager_v2() -> KnowledgeBaseManagerV2:
    if _global_kb_manager_v2 is None:
        return init_kb_manager_v2()
    return _global_kb_manager_v2
