"""
Checkpoint/Rollback System — RooCode 风格状态快照 + 一键回滚

借鉴 RooCode checkpoints/ 设计：
- 每次 Agent 执行完成自动保存状态快照
- 快照包含：文件内容、Agent配置、对话历史摘要
- 支持回滚到任意 checkpoint (恢复文件内容)
- 最大保留 N 个 checkpoints (自动清理旧快照)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.checkpoint")


# ── Data Models ────────────────────────────────────────


@dataclass
class FileSnapshot:
    """单个文件的快照"""
    path: str                    # 相对工作区路径
    content_hash: str            # sha256
    content: str                 # 完整文件内容 (小文件) 或备份路径 (大文件)
    stored_inline: bool = True   # True=content存此对象, False=存入外部文件


@dataclass
class FileCheckpoint:
    """Agent 执行文件检查点 (RooCode 风格 — 文件内容快照)"""
    id: str
    agent_name: str
    turn_number: int
    timestamp: float
    user_message: str            # 触发此检查点的用户消息
    assistant_summary: str       # AI 回复摘要 (前200字符)
    
    # 文件快照
    files_modified: list[FileSnapshot] = field(default_factory=list)
    
    # 元数据
    model_used: str = ""
    tokens_used: int = 0
    tool_calls_count: int = 0
    
    # 存储
    _backup_dir: str = ""        # 大文件备份目录 (内部使用)


# ── Checkpoint Manager ─────────────────────────────────


class FileCheckpointManager:
    """
    检查点管理器
    
    用法:
        cpm = CheckpointManager(workspace="/project", storage_dir="data/checkpoints")
        
        # 保存快照
        cp = await cpm.save(snapshot)
        
        # 列出所有检查点
        cps = cpm.list(agent_name="code")
        
        # 回滚到指定检查点
        files_restored = await cpm.rollback(checkpoint_id)
        
        # 清理旧检查点
        await cpm.cleanup(max_checkpoints=50)
    """
    
    MAX_INLINE_SIZE = 50 * 1024   # 50KB — 小文件存内存，大文件存磁盘
    MAX_TOTAL_CHECKPOINTS = 100   # 默认最大保留数
    
    def __init__(
        self,
        workspace: str = "",
        storage_dir: str = "data/file_checkpoints",
        max_checkpoints: int = 100,
    ):
        self._workspace = str(Path(workspace).resolve()) if workspace else str(Path.cwd())
        self._storage = Path(storage_dir)
        self._max_checkpoints = max_checkpoints
        self._storage.mkdir(parents=True, exist_ok=True)
        self._index_file = self._storage / "index.json"
        self._index: dict[str, FileCheckpoint] = {}
        self._load_index()
    
    # ── 公共 API ────────────────────────────────────
    
    async def save(
        self,
        agent_name: str,
        user_message: str,
        assistant_summary: str = "",
        modified_files: list[str] | None = None,
        model_used: str = "",
        tokens_used: int = 0,
        tool_calls_count: int = 0,
        turn_number: int = 1,
    ) -> FileCheckpoint:
        """
        保存一个检查点
        
        Args:
            agent_name: Agent 名称
            user_message: 触发检查点的用户消息
            assistant_summary: AI 回复摘要
            modified_files: 此轮修改的文件列表 (相对路径)
            model_used: 使用的模型
            tokens_used: Token 消耗
            tool_calls_count: 工具调用次数
            turn_number: 当前轮次
            
        Returns:
            Checkpoint 对象
        """
        cp_id = str(uuid.uuid4())[:12]
        backup_dir = self._storage / cp_id
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        # 快照修改的文件
        file_snapshots: list[FileSnapshot] = []
        for rel_path in (modified_files or []):
            snap = self._snapshot_file(rel_path, backup_dir)
            if snap:
                file_snapshots.append(snap)
        
        cp = FileCheckpoint(
            id=cp_id,
            agent_name=agent_name,
            turn_number=turn_number,
            timestamp=time.time(),
            user_message=user_message[:500],
            assistant_summary=assistant_summary[:200],
            files_modified=file_snapshots,
            model_used=model_used,
            tokens_used=tokens_used,
            tool_calls_count=tool_calls_count,
            _backup_dir=str(backup_dir),
        )
        
        self._index[cp_id] = cp
        self._save_index()
        
        logger.info(
            "Checkpoint saved: %s (agent=%s, turn=%d, files=%d)",
            cp_id, agent_name, turn_number, len(file_snapshots),
        )
        return cp
    
    async def rollback(self, checkpoint_id: str) -> dict[str, Any]:
        """
        回滚到指定检查点
        
        Returns:
            {"restored": [file_path, ...], "failed": [file_path, ...]}
        """
        cp = self._index.get(checkpoint_id)
        if not cp:
            raise ValueError(f"Checkpoint '{checkpoint_id}' not found")
        
        restored: list[str] = []
        failed: list[str] = []
        
        for snap in cp.files_modified:
            try:
                if snap.stored_inline:
                    # 小文件：直接从内存恢复
                    target = Path(self._workspace) / snap.path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(snap.content, encoding="utf-8")
                    restored.append(snap.path)
                else:
                    # 大文件：从备份文件恢复
                    backup_file = Path(cp._backup_dir) / f"{snap.content_hash}.bak"
                    if backup_file.exists():
                        target = Path(self._workspace) / snap.path
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(backup_file), str(target))
                        restored.append(snap.path)
                    else:
                        failed.append(snap.path)
            except Exception as e:
                logger.error("Failed to restore %s: %s", snap.path, e)
                failed.append(snap.path)
        
        logger.info(
            "Rollback to %s: %d restored, %d failed",
            checkpoint_id, len(restored), len(failed),
        )
        return {"restored": restored, "failed": failed}
    
    def list(
        self,
        agent_name: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """列出检查点"""
        items = list(self._index.values())
        items.sort(key=lambda x: x.timestamp, reverse=True)
        
        if agent_name:
            items = [c for c in items if c.agent_name == agent_name]
        
        result = []
        for cp in items[offset:offset + limit]:
            result.append({
                "id": cp.id,
                "agent_name": cp.agent_name,
                "turn_number": cp.turn_number,
                "timestamp": cp.timestamp,
                "user_message": cp.user_message[:200],
                "assistant_summary": cp.assistant_summary,
                "files_count": len(cp.files_modified),
                "files_modified": [
                    {"path": s.path, "hash": s.content_hash[:12]}
                    for s in cp.files_modified
                ],
                "model_used": cp.model_used,
                "tokens_used": cp.tokens_used,
                "tool_calls_count": cp.tool_calls_count,
            })
        return result
    
    def get(self, checkpoint_id: str) -> FileCheckpoint | None:
        """获取单个检查点"""
        return self._index.get(checkpoint_id)
    
    async def cleanup(self, max_checkpoints: int | None = None) -> int:
        """
        清理旧检查点
        
        Returns:
            删除的检查点数量
        """
        limit = max_checkpoints or self._max_checkpoints
        items = list(self._index.values())
        items.sort(key=lambda x: x.timestamp, reverse=True)
        
        deleted = 0
        for cp in items[limit:]:
            # 删除备份目录
            try:
                backup_dir = Path(cp._backup_dir) if cp._backup_dir else self._storage / cp.id
                if backup_dir.exists():
                    shutil.rmtree(str(backup_dir))
            except Exception as e:
                logger.warning("Failed to clean checkpoint %s: %s", cp.id, e)
            
            del self._index[cp.id]
            deleted += 1
        
        if deleted:
            self._save_index()
            logger.info("Cleaned %d old checkpoints (remaining: %d)", deleted, len(self._index))
        
        return deleted
    
    @property
    def total(self) -> int:
        """检查点总数"""
        return len(self._index)
    
    # ── 内部方法 ────────────────────────────────────
    
    def _snapshot_file(self, rel_path: str, backup_dir: Path) -> FileSnapshot | None:
        """创建单个文件的快照"""
        target = Path(self._workspace) / rel_path
        if not target.is_file():
            return None
        
        try:
            content = target.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            # 二进制文件或权限错误 → 读为 bytes + 备份
            try:
                content_bytes = target.read_bytes()
                content_hash = hashlib.sha256(content_bytes).hexdigest()
                backup_file = backup_dir / f"{content_hash}.bak"
                shutil.copy2(str(target), str(backup_file))
                return FileSnapshot(
                    path=rel_path,
                    content_hash=content_hash,
                    content="",
                    stored_inline=False,
                )
            except Exception:
                return None
        
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        
        if len(content) <= self.MAX_INLINE_SIZE:
            return FileSnapshot(
                path=rel_path,
                content_hash=content_hash,
                content=content,
                stored_inline=True,
            )
        else:
            # 大文件备份到磁盘
            backup_file = backup_dir / f"{content_hash}.bak"
            backup_file.write_text(content, encoding="utf-8")
            return FileSnapshot(
                path=rel_path,
                content_hash=content_hash,
                content="",
                stored_inline=False,
            )
    
    def _load_index(self) -> None:
        """从磁盘加载索引"""
        if self._index_file.exists():
            try:
                data = json.loads(self._index_file.read_text(encoding="utf-8"))
                for cp_id, raw in data.items():
                    cp = FileCheckpoint(
                        id=raw["id"],
                        agent_name=raw["agent_name"],
                        turn_number=raw["turn_number"],
                        timestamp=raw["timestamp"],
                        user_message=raw.get("user_message", ""),
                        assistant_summary=raw.get("assistant_summary", ""),
                        files_modified=[
                            FileSnapshot(
                                path=f["path"],
                                content_hash=f["content_hash"],
                                content=f.get("content", ""),
                                stored_inline=f.get("stored_inline", True),
                            )
                            for f in raw.get("files_modified", [])
                        ],
                        model_used=raw.get("model_used", ""),
                        tokens_used=raw.get("tokens_used", 0),
                        tool_calls_count=raw.get("tool_calls_count", 0),
                        _backup_dir=raw.get("_backup_dir", str(self._storage / cp_id)),
                    )
                    self._index[cp_id] = cp
                logger.info("Loaded %d checkpoints from index", len(self._index))
            except Exception as e:
                logger.warning("Failed to load checkpoint index: %s", e)
                self._index = {}
    
    def _save_index(self) -> None:
        """保存索引到磁盘 (只保存行内内容, 大文件由备份目录管理)"""
        data = {}
        for cp_id, cp in self._index.items():
            data[cp_id] = {
                "id": cp.id,
                "agent_name": cp.agent_name,
                "turn_number": cp.turn_number,
                "timestamp": cp.timestamp,
                "user_message": cp.user_message,
                "assistant_summary": cp.assistant_summary,
                "files_modified": [
                    {
                        "path": s.path,
                        "content_hash": s.content_hash,
                        "content": s.content if s.stored_inline else "",
                        "stored_inline": s.stored_inline,
                    }
                    for s in cp.files_modified
                ],
                "model_used": cp.model_used,
                "tokens_used": cp.tokens_used,
                "tool_calls_count": cp.tool_calls_count,
                "_backup_dir": cp._backup_dir or str(self._storage / cp_id),
            }
        self._index_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 全局单例 ──────────────────────────────────────────


_global_file_checkpoint_manager: FileCheckpointManager | None = None


def init_file_checkpoint_manager(
    workspace: str = "",
    storage_dir: str = "data/file_checkpoints",
) -> FileCheckpointManager:
    global _global_file_checkpoint_manager
    _global_file_checkpoint_manager = FileCheckpointManager(
        workspace=workspace or str(Path.cwd()),
        storage_dir=storage_dir,
    )
    return _global_file_checkpoint_manager


def get_file_checkpoint_manager() -> FileCheckpointManager:
    global _global_file_checkpoint_manager
    if _global_file_checkpoint_manager is None:
        return init_file_checkpoint_manager()
    return _global_file_checkpoint_manager
