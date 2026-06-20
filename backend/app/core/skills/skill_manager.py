"""
技能 (Skills) 管理系统 — 技能发现/激活/安装/LLM 提示生成

借鉴 AstrBot SkillManager:
- 三层来源: 本地 skills_root + 插件 plugins/skills/ + 工作区
- 激活/停用 + 按名称索引
- Zip 包安装 (root_mode / 嵌套目录)
- 为 LLM 构建 skill prompt (渐进披露 + 使用规则)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("app.core.skills")

SKILL_CONFIG_FILENAME = "SKILL.md"


@dataclass
class SkillInfo:
    """技能元数据"""
    name: str
    description: str = ""
    path: str = ""
    active: bool = True
    source: str = "local"  # local / plugin / workspace
    readonly: bool = False
    metadata: dict = field(default_factory=dict)
    skill_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def to_prompt_entry(self) -> str:
        content = ""
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                pass

        if not content:
            # 从 metadata 生成
            content = f"# {self.name}\n{self.description}"

        return content


class SkillManager:
    """
    技能管理器

    Usage:
        mgr = SkillManager(skills_root="./skills")
        await mgr.discover()
        skills = mgr.list_skills()
        prompt = mgr.build_skills_prompt()
    """

    def __init__(self, skills_root: str):
        self._skills_root = os.path.abspath(skills_root)
        self._plugin_skills_dirs: list[str] = []
        self._skills: dict[str, SkillInfo] = {}
        os.makedirs(self._skills_root, exist_ok=True)

    # ── 发现 ───────────────────────────────

    async def discover(self) -> None:
        """扫描所有来源发现技能"""
        self._skills.clear()

        # 1. 本地技能
        await self._scan_directory(self._skills_root, source="local")

        # 2. 插件技能
        for plugin_dir in self._plugin_skills_dirs:
            if os.path.isdir(plugin_dir):
                await self._scan_directory(plugin_dir, source="plugin")

        logger.debug("Discovered %d skills", len(self._skills))

    async def _scan_directory(self, root: str, source: str) -> None:
        """扫描目录，发现技能"""
        if not os.path.isdir(root):
            return
        for entry in os.listdir(root):
            full_path = os.path.join(root, entry)
            skill_file = os.path.join(full_path, SKILL_CONFIG_FILENAME)

            if os.path.isfile(skill_file):
                info = await self._parse_skill(skill_file, source)
                if info:
                    self._skills[info.name] = info
            elif os.path.isdir(full_path) and not entry.startswith("."):
                # 嵌套目录
                nested_skill = os.path.join(full_path, SKILL_CONFIG_FILENAME)
                if os.path.isfile(nested_skill):
                    info = await self._parse_skill(nested_skill, source)
                    if info:
                        info.path = full_path  # 目录级技能
                        self._skills[info.name] = info

    async def _parse_skill(self, skill_file: str, source: str) -> Optional[SkillInfo]:
        """读取 SKILL.md 解析技能元数据"""
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning("Failed to read skill file %s: %s", skill_file, e)
            return None

        # 解析 frontmatter
        name, description = self._parse_frontmatter(content)
        if not name:
            name = os.path.basename(os.path.dirname(skill_file) or skill_file)

        return SkillInfo(
            name=name,
            description=description,
            path=skill_file,
            source=source,
            metadata={"file": skill_file},
        )

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[str, str]:
        """解析 YAML frontmatter"""
        name = ""
        description = ""

        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                fm_text = content[3:end].strip()
                for line in fm_text.split("\n"):
                    line = line.strip()
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip().strip("'\"")
                    elif line.startswith("description:"):
                        description = line.split(":", 1)[1].strip().strip("'\"'")

        return name, description

    # ── CRUD ───────────────────────────────

    def add_plugin_skills_dir(self, path: str) -> None:
        """添加插件技能目录"""
        if path not in self._plugin_skills_dirs:
            self._plugin_skills_dirs.append(path)

    def list_skills(self, active_only: bool = True) -> list[SkillInfo]:
        """列出所有技能"""
        skills = list(self._skills.values())
        if active_only:
            skills = [s for s in skills if s.active]
        return skills

    def get_skill(self, name: str) -> Optional[SkillInfo]:
        return self._skills.get(name)

    def set_skill_active(self, name: str, active: bool) -> bool:
        """激活或停用技能"""
        skill = self._skills.get(name)
        if skill and not skill.readonly:
            skill.active = active
            return True
        return False

    def delete_skill(self, name: str) -> bool:
        """删除技能文件"""
        skill = self._skills.pop(name, None)
        if skill and not skill.readonly and os.path.isfile(skill.path):
            try:
                os.remove(skill.path)
                return True
            except OSError:
                pass
        return False

    # ── 安装 ───────────────────────────────

    async def install_from_zip(self, zip_path: str) -> Optional[SkillInfo]:
        """
        从 zip 包安装技能

        支持两种布局:
        - root_mode: zip 根目录直接有 SKILL.md
        - 嵌套: zip 根目录是一个子目录，子目录内有 SKILL.md
        """
        if not os.path.isfile(zip_path):
            raise FileNotFoundError(f"Zip not found: {zip_path}")

        tmp_dir = tempfile.mkdtemp(prefix="skill_install_")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp_dir)

            # 查找 SKILL.md
            skill_file = self._find_skill_file(tmp_dir)
            if not skill_file:
                raise ValueError("No SKILL.md found in zip package")

            # 读取并解析名称
            info = await self._parse_skill(skill_file, source="local")
            if not info:
                raise ValueError("Failed to parse SKILL.md")

            # 确定安装目录
            skill_dir_name = info.name.lower().replace(" ", "_").replace("-", "_")
            dest_dir = os.path.join(self._skills_root, skill_dir_name)

            # 如果已存在，重命名
            if os.path.exists(dest_dir):
                skill_dir_name = f"{skill_dir_name}_{info.skill_id}"
                dest_dir = os.path.join(self._skills_root, skill_dir_name)

            # 复制技能目录
            src_dir = os.path.dirname(skill_file) if skill_file != os.path.join(tmp_dir, SKILL_CONFIG_FILENAME) else tmp_dir
            shutil.copytree(src_dir, dest_dir, dirs_exist_ok=True)

            # 注册
            installed_file = os.path.join(dest_dir, SKILL_CONFIG_FILENAME)
            info.path = installed_file
            info.source = "local"
            info.readonly = False
            self._skills[info.name] = info

            logger.info("Installed skill '%s' from zip: %s", info.name, dest_dir)
            return info

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def _find_skill_file(root: str) -> Optional[str]:
        """在目录中查找 SKILL.md"""
        # 检查根目录
        skill_file = os.path.join(root, SKILL_CONFIG_FILENAME)
        if os.path.isfile(skill_file):
            return skill_file

        # 检查子目录（取第一个）
        for entry in os.listdir(root):
            full = os.path.join(root, entry)
            if os.path.isdir(full):
                sf = os.path.join(full, SKILL_CONFIG_FILENAME)
                if os.path.isfile(sf):
                    return sf

        return None

    # ── LLM Prompt 生成 ─────────────────────

    def build_skills_prompt(self) -> str:
        """为 LLM 构建完整的技能提示（渐进披露原则）"""
        active = self.list_skills(active_only=True)
        if not active:
            return ""

        lines = [
            "# Available Skills",
            "",
            "You have access to the following skills. Skills provide specialized capabilities.",
            "",
            "## Using Skills",
            "",
            "1. **Progressive disclosure** — Read a skill's `SKILL.md` content fully before using it.",
            "2. **Do not guess** — If you're unsure whether a skill applies, re-read the skill description.",
            "3. **Coordinate** — Some skills may work together. Use them in the correct sequence.",
            "4. **Respect skill boundaries** — Each skill is self-contained. Do not mix instructions between skills.",
            "5. **Explicit activation** — Mention which skill you're using when you invoke it.",
            "",
            "## Available Skills",
            "",
        ]

        for i, skill in enumerate(active, 1):
            lines.append(f"### {i}. {skill.name}")
            if skill.description:
                lines.append(f"**Description**: {skill.description}")
            lines.append(f"**Source**: {skill.source}")
            lines.append(f"**Path**: `{skill.path}`")
            lines.append("")

        return "\n".join(lines)

    def get_skill_prompt(self, name: str) -> Optional[str]:
        """获取单个技能内容"""
        skill = self._skills.get(name)
        if not skill or not skill.active:
            return None
        return skill.to_prompt_entry()
