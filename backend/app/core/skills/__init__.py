"""
Skills — Markdown 技能指令集 (借鉴 Open WebUI Skills)

每个技能是一个 Markdown 文件，定义模型如何完成特定任务。
技能在执行时被注入 system prompt，指导模型的行为方式。

格式:
```
# skill: <name>
## description: <description>
## category: <category>
---
... Markdown 指令内容 ...
```
"""

import re
import os
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Skill:
    """单个技能定义"""
    name: str
    description: str = ""
    category: str = "general"
    content: str = ""  # 纯 Markdown 指令内容
    author: str = ""
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)
    path: str = ""  # 文件路径
    enabled: bool = True
    created_at: float = 0.0
    updated_at: float = 0.0
    usage_count: int = 0

    def to_system_prompt(self) -> str:
        """将技能转换为 system prompt 片段"""
        return f"""# Skill: {self.name}
{self.description}
---
{self.content}"""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "content": self.content,
            "author": self.author,
            "version": self.version,
            "tags": self.tags,
            "path": self.path,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "usage_count": self.usage_count,
        }


SKILL_HEADER_RE = re.compile(
    r"^#\s*skill:\s*(.+)$\s*"
    r"^##\s*description:\s*(.+)$\s*"
    r"^##\s*category:\s*(.+)$",
    re.MULTILINE | re.IGNORECASE,
)

YAML_LIKE_RE = re.compile(
    r"^author:\s*(.+)$\s*"
    r"^version:\s*(.+)$\s*"
    r"^tags:\s*\[(.*)\]$",
    re.MULTILINE | re.IGNORECASE,
)


def parse_skill(markdown: str, source_path: str = "") -> Optional[Skill]:
    """解析 Markdown 字符串为 Skill 对象"""
    if not markdown or not markdown.strip():
        return None

    # 匹配标题头部
    header_match = SKILL_HEADER_RE.search(markdown)
    if not header_match:
        return None

    name = header_match.group(1).strip()
    description = header_match.group(2).strip()
    category = header_match.group(3).strip()

    # 提取内容（头部之后的所有内容）
    content_start = header_match.end()
    # 移除头部，取分隔符之后的内容
    remaining = markdown[content_start:].lstrip()
    # 跳过可能的 `---` 分隔符
    if remaining.startswith("---"):
        remaining = remaining[3:].lstrip("\n").lstrip()

    content = remaining.strip()

    # 尝试提取元数据
    author = ""
    version = "1.0"
    tags: list[str] = []

    yaml_match = YAML_LIKE_RE.search(content)
    if yaml_match:
        author = yaml_match.group(1).strip() or ""
        version = yaml_match.group(2).strip() or "1.0"
        tags_str = yaml_match.group(3).strip() or ""
        tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    now = time.time()
    return Skill(
        name=name,
        description=description,
        category=category,
        content=content,
        author=author,
        version=version,
        tags=tags,
        path=source_path,
        created_at=now,
        updated_at=now,
    )


def parse_skill_file(filepath: str) -> Optional[Skill]:
    """从文件加载技能"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            markdown = f.read()
        skill = parse_skill(markdown, source_path=filepath)
        if skill:
            stat = os.stat(filepath)
            skill.created_at = stat.st_ctime
            skill.updated_at = stat.st_mtime
        return skill
    except (OSError, UnicodeDecodeError):
        return None


class SkillsRegistry:
    """技能注册中心 — 从 skills/ 目录自动加载"""

    def __init__(self, skills_root: str = "skills"):
        self.skills_root: str = skills_root
        self._skills: dict[str, Skill] = {}
        self._by_category: dict[str, list[str]] = {}

    def load_all(self) -> int:
        """扫描并加载所有 .md 技能文件"""
        count = 0
        if not os.path.isdir(self.skills_root):
            os.makedirs(self.skills_root, exist_ok=True)
            return 0

        for fname in os.listdir(self.skills_root):
            if not fname.endswith(".md"):
                continue
            filepath = os.path.join(self.skills_root, fname)
            skill = parse_skill_file(filepath)
            if skill:
                self._skills[skill.name] = skill
                self._by_category.setdefault(skill.category, []).append(skill.name)
                count += 1
        return count

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_all(self, category: Optional[str] = None, enabled_only: bool = True) -> list[dict]:
        result = []
        for skill in self._skills.values():
            if enabled_only and not skill.enabled:
                continue
            if category and skill.category != category:
                continue
            result.append(skill.to_dict())
        result.sort(key=lambda s: s["name"])
        return result

    def list_categories(self) -> list[dict]:
        return [
            {"name": cat, "count": len(names)}
            for cat, names in sorted(self._by_category.items())
        ]

    def save_skill(self, skill: Skill) -> str:
        """保存技能到文件"""
        filepath = os.path.join(self.skills_root, f"{skill.name}.md")
        # 生成 Markdown 格式
        lines = [
            f"# skill: {skill.name}",
            f"## description: {skill.description}",
            f"## category: {skill.category}",
            "",
            "---",
            "",
            skill.content,
        ]
        content = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        skill.path = filepath
        self._skills[skill.name] = skill
        self._by_category.setdefault(skill.category, []).append(skill.name)
        return filepath

    def delete_skill(self, name: str) -> bool:
        skill = self._skills.pop(name, None)
        if skill:
            # 从分类中移除
            for cat_list in self._by_category.values():
                if name in cat_list:
                    cat_list.remove(name)
            # 删除文件
            if skill.path and os.path.isfile(skill.path):
                os.remove(skill.path)
            return True
        return False

    def build_system_prompt(self, skill_names: list[str]) -> str:
        """将多个技能组合为一个 system prompt"""
        if not skill_names:
            return ""
        prompts: list[str] = []
        for name in skill_names:
            skill = self._skills.get(name)
            if skill and skill.enabled:
                prompts.append(skill.to_system_prompt())
        if not prompts:
            return ""
        return "\n\n---\n\n".join(prompts)

    @property
    def count(self) -> int:
        return len(self._skills)


# 全局单例
_registry: Optional[SkillsRegistry] = None


def get_skills_registry() -> SkillsRegistry:
    global _registry
    if _registry is None:
        _registry = SkillsRegistry(skills_root="skills")
    return _registry


def init_skills_registry(skills_root: str = "skills") -> SkillsRegistry:
    global _registry
    _registry = SkillsRegistry(skills_root=skills_root)
    _registry.load_all()
    return _registry
