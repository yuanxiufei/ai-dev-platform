"""
Agent Custom Modes 系统 — 借鉴 Roo Code .roomodes 设计

提供多种 Agent 工作模式，每种模式有不同的：
- 角色定义 & 系统提示词
- 可用工具集
- 推荐模型
- 温度等参数

模式类型:
  - architect  🏗️ 架构设计 — 只读工具，专注分析规划
  - code       💻 编码实现 — 完整工具集，专注代码编写
  - debug      🪲 问题调试 — 终端 + 搜索，专注定位问题
  - test       🧪 测试开发 — 测试文件操作，专注测试编写
  - review     📋 代码审查 — 只读 + diff，专注审阅
  - docs       📖 文档编写 — 只读 + web_search，专注文档

支持:
  - YAML/.roomodes 文件加载
  - 运行时模式切换
  - 模式内 AgentConfig 生成
  - 自定义模式注册
"""

from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.modes")


# ── Human Input Mode (借鉴 AutoGen NEVER/TERMINATE/ALWAYS) ─────

class HumanInputMode(str, enum.Enum):
    """
    人工介入级别 (~AutoGen human_input_mode)

    NEVER     — 全自动，不需要人类确认 (适合信任度高的任务)
    TERMINATE — 仅在终止时需要确认 (默认，最实用)
    ALWAYS    — 每一步都需要确认 (最安全，适合高风险操作)
    """
    NEVER = "never"
    TERMINATE = "terminate"
    ALWAYS = "always"


# ── 模式定义 ──────────────────────────────────────────────────

@dataclass
class AgentMode:
    """单个 Agent 模式定义"""
    slug: str                          # 唯一标识，如 "architect"
    name: str                          # 展示名称，如 "🏗️ 架构设计"
    description: str = ""              # 模式描述
    role_instructions: str = ""        # 角色提示词（注入 system prompt）
    tools: list[str] = field(default_factory=list)   # 允许的工具（空=全部）
    tool_categories: list[str] = field(default_factory=list)  # 工具分类
    preferred_model: str = ""          # 推荐模型
    temperature: float = 0.7           # LLM 温度
    max_turns: int = 10                # 最大轮次
    icon: str = "🤖"                   # 图标
    color: str = "#6366f1"             # UI 颜色
    skills: list[str] = field(default_factory=list)  # 🆕 绑定的 Skills
    human_input_mode: HumanInputMode = HumanInputMode.TERMINATE  # 🆕 人工介入级别
    git_auto_commit: bool = True  # 🆕 自动 git commit (借鉴 Aider)
    custom: dict[str, Any] = field(default_factory=dict)  # 自定义扩展

    def to_dict(self) -> dict[str, Any]:
        return {
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
            "tool_categories": self.tool_categories,
            "preferred_model": self.preferred_model,
            "temperature": self.temperature,
            "max_turns": self.max_turns,
            "icon": self.icon,
            "color": self.color,
            "skills": self.skills,
            "human_input_mode": self.human_input_mode.value if isinstance(self.human_input_mode, HumanInputMode) else self.human_input_mode,
            "git_auto_commit": self.git_auto_commit,
        }

    def to_agent_config(self) -> "AgentConfig":
        """从模式生成 AgentConfig"""
        from app.core.agent.agent_config import AgentConfig
        return AgentConfig(
            name=self.slug,
            description=self.description,
            instructions=self.role_instructions,
            tools=list(self.tools),
            tool_categories=list(self.tool_categories),
            preferred_model=self.preferred_model,
            max_turns=self.max_turns,
            human_input_mode=self.human_input_mode,
            git_auto_commit=self.git_auto_commit,
        )


# ── 预设模式 ──────────────────────────────────────────────────

PRESET_MODES: list[AgentMode] = [
    AgentMode(
        slug="architect",
        name="🏗️ 架构设计",
        description="分析和设计系统架构，评审代码结构，产出设计文档",
        role_instructions="""你是一位资深软件架构师。你的职责是：
1. 分析代码结构和系统架构
2. 识别设计模式和架构问题
3. 提出可落地的优化方案
4. 产出清晰的设计文档

工作方式：
- 先理解整体面貌，再深入细节
- 使用 read_file、search_code 等只读工具
- 绘制架构图（用 Mermaid/Markdown）
- 输出结构化的分析报告

注意：你只能使用只读工具，不要直接修改代码。""",
        tools=["read_file", "search_code", "list_dir", "web_search", "search_content"],
        tool_categories=["read", "search"],
        preferred_model="claude-sonnet",
        temperature=0.3,
        max_turns=15,
        icon="🏗️",
        color="#f59e0b",
        skills=["code-review", "explain"],
    ),
    AgentMode(
        slug="code",
        name="💻 编码实现",
        description="编写和修改代码，实现功能需求",
        role_instructions="""你是一位全栈开发工程师。你的职责是：
1. 根据需求编写高质量代码
2. 遵循项目现有的代码规范
3. 修改和优化现有代码
4. 确保代码可运行、可测试

工作方式：
- 先用 read_file 了解现有代码
- 用 str_replace 精确修改文件（不要重写整个文件）
- 修改后验证语法正确性
- 遵循 SOLID 原则和 DRY 原则

重要：修改文件时使用 str_replace 进行精确替换，不要重写整个文件。""",
        tools=["read_file", "write_file", "edit_file", "str_replace", "execute_command",
               "search_code", "search_content", "list_dir", "web_search"],
        tool_categories=["code", "file", "shell"],
        preferred_model="gpt-4o",
        temperature=0.3,
        max_turns=20,
        icon="💻",
        color="#10b981",
        skills=["frontend-design", "refactor"],
        git_auto_commit=True,
    ),
    AgentMode(
        slug="debug",
        name="🪲 问题调试",
        description="定位和修复 bug，分析错误日志，排查运行时问题",
        role_instructions="""你是一位高级调试工程师。你的职责是：
1. 快速定位 bug 根因
2. 分析错误日志和堆栈追踪
3. 提出并验证修复方案
4. 防止同类问题再次出现

工作方式：
- 先用 execute_command 运行诊断命令
- 阅读相关代码定位问题
- 用 grep_search 搜索关键错误信息
- 每次修复后验证

重要：诊断问题优先于直接修改，确保理解根因后再修复。""",
        tools=["read_file", "execute_command", "search_code", "search_content",
               "grep_search", "list_dir", "str_replace", "edit_file"],
        tool_categories=["shell", "search", "code"],
        preferred_model="deepseek-v3",
        temperature=0.2,
        max_turns=25,
        icon="🪲",
        color="#ef4444",
        skills=["debug", "explain"],
        human_input_mode=HumanInputMode.ALWAYS,  # 调试高风险，需确认
    ),
    AgentMode(
        slug="test",
        name="🧪 测试开发",
        description="编写单元测试、集成测试，提升代码覆盖率和质量",
        role_instructions="""你是一位测试开发工程师。你的职责是：
1. 为现有代码编写单元测试
2. 设计集成测试用例
3. 提升测试覆盖率
4. 修复失败的测试

工作方式：
- 先分析被测代码的接口和边界条件
- 使用项目的测试框架编写测试
- 覆盖正常路径、边界值和异常路径
- 运行测试验证通过

注意：不要修改被测代码本身，只编写测试。""",
        tools=["read_file", "write_file", "str_replace", "execute_command",
               "search_code", "list_dir"],
        tool_categories=["code", "file", "shell"],
        preferred_model="gpt-4o",
        temperature=0.2,
        max_turns=15,
        icon="🧪",
        color="#8b5cf6",
        skills=["test-gen", "webapp-testing"],
    ),
    AgentMode(
        slug="review",
        name="📋 代码审查",
        description="审查代码变更，检查代码质量和安全隐患",
        role_instructions="""你是一位代码审查专家。你的职责是：
1. 审查代码变更的正确性和安全性
2. 检查代码风格和最佳实践
3. 发现潜在的性能问题和安全漏洞
4. 提供建设性的改进建议

工作方式：
- 使用 git diff 或 read_file 获取变更内容
- 从多个维度评审：正确性、安全性、性能、可维护性、风格
- 输出结构化的审查报告
- 区分阻塞问题和建议改进

注意：你只能提出建议，不要修改代码。""",
        tools=["read_file", "execute_command", "search_code", "search_content",
               "list_dir", "web_search"],
        tool_categories=["read", "search", "shell"],
        preferred_model="claude-sonnet",
        temperature=0.2,
        max_turns=10,
        icon="📋",
        color="#06b6d4",
        skills=["code-review"],
    ),
    AgentMode(
        slug="docs",
        name="📖 文档编写",
        description="生成和维护项目文档、API 文档、README",
        role_instructions="""你是一位技术文档工程师。你的职责是：
1. 为代码生成清晰的文档
2. 编写和维护 README、API 文档
3. 生成代码注释和 docstring
4. 确保文档准确且易读

工作方式：
- 先阅读需要文档化的代码
- 提取关键接口、参数和返回值
- 使用标准的文档格式（JSDoc/Google Style）
- 生成中文或用户指定的语言

注意：只读取代码，将文档输出到指定文件。""",
        tools=["read_file", "write_file", "search_code", "list_dir", "web_search"],
        tool_categories=["read", "file", "search"],
        preferred_model="gpt-4o",
        temperature=0.5,
        max_turns=12,
        icon="📖",
        color="#d946ef",
        skills=["explain"],
    ),
]


# ── 模式管理器 ────────────────────────────────────────────────

class ModeManager:
    """
    Agent 模式管理器

    用法:
        manager = ModeManager()
        manager.load_presets()        # 加载预设模式
        manager.load_from_file(".roomodes")  # 加载自定义模式

        mode = manager.get("architect")
        config = mode.to_agent_config()
        runner.run(config, "分析这个项目的架构")
    """

    def __init__(self):
        self._modes: dict[str, AgentMode] = {}

    # ── CRUD ──────────────────────────────────────────────

    def register(self, mode: AgentMode) -> None:
        """注册一个模式（覆盖同 slug）"""
        existed = mode.slug in self._modes
        self._modes[mode.slug] = mode
        logger.info(
            "Mode %s: %s (%s tools)",
            "updated" if existed else "registered",
            mode.slug, len(mode.tools),
        )

    def unregister(self, slug: str) -> bool:
        """注销一个模式"""
        if slug in self._modes:
            del self._modes[slug]
            logger.info("Mode unregistered: %s", slug)
            return True
        return False

    def get(self, slug: str) -> AgentMode | None:
        """获取指定模式"""
        return self._modes.get(slug)

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有模式"""
        return [m.to_dict() for m in self._modes.values()]

    @property
    def slugs(self) -> list[str]:
        return list(self._modes.keys())

    @property
    def count(self) -> int:
        return len(self._modes)

    def __contains__(self, slug: str) -> bool:
        return slug in self._modes

    # ── 加载 ──────────────────────────────────────────────

    def load_presets(self) -> int:
        """加载内置预设模式"""
        for mode in PRESET_MODES:
            if mode.slug not in self._modes:
                self._modes[mode.slug] = mode
        logger.info("Loaded %d preset modes", len(PRESET_MODES))
        return len(PRESET_MODES)

    def load_from_file(self, filepath: str | Path) -> int:
        """
        从 .roomodes YAML/JSON 文件加载自定义模式

        支持 YAML 格式:
            modes:
              - slug: my-mode
                name: 我的模式
                tools: [read_file, write_file]
                preferred_model: gpt-4o

        也支持 JSON 格式。
        """
        filepath = Path(filepath)
        if not filepath.exists():
            logger.warning("Modes file not found: %s", filepath)
            return 0

        content = filepath.read_text(encoding="utf-8")
        data = self._parse_modes_file(content, filepath.suffix)

        if not data:
            return 0

        modes_data = data if isinstance(data, list) else data.get("modes", [])
        count = 0
        for item in modes_data:
            try:
                mode = AgentMode(
                    slug=item["slug"],
                    name=item.get("name", item["slug"]),
                    description=item.get("description", ""),
                    role_instructions=item.get("role_instructions", ""),
                    tools=item.get("tools", []),
                    tool_categories=item.get("tool_categories", []),
                    preferred_model=item.get("preferred_model", ""),
                    temperature=item.get("temperature", 0.7),
                    max_turns=item.get("max_turns", 10),
                    icon=item.get("icon", "🤖"),
                    color=item.get("color", "#6366f1"),
                    custom=item.get("custom", {}),
                )
                self.register(mode)
                count += 1
            except Exception as e:
                logger.warning("Failed to parse mode: %s", e)

        logger.info("Loaded %d modes from %s", count, filepath)
        return count

    def _parse_modes_file(self, content: str, suffix: str) -> Any:
        """解析模式文件（支持 JSON/YAML）"""
        import json

        suffix_lower = suffix.lower()
        if suffix_lower in (".json",):
            return json.loads(content)

        # 尝试 YAML
        try:
            import yaml
            return yaml.safe_load(content)
        except ImportError:
            pass

        # 回退：简单的 YAML 解析（处理最常见格式）
        if suffix_lower in (".yaml", ".yml", ""):
            return self._simple_yaml_parse(content)

        return None

    def _simple_yaml_parse(self, content: str) -> Any:
        """极简 YAML 解析（仅处理 .roomodes 格式）"""
        lines = content.strip().split("\n")
        modes: list[dict] = []
        current: dict[str, Any] = {}
        in_modes = False
        in_list_item = False

        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            # 检测 modes: 顶层
            if stripped.startswith("modes:") and not in_modes:
                in_modes = True
                continue

            # 检测列表项
            if in_modes and stripped.startswith("- slug:") or stripped.startswith("-"):
                if current:
                    modes.append(current)
                current = {}
                in_list_item = True
                # 提取 slug
                key_part = stripped.lstrip("- ").strip()
                if ":" in key_part:
                    key, _, val = key_part.partition(":")
                    current[key.strip()] = val.strip().strip("\"'")
                continue

            # 列表项内的键值对
            if in_list_item and ":" in stripped:
                key, _, val = stripped.partition(":")
                key = key.strip()
                val = val.strip().strip("\"'")

                if key == "tools" or key == "tool_categories":
                    # 解析列表
                    val_match = re.search(r"\[(.*?)\]", val)
                    if val_match:
                        current[key] = [
                            item.strip().strip("\"'")
                            for item in val_match.group(1).split(",")
                            if item.strip()
                        ]
                    else:
                        current[key] = []
                elif key in ("temperature", "max_turns"):
                    try:
                        current[key] = float(val) if "." in val else int(val)
                    except ValueError:
                        current[key] = val
                else:
                    current[key] = val

        if current:
            modes.append(current)

        return {"modes": modes}


# ── Codebase Memory 模式 ────────────────────────────────────

@dataclass
class CKGMode(AgentMode):
    """
    代码知识图谱探索模式（已迁移到 CodebaseMemory 工具）

    继承 AgentMode，额外提供代码分析专用的搜索工具。
    工具名已从 ckg_* 更新为 codebase-memory/cbm_* 命名。
    """
    ckg_tools: list[str] = field(default_factory=lambda: [
        "search_graph", "search_code", "get_code_snippet",
        "get_architecture", "trace_path", "index_repository",
        "list_projects", "index_status",
    ])

    def __post_init__(self):
        # 自动合并 CodebaseMemory 专用工具
        all_tools = list(self.tools) + self.ckg_tools
        self.tools = list(dict.fromkeys(all_tools))  # 去重保序


# ── 全局单例 ──────────────────────────────────────────────────

_global_mode_manager: ModeManager | None = None


def init_mode_manager() -> ModeManager:
    """初始化全局模式管理器（启动时调用）"""
    global _global_mode_manager
    _global_mode_manager = ModeManager()
    _global_mode_manager.load_presets()
    logger.info("ModeManager initialized with %d modes", _global_mode_manager.count)
    return _global_mode_manager


def get_mode_manager() -> ModeManager:
    """获取全局模式管理器"""
    global _global_mode_manager
    if _global_mode_manager is None:
        return init_mode_manager()
    return _global_mode_manager
