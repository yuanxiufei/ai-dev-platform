"""
Worktree 管理 — Git Worktree 并行开发环境

借鉴 Roo-Code packages/core/src/worktree/ 设计：
- WorktreeManager: Git worktree CRUD (创建/列表/删除/检出/合并)
- WorktreeSanbox: 每个 worktree 关联独立 Sandbox 实现路径隔离
- WorktreeTask: 在 worktree 中执行的 Agent 任务（并行执行）
- 路径安全：所有 worktree 操作限制在仓库目录范围内
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.worktree")


# ══════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════


class WorktreeStatus(str, Enum):
    """Worktree 状态"""
    ACTIVE = "active"          # 正常使用中
    LOCKED = "locked"          # 被锁定（git worktree lock）
    PRUNING = "pruning"        # 正在清理
    DETACHED = "detached"      # 游离 HEAD（无分支关联）
    DELETED = "deleted"        # 已清理


@dataclass
class WorktreeInfo:
    """Worktree 元信息"""
    path: str = ""
    """worktree 在文件系统上的绝对路径"""
    branch: str = ""
    """关联的分支名（detached 时为空）"""
    commit_hash: str = ""
    """HEAD 提交哈希"""
    is_current: bool = False
    """是否为当前 worktree"""
    is_bare: bool = False
    """是否为裸仓库"""
    is_detached: bool = False
    """是否为游离 HEAD"""
    is_locked: bool = False
    """是否被锁定"""
    lock_reason: str = ""

    # 扩展字段
    status: WorktreeStatus = WorktreeStatus.ACTIVE
    created_at: str = ""  # ISO 8601
    task_count: int = 0
    """该 worktree 上执行过的任务数量"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "branch": self.branch,
            "commit_hash": self.commit_hash[:8] if self.commit_hash else "",
            "is_current": self.is_current,
            "is_detached": self.is_detached,
            "is_locked": self.is_locked,
            "lock_reason": self.lock_reason,
            "status": self.status.value,
            "created_at": self.created_at,
            "task_count": self.task_count,
        }


@dataclass
class WorktreeResult:
    """Worktree 操作结果"""
    success: bool
    message: str
    worktree: WorktreeInfo | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorktreeTask:
    """在 worktree 中执行的 Agent 任务"""
    task_id: str
    worktree_path: str
    branch: str
    description: str = ""
    status: str = "pending"  # pending | running | completed | failed
    started_at: str = ""
    completed_at: str = ""
    error: str = ""
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "worktree_path": self.worktree_path,
            "branch": self.branch,
            "description": self.description,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "error": self.error,
            "result": self.result,
        }


@dataclass
class WorktreeConfig:
    """Worktree 全局配置"""
    # Git 仓库根路径
    repo_root: str = ""

    # Worktree 存放目录（相对于 repo_root 或绝对路径）
    worktrees_dir: str = ".worktrees"

    # 最大同时 active 的 worktree 数量
    max_active_worktrees: int = 5

    # 自动清理：任务完成后 N 分钟后清理
    auto_cleanup_minutes: int = 60

    # 分支命名前缀
    branch_prefix: str = "agent/"

    # 是否允许 force 删除
    allow_force_delete: bool = True


# ══════════════════════════════════════════════════════════════
# Worktree 管理器
# ══════════════════════════════════════════════════════════════


class WorktreeManager:
    """Git worktree 管理器

    借鉴 Roo-Code WorktreeService — 平台无关的 git worktree 操作：
    - 创建/列表/删除 worktree
    - 分支列表（本地 + 远程）
    - 检出/合并
    - 与 Sandbox 集成：每个 worktree 关联独立沙箱
    """

    def __init__(self, config: WorktreeConfig | None = None) -> None:
        self.config = config or WorktreeConfig()
        self._tasks: dict[str, WorktreeTask] = {}
        self._lock = asyncio.Lock()

    # ── 仓库检测 ────────────────────────────────────────

    async def _git(self, *args: str, cwd: str | None = None) -> tuple[str, str, int]:
        """执行 git 命令，返回 (stdout, stderr, exit_code)"""
        work_dir = cwd or self.config.repo_root or os.getcwd()
        cmd = ["git"] + list(args)
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=work_dir,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=30,
            )
            return (
                stdout.decode("utf-8", errors="replace").strip(),
                stderr.decode("utf-8", errors="replace").strip(),
                proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            return "", "Git command timed out after 30s", -1
        except FileNotFoundError:
            return "", "Git not found on system", -1
        except Exception as e:
            return "", str(e), -1

    async def is_git_repo(self, cwd: str | None = None) -> bool:
        """检查是否为 git 仓库"""
        _, stderr, code = await self._git("rev-parse", "--git-dir", cwd=cwd)
        return code == 0

    async def get_repo_root(self, cwd: str | None = None) -> str | None:
        """获取 git 仓库根路径"""
        stdout, _, code = await self._git("rev-parse", "--show-toplevel", cwd=cwd)
        if code == 0 and stdout:
            return stdout
        return None

    def _ensure_config(self) -> None:
        """确保配置中有 repo_root"""
        if not self.config.repo_root:
            self.config.repo_root = os.getcwd()

    def _worktrees_root(self) -> Path:
        """获取 worktree 存放根目录"""
        self._ensure_config()
        wt_dir = self.config.worktrees_dir
        if os.path.isabs(wt_dir):
            return Path(wt_dir)
        return Path(self.config.repo_root) / wt_dir

    def _normalize_path(self, p: str) -> str:
        """规范化路径用于比较"""
        normalized = os.path.normpath(p)
        if len(normalized) > 1 and normalized.endswith(os.sep):
            normalized = normalized[:-1]
        return normalized

    # ── Worktree CRUD ────────────────────────────────────

    async def list_worktrees(self) -> list[WorktreeInfo]:
        """列出所有 worktree"""
        self._ensure_config()

        stdout, stderr, code = await self._git(
            "worktree", "list", "--porcelain",
            cwd=self.config.repo_root,
        )
        if code != 0 or not stdout:
            logger.warning("List worktrees failed: %s", stderr)
            return []

        return self._parse_porcelain(stdout)

    def _parse_porcelain(self, output: str) -> list[WorktreeInfo]:
        """解析 git worktree list --porcelain 输出"""
        worktrees: list[WorktreeInfo] = []
        entries = output.strip().split("\n\n")

        for entry in entries:
            if not entry.strip():
                continue

            info = WorktreeInfo()
            lines = entry.strip().split("\n")

            for line in lines:
                if line.startswith("worktree "):
                    info.path = line[9:].strip()
                elif line.startswith("HEAD "):
                    info.commit_hash = line[5:].strip()
                elif line.startswith("branch "):
                    branch_ref = line[7:].strip()
                    info.branch = branch_ref.replace("refs/heads/", "")
                elif line == "bare":
                    info.is_bare = True
                elif line == "detached":
                    info.is_detached = True
                    info.status = WorktreeStatus.DETACHED
                elif line == "locked":
                    info.is_locked = True
                    info.status = WorktreeStatus.LOCKED
                elif line.startswith("locked "):
                    info.is_locked = True
                    info.lock_reason = line[7:].strip()
                    info.status = WorktreeStatus.LOCKED

            if info.path:
                info.is_current = (
                    self._normalize_path(info.path)
                    == self._normalize_path(self.config.repo_root)
                )
                # 任务计数
                info.task_count = sum(
                    1 for t in self._tasks.values()
                    if self._normalize_path(t.worktree_path) == self._normalize_path(info.path)
                )
                worktrees.append(info)

        return worktrees

    async def create_worktree(
        self,
        branch: str = "",
        base_branch: str = "",
        create_new_branch: bool = True,
        path_override: str = "",
        description: str = "",
    ) -> WorktreeResult:
        """创建新的 worktree

        Args:
            branch: 分支名（create_new_branch=True 时必填）
            base_branch: 基础分支（从哪个分支分叉）
            create_new_branch: 是否创建新分支（False 则检出已有分支）
            path_override: 覆盖 worktree 路径（默认自动生成）
            description: 任务描述
        """
        self._ensure_config()

        # 检查上限
        existing = await self.list_worktrees()
        active_count = sum(1 for wt in existing if wt.status == WorktreeStatus.ACTIVE)
        if active_count >= self.config.max_active_worktrees:
            return WorktreeResult(
                success=False,
                message=f"Max active worktrees ({self.config.max_active_worktrees}) reached. "
                        f"Active: {active_count}",
            )

        # 生成分支名
        if create_new_branch and not branch:
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            branch = f"{self.config.branch_prefix}{ts}"
        elif create_new_branch and self.config.branch_prefix and not branch.startswith(self.config.branch_prefix):
            branch = f"{self.config.branch_prefix}{branch}"

        if not branch:
            return WorktreeResult(success=False, message="Branch name is required")

        # 检查分支名冲突
        stdout, _, code = await self._git("branch", "--list", branch, cwd=self.config.repo_root)
        if code == 0 and stdout.strip() and create_new_branch:
            return WorktreeResult(
                success=False,
                message=f"Branch '{branch}' already exists. Use a different name or set create_new_branch=false.",
            )

        # 生成 worktree 路径
        if path_override:
            worktree_path = path_override
        else:
            safe_branch = re.sub(r"[^a-zA-Z0-9_\-.]", "_", branch)
            wt_root = self._worktrees_root()
            wt_root.mkdir(parents=True, exist_ok=True)
            worktree_path = str(wt_root / safe_branch)

        # 如果路径已存在，追加时间戳
        if os.path.exists(worktree_path):
            ts = datetime.now(timezone.utc).strftime("%H%M%S")
            worktree_path = f"{worktree_path}_{ts}"

        # 执行 git worktree add
        args = ["worktree", "add"]
        if create_new_branch:
            args.extend(["-b", branch, worktree_path])
            if base_branch:
                args.append(base_branch)
        else:
            args.extend([worktree_path, branch])

        stdout, stderr, code = await self._git(*args, cwd=self.config.repo_root)

        if code != 0:
            logger.error("Create worktree failed: %s", stderr)
            return WorktreeResult(
                success=False,
                message=f"Failed to create worktree: {stderr}",
            )

        # 汇总信息
        info = await self._get_worktree_by_path(worktree_path)
        if info:
            info.created_at = datetime.now(timezone.utc).isoformat()
            info.task_count = 0
            return WorktreeResult(
                success=True,
                message=f"Worktree created: {branch} → {worktree_path}",
                worktree=info,
            )

        return WorktreeResult(
            success=True,
            message=f"Worktree created at {worktree_path}",
        )

    async def delete_worktree(
        self,
        worktree_path: str,
        force: bool | None = None,
    ) -> WorktreeResult:
        """删除 worktree

        Args:
            worktree_path: worktree 路径
            force: 强制删除（默认使用配置中的 allow_force_delete）
        """
        self._ensure_config()

        if force is None:
            force = self.config.allow_force_delete

        # 获取删除前的信息
        info = await self._get_worktree_by_path(worktree_path)

        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(worktree_path)

        stdout, stderr, code = await self._git(*args, cwd=self.config.repo_root)

        if code != 0:
            logger.error("Delete worktree failed: %s", stderr)
            return WorktreeResult(
                success=False,
                message=f"Failed to delete worktree: {stderr}",
            )

        # 尝试删除分支
        if info and info.branch and not info.is_detached:
            try:
                await self._git("branch", "-d", info.branch, cwd=self.config.repo_root)
            except Exception:
                pass  # 非关键

        # 清理任务记录
        async with self._lock:
            to_remove = [
                tid for tid, t in self._tasks.items()
                if self._normalize_path(t.worktree_path) == self._normalize_path(worktree_path)
            ]
            for tid in to_remove:
                del self._tasks[tid]

        return WorktreeResult(
            success=True,
            message=f"Worktree removed: {worktree_path}",
        )

    async def get_worktree_info(self, worktree_path: str) -> WorktreeInfo | None:
        """获取单个 worktree 详情"""
        return await self._get_worktree_by_path(worktree_path)

    async def _get_worktree_by_path(self, worktree_path: str) -> WorktreeInfo | None:
        """按路径查找 worktree"""
        worktrees = await self.list_worktrees()
        normalized = self._normalize_path(worktree_path)
        for wt in worktrees:
            if self._normalize_path(wt.path) == normalized:
                return wt
        return None

    async def get_branches(self, include_worktree_branches: bool = False) -> dict[str, Any]:
        """获取可用分支列表（本地 + 远程）

        Args:
            include_worktree_branches: 是否包含已在 worktree 中的分支
        """
        self._ensure_config()

        # 并行查询
        wt_list, local_out, remote_out, current_out = await asyncio.gather(
            self.list_worktrees(),
            self._git("branch", "--format=%(refname:short)", cwd=self.config.repo_root),
            self._git("branch", "-r", "--format=%(refname:short)", cwd=self.config.repo_root),
            self._git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.config.repo_root),
        )

        branches_in_worktrees: set[str] = {
            wt.branch for wt in wt_list if wt.branch
        }

        def _filter(branch_list: list[str]) -> list[str]:
            if include_worktree_branches:
                return branch_list
            return [b for b in branch_list if b not in branches_in_worktrees]

        local_branches = _filter(
            [b.strip() for b in local_out[0].split("\n") if b.strip()]
        ) if local_out[2] == 0 else []

        remote_branches = _filter([
            b.strip() for b in remote_out[0].split("\n")
            if b.strip() and "HEAD" not in b
        ]) if remote_out[2] == 0 else []

        current_branch = current_out[0].strip() if current_out[2] == 0 else ""

        return {
            "local_branches": local_branches,
            "remote_branches": remote_branches,
            "current_branch": current_branch if current_branch != "HEAD" else "",
            "active_worktrees": len(wt_list),
        }

    async def checkout_branch(self, branch: str, worktree_path: str | None = None) -> WorktreeResult:
        """在指定或当前 worktree 中检出分支"""
        cwd = worktree_path or self.config.repo_root
        stdout, stderr, code = await self._git("checkout", branch, cwd=cwd)
        if code != 0:
            return WorktreeResult(
                success=False,
                message=f"Failed to checkout branch '{branch}': {stderr}",
            )
        return WorktreeResult(
            success=True,
            message=f"Checked out branch '{branch}' in {cwd}",
        )

    async def merge_branch(
        self,
        source_branch: str,
        worktree_path: str | None = None,
        message: str = "",
    ) -> WorktreeResult:
        """在 worktree 中合并分支"""
        self._ensure_config()
        cwd = worktree_path or self.config.repo_root

        args = ["merge", source_branch]
        if message:
            args.extend(["-m", message])

        stdout, stderr, code = await self._git(*args, cwd=cwd)
        if code != 0:
            return WorktreeResult(
                success=False,
                message=f"Merge '{source_branch}' failed: {stderr}",
                data={"conflict": "CONFLICT" in stderr or "CONFLICT" in stdout},
            )
        return WorktreeResult(
            success=True,
            message=f"Merged '{source_branch}' into {cwd}",
        )

    async def get_diff(self, worktree_path: str | None = None) -> str:
        """获取 worktree 的 git diff"""
        self._ensure_config()
        cwd = worktree_path or self.config.repo_root
        stdout, _, _ = await self._git("diff", "--stat", cwd=cwd)
        return stdout

    async def clean_orphan_worktrees(self) -> WorktreeResult:
        """清理文件系统上存在但 git 不认识的孤立 worktree 目录"""
        self._ensure_config()
        wt_root = self._worktrees_root()
        if not wt_root.exists():
            return WorktreeResult(success=True, message="No worktree directory found")

        # 获取 git 记录的 worktree 路径
        tracked = await self.list_worktrees()
        tracked_paths = {
            self._normalize_path(wt.path) for wt in tracked
        }

        cleaned = 0
        for child in wt_root.iterdir():
            if child.is_dir():
                normalized = self._normalize_path(str(child))
                if normalized not in tracked_paths:
                    try:
                        # 检查是否还是 git 仓库
                        git_dir = child / ".git"
                        if git_dir.exists() and git_dir.is_file():
                            # 这是 git worktree 的 .git 文件，读内容判断
                            content = git_dir.read_text().strip()
                            if "gitdir:" in content:
                                # 尝试 prune
                                await self._git("worktree", "prune", cwd=self.config.repo_root)
                    except Exception:
                        pass

        return WorktreeResult(
            success=True,
            message=f"Cleaned {cleaned} orphan worktree directories",
        )

    # ── 任务关联 ────────────────────────────────────────

    async def register_task(self, task: WorktreeTask) -> None:
        """注册任务到 worktree"""
        async with self._lock:
            self._tasks[task.task_id] = task
            task.started_at = datetime.now(timezone.utc).isoformat()
            task.status = "running"
        logger.info("Task %s registered on worktree %s", task.task_id, task.worktree_path)

    async def complete_task(
        self,
        task_id: str,
        success: bool,
        error: str = "",
        result: dict[str, Any] | None = None,
    ) -> WorktreeTask | None:
        """完成任务"""
        async with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = "completed" if success else "failed"
                task.completed_at = datetime.now(timezone.utc).isoformat()
                task.error = error
                task.result = result or {}
        return task

    async def get_task(self, task_id: str) -> WorktreeTask | None:
        """获取任务"""
        return self._tasks.get(task_id)

    async def list_tasks(
        self,
        worktree_path: str | None = None,
        status: str | None = None,
    ) -> list[WorktreeTask]:
        """列出任务（可按 worktree / status 过滤）"""
        tasks = list(self._tasks.values())
        if worktree_path:
            normalized = self._normalize_path(worktree_path)
            tasks = [
                t for t in tasks
                if self._normalize_path(t.worktree_path) == normalized
            ]
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    # ── Sandbox 关联 ────────────────────────────────────

    def get_worktree_sandbox_config(self, worktree_path: str) -> dict[str, Any]:
        """为 worktree 生成 Sandbox 配置，实现路径隔离"""
        return {
            "type": "local",
            "workspace_dir": worktree_path,
            "allowed_paths": [worktree_path],
            "denied_paths": [
                os.path.join(worktree_path, ".git"),
            ],
        }

    # ── 统计 ────────────────────────────────────────────

    async def stats(self) -> dict[str, Any]:
        """获取 worktree 统计信息"""
        worktrees = await self.list_worktrees()
        active = sum(1 for wt in worktrees if wt.status == WorktreeStatus.ACTIVE)
        locked = sum(1 for wt in worktrees if wt.status == WorktreeStatus.LOCKED)
        detached = sum(1 for wt in worktrees if wt.status == WorktreeStatus.DETACHED)

        return {
            "total": len(worktrees),
            "active": active,
            "locked": locked,
            "detached": detached,
            "max_active": self.config.max_active_worktrees,
            "tasks": {
                "total": len(self._tasks),
                "running": sum(1 for t in self._tasks.values() if t.status == "running"),
                "completed": sum(1 for t in self._tasks.values() if t.status == "completed"),
                "failed": sum(1 for t in self._tasks.values() if t.status == "failed"),
            },
            "worktrees": [wt.to_dict() for wt in worktrees],
        }


# ══════════════════════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════════════════════

_worktree_manager: WorktreeManager | None = None


def get_worktree_manager() -> WorktreeManager:
    """获取全局 WorktreeManager 单例"""
    global _worktree_manager
    if _worktree_manager is None:
        _worktree_manager = WorktreeManager()
    return _worktree_manager


def init_worktree_manager(config: WorktreeConfig | None = None) -> WorktreeManager:
    """初始化全局 WorktreeManager"""
    global _worktree_manager
    _worktree_manager = WorktreeManager(config)
    return _worktree_manager
