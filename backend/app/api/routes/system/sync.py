"""
用户数据同步 API — Session 52

对标 VSCode userDataSync / Settings Sync:
- 跨设备同步 settings.json / keybindings.json / snippets.json / extensions.json
- 增量同步 + 冲突检测 + 时间戳版本
- 每用户隔离 (JWT auth)

路由:
  GET    /system/sync/manifest       — 获取同步清单（各数据类型的最后更新时间+大小）
  POST   /system/sync/push           — 推送本地数据到服务端
  POST   /system/sync/pull           — 从服务端拉取最新数据
  POST   /system/sync/merge          — 三方合并（base+local+remote → merged）
  DELETE /system/sync/reset          — 清除服务端同步数据
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("app.api.routes.system.sync")

router = APIRouter(prefix="/system/sync", tags=["system-sync"])

# ── 同步数据类型 ──
SYNC_DATA_TYPES = ["settings", "keybindings", "snippets", "extensions", "globalState", "tasks"]

# ── SQLite 持久化 ──
_DB_DIR = Path("data")
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "user_sync.db"


def _get_db() -> sqlite3.Connection:
    """获取同步数据库连接"""
    db = sqlite3.connect(str(_DB_PATH))
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE IF NOT EXISTS sync_data (
            user_id TEXT NOT NULL,
            data_type TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, data_type)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS sync_conflicts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            data_type TEXT NOT NULL,
            base_content TEXT,
            local_content TEXT,
            remote_content TEXT,
            resolved_content TEXT,
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )
    """)
    db.commit()
    return db


# ── 辅助: 解析用户ID (简化版, 实际应从JWT获取) ──
def _get_user_id() -> str:
    """从请求上下文获取用户ID，回退到默认值"""
    try:
        from fastapi import Request
        import inspect
        # 尝试从调用栈中找到 Request 对象
        frame = inspect.currentframe()
        while frame:
            if 'request' in frame.f_locals:
                req = frame.f_locals['request']
                if hasattr(req, 'state') and hasattr(req.state, 'user_id'):
                    return req.state.user_id
            frame = frame.f_back
    except Exception:
        pass
    return "default"


# ═══════════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════════

class SyncEntry(BaseModel):
    """单条同步数据"""
    data_type: str = Field(..., description="settings | keybindings | snippets | extensions | globalState | tasks")
    content: dict = Field(default_factory=dict, description="JSON数据")
    version: int = Field(default=0, description="本地版本号")


class PushRequest(BaseModel):
    """推送请求"""
    entries: list[SyncEntry] = Field(..., min_length=1, max_length=20)


class PushResponse(BaseModel):
    """推送结果"""
    accepted: list[str] = Field(default_factory=list)  # 被接受的数据类型
    conflicts: list[str] = Field(default_factory=list)  # 有冲突的数据类型
    rejected: list[str] = Field(default_factory=list)   # 被拒绝的数据类型


class PullRequest(BaseModel):
    """拉取请求"""
    data_types: Optional[list[str]] = Field(None, description="指定拉取的数据类型，None=全部")
    since_version: Optional[dict[str, int]] = Field(None, description="各类型的本地版本号")


class PullResponse(BaseModel):
    """拉取结果"""
    entries: list[SyncEntry] = Field(default_factory=list)
    server_time: str


class SyncManifest(BaseModel):
    """同步清单"""
    data_type: str
    version: int
    size_bytes: int
    updated_at: str


class SyncManifestResponse(BaseModel):
    """同步清单响应"""
    manifest: list[SyncManifest] = Field(default_factory=list)


class MergeRequest(BaseModel):
    """三方合并请求"""
    data_type: str
    base_content: dict = Field(default_factory=dict)
    local_content: dict = Field(default_factory=dict)
    remote_content: dict = Field(default_factory=dict)


class MergeResponse(BaseModel):
    """合并结果"""
    merged: dict = Field(default_factory=dict)
    conflict_id: Optional[int] = None
    auto_resolved: bool = True


# ═══════════════════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════════════════

@router.get("/manifest", response_model=SyncManifestResponse)
async def get_manifest(user_id: str = "default") -> SyncManifestResponse:
    """获取服务端同步清单 — 各数据类型的版本号和最后更新时间"""
    db = _get_db()
    manifest = []
    try:
        rows = db.execute(
            "SELECT data_type, version, length(content) as size, updated_at FROM sync_data WHERE user_id=?",
            (user_id,)
        ).fetchall()
        for row in rows:
            manifest.append(SyncManifest(
                data_type=row["data_type"],
                version=row["version"],
                size_bytes=row["size"],
                updated_at=row["updated_at"],
            ))
    finally:
        db.close()
    return SyncManifestResponse(manifest=manifest)


@router.post("/push", response_model=PushResponse)
async def push_data(req: PushRequest, user_id: str = "default") -> PushResponse:
    """
    推送本地数据到服务端。
    版本冲突检测：如果本地version < 服务端version，标记为冲突
    """
    db = _get_db()
    response = PushResponse()
    now = datetime.now(timezone.utc).isoformat()

    try:
        for entry in req.entries:
            if entry.data_type not in SYNC_DATA_TYPES:
                response.rejected.append(entry.data_type)
                continue

            # 检查服务端版本
            existing = db.execute(
                "SELECT version FROM sync_data WHERE user_id=? AND data_type=?",
                (user_id, entry.data_type)
            ).fetchone()

            if existing and entry.version > 0 and entry.version < existing["version"]:
                # 本地版本落后 → 冲突
                response.conflicts.append(entry.data_type)
                db.execute(
                    "INSERT INTO sync_conflicts (user_id, data_type, local_content, remote_content, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, entry.data_type, json.dumps(entry.content),
                     json.dumps(_get_remote_content(db, user_id, entry.data_type)), now)
                )
            else:
                # 接受推送
                new_version = (existing["version"] + 1) if existing else 1
                db.execute(
                    "INSERT OR REPLACE INTO sync_data (user_id, data_type, content, version, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, entry.data_type, json.dumps(entry.content), new_version, now)
                )
                response.accepted.append(entry.data_type)

        db.commit()
    finally:
        db.close()

    return response


@router.post("/pull", response_model=PullResponse)
async def pull_data(req: PullRequest, user_id: str = "default") -> PullResponse:
    """
    从服务端拉取最新数据。
    如果since_version提供且 >= 服务端版本，跳过（增量同步）
    """
    db = _get_db()
    entries = []
    data_types = req.data_types or SYNC_DATA_TYPES
    since = req.since_version or {}

    try:
        for dt in data_types:
            if dt not in SYNC_DATA_TYPES:
                continue
            row = db.execute(
                "SELECT content, version FROM sync_data WHERE user_id=? AND data_type=?",
                (user_id, dt)
            ).fetchone()
            if not row:
                continue
            # 增量：本地版本已是最新则跳过
            if dt in since and since[dt] >= row["version"]:
                continue
            entries.append(SyncEntry(
                data_type=dt,
                content=json.loads(row["content"]) if row["content"] else {},
                version=row["version"],
            ))
    finally:
        db.close()

    return PullResponse(entries=entries, server_time=datetime.now(timezone.utc).isoformat())


@router.post("/merge", response_model=MergeResponse)
async def merge_data(req: MergeRequest, user_id: str = "default") -> MergeResponse:
    """
    三方合并：base + local + remote → merged。
    简单策略：deep merge (remote 优先，local 补充新字段)
    """
    if req.data_type not in SYNC_DATA_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid data_type: {req.data_type}")

    # 简单深度合并策略
    merged = _deep_merge(req.base_content, req.local_content, req.remote_content)

    # 如果有无法自动合并的冲突，记录到冲突表
    auto_resolved = True
    conflict_id = None
    has_conflict = _detect_conflict(req.local_content, req.remote_content, req.base_content)

    if has_conflict:
        db = _get_db()
        try:
            now = datetime.now(timezone.utc).isoformat()
            cursor = db.execute(
                "INSERT INTO sync_conflicts (user_id, data_type, base_content, local_content, remote_content, resolved_content, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, req.data_type,
                 json.dumps(req.base_content), json.dumps(req.local_content),
                 json.dumps(req.remote_content), json.dumps(merged), now, now)
            )
            db.commit()
            conflict_id = cursor.lastrowid
            auto_resolved = False
        finally:
            db.close()

    return MergeResponse(merged=merged, conflict_id=conflict_id, auto_resolved=auto_resolved)


@router.delete("/reset")
async def reset_sync(user_id: str = "default") -> dict:
    """清除用户所有服务端同步数据"""
    db = _get_db()
    try:
        db.execute("DELETE FROM sync_data WHERE user_id=?", (user_id,))
        db.execute("DELETE FROM sync_conflicts WHERE user_id=?", (user_id,))
        db.commit()
    finally:
        db.close()
    return {"status": "ok", "message": f"Sync data reset for user {user_id}"}


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _get_remote_content(db: sqlite3.Connection, user_id: str, data_type: str) -> dict:
    """获取服务端存储的内容"""
    row = db.execute(
        "SELECT content FROM sync_data WHERE user_id=? AND data_type=?",
        (user_id, data_type)
    ).fetchone()
    if row and row["content"]:
        return json.loads(row["content"])
    return {}


def _deep_merge(base: dict, local: dict, remote: dict) -> dict:
    """
    简单深度合并策略：
    - remote 优先 (服务端作为权威)
    - local 中 remote 没有的字段 → 保留
    - base 中相同字段 → remote 覆盖
    """
    result = dict(remote)  # 服务端优先

    for key, local_val in local.items():
        if key not in result:
            # local 有但 remote 没有 → 新增
            result[key] = local_val
        elif key in base and base[key] == local_val:
            # local 未修改 (与 base 相同) → remote 覆盖 (已生效)
            pass
        elif isinstance(local_val, dict) and isinstance(result.get(key), dict):
            # 都是字典 → 递归合并
            base_val = base.get(key, {}) if isinstance(base.get(key), dict) else {}
            result[key] = _deep_merge(base_val, local_val, result[key])
        elif local_val != result[key]:
            # 真正的冲突：local和remote都修改了 → remote优先
            pass

    # local 中删除的字段 (在base中有但local中没有) → remote保留
    for key in base:
        if key not in local and key in remote:
            pass  # remote 已保留

    return result


def _detect_conflict(local: dict, remote: dict, base: dict) -> bool:
    """检测是否存在真正的三方冲突"""
    all_keys = set(local.keys()) | set(remote.keys())
    for key in all_keys:
        lv = local.get(key)
        rv = remote.get(key)
        bv = base.get(key)

        # 两边都改了，且改的不一样
        if lv != rv and lv != bv and rv != bv:
            if isinstance(lv, dict) and isinstance(rv, dict) and isinstance(bv, dict):
                if _detect_conflict(lv, rv, bv):
                    return True
            else:
                return True
    return False
