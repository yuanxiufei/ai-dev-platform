"""
Persona 管理器 — 角色/提示词的 CRUD 和分级解析

借鉴 AstrBot PersonaManager:
- 初始化时从存储加载所有 personas
- 分级解析：session 覆盖 > conversation 设置 > provider 默认
- 文件夹树形组织 + 排序
- begin_dialogs 自动转换为 message 格式
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.core.persona.models import DEFAULT_PERSONA, Persona, PersonaFolder

logger = logging.getLogger("persona.manager")


class PersonaManager:
    """角色管理器

    职责：
    1. Persona CRUD
    2. 文件夹管理
    3. 分级解析（当前会话生效的角色）
    """

    def __init__(self) -> None:
        self._personas: dict[str, Persona] = {}
        self._folders: dict[str, PersonaFolder] = {}
        self._default_persona_id: str = "default"

        # 注册默认角色
        self._personas["default"] = DEFAULT_PERSONA

    # ── 初始化 ─────────────────────────────────────────

    async def initialize(self, personas: list[Persona] | None = None) -> None:
        """从存储加载所有 personas"""
        if personas:
            for p in personas:
                self._personas[p.persona_id] = p
        logger.info("PersonaManager: loaded %d personas", len(self._personas))

    # ── Persona CRUD ───────────────────────────────────

    async def create_persona(
        self,
        system_prompt: str,
        persona_id: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        custom_error_message: str | None = None,
        folder_id: str | None = None,
        sort_order: int = 0,
    ) -> Persona:
        """创建新角色"""
        pid = persona_id or uuid.uuid4().hex[:12]
        if pid in self._personas:
            raise ValueError(f"Persona '{pid}' already exists")

        persona = Persona(
            persona_id=pid,
            system_prompt=system_prompt,
            begin_dialogs=begin_dialogs or [],
            tools=tools,
            skills=skills,
            custom_error_message=custom_error_message,
            folder_id=folder_id,
            sort_order=sort_order,
        )
        self._personas[pid] = persona
        logger.info("PersonaManager: created persona '%s'", pid)
        return persona

    async def get_persona(self, persona_id: str) -> Persona | None:
        """获取指定角色"""
        return self._personas.get(persona_id)

    async def get_all_personas(self) -> list[Persona]:
        """获取所有角色"""
        return sorted(
            self._personas.values(),
            key=lambda p: (p.sort_order, p.persona_id),
        )

    async def update_persona(
        self,
        persona_id: str,
        system_prompt: str | None = None,
        begin_dialogs: list[str] | None = None,
        tools: list[str] | None = None,
        skills: list[str] | None = None,
        custom_error_message: str | None = None,
        folder_id: str | None = None,
        sort_order: int | None = None,
    ) -> Persona:
        """更新角色"""
        persona = self._personas.get(persona_id)
        if not persona:
            raise ValueError(f"Persona '{persona_id}' not found")

        if system_prompt is not None:
            persona.system_prompt = system_prompt
        if begin_dialogs is not None:
            persona.begin_dialogs = begin_dialogs
        if tools is not None:
            persona.tools = tools
        if skills is not None:
            persona.skills = skills
        if custom_error_message is not None:
            persona.custom_error_message = custom_error_message
        if folder_id is not None:
            persona.folder_id = folder_id
        if sort_order is not None:
            persona.sort_order = sort_order

        logger.info("PersonaManager: updated persona '%s'", persona_id)
        return persona

    async def delete_persona(self, persona_id: str) -> None:
        """删除角色"""
        if persona_id == "default":
            raise ValueError("Cannot delete the default persona")
        if persona_id not in self._personas:
            raise ValueError(f"Persona '{persona_id}' not found")
        del self._personas[persona_id]
        logger.info("PersonaManager: deleted persona '%s'", persona_id)

    # ── 分级解析 ───────────────────────────────────────

    async def resolve_persona(
        self,
        session_persona_id: str | None = None,
        conversation_persona_id: str | None = None,
        provider_default_persona_id: str | None = None,
    ) -> Persona:
        """分级解析当前生效的角色

        解析顺序（优先级从高到低）：
        1. session_persona_id — 会话级覆盖（强制应用）
        2. conversation_persona_id — 对话级设置
        3. provider_default_persona_id — Provider 默认
        4. "default" — 系统默认

        Returns:
            最终生效的 Persona
        """
        resolution_order = [
            ("session", session_persona_id),
            ("conversation", conversation_persona_id),
            ("provider", provider_default_persona_id),
            ("system_default", "default"),
        ]

        for source, pid in resolution_order:
            if pid and pid in self._personas:
                persona = self._personas[pid]
                logger.debug(
                    "PersonaManager: resolved persona '%s' (source=%s)",
                    persona.persona_id, source,
                )
                return persona

        return DEFAULT_PERSONA

    def get_system_prompt(
        self,
        session_persona_id: str | None = None,
        conversation_persona_id: str | None = None,
    ) -> str:
        """同步获取 system prompt（使用默认解析链）"""
        # 快速路径：按优先级查找
        for pid in [session_persona_id, conversation_persona_id, "default"]:
            if pid and pid in self._personas:
                return self._personas[pid].system_prompt
        return DEFAULT_PERSONA.system_prompt

    # ── 文件夹管理 ─────────────────────────────────────

    async def create_folder(
        self,
        name: str,
        parent_id: str | None = None,
        description: str | None = None,
        sort_order: int = 0,
    ) -> PersonaFolder:
        """创建文件夹"""
        folder_id = uuid.uuid4().hex[:12]
        folder = PersonaFolder(
            folder_id=folder_id,
            name=name,
            parent_id=parent_id,
            description=description,
            sort_order=sort_order,
        )
        self._folders[folder_id] = folder
        return folder

    async def get_folder(self, folder_id: str) -> PersonaFolder | None:
        return self._folders.get(folder_id)

    async def get_all_folders(self) -> list[PersonaFolder]:
        return sorted(
            self._folders.values(),
            key=lambda f: (f.sort_order, f.name),
        )

    async def get_folder_tree(self) -> list[dict]:
        """获取文件夹树形结构"""
        folders = await self.get_all_folders()
        folder_map: dict[str, dict] = {
            f.folder_id: f.to_dict() for f in folders
        }

        root = []
        for fid, fdata in folder_map.items():
            parent_id = self._folders[fid].parent_id
            if parent_id is None:
                root.append(fdata)
            elif parent_id in folder_map:
                folder_map[parent_id]["children"].append(fdata)

        def _sort(folders: list[dict]) -> list[dict]:
            folders.sort(key=lambda f: (f["sort_order"], f["name"]))
            for f in folders:
                if f["children"]:
                    f["children"] = _sort(f["children"])
            return folders

        return _sort(root)

    async def delete_folder(self, folder_id: str) -> None:
        """删除文件夹，内部 persona 移到根目录"""
        if folder_id not in self._folders:
            raise ValueError(f"Folder '{folder_id}' not found")
        # 解除关联的 persona
        for persona in self._personas.values():
            if persona.folder_id == folder_id:
                persona.folder_id = None
        del self._folders[folder_id]

    # ── 属性 ───────────────────────────────────────────

    @property
    def default_persona_id(self) -> str:
        return self._default_persona_id

    @default_persona_id.setter
    def default_persona_id(self, value: str) -> None:
        if value not in self._personas:
            raise ValueError(f"Default persona '{value}' not found")
        self._default_persona_id = value

    @property
    def personas(self) -> list[dict]:
        """返回所有 persona 的序列化列表"""
        return [p.to_dict() for p in self._personas.values()]

    @property
    def persona_count(self) -> int:
        return len(self._personas)


# ── 全局单例 ──────────────────────────────────────────────

_persona_manager: PersonaManager | None = None


def init_persona_manager(personas: list[Persona] | None = None) -> PersonaManager:
    """初始化全局 PersonaManager"""
    global _persona_manager
    _persona_manager = PersonaManager()
    # 注意：initialize 是 async，调用方需 await
    return _persona_manager


def get_persona_manager() -> PersonaManager:
    """获取全局 PersonaManager"""
    global _persona_manager
    if _persona_manager is None:
        _persona_manager = PersonaManager()
    return _persona_manager
