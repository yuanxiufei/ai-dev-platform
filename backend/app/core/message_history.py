"""
平台消息历史管理器 — 跨平台消息日志持久化

借鉴 AstrBot PlatformMessageHistoryManager 设计：
- 记录用户发送的原始消息和平台信息
- 支持按平台/用户查询历史
- 支持带 LLM checkpoint ID 的消息追踪
- 支持定期清理旧消息
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("platform.message_history")


@dataclass
class MessageRecord:
    """单条消息历史记录"""

    message_id: str
    """消息唯一 ID"""
    platform_id: str
    """平台标识"""
    session_id: str
    """会话 ID"""
    sender_id: str | None = None
    """发送者 ID"""
    sender_name: str | None = None
    """发送者名称"""
    content: dict[str, Any] = field(default_factory=dict)
    """消息内容（结构化）"""
    llm_checkpoint_id: str | None = None
    """关联的 LLM checkpoint ID"""
    timestamp: float = field(default_factory=time.time)
    """消息时间戳"""


# ── 存储抽象 ────────────────────────────────────────


class MessageHistoryStore:
    """消息历史存储抽象接口"""

    async def insert(self, record: MessageRecord) -> MessageRecord:
        raise NotImplementedError

    async def get(
        self,
        session_id: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 200,
    ) -> list[MessageRecord]:
        raise NotImplementedError

    async def delete_older_than(
        self, session_id: str, max_age_seconds: int
    ) -> int:
        raise NotImplementedError

    async def delete_by_id(self, message_id: str) -> None:
        raise NotImplementedError

    async def update(
        self,
        message_id: str,
        content: dict[str, Any] | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        raise NotImplementedError


class SqliteMessageHistoryStore(MessageHistoryStore):
    """SQLite 持久化消息历史存储"""

    def __init__(self, db_path: str = "data/messages.db") -> None:
        import sqlite3
        import os
        os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)
        self._db = sqlite3.connect(db_path, check_same_thread=False)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS message_history (
                message_id TEXT PRIMARY KEY,
                platform_id TEXT NOT NULL DEFAULT 'unknown',
                session_id TEXT NOT NULL,
                sender_id TEXT,
                sender_name TEXT,
                content TEXT NOT NULL DEFAULT '{}',
                llm_checkpoint_id TEXT,
                timestamp REAL NOT NULL
            )
        """)
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_mh_session ON message_history(session_id)")
        self._db.execute("CREATE INDEX IF NOT EXISTS idx_mh_ts ON message_history(timestamp)")
        self._db.commit()

    async def insert(self, record: MessageRecord) -> MessageRecord:
        import json
        self._db.execute(
            """INSERT OR REPLACE INTO message_history
               (message_id, platform_id, session_id, sender_id, sender_name,
                content, llm_checkpoint_id, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (record.message_id, record.platform_id, record.session_id,
             record.sender_id, record.sender_name,
             json.dumps(record.content, ensure_ascii=False),
             record.llm_checkpoint_id, record.timestamp),
        )
        self._db.commit()
        return record

    async def get(
        self,
        session_id: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 200,
    ) -> list[MessageRecord]:
        import json
        query = "SELECT * FROM message_history WHERE session_id = ?"
        params: list = [session_id]
        if platform_id is not None:
            query += " AND platform_id = ?"
            params.append(platform_id)
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
        rows = self._db.execute(query, params).fetchall()
        results = []
        for row in rows:
            results.append(MessageRecord(
                message_id=row[0], platform_id=row[1], session_id=row[2],
                sender_id=row[3], sender_name=row[4],
                content=json.loads(row[5]) if row[5] else {},
                llm_checkpoint_id=row[6], timestamp=row[7],
            ))
        return results

    async def delete_older_than(
        self, session_id: str, max_age_seconds: int
    ) -> int:
        cutoff = time.time() - max_age_seconds
        cursor = self._db.execute(
            "DELETE FROM message_history WHERE session_id = ? AND timestamp < ?",
            (session_id, cutoff),
        )
        self._db.commit()
        return cursor.rowcount

    async def delete_by_id(self, message_id: str) -> None:
        self._db.execute("DELETE FROM message_history WHERE message_id = ?", (message_id,))
        self._db.commit()

    async def update(
        self,
        message_id: str,
        content: dict[str, Any] | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        import json
        if content is not None:
            self._db.execute(
                "UPDATE message_history SET content = ? WHERE message_id = ?",
                (json.dumps(content, ensure_ascii=False), message_id),
            )
        if llm_checkpoint_id is not None:
            self._db.execute(
                "UPDATE message_history SET llm_checkpoint_id = ? WHERE message_id = ?",
                (llm_checkpoint_id, message_id),
            )
        self._db.commit()


class MemoryMessageHistoryStore(MessageHistoryStore):
    """内存消息历史存储（开发/测试用）"""

    def __init__(self, max_records: int = 10000) -> None:
        self._records: list[MessageRecord] = []
        self._max = max_records

    async def insert(self, record: MessageRecord) -> MessageRecord:
        self._records.append(record)
        if len(self._records) > self._max:
            self._records = self._records[-self._max:]
        return record

    async def get(
        self,
        session_id: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 200,
    ) -> list[MessageRecord]:
        filtered = [
            r for r in self._records
            if r.session_id == session_id
            and (platform_id is None or r.platform_id == platform_id)
        ]
        # 分区内存分页
        total = len(filtered)
        start = (page - 1) * page_size
        if start >= total:
            return []
        return filtered[start : start + page_size]

    async def delete_older_than(
        self, session_id: str, max_age_seconds: int
    ) -> int:
        cutoff = time.time() - max_age_seconds
        before = len(self._records)
        self._records = [
            r for r in self._records
            if not (r.session_id == session_id and r.timestamp < cutoff)
        ]
        return before - len(self._records)

    async def delete_by_id(self, message_id: str) -> None:
        self._records = [
            r for r in self._records if r.message_id != message_id
        ]

    async def update(
        self,
        message_id: str,
        content: dict[str, Any] | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        for r in self._records:
            if r.message_id == message_id:
                if content is not None:
                    r.content = content
                if llm_checkpoint_id is not None:
                    r.llm_checkpoint_id = llm_checkpoint_id
                break


# ── 消息历史管理器 ───────────────────────────────────


class PlatformMessageHistoryManager:
    """跨平台消息历史管理器。

    负责记录和管理所有平台的消息历史，支持：
    - 插入消息记录
    - 按会话查询历史
    - 定期清理旧记录
    - LLM checkpoint 追踪
    """

    def __init__(
        self,
        store: MessageHistoryStore | None = None,
        default_retention_seconds: int = 86400 * 7,
    ) -> None:
        self._store: MessageHistoryStore = store or MemoryMessageHistoryStore()
        self._default_retention = default_retention_seconds

    async def insert(
        self,
        session_id: str,
        content: dict[str, Any],
        platform_id: str = "unknown",
        sender_id: str | None = None,
        sender_name: str | None = None,
        llm_checkpoint_id: str | None = None,
        message_id: str | None = None,
    ) -> MessageRecord:
        """插入一条消息历史记录"""
        import uuid

        record = MessageRecord(
            message_id=message_id or uuid.uuid4().hex,
            platform_id=platform_id,
            session_id=session_id,
            sender_id=sender_id,
            sender_name=sender_name,
            content=content,
            llm_checkpoint_id=llm_checkpoint_id,
        )
        return await self._store.insert(record)

    async def get_history(
        self,
        session_id: str,
        platform_id: str | None = None,
        page: int = 1,
        page_size: int = 200,
    ) -> list[MessageRecord]:
        """获取会话的消息历史（倒序，最新在前）"""
        records = await self._store.get(
            session_id=session_id,
            platform_id=platform_id,
            page=page,
            page_size=page_size,
        )
        records.reverse()
        return records

    async def delete_old(
        self, session_id: str, max_age_seconds: int | None = None
    ) -> int:
        """删除指定会话中超过保留时间的旧记录"""
        age = max_age_seconds or self._default_retention
        return await self._store.delete_older_than(session_id, age)

    async def delete_by_id(self, message_id: str) -> None:
        """按 ID 删除消息"""
        await self._store.delete_by_id(message_id)

    async def update(
        self,
        message_id: str,
        content: dict[str, Any] | None = None,
        llm_checkpoint_id: str | None = None,
    ) -> None:
        """更新消息记录"""
        await self._store.update(
            message_id=message_id,
            content=content,
            llm_checkpoint_id=llm_checkpoint_id,
        )


# ── 全局单例 ────────────────────────────────────────

_message_history_manager: PlatformMessageHistoryManager | None = None


def init_message_history_manager(
    use_sqlite: bool = True,
    db_path: str = "data/messages.db",
) -> PlatformMessageHistoryManager:
    """初始化全局消息历史管理器（默认 SQLite 持久化）"""
    global _message_history_manager
    store = SqliteMessageHistoryStore(db_path) if use_sqlite else MemoryMessageHistoryStore()
    _message_history_manager = PlatformMessageHistoryManager(store=store)
    logger.info(
        "PlatformMessageHistoryManager initialized (backend=%s)",
        "SQLite" if use_sqlite else "Memory",
    )
    return _message_history_manager


def get_message_history_manager() -> PlatformMessageHistoryManager:
    """获取全局消息历史管理器"""
    global _message_history_manager
    if _message_history_manager is None:
        _message_history_manager = init_message_history_manager()
    return _message_history_manager
