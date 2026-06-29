"""
工具优先级排序系统 — 借鉴 hermes-agent 的工具优先级设计

将工具按使用场景分为高/中/低三个优先级：
- HIGH: 上下文理解工具（理解代码库、搜索定义）
- MEDIUM: 代码探索工具（读取文件、浏览目录）
- LOW: 修改操作工具（执行命令、修改文件）

Agent 应在使用 LOW 优先级工具前，先通过 HIGH/MEDIUM 工具收集足够上下文。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class ToolPriorityLevel(IntEnum):
    """工具优先级"""
    HIGH = 0     # 上下文理解 — 先于一切
    MEDIUM = 1   # 代码探索 — 理解足够后使用
    LOW = 2      # 修改操作 — 最后执行


@dataclass
class ToolPriority:
    """单个工具的优先级配置"""
    tool_name: str
    priority: ToolPriorityLevel
    prerequisite_tools: list[str] = field(default_factory=list)
    """执行前建议先调用的工具"""
    description: str = ""


# ── 预设的工具优先级表 ────────────────────────────

PRESET_PRIORITIES: dict[str, ToolPriority] = {
    # HIGH — 上下文理解
    "search_graph": ToolPriority(
        "search_graph", ToolPriorityLevel.HIGH,
        description="Search code structure to understand the codebase",
    ),
    "get_code_snippet": ToolPriority(
        "get_code_snippet", ToolPriorityLevel.HIGH,
        prerequisite_tools=["search_graph"],
        description="Read source code after finding the symbol",
    ),
    "get_architecture": ToolPriority(
        "get_architecture", ToolPriorityLevel.HIGH,
        description="Get project architecture overview",
    ),
    "list_projects": ToolPriority(
        "list_projects", ToolPriorityLevel.HIGH,
        description="List indexed projects",
    ),
    "index_repository": ToolPriority(
        "index_repository", ToolPriorityLevel.HIGH,
        description="Index a repository for search",
    ),

    # MEDIUM — 代码探索
    "search_code": ToolPriority(
        "search_code", ToolPriorityLevel.MEDIUM,
        prerequisite_tools=["search_graph"],
        description="Grep-like search in indexed files",
    ),
    "trace_path": ToolPriority(
        "trace_path", ToolPriorityLevel.MEDIUM,
        prerequisite_tools=["search_graph"],
        description="Trace call paths through the code",
    ),
    "read_file": ToolPriority(
        "read_file", ToolPriorityLevel.MEDIUM,
        description="Read a specific file",
    ),
    "list_directory": ToolPriority(
        "list_directory", ToolPriorityLevel.MEDIUM,
        description="List files in a directory",
    ),
    "get_graph_schema": ToolPriority(
        "get_graph_schema", ToolPriorityLevel.MEDIUM,
        description="Get knowledge graph schema",
    ),

    # LOW — 修改操作
    "write_file": ToolPriority(
        "write_file", ToolPriorityLevel.LOW,
        prerequisite_tools=["read_file"],
        description="Write content to a file",
    ),
    "execute_command": ToolPriority(
        "execute_command", ToolPriorityLevel.LOW,
        description="Execute a shell command",
    ),
    "delete_file": ToolPriority(
        "delete_file", ToolPriorityLevel.LOW,
        prerequisite_tools=["read_file"],
        description="Delete a file or directory",
    ),
    "replace_in_file": ToolPriority(
        "replace_in_file", ToolPriorityLevel.LOW,
        prerequisite_tools=["read_file"],
        description="Replace text in a file",
    ),
    "run_test": ToolPriority(
        "run_test", ToolPriorityLevel.LOW,
        prerequisite_tools=["write_file"],
        description="Run tests",
    ),
    "git_commit": ToolPriority(
        "git_commit", ToolPriorityLevel.LOW,
        prerequisite_tools=["write_file"],
        description="Commit changes to git",
    ),
}


class PrioritizedToolSet:
    """
    优先级排序的工具集

    用法:
        pts = PrioritizedToolSet()
        ordered = pts.order_tools(["search_graph", "write_file", "read_file"])
        # → ["search_graph", "read_file", "write_file"]
    """

    def __init__(self, custom_priorities: dict[str, ToolPriority] | None = None):
        self._priorities = dict(PRESET_PRIORITIES)
        if custom_priorities:
            self._priorities.update(custom_priorities)

    def get_priority(self, tool_name: str) -> ToolPriorityLevel:
        """获取工具的优先级"""
        entry = self._priorities.get(tool_name)
        if entry:
            return entry.priority
        # 回退：根据工具名推断
        if any(kw in tool_name.lower() for kw in ["search", "get_", "index", "list"]):
            return ToolPriorityLevel.HIGH
        if any(kw in tool_name.lower() for kw in ["read", "trace", "query"]):
            return ToolPriorityLevel.MEDIUM
        return ToolPriorityLevel.LOW

    def order_tools(self, tool_names: list[str]) -> list[str]:
        """按优先级排序工具列表"""
        return sorted(tool_names, key=lambda n: self.get_priority(n).value)

    def get_prerequisites(self, tool_name: str) -> list[str]:
        """获取建议的 prerequisite 工具"""
        entry = self._priorities.get(tool_name)
        return entry.prerequisite_tools if entry else []

    def get_recommended_before(self, target_tools: list[str]) -> list[str]:
        """
        给定一批目标工具，返回建议先执行的工具列表

        Example:
            get_recommended_before(["write_file", "execute_command"])
            → ["search_graph", "read_file", "search_code"]
        """
        recommended: set[str] = set()
        for name in target_tools:
            for prereq in self.get_prerequisites(name):
                recommended.add(prereq)
                # 递归获取前置的前置
                for pre_prereq in self.get_prerequisites(prereq):
                    recommended.add(pre_prereq)
        return sorted(recommended, key=lambda n: self.get_priority(n).value)

    def generate_agent_guidance(self) -> str:
        """生成 Agent 工具使用指导（注入到 system prompt）"""
        lines = [
            "## Tool Usage Priority Guidelines",
            "",
            "Use tools in this order to minimize unnecessary changes:",
            "",
            "### 1. Understand First (HIGH priority)",
            "Before making any changes, understand the codebase:",
        ]
        high_tools = [
            n for n, p in self._priorities.items()
            if p.priority == ToolPriorityLevel.HIGH
        ]
        for tool in high_tools[:6]:
            lines.append(f"- `{tool}`: {self._priorities[tool].description}")

        lines.extend([
            "",
            "### 2. Explore (MEDIUM priority)",
            "After understanding the context, explore specific areas:",
        ])
        medium_tools = [
            n for n, p in self._priorities.items()
            if p.priority == ToolPriorityLevel.MEDIUM
        ]
        for tool in medium_tools[:6]:
            lines.append(f"- `{tool}`: {self._priorities[tool].description}")

        lines.extend([
            "",
            "### 3. Modify (LOW priority)",
            "Only after understanding and exploring, make changes:",
        ])
        low_tools = [
            n for n, p in self._priorities.items()
            if p.priority == ToolPriorityLevel.LOW
        ]
        for tool in low_tools[:6]:
            lines.append(f"- `{tool}`: {self._priorities[tool].description}")

        return "\n".join(lines)


# ── 全局单例 ──────────────────────────────────────

_global_toolset: PrioritizedToolSet | None = None


def get_prioritized_toolset() -> PrioritizedToolSet:
    """获取全局优先级工具集"""
    global _global_toolset
    if _global_toolset is None:
        _global_toolset = PrioritizedToolSet()
    return _global_toolset
