"""
统一存储管理 — 用户可自定义的存储路径与空间分配

借鉴 GPUStack 多租户存储架构，提供：
  1. 全局存储根目录配置（STORAGE_ROOT）
  2. 子目录分类管理（models/knowledge_bases/workspace/trajectories/backups/plugins/data）
  3. 磁盘配额检查（per-user 可选）
  4. 单例模式 init_storage_manager / get_storage_manager
  5. 存储统计 API（已用空间、剩余空间、文件数）
"""

import os
import shutil
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("app.core.storage")


# ──────────────────────── 数据结构 ────────────────────────

@dataclass
class StorageStats:
    """存储统计"""
    path: str
    total_bytes: int = 0
    used_bytes: int = 0
    free_bytes: int = 0
    file_count: int = 0
    is_readable: bool = True


@dataclass
class StorageConfig:
    """存储配置"""
    storage_root: str = "storage"            # 存储根目录
    models_dir: str = "models"              # 模型文件
    kb_dir: str = "storage/knowledge_bases" # 知识库
    workspace_dir: str = "workspace"        # 工作区/沙箱
    trajectories_dir: str = "trajectories"  # 轨迹记录
    backups_dir: str = "storage/backups"    # 备份
    plugins_dir: str = "storage/plugins"    # 插件数据
    data_dir: str = "data"                  # 通用数据（SQLite/CKG）
    skills_dir: str = "skills"              # 技能文件

    max_storage_gb: int = 100               # 全局最大存储（GB），0=不限
    max_workspace_gb: int = 10              # 单工作区最大（GB），0=不限

    auto_create_dirs: bool = True           # 启动时自动创建目录


# ──────────────────────── 存储管理器 ────────────────────────

class StorageManager:
    """统一存储管理器"""

    def __init__(self, config: StorageConfig | None = None) -> None:
        self._config = config or StorageConfig()
        self._ensure_directories()

    # ── 属性 ────────────────────────────────────────
    @property
    def config(self) -> StorageConfig:
        return self._config

    @property
    def storage_root(self) -> str:
        return self._config.storage_root

    # ── 目录操作 ─────────────────────────────────────
    def _ensure_directories(self) -> None:
        """创建所有必要的存储目录"""
        dirs = [
            self._config.storage_root,
            self._config.models_dir,
            self._config.kb_dir,
            self._config.workspace_dir,
            self._config.trajectories_dir,
            self._config.backups_dir,
            self._config.plugins_dir,
            self._config.data_dir,
            self._config.skills_dir,
        ]
        if self._config.auto_create_dirs:
            for d in dirs:
                Path(d).mkdir(parents=True, exist_ok=True)
                logger.debug("Storage directory ensured: %s", d)

    async def ensure_directories(self) -> None:
        """异步创建所有目录"""
        self._ensure_directories()

    def get_path(self, category: str, subpath: str = "") -> str:
        """根据类别获取完整路径"""
        category_map: dict[str, str] = {
            "models":      self._config.models_dir,
            "kb":          self._config.kb_dir,
            "workspace":   self._config.workspace_dir,
            "trajectories": self._config.trajectories_dir,
            "backups":     self._config.backups_dir,
            "plugins":     self._config.plugins_dir,
            "data":        self._config.data_dir,
            "skills":      self._config.skills_dir,
            "root":        self._config.storage_root,
        }
        base = category_map.get(category, str(Path(self._config.storage_root) / category))
        result = os.path.join(base, subpath) if subpath else base
        Path(result).parent.mkdir(parents=True, exist_ok=True)
        return result

    # ── 空间统计 ─────────────────────────────────────
    def get_stats(self, path: str | None = None) -> StorageStats:
        """获取目录存储统计"""
        target = path or self._config.storage_root
        stats = StorageStats(path=target)

        try:
            usage = shutil.disk_usage(target)
            stats.total_bytes = usage.total
            stats.used_bytes = usage.used
            stats.free_bytes = usage.free
        except OSError:
            stats.is_readable = False

        # 统计文件数（限制深度，防止过慢）
        try:
            file_count = 0
            for root, dirs, files in os.walk(target):
                file_count += len(files)
                # 限制遍历深度
                if root.count(os.sep) - target.count(os.sep) > 5:
                    dirs.clear()
            stats.file_count = file_count
        except OSError:
            stats.file_count = -1

        return stats

    def get_all_stats(self) -> dict[str, StorageStats]:
        """获取所有类别存储统计"""
        categories = {
            "storage_root":     self._config.storage_root,
            "models":          self._config.models_dir,
            "knowledge_bases": self._config.kb_dir,
            "workspace":       self._config.workspace_dir,
            "trajectories":    self._config.trajectories_dir,
            "backups":         self._config.backups_dir,
            "plugins":         self._config.plugins_dir,
            "data":            self._config.data_dir,
            "skills":          self._config.skills_dir,
        }
        return {k: self.get_stats(v) for k, v in categories.items()}

    def check_quota(self, path: str, additional_bytes: int = 0) -> tuple[bool, str]:
        """检查是否有足够空间（返回 是否通过, 原因）"""
        if self._config.max_storage_gb == 0 and self._config.max_workspace_gb == 0:
            return True, ""

        try:
            usage = shutil.disk_usage(path)
            used_gb = usage.used / (1024**3)

            if self._config.max_storage_gb > 0:
                max_bytes = self._config.max_storage_gb * (1024**3)
                if used_gb + additional_bytes / (1024**3) > self._config.max_storage_gb:
                    return False, (
                        f"Storage limit exceeded: {used_gb:.1f}GB used "
                        f"of {self._config.max_storage_gb}GB max"
                    )
        except OSError:
            return True, ""  # 无法检查时不阻止

        return True, ""

    # ── 清理 ─────────────────────────────────────────
    def cleanup_old_files(self, path: str, max_age_hours: int = 24) -> int:
        """清理超过指定时间的临时文件，返回删除数量"""
        import time
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        deleted = 0

        try:
            for root, dirs, files in os.walk(path):
                for f in files:
                    fp = os.path.join(root, f)
                    try:
                        if now - os.path.getmtime(fp) > max_age_seconds:
                            os.remove(fp)
                            deleted += 1
                    except OSError:
                        pass
                # 也清理空目录
                for d in list(dirs):
                    dp = os.path.join(root, d)
                    try:
                        os.rmdir(dp)
                        dirs.remove(d)
                    except OSError:
                        pass
        except OSError:
            pass

        logger.info("Cleaned %d old files from %s (max_age=%dh)", deleted, path, max_age_hours)
        return deleted

    # ── 批量迁移 ─────────────────────────────────────
    async def migrate_storage_root(self, new_root: str) -> bool:
        """迁移存储根目录到新位置"""
        old = Path(self._config.storage_root)
        new = Path(new_root)

        if old == new:
            return True
        if new.exists() and any(new.iterdir()):
            logger.warning("Target storage root not empty: %s", new_root)
            return False

        new.mkdir(parents=True, exist_ok=True)

        # 移动所有子目录内容
        for item in old.iterdir():
            target = new / item.name
            if item.is_dir():
                shutil.copytree(str(item), str(target))
            else:
                shutil.copy2(str(item), str(target))

        self._config.storage_root = new_root
        self._config.models_dir = self._resolve_path(self._config.models_dir, str(old), str(new))
        self._config.kb_dir = self._resolve_path(self._config.kb_dir, str(old), str(new))
        self._config.workspace_dir = self._resolve_path(self._config.workspace_dir, str(old), str(new))
        self._config.trajectories_dir = self._resolve_path(self._config.trajectories_dir, str(old), str(new))
        self._config.backups_dir = self._resolve_path(self._config.backups_dir, str(old), str(new))
        self._config.plugins_dir = self._resolve_path(self._config.plugins_dir, str(old), str(new))
        self._config.data_dir = self._resolve_path(self._config.data_dir, str(old), str(new))
        self._config.skills_dir = self._resolve_path(self._config.skills_dir, str(old), str(new))

        logger.info("Storage root migrated: %s → %s", old, new)
        return True

    @staticmethod
    def _resolve_path(path: str, old_root: str, new_root: str) -> str:
        """将旧根目录下的子路径映射到新根目录"""
        if path.startswith(old_root):
            return str(Path(new_root) / Path(path).relative_to(old_root))
        return path


# ──────────────────────── 单例 ────────────────────────

_storage_manager: StorageManager | None = None


def init_storage_manager(
    storage_root: str = "storage",
    max_storage_gb: int = 100,
    max_workspace_gb: int = 10,
    **kwargs: Any,
) -> StorageManager:
    """初始化存储管理器（启动时调用一次）"""
    global _storage_manager
    config = StorageConfig(
        storage_root=storage_root,
        max_storage_gb=max_storage_gb,
        max_workspace_gb=max_workspace_gb,
        **kwargs,
    )
    _storage_manager = StorageManager(config)
    logger.info(
        "StorageManager initialized: root=%s, max_storage=%dGB, max_workspace=%dGB",
        storage_root, max_storage_gb, max_workspace_gb,
    )
    return _storage_manager


def get_storage_manager() -> StorageManager:
    """获取存储管理器单例"""
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager()
    return _storage_manager
