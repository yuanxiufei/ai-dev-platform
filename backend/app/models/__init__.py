"""
数据模型包 —— 按域拆分：core_models / studio_models / video_models / system_models / agent_models
所有模型启动时由 db.py 通过 SQLModel.metadata 自动创建表
"""
from sqlmodel import SQLModel  # noqa: F401 — 供 alembic 使用

from app.models.core_models import (
    User,
    UserCreate,
    UserRegister,
    UserUpdate,
    UserUpdateMe,
    UserPublic,
    UsersPublic,
    UpdatePassword,
    Item,
    ItemCreate,
    ItemUpdate,
    ItemPublic,
    ItemsPublic,
    Message,
    Token,
    TokenPayload,
    NewPassword,
)
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
    Rule,
    Integration,
    AgentConfig,
)
from app.models.model_presets import (
    ModelPreset,
    ArenaComparison,
    ArenaVote,
    ModelEloRanking,
    ModelUsageLog,
    MemoryEntry,
)
from app.models.agent_models import (
    AgentTrace,
    AgentToolCall,
    AgentFileChange,
    AgentExecLog,
)

__all__ = [
    "SQLModel",
    "User",
    "UserCreate",
    "UserRegister",
    "UserUpdate",
    "UserUpdateMe",
    "UserPublic",
    "UsersPublic",
    "UpdatePassword",
    "Item",
    "ItemCreate",
    "ItemUpdate",
    "ItemPublic",
    "ItemsPublic",
    "Message",
    "Token",
    "TokenPayload",
    "NewPassword",
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
    "Rule",
    "Integration",
    "AgentConfig",
    "ModelPreset",
    "ArenaComparison",
    "ArenaVote",
    "ModelEloRanking",
    "ModelUsageLog",
    "MemoryEntry",
]
