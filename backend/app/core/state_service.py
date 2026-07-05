"""
State Persistence Service — VS Code 风格全局/工作区状态持久化

对标: vscode/src/vs/platform/state/ + vscode/src/vs/workbench/services/storage/
支持: globalState (全局), workspaceState (工作区), 带TTL的临时状态
存储: SQLite WAL 模式, 按 workspace 隔离
"""

from __future__ import annotations
import time, threading, json, sqlite3
from typing import Any, Optional
from dataclasses import dataclass, field

@dataclass
class StateEntry:
    key: str
    value: Any
    scope: str  # global / workspace / session
    ttl: float = 0.0  # 0 = 永不过期
    updated_at: float = field(default_factory=time.time)

class StateService:
    """全局/工作区状态持久化服务"""

    _instance: Optional["StateService"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls, db_path: str = ":memory:") -> "StateService":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(db_path)
        return cls._instance

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._memory: dict[str, dict[str, StateEntry]] = {
            "global": {},
            "workspace": {},
            "session": {},
        }

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                scope TEXT NOT NULL,
                workspace_id TEXT NOT NULL DEFAULT '',
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'string',
                ttl REAL NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL,
                PRIMARY KEY (scope, workspace_id, key)
            )
        """)
        conn.commit()
        return conn

    def _serialize(self, value: Any) -> tuple[str, str]:
        if isinstance(value, bool):
            return ('true' if value else 'false', 'bool')
        if isinstance(value, (int, float)):
            return (str(value), 'number')
        if value is None:
            return ('null', 'null')
        if isinstance(value, (dict, list)):
            return (json.dumps(value), 'json')
        return (str(value), 'string')

    def _deserialize(self, val: str, vtype: str) -> Any:
        if vtype == 'bool':
            return val == 'true'
        if vtype == 'number':
            return float(val) if '.' in val else int(val)
        if vtype == 'null':
            return None
        if vtype == 'json':
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return val
        return val

    # ---- 全局状态 (globalStorage) ----

    def set_global(self, key: str, value: Any, ttl: float = 0, persist: bool = True) -> None:
        entry = StateEntry(key=key, value=value, scope="global", ttl=ttl)
        self._memory["global"][key] = entry
        if persist:
            self._persist("global", "", entry)

    def get_global(self, key: str, default: Any = None) -> Any:
        entry = self._memory["global"].get(key)
        if entry and not self._is_expired(entry):
            return entry.value
        return default

    def delete_global(self, key: str) -> None:
        self._memory["global"].pop(key, None)
        try:
            conn = self._get_db()
            conn.execute("DELETE FROM app_state WHERE scope='global' AND key=?", (key,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    # ---- 工作区状态 (workspaceStorage) ----

    def set_workspace(self, workspace_id: str, key: str, value: Any, ttl: float = 0) -> None:
        entry = StateEntry(key=key, value=value, scope="workspace", ttl=ttl)
        if workspace_id not in self._memory["workspace"]:
            self._memory["workspace"][workspace_id] = {}
        self._memory["workspace"][workspace_id][key] = entry
        self._persist("workspace", workspace_id, entry)

    def get_workspace(self, workspace_id: str, key: str, default: Any = None) -> Any:
        ws = self._memory["workspace"].get(workspace_id, {})
        entry = ws.get(key)
        if entry and not self._is_expired(entry):
            return entry.value
        return default

    def delete_workspace(self, workspace_id: str, key: str) -> None:
        ws = self._memory["workspace"].get(workspace_id, {})
        ws.pop(key, None)
        try:
            conn = self._get_db()
            conn.execute(
                "DELETE FROM app_state WHERE scope='workspace' AND workspace_id=? AND key=?",
                (workspace_id, key)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def list_workspace(self, workspace_id: str) -> dict[str, Any]:
        ws = self._memory["workspace"].get(workspace_id, {})
        return {k: v.value for k, v in ws.items() if not self._is_expired(v)}

    # ---- 会话状态 (内存, 不持久化) ----

    def set_session(self, key: str, value: Any) -> None:
        entry = StateEntry(key=key, value=value, scope="session")
        self._memory["session"][key] = entry

    def get_session(self, key: str, default: Any = None) -> Any:
        return self._memory["session"].get(key, StateEntry(key="", value=default)).value

    def delete_session(self, key: str) -> None:
        self._memory["session"].pop(key, None)

    # ---- 批量 & 清理 ----

    def flush(self) -> None:
        """强制持久化所有内存中的状态"""
        for entry in self._memory["global"].values():
            self._persist("global", "", entry)
        for ws_id, ws in self._memory["workspace"].items():
            for entry in ws.values():
                self._persist("workspace", ws_id, entry)

    def cleanup_expired(self) -> int:
        """清理所有过期状态, 返回清理数量"""
        count = 0
        now = time.time()
        for scope_map in self._memory.values():
            for ws_id in list(scope_map.keys()):
                ws = scope_map[ws_id] if isinstance(scope_map[ws_id], dict) else {"_": scope_map[ws_id]}
                for key in list(ws.keys()):
                    if self._is_expired(ws[key]):
                        del ws[key]
                        count += 1
        try:
            conn = self._get_db()
            conn.execute("DELETE FROM app_state WHERE ttl > 0 AND ? - updated_at > ttl", (now))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return count

    def clear_all(self, workspace_id: str = "") -> None:
        """清除所有状态"""
        self._memory = {"global": {}, "workspace": {}, "session": {}}
        try:
            conn = self._get_db()
            if workspace_id:
                conn.execute("DELETE FROM app_state WHERE workspace_id=?", (workspace_id,))
            else:
                conn.execute("DELETE FROM app_state")
            conn.commit()
            conn.close()
        except Exception:
            pass

    # ---- 内部方法 ----

    def _persist(self, scope: str, workspace_id: str, entry: StateEntry) -> None:
        try:
            val_str, vtype = self._serialize(entry.value)
            conn = self._get_db()
            conn.execute(
                """INSERT OR REPLACE INTO app_state
                   (scope, workspace_id, key, value, value_type, ttl, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (scope, workspace_id, entry.key, val_str, vtype, entry.ttl, entry.updated_at)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    @staticmethod
    def _is_expired(entry: StateEntry) -> bool:
        if entry.ttl <= 0:
            return False
        return (time.time() - entry.updated_at) > entry.ttl


# 全局快捷方法
def state() -> StateService:
    return StateService.get_instance()
