"""
Persona 数据模型 — 角色/提示词管理

借鉴 AstrBot 的 Persona + Personality 设计：
- Persona: 完整的角色定义（system_prompt + begin_dialogs + tools/skills 白名单）
- PersonaFolder: 文件夹树形组织
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Persona:
    """角色定义"""

    persona_id: str
    """唯一标识"""

    system_prompt: str = ""
    """系统提示词"""

    begin_dialogs: list[str] = field(default_factory=list)
    """预设对话示例 (few-shot)，交替 user/assistant"""

    tools: list[str] | None = None
    """工具白名单。None = 使用全部工具，[] = 不使用任何工具"""

    skills: list[str] | None = None
    """技能白名单。None = 使用全部技能，[] = 不使用任何技能"""

    custom_error_message: str | None = None
    """自定义错误回复"""

    folder_id: str | None = None
    """所属文件夹 ID"""

    sort_order: int = 0
    """排序顺序"""

    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "persona_id": self.persona_id,
            "system_prompt": self.system_prompt,
            "begin_dialogs": self.begin_dialogs,
            "tools": self.tools,
            "skills": self.skills,
            "custom_error_message": self.custom_error_message,
            "folder_id": self.folder_id,
            "sort_order": self.sort_order,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def get_processed_dialogs(self) -> list[dict]:
        """将 begin_dialogs 转换为 OpenAI 兼容的 message 列表"""
        result = []
        user_turn = True
        for dialog in self.begin_dialogs:
            result.append({
                "role": "user" if user_turn else "assistant",
                "content": dialog,
            })
            user_turn = not user_turn
        return result

    @property
    def system_message(self) -> dict:
        """获取 system prompt 组成的 message"""
        return {"role": "system", "content": self.system_prompt}


@dataclass
class PersonaFolder:
    """角色文件夹"""

    folder_id: str
    name: str
    parent_id: str | None = None
    description: str | None = None
    sort_order: int = 0

    def to_dict(self) -> dict:
        return {
            "folder_id": self.folder_id,
            "name": self.name,
            "parent_id": self.parent_id,
            "description": self.description,
            "sort_order": self.sort_order,
            "children": [],
        }


# 默认角色
DEFAULT_PERSONA = Persona(
    persona_id="default",
    system_prompt="You are a helpful and friendly AI assistant. "
                  "Provide accurate, helpful, and safe responses.",
    begin_dialogs=[],
    tools=None,
    skills=None,
)
