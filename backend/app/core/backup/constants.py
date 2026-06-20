"""
备份/恢复常量定义

借鉴 AstrBot backup/constants.py:
- 共享的模型映射和目录列表
- 统一导出器和导入器的配置
"""

from __future__ import annotations

# 备份清单版本号
BACKUP_MANIFEST_VERSION = "1.0"

# 需要备份的模型表
MAIN_DB_MODELS: dict[str, type] = {}

# 知识库元数据模型
KB_METADATA_MODELS: dict[str, type] = {
    "knowledge_bases": None,   # app.core.rag.models.KnowledgeBase
    "kb_documents": None,      # app.core.rag.models.KBDocument
    "kb_media": None,          # app.core.rag.models.KBMedia
}


def get_backup_directories() -> list[str]:
    """需要备份的目录列表"""
    return [
        "plugins",
        "config",
        "skills",
        "data",
    ]


def _lazy_load_models() -> None:
    """延迟加载模型类"""
    if MAIN_DB_MODELS:
        return
    try:
        from app.core.rag.models import KnowledgeBase, KBDocument, KBMedia
        KB_METADATA_MODELS["knowledge_bases"] = KnowledgeBase
        KB_METADATA_MODELS["kb_documents"] = KBDocument
        KB_METADATA_MODELS["kb_media"] = KBMedia
    except ImportError:
        pass
