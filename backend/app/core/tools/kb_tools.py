"""
知识库工具 — 将 KB 暴露为 LLM 工具

借鉴 AstrBot knowledge_base_tools.py:
- KnowledgeBaseQueryTool: 搜索知识库, 支持会话级/全局配置
- KnowledgeBaseInfoTool: 查询 KB 状态
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("app.core.tools.kb_tools")

try:
    from app.core.tools.builtin_tool import builtin_tool, BuiltinTool
except ImportError:
    # Fallback: 如果 builtin_tool 未导入，定义一个简单的装饰器
    def builtin_tool(config=None):
        return lambda cls: cls

    class BuiltinTool:
        pass


_KB_TOOL_CONFIG = {
    "kb_agentic_mode": True,
}


async def _get_kb_context(query: str, kb_names: Optional[list[str]] = None) -> str | None:
    """检索知识库上下文"""
    try:
        from app.core.rag.kb_manager import get_kb_manager_v2
    except ImportError:
        logger.warning("KB manager not available")
        return None

    mgr = get_kb_manager_v2()
    if not mgr._instances:
        return None

    # 如果指定了 kb_names，使用指定；否则使用全部
    if not kb_names:
        # 默认使用所有非空 KB
        kb_names = [
            inst.name for inst in mgr._instances.values()
            if inst.storage and inst.storage.count() > 0
        ]
        if not kb_names:
            return None

    result = await mgr.retrieve(
        query=query,
        kb_names=kb_names,
        top_m_final=5,
    )
    context_text = result.get("context_text", "")
    if context_text:
        logger.debug("KB context for query: %d chars", len(context_text))
    return context_text or None


@builtin_tool(config=_KB_TOOL_CONFIG)
@dataclass
class KnowledgeBaseQueryTool(BuiltinTool):
    """知识库搜索工具 — LLM 可调用的知识检索"""

    name: str = "knowledge_base_search"
    description: str = (
        "Search the knowledge base for facts, context, or reference material. "
        "Use this when the user asks about specific topics that may be in indexed documents. "
        "Provide a concise keyword query."
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A concise keyword query to search the knowledge base.",
            },
            "kb_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of knowledge base names to search. If empty, search all.",
            },
        },
        "required": ["query"],
    })

    async def __call__(self, **kwargs) -> str:
        query = kwargs.get("query", "")
        kb_names = kwargs.get("kb_names", None)

        if not query:
            return "Error: query parameter is required."

        context = await _get_kb_context(query, kb_names)
        if not context:
            return "No relevant knowledge found in the knowledge base."

        return context


@builtin_tool(config=_KB_TOOL_CONFIG)
@dataclass
class KnowledgeBaseInfoTool(BuiltinTool):
    """知识库信息工具 — 查询 KB 元信息"""

    name: str = "knowledge_base_info"
    description: str = (
        "Get information about available knowledge bases, including names, "
        "document counts, and descriptions."
    )
    parameters: dict = field(default_factory=lambda: {
        "type": "object",
        "properties": {},
    })

    async def __call__(self, **kwargs) -> str:
        try:
            from app.core.rag.kb_manager import get_kb_manager_v2
            mgr = get_kb_manager_v2()
        except ImportError:
            return "Knowledge base system is not available."

        instances = mgr._instances
        if not instances:
            return "No knowledge bases configured."

        lines = ["## Available Knowledge Bases\n"]
        for inst in instances.values():
            name = inst.model.kb_name
            desc = inst.model.description or "(no description)"
            docs = inst.model.doc_count
            chunks = inst.model.chunk_count
            lines.append(f"- **{name}**: {desc} ({docs} docs, {chunks} chunks)")

        return "\n".join(lines)
