"""
代码库索引器 — 文件扫描 + 增量更新 + 持久化

纯 Python 实现，使用 sqlite3 内置模块。
优化：每个文件只读一次，单次 I/O 同时用于哈希和解析。
"""

from __future__ import annotations

import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path

from .graph import CodeGraph
from .parser import parse_file, parse_source

logger = logging.getLogger("cbm.indexer")

DEFAULT_IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", ".pytest_cache",
    "node_modules", ".next", "dist", "build", ".cache",
    "output", "storage", "trajectories", ".mypy_cache",
    ".ruff_cache", ".idea", ".vscode", ".copier",
    ".playwright-cli", "workspace", ".codebuddy",
}

DEFAULT_IGNORE_EXT = {".pyc", ".pyo", ".so", ".dll", ".png", ".jpg",
                       ".gif", ".ico", ".svg", ".mp4", ".mov", ".mp3",
                       ".wav", ".ttf", ".woff2", ".lock", ".sqlite3",
                       ".zst", ".bin", ".db", ".egg-info"}


class FileIndexer:

    def __init__(self, project_path: str, db_path: str = ""):
        self.project_path = Path(project_path).resolve()
        self.project_name = self._slugify(str(self.project_path))
        self.graph = CodeGraph()
        if not db_path:
            db_path = str(Path(project_path) / ".codebase-memory" / "index.db")
        self.db_path = db_path
        self._init_db()

    def _slugify(self, path: str) -> str:
        return path.replace("/", "-").replace("\\", "-").replace(":", "").strip("-")

    def save_graph(self) -> str:
        """保存图到 SQLite 数据库（主要持久化方式）"""
        self.graph.save_to_db(self.db_path)
        return self.db_path

    def load_graph(self) -> bool:
        """从 SQLite 或 JSON 文件加载图"""
        # 优先从 SQLite 加载
        if self.graph.load_from_db(self.db_path):
            return True
        # 回退到 JSON
        import json
        graph_path = str(Path(self.db_path).parent / "graph.json")
        if not Path(graph_path).exists():
            return False
        with open(graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.graph = CodeGraph()
        from .graph import Node, NodeType, EdgeType
        for n in data.get("nodes", []):
            node = Node(
                name=n["name"],
                node_type=NodeType(n["type"]),
                id=n["id"],
                file_path=n.get("file_path", ""),
                line_start=n.get("line_start", 0),
                line_end=n.get("line_end", 0),
                qualified_name=n.get("qualified_name", ""),
                signature=n.get("signature", ""),
                language=n.get("language", ""),
            )
            self.graph._nodes[node.id] = node
            self.graph._node_counter = max(self.graph._node_counter, int(node.id[1:]))
        from .graph import EdgeType as ET
        for e in data.get("edges", []):
            self.graph.add_edge(e["source"], e["target"], ET(e["type"]))
        # 迁移到 SQLite
        self.graph.save_to_db(self.db_path)
        return True

    def _init_db(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.execute("PRAGMA journal_mode=WAL")
        # 文件索引表
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS file_index (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                language TEXT DEFAULT '',
                indexed_at REAL DEFAULT 0
            )
        """)
        # 图节点/边表（与 CodeGraph.save_to_db 共用）
        self.graph._init_graph_schema(self._db)
        self._db.commit()

    def scan_files(self) -> list[Path]:
        files: list[Path] = []
        for root, dirs, filenames in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS
                       and not d.startswith(".")]
            for fname in filenames:
                fpath = Path(root) / fname
                if fpath.suffix.lower() in DEFAULT_IGNORE_EXT:
                    continue
                if fname.startswith(".") and fname != ".env.example":
                    continue
                files.append(fpath)
        return files

    def index(self, force: bool = False) -> dict:
        start_time = time.monotonic()
        files = self.scan_files()
        logger.info("Scanning %d files in %s", len(files), self.project_name)

        new_count = 0
        skip_count = 0
        error_count = 0
        total_read_ms = 0.0

        # 首次索引标志
        row = self._db.execute("SELECT COUNT(*) FROM file_index").fetchone()
        is_first = not force and not row[0]

        for i, file_path in enumerate(files):
            rel_path = str(file_path.relative_to(self.project_path))

            # 读取文件（仅一次 I/O）
            t0 = time.monotonic()
            try:
                content = file_path.read_bytes()
            except Exception:
                error_count += 1
                continue
            total_read_ms += (time.monotonic() - t0) * 1000

            file_hash = hashlib.sha256(content).hexdigest()[:16]

            # 增量更新：哈希未变则跳过
            if not force and not is_first:
                cached = self._db.execute(
                    "SELECT file_hash FROM file_index WHERE file_path=?", (rel_path,)
                ).fetchone()
                if cached and cached[0] == file_hash:
                    skip_count += 1
                    continue

            # 解析文件
            try:
                source = content.decode("utf-8", errors="ignore")
                ext = file_path.suffix.lower()
                fid = parse_source(str(file_path), source, self.graph, ext)
                if fid:
                    lang = self.graph.get_node(fid).language if self.graph.get_node(fid) else ""
                    self._db.execute(
                        """INSERT OR REPLACE INTO file_index
                           (file_path, file_hash, language, indexed_at) VALUES (?,?,?,?)""",
                        (rel_path, file_hash, lang, time.time()),
                    )
                    new_count += 1
            except Exception:
                error_count += 1

            if (new_count + skip_count) % 200 == 0:
                logger.info("Indexed %d/%d files", new_count, len(files))

        self._db.commit()
        elapsed = (time.monotonic() - start_time) * 1000

        logger.info(
            "Index done: %d new, %d skip, %d err, %.0fms (%.0fms I/O), %d nodes, %d edges",
            new_count, skip_count, error_count, elapsed, total_read_ms,
            self.graph.node_count, self.graph.edge_count,
        )

        return {
            "status": "indexed",
            "project": self.project_name,
            "files_scanned": len(files),
            "files_indexed": new_count,
            "files_skipped": skip_count,
            "nodes": self.graph.node_count,
            "edges": self.graph.edge_count,
            "elapsed_ms": int(elapsed),
        }

    def get_status(self) -> dict:
        total = self._db.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
        return {
            "project": self.project_name,
            "path": str(self.project_path),
            "nodes": self.graph.node_count,
            "edges": self.graph.edge_count,
            "files_indexed": total,
            "indexed": total > 0,
        }
