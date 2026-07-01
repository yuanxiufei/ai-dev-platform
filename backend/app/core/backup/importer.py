"""
数据导入器 — 从 ZIP 备份恢复数据

借鉴 AstrBot AstrBotImporter:
- main_version 兼容性检查
- 安全路径验证 (防止路径穿越)
- 清空后导入
- 逐表恢复 + 错误收集
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.core.backup.constants import (
    BACKUP_MANIFEST_VERSION,
    get_backup_directories,
    KB_METADATA_MODELS,
    _lazy_load_models,
)

logger = logging.getLogger("app.core.backup.importer")

ProgressCallback = Callable[[str, float, str], None]


@dataclass
class ImportResult:
    """导入结果"""
    success: bool = True
    imported_tables: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class DataImporter:
    """全量数据导入器"""

    def __init__(
        self,
        kb_manager=None,
        config_dir: str = "",
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self._kb_manager = kb_manager
        self._config_dir = config_dir
        self._progress = progress_callback
        _lazy_load_models()

    async def import_all(self, zip_path: str) -> ImportResult:
        """从 ZIP 备份恢复全部数据"""
        result = ImportResult()
        tmp_dir = tempfile.mkdtemp(prefix="import_")

        try:
            # 解压 — ZIP Slip 防护
            self._report("extract", 0, "Extracting backup...")
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    member_path = os.path.realpath(os.path.join(tmp_dir, member.filename))
                    if os.path.commonpath([member_path, os.path.realpath(tmp_dir)]) != os.path.realpath(tmp_dir):
                        raise ValueError(f"ZIP path traversal detected: {member.filename}")
                zf.extractall(tmp_dir)

            # 1. 验证 manifest
            manifest = await self._validate_manifest(tmp_dir, result)
            if not manifest:
                result.success = False
                result.errors.append("Invalid or missing manifest")
                return result

            # 2. 导入 KB 元数据
            await self._import_kb_metadata(tmp_dir, result)

            # 3. 导入 KB 索引
            await self._import_kb_indices(tmp_dir, result)

            # 4. 导入配置
            self._import_configs(tmp_dir, result)

            # 5. 导入目录
            self._import_directories(tmp_dir, result)

            self._report("done", 100, "Import complete")
            logger.info(
                "Import finished: %d tables, %d warnings, %d errors",
                len(result.imported_tables), len(result.warnings), len(result.errors),
            )

        except Exception as e:
            result.success = False
            result.errors.append(str(e))
            logger.exception("Import failed")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return result

    # ── Manifest 验证 ──────────────────────────

    async def _validate_manifest(self, tmp_dir: str, result: ImportResult) -> Optional[dict]:
        manifest_path = os.path.join(tmp_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            result.errors.append("manifest.json not found in backup")
            return None

        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)

        # 版本兼容性检查
        backup_ver = manifest.get("version", "0.0")
        if not self._version_compatible(backup_ver):
            msg = f"Backup version {backup_ver} is not compatible with current {BACKUP_MANIFEST_VERSION}"
            result.warnings.append(msg)
            logger.warning(msg)

        logger.info("Manifest: version=%s, exported=%s, tables=%d",
                     backup_ver, manifest.get("exported_at", "N/A"),
                     len(manifest.get("tables", {})))

        return manifest

    @staticmethod
    def _version_compatible(backup_ver: str) -> bool:
        """检查版本兼容：主版本必须匹配"""
        try:
            cur_major = BACKUP_MANIFEST_VERSION.split(".")[0]
            bak_major = backup_ver.split(".")[0]
            return cur_major == bak_major
        except (IndexError, ValueError):
            return False

    # ── KB 元数据导入 ─────────────────────────

    async def _import_kb_metadata(self, tmp_dir: str, result: ImportResult) -> None:
        self._report("kb_metadata", 10, "Importing KB metadata...")
        db_dir = os.path.join(tmp_dir, "databases")
        if not os.path.isdir(db_dir):
            return

        for table_name, model_cls in KB_METADATA_MODELS.items():
            if model_cls is None:
                continue
            file_path = os.path.join(db_dir, f"kb_{table_name}.json")
            if not os.path.isfile(file_path):
                continue

            try:
                with open(file_path, encoding="utf-8") as f:
                    records = json.load(f)

                from app.core.rag.kb_store import get_kb_store
                store = get_kb_store()
                count = 0
                async with store.get_db() as db:
                    for record in records:
                        # 移除 id 让数据库自增
                        record.pop("id", None)
                        obj = model_cls(**record)
                        db.add(obj)
                        count += 1
                    await db.commit()

                result.imported_tables[table_name] = count
                logger.debug("Imported %s: %d records", table_name, count)
            except Exception as e:
                msg = f"Failed to import {table_name}: {e}"
                result.errors.append(msg)
                logger.error(msg)

    async def _import_kb_indices(self, tmp_dir: str, result: ImportResult) -> None:
        self._report("kb_indices", 30, "Importing KB indices...")
        db_dir = os.path.join(tmp_dir, "databases")
        if not os.path.isdir(db_dir) or not self._kb_manager:
            return

        for entry in os.listdir(db_dir):
            if not entry.startswith("kb_") or entry.startswith("kb_knowledge_bases") or \
               entry.startswith("kb_kb_documents") or entry.startswith("kb_kb_media"):
                continue

            kb_dir = os.path.join(db_dir, entry)
            if not os.path.isdir(kb_dir):
                continue

            kb_id = entry[3:]  # remove "kb_" prefix

            try:
                # 恢复向量索引
                index_dir = os.path.join(kb_dir, "index")
                if os.path.isdir(index_dir):
                    inst = self._kb_manager.get(kb_id)
                    if inst and inst.storage:
                        inst.storage.load(index_dir)

                # 恢复媒体文件
                media_dir = os.path.join(kb_dir, "media")
                if os.path.isdir(media_dir):
                    dest = os.path.join(
                        self._kb_manager._config.kb_dir, kb_id, "media",
                    )
                    os.makedirs(dest, exist_ok=True)
                    for f in os.listdir(media_dir):
                        shutil.copy2(
                            os.path.join(media_dir, f),
                            os.path.join(dest, f),
                        )

                result.imported_tables[f"kb_index_{kb_id}"] = 1
            except Exception as e:
                msg = f"Failed to import KB index {kb_id}: {e}"
                result.errors.append(msg)
                logger.error(msg)

    # ── 配置导入 ──────────────────────────────

    def _import_configs(self, tmp_dir: str, result: ImportResult) -> None:
        self._report("configs", 60, "Importing configs...")
        config_dir = os.path.join(tmp_dir, "config")
        if not os.path.isdir(config_dir) or not self._config_dir:
            return

        # 先备份现有配置
        backup_configs = tempfile.mkdtemp(prefix="config_backup_")
        if os.path.isdir(self._config_dir):
            try:
                for f in os.listdir(self._config_dir):
                    src = os.path.join(self._config_dir, f)
                    if os.path.isfile(src):
                        shutil.copy2(src, os.path.join(backup_configs, f))
            except Exception:
                pass

        count = 0
        for f in os.listdir(config_dir):
            src = os.path.join(config_dir, f)
            if os.path.isfile(src):
                dest = os.path.join(self._config_dir, f)
                self._validate_path_within(dest, self._config_dir)
                shutil.copy2(src, dest)
                count += 1

        result.imported_tables["configs"] = count

    # ── 目录导入 ──────────────────────────────

    def _import_directories(self, tmp_dir: str, result: ImportResult) -> None:
        self._report("directories", 80, "Importing directories...")
        for dir_name in get_backup_directories():
            src = os.path.join(tmp_dir, dir_name)
            if not os.path.isdir(src):
                continue
            dest = os.path.join(os.getcwd(), dir_name)
            self._validate_path_within(dest, os.getcwd())

            # 备份现有目录
            if os.path.isdir(dest):
                backup = dest + ".backup"
                if os.path.exists(backup):
                    shutil.rmtree(backup, ignore_errors=True)
                shutil.move(dest, backup)

            try:
                shutil.copytree(src, dest)
                count = sum(1 for _ in self._walk_files(dest))
                result.imported_tables[f"dir_{dir_name}"] = count
            except Exception as e:
                result.errors.append(f"Failed to import dir {dir_name}: {e}")

    # ── 工具方法 ────────────────────────────

    @staticmethod
    def _validate_path_within(path: str, allowed_base: str) -> None:
        """安全验证：确保路径不穿越边界 (CWE-22防护)"""
        real_path = os.path.realpath(path)
        real_base = os.path.realpath(allowed_base)
        if not real_path.startswith(real_base + os.sep) and real_path != real_base:
            raise ValueError(f"Path traversal detected: {path}")

    @staticmethod
    def _walk_files(root: str):
        for dirpath, _, filenames in os.walk(root):
            for f in filenames:
                yield os.path.join(dirpath, f)

    def _report(self, stage: str, pct: float, detail: str) -> None:
        if self._progress:
            try:
                self._progress(stage, pct, detail)
            except Exception:
                pass
