"""
RAG — 检索增强生成系统

借鉴 AstrBot 架构精华：
- 混合检索: Dense (FAISS) + Sparse (FTS5/BM25) → RRF 融合 → CrossEncoder Rerank
- 上下文压缩: 去重 + Token 感知裁剪 (3 种策略: truncate/head/hybrid)
- 多格式解析: txt / md / pdf / docx / xls / epub / url
- 插件式 Embedding: OpenAI / Ollama / 本地 BGE / 百炼
- 多知识库管理: 每 KB 独立索引 + FTS5
- 代码感知分块: Python AST + 通用多语言 + Markdown 结构
- SQLite 持久化: KB 元数据 + 文档追踪 + 多媒体管理
- LLM 文本修复: 噪音清洗 + 多主题拆分
- URL 导入: Tavily + 直接 HTTP 回退

Pipeline:
  Upload → Parse → Clean(LLM) → Chunk → Embed → [FAISS + FTS5] → KB Ready
  Query  → Dense + Sparse → RRF → Rerank → Compress → Generate
"""

__version__ = "3.0.0"
