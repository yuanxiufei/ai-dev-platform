"""
Persona 模块 — 角色/提示词分级管理系统

借鉴 AstrBot 的 PersonaManager：
- 分级解析：session > conversation > provider > default
- 文件夹树形组织
- begin_dialogs few-shot 示例注入
- 工具/技能白名单 per-persona
"""

from app.core.persona.models import DEFAULT_PERSONA, Persona, PersonaFolder  # noqa: F401
from app.core.persona.manager import (  # noqa: F401
    PersonaManager,
    init_persona_manager,
    get_persona_manager,
)
