"""
配置热加载 — 借鉴 GPUStack cmd/reload_config.py

支持运行时热加载 .env 文件和环境变量，重新初始化 Settings 对象。
通过 API 端点触发或文件监听自动触发。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ConfigReloader:
    """配置热加载管理器

    监视 .env 文件变更，支持手动/自动触发配置重新加载。
    通过回调机制通知各组件配置变更。
    """

    env_file: str = ".env"
    watch_interval: float = 5.0
    _last_mtime: float = 0.0
    _watcher_thread: threading.Thread | None = None
    _running: bool = False
    _callbacks: list[Callable[[], None]] = field(default_factory=list)
    _reload_count: int = 0

    def on_reload(self, callback: Callable[[], None]) -> None:
        """注册配置重载回调"""
        self._callbacks.append(callback)

    def reload_now(self) -> dict[str, Any]:
        """立即重新加载配置

        Returns:
            变更摘要，包含 reload_count 和重载的时间戳
        """
        # 重新读取 .env 文件
        if os.path.exists(self.env_file):
            self._load_env_file(self.env_file)

        # 更新 Settings 对象
        try:
            from app.core.config import settings

            # pydantic-settings 支持运行时刷新
            if hasattr(settings, "__init__"):
                # 重新初始化 Settings（读取新的环境变量）
                for field_name in settings.model_fields:
                    env_val = os.getenv(field_name)
                    if env_val is not None:
                        try:
                            setattr(settings, field_name, env_val)
                        except Exception:
                            pass
        except Exception as e:
            logger.warning("Settings refresh failed: %s", e)

        self._reload_count += 1
        timestamp = time.time()

        # 通知所有回调
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.warning("Config reload callback failed: %s", e)

        logger.info("Config reloaded (#%d) at %.2f", self._reload_count, timestamp)

        return {
            "reload_count": self._reload_count,
            "timestamp": timestamp,
            "env_file": self.env_file,
            "env_file_mtime": self._last_mtime,
        }

    def start_watching(self) -> None:
        """启动文件监听（后台线程）"""
        if self._running:
            return
        self._running = True
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            daemon=True,
            name="config-watcher",
        )
        self._watcher_thread.start()
        logger.info("Config watcher started (interval=%ss)", self.watch_interval)

    def stop_watching(self) -> None:
        """停止文件监听"""
        self._running = False
        if self._watcher_thread:
            self._watcher_thread.join(timeout=2.0)
            self._watcher_thread = None
        logger.info("Config watcher stopped")

    def _watch_loop(self) -> None:
        """后台监听循环"""
        while self._running:
            try:
                if self._file_changed():
                    logger.info("Config file changed, auto-reloading...")
                    self.reload_now()
            except Exception as e:
                logger.warning("Config watcher error: %s", e)
            time.sleep(self.watch_interval)

    def _file_changed(self) -> bool:
        """检查 .env 文件是否变更"""
        if not os.path.exists(self.env_file):
            return False
        current_mtime = os.path.getmtime(self.env_file)
        if current_mtime > self._last_mtime:
            self._last_mtime = current_mtime
            return True
        return False

    @staticmethod
    def _load_env_file(filepath: str) -> None:
        """加载 .env 文件到 os.environ"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip("\"'")
                        if key and not os.getenv(key):  # 环境变量优先
                            os.environ[key] = val
        except FileNotFoundError:
            pass


# ══════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════

_reloader: ConfigReloader | None = None


def init_config_reloader(
    env_file: str = ".env",
    watch_interval: float = 5.0,
    auto_watch: bool = True,
) -> ConfigReloader:
    """初始化配置热加载管理器"""
    global _reloader
    _reloader = ConfigReloader(
        env_file=env_file,
        watch_interval=watch_interval,
    )
    if auto_watch:
        _reloader.start_watching()
    return _reloader


def get_config_reloader() -> ConfigReloader | None:
    """获取配置热加载管理器（全局单例）"""
    return _reloader
