"""
数据导出器 — 全量数据导出为 ZIP

借鉴 AstrBot AstrBotExporter:
- 数据库无关的 JSON 格式
- 版本化 manifest + SHA256 校验
- 知识库 (KB 元数据 + FAISS 索引)
- 配置文件 / 插件 / 技能
- 进度回调
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Callable, Optional

from app.core.backup.constants import (
    BACKUP_MANIFEST_VERSION,
    get_backup_directories,
    KB_METADATA_MODELS,
    _lazy_load_models,
)

logger = logging.getLogger("app.core.backup.exporter")

ProgressCallback = Callable[[str, float, str], None]  # (stage, progress_pct, detail)


class DataExporter:
    """全量数据导出器"""

    def __init__(
        self,
        kb_manager=None,  # Optional KnowledgeBaseManagerV2
        config_dir: str = "",
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self._kb_manager = kb_manager
        self._config_dir = config_dir
        self._progress = progress_callback
        _lazy_load_models()

    async def export_all(self, output_path: str) -> str:
        """
        导出全部数据到 ZIP 文件

        Returns:
            输出文件路径
        """
        self._report("init", 0, "Starting export...")
        manifest = {
            "version": BACKUP_MANIFEST_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tables": {},
            "checksums": {},
            "statistics": {},
        }

        tmp_dir = tempfile.mkdtemp(prefix="export_")
        db_dir = os.path.join(tmp_dir, "databases")
        os.makedirs(db_dir, exist_ok=True)

        try:
            # ── 1. 导出知识库元数据 ──
            await self._export_kb_metadata(db_dir, manifest)

            # ── 2. 导出知识库索引 ──
            await self._export_kb_indices(db_dir, manifest)

            # ── 3. 导出配置文件 ──
            self._export_configs(tmp_dir, manifest)

            # ── 4. 导出目录 ──
            self._export_directories(tmp_dir, manifest)

            # ── 5. 写入 manifest ──
            manifest_path = os.path.join(tmp_dir, "manifest.json")
            self._report("manifest", 95, "Writing manifest...")
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2, default=str)

            # ── 6. 打包 ZIP ──
            self._report("zip", 98, "Creating ZIP archive...")
            self._create_zip(tmp_dir, output_path)

            self._report("done", 100, f"Export complete: {output_path}")
            logger.info("Export completed: %s (%d tables)", output_path, len(manifest["tables"]))

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        return output_path

    # ── KB 元数据导出 ───────────────────────────

    async def _export_kb_metadata(self, db_dir: str, manifest: dict) -> None:
        """导出知识库元数据表"""
        self._report("kb_metadata", 10, "Exporting KB metadata...")

        for table_name, model_cls in KB_METADATA_MODELS.items():
            if model_cls is None:
                continue
            try:
                from app.core.rag.kb_store import get_kb_store
                store = get_kb_store()

                records = []
                async with store.get_db() as db:
                    from sqlmodel import select
                    result = await db.exec(
                        select(model_cls).limit(100_000)  # 导出安全上限 10 万条
                    )
                    rows = result.all()
                    for row in rows:
                        records.append(self._model_to_dict(row))

                file_path = os.path.join(db_dir, f"kb_{table_name}.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(records, f, ensure_ascii=False, indent=2, default=str)

                checksum = self._file_sha256(file_path)
                manifest["tables"][f"kb_{table_name}"] = {"count": len(records)}
                manifest["checksums"][f"kb_{table_name}"] = checksum

                logger.debug("Exported %s: %d records", table_name, len(records))
            except Exception as e:
                logger.warning("Failed to export %s: %s", table_name, e)

    async def _export_kb_indices(self, db_dir: str, manifest: dict) -> None:
        """导出知识库向量索引"""
        self._report("kb_indices", 20, "Exporting KB indices...")
        if not self._kb_manager:
            return

        for inst in self._kb_manager._instances.values():
            kb_dir = os.path.join(db_dir, f"kb_{inst.model.kb_id}")
            os.makedirs(kb_dir, exist_ok=True)

            # 导出向量存储
            if inst.storage:
                try:
                    inst.storage.save(os.path.join(kb_dir, "index"))
                    manifest["tables"][f"kb_index_{inst.model.kb_id}"] = {
                        "name": inst.model.kb_name,
                        "chunks": inst.storage.count(),
                    }
                except Exception as e:
                    logger.warning("Failed to export KB index %s: %s", inst.name, e)

            # 导出媒体文件
            media_dir = os.path.join(self._kb_manager._config.kb_dir, inst.model.kb_id, "media")
            if os.path.isdir(media_dir):
                dest = os.path.join(kb_dir, "media")
                shutil.copytree(media_dir, dest, dirs_exist_ok=True)
                media_count = len(os.listdir(dest)) if os.path.isdir(dest) else 0
                manifest["tables"][f"kb_media_{inst.model.kb_id}"] = {"count": media_count}

    # ── 配置文件导出 ───────────────────────────

    def _export_configs(self, tmp_dir: str, manifest: dict) -> None:
        self._report("configs", 50, "Exporting config files...")
        config_dest = os.path.join(tmp_dir, "config")
        os.makedirs(config_dest, exist_ok=True)

        if self._config_dir and os.path.isdir(self._config_dir):
            for fname in os.listdir(self._config_dir):
                if fname.endswith((".json", ".yaml", ".yml", ".toml", ".env.example")):
                    src = os.path.join(self._config_dir, fname)
                    if os.path.isfile(src):
                        shutil.copy2(src, os.path.join(config_dest, fname))

        manifest["tables"]["configs"] = {
            "count": len(os.listdir(config_dest)) if os.path.isdir(config_dest) else 0,
        }

    def _export_directories(self, tmp_dir: str, manifest: dict) -> None:
        self._report("directories", 70, "Exporting directories...")
        for dir_name in get_backup_directories():
            src = os.path.join(os.getcwd(), dir_name)
            if os.path.isdir(src):
                dest = os.path.join(tmp_dir, dir_name)
                try:
                    shutil.copytree(
                        src, dest, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "node_modules"),
                    )
                    manifest["tables"][f"dir_{dir_name}"] = {
                        "files": sum(1 for _ in self._walk_files(dest)),
                    }
                except Exception as e:
                    logger.warning("Failed to export dir %s: %s", dir_name, e)

    # ── 工具方法 ────────────────────────────

    @staticmethod
    def _create_zip(src_dir: str, output_path: str) -> None:
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(src_dir):
                for f in files:
                    abs_path = os.path.join(root, f)
                    arcname = os.path.relpath(abs_path, src_dir)
                    zf.write(abs_path, arcname)

    @staticmethod
    def _model_to_dict(obj) -> dict:
        """SQLModel 实例 → 字典"""
        data = {}
        for col in obj.__table__.columns:
            val = getattr(obj, col.name, None)
            if isinstance(val, datetime):
                val = val.isoformat()
            data[col.name] = val
        return data

    @staticmethod
    def _file_sha256(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

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
