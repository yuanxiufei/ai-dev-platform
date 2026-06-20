"""
Git Checkpoints — 代码修改检查点/回滚系统

借鉴 Cline CheckpointTracker 设计：
  1. 每次 AI 代码修改前自动创建 Git 检查点（tag + stash）
  2. 支持一键回滚到任意检查点
  3. 检查点快照对比（diff）
  4. 单例模式 init_checkpoint_manager / get_checkpoint_manager

核心流程：
  AI 开始编辑 → create_checkpoint("pre-edit", metadata)
  AI 编辑完成 → 可选 delete_checkpoint 或保留
  AI 编辑失败 → restore_checkpoint 回滚
"""

import subprocess
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("app.core.checkpoint")


# ──────────────────────── 数据结构 ────────────────────────

@dataclass
class Checkpoint:
    """检查点记录"""
    id: str                                    # 检查点 ID (tag 名)
    timestamp: str                             # ISO 时间
    git_ref: str                               # Git 引用（分支/tag/commit）
    metadata: dict[str, Any] = field(default_factory=dict)  # 元数据
    file_count: int = 0                        # 变更文件数
    diff_summary: str = ""                     # 变更摘要


@dataclass
class CheckpointResult:
    """检查点操作结果"""
    success: bool
    checkpoint: Checkpoint | None = None
    error: str = ""


# ──────────────────────── 检查点管理器 ────────────────────────

class CheckpointManager:
    """Git 检查点管理器"""

    def __init__(self, repo_path: str = "", max_checkpoints: int = 50) -> None:
        self._repo_path = repo_path or str(Path.cwd())
        self._max_checkpoints = max_checkpoints
        self._tag_prefix = "ai-checkpoint-"
        self._active_checkpoints: dict[str, Checkpoint] = {}

    def _run_git(self, *args: str, capture: bool = True) -> tuple[str, str, int]:
        """执行 Git 命令"""
        cmd = ["git", "-C", self._repo_path] + list(args)
        try:
            result = subprocess.run(
                cmd, capture_output=capture, text=True, timeout=30,
            )
            return result.stdout.strip(), result.stderr.strip(), result.returncode
        except subprocess.TimeoutExpired:
            return "", "Git command timeout", -1
        except FileNotFoundError:
            return "", "Git not found", -2

    def _is_git_repo(self) -> bool:
        """检查是否是 Git 仓库"""
        _, _, rc = self._run_git("rev-parse", "--git-dir")
        return rc == 0

    def _generate_checkpoint_id(self, label: str = "") -> str:
        """生成唯一检查点 ID"""
        ts = int(time.time())
        return f"{self._tag_prefix}{ts}-{label}" if label else f"{self._tag_prefix}{ts}"

    # ── 创建检查点 ─────────────────────────────────
    def create(self, label: str = "", metadata: dict[str, Any] | None = None) -> CheckpointResult:
        """
        创建 Git 检查点
        步骤：git stash push → git tag <checkpoint-id> → git stash pop
        回滚时使用：git checkout <checkpoint-id>
        """
        if not self._is_git_repo():
            return CheckpointResult(success=False, error="Not a Git repository")

        checkpoint_id = self._generate_checkpoint_id(label or "snap")
        metadata = metadata or {}

        # 1. 检查是否有未暂存修改
        status_out, _, rc = self._run_git("status", "--porcelain")
        if rc != 0:
            return CheckpointResult(success=False, error=f"Git status failed: {status_out}")

        if not status_out:
            return CheckpointResult(success=False, error="No changes to checkpoint")

        # 2. 暂存所有变更
        stash_msg = f"WIP on tag {checkpoint_id}"
        _, err, rc = self._run_git("stash", "push", "--include-untracked", "-m", stash_msg)
        if rc != 0:
            return CheckpointResult(success=False, error=f"Stash failed: {err}")

        # 3. 获取当前 commit hash
        commit, _, rc = self._run_git("rev-parse", "HEAD")
        if rc != 0:
            # 恢复 stash 并返回错误
            self._run_git("stash", "pop")
            return CheckpointResult(success=False, error=f"Rev-parse failed: {commit}")

        # 4. 创建检查点 tag
        _, err, rc = self._run_git("tag", checkpoint_id, commit)
        if rc != 0:
            self._run_git("stash", "pop")
            return CheckpointResult(success=False, error=f"Tag creation failed: {err}")

        # 5. 恢复 stash
        _, err, rc = self._run_git("stash", "pop")
        if rc != 0:
            logger.warning("Checkpoint stash pop warning: %s", err)

        # 6. 统计变更
        file_count = len([l for l in status_out.split("\n") if l.strip()])

        checkpoint = Checkpoint(
            id=checkpoint_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            git_ref=commit[:8],
            metadata=metadata,
            file_count=file_count,
            diff_summary=status_out[:500],
        )

        self._active_checkpoints[checkpoint_id] = checkpoint
        self._prune_old_checkpoints()

        logger.info("Checkpoint created: %s (ref=%s, files=%d)", checkpoint_id, commit[:8], file_count)
        return CheckpointResult(success=True, checkpoint=checkpoint)

    # ── 恢复检查点 ─────────────────────────────────
    def restore(self, checkpoint_id: str) -> CheckpointResult:
        """
        回滚到指定检查点
        步骤：git checkout <checkpoint-id> → git stash pop（应用变更）
        """
        if not self._is_git_repo():
            return CheckpointResult(success=False, error="Not a Git repository")

        cp = self._active_checkpoints.get(checkpoint_id)
        if cp is None:
            return CheckpointResult(success=False, error=f"Checkpoint not found: {checkpoint_id}")

        # 1. 硬回滚到检查点
        _, err, rc = self._run_git("reset", "--hard", checkpoint_id)
        if rc != 0:
            return CheckpointResult(success=False, error=f"Reset failed: {err}")

        # 2. 清理工作区
        self._run_git("clean", "-fd")

        # 3. 删除检查点 tag
        self._run_git("tag", "-d", checkpoint_id)
        del self._active_checkpoints[checkpoint_id]

        logger.info("Checkpoint restored: %s", checkpoint_id)
        return CheckpointResult(success=True, checkpoint=cp)

    # ── 删除检查点 ─────────────────────────────────
    def delete(self, checkpoint_id: str) -> bool:
        """删除检查点（正常完成时调用）"""
        if not self._is_git_repo():
            return False

        _, _, rc = self._run_git("tag", "-d", checkpoint_id)
        if rc == 0 or "not found" in str(rc).lower():
            self._active_checkpoints.pop(checkpoint_id, None)
            logger.info("Checkpoint deleted: %s", checkpoint_id)
            return True
        return False

    # ── 列出检查点 ─────────────────────────────────
    def list_all(self) -> list[Checkpoint]:
        """列出所有活跃检查点"""
        return list(self._active_checkpoints.values())

    def get_diff(self, checkpoint_id: str) -> str:
        """获取检查点相对于 HEAD 的差异"""
        if not self._active_checkpoints.get(checkpoint_id):
            return ""

        diff, _, rc = self._run_git("diff", checkpoint_id, "HEAD", "--stat")
        return diff if rc == 0 else ""

    # ── 修剪旧检查点 ───────────────────────────────
    def _prune_old_checkpoints(self) -> None:
        """超过最大数量时删除最旧的检查点"""
        if len(self._active_checkpoints) <= self._max_checkpoints:
            return

        sorted_ids = sorted(
            self._active_checkpoints.keys(),
            key=lambda cid: self._active_checkpoints[cid].timestamp,
        )
        excess = len(self._active_checkpoints) - self._max_checkpoints

        for cid in sorted_ids[:excess]:
            self.delete(cid)
            logger.debug("Pruned old checkpoint: %s", cid)

    # ── 内嵌 diff 快速对比 ──────────────────────────
    def quick_diff(self, before_id: str, after_id: str = "HEAD") -> str:
        """两个检查点之间的快速 diff"""
        diff, _, rc = self._run_git("diff", before_id, after_id, "--stat")
        return diff if rc == 0 else ""


# ──────────────────────── 单例 ────────────────────────

_checkpoint_manager: CheckpointManager | None = None


def init_checkpoint_manager(
    repo_path: str = "",
    max_checkpoints: int = 50,
) -> CheckpointManager:
    """初始化检查点管理器"""
    global _checkpoint_manager
    _checkpoint_manager = CheckpointManager(
        repo_path=repo_path,
        max_checkpoints=max_checkpoints,
    )
    logger.info(
        "CheckpointManager initialized: repo=%s, max=%d",
        _checkpoint_manager._repo_path, max_checkpoints,
    )
    return _checkpoint_manager


def get_checkpoint_manager() -> CheckpointManager:
    """获取检查点管理器单例"""
    global _checkpoint_manager
    if _checkpoint_manager is None:
        _checkpoint_manager = CheckpointManager()
    return _checkpoint_manager
