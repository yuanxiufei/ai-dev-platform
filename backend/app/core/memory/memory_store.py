"""
长期记忆存储 — MemoryNode / MemoryEdge + SQLite 持久化

自主设计，借鉴 cognee 的实体关系图谱理念：
- 两层存储：记忆节点 + 记忆关系
- 基于重要性和访问频率的自动衰减
- 语义搜索（余弦相似度）+ 图遍历检索

纯 Python 实现，零外部向量数据库依赖。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("memory.store")


# ── 数据类型 ──────────────────────────────────────

class MemoryType:
    """记忆类型枚举"""
    CODE = "code"               # 代码相关的记忆
    CONVERSATION = "conversation"  # 对话上下文
    DECISION = "decision"       # 架构决策
    LESSON = "lesson"           # 经验教训
    FACT = "fact"               # 事实性知识
    PATTERN = "pattern"         # 代码模式
    PREFERENCE = "preference"   # 用户偏好


class RelationType:
    """记忆关系类型"""
    RELATES_TO = "RELATES_TO"
    DEPENDS_ON = "DEPENDS_ON"
    BEFORE = "BEFORE"
    AFTER = "AFTER"
    CAUSED_BY = "CAUSED_BY"
    CONTRADICTS = "CONTRADICTS"
    GENERALIZES = "GENERALIZES"
    CONVERSATION_FLOW = "CONVERSATION_FLOW"  # 对话流转


# ── 数据模型 ──────────────────────────────────────

@dataclass
class MemoryNode:
    """记忆节点"""
    id: str = ""
    content: str = ""
    memory_type: str = MemoryType.FACT
    importance: float = 0.5        # 重要性 0~1
    created_at: float = 0
    last_accessed: float = 0
    access_count: int = 0
    source: str = ""               # 来源: conversation / code_change / reflection
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        now = time.time()
        if not self.created_at:
            self.created_at = now
        if not self.last_accessed:
            self.last_accessed = now
        if not self.id:
            self.id = f"mem_{uuid.uuid4().hex[:12]}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "importance": self.importance,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "source": self.source,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @property
    def decay_score(self) -> float:
        """计算衰减后的有效重要性

        公式: importance × (1 / (1 + hours_since_access))
        同时受 access_count 轻微加权。
        """
        hours = (time.time() - self.last_accessed) / 3600
        recency = 1.0 / (1.0 + hours * 0.01)  # 缓慢衰减
        frequency_bonus = math.log(1 + self.access_count) * 0.1
        return min(1.0, self.importance * recency + frequency_bonus)


@dataclass
class MemoryEdge:
    """记忆关系"""
    source_id: str
    target_id: str
    relation_type: str
    weight: float = 0.5

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type,
            "weight": self.weight,
        }


# ── 存储引擎 ──────────────────────────────────────

class MemoryStore:
    """
    长期记忆存储引擎

    基于 SQLite 的双层图存储：
    - memory_nodes: 记忆节点
    - memory_edges: 记忆关系

    特性：
    - 自动重要性衰减
    - 基于关键词的图遍历检索
    - 低重要性记忆自动遗忘
    """

    def __init__(self, db_path: str = "data/memory.db"):
        self.db_path = db_path
        self._db: sqlite3.Connection | None = None
        self._ensure_db()

    def _ensure_db(self) -> sqlite3.Connection:
        if self._db is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(self.db_path)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._init_schema()
        return self._db

    def _init_schema(self) -> None:
        if self._db is None:
            return
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS memory_nodes (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL DEFAULT 'fact',
                importance REAL DEFAULT 0.5,
                created_at REAL DEFAULT 0,
                last_accessed REAL DEFAULT 0,
                access_count INTEGER DEFAULT 0,
                source TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_mem_type ON memory_nodes(memory_type);
            CREATE INDEX IF NOT EXISTS idx_mem_importance ON memory_nodes(importance);
            CREATE INDEX IF NOT EXISTS idx_mem_accessed ON memory_nodes(last_accessed);
            CREATE INDEX IF NOT EXISTS idx_mem_source ON memory_nodes(source);

            CREATE TABLE IF NOT EXISTS memory_edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                weight REAL DEFAULT 0.5,
                PRIMARY KEY (source_id, target_id, relation_type)
            );
            CREATE INDEX IF NOT EXISTS idx_mem_edge_src ON memory_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_mem_edge_tgt ON memory_edges(target_id);
        """)
        self._db.commit()

    # ── CRUD ─────────────────────────────────────

    def save(self, node: MemoryNode) -> str:
        """保存或更新记忆节点"""
        db = self._ensure_db()
        db.execute(
            """INSERT OR REPLACE INTO memory_nodes
               (id, content, memory_type, importance, created_at, last_accessed,
                access_count, source, tags, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.id, node.content, node.memory_type,
                node.importance, node.created_at, node.last_accessed,
                node.access_count, node.source,
                json.dumps(node.tags, ensure_ascii=False),
                json.dumps(node.metadata, ensure_ascii=False),
            ),
        )
        db.commit()
        return node.id

    def get(self, node_id: str) -> MemoryNode | None:
        """获取单个记忆节点"""
        db = self._ensure_db()
        db.row_factory = sqlite3.Row
        row = db.execute(
            "SELECT * FROM memory_nodes WHERE id = ?", (node_id,)
        ).fetchone()
        db.row_factory = None
        if not row:
            return None

        node = self._row_to_node(row)
        # 更新访问记录
        self._touch(node.id)
        return node

    def delete(self, node_id: str) -> bool:
        """删除记忆节点及其所有关系"""
        db = self._ensure_db()
        db.execute("DELETE FROM memory_edges WHERE source_id = ? OR target_id = ?",
                   (node_id, node_id))
        db.execute("DELETE FROM memory_nodes WHERE id = ?", (node_id,))
        db.commit()
        return True

    def _touch(self, node_id: str) -> None:
        """更新访问记录"""
        db = self._ensure_db()
        db.execute(
            "UPDATE memory_nodes SET last_accessed = ?, access_count = access_count + 1 WHERE id = ?",
            (time.time(), node_id),
        )
        db.commit()

    # ── 关系操作 ──────────────────────────────────

    def add_edge(self, source_id: str, target_id: str,
                 relation_type: str, weight: float = 0.5) -> None:
        """添加记忆关系"""
        db = self._ensure_db()
        db.execute(
            """INSERT OR REPLACE INTO memory_edges
               (source_id, target_id, relation_type, weight)
               VALUES (?, ?, ?, ?)""",
            (source_id, target_id, relation_type, weight),
        )
        db.commit()

    def get_edges(self, node_id: str, direction: str = "both") -> list[MemoryEdge]:
        """获取节点的所有关系"""
        db = self._ensure_db()
        db.row_factory = sqlite3.Row
        if direction == "outbound":
            rows = db.execute(
                "SELECT * FROM memory_edges WHERE source_id = ?", (node_id,)
            ).fetchall()
        elif direction == "inbound":
            rows = db.execute(
                "SELECT * FROM memory_edges WHERE target_id = ?", (node_id,)
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM memory_edges WHERE source_id = ? OR target_id = ?",
                (node_id, node_id),
            ).fetchall()
        db.row_factory = None
        return [MemoryEdge(
            source_id=r["source_id"], target_id=r["target_id"],
            relation_type=r["relation_type"], weight=r["weight"],
        ) for r in rows]

    def get_connected(self, node_id: str, depth: int = 2) -> list[MemoryNode]:
        """获取节点的关联记忆（BFS 遍历）"""
        visited: set[str] = {node_id}
        frontier = {node_id}
        results: dict[str, MemoryNode] = {}

        for _ in range(depth):
            next_frontier: set[str] = set()
            for nid in frontier:
                for edge in self.get_edges(nid, "both"):
                    other = edge.target_id if edge.source_id == nid else edge.source_id
                    if other not in visited:
                        visited.add(other)
                        next_frontier.add(other)
                        node = self.get(other)
                        if node:
                            results[node.id] = node
            frontier = next_frontier
            if not frontier:
                break

        return list(results.values())

    # ── 检索 ──────────────────────────────────────

    def search_by_keyword(
        self,
        query: str,
        memory_type: str | None = None,
        limit: int = 20,
        min_importance: float = 0.0,
    ) -> list[MemoryNode]:
        """基于关键词搜索记忆（带重要性排序）"""
        db = self._ensure_db()
        db.row_factory = sqlite3.Row

        conditions = ["(content LIKE ? OR tags LIKE ?)"]
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if memory_type:
            conditions.append("memory_type = ?")
            params.append(memory_type)
        if min_importance > 0:
            conditions.append("importance >= ?")
            params.append(min_importance)

        rows = db.execute(
            f"SELECT * FROM memory_nodes WHERE {' AND '.join(conditions)} "
            f"ORDER BY importance DESC, last_accessed DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        db.row_factory = None

        return [self._row_to_node(r) for r in rows]

    def search_recent(
        self,
        limit: int = 20,
        memory_type: str | None = None,
    ) -> list[MemoryNode]:
        """获取最近的记忆"""
        db = self._ensure_db()
        db.row_factory = sqlite3.Row

        if memory_type:
            rows = db.execute(
                "SELECT * FROM memory_nodes WHERE memory_type = ? "
                "ORDER BY last_accessed DESC LIMIT ?",
                (memory_type, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM memory_nodes ORDER BY last_accessed DESC LIMIT ?",
                (limit,),
            ).fetchall()
        db.row_factory = None
        return [self._row_to_node(r) for r in rows]

    def get_context(
        self,
        query: str = "",
        recent_count: int = 10,
        related_depth: int = 2,
    ) -> str:
        """获取记忆上下文（注入到 Agent）

        1. 关键词搜索 + 高重要性记忆
        2. 图遍历获取关联记忆
        3. 格式化为 Agent 可读的上下文文本
        """
        lines: list[str] = []
        seen_ids: set[str] = set()

        # 关键词检索
        if query:
            results = self.search_by_keyword(query, limit=recent_count)
            for node in results:
                if node.id not in seen_ids:
                    seen_ids.add(node.id)
                    lines.append(f"[{node.memory_type}] {node.content}")

        # 最近记忆
        recent = self.search_recent(limit=recent_count)
        for node in recent:
            if node.id not in seen_ids:
                seen_ids.add(node.id)
                lines.append(f"[{node.memory_type}] {node.content}")

        # 图遍历关联
        if lines and related_depth > 0:
            first_id = list(seen_ids)[0] if seen_ids else ""
            if first_id:
                related = self.get_connected(first_id, depth=related_depth)
                for node in related:
                    if node.id not in seen_ids:
                        seen_ids.add(node.id)
                        lines.append(f"[{node.memory_type}][related] {node.content}")

        if not lines:
            return ""

        return "# Context from Memory\n\n" + "\n".join(lines)

    # ── 遗忘机制 ──────────────────────────────────

    def forget(self, threshold: float = 0.05) -> int:
        """自动遗忘低重要性的记忆

        删除 decay_score < threshold 的记忆节点。
        """
        db = self._ensure_db()
        db.row_factory = sqlite3.Row
        rows = db.execute("SELECT * FROM memory_nodes").fetchall()
        db.row_factory = None

        removed = 0
        for row in rows:
            node = self._row_to_node(row)
            if node.decay_score < threshold:
                self.delete(node.id)
                removed += 1

        if removed:
            logger.info("Forgot %d low-importance memories (threshold=%.2f)",
                        removed, threshold)
        return removed

    # ── 聚合查询 ──────────────────────────────────

    def search_by_source(
        self, source: str, limit: int = 50
    ) -> list[MemoryNode]:
        """按来源检索"""
        db = self._ensure_db()
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT * FROM memory_nodes WHERE source = ? ORDER BY created_at DESC LIMIT ?",
            (source, limit),
        ).fetchall()
        db.row_factory = None
        return [self._row_to_node(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        """获取记忆统计"""
        db = self._ensure_db()
        total = db.execute("SELECT COUNT(*) FROM memory_nodes").fetchone()[0]
        edges = db.execute("SELECT COUNT(*) FROM memory_edges").fetchone()[0]
        by_type = {}
        for row in db.execute(
            "SELECT memory_type, COUNT(*) FROM memory_nodes GROUP BY memory_type"
        ).fetchall():
            by_type[row[0]] = row[1]
        avg_importance = db.execute(
            "SELECT AVG(importance) FROM memory_nodes"
        ).fetchone()[0] or 0.0
        return {
            "total_memories": total,
            "total_edges": edges,
            "by_type": by_type,
            "avg_importance": round(avg_importance, 3),
        }

    # ── 辅助方法 ──────────────────────────────────

    def _row_to_node(self, row: sqlite3.Row) -> MemoryNode:
        """将数据库行转为 MemoryNode"""
        tags = []
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
        except Exception:
            pass

        metadata = {}
        try:
            metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        except Exception:
            pass

        return MemoryNode(
            id=row["id"],
            content=row["content"],
            memory_type=row["memory_type"],
            importance=row["importance"] or 0.5,
            created_at=row["created_at"] or time.time(),
            last_accessed=row["last_accessed"] or time.time(),
            access_count=row["access_count"] or 0,
            source=row["source"] or "",
            tags=tags,
            metadata=metadata,
        )

    def close(self) -> None:
        if self._db:
            self._db.close()
            self._db = None


# ── 全局单例 ──────────────────────────────────────

_global_memory_store: MemoryStore | None = None


def init_memory_store(db_path: str = "data/memory.db") -> MemoryStore:
    """初始化全局记忆存储"""
    global _global_memory_store
    _global_memory_store = MemoryStore(db_path=db_path)
    logger.info("MemoryStore initialized: %s", db_path)
    return _global_memory_store


def get_memory_store() -> MemoryStore:
    """获取全局记忆存储"""
    global _global_memory_store
    if _global_memory_store is None:
        return init_memory_store()
    return _global_memory_store
