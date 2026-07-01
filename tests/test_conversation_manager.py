"""
对话管理器单元测试

覆盖:
  - SqliteConversationStore CRUD (create/get/update/delete/list)
  - MemoryConversationStore CRUD
  - ConversationManager 对话生命周期 (new/switch/delete)
  - 会话级联删除
  - 对话消息对追加
  - 分页列表

所有测试使用临时目录，零副作用。
"""
import sys
import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(str(PROJECT_ROOT))

import asyncio

PASS = 0
FAIL = 0


def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  [PASS] {label}")


def _fail(label: str, expected=None, got=None) -> None:
    global FAIL
    FAIL += 1
    detail = f": expected={expected}, got={got}" if expected is not None else ""
    print(f"  [FAIL] {label}{detail}")


def assert_equal(actual, expected, label):
    if actual == expected:
        _ok(label)
    else:
        _fail(label, expected, actual)


def assert_true(cond, label):
    if cond:
        _ok(label)
    else:
        _fail(label)


def assert_is_not_none(val, label):
    if val is not None:
        _ok(label)
    else:
        _fail(label, "not None", "None")





# ── SqliteConversationStore 测试 ────────────────────


async def test_sqlite_store_crud():
    """SQLite 对话存储 — 完整 CRUD"""
    from app.core.conversation.manager import (
        SqliteConversationStore, Conversation,
    )

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SqliteConversationStore(db_path)

        # 创建
        conv = Conversation(
            session_id="sql-sess",
            platform_id="test",
            title="Test Conversation",
            history=[{"role": "user", "content": "Hello"}],
        )
        result = await store.create(conv)
        assert_equal(result.title, "Test Conversation", "create — 标题正确")

        # 读取
        fetched = await store.get(conv.conversation_id)
        assert_is_not_none(fetched, "get — 可正常读取")
        if fetched:
            assert_equal(fetched.session_id, "sql-sess", "get — session_id 正确")
            assert_equal(len(fetched.history), 1, "get — 历史消息 1 条")

        # 更新
        await store.update(
            conversation_id=conv.conversation_id,
            title="Updated Title",
            history=[{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi"}],
        )
        updated = await store.get(conv.conversation_id)
        if updated:
            assert_equal(updated.title, "Updated Title", "update — 标题已更新")
            assert_equal(len(updated.history), 2, "update — 历史消息 2 条")

        # 删除
        await store.delete(conv.conversation_id)
        after_del = await store.get(conv.conversation_id)
        assert_equal(after_del, None, "delete — 删除后读取为 None")

    finally:
        try:
            store._db.close()
        except Exception:
            pass
        os.unlink(db_path)


async def test_sqlite_store_list():
    """SQLite 对话存储 — 分页列表"""
    from app.core.conversation.manager import (
        SqliteConversationStore, Conversation,
    )
    import time

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SqliteConversationStore(db_path)

        # 插入 15 条
        for i in range(15):
            conv = Conversation(
                session_id="list-sess",
                platform_id="test",
                title=f"Convo {i}",
                created_at=time.time() - (15 - i) * 60,
                updated_at=time.time() - (15 - i) * 60,
            )
            await store.create(conv)

        # 分页查询
        page1, total = await store.list_by_session("list-sess", page=1, page_size=10)
        assert_equal(len(page1), 10, "list — page=1 返回 10 条")
        assert_equal(total, 15, "list — 总数 15 条")

        page2, _ = await store.list_by_session("list-sess", page=2, page_size=10)
        assert_equal(len(page2), 5, "list — page=2 返回 5 条")

        # 排序验证（最新在前）
        if len(page1) >= 2:
            assert_true(
                page1[0].updated_at >= page1[1].updated_at,
                "list — 按更新时间倒序排列",
            )

    finally:
        try:
            store._db.close()
        except Exception:
            pass
        os.unlink(db_path)


async def test_sqlite_store_delete_by_session():
    """SQLite 对话存储 — 级联删除会话下所有对话"""
    from app.core.conversation.manager import (
        SqliteConversationStore, Conversation,
    )

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SqliteConversationStore(db_path)

        # 两个会话各 3 个对话
        for i in range(3):
            await store.create(Conversation(session_id="cascade-sess", title=f"Cascade {i}"))
        for i in range(3):
            await store.create(Conversation(session_id="keep-sess", title=f"Keep {i}"))

        # 级联删除 cascade-sess
        await store.delete_by_session("cascade-sess")

        # cascade-sess 应该为空
        remaining_cascade, total_cascade = await store.list_by_session("cascade-sess")
        assert_equal(total_cascade, 0, "delete_by_session — 目标会话全部清除")

        # keep-sess 应该不受影响
        remaining_keep, total_keep = await store.list_by_session("keep-sess")
        assert_equal(total_keep, 3, "delete_by_session — 其他会话不受影响")

    finally:
        try:
            store._db.close()
        except Exception:
            pass
        os.unlink(db_path)


# ── MemoryConversationStore 测试 ────────────────────


async def test_memory_store_crud():
    """内存对话存储 — 完整 CRUD"""
    from app.core.conversation.manager import (
        MemoryConversationStore, Conversation,
    )

    store = MemoryConversationStore()

    conv = Conversation(
        session_id="mem-sess",
        title="Memory Test",
    )
    await store.create(conv)

    fetched = await store.get(conv.conversation_id)
    assert_is_not_none(fetched, "MemoryStore — 可正常读取")

    await store.update(conversation_id=conv.conversation_id, title="Updated")
    updated = await store.get(conv.conversation_id)
    if updated:
        assert_equal(updated.title, "Updated", "MemoryStore — 已更新")

    await store.delete(conv.conversation_id)
    assert_equal(await store.get(conv.conversation_id), None, "MemoryStore — 已删除")


# ── ConversationManager 集成测试 ────────────────────


async def test_manager_lifecycle():
    """ConversationManager 对话生命周期管理"""
    from app.core.conversation.manager import (
        MemoryConversationStore, ConversationManager,
    )

    store = MemoryConversationStore()
    mgr = ConversationManager(store=store)

    # 创建新对话
    cid = await mgr.new_conversation(
        session_id="lifecycle-sess",
        platform_id="test",
        title="Lifecycle Test",
    )
    assert_true(len(cid) > 0, "new_conversation — 返回有效 ID")

    # 当前活跃对话
    active_id = await mgr.get_current_conversation_id("lifecycle-sess")
    assert_equal(active_id, cid, "get_current — 活跃对话为刚创建的对话")

    # 创建第二个对话
    cid2 = await mgr.new_conversation(session_id="lifecycle-sess", title="Second")
    assert_true(cid != cid2, "new_conversation — 新建对话 ID 不重复")
    new_active = await mgr.get_current_conversation_id("lifecycle-sess")
    assert_equal(new_active, cid2, "get_current — 活跃切换为新对话")

    # 切换到第一个对话
    await mgr.switch_conversation("lifecycle-sess", cid)
    switched = await mgr.get_current_conversation_id("lifecycle-sess")
    assert_equal(switched, cid, "switch — 手动切换成功")

    # 删除当前活跃对话
    await mgr.delete_conversation("lifecycle-sess", cid)
    deleted = await mgr.get_current_conversation_id("lifecycle-sess")
    assert_equal(deleted, None, "delete — 删除后当前活跃解绑")


async def test_manager_add_message_pair():
    """ConversationManager 消息对追加"""
    from app.core.conversation.manager import (
        MemoryConversationStore, ConversationManager,
    )

    store = MemoryConversationStore()
    mgr = ConversationManager(store=store)

    cid = await mgr.new_conversation(session_id="msg-sess", title="Message Test")

    # 追加一轮对话
    user_msg = {"role": "user", "content": "Hello AI"}
    assistant_msg = {"role": "assistant", "content": "Hello Human"}
    await mgr.add_message_pair(session_id="msg-sess", user_msg=user_msg, assistant_msg=assistant_msg)

    # 验证
    conv = await store.get(cid)
    assert_is_not_none(conv, "add_message_pair — 对话存在")
    if conv:
        assert_equal(len(conv.history), 2, "add_message_pair — 历史 2 条")
        assert_equal(conv.history[0]["content"], "Hello AI", "add_message_pair — 用户消息正确")
        assert_equal(conv.history[1]["content"], "Hello Human", "add_message_pair — AI 消息正确")


async def test_manager_session_delete():
    """ConversationManager 会话级联删除"""
    from app.core.conversation.manager import (
        MemoryConversationStore, ConversationManager,
    )

    store = MemoryConversationStore()
    mgr = ConversationManager(store=store)

    # 创建 3 个对话
    for i in range(3):
        await mgr.new_conversation(session_id="del-sess", title=f"Del {i}")

    convs, total = await store.list_by_session("del-sess")
    assert_equal(total, 3, "session_delete — 删除前 3 个对话")

    # 级联删除整个会话
    await mgr.delete_session("del-sess")

    convs, total = await store.list_by_session("del-sess")
    assert_equal(total, 0, "session_delete — 删除后 0 个对话")


async def test_sqlite_persistence():
    """SQLite 持久化验证：模拟重启"""
    from app.core.conversation.manager import (
        SqliteConversationStore, Conversation,
    )

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # 第一次写入
        store1 = SqliteConversationStore(db_path)
        conv = Conversation(session_id="persist", title="Persist Me")
        await store1.create(conv)
        cid = conv.conversation_id
        store1._db.close()

        # 模拟重启
        store2 = SqliteConversationStore(db_path)
        fetched = await store2.get(cid)
        assert_is_not_none(fetched, "持久化 — 重启后数据仍在")
        if fetched:
            assert_equal(fetched.title, "Persist Me", "持久化 — 标题未丢失")
        store2._db.close()

    finally:
        os.unlink(db_path)


# ── Main ─────────────────────────────────────────────


async def _main():
    print("=" * 60)
    print("Conversation Manager 单元测试")
    print("=" * 60)

    print("\n[1/8] SQLite Store CRUD")
    await test_sqlite_store_crud()

    print("\n[2/8] SQLite Store 分页列表")
    await test_sqlite_store_list()

    print("\n[3/8] SQLite Store 级联删除")
    await test_sqlite_store_delete_by_session()

    print("\n[4/8] Memory Store CRUD")
    await test_memory_store_crud()

    print("\n[5/8] Manager 生命周期")
    await test_manager_lifecycle()

    print("\n[6/8] Manager 消息对追加")
    await test_manager_add_message_pair()

    print("\n[7/8] Manager 会话级联删除")
    await test_manager_session_delete()

    print("\n[8/8] SQLite 持久化验证")
    await test_sqlite_persistence()

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
