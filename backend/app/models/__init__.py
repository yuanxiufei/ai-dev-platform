"""
数据模型包 —— 按域拆分：studio_models / video_models / system_models / agent_models
所有模型启动时由 db.py 通过 SQLModel.metadata 自动创建表
"""
from app.models.studio_models import (
    StudioProject,
    StudioTemplate,
    ChatSession,
    ChatMessage,
)
from app.models.video_models import (
    VideoTask,
    VideoAsset,
)
from app.models.system_models import (
    ModelDownload,
    ModelUsageStat,
    ApiCredential,
)
from app.models.agent_models import (
    AgentTrace,
    AgentToolCall,
    AgentFileChange,
    AgentExecLog,
)

__all__ = [
    "StudioProject",
    "StudioTemplate",
    "ChatSession",
    "ChatMessage",
    "VideoTask",
    "VideoAsset",
    "ModelDownload",
    "ModelUsageStat",
    "ApiCredential",
    "AgentTrace",
    "AgentToolCall",
    "AgentFileChange",
    "AgentExecLog",
]
