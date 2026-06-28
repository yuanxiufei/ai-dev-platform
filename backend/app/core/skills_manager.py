"""Skills 技能系统 — 加载、匹配、注入技能指令"""

from __future__ import annotations

import logging
import re
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("skills")


class Skill:
    """单个技能定义"""

    def __init__(self, name: str, display: str, icon: str, triggers: list[str],
                 category: str, content: str, version: str = "1.0"):
        self.name = name
        self.display = display
        self.icon = icon
        self.triggers = triggers
        self.category = category
        self.content = content
        self.version = version

    def matches(self, text: str) -> bool:
        """检查触发词是否匹配"""
        text_lower = text.lower()
        return any(t.lower() in text_lower for t in self.triggers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "display": self.display,
            "icon": self.icon,
            "triggers": self.triggers,
            "category": self.category,
            "version": self.version,
        }


class SkillsManager:
    """技能管理器 — 单例"""

    _instance: SkillsManager | None = None
    _skills: list[Skill] = []

    def __new__(cls) -> SkillsManager:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def load(cls, skills_dir: str | Path = "skills") -> None:
        """从目录加载所有技能文件"""
        mgr = cls()
        mgr._skills = []
        paths = [Path(skills_dir), Path(__file__).parent.parent.parent.parent / "skills"]

        for base in paths:
            if not base.exists():
                continue
            for f in sorted(base.glob("*.md")):
                try:
                    skill = mgr._parse_skill_file(f)
                    if skill:
                        mgr._skills.append(skill)
                        logger.info("Skill loaded: %s (%s)", skill.name, skill.display)
                except Exception as e:
                    logger.warning("Failed to load skill %s: %s", f, e)

        mgr._sort_by_triggers()
        logger.info("SkillsManager: %d skills loaded", len(mgr._skills))

    @staticmethod
    def _parse_skill_file(path: Path) -> Skill | None:
        """解析 markdown 技能文件（frontmatter + content）"""
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")

        if not lines or lines[0].strip() != "---":
            return None

        # 解析 frontmatter
        fm: dict[str, Any] = {}
        end = 0
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                end = i
                break
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip()
                val = val.strip()
                if key == "triggers":
                    fm[key] = [t.strip() for t in val.strip("[]").split(",")]
                else:
                    fm[key] = val

        content = "\n".join(lines[end + 1:]).strip()
        if not content or "name" not in fm:
            return None

        return Skill(
            name=fm["name"],
            display=fm.get("display", fm["name"]),
            icon=fm.get("icon", "Code"),
            triggers=fm.get("triggers", []),
            category=fm.get("category", "general"),
            content=content,
            version=fm.get("version", "1.0"),
        )

    @classmethod
    def _sort_by_triggers(cls) -> None:
        """按触发词长度降序（优先匹配更长的关键词）"""
        mgr = cls()
        mgr._skills.sort(key=lambda s: -max(len(t) for t in s.triggers or ["x"]))

    @classmethod
    def match(cls, text: str, limit: int = 3) -> list[Skill]:
        """匹配用户输入，返回相关技能"""
        mgr = cls()
        matched = [s for s in mgr._skills if s.matches(text)]
        return matched[:limit]

    @classmethod
    def get_all(cls) -> list[Skill]:
        return cls()._skills

    @classmethod
    def get(cls, name: str) -> Skill | None:
        for s in cls()._skills:
            if s.name == name:
                return s
        return None

    @classmethod
    def build_skill_instructions(cls, text: str, skill_names: list[str] | None = None) -> str:
        """构建注入到 system prompt 的技能指令"""
        if skill_names:
            skills = [s for s in cls()._skills if s.name in skill_names]
        else:
            skills = cls.match(text)

        if not skills:
            return ""

        parts = ["## 🎯 激活技能\n"]
        for sk in skills:
            parts.append(f"### {sk.display}\n{sk.content}\n")
        return "\n".join(parts)


# 自动加载
def init_skills(skills_dir: str = "skills") -> SkillsManager:
    SkillsManager.load(skills_dir)
    return SkillsManager()
