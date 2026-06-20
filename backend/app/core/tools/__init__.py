"""
工具抽象层 — 借鉴 AstrBot ToolSet/FunctionTool 体系

提供：
- ToolSchema: 工具参数定义（可转 OpenAI/Anthropic 格式）
- FunctionTool: 可调用工具包装器
- ToolSet: 工具集合 + 多格式 schema 导出
- ToolRegistry: 全局工具注册中心 + 自动发现
- BuiltinTool: 内置工具 + 装饰器 + 配置条件规则
- ToolImageCache: 工具调用图片缓存管理
- KnowledgeBaseQueryTool: 知识库搜索工具
- WebSearchTool: 多引擎 Web 搜索 (Tavily/Brave/Firecrawl/百度)
- WebExtractTool: 网页内容提取工具
- IDE Tools: codebase_search / file_operation / terminal_exec
- CodeCompletion: FIM 代码补全引擎 (ContextAssembler + FIMCompletionEngine + CompletionRanker + Cache)
"""

from app.core.tools.schema import FunctionTool, ToolParam, ToolSchema, ToolSet, ToolResult, tool  # noqa: F401
from app.core.tools.registry import ToolRegistry, get_tool_registry, register_tool  # noqa: F401
from app.core.tools.builtin_tool import (  # noqa: F401
    BuiltinTool, builtin_tool, BuiltinToolConfigRule, BuiltinToolConfigCondition,
    register_config_rule, get_config_rule, evaluate_all_tools,
)
from app.core.tools.image_cache import (  # noqa: F401
    CachedImage, ToolImageCache, get_tool_image_cache,
)
from app.core.tools.kb_tools import (  # noqa: F401
    KnowledgeBaseQueryTool, KnowledgeBaseInfoTool,
)
from app.core.tools.web_search import (  # noqa: F401
    WebSearchTool, WebFetchTool, register_web_tools,
)
from app.core.tools.code_completion import (  # noqa: F401
    FIMCompletionEngine, ContextAssembler, CompletionRanker, CompletionCache,
    CursorContext, CompletionItem, CompletionResult, CompletionTrigger,
    get_completion_engine, init_completion_engine,
    register_code_completion_tools,
)
