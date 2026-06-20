"""
备份/恢复系统 — 全量数据导出导入

借鉴 AstrBot backup 系统:
- DataExporter: ZIP 导出 (KB 元数据 + 索引 + 配置 + 目录)
- DataImporter: ZIP 导入 (版本检查 + 安全验证 + 逐个表恢复)
"""

from app.core.backup.exporter import DataExporter  # noqa: F401
from app.core.backup.importer import DataImporter, ImportResult  # noqa: F401
from app.core.backup.constants import BACKUP_MANIFEST_VERSION, get_backup_directories  # noqa: F401
