"""
Session 树 + 检查点恢复 — 借鉴 hermes-agent Session Tree / Checkpoint 设计

持久化：对接 MemoryStore（SQLite 图数据库 data/memory.db）+ StorageManager 文件存储
  - SessionNode → MemoryNode(memory_type="session")  + MemoryEdge(CONVERSATION_FLOW / BRANCHES_FROM)
  - Checkpoint   → MemoryNode(memory_type="checkpoint") + MemoryEdge(BELONGS_TO / PARENT_CHECKPOINT)
  - 大负载(>100KB) → StorageManager data/checkpoints/{id}.json
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("session_tree")

LARGE_PAYLOAD_THRESHOLD_BYTES = 100_000  # 大型负载阈值（字节）


class SessionRelation:
    """会话树专用边关系（扩展 MemoryStore RelationType）"""
    CONVERSATION_FLOW = "CONVERSATION_FLOW"   # 父→子
    BRANCHES_FROM = "BRANCHES_FROM"            # fork源→分支
    BELONGS_TO = "BELONGS_TO"                  # 检查点→会话
    PARENT_CHECKPOINT = "PARENT_CHECKPOINT"    # 子检查点→父检查点
    RESTORED_FROM = "RESTORED_FROM"            # 恢复节点→源检查点


# ── Session 节点 ───────────────────────────────────────────

@dataclass
class SessionNode:
    """会话树中的节点"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    parent_id: str | None = None
    children_ids: list[str] = field(default_factory=list)

    # 分支信息
    branch_name: str = "main"
    branch_reason: str = ""
    forked_from: str | None = None
    depth: int = 0

    # 运行数据
    user_message: str = ""
    agent_config: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    final_answer: str = ""
    error: str = ""

    # 状态
    status: str = "pending"  # pending | running | completed | failed | cancelled | branched
    created_at: float = field(default_factory=time.time)
    completed_at: float = 0.0
    total_turns: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0

    # 检查点关联
    checkpoint_id: str | None = None
    restored_from_checkpoint: str | None = None

    @property
    def is_leaf(self) -> bool:
        return len(self.children_ids) == 0

    @property
    def is_root(self) -> bool:
        return self.parent_id is None

    @property
    def importance(self) -> float:
        """映射状态到 MemoryStore 重要性"""
        return {
            "completed": 0.85, "branched": 0.80, "running": 0.60,
            "pending": 0.40, "failed": 0.30, "cancelled": 0.20,
        }.get(self.status, 0.40)

    def to_dict(self, include_messages: bool = False) -> dict[str, Any]:
        d = {
            "id": self.id, "agent_id": self.agent_id, "parent_id": self.parent_id,
            "children_ids": self.children_ids, "branch_name": self.branch_name,
            "branch_reason": self.branch_reason, "forked_from": self.forked_from,
            "depth": self.depth, "user_message": self.user_message, "status": self.status,
            "created_at": self.created_at, "completed_at": self.completed_at,
            "total_turns": self.total_turns, "total_tool_calls": self.total_tool_calls,
            "total_tokens": self.total_tokens, "total_latency_ms": self.total_latency_ms,
            "checkpoint_id": self.checkpoint_id,
            "restored_from_checkpoint": self.restored_from_checkpoint,
            "final_answer_preview": self.final_answer[:300] if self.final_answer else "",
            "error": self.error[:300] if self.error else "",
        }
        if include_messages:
            d["messages"] = self.messages
            d["tool_results"] = self.tool_results
            d["agent_config"] = self.agent_config
        return d

    # ── MemoryStore 序列化 ──────────────────────────────

    def to_memory_node(self) -> dict[str, Any]:
        """序列化为 MemoryNode 字段"""
        return {
            "id": self.id,
            "content": self.user_message,
            "memory_type": "session",
            "importance": self.importance,
            "created_at": self.created_at,
            "last_accessed": time.time(),
            "access_count": 0,
            "source": self.agent_id,
            "tags": [t for t in [self.branch_name, f"depth:{self.depth}", self.status, f"agent:{self.agent_id}"] if t],
            "metadata": {
                "branch_name": self.branch_name, "branch_reason": self.branch_reason,
                "forked_from": self.forked_from, "depth": self.depth, "status": self.status,
                "completed_at": self.completed_at, "total_turns": self.total_turns,
                "total_tool_calls": self.total_tool_calls, "total_tokens": self.total_tokens,
                "total_latency_ms": self.total_latency_ms,
                "final_answer_preview": self.final_answer[:300] if self.final_answer else "",
                "error": self.error[:500] if self.error else "",
                "checkpoint_id": self.checkpoint_id,
                "restored_from_checkpoint": self.restored_from_checkpoint,
                "agent_config": self.agent_config,
                "parent_id": self.parent_id,
                "children_ids": self.children_ids,
            },
        }

    @classmethod
    def from_memory_node(cls, mn: Any) -> SessionNode:
        """从 MemoryNode 反序列化（兼容 dict 和 dataclass）"""
        _g = lambda k, d=None: mn.get(k, d) if isinstance(mn, dict) else getattr(mn, k, d)
        meta = _g("metadata", {}) or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return cls(
            id=_g("id", ""), agent_id=_g("source", ""),
            parent_id=meta.get("parent_id"),
            children_ids=meta.get("children_ids", []),
            branch_name=meta.get("branch_name", "main"),
            branch_reason=meta.get("branch_reason", ""),
            forked_from=meta.get("forked_from"),
            depth=meta.get("depth", 0),
            user_message=_g("content", ""),
            agent_config=meta.get("agent_config", {}),
            status=meta.get("status", "pending"),
            created_at=_g("created_at", time.time()),
            completed_at=meta.get("completed_at", 0),
            total_turns=meta.get("total_turns", 0),
            total_tool_calls=meta.get("total_tool_calls", 0),
            total_tokens=meta.get("total_tokens", 0),
            total_latency_ms=meta.get("total_latency_ms", 0),
            checkpoint_id=meta.get("checkpoint_id"),
            restored_from_checkpoint=meta.get("restored_from_checkpoint"),
            final_answer=meta.get("final_answer_preview", ""),
            error=meta.get("error", ""),
        )


# ── 检查点（快照）─────────────────────────────────────────

@dataclass
class Checkpoint:
    """
    会话状态快照 — 可在分支点或任意轮次保存

    借鉴 hermes-agent 的快照语义：
      - 完整消息历史（所有角色）
      - Agent 配置副本
      - 工具执行结果
      - 上下文变量（预算、worktree 等）
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str = ""
    agent_id: str = ""
    label: str = ""
    description: str = ""

    # 快照数据
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    agent_config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # 上下文
    turn: int = 0
    total_tokens: int = 0
    created_at: float = field(default_factory=time.time)

    # 持久化路径
    file_path: str = ""
    parent_checkpoint_id: str | None = None

    @property
    def payload_size(self) -> int:
        """估算负载大小（字节）"""
        try:
            return len(json.dumps({
                "messages": self.messages, "tool_results": self.tool_results,
                "agent_config": self.agent_config,
            }, ensure_ascii=False).encode("utf-8"))
        except Exception:
            return 0

    @property
    def is_large(self) -> bool:
        return self.payload_size >= LARGE_PAYLOAD_THRESHOLD_BYTES

    def to_dict(self, include_payload: bool = False) -> dict[str, Any]:
        d = {
            "id": self.id, "session_id": self.session_id, "agent_id": self.agent_id,
            "label": self.label, "description": self.description,
            "turn": self.turn, "total_tokens": self.total_tokens,
            "messages_count": len(self.messages), "created_at": self.created_at,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "file_path": self.file_path, "payload_size": self.payload_size,
            "is_large": self.is_large, "metadata": self.metadata,
        }
        if include_payload:
            d["messages"] = self.messages
            d["tool_results"] = self.tool_results
            d["agent_config"] = self.agent_config
        return d

    # ── MemoryStore 序列化 ─────────────────────────────

    def to_memory_node(self) -> dict[str, Any]:
        """序列化为 MemoryNode；大负载只放 file_path 引用"""
        meta: dict[str, Any] = {
            "session_id": self.session_id, "agent_id": self.agent_id,
            "description": self.description, "turn": self.turn,
            "total_tokens": self.total_tokens,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "file_path": self.file_path, "checkpoint_metadata": self.metadata,
        }
        if not self.is_large:
            meta["messages"] = self.messages
            meta["tool_results"] = self.tool_results
            meta["agent_config"] = self.agent_config
        return {
            "id": self.id, "content": self.label, "memory_type": "checkpoint",
            "importance": 0.70, "created_at": self.created_at,
            "last_accessed": self.created_at, "access_count": 0,
            "source": self.agent_id, "tags": [self.session_id, f"turn:{self.turn}"],
            "metadata": meta,
        }

    @classmethod
    def from_memory_node(cls, mn: Any) -> Checkpoint:
        """从 MemoryNode 反序列化"""
        _g = lambda k, d=None: mn.get(k, d) if isinstance(mn, dict) else getattr(mn, k, d)
        meta = _g("metadata", {}) or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        return cls(
            id=_g("id", ""), session_id=meta.get("session_id", ""),
            agent_id=_g("source", ""), label=_g("content", ""),
            description=meta.get("description", ""),
            messages=meta.get("messages", []),
            tool_results=meta.get("tool_results", []),
            agent_config=meta.get("agent_config", {}),
            metadata=meta.get("checkpoint_metadata", {}),
            turn=meta.get("turn", 0), total_tokens=meta.get("total_tokens", 0),
            created_at=_g("created_at", time.time()),
            file_path=meta.get("file_path", ""),
            parent_checkpoint_id=meta.get("parent_checkpoint_id"),
        )


# ── 检查点管理器 ──────────────────────────────────────────

class CheckpointManager:
    """
    检查点管理器 — MemoryStore（SQLite 图数据库）+ StorageManager 文件存储

    借鉴 hermes-agent 的 checkpoint 管理：
      - 元数据 → MemoryNode(memory_type="checkpoint") 存入 data/memory.db
      - 边关系 → MemoryEdge (BELONGS_TO / PARENT_CHECKPOINT)
      - 大负载(>100KB) → StorageManager data/checkpoints/{id}.json
      - 内存 LRU 缓存加速热检查点
    """

    def __init__(
        self,
        memory_store=None,
        storage_manager=None,
        storage_subdir: str = "checkpoints",
    ):
        self._ms = memory_store
        self._sm = storage_manager
        self._storage_subdir = storage_subdir
        self._cache: dict[str, Checkpoint] = {}

    @property
    def memory_store(self):
        if self._ms is None:
            from app.core.memory.memory_store import get_memory_store
            self._ms = get_memory_store()
        return self._ms

    @property
    def storage_manager(self):
        if self._sm is None:
            from app.core.storage import get_storage_manager
            self._sm = get_storage_manager()
        return self._sm

    def _get_storage_dir(self) -> Path:
        try:
            base = self.storage_manager.get_path("data", self._storage_subdir)
        except Exception:
            base = f"data/{self._storage_subdir}"
        p = Path(base)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _save_large_payload(self, checkpoint: Checkpoint) -> str:
        if not checkpoint.is_large:
            return ""
        fp = self._get_storage_dir() / f"{checkpoint.id}.json"
        try:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump({
                    "id": checkpoint.id, "session_id": checkpoint.session_id,
                    "agent_id": checkpoint.agent_id, "label": checkpoint.label,
                    "description": checkpoint.description, "turn": checkpoint.turn,
                    "total_tokens": checkpoint.total_tokens,
                    "messages": checkpoint.messages,
                    "tool_results": checkpoint.tool_results,
                    "agent_config": checkpoint.agent_config,
                    "metadata": checkpoint.metadata,
                    "created_at": checkpoint.created_at,
                    "parent_checkpoint_id": checkpoint.parent_checkpoint_id,
                }, f, ensure_ascii=False, indent=2)
            return str(fp)
        except Exception as e:
            logger.error("Failed to save large checkpoint: %s", e)
            return ""

    def _load_large_payload(self, file_path: str) -> dict[str, Any] | None:
        fp = Path(file_path)
        if not fp.exists():
            return None
        try:
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load checkpoint payload: %s", e)
            return None

    def save(
        self, session_id: str, agent_id: str,
        messages: list[dict[str, Any]], tool_results: list[dict[str, Any]],
        agent_config: dict[str, Any], label: str = "", description: str = "",
        turn: int = 0, total_tokens: int = 0,
        metadata: dict[str, Any] | None = None,
        parent_checkpoint_id: str | None = None,
    ) -> Checkpoint:
        """保存检查点 → MemoryStore(SQLite) + 大负载 StorageManager(文件)"""
        checkpoint = Checkpoint(
            session_id=session_id, agent_id=agent_id,
            label=label, description=description,
            messages=list(messages),
            tool_results=[dict(tr) for tr in tool_results],
            agent_config=dict(agent_config),
            metadata=dict(metadata or {}),
            turn=turn, total_tokens=total_tokens,
            parent_checkpoint_id=parent_checkpoint_id,
        )
        ms = self.memory_store

        # 大负载 → 文件，路径写入 file_path
        if checkpoint.is_large:
            checkpoint.file_path = self._save_large_payload(checkpoint)

        # 写入 MemoryNode
        from app.core.memory.memory_store import MemoryNode as MN
        ms.save(MN(**checkpoint.to_memory_node()))

        # 写边：检查点 → 所属会话
        ms.add_edge(checkpoint.id, session_id, SessionRelation.BELONGS_TO, weight=0.95)
        if parent_checkpoint_id:
            ms.add_edge(checkpoint.id, parent_checkpoint_id, SessionRelation.PARENT_CHECKPOINT, weight=0.90)

        self._cache[checkpoint.id] = checkpoint
        logger.info("Checkpoint saved: id=%s session=%s turn=%d msgs=%d large=%s",
                     checkpoint.id, session_id, turn, len(messages), checkpoint.is_large)
        return checkpoint

    def load(self, checkpoint_id: str) -> Checkpoint | None:
        """加载检查点 — MemoryStore 元数据 + 可选文件负载"""
        if checkpoint_id in self._cache:
            return self._cache[checkpoint_id]

        ms = self.memory_store
        mn = ms.get(checkpoint_id)
        if mn is None or mn.memory_type != "checkpoint":
            return None

        cp = Checkpoint.from_memory_node(mn)

        # 大负载 → 从文件恢复
        if cp.file_path and not cp.messages:
            file_data = self._load_large_payload(cp.file_path)
            if file_data:
                cp.messages = file_data.get("messages", [])
                cp.tool_results = file_data.get("tool_results", [])
                cp.agent_config = file_data.get("agent_config", {})

        self._cache[checkpoint_id] = cp
        return cp

    def delete(self, checkpoint_id: str) -> bool:
        """删除检查点 — MemoryNode + 文件 + 边（MemoryStore.delete 自动清边）"""
        cp = self.load(checkpoint_id)
        if cp and cp.file_path:
            Path(cp.file_path).unlink(missing_ok=True)
        self.memory_store.delete(checkpoint_id)
        self._cache.pop(checkpoint_id, None)
        return True

    def list_for_session(self, session_id: str) -> list[Checkpoint]:
        """列出会话的所有检查点（通过 BELONGS_TO 边查询）"""
        ms = self.memory_store
        db = ms._ensure_db()
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """SELECT mn.* FROM memory_nodes mn
               INNER JOIN memory_edges me ON me.source_id = mn.id
               WHERE me.target_id = ? AND me.relation_type = ?
                 AND mn.memory_type = 'checkpoint'
               ORDER BY mn.created_at DESC""",
            (session_id, SessionRelation.BELONGS_TO),
        ).fetchall()
        db.row_factory = None
        return [Checkpoint.from_memory_node(ms._row_to_node(r)) for r in rows]

    def list_all(self, limit: int = 100) -> list[dict[str, Any]]:
        ms = self.memory_store
        db = ms._ensure_db()
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT * FROM memory_nodes WHERE memory_type = 'checkpoint' "
            "ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        db.row_factory = None
        return [Checkpoint.from_memory_node(ms._row_to_node(r)).to_dict(include_payload=False) for r in rows]

    def count(self) -> int:
        db = self.memory_store._ensure_db()
        return db.execute(
            "SELECT COUNT(*) FROM memory_nodes WHERE memory_type = 'checkpoint'"
        ).fetchone()[0]


# ── Session 树 ─────────────────────────────────────────────

class SessionTree:
    """
    Session 树管理器 — 基于 MemoryStore（SQLite 图数据库 data/memory.db）

    借鉴 hermes-agent 的 Session 树：
      - 根节点：初始用户请求
      - 分支节点：从任意节点的 fork 点
      - 叶子节点：当前活跃 / 已完成的分支

    持久化映射:
      SessionNode → MemoryNode(memory_type="session")
      父→子       → MemoryEdge(CONVERSATION_FLOW)
      fork源→分支 → MemoryEdge(BRANCHES_FROM)
      恢复关系     → MemoryEdge(RESTORED_FROM)
    """

    _memory_store = None

    def __init__(self, max_nodes: int = 100,
                 checkpoint_manager: CheckpointManager | None = None,
                 memory_store=None, storage_manager=None):
        self.max_nodes = max_nodes
        self._ms = memory_store
        self.checkpoints = checkpoint_manager or CheckpointManager(
            memory_store=memory_store, storage_manager=storage_manager)

        self._nodes: dict[str, SessionNode] = {}
        self._root_ids: list[str] = []

        # 从 MemoryStore 恢复
        self._init_from_memory_store()

    @property
    def memory_store(self):
        if self._ms is None:
            from app.core.memory.memory_store import get_memory_store
            self._ms = get_memory_store()
        return self._ms

    @property
    def nodes(self) -> dict[str, SessionNode]:
        return self._nodes

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def root_nodes(self) -> list[SessionNode]:
        return [self._nodes[rid] for rid in self._root_ids if rid in self._nodes]

    # ── MemoryStore 启动恢复 ────────────────────────────

    def _init_from_memory_store(self) -> None:
        """从 MemoryStore 加载所有 session 节点，重建边关系"""
        ms = self.memory_store
        try:
            db = ms._ensure_db()
            db.row_factory = sqlite3.Row
            rows = db.execute(
                "SELECT * FROM memory_nodes WHERE memory_type = 'session' ORDER BY created_at ASC"
            ).fetchall()
            db.row_factory = None

            for row in rows:
                mn = ms._row_to_node(row)
                node = SessionNode.from_memory_node(mn)

                # 从边恢复 children（parent → child 是 CONVERSATION_FLOW）
                child_rows = db.execute(
                    "SELECT target_id FROM memory_edges WHERE source_id = ? AND relation_type = ?",
                    (node.id, SessionRelation.CONVERSATION_FLOW),
                ).fetchall()
                node.children_ids = [r[0] for r in child_rows]

                # 从边恢复 parent
                parent_rows = db.execute(
                    "SELECT source_id FROM memory_edges WHERE target_id = ? AND relation_type = ?",
                    (node.id, SessionRelation.CONVERSATION_FLOW),
                ).fetchall()
                node.parent_id = parent_rows[0][0] if parent_rows else None

                # 同步 metadata 中的 parent_id/children_ids
                self._nodes[node.id] = node

            # 找根节点
            self._root_ids = [nid for nid, n in self._nodes.items() if n.is_root]

            logger.info("SessionTree restored from MemoryStore: %d nodes, %d roots",
                         len(self._nodes), len(self._root_ids))
        except Exception as e:
            logger.error("Failed to restore SessionTree from MemoryStore: %s", e)

    # ── MemoryStore 持久化 ─────────────────────────────

    def _save_node_to_memory(self, node: SessionNode) -> None:
        """将单个节点同步到 MemoryStore"""
        ms = self.memory_store
        from app.core.memory.memory_store import MemoryNode as MN
        ms.save(MN(**node.to_memory_node()))

    def _save_edge(self, source_id: str, target_id: str, rel_type: str, weight: float = 0.80) -> None:
        """保存边关系到 MemoryStore"""
        self.memory_store.add_edge(source_id, target_id, rel_type, weight)

    def _delete_node_from_memory(self, node_id: str) -> None:
        """从 MemoryStore 删除节点（自动清理边）"""
        self.memory_store.delete(node_id)

    # ── 节点管理 ───────────────────────────────────────

    def create_session(
        self, agent_id: str = "", user_message: str = "",
        agent_config: dict[str, Any] | None = None,
        parent_id: str | None = None, branch_name: str = "main",
        branch_reason: str = "", forked_from: str | None = None,
    ) -> SessionNode:
        """创建新会话节点 → MemoryStore"""
        if self.node_count >= self.max_nodes:
            self._evict_oldest()

        depth = 0
        if parent_id and parent_id in self._nodes:
            depth = self._nodes[parent_id].depth + 1

        node = SessionNode(
            agent_id=agent_id, parent_id=parent_id,
            branch_name=branch_name, branch_reason=branch_reason,
            forked_from=forked_from or parent_id, depth=depth,
            user_message=user_message, agent_config=agent_config or {},
        )

        # 注册到内存
        self._nodes[node.id] = node
        if parent_id and parent_id in self._nodes:
            self._nodes[parent_id].children_ids.append(node.id)
        else:
            self._root_ids.append(node.id)

        # 持久化到 MemoryStore
        self._save_node_to_memory(node)
        if parent_id:
            self._save_edge(parent_id, node.id, SessionRelation.CONVERSATION_FLOW)
        if forked_from and forked_from != parent_id:
            self._save_edge(forked_from, node.id, SessionRelation.BRANCHES_FROM, weight=0.85)

        logger.info("Session created: id=%s agent=%s branch=%s depth=%d parent=%s",
                     node.id, agent_id, branch_name, depth, parent_id or "root")
        return node

    def fork(self, node_id: str, branch_name: str = "",
             branch_reason: str = "", save_checkpoint: bool = True) -> SessionNode | None:
        """从指定节点 fork 新分支 → MemoryStore"""
        if node_id not in self._nodes:
            logger.error("Fork failed: node %s not found", node_id)
            return None

        source = self._nodes[node_id]

        # 保存检查点
        if save_checkpoint and source.messages:
            self.save_checkpoint(
                session_id=node_id, agent_id=source.agent_id,
                messages=source.messages, tool_results=source.tool_results,
                agent_config=source.agent_config,
                label=f"auto-fork-{branch_name or 'branch'}",
                description=f"Auto-saved checkpoint at fork from '{source.branch_name}'",
                turn=source.total_turns, total_tokens=source.total_tokens,
            )

        if source.status == "completed":
            source.status = "branched"
            self._save_node_to_memory(source)  # 同步状态更新

        branch = self.create_session(
            agent_id=source.agent_id, user_message=source.user_message,
            agent_config=dict(source.agent_config),
            parent_id=source.parent_id,  # 同级分支
            branch_name=branch_name or f"branch-{len(source.children_ids) + 1}",
            branch_reason=branch_reason, forked_from=node_id,
        )
        branch.messages = [dict(m) for m in source.messages]
        branch.tool_results = [dict(tr) for tr in source.tool_results]

        logger.info("Branch forked: %s → %s (%s)", node_id, branch.id, branch.branch_name)
        return branch

    def update_node(self, node_id: str, **updates) -> bool:
        """更新节点属性 → MemoryStore"""
        if node_id not in self._nodes:
            return False
        node = self._nodes[node_id]
        for key, value in updates.items():
            if hasattr(node, key):
                setattr(node, key, value)
        self._save_node_to_memory(node)
        return True

    def get_node(self, node_id: str) -> SessionNode | None:
        return self._nodes.get(node_id)

    def get_children(self, node_id: str) -> list[SessionNode]:
        if node_id not in self._nodes:
            return []
        return [self._nodes[cid] for cid in self._nodes[node_id].children_ids if cid in self._nodes]

    def get_subtree(self, node_id: str) -> list[SessionNode]:
        if node_id not in self._nodes:
            return []
        result = [self._nodes[node_id]]
        for child_id in self._nodes[node_id].children_ids:
            result.extend(self.get_subtree(child_id))
        return result

    def get_branch_chain(self, node_id: str) -> list[SessionNode]:
        chain: list[SessionNode] = []
        current = self._nodes.get(node_id)
        while current:
            chain.insert(0, current)
            current = self._nodes.get(current.parent_id) if current.parent_id else None
        return chain

    def get_all_branches(self, root_id: str | None = None) -> list[dict[str, Any]]:
        branches = []
        root_ids = [root_id] if root_id else self._root_ids
        for rid in root_ids:
            if rid not in self._nodes:
                continue
            for node in self.get_subtree(rid):
                branches.append(node.to_dict(include_messages=False))
        return branches

    # ── 检查点 ────────────────────────────────────────

    def save_checkpoint(self, session_id: str, agent_id: str,
                        messages: list[dict[str, Any]], tool_results: list[dict[str, Any]],
                        agent_config: dict[str, Any], label: str = "",
                        description: str = "", turn: int = 0, total_tokens: int = 0,
                        ) -> Checkpoint:
        """保存检查点 → MemoryStore + 关联节点"""
        cp = self.checkpoints.save(
            session_id=session_id, agent_id=agent_id,
            messages=messages, tool_results=tool_results,
            agent_config=agent_config, label=label,
            description=description, turn=turn, total_tokens=total_tokens,
        )
        if session_id in self._nodes:
            self._nodes[session_id].checkpoint_id = cp.id
            self._save_node_to_memory(self._nodes[session_id])
        return cp

    async def restore(self, checkpoint_id: str,
                      agent_config: dict[str, Any] | None = None,
                      user_message: str = "") -> SessionNode | None:
        """从检查点恢复会话 → 创建节点 + RESTORED_FROM 边"""
        cp = self.checkpoints.load(checkpoint_id)
        if not cp:
            logger.error("Restore failed: checkpoint %s not found", checkpoint_id)
            return None

        node = self.create_session(
            agent_id=cp.agent_id,
            user_message=user_message or f"Restored from checkpoint {cp.id}",
            agent_config=agent_config or cp.agent_config,
            branch_name=f"restored-{checkpoint_id[:8]}",
            branch_reason=f"Checkpoint restore from turn {cp.turn}",
        )
        node.messages = [dict(m) for m in cp.messages]
        node.tool_results = [dict(tr) for tr in cp.tool_results]
        node.restored_from_checkpoint = checkpoint_id
        node.total_turns = cp.turn
        node.total_tokens = cp.total_tokens

        # 恢复关系边
        self._save_edge(node.id, checkpoint_id, SessionRelation.RESTORED_FROM, weight=0.95)
        self._save_node_to_memory(node)

        logger.info("Session restored: id=%s from checkpoint=%s messages=%d",
                     node.id, checkpoint_id, len(node.messages))
        return node

    def get_checkpoints_for_node(self, node_id: str) -> list[Checkpoint]:
        if node_id not in self._nodes:
            return []
        return self.checkpoints.list_for_session(node_id)

    # ── 淘汰 ─────────────────────────────────────────

    def _evict_oldest(self) -> None:
        """淘汰最旧根节点及其子树（MemoryStore + 检查点）"""
        if not self._root_ids:
            return
        oldest_root = self._root_ids[0]
        if oldest_root in self._nodes:
            to_delete = self.get_subtree(oldest_root)
            for node in to_delete:
                if node.checkpoint_id:
                    self.checkpoints.delete(node.checkpoint_id)
                self._delete_node_from_memory(node.id)  # MemoryStore 自动清边
                self._nodes.pop(node.id, None)
            self._root_ids.remove(oldest_root)
            logger.info("Evicted session tree root '%s' and %d descendants",
                         oldest_root, len(to_delete) - 1)

    def tree_summary(self, root_id: str | None = None) -> dict[str, Any]:
        root_ids = [root_id] if root_id else self._root_ids
        result: dict[str, Any] = {
            "total_nodes": self.node_count, "total_roots": len(self._root_ids),
            "total_checkpoints": self.checkpoints.count(), "trees": [],
            "storage": "MemoryStore (data/memory.db) + StorageManager (大型检查点)",
        }
        for rid in root_ids:
            if rid not in self._nodes:
                continue
            subtree = self.get_subtree(rid)
            branches = set()
            statuses = {}
            max_depth = 0
            for node in subtree:
                branches.add(node.branch_name)
                statuses[node.status] = statuses.get(node.status, 0) + 1
                if node.depth > max_depth:
                    max_depth = node.depth
            result["trees"].append({
                "root_id": rid, "node_count": len(subtree),
                "branches": sorted(branches), "max_depth": max_depth,
                "status_breakdown": statuses,
                "leaf_nodes": [node.id for node in subtree if node.is_leaf],
            })
        return result


# ── 全局单例 ──────────────────────────────────────────────

_global_session_tree: SessionTree | None = None
_global_checkpoint_manager: CheckpointManager | None = None


def init_session_tree(
    max_nodes: int = 100,
    data_dir: str = "data",
    memory_store=None,
    storage_manager=None,
) -> SessionTree:
    """初始化全局 SessionTree（对接 MemoryStore + StorageManager）"""
    global _global_session_tree, _global_checkpoint_manager

    _global_checkpoint_manager = CheckpointManager(
        memory_store=memory_store,
        storage_manager=storage_manager,
        storage_subdir="checkpoints",
    )
    _global_session_tree = SessionTree(
        max_nodes=max_nodes,
        checkpoint_manager=_global_checkpoint_manager,
        memory_store=memory_store,
        storage_manager=storage_manager,
    )

    logger.info(
        "SessionTree initialized (MemoryStore): max_nodes=%d data_dir=%s",
        max_nodes, data_dir,
    )
    return _global_session_tree


def get_session_tree() -> SessionTree:
    """获取全局 SessionTree"""
    global _global_session_tree
    if _global_session_tree is None:
        return init_session_tree()
    return _global_session_tree


def get_checkpoint_manager() -> CheckpointManager:
    """获取全局 CheckpointManager"""
    global _global_checkpoint_manager
    if _global_checkpoint_manager is None:
        _global_checkpoint_manager = CheckpointManager()
    return _global_checkpoint_manager
