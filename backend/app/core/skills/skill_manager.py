"""
技能 (Skills) 管理系统 — 技能发现/激活/安装/LLM 提示生成

v2 更新（借鉴 anthropics-skills SKILL.md 规范）：
- 渐进披露：Level 1 (元数据) → Level 2 (SKILL.md body) → Level 3 (捆绑资源)
- 支持 scripts/references/assets 资源目录
- 格式验证：SKILL.md 必须有 name + description frontmatter
- 三层来源: 本地 skills_root + 插件 plugins/skills/ + 工作区
- 激活/停用 + 按名称索引
- Zip 包安装 (root_mode / 嵌套目录)
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("app.core.skills")

SKILL_CONFIG_FILENAME = "SKILL.md"

# ── 渐进披露层级 ──

class SkillDisclosureLevel:
    """渐进披露层级（借鉴 anthropics-skills）"""
    LEVEL_1 = 1  # 元数据（name + description），始终在上下文中
    LEVEL_2 = 2  # SKILL.md 完整内容，技能触发时加载
    LEVEL_3 = 3  # 捆绑资源（scripts/references/assets），按需加载


# ── 捆绑资源类型 ──

RESOURCE_DIRS = {
    "scripts": "可执行脚本（确定性/可重复任务）",
    "references": "参考文档（按需加载到上下文）",
    "assets": "静态资源（模板、图标、字体等）",
}


@dataclass
class SkillInfo:
    """技能元数据（v2 — 对齐 anthropics-skills SKILL.md 规范）"""
    name: str
    description: str = ""
    path: str = ""
    active: bool = True
    source: str = "local"  # local / plugin / workspace
    readonly: bool = False
    metadata: dict = field(default_factory=dict)
    skill_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    # 🆕 v2 新增字段
    license_info: str = ""         # 许可证信息
    version: str = "1.0.0"         # 技能版本
    author: str = ""               # 作者
    tags: list[str] = field(default_factory=list)  # 标签
    tier: str = "curated"          # 层级: system / curated / experimental（借鉴 openai-skills）
    requires_confirmation: bool = False  # 是否需要用户确认

    # 捆绑资源路径
    scripts_dir: str = ""
    references_dir: str = ""
    assets_dir: str = ""

    # 原始内容缓存
    _raw_content: str = ""  # SKILL.md 完整正文（Level 2）
    _body_only: str = ""    # 去掉 frontmatter 的指令正文

    def to_prompt_entry(self) -> str:
        """获取完整的 SKILL.md 内容（Level 2 渐进披露）"""
        content = ""
        if os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                pass

        if not content and self._raw_content:
            content = self._raw_content

        if not content:
            # 从 metadata 生成
            content = f"# {self.name}\n{self.description}"

        return content

    def get_level1_summary(self) -> str:
        """获取 Level 1 元数据摘要（始终在上下文中）"""
        parts = [f"### {self.name}"]
        if self.description:
            parts.append(f"**{self.description}**")
        if self.tags:
            parts.append(f"*Tags: {', '.join(self.tags)}*")
        if self.tier != "curated":
            parts.append(f"*Tier: {self.tier}*")
        if self.version:
            parts.append(f"*Version: {self.version}*")
        return "\n".join(parts)

    def get_resources(self) -> dict[str, list[str]]:
        """获取所有捆绑资源路径"""
        resources = {}
        for dir_type, desc in RESOURCE_DIRS.items():
            dir_path = getattr(self, f"{dir_type}_dir", "")
            if dir_path and os.path.isdir(dir_path):
                try:
                    files = [f for f in os.listdir(dir_path) if not f.startswith(".")]
                    if files:
                        resources[dir_type] = files
                except Exception:
                    pass
        return resources


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
        """读取 SKILL.md 解析技能元数据（v2 — 对齐 anthropics-skills 规范）"""
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            logger.warning("Failed to read skill file %s: %s", skill_file, e)
            return None

        # 解析 frontmatter（v2 扩展字段）
        fm = self._parse_frontmatter_v2(content)
        name = fm.get("name", "")
        if not name:
            name = os.path.basename(os.path.dirname(skill_file) or skill_file)

        # 格式验证：必须有 name + description
        if not fm.get("description"):
            logger.warning("SKILL.md at %s missing 'description' in frontmatter", skill_file)

        # 提取正文（去掉 frontmatter）
        body = content
        if content.startswith("---"):
            end = content.find("---", 3)
            if end > 0:
                body = content[end + 3:].strip()

        # 确定资源目录（与 SKILL.md 同级的 scripts/references/assets/）
        skill_dir = os.path.dirname(os.path.abspath(skill_file))
        scripts_dir = os.path.join(skill_dir, "scripts") if os.path.isdir(os.path.join(skill_dir, "scripts")) else ""
        references_dir = os.path.join(skill_dir, "references") if os.path.isdir(os.path.join(skill_dir, "references")) else ""
        assets_dir = os.path.join(skill_dir, "assets") if os.path.isdir(os.path.join(skill_dir, "assets")) else ""

        return SkillInfo(
            name=name,
            description=fm.get("description", ""),
            path=skill_file,
            source=source,
            metadata={"file": skill_file},
            # v2 新增
            license_info=fm.get("license", ""),
            version=fm.get("version", "1.0.0"),
            author=fm.get("author", ""),
            tags=fm.get("tags", []),
            tier=fm.get("tier", "curated"),
            requires_confirmation=fm.get("requires_confirmation", False),
            scripts_dir=scripts_dir,
            references_dir=references_dir,
            assets_dir=assets_dir,
            _raw_content=content,
            _body_only=body,
        )

    # ── Frontmatter 解析 v2 ──

    @staticmethod
    def _parse_frontmatter(content: str) -> tuple[str, str]:
        """解析 YAML frontmatter（兼容旧版，返回 name, description）"""
        fm = SkillManager._parse_frontmatter_v2(content)
        return fm.get("name", ""), fm.get("description", "")

    @staticmethod
    def _parse_frontmatter_v2(content: str) -> dict:
        """解析 YAML frontmatter（v2 完整字段，对齐 anthropics-skills 规范）

        支持的字段：
        - name (必填): 技能唯一标识符
        - description (必填): 技能用途和触发条件
        - license: 许可证信息
        - version: 版本号
        - author: 作者
        - tags: 标签列表（逗号分隔或 YAML 列表）
        - tier: 层级 (system/curated/experimental)
        - requires_confirmation: 是否需要用户确认
        """
        result: dict = {
            "name": "",
            "description": "",
            "license": "",
            "version": "1.0.0",
            "author": "",
            "tags": [],
            "tier": "curated",
            "requires_confirmation": False,
        }

        if not content.startswith("---"):
            return result

        end = content.find("---", 3)
        if end <= 0:
            return result

        fm_text = content[3:end].strip()
        for line in fm_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # 简单键值解析（兼容无引号、单引号、双引号）
            if ":" not in line:
                continue

            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("'\"")

            if key == "name":
                result["name"] = value
            elif key == "description":
                result["description"] = value
            elif key == "license":
                result["license"] = value
            elif key == "version":
                result["version"] = value
            elif key == "author":
                result["author"] = value
            elif key == "tier":
                result["tier"] = value if value in ("system", "curated", "experimental") else "curated"
            elif key == "requires_confirmation":
                result["requires_confirmation"] = value.lower() in ("true", "yes", "1")
            elif key == "tags":
                # 支持逗号分隔或 JSON 列表
                if value.startswith("["):
                    try:
                        result["tags"] = json.loads(value)
                    except Exception:
                        result["tags"] = [t.strip() for t in value.strip("[]").split(",") if t.strip()]
                else:
                    result["tags"] = [t.strip() for t in value.split(",") if t.strip()]

        return result

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
                # ZIP Slip 防护：校验每个成员的提取路径
                for member in zf.infolist():
                    member_path = os.path.realpath(os.path.join(tmp_dir, member.filename))
                    if os.path.commonpath([member_path, os.path.realpath(tmp_dir)]) != os.path.realpath(tmp_dir):
                        raise ValueError(f"ZIP path traversal detected: {member.filename}")
                zf.extractall(tmp_dir)

            # 查找 SKILL.md
            skill_file = self._find_skill_file(tmp_dir)
            if not skill_file:
                raise ValueError("No SKILL.md found in zip package")

            # 读取并解析名称
            info = await self._parse_skill(skill_file, source="local")
            if not info:
                raise ValueError("Failed to parse SKILL.md")

            # 确定安装目录 — 过滤路径分隔符防止穿越
            skill_dir_name = info.name.lower().replace(" ", "_").replace("-", "_")
            skill_dir_name = "".join(c for c in skill_dir_name if c.isalnum() or c == "_")
            if not skill_dir_name:
                raise ValueError(f"Invalid skill name: {info.name}")
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

    # ── LLM Prompt 生成（v2 渐进披露）────────────────

    def build_skills_prompt(self, level: int = 1) -> str:
        """为 LLM 构建技能提示（v2 渐进披露原则）

        借鉴 anthropics-skills 三级渐进披露：
        - Level 1: 元数据摘要（始终在上下文中，~100 词/技能）
        - Level 2: 完整 SKILL.md 内容（技能触发时加载）
        - Level 3: 捆绑资源引用（按需加载）
        """
        active = self.list_skills(active_only=True)
        if not active:
            return ""

        # 按 tier 排序（system > curated > experimental）
        tier_order = {"system": 0, "curated": 1, "experimental": 2}
        active.sort(key=lambda s: (tier_order.get(s.tier, 99), s.name))

        if level == 1:
            return self._build_level1_prompt(active)
        elif level == 2:
            return self._build_level2_prompt(active)
        else:
            return self._build_level3_prompt(active)

    def _build_level1_prompt(self, skills: list[SkillInfo]) -> str:
        """Level 1: 元数据摘要（始终在上下文中）"""
        lines = [
            "# Available Skills",
            "",
            "You have access to the following skills. Skills provide specialized capabilities.",
            "When a skill is relevant to the user's request, read its full SKILL.md content.",
            "",
            "## Skill Catalog",
            "",
        ]

        for i, skill in enumerate(skills, 1):
            lines.append(f"### {i}. {skill.name}")
            if skill.description:
                lines.append(f"**{skill.description}**")
            meta_parts = []
            if skill.tags:
                meta_parts.append(f"Tags: {', '.join(skill.tags)}")
            if skill.tier != "curated":
                meta_parts.append(f"Tier: {skill.tier}")
            if skill.version and skill.version != "1.0.0":
                meta_parts.append(f"v{skill.version}")
            if skill.requires_confirmation:
                meta_parts.append("⚠️ Requires confirmation")
            if meta_parts:
                lines.append(f"*{(' · ').join(meta_parts)}*")
            lines.append(f"*Source: {skill.source}, Path: `{skill.path}`*")
            lines.append("")

        # 使用规则
        lines.extend([
            "## Using Skills",
            "",
            "1. **Progressive disclosure** — Read a skill's `SKILL.md` content fully before using it.",
            "2. **Do not guess** — If you're unsure whether a skill applies, re-read the skill description.",
            "3. **Coordinate** — Some skills may work together. Use them in the correct sequence.",
            "4. **Respect skill boundaries** — Each skill is self-contained. Do not mix instructions between skills.",
            "5. **Explicit activation** — Mention which skill you're using when you invoke it.",
            "6. **Confirmation required** — Skills marked ⚠️ need user confirmation before execution.",
            "",
        ])

        return "\n".join(lines)

    def _build_level2_prompt(self, skills: list[SkillInfo]) -> str:
        """Level 2: 完整 SKILL.md 内容"""
        lines = ["# Full Skill Instructions", ""]
        for skill in skills:
            lines.append(f"## {skill.name}")
            content = skill.to_prompt_entry()
            lines.append(content)
            lines.append("---\n")
        return "\n".join(lines)

    def _build_level3_prompt(self, skills: list[SkillInfo]) -> str:
        """Level 3: 捆绑资源引用"""
        lines = ["# Skill Resources", ""]
        has_resources = False
        for skill in skills:
            resources = skill.get_resources()
            if resources:
                has_resources = True
                lines.append(f"## {skill.name}")
                for res_type, files in resources.items():
                    desc = RESOURCE_DIRS.get(res_type, "")
                    lines.append(f"- **{res_type}/** ({desc}): {', '.join(files[:10])}")
                lines.append("")
        if not has_resources:
            lines.append("*No bundled resources available.*")
        return "\n".join(lines)

    def get_skill_prompt(self, name: str) -> Optional[str]:
        """获取单个技能内容"""
        skill = self._skills.get(name)
        if not skill or not skill.active:
            return None
        return skill.to_prompt_entry()

    def validate_skill(self, name: str) -> dict:
        """验证技能格式（对齐 anthropics-skills 规范）"""
        skill = self._skills.get(name)
        if not skill:
            return {"valid": False, "error": f"Skill '{name}' not found"}

        issues = []
        if not skill.name:
            issues.append("Missing 'name' in frontmatter")
        if not skill.description:
            issues.append("Missing 'description' in frontmatter")
        if not os.path.isfile(skill.path):
            issues.append(f"SKILL.md file not found at {skill.path}")
        if skill.tier not in ("system", "curated", "experimental"):
            issues.append(f"Invalid tier '{skill.tier}' (must be system/curated/experimental)")

        return {
            "valid": len(issues) == 0,
            "skill_name": skill.name,
            "issues": issues,
            "warnings": [],
            "resources": {
                rt: bool(getattr(skill, f"{rt}_dir", ""))
                for rt in RESOURCE_DIRS
            }
        }

    def validate_all(self) -> list[dict]:
        """验证全部技能格式"""
        return [self.validate_skill(name) for name in self._skills]


# ══════════════════════════════════════════════
# 技能热加载 (SkillWatcher)
# ══════════════════════════════════════════════

import threading as _th
import time as _time


class SkillWatcher:
    """监听技能目录变更，自动重新加载新增/修改的 SKILL.md 文件

    采用轮询模式 (mtime 对比)，与 ConfigReloader 一致。
    """

    def __init__(self, manager: SkillManager, poll_interval: float = 5.0):
        self._mgr = manager
        self._interval = poll_interval
        self._dir_mtimes: dict[str, float] = {}
        self._files_mtimes: dict[str, float] = {}
        self._thread: _th.Thread | None = None
        self._running = False
        self._added_count = 0
        self._reload_count = 0

    def start_watching(self) -> None:
        if self._running:
            return
        self._running = True
        self._snapshot()
        self._thread = _th.Thread(target=self._watch_loop, daemon=True, name="skill-watcher")
        self._thread.start()
        logger.info("SkillWatcher started (interval=%.1fs)", self._interval)

    def stop_watching(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("SkillWatcher stopped")

    def reload_now(self) -> dict:
        """立即重新发现技能 (同步包装 async discover)"""
        import asyncio

        async def _do():
            self._mgr._skills.clear()
            await self._mgr.discover()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已运行的事件循环中提交任务
                task = asyncio.ensure_future(_do())
                # 轮询等待完成（非阻塞）
                deadline = _time.monotonic() + 10
                while not task.done() and _time.monotonic() < deadline:
                    _time.sleep(0.1)
            else:
                asyncio.run(_do())
        except RuntimeError:
            asyncio.run(_do())

        self._reload_count += 1
        self._snapshot()
        logger.info("SkillWatcher reloaded: %d skills (#%d)",
                    len(self._mgr._skills), self._reload_count)
        return {
            "skills_count": len(self._mgr._skills),
            "reload_count": self._reload_count,
            "added_count": self._added_count,
        }

    def _snapshot(self) -> None:
        self._dir_mtimes.clear()
        self._files_mtimes.clear()
        dirs_to_scan = [self._mgr._skills_root] + list(self._mgr._plugin_skills_dirs)
        for d in dirs_to_scan:
            if not os.path.isdir(d):
                continue
            self._dir_mtimes[d] = os.path.getmtime(d)
            for entry in os.listdir(d):
                full = os.path.join(d, entry)
                if os.path.isfile(full):
                    self._files_mtimes[full] = os.path.getmtime(full)
                elif os.path.isdir(full):
                    sf = os.path.join(full, SKILL_CONFIG_FILENAME)
                    if os.path.isfile(sf):
                        self._files_mtimes[sf] = os.path.getmtime(sf)

    def _has_changes(self) -> bool:
        # 检查目录变化 (新目录出现)
        dirs_to_scan = [self._mgr._skills_root] + list(self._mgr._plugin_skills_dirs)
        for d in dirs_to_scan:
            if not os.path.isdir(d):
                continue
            prev = self._dir_mtimes.get(d, 0)
            curr = os.path.getmtime(d)
            if curr != prev:
                return True

        # 检查 SKILL.md 文件变化
        for d in dirs_to_scan:
            if not os.path.isdir(d):
                continue
            for entry in os.listdir(d):
                full = os.path.join(d, entry)
                if os.path.isfile(full):
                    prev = self._files_mtimes.get(full, 0)
                    curr = os.path.getmtime(full)
                    if curr != prev:
                        return True
                elif os.path.isdir(full):
                    sf = os.path.join(full, SKILL_CONFIG_FILENAME)
                    if os.path.isfile(sf):
                        prev = self._files_mtimes.get(sf, 0)
                        curr = os.path.getmtime(sf)
                        if curr != prev:
                            return True

        return False

    def _watch_loop(self) -> None:
        while self._running:
            try:
                if self._has_changes():
                    self._added_count += 1
                    logger.info("SkillWatcher: changes detected, reloading...")
                    self.reload_now()
            except Exception as e:
                logger.warning("SkillWatcher error: %s", e)
            _time.sleep(self._interval)


# 全局单例
_skill_watcher: SkillWatcher | None = None


def init_skill_watcher(manager: SkillManager, poll_interval: float = 5.0,
                        auto_watch: bool = True) -> SkillWatcher:
    global _skill_watcher
    _skill_watcher = SkillWatcher(manager, poll_interval=poll_interval)
    if auto_watch:
        _skill_watcher.start_watching()
    return _skill_watcher


def get_skill_watcher() -> SkillWatcher | None:
    return _skill_watcher
