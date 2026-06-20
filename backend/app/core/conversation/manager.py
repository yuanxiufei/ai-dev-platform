"""
对话管理器 — 会话与对话的映射管理

借鉴 AstrBot ConversationManager 设计：
- 会话 (Session) 与对话 (Conversation) 是独立的两个概念
- 一个会话可以包含多个对话，支持切换和删除
- 当前活跃对话的 tracking
- 对话历史持久化 / 更新 / 检索
- 会话删除时的级联清理回调

设计原则：
- 不依赖具体的 ORM/存储后端，通过接口抽象
- 支持内存缓存 + 数据库持久化
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("platform.conversation")


@dataclass
class Conversation:
    """对话数据结构"""

    conversation_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    """对话唯一 ID"""
    session_id: str = ""
    """所属会话 ID (unified_msg_origin)"""
    platform_id: str = ""
    """平台 ID"""
    title: str | None = None
    """对话标题（可自动生成）"""
    history: list[dict[str, Any]] = field(default_factory=list)
    """对话历史消息列表 [{"role": "user", "content": "..."}, ...]"""
    persona_id: str | None = None
    """绑定的 Persona ID"""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    token_usage: int = 0
    """累计 token 使用量"""


# ── 存储抽象接口 ─────────────────────────────────────


class ConversationStore:
    """对话存储抽象接口。

    子类可以实现为内存存储、数据库存储、文件存储等。
    """

    async def create(self, conv: Conversation) -> Conversation:
        raise NotImplementedError

    async def get(self, conversation_id: str) -> Conversation | None:
        raise NotImplementedError

    async def update(
        self,
        conversation_id: str,
        history: list[dict[str, Any]] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        token_usage: int | None = None,
    ) -> None:
        raise NotImplementedError

    async def delete(self, conversation_id: str) -> None:
        raise NotImplementedError

    async def delete_by_session(self, session_id: str) -> None:
        raise NotImplementedError

    async def list_by_session(
        self, session_id: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[Conversation], int]:
        raise NotImplementedError


class MemoryConversationStore(ConversationStore):
    """内存对话存储（用于开发/测试）"""

    def __init__(self) -> None:
        self._store: dict[str, Conversation] = {}

    async def create(self, conv: Conversation) -> Conversation:
        self._store[conv.conversation_id] = conv
        return conv

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._store.get(conversation_id)

    async def update(
        self,
        conversation_id: str,
        history: list[dict[str, Any]] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        token_usage: int | None = None,
    ) -> None:
        conv = self._store.get(conversation_id)
        if not conv:
            return
        if history is not None:
            conv.history = history
        if title is not None:
            conv.title = title
        if persona_id is not None:
            conv.persona_id = persona_id
        if token_usage is not None:
            conv.token_usage = token_usage
        conv.updated_at = time.time()

    async def delete(self, conversation_id: str) -> None:
        self._store.pop(conversation_id, None)

    async def delete_by_session(self, session_id: str) -> None:
        to_delete = [
            cid for cid, c in self._store.items()
            if c.session_id == session_id
        ]
        for cid in to_delete:
            del self._store[cid]

    async def list_by_session(
        self, session_id: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[Conversation], int]:
        all_convs = [
            c for c in self._store.values()
            if c.session_id == session_id
        ]
        total = len(all_convs)
        start = (page - 1) * page_size
        return all_convs[start : start + page_size], total


# ── 对话管理器 ───────────────────────────────────────


class ConversationManager:
    """负责管理会话与 LLM 对话的映射关系。

    核心职责：
    - 维护 session → current conversation 的映射
    - 创建/切换/删除对话
    - 更新对话历史和元数据
    - 会话删除时级联清理

    使用方式：
        >>> mgr = ConversationManager(MemoryConversationStore())
        >>> cid = await mgr.new_conversation("chat_room_123")
        >>> await mgr.update_conversation_history(cid, [...])
        >>> await mgr.switch_conversation("chat_room_123", cid)
    """

    def __init__(self, store: ConversationStore | None = None) -> None:
        self._store: ConversationStore = store or MemoryConversationStore()
        # session_id → current conversation_id
        self._session_conv_map: dict[str, str] = {}
        # 会话删除回调列表（级联清理）
        self._on_session_deleted: list[
            Callable[[str], Awaitable[None]]
        ] = []

    # ── 回调注册 ─────────────────────────────────────

    def register_on_session_deleted(
        self, callback: Callable[[str], Awaitable[None]]
    ) -> None:
        """注册会话删除回调（用于级联清理）。

        例如：知识库模块可以注册回调来清理会话的 RAG 配置。
        """
        self._on_session_deleted.append(callback)

    async def _trigger_session_deleted(self, session_id: str) -> None:
        """触发所有会话删除回调"""
        for cb in self._on_session_deleted:
            try:
                await cb(session_id)
            except Exception as e:
                logger.error(
                    "Session-deleted callback failed for '%s': %s",
                    session_id, e,
                )

    # ── 对话 CRUD ─────────────────────────────────────

    async def new_conversation(
        self,
        session_id: str,
        platform_id: str = "unknown",
        content: list[dict[str, Any]] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
    ) -> str:
        """创建新对话，并将当前会话切换到新对话。

        Returns:
            conversation_id: 新对话的 UUID
        """
        conv = Conversation(
            session_id=session_id,
            platform_id=platform_id,
            history=content or [],
            title=title,
            persona_id=persona_id,
        )
        await self._store.create(conv)
        self._session_conv_map[session_id] = conv.conversation_id
        logger.debug(
            "New conversation '%s' for session '%s'",
            conv.conversation_id, session_id,
        )
        return conv.conversation_id

    async def switch_conversation(
        self, session_id: str, conversation_id: str
    ) -> None:
        """切换会话的当前活跃对话"""
        self._session_conv_map[session_id] = conversation_id

    async def delete_conversation(
        self, session_id: str, conversation_id: str | None = None
    ) -> None:
        """删除对话。

        如果 conversation_id 为 None，则删除当前活跃对话。
        删除后如果等于当前对话则自动解绑。
        """
        cid = conversation_id or self._session_conv_map.get(session_id)
        if not cid:
            return
        await self._store.delete(cid)
        if self._session_conv_map.get(session_id) == cid:
            self._session_conv_map.pop(session_id, None)

    async def delete_session(self, session_id: str) -> None:
        """删除整个会话及其所有对话"""
        await self._store.delete_by_session(session_id)
        self._session_conv_map.pop(session_id, None)
        await self._trigger_session_deleted(session_id)

    # ── 查询接口 ─────────────────────────────────────

    async def get_current_conversation_id(
        self, session_id: str
    ) -> str | None:
        """获取会话的当前活跃对话 ID"""
        return self._session_conv_map.get(session_id)

    async def get_conversation(
        self,
        session_id: str,
        conversation_id: str,
        auto_create: bool = False,
    ) -> Conversation | None:
        """获取指定对话。

        Args:
            session_id: 会话 ID
            conversation_id: 对话 ID
            auto_create: 如果对话不存在，是否自动创建
        """
        conv = await self._store.get(conversation_id)
        if conv is None and auto_create:
            new_cid = await self.new_conversation(session_id)
            conv = await self._store.get(new_cid)
        return conv

    async def list_conversations(
        self, session_id: str, page: int = 1, page_size: int = 20
    ) -> tuple[list[Conversation], int]:
        """分页列出会话下的所有对话"""
        return await self._store.list_by_session(session_id, page, page_size)

    async def update_conversation(
        self,
        session_id: str,
        history: list[dict[str, Any]] | None = None,
        title: str | None = None,
        persona_id: str | None = None,
        token_usage: int | None = None,
        conversation_id: str | None = None,
    ) -> None:
        """更新对话数据和元数据"""
        cid = conversation_id or await self.get_current_conversation_id(session_id)
        if not cid:
            return
        await self._store.update(
            conversation_id=cid,
            history=history,
            title=title,
            persona_id=persona_id,
            token_usage=token_usage,
        )

    # ── 对话消息操作 ─────────────────────────────────

    async def add_message_pair(
        self,
        session_id: str,
        user_msg: dict[str, Any],
        assistant_msg: dict[str, Any],
        conversation_id: str | None = None,
    ) -> None:
        """向对话历史追加一轮 user + assistant 消息对"""
        cid = conversation_id or await self.get_current_conversation_id(session_id)
        if not cid:
            logger.warning(
                "No active conversation for session '%s'", session_id
            )
            return
        conv = await self._store.get(cid)
        if not conv:
            return
        conv.history.append(user_msg)
        conv.history.append(assistant_msg)
        await self._store.update(
            conversation_id=cid, history=conv.history
        )

    async def get_human_readable_context(
        self,
        session_id: str,
        conversation_id: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[str], int]:
        """获取人类可读的对话历史（分页）。

        Returns:
            (格式化消息列表, 总页数)
        """
        cid = conversation_id or await self.get_current_conversation_id(session_id)
        if not cid:
            return [], 0
        conv = await self._store.get(cid)
        if not conv:
            return [], 0

        # 按轮次分组
        turns: list[list[str]] = []
        current_turn: list[str] = []
        for msg in conv.history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                current_turn.append(f"User: {content}")
            elif role == "assistant":
                if content:
                    current_turn.append(f"Assistant: {content}")
                elif "tool_calls" in msg:
                    import json
                    tc = json.dumps(msg["tool_calls"], ensure_ascii=False)
                    current_turn.append(f"Assistant: [Tool Call] {tc}")
                turns.append(list(current_turn))
                current_turn = []

        # 展平
        flat = [item for turn in turns for item in turn]

        # 分页
        total_pages = max(1, (len(flat) + page_size - 1) // page_size)
        start = (page - 1) * page_size
        return flat[start : start + page_size], total_pages
