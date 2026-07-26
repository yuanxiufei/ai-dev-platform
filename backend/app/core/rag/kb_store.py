"""
KB 元数据持久化存储 — 统一 PostgreSQL 后端

所有 KB 元数据模型 (KnowledgeBase/KBDocument/KBMedia/KBJob/Segment)
通过 table=True 自动注册到 SQLModel.metadata，由主 init_db() 统一建表。
此模块提供异步 CRUD 层，复用主 PostgreSQL AsyncEngine。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession

from app.core.rag.models import KnowledgeBase, KBDocument, KBMedia, KBJob

logger = logging.getLogger("app.core.rag.kb_store")


class KBPGStore:
    """KB 元数据 PostgreSQL 持久化层 — 异步 CRUD"""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self._initialized = False

    async def initialize(self) -> None:
        """初始化 — 验证引擎可用性，表由主 init_db() 统一创建"""
        try:
            async with SQLModelAsyncSession(self.engine) as session:
                await session.execute(select(1))
            self._initialized = True
            logger.info("KBPGStore connected to PostgreSQL")
        except Exception as e:
            logger.error("KBPGStore 连接 PostgreSQL 失败: %s", e)
            raise

    # ── 会话工厂 ──────────────────────────────────────

    async def get_session(self) -> SQLModelAsyncSession:
        session = SQLModelAsyncSession(self.engine)
        # expire_on_commit=False 防止 commit 后属性过期导致 detached instance 访问报错
        session.expire_on_commit = False
        return session

    async def get_db(self) -> SQLModelAsyncSession:
        """兼容旧版 get_db() 接口"""
        return await self.get_session()

    # ── 工具函数 ──────────────────────────────────────

    def _serialize_dict(self, d: dict) -> str:
        return json.dumps(d, ensure_ascii=False)

    def _deserialize_dict(self, s: Optional[str]) -> dict:
        if not s:
            return {}
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return {}

    # ── KnowledgeBase CRUD ─────────────────────────────

    async def create_kb(self, model_or_name, description: str = "", **kwargs) -> KnowledgeBase:
        """创建 KB — 兼容两种调用方式:
        - create_kb(model: KnowledgeBase)   → 直接持久化模型实例
        - create_kb(name: str, description: str, **kwargs) → 构造新实例
        """
        if isinstance(model_or_name, KnowledgeBase):
            kb = model_or_name
            async with await self.get_session() as session:
                session.add(kb)
                await session.commit()
                await session.refresh(kb)
                return kb
        async with await self.get_session() as session:
            kb = KnowledgeBase(kb_name=model_or_name, description=description, **kwargs)
            session.add(kb)
            await session.commit()
            await session.refresh(kb)
            return kb

    async def get_kb(self, kb_id: str) -> Optional[KnowledgeBase]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )
            return result.first()

    async def get_kb_by_name(self, name: str) -> Optional[KnowledgeBase]:
        """按名称查询 KB（kb_manager v2 兼容接口）"""
        async with await self.get_session() as session:
            result = await session.exec(
                select(KnowledgeBase).where(KnowledgeBase.kb_name == name)
            )
            return result.first()

    async def list_kbs(self, offset: int = 0, limit: int = 50) -> list[KnowledgeBase]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KnowledgeBase).offset(offset).limit(limit).order_by(KnowledgeBase.created_at.desc())
            )
            return list(result.all())

    async def update_kb(self, model_or_id, **updates) -> Optional[KnowledgeBase]:
        """更新 KB — 兼容两种调用方式:
        - update_kb(model: KnowledgeBase)     → 直接持久化模型实例
        - update_kb(kb_id: str, **updates)    → 按字段更新
        """
        if isinstance(model_or_id, KnowledgeBase):
            kb = model_or_id
            async with await self.get_session() as session:
                session.add(kb)
                await session.commit()
                await session.refresh(kb)
                return kb
        kb_id = model_or_id
        async with await self.get_session() as session:
            result = await session.exec(
                select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )
            kb = result.first()
            if not kb:
                return None
            for key, value in updates.items():
                if hasattr(kb, key):
                    setattr(kb, key, value)
            session.add(kb)
            await session.commit()
            await session.refresh(kb)
            return kb

    async def delete_kb(self, kb_id: str) -> bool:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )
            kb = result.first()
            if not kb:
                return False
            # 级联删除关联文档、媒体、任务
            for doc in await session.exec(select(KBDocument).where(KBDocument.kb_id == kb_id)):
                await session.delete(doc)
            for media in await session.exec(select(KBMedia).where(KBMedia.kb_id == kb_id)):
                await session.delete(media)
            for job in await session.exec(select(KBJob).where(KBJob.kb_id == kb_id)):
                await session.delete(job)
            await session.delete(kb)
            await session.commit()
            return True

    async def update_kb_stats(self, kb_id: str, doc_count: int, chunk_count: int) -> Optional[KnowledgeBase]:
        """更新 KB 文档/分块计数（kb_manager v2 兼容接口）"""
        return await self.update_kb(kb_id, doc_count=doc_count, chunk_count=chunk_count)

    async def count_documents_by_kb(self, kb_id: str) -> int:
        """按 KB 统计文档数（kb_manager v2 兼容接口）"""
        async with await self.get_session() as session:
            from sqlalchemy import func
            result = await session.exec(
                select(func.count()).where(KBDocument.kb_id == kb_id)
            )
            return result.one()

    # ── KBDocument CRUD ────────────────────────────────

    async def create_doc(self, kb_id_or_doc, doc_name: str = "", **kwargs) -> KBDocument:
        """创建文档 — 兼容两种调用方式:
        - create_doc(doc: KBDocument)       → 直接持久化模型实例
        - create_doc(kb_id: str, doc_name: str, **kwargs) → 构造新实例
        """
        if isinstance(kb_id_or_doc, KBDocument):
            doc = kb_id_or_doc
            async with await self.get_session() as session:
                session.add(doc)
                await session.commit()
                await session.refresh(doc)
                # 同步 doc_count
                kb = (await session.exec(select(KnowledgeBase).where(KnowledgeBase.kb_id == doc.kb_id))).first()
                if kb:
                    kb.doc_count = (kb.doc_count or 0) + 1
                    session.add(kb)
                    await session.commit()
                    # 二次 commit 后重新刷新 doc，否则属性过期
                    await session.refresh(doc)
                return doc
        kb_id = kb_id_or_doc
        return await self._create_doc_internal(kb_id, doc_name, **kwargs)

    async def _create_doc_internal(self, kb_id: str, doc_name: str, **kwargs) -> KBDocument:
        async with await self.get_session() as session:
            doc = KBDocument(kb_id=kb_id, doc_name=doc_name, **kwargs)
            session.add(doc)
            await session.commit()
            await session.refresh(doc)
            kb = (await session.exec(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))).first()
            if kb:
                kb.doc_count = (kb.doc_count or 0) + 1
                session.add(kb)
                await session.commit()
            return doc

    # kb_manager v2 兼容别名
    async def create_document(self, doc_or_kb_id, doc_name: str = "", **kwargs) -> KBDocument:
        """kb_manager v2 兼容接口：create_document(doc) 或 create_document(kb_id, doc_name, **kwargs)"""
        return await self.create_doc(doc_or_kb_id, doc_name, **kwargs)

    async def get_doc(self, doc_id: str) -> Optional[KBDocument]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBDocument).where(KBDocument.doc_id == doc_id)
            )
            return result.first()

    # kb_manager v2 兼容别名
    async def get_document_by_id(self, doc_id: str) -> Optional[KBDocument]:
        return await self.get_doc(doc_id)

    async def list_docs(self, kb_id: str, offset: int = 0, limit: int = 50) -> list[KBDocument]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBDocument)
                .where(KBDocument.kb_id == kb_id)
                .offset(offset)
                .limit(limit)
                .order_by(KBDocument.created_at.desc())
            )
            return list(result.all())

    # kb_manager v2 兼容别名
    async def list_documents_by_kb(self, kb_id: str) -> list[KBDocument]:
        """kb_manager v2 兼容接口：列出 KB 下所有文档（不分页）"""
        return await self.list_docs(kb_id, offset=0, limit=10000)

    async def update_doc(self, doc_id: str, **updates) -> Optional[KBDocument]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBDocument).where(KBDocument.doc_id == doc_id)
            )
            doc = result.first()
            if not doc:
                return None
            for key, value in updates.items():
                if hasattr(doc, key):
                    setattr(doc, key, value)
            session.add(doc)
            await session.commit()
            await session.refresh(doc)
            return doc

    async def update_document_embedding(
        self, doc_id: str, status: str = "completed", chunk_count: int = 0,
    ) -> Optional[KBDocument]:
        """更新文档嵌入状态（kb_manager v2 兼容接口）"""
        return await self.update_doc(doc_id, embedding_status=status, chunk_count=chunk_count)

    async def delete_doc(self, doc_id: str) -> bool:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBDocument).where(KBDocument.doc_id == doc_id)
            )
            doc = result.first()
            if not doc:
                return False
            kb_id = doc.kb_id
            # 级联删除关联媒体、任务
            for media in await session.exec(select(KBMedia).where(KBMedia.doc_id == doc_id)):
                await session.delete(media)
            for job in await session.exec(select(KBJob).where(KBJob.kb_id == kb_id)):
                await session.delete(job)
            await session.delete(doc)
            # 同步 doc_count
            kb = (await session.exec(select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id))).first()
            if kb:
                kb.doc_count = max(0, (kb.doc_count or 0) - 1)
                session.add(kb)
            await session.commit()
            return True

    # kb_manager v2 兼容别名
    async def delete_document_by_id(self, doc_id: str) -> bool:
        return await self.delete_doc(doc_id)

    async def reset_embedding_status(self, kb_id: str) -> None:
        """重置 KB 下所有文档的嵌入状态为 pending（kb_manager v2 兼容接口）"""
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBDocument).where(KBDocument.kb_id == kb_id)
            )
            for doc in result.all():
                doc.embedding_status = "pending"
                doc.chunk_count = 0
                session.add(doc)
            await session.commit()

    # ── KBMedia CRUD ──────────────────────────────────

    async def create_media(self, kb_id: str, doc_id: str, file_name: str, **kwargs) -> KBMedia:
        async with await self.get_session() as session:
            media = KBMedia(kb_id=kb_id, doc_id=doc_id, file_name=file_name, **kwargs)
            session.add(media)
            await session.commit()
            await session.refresh(media)
            return media

    async def get_media(self, media_id: str) -> Optional[KBMedia]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBMedia).where(KBMedia.media_id == media_id)
            )
            return result.first()

    async def list_media(self, kb_id: str, doc_id: Optional[str] = None,
                         offset: int = 0, limit: int = 50) -> list[KBMedia]:
        async with await self.get_session() as session:
            stmt = select(KBMedia).where(KBMedia.kb_id == kb_id)
            if doc_id:
                stmt = stmt.where(KBMedia.doc_id == doc_id)
            result = await session.exec(stmt.offset(offset).limit(limit))
            return list(result.all())

    async def delete_media(self, media_id: str) -> bool:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBMedia).where(KBMedia.media_id == media_id)
            )
            media = result.first()
            if not media:
                return False
            await session.delete(media)
            await session.commit()
            return True

    # ── KBJob 异步任务 CRUD ────────────────────────────

    async def create_job(self, kb_id_or_job, job_type: str = "", payload: Optional[dict] = None) -> KBJob:
        """创建任务 — 兼容两种调用方式:
        - create_job(job: KBJob)           → 直接持久化模型实例
        - create_job(kb_id: str, job_type: str, payload: dict) → 构造新实例
        """
        if isinstance(kb_id_or_job, KBJob):
            job = kb_id_or_job
            async with await self.get_session() as session:
                session.add(job)
                await session.commit()
                await session.refresh(job)
                return job
        kb_id = kb_id_or_job
        async with await self.get_session() as session:
            job = KBJob(kb_id=kb_id, job_type=job_type)
            if payload:
                job.set_payload(payload)
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    async def get_job(self, job_id: str) -> Optional[KBJob]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBJob).where(KBJob.job_id == job_id)
            )
            return result.first()

    async def list_jobs(self, kb_id: str, offset: int = 0, limit: int = 50) -> list[KBJob]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBJob)
                .where(KBJob.kb_id == kb_id)
                .offset(offset)
                .limit(limit)
                .order_by(KBJob.created_at.desc())
            )
            return list(result.all())

    # kb_manager v2 兼容别名（参数顺序: kb_manager 传 limit, offset)
    async def list_jobs_by_kb(self, kb_id: str, limit: int = 50, offset: int = 0) -> list[KBJob]:
        return await self.list_jobs(kb_id, offset=offset, limit=limit)

    async def list_jobs_by_status(self, status: str, limit: int = 50, offset: int = 0) -> list[KBJob]:
        """按状态查询任务（kb_manager v2 兼容接口）"""
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBJob)
                .where(KBJob.status == status)
                .limit(limit)
                .offset(offset)
                .order_by(KBJob.created_at.desc())
            )
            return list(result.all())

    async def update_job(self, job_id: str, **updates) -> Optional[KBJob]:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBJob).where(KBJob.job_id == job_id)
            )
            job = result.first()
            if not job:
                return None
            from datetime import datetime, timezone
            for key, value in updates.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = datetime.now(timezone.utc).isoformat()
            session.add(job)
            await session.commit()
            await session.refresh(job)
            return job

    async def delete_job(self, job_id: str) -> bool:
        async with await self.get_session() as session:
            result = await session.exec(
                select(KBJob).where(KBJob.job_id == job_id)
            )
            job = result.first()
            if not job:
                return False
            await session.delete(job)
            await session.commit()
            return True

    # ── Lifecycle ──

    async def close(self) -> None:
        """释放连接池（kb_manager v2 兼容接口）"""
        if self._engine:
            await self._engine.dispose()
            self._engine = None


# ── 全局单例 ─────────────────────────────────────────

_global_kb_store: Optional[KBPGStore] = None


async def init_kb_store(engine: AsyncEngine) -> KBPGStore:
    """初始化 KB 元数据存储 (PostgreSQL, 复用主 engine)

    :param engine: PostgreSQL AsyncEngine (复用主数据库连接)
    """
    global _global_kb_store
    _global_kb_store = KBPGStore(engine)
    await _global_kb_store.initialize()
    return _global_kb_store


def get_kb_store() -> KBPGStore:
    """获取全局 KB 存储单例"""
    if _global_kb_store is None:
        raise RuntimeError(
            "KB store 未初始化，请先调用 init_kb_store(engine)"
        )
    return _global_kb_store


# ── 向后兼容别名 ─────────────────────────────────────
# 旧代码引用 KBSQLiteStore 时自动映射到 KBPGStore
KBSQLiteStore = KBPGStore
