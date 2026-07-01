"""
消息历史持久化单元测试

覆盖:
  - SqliteMessageHistoryStore CRUD (insert/get/update/delete)
  - MemoryMessageHistoryStore CRUD
  - PlatformMessageHistoryManager 分页查询
  - 旧记录清理 (delete_older_than)
  - 数据重启持久化验证

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


# ── Test Runner ──────────────────────────────────────





async def test_sqlite_store_crud():
    """SQLite 消息历史存储 — 完整 CRUD"""
    from app.core.message_history import (
        SqliteMessageHistoryStore, MessageRecord,
    )
    import time

    # 临时数据库
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SqliteMessageHistoryStore(db_path)

        # 插入
        record = MessageRecord(
            message_id="msg-001",
            platform_id="test-platform",
            session_id="sess-001",
            sender_id="user-1",
            sender_name="TestUser",
            content={"role": "user", "text": "Hello"},
            timestamp=time.time(),
        )
        result = await store.insert(record)
        assert_equal(result.message_id, "msg-001", "insert — 返回消息 ID 正确")

        # 查询
        records = await store.get(session_id="sess-001", page=1, page_size=10)
        assert_true(len(records) > 0, "get — 查询返回记录")
        if records:
            assert_equal(records[0].sender_name, "TestUser", "get — 发送者名称正确")

        # 更新
        await store.update(message_id="msg-001", content={"role": "user", "text": "Updated"})
        updated = await store.get(session_id="sess-001", page=1, page_size=10)
        assert_true(len(updated) > 0, "update — 更新后仍可查询")
        if updated:
            assert_equal(updated[0].content.get("text"), "Updated", "update — 内容已更新")

        # 删除
        await store.delete_by_id("msg-001")
        after_del = await store.get(session_id="sess-001", page=1, page_size=10)
        assert_equal(len(after_del), 0, "delete — 删除后记录为空")

    finally:
        try:
            store._db.close()
        except Exception:
            pass
        os.unlink(db_path)


async def test_sqlite_store_pagination():
    """SQLite 消息历史存储 — 分页查询"""
    from app.core.message_history import (
        SqliteMessageHistoryStore, MessageRecord,
    )
    import time
    import uuid

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SqliteMessageHistoryStore(db_path)

        # 插入 25 条记录
        for i in range(25):
            record = MessageRecord(
                message_id=uuid.uuid4().hex,
                platform_id="pag-platform",
                session_id="sess-pag",
                content={"index": i, "text": f"Message {i}"},
                timestamp=time.time() - (25 - i) * 10,
            )
            await store.insert(record)

        # Page 1: 20 条
        page1 = await store.get(session_id="sess-pag", page=1, page_size=20)
        assert_equal(len(page1), 20, "分页 — page=1 返回 20 条")

        # Page 2: 5 条
        page2 = await store.get(session_id="sess-pag", page=2, page_size=20)
        assert_equal(len(page2), 5, "分页 — page=2 返回 5 条")

        # Page 3: 0 条
        page3 = await store.get(session_id="sess-pag", page=3, page_size=20)
        assert_equal(len(page3), 0, "分页 — page=3 返回 0 条")

        # 倒序验证（最新在前）
        if len(page1) >= 2:
            # 按 index 降序排列：最新消息有最大的 index
            assert_true(
                page1[0].content["index"] > page1[1].content["index"],
                "分页 — 结果按时间倒序排列",
            )

    finally:
        try:
            store._db.close()
        except Exception:
            pass
        os.unlink(db_path)


async def test_memory_store_crud():
    """内存消息历史存储 — 完整 CRUD"""
    from app.core.message_history import (
        MemoryMessageHistoryStore, MessageRecord,
    )
    import time

    store = MemoryMessageHistoryStore(max_records=100)

    # 插入
    record = MessageRecord(
        message_id="mem-001",
        platform_id="mem-platform",
        session_id="mem-sess",
        content={"text": "Memory test"},
        timestamp=time.time(),
    )
    await store.insert(record)

    records = await store.get(session_id="mem-sess")
    assert_equal(len(records), 1, "MemoryStore — 查询返回 1 条")
    assert_equal(records[0].message_id, "mem-001", "MemoryStore — 消息 ID 正确")

    # 更新
    await store.update(message_id="mem-001", content={"text": "Updated memory"})
    updated = await store.get(session_id="mem-sess")
    assert_equal(updated[0].content["text"], "Updated memory", "MemoryStore — 内容已更新")

    # 删除
    await store.delete_by_id("mem-001")
    after = await store.get(session_id="mem-sess")
    assert_equal(len(after), 0, "MemoryStore — 删除后为空")


async def test_platform_manager_integration():
    """PlatformMessageHistoryManager 集成测试"""
    from app.core.message_history import (
        MemoryMessageHistoryStore,
        PlatformMessageHistoryManager,
    )

    store = MemoryMessageHistoryStore()
    mgr = PlatformMessageHistoryManager(store=store)

    # 插入
    record = await mgr.insert(
        session_id="integration-sess",
        content={"role": "user", "text": "Integration test"},
        platform_id="test",
        sender_name="tester",
    )
    assert_true(len(record.message_id) > 0, "Manager — 自动生成 message_id")

    # 查询
    history = await mgr.get_history(session_id="integration-sess")
    assert_equal(len(history), 1, "Manager — 历史查询返回 1 条")
    assert_equal(history[0].sender_name, "tester", "Manager — 发送者名称正确")

    # 删除
    await mgr.delete_by_id(record.message_id)
    after = await mgr.get_history(session_id="integration-sess")
    assert_equal(len(after), 0, "Manager — 删除后为空")


async def test_delete_older_than():
    """旧记录清理测试"""
    from app.core.message_history import (
        SqliteMessageHistoryStore, MessageRecord,
    )
    import time
    import uuid

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SqliteMessageHistoryStore(db_path)

        # 插入 2 条：一个旧（2 小时前），一个新（现在）
        old_record = MessageRecord(
            message_id=uuid.uuid4().hex,
            platform_id="old-platform",
            session_id="clean-sess",
            content={"text": "Old message"},
            timestamp=time.time() - 7200,  # 2 小时前
        )
        new_record = MessageRecord(
            message_id=uuid.uuid4().hex,
            platform_id="old-platform",
            session_id="clean-sess",
            content={"text": "New message"},
            timestamp=time.time(),
        )
        await store.insert(old_record)
        await store.insert(new_record)

        # 1 小时前
        deleted = await store.delete_older_than("clean-sess", max_age_seconds=3600)
        assert_equal(deleted, 1, "清理 — 删除 1 条旧记录")

        # 应该只剩新记录
        remaining = await store.get(session_id="clean-sess")
        assert_equal(len(remaining), 1, "清理 — 剩余 1 条新记录")
        assert_equal(remaining[0].content["text"], "New message", "清理 — 新记录保留")

    finally:
        try:
            store._db.close()
        except Exception:
            pass
        os.unlink(db_path)


async def test_sqlite_persistence():
    """SQLite 持久化验证：模拟重启"""
    from app.core.message_history import (
        SqliteMessageHistoryStore, MessageRecord,
    )
    import time

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        # 第一次写入
        store1 = SqliteMessageHistoryStore(db_path)
        record = MessageRecord(
            message_id="persist-001",
            platform_id="persist",
            session_id="persist-sess",
            content={"text": "Persist me"},
            timestamp=time.time(),
        )
        await store1.insert(record)
        # 关闭连接
        store1._db.close()

        # 模拟重启：新连接读取
        store2 = SqliteMessageHistoryStore(db_path)
        records = await store2.get(session_id="persist-sess")
        assert_equal(len(records), 1, "持久化 — 重启后数据仍在")
        assert_equal(records[0].content["text"], "Persist me", "持久化 — 内容未丢失")
        store2._db.close()

    finally:
        os.unlink(db_path)


# ── Main ─────────────────────────────────────────────


async def _main():
    print("=" * 60)
    print("Message History 持久化单元测试")
    print("=" * 60)

    print("\n[1/6] SQLite Store CRUD")
    await test_sqlite_store_crud()

    print("\n[2/6] SQLite Store 分页查询")
    await test_sqlite_store_pagination()

    print("\n[3/6] Memory Store CRUD")
    await test_memory_store_crud()

    print("\n[4/6] PlatformManager 集成")
    await test_platform_manager_integration()

    print("\n[5/6] 旧记录清理")
    await test_delete_older_than()

    print("\n[6/6] SQLite 持久化验证")
    await test_sqlite_persistence()

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
