"""
Memory 核心层 — 借鉴 Open WebUI Memory + DeerFlow long-term memory + cognee Knowledge Graph

长期记忆系统：
- MemoryStore: CRUD + 语义检索 + 域管理
- EmbeddingService: 多 Provider embedding 生成
- MemoryTools: Agent 可调用工具（save_memory / recall_memory）
- MemoryStore (新的长期记忆图): MemoryNode + MemoryEdge + SQLite 存储
- MemoryExtractor: 从对话/代码/反思中提取结构化记忆
- MemoryRetriever: 关键词 + 图遍历综合检索

双层记忆架构：
- 层1: 向量记忆 (store.py) — 快速语义搜索
- 层2: 图记忆 (memory_store.py) — 实体关系图谱 + 长期持久化
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

# 新的长期记忆图系统
from app.core.memory.memory_store import (  # noqa: F401
    MemoryNode, MemoryEdge, MemoryType, RelationType,
)
from app.core.memory.memory_extractor import (  # noqa: F401
    MemoryExtractor, extract_and_save,
)
from app.core.memory.memory_retriever import (  # noqa: F401
    MemoryRetriever, init_retriever, get_retriever,
)
