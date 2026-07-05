"""
Local History API + Indentation Detection

对标: vscode/src/vs/workbench/contrib/localHistory/ + vs/platform/files/
- 文件本地历史: 按文件存储历史版本, 支持 diff/restore/prune
- 缩进检测: 从文件内容自动检测缩进类型和大小
"""

from __future__ import annotations
import os, time, hashlib, json, sqlite3, re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ==================== Indentation Detection ====================

@dataclass
class IndentInfo:
    """缩进检测结果"""
    indent_size: int = 2
    uses_tabs: bool = False
    confidence: float = 0.0
    mixed: bool = False  # 是否混用 tabs 和 spaces

    def to_dict(self) -> dict:
        return {
            "indentSize": self.indent_size,
            "usesTabs": self.uses_tabs,
            "confidence": round(self.confidence, 2),
            "mixed": self.mixed,
        }


def detect_indentation(content: str, sample_lines: int = 500) -> IndentInfo:
    """
    从文件内容自动检测缩进风格

    算法:
      1. 统计每行前导空格数和 tab 数
      2. 确定主导缩进类型 (spaces vs tabs)
      3. 如为空格, 计算最大公约数确定 size

    Returns:
        IndentInfo 缩进信息
    """
    lines = content.splitlines()[:sample_lines]

    tab_count = 0
    space_indents: list[int] = []
    space_lines = 0
    tab_lines = 0

    for line in lines:
        if not line or not line.strip():
            continue

        match = re.match(r'^(\s+)', line)
        if not match:
            # 无缩进行
            space_indents.append(0)
            continue

        prefix = match.group(1)
        tab_c = prefix.count('\t')
        space_c = prefix.count(' ')

        if tab_c > 0:
            tab_count += tab_c
            tab_lines += 1
        if space_c > 0:
            space_indents.append(space_c)
            space_lines += 1

    if not space_indents:
        space_indents = [0]

    # 移除零值
    non_zero = [s for s in space_indents if s > 0]
    if not non_zero:
        return IndentInfo(indent_size=2, uses_tabs=False, confidence=0.5)

    # 如果 tabs 比 spaces 多 → use tabs
    total_lines = tab_lines + space_lines
    if total_lines == 0:
        return IndentInfo(indent_size=2, uses_tabs=False, confidence=0.5)

    tab_ratio = tab_lines / total_lines if total_lines > 0 else 0
    uses_tabs = tab_count > len(non_zero)

    if uses_tabs:
        return IndentInfo(indent_size=4, uses_tabs=True, confidence=round(tab_ratio, 2),
                          mixed=space_lines > 0)

    # 空格模式: 用最大公约数确定 size
    unique_sizes = set(non_zero)
    indent_size = _gcd_list(list(unique_sizes))
    if indent_size < 1:
        indent_size = min(unique_sizes) if unique_sizes else 2
    if indent_size > 8:
        indent_size = 2  # 不合理的值, 回退

    confidence = space_lines / total_lines if total_lines > 0 else 0.5
    mixed = tab_lines > 0

    return IndentInfo(indent_size=indent_size, uses_tabs=False,
                      confidence=round(confidence, 2), mixed=mixed)


def _gcd(a: int, b: int) -> int:
    while b:
        a, b = b, a % b
    return a


def _gcd_list(nums: list[int]) -> int:
    if not nums:
        return 2
    result = nums[0]
    for n in nums[1:]:
        result = _gcd(result, n)
    return result


# ==================== Local History ====================

@dataclass
class FileSnapshot:
    id: str
    file_path: str
    content: str
    created_at: float = field(default_factory=time.time)
    size: int = 0
    label: str = ""  # "自动保存" / "编辑前" / user label

    def to_dict(self, include_content: bool = False) -> dict:
        d = {
            "id": self.id,
            "filePath": self.file_path,
            "createdAt": self.created_at,
            "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.created_at)),
            "size": self.size,
            "label": self.label,
        }
        if include_content:
            d["content"] = self.content
        return d


class LocalHistoryStore:
    """文件本地历史存储 (SQLite)"""

    def __init__(self, db_path: str = ":memory:", max_per_file: int = 50, max_age_days: int = 30):
        self._db_path = db_path
        self.max_per_file = max_per_file
        self.max_age_days = max_age_days

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_snapshots (
                id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                size INTEGER NOT NULL DEFAULT 0,
                label TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snapshots_file
            ON file_snapshots(file_path, created_at DESC)
        """)
        conn.commit()
        return conn

    def _hash_content(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def save_snapshot(self, file_path: str, content: str, label: str = "") -> FileSnapshot:
        """保存文件快照"""
        snap_id = self._hash_content(content + str(time.time()))
        snapshot = FileSnapshot(
            id=snap_id, file_path=file_path, content=content,
            size=len(content), label=label
        )

        try:
            conn = self._get_db()
            conn.execute(
                """INSERT OR REPLACE INTO file_snapshots
                   (id, file_path, content, created_at, size, label)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (snap_id, file_path, content, snapshot.created_at, snapshot.size, label)
            )
            conn.commit()
            conn.close()

            # 清理旧快照
            self._prune_file(file_path)
        except Exception:
            pass

        return snapshot

    def get_snapshots(self, file_path: str, limit: int = 50) -> list[dict]:
        """列出文件所有快照"""
        try:
            conn = self._get_db()
            rows = conn.execute(
                "SELECT id, created_at, size, label FROM file_snapshots "
                "WHERE file_path = ? ORDER BY created_at DESC LIMIT ?",
                (file_path, limit)
            ).fetchall()
            conn.close()
            return [
                {
                    "id": r[0],
                    "createdAt": r[1],
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r[1])),
                    "size": r[2],
                    "label": r[3],
                }
                for r in rows
            ]
        except Exception:
            return []

    def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        """获取单个快照 (含内容)"""
        try:
            conn = self._get_db()
            row = conn.execute(
                "SELECT id, file_path, content, created_at, size, label "
                "FROM file_snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
            conn.close()
            if row:
                return {
                    "id": row[0], "filePath": row[1], "content": row[2],
                    "createdAt": row[3],
                    "time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row[3])),
                    "size": row[4], "label": row[5],
                }
        except Exception:
            pass
        return None

    def delete_snapshot(self, snapshot_id: str) -> bool:
        try:
            conn = self._get_db()
            conn.execute("DELETE FROM file_snapshots WHERE id = ?", (snapshot_id,))
            conn.commit()
            conn.close()
            return True
        except Exception:
            return False

    def delete_file_snapshots(self, file_path: str) -> int:
        try:
            conn = self._get_db()
            cursor = conn.execute(
                "DELETE FROM file_snapshots WHERE file_path = ?", (file_path,)
            )
            count = cursor.rowcount
            conn.commit()
            conn.close()
            return count
        except Exception:
            return 0

    def _prune_file(self, file_path: str) -> None:
        """清理超出限制的快照"""
        try:
            conn = self._get_db()
            conn.execute("""
                DELETE FROM file_snapshots WHERE id IN (
                    SELECT id FROM file_snapshots WHERE file_path = ?
                    ORDER BY created_at DESC
                    LIMIT -1 OFFSET ?
                )
            """, (file_path, self.max_per_file))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def prune_old(self, days: int = 0) -> int:
        """清理超过 N 天的快照"""
        if days <= 0:
            days = self.max_age_days
        cutoff = time.time() - days * 86400
        try:
            conn = self._get_db()
            cursor = conn.execute(
                "DELETE FROM file_snapshots WHERE created_at < ?", (cutoff,)
            )
            count = cursor.rowcount
            conn.commit()
            conn.close()
            return count
        except Exception:
            return 0

    def get_all_file_paths(self) -> list[str]:
        try:
            conn = self._get_db()
            rows = conn.execute(
                "SELECT DISTINCT file_path FROM file_snapshots"
            ).fetchall()
            conn.close()
            return [r[0] for r in rows]
        except Exception:
            return []

    def get_stats(self) -> dict:
        try:
            conn = self._get_db()
            total = conn.execute("SELECT COUNT(*) FROM file_snapshots").fetchone()[0]
            files = conn.execute(
                "SELECT COUNT(DISTINCT file_path) FROM file_snapshots"
            ).fetchone()[0]
            conn.close()
            return {"totalSnapshots": total, "totalFiles": files}
        except Exception:
            return {"totalSnapshots": 0, "totalFiles": 0}


# 全局实例
_local_history: Optional[LocalHistoryStore] = None


def get_local_history(db_path: str = ":memory:") -> LocalHistoryStore:
    global _local_history
    if _local_history is None:
        _local_history = LocalHistoryStore(db_path)
    return _local_history
