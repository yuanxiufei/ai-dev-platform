"""
知识图谱数据结构 — 节点 / 边 / 图操作 + SQLite 持久化

纯 Python 实现，基于 dict + list，使用内置 sqlite3 持久化。
合并了原 CKG 系统的 SQLite 存储能力，统一为单一代码知识图谱系统。
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

logger = logging.getLogger("cbm.graph")


class NodeType(StrEnum):
    """节点类型"""
    FILE = "File"
    FOLDER = "Folder"
    MODULE = "Module"
    CLASS = "Class"
    FUNCTION = "Function"
    METHOD = "Method"
    VARIABLE = "Variable"
    IMPORT = "Import"
    ROUTE = "Route"
    DECORATOR = "Decorator"
    TYPE = "Type"
    ENUM = "Enum"
    FIELD = "Field"


class EdgeType(StrEnum):
    """边类型"""
    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    DECORATES = "DECORATES"
    USAGE = "USAGE"
    HTTP_CALLS = "HTTP_CALLS"
    TESTS = "TESTS"
    DATA_FLOWS = "DATA_FLOWS"


@dataclass
class Node:
    """知识图谱节点"""
    name: str
    node_type: NodeType
    id: str = ""
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    qualified_name: str = ""
    signature: str = ""
    language: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": str(self.node_type),
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "qualified_name": self.qualified_name,
            "signature": self.signature,
            "language": self.language,
            **self.extra,
        }


@dataclass
class Edge:
    """知识图谱边"""
    source_id: str
    target_id: str
    edge_type: EdgeType

    def to_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": str(self.edge_type),
        }


class CodeGraph:
    """代码知识图谱 — 内存数据模型"""

    def __init__(self):
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []
        self._node_counter: int = 0

    # ── 节点操作 ────────────────────────────────

    def add_node(self, node: Node) -> str:
        """添加节点，返回节点 ID"""
        if not node.id:
            self._node_counter += 1
            node.id = f"n{self._node_counter}"
        self._nodes[node.id] = node
        return node.id

    def get_node(self, node_id: str) -> Node | None:
        return self._nodes.get(node_id)

    def find_by_name(self, name: str, node_type: NodeType | None = None) -> list[Node]:
        """按名称查找节点"""
        results = []
        for node in self._nodes.values():
            if name.lower() in node.name.lower():
                if node_type and node.node_type != node_type:
                    continue
                results.append(node)
        return results

    def find_by_qualified_name(self, qname: str) -> list[Node]:
        """按限定名查找（精确匹配 + 模糊匹配）"""
        exact = [n for n in self._nodes.values() if n.qualified_name == qname]
        if exact:
            return exact
        return [n for n in self._nodes.values() if qname in n.qualified_name]

    # ── 边操作 ────────────────────────────────

    def add_edge(self, source_id: str, target_id: str, edge_type: EdgeType) -> None:
        """添加边（去重）"""
        # 简单去重
        for e in self._edges:
            if e.source_id == source_id and e.target_id == target_id and e.edge_type == edge_type:
                return
        self._edges.append(Edge(source_id, target_id, edge_type))

    def get_outbound(self, node_id: str) -> list[Edge]:
        return [e for e in self._edges if e.source_id == node_id]

    def get_inbound(self, node_id: str) -> list[Edge]:
        return [e for e in self._edges if e.target_id == node_id]

    def get_callers(self, node_id: str) -> list[Node]:
        """获取调用者"""
        caller_ids = {e.source_id for e in self._edges if e.target_id == node_id and e.edge_type == EdgeType.CALLS}
        return [self._nodes[nid] for nid in caller_ids if nid in self._nodes]

    def get_callees(self, node_id: str) -> list[Node]:
        """获取被调用者"""
        callee_ids = {e.target_id for e in self._edges if e.source_id == node_id and e.edge_type == EdgeType.CALLS}
        return [self._nodes[nid] for nid in callee_ids if nid in self._nodes]

    # ── 统计 ──────────────────────────────────

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def node_type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for n in self._nodes.values():
            key = str(n.node_type)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def edge_type_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for e in self._edges:
            key = str(e.edge_type)
            counts[key] = counts.get(key, 0) + 1
        return counts

    def language_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for n in self._nodes.values():
            if n.language:
                counts[n.language] = counts.get(n.language, 0) + 1
        return counts

    # ── 序列化 ────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_types": self.node_type_counts(),
            "edge_types": self.edge_type_counts(),
            "languages": self.language_counts(),
        }

    # ── SQLite 持久化 ──────────────────────────

    def save_to_db(self, db_path: str) -> None:
        """将图持久化到 SQLite 数据库（合并自 CKG 的 SQLite 方案）"""
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(db_path)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")

        self._init_graph_schema(db)

        # 清空旧数据
        db.execute("DELETE FROM graph_edges")
        db.execute("DELETE FROM graph_nodes")

        # 批量插入节点
        node_rows: list[tuple] = []
        for node in self._nodes.values():
            node_rows.append((
                node.id, node.name, str(node.node_type),
                node.file_path, node.line_start, node.line_end,
                node.qualified_name, node.signature,
                node.language, json.dumps(node.extra, ensure_ascii=False),
            ))
        db.executemany(
            """INSERT INTO graph_nodes
               (id, name, node_type, file_path, line_start, line_end,
                qualified_name, signature, language, extra)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            node_rows,
        )

        # 批量插入边
        edge_rows = [(e.source_id, e.target_id, str(e.edge_type)) for e in self._edges]
        db.executemany(
            "INSERT INTO graph_edges (source_id, target_id, edge_type) VALUES (?, ?, ?)",
            edge_rows,
        )

        db.commit()
        # 创建索引
        db.executescript("""
            CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_graph_nodes_name ON graph_nodes(name);
            CREATE INDEX IF NOT EXISTS idx_graph_nodes_file ON graph_nodes(file_path);
            CREATE INDEX IF NOT EXISTS idx_graph_nodes_qname ON graph_nodes(qualified_name);
            CREATE INDEX IF NOT EXISTS idx_graph_edges_src ON graph_edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_graph_edges_tgt ON graph_edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_graph_edges_type ON graph_edges(edge_type);
        """)
        db.commit()
        db.close()

        logger.info("Saved graph to DB: %d nodes, %d edges → %s",
                     self.node_count, self.edge_count, db_path)

    def load_from_db(self, db_path: str) -> bool:
        """从 SQLite 数据库加载图"""
        if not Path(db_path).exists():
            return False

        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row

        # 检查表是否存在
        exists = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_nodes'"
        ).fetchone()
        if not exists:
            db.close()
            return False

        self._nodes.clear()
        self._edges.clear()
        self._node_counter = 0

        # 加载节点
        for row in db.execute("SELECT * FROM graph_nodes"):
            extra = {}
            try:
                extra = json.loads(row["extra"]) if row["extra"] else {}
            except Exception:
                pass

            node = Node(
                name=row["name"],
                node_type=NodeType(row["node_type"]),
                id=row["id"],
                file_path=row["file_path"] or "",
                line_start=row["line_start"] or 0,
                line_end=row["line_end"] or 0,
                qualified_name=row["qualified_name"] or "",
                signature=row["signature"] or "",
                language=row["language"] or "",
                extra=extra,
            )
            self._nodes[node.id] = node
            # 恢复计数器
            if node.id.startswith("n"):
                try:
                    num = int(node.id[1:])
                    self._node_counter = max(self._node_counter, num)
                except ValueError:
                    pass

        # 加载边
        for row in db.execute("SELECT * FROM graph_edges"):
            self._edges.append(Edge(
                source_id=row["source_id"],
                target_id=row["target_id"],
                edge_type=EdgeType(row["edge_type"]),
            ))

        db.close()
        logger.info("Loaded graph from DB: %d nodes, %d edges ← %s",
                     self.node_count, self.edge_count, db_path)
        return True

    @staticmethod
    def _init_graph_schema(db: sqlite3.Connection) -> None:
        """初始化图的 SQLite 表结构"""
        db.executescript("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                node_type TEXT NOT NULL,
                file_path TEXT DEFAULT '',
                line_start INTEGER DEFAULT 0,
                line_end INTEGER DEFAULT 0,
                qualified_name TEXT DEFAULT '',
                signature TEXT DEFAULT '',
                language TEXT DEFAULT '',
                extra TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS graph_edges (
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL
            );
        """)
        db.commit()
