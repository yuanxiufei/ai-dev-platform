"""
ContextProvider 插件系统 — 分层上下文注入框架

借鉴 Continue core/context/ 的设计：
- ContextProvider: 上下文源抽象基类（name + priority + provide）
- ContextProviderRegistry: 注册中心（优先级排序 + 条件启用 + 自动发现）
- 6 个内置 Provider：SystemInstruction / ToolDescription / Memory / Skill / Project / File

上下文装配流程（替换原有硬编码）：
    AgentRunner.run()
      → registry.get_all(context)  # 按优先级排序
      → for provider in providers:
            text = await provider.provide(config, user_message, ctx)
            parts.append(text)
      → system_prompt = "\n\n".join(parts)

优先级设计：
    0    — SystemInstruction（固定指令，最高）
    10   — Skills（技能注入，比指令具体）
    20   — ToolDescription（工具列表，足够长）
    30   — FileContext（用户 @ 的文件，具体上下文）
    40   — Memory（历史记忆，辅助）
    50   — Project（项目结构，全局）
    100+ — 用户自定义插件（最低）
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger("agent.context_provider")


# ══════════════════════════════════════════════════════════════
# 协议定义
# ══════════════════════════════════════════════════════════════


class ContextProvider(ABC):
    """上下文源的抽象基类

    每个 Provider 负责提供一部分上下文文本，所有 Provider 的输出
    按 priority 排序后拼接成完整的 system prompt。

    使用方式:
        class MyProvider(ContextProvider):
            name = "my-provider"
            priority = 50
            
            async def provide(self, config, user_message, context):
                return "Custom context from MyProvider"
    """

    name: str = ""
    """唯一标识符，用于注册/卸载/条件启用"""

    priority: int = 100
    """注入优先级（越小越靠前），0=最高 100+=用户自定义"""

    enabled: bool = True
    """是否默认启用，可被 context 中的条件覆盖"""

    @abstractmethod
    async def provide(
        self,
        config: Any,           # AgentConfig
        user_message: str,
        context: Any = None,   # AgentRunContext
    ) -> str | None:
        """生成要注入的上下文文本

        Returns:
            要注入的文本片段，返回 None 或 "" 表示跳过
        """
        ...

    def should_enable(self, config: Any) -> bool:
        """运行时决定是否启用（子类可按需覆盖）"""
        return self.enabled

    def __repr__(self) -> str:
        return f"ContextProvider({self.name}, pri={self.priority})"


# ══════════════════════════════════════════════════════════════
# 注册中心
# ══════════════════════════════════════════════════════════════


@dataclass
class ProviderEntry:
    """注册中心中的 Provider 条目"""
    provider: ContextProvider
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class ContextProviderRegistry:
    """上下文 Provider 注册中心

    借鉴 Continue ContextProviderRegistry 设计：
    - 按 priority 排序
    - 支持注册/卸载/条件启用
    - 支持自动发现（从模块路径扫描 ContextProvider 子类）
    """

    def __init__(self):
        self._providers: dict[str, ProviderEntry] = {}
        self._sorted: list[ContextProvider] = []
        self._dirty: bool = True

    # ── CRUD ──

    def register(
        self,
        provider: ContextProvider,
        enabled: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """注册一个 ContextProvider"""
        self._providers[provider.name] = ProviderEntry(
            provider=provider,
            enabled=enabled,
            metadata=metadata or {},
        )
        self._dirty = True
        logger.debug("ContextProvider registered: %s (priority=%d)", provider.name, provider.priority)

    def unregister(self, name: str) -> bool:
        """卸载一个 ContextProvider"""
        if name in self._providers:
            del self._providers[name]
            self._dirty = True
            logger.debug("ContextProvider unregistered: %s", name)
            return True
        return False

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """启用/禁用一个 Provider"""
        if name in self._providers:
            self._providers[name].enabled = enabled
            self._dirty = True
            return True
        return False

    def get(self, name: str) -> ContextProvider | None:
        """获取指定 Provider"""
        entry = self._providers.get(name)
        return entry.provider if entry else None

    def get_all(self, config: Any = None) -> list[ContextProvider]:
        """获取所有已启用、按优先级排序的 Provider 列表"""
        if self._dirty:
            self._resort()
        # 运行时过滤
        # 这里 config 参数预留用于按条件过滤
        _ = config
        return [p for p in self._sorted if self._providers[p.name].enabled and p.should_enable(config)]

    def list_providers(self) -> list[dict[str, Any]]:
        """列出所有已注册 Provider 的元数据"""
        result = []
        for entry in self._providers.values():
            p = entry.provider
            result.append({
                "name": p.name,
                "priority": p.priority,
                "enabled": entry.enabled,
                "metadata": entry.metadata,
            })
        return sorted(result, key=lambda x: x["priority"])

    def clear(self) -> None:
        """清空所有 Provider"""
        self._providers.clear()
        self._sorted = []
        self._dirty = False

    # ── 内部 ──

    def _resort(self) -> None:
        """按 priority 排序（越小越靠前）"""
        self._sorted = sorted(
            [e.provider for e in self._providers.values()],
            key=lambda p: p.priority,
        )
        self._dirty = False


# ══════════════════════════════════════════════════════════════
# 内置 Provider 实现
# ══════════════════════════════════════════════════════════════


class SystemInstructionProvider(ContextProvider):
    """系统指令注入 — 最基础的 Agent 角色定义

    优先级: 0（最高，必须在所有上下文之前）
    """

    name: str = "system-instruction"
    priority: int = 0

    async def provide(self, config, user_message: str, context=None) -> str | None:
        if not config.instructions:
            return None
        return config.instructions


class ToolDescriptionProvider(ContextProvider):
    """工具列表注入 — 告知 Agent 可用的工具

    优先级: 20
    """

    name: str = "tool-description"
    priority: int = 20

    async def provide(self, config, user_message: str, context=None) -> str | None:
        from app.core.tools.registry import get_tool_registry
        registry = get_tool_registry()
        tools = config.get_toolset(registry)

        if not tools:
            return None

        tool_names = [t["function"]["name"] for t in tools]
        tool_descs = [
            f"- `{t['function']['name']}`: {t['function']['description']}"
            for t in tools
        ]
        return (
            "\n## Available Tools\n"
            "You have access to the following tools:\n\n"
            + "\n".join(tool_descs)
            + "\n\nUse these tools when needed. "
            + f"You can call multiple tools in parallel. "
            + "After receiving tool results, use them to formulate your response."
        )


class MemoryContextProvider(ContextProvider):
    """记忆上下文注入 — 从 MemoryStore 检索历史记忆

    优先级: 40（在系统指令和工具列表之后）
    """

    name: str = "memory-context"
    priority: int = 40

    async def provide(self, config, user_message: str, context=None) -> str | None:
        if not getattr(config, "enable_memory", False):
            return None

        try:
            from app.core.memory.memory_retriever import get_retriever
            retriever = get_retriever()
            memory_context = retriever.retrieve_as_context(
                query=user_message,
                max_items=10,
            )
            if memory_context:
                logger.info(
                    "MemoryProvider: injected %d chars of memory context",
                    len(memory_context),
                )
                return f"## Relevant Context from Memory\n{memory_context}"
        except Exception as e:
            logger.warning("Memory retrieval failed (non-blocking): %s", e)
        return None


class SkillContextProvider(ContextProvider):
    """技能指令注入 — 匹配用户输入，注入相关技能指令

    优先级: 10（仅次于系统指令，确保 Agent 获取专业技能指导）

    借鉴 Continue 的 slash command 理念 — 通过用户输入匹配技能并注入上下文。
    """

    name: str = "skill-context"
    priority: int = 10

    async def provide(self, config, user_message: str, context=None) -> str | None:
        try:
            from app.core.skills_manager import SkillsManager
            skills_text = SkillsManager.build_skill_instructions(user_message)
            if skills_text:
                logger.info("SkillProvider: injected skill instructions (%d chars)", len(skills_text))
                return skills_text
        except Exception as e:
            logger.warning("Skill injection failed (non-blocking): %s", e)
        return None


class ProjectContextProvider(ContextProvider):
    """项目上下文注入 — 工作区结构、语言、框架信息

    优先级: 50（在工具和记忆之后，作为全局背景）
    """

    name: str = "project-context"
    priority: int = 50

    def __init__(self, workspace_root: str | None = None):
        self.workspace_root = workspace_root or str(Path.cwd())

    async def provide(self, config, user_message: str, context=None) -> str | None:
        root = Path(self.workspace_root)
        if not root.exists():
            return None

        parts = ["## Project Context"]

        # 项目名称
        parts.append(f"You are working in project: **{root.name}**")

        # 检测关键文件
        key_files = {
            "pyproject.toml": "Python project (pyproject.toml)",
            "package.json": "JavaScript/TypeScript project (package.json)",
            "go.mod": "Go module (go.mod)",
            "Cargo.toml": "Rust project (Cargo.toml)",
            "Makefile": "Uses Make for build",
            "Dockerfile": "Has Docker support",
            "docker-compose.yml": "Uses Docker Compose",
        }
        detected = []
        for fname, desc in key_files.items():
            if (root / fname).exists():
                detected.append(f"- {desc}")
        if detected:
            parts.append("Detected project features:\n" + "\n".join(detected))

        # 目录结构概览（仅顶级）
        top_dirs = []
        top_files = []
        try:
            for item in sorted(root.iterdir()):
                if item.name.startswith(".") or item.name.startswith("__"):
                    continue
                if item.is_dir():
                    top_dirs.append(f"  - {item.name}/")
                else:
                    top_files.append(f"  - {item.name}")
        except PermissionError:
            pass

        if top_dirs:
            parts.append(
                "Top-level directories:\n" + "\n".join(top_dirs[:15])
                + ("\n  ..." if len(top_dirs) > 15 else "")
            )
        if top_files:
            parts.append(
                "Top-level files:\n" + "\n".join(top_files[:10])
                + ("\n  ..." if len(top_files) > 10 else "")
            )

        return "\n".join(parts)


class FileContextProvider(ContextProvider):
    """用户 @mention 文件上下文注入

    优先级: 30（在项目结构之前，因为这是用户明确请求的上下文）

    借鉴 Continue @-mention 设计：
    - 解析 user_message 中的 @file:path 或 @dir:path
    - 读取对应文件/目录内容
    - 注入到上下文中
    """

    name: str = "file-context"
    priority: int = 30
    max_file_size: int = 50000  # 50KB
    max_dir_depth: int = 2

    async def provide(self, config, user_message: str, context=None) -> str | None:
        try:
            from app.core.agent.mention_parser import parse_mentions
        except ImportError:
            return None

        result = parse_mentions(user_message)
        if not result.mentions:
            return None

        parts = ["## Referenced Files/Directories"]
        for mention in result.mentions[:10]:  # 最多10个引用
            path = Path(mention.path)
            if not path.exists():
                parts.append(f"- ⚠️ `{mention.path}`: File not found")
                continue

            if path.is_file():
                try:
                    size = path.stat().st_size
                    if size > self.max_file_size:
                        parts.append(
                            f"- 📄 `{mention.path}` ({size/1024:.0f}KB, too large, only header shown)"
                        )
                        # 只注入前 500 字符作为摘要
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read(500)
                        parts.append(f"\nContent preview:\n```\n{content}\n...\n```")
                    else:
                        with open(path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read()
                        parts.append(f"\nFile: `{mention.path}`\n```\n{content}\n```")
                except Exception as e:
                    parts.append(f"- ❌ `{mention.path}`: Read error ({e})")
            elif path.is_dir():
                files = self._list_dir(path, depth=0)
                parts.append(f"\nDirectory: `{mention.path}`\n```\n" + "\n".join(files) + "\n```")

        if len(parts) <= 1:
            return None
        return "\n".join(parts)

    def _list_dir(self, path: Path, depth: int = 0) -> list[str]:
        """列出目录结构（受深度限制）"""
        if depth > self.max_dir_depth:
            return []
        result = []
        try:
            for item in sorted(path.iterdir())[:50]:
                if item.name.startswith("."):
                    continue
                prefix = "  " * depth
                if item.is_dir():
                    result.append(f"{prefix}📁 {item.name}/")
                    result.extend(self._list_dir(item, depth + 1))
                else:
                    result.append(f"{prefix}📄 {item.name}")
        except PermissionError:
            pass
        return result


class MCPContextProvider(ContextProvider):
    """MCP 服务器上下文注入 — 列出可用的 MCP 资源和工具

    优先级: 60（最低，作为可选资源）
    """

    name: str = "mcp-context"
    priority: int = 60

    async def provide(self, config, user_message: str, context=None) -> str | None:
        try:
            from app.core.mcp import get_mcp_manager
            manager = get_mcp_manager()
            servers = manager.list_servers()
        except (ImportError, AttributeError):
            return None

        active_servers = [s for s in servers if getattr(s, "connected", False)]
        if not active_servers:
            return None

        parts = ["## Available MCP Servers"]
        for srv in active_servers[:5]:
            parts.append(
                f"- **{getattr(srv, 'name', 'unknown')}**: "
                f"{getattr(srv, 'tools_count', 0)} tools, "
                f"{getattr(srv, 'resources_count', 0)} resources"
            )
        parts.append("\nUse MCP tools just like regular tools.")
        return "\n".join(parts)


# ══════════════════════════════════════════════════════════════
# 全局单例 + 初始化
# ══════════════════════════════════════════════════════════════

_registry: ContextProviderRegistry | None = None


def get_context_provider_registry() -> ContextProviderRegistry:
    """获取全局 ContextProvider 注册中心（延迟创建）"""
    global _registry
    if _registry is None:
        _registry = ContextProviderRegistry()
        _register_builtins(_registry)
    return _registry


def init_context_provider_registry(
    workspace_root: str | None = None,
) -> ContextProviderRegistry:
    """初始化全局注册中心（应用启动时调用）"""
    global _registry
    _registry = ContextProviderRegistry()
    _register_builtins(_registry, workspace_root=workspace_root)
    logger.info(
        "ContextProviderRegistry initialized: %d providers",
        len(_registry.list_providers()),
    )
    return _registry


def _register_builtins(
    registry: ContextProviderRegistry,
    workspace_root: str | None = None,
) -> None:
    """注册所有内置 Provider"""
    registry.register(SystemInstructionProvider())

    # Skill 需要先加载技能文件
    try:
        from app.core.skills_manager import init_skills
        init_skills("skills")
    except Exception:
        pass
    registry.register(SkillContextProvider())

    registry.register(ToolDescriptionProvider())

    registry.register(FileContextProvider())

    # RelatedFiles（多文件关系感知，借鉴 Zed multi-buffer）
    try:
        from app.core.agent.related_files import init_related_files_provider
        rfp = init_related_files_provider(workspace_root)
        registry.register(rfp)
    except Exception as e:
        logger.debug("RelatedFilesProvider registration skipped: %s", e)

    # Memory 需要 memory store 初始化
    registry.register(MemoryContextProvider())

    registry.register(ProjectContextProvider(
        workspace_root=workspace_root or str(Path.cwd()),
    ))

    # MCP 是可选依赖
    registry.register(MCPContextProvider())
    registry.set_enabled("mcp-context", False)  # 默认禁用

    logger.debug("Registered %d built-in ContextProviders", len(registry.list_providers()))
