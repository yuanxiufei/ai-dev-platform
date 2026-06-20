"""
KB SQLite 持久化层 — 异步 SQLAlchemy + aiosqlite

借鉴 AstrBot KBSQLiteDatabase:
- 异步引擎 + 连接池
- SQLite PRAGMA 性能优化 (WAL/NORMAL/缓存/mmapsize)
- 完整 CRUD: KB / 文档 / 媒体
- 统计同步
- 索引迁移
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import select, func, delete as sqldelete, update as sqlupdate

from app.core.rag.models import KnowledgeBase, KBDocument, KBMedia

logger = logging.getLogger("app.core.rag.kb_store")


class KBSQLiteStore:
    """知识库 SQLite 持久化层"""

    def __init__(self, db_path: str):
        self._db_path = db_path
        self._engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self._session_factory = async_sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False,
        )

    # ── 生命周期 ────────────────────────────────

    async def initialize(self) -> None:
        """创建表 + SQLite 性能优化"""
        from sqlmodel import SQLModel
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

        # PRAGMA 优化
        pragmas = [
            "PRAGMA journal_mode=WAL",
            "PRAGMA synchronous=NORMAL",
            "PRAGMA cache_size=-20000",
            "PRAGMA temp_store=MEMORY",
            "PRAGMA mmap_size=134217728",
        ]
        async with self._engine.begin() as conn:
            for p in pragmas:
                await conn.run_sync(lambda c, s=p: c.execute(s))

        # 创建索引
        await self._create_indexes()

        logger.info("KB store initialized: %s", db_path)

    async def close(self) -> None:
        await self._engine.dispose()

    async def _create_indexes(self) -> None:
        """创建关键查询索引"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_kb_documents_kb_id ON kb_documents(kb_id)",
            "CREATE INDEX IF NOT EXISTS idx_kb_media_doc_id ON kb_media(doc_id)",
            "CREATE INDEX IF NOT EXISTS idx_kb_media_kb_id ON kb_media(kb_id)",
        ]
        async with self._engine.begin() as conn:
            for sql in indexes:
                try:
                    await conn.run_sync(lambda c, s=sql: c.execute(s))
                except Exception:
                    pass

    @asynccontextmanager
    async def get_db(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._session_factory() as session:
            yield session

    # ── 知识库 CRUD ────────────────────────────────

    async def create_kb(self, kb: KnowledgeBase) -> KnowledgeBase:
        async with self.get_db() as db:
            db.add(kb)
            await db.commit()
            await db.refresh(kb)
            return kb

    async def get_kb_by_id(self, kb_id: str) -> Optional[KnowledgeBase]:
        async with self.get_db() as db:
            result = await db.exec(
                select(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )
            return result.first()

    async def get_kb_by_name(self, name: str) -> Optional[KnowledgeBase]:
        async with self.get_db() as db:
            result = await db.exec(
                select(KnowledgeBase).where(KnowledgeBase.kb_name == name)
            )
            return result.first()

    async def list_kbs(self) -> list[KnowledgeBase]:
        async with self.get_db() as db:
            result = await db.exec(select(KnowledgeBase))
            return list(result.all())

    async def count_kbs(self) -> int:
        async with self.get_db() as db:
            result = await db.exec(
                select(func.count()).select_from(KnowledgeBase)
            )
            return result.one()

    async def update_kb(self, kb: KnowledgeBase) -> KnowledgeBase:
        async with self.get_db() as db:
            db.add(kb)
            await db.commit()
            await db.refresh(kb)
            return kb

    async def delete_kb(self, kb_id: str) -> None:
        async with self.get_db() as db:
            await db.exec(
                sqldelete(KnowledgeBase).where(KnowledgeBase.kb_id == kb_id)
            )
            await db.exec(
                sqldelete(KBDocument).where(KBDocument.kb_id == kb_id)
            )
            await db.exec(
                sqldelete(KBMedia).where(KBMedia.kb_id == kb_id)
            )
            await db.commit()

    # ── 文档 CRUD ────────────────────────────────

    async def create_document(self, doc: KBDocument) -> KBDocument:
        async with self.get_db() as db:
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            return doc

    async def get_document_by_id(self, doc_id: str) -> Optional[KBDocument]:
        async with self.get_db() as db:
            result = await db.exec(
                select(KBDocument).where(KBDocument.doc_id == doc_id)
            )
            return result.first()

    async def list_documents_by_kb(self, kb_id: str) -> list[KBDocument]:
        async with self.get_db() as db:
            result = await db.exec(
                select(KBDocument).where(KBDocument.kb_id == kb_id)
            )
            return list(result.all())

    async def count_documents_by_kb(self, kb_id: str) -> int:
        async with self.get_db() as db:
            result = await db.exec(
                select(func.count()).select_from(KBDocument).where(
                    KBDocument.kb_id == kb_id
                )
            )
            return result.one()

    async def delete_document_by_id(self, doc_id: str) -> None:
        async with self.get_db() as db:
            await db.exec(
                sqldelete(KBDocument).where(KBDocument.doc_id == doc_id)
            )
            await db.exec(
                sqldelete(KBMedia).where(KBMedia.doc_id == doc_id)
            )
            await db.commit()

    # ── 媒体 CRUD ────────────────────────────────

    async def create_media(self, media: KBMedia) -> KBMedia:
        async with self.get_db() as db:
            db.add(media)
            await db.commit()
            await db.refresh(media)
            return media

    async def list_media_by_doc(self, doc_id: str) -> list[KBMedia]:
        async with self.get_db() as db:
            result = await db.exec(
                select(KBMedia).where(KBMedia.doc_id == doc_id)
            )
            return list(result.all())

    async def list_media_by_kb(self, kb_id: str) -> list[KBMedia]:
        async with self.get_db() as db:
            result = await db.exec(
                select(KBMedia).where(KBMedia.kb_id == kb_id)
            )
            return list(result.all())

    async def get_media_by_id(self, media_id: str) -> Optional[KBMedia]:
        async with self.get_db() as db:
            result = await db.exec(
                select(KBMedia).where(KBMedia.media_id == media_id)
            )
            return result.first()

    # ── 统计同步 ────────────────────────────────

    async def update_kb_stats(self, kb_id: str, doc_count: int, chunk_count: int) -> None:
        """同步向量数据库中的实际计数到知识库记录"""
        from datetime import datetime, timezone
        async with self.get_db() as db:
            await db.exec(
                sqlupdate(KnowledgeBase)
                .where(KnowledgeBase.kb_id == kb_id)
                .values(
                    doc_count=doc_count,
                    chunk_count=chunk_count,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
            )
            await db.commit()


# ── 全局单例 ──────────────────────────────────────────

_global_kb_store: Optional[KBSQLiteStore] = None


def init_kb_store(db_path: str) -> KBSQLiteStore:
    global _global_kb_store
    _global_kb_store = KBSQLiteStore(db_path)
    return _global_kb_store


def get_kb_store() -> KBSQLiteStore:
    if _global_kb_store is None:
        raise RuntimeError("KB store not initialized — call init_kb_store() first")
    return _global_kb_store
