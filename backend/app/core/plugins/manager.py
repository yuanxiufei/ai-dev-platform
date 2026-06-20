"""
插件管理器 — 插件的加载、初始化、终止、重载等完整生命周期管理

借鉴 AstrBot PluginManager / star_manager.py 设计：
- 扫描 plugins/ 和 builtin_plugins/ 目录
- 读取 metadata.yaml / plugin.json 配置文件
- 实例化插件类、调用 initialize()
- 支持热重载（watchfiles 文件变更检测）
- 启停控制（turn_on / turn_off）
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import os
import sys
import traceback
from pathlib import Path
from typing import Any

from .base import Plugin
from .handler import handler_registry
from .metadata import PluginMetadata, plugin_map, plugin_registry

logger = logging.getLogger("platform.plugins.manager")

# 标记插件源码可能的根目录标签
_PLUGIN_SOURCE_FLAGS = {"plugins", "builtin_plugins", "builtin_stars"}

# ── 插件依赖恢复模式 ──
# 导入失败时尝试通过 pip 自动安装缺失的依赖


class ImportRecoveryMode:
    """插件导入失败的恢复策略"""

    SKIP = "skip"          # 跳过该插件
    RETRY_INSTALL = "retry_install"  # 尝试自动安装依赖
    RAISE = "raise"        # 直接抛出异常


class PluginManager:
    """插件生命周期管理器。

    负责：
    1. 扫描插件目录发现插件
    2. 加载插件模块并实例化
    3. 管理插件的启停和重载
    """

    def __init__(
        self,
        plugin_dirs: list[str] | None = None,
        auto_discover: bool = True,
    ) -> None:
        self._plugin_dirs: list[str] = plugin_dirs or self._default_plugin_dirs()
        self._auto_discover = auto_discover
        self._load_errors: dict[str, str] = {}
        """模块路径 → 错误信息"""

    # ── 默认插件目录 ────────────────────────────────

    @staticmethod
    def _default_plugin_dirs() -> list[str]:
        """返回默认的插件搜索目录"""
        base = Path(os.getcwd())
        dirs = []
        candidate_paths = [
            base / "plugins",
            base / "backend" / "plugins",
            base / "backend" / "app" / "plugins",
        ]
        for p in candidate_paths:
            if p.is_dir():
                dirs.append(str(p))
        return dirs or [str(base / "plugins")]

    # ── 插件发现 ─────────────────────────────────────

    def _discover_plugin_modules(self) -> list[tuple[str, Path, Path]]:
        """扫描所有插件目录，返回 (module_name, root_dir, entry_file) 列表"""
        results: list[tuple[str, Path, Path]] = []

        for dir_path_str in self._plugin_dirs:
            dir_path = Path(dir_path_str)
            if not dir_path.is_dir():
                continue

            for entry in dir_path.iterdir():
                if entry.name.startswith(".") or entry.name.startswith("_"):
                    continue

                if entry.is_dir():
                    main_file = entry / "main.py"
                    if main_file.is_file():
                        module_name = f"plugins.{entry.name}.main"
                        results.append((module_name, entry, main_file))
                    elif (entry / f"{entry.name}.py").is_file():
                        module_name = f"plugins.{entry.name}.{entry.name}"
                        results.append((module_name, entry, entry / f"{entry.name}.py"))
                elif entry.suffix == ".py" and entry.stem != "__init__":
                    module_name = f"plugins.{entry.stem}"
                    results.append((module_name, entry.parent, entry))

        return results

    def _read_plugin_metadata(self, root_dir: Path) -> dict[str, Any]:
        """读取插件元数据文件 (metadata.yaml / plugin.json)"""
        for name in ("metadata.yaml", "metadata.yml", "plugin.json"):
            path = root_dir / name
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8")
                    if name.endswith((".yaml", ".yml")):
                        import yaml
                        return yaml.safe_load(content) or {}
                    return json.loads(content)
                except Exception:
                    logger.warning(
                        "Failed to parse plugin metadata: %s", path
                    )
        return {}

    # ── 插件加载 ─────────────────────────────────────

    async def load_all(self) -> None:
        """发现并加载所有插件"""
        modules = self._discover_plugin_modules()
        logger.info(
            "PluginManager: discovered %d plugin(s) in %s",
            len(modules),
            self._plugin_dirs,
        )

        for module_name, root_dir, entry_file in modules:
            await self._load_one(module_name, root_dir, entry_file)

    async def _load_one(
        self,
        module_name: str,
        root_dir: Path,
        entry_file: Path,
    ) -> PluginMetadata | None:
        """加载单个插件"""
        # 读取元数据
        raw_meta = self._read_plugin_metadata(root_dir)

        # 导入模块
        try:
            spec = importlib.util.spec_from_file_location(
                module_name, str(entry_file)
            )
            if not spec or not spec.loader:
                raise ImportError(f"Cannot load spec for {module_name}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except ImportError as e:
            logger.error("Plugin '%s' import failed: %s", module_name, e)
            self._load_errors[module_name] = str(e)
            return None
        except Exception as e:
            logger.error(
                "Plugin '%s' load error: %s\n%s",
                module_name, e, traceback.format_exc(),
            )
            self._load_errors[module_name] = str(e)
            return None

        # 查找 Plugin 子类并实例化
        metadata = plugin_map.get(module_name)
        if metadata is None:
            logger.warning(
                "Plugin '%s' loaded but no Plugin subclass found", module_name
            )
            return None

        # 填充元数据
        metadata.root_dir_name = root_dir.name
        metadata.module = module
        metadata.name = metadata.name or raw_meta.get("name") or root_dir.name
        metadata.author = metadata.author or raw_meta.get("author", "unknown")
        metadata.version = metadata.version or raw_meta.get("version", "0.1.0")
        metadata.desc = metadata.desc or raw_meta.get("desc", "")
        metadata.display_name = metadata.display_name or raw_meta.get(
            "display_name", metadata.name
        )
        metadata.config = metadata.config or raw_meta.get("config", {})

        # 实例化
        try:
            if metadata.plugin_cls_type is None:
                logger.error("Plugin '%s' has no cls_type", module_name)
                return None
            instance = metadata.plugin_cls_type(config=metadata.config)
            metadata.plugin_cls = instance
        except Exception as e:
            logger.error(
                "Plugin '%s' instantiation failed: %s", module_name, e
            )
            self._load_errors[module_name] = f"Instantiation: {e}"
            return None

        # 初始化
        try:
            await instance.initialize()
            logger.info(
                "Plugin loaded: %s v%s by %s",
                metadata.name, metadata.version, metadata.author,
            )
        except Exception as e:
            logger.error(
                "Plugin '%s' initialize() failed: %s", metadata.name, e
            )
            # 初始化失败也保留插件，只记录错误

        return metadata

    # ── 插件重载 ─────────────────────────────────────

    async def reload_all(self) -> None:
        """重新加载所有插件：先终止所有，清空注册表，再重新发现加载"""
        # 终止所有已激活插件
        for md in list(plugin_registry):
            await self._terminate_plugin(md)

        # 清空注册表
        plugin_registry.clear()
        plugin_map.clear()
        handler_registry.clear()
        self._load_errors.clear()

        # 重新加载
        await self.load_all()

    async def reload_plugin(self, module_path: str) -> PluginMetadata | None:
        """重载单个插件"""
        md = plugin_map.get(module_path)
        if md is None:
            raise ValueError(f"Plugin not found: {module_path}")

        # 终止旧实例
        await self._terminate_plugin(md)

        # 重新加载
        return await self._load_one(
            module_path,
            md.root_dir_name and Path(md.root_dir_name) or Path("."),
            Path("."),
        )

    # ── 插件启停 ─────────────────────────────────────

    async def turn_on_plugin(self, module_path: str) -> None:
        """启用插件"""
        md = plugin_map.get(module_path)
        if md is None:
            raise ValueError(f"Plugin not found: {module_path}")
        if md.activated:
            return
        md.activated = True
        if md.plugin_cls:
            await md.plugin_cls.initialize()
        logger.info("Plugin enabled: %s", md.name)

    async def turn_off_plugin(self, module_path: str) -> None:
        """停用插件"""
        md = plugin_map.get(module_path)
        if md is None:
            raise ValueError(f"Plugin not found: {module_path}")
        if not md.activated:
            return
        await self._terminate_plugin(md)
        md.activated = False
        logger.info("Plugin disabled: %s", md.name)

    # ── 内部辅助 ─────────────────────────────────────

    async def _terminate_plugin(self, md: PluginMetadata) -> None:
        """安全终止一个插件"""
        try:
            if md.plugin_cls:
                await md.plugin_cls.terminate()
        except Exception as e:
            logger.warning(
                "Plugin '%s' terminate() failed: %s", md.name, e
            )
        # 移除该插件的 handlers
        handler_registry.unregister_by_module(md.module_path or "")

    # ── 查询接口 ─────────────────────────────────────

    def get_plugin(self, plugin_name: str) -> PluginMetadata | None:
        """按名称查找插件"""
        for md in plugin_registry:
            if md.name == plugin_name:
                return md
        return None

    def get_all_plugins(self) -> list[PluginMetadata]:
        """返回所有已注册插件"""
        return list(plugin_registry)

    def get_load_errors(self) -> dict[str, str]:
        """返回所有加载错误"""
        return dict(self._load_errors)

    def get_activated_plugins(self) -> list[PluginMetadata]:
        """返回已激活的插件"""
        return [md for md in plugin_registry if md.activated]
