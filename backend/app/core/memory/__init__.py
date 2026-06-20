"""
Memory 核心层 — 借鉴 Open WebUI Memory + DeerFlow long-term memory

长期向量化记忆系统：
- MemoryStore: CRUD + 语义检索 + 域管理
- EmbeddingService: 多 Provider embedding 生成
- MemoryTools: Agent 可调用工具（save_memory / recall_memory）

与 DeerFlow 的对齐：
- DeerFlow 使用 JSON + LLM 更新记忆，我们扩展到向量 + LLM 双路径
- 支持域分类（project/task/domain_knowledge/user_preference）
- embedding 生成支持多种 Provider（本地模型 / OpenAI / 兼容接口）
"""

from app.core.memory.store import (  # noqa: F401
    MemoryStore, MemoryRecord, MemorySearchResult,
    get_memory_store, init_memory_store,
)
from app.core.memory.embedding import (  # noqa: F401
    EmbeddingService, EmbeddingProvider,
    OpenAIEmbeddingProvider,
    get_embedding_service, init_embedding_service,
)
