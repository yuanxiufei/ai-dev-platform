"""
RAG 系统演示 — 完整混合检索流程

用法:
    cd backend
    python -m app.core.rag.demo

流程：
    1. 创建知识库
    2. 上传文档 (txt/md/pdf/url)
    3. 混合检索查询 (Dense + Sparse → RRF → Rerank)
    4. RAG 生成回答
"""

import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("app.core.rag.demo")


async def main():
    from app.core.rag.knowledge_base import init_knowledge_base, get_knowledge_base
    from app.core.rag.rag_pipeline import RAGPipeline

    # 1. 初始化
    kb_mgr = init_knowledge_base()
    logger.info("Knowledge base manager initialized")

    # 2. 创建知识库
    kb = await kb_mgr.create(
        name="demo_kb",
        description="演示知识库 — 混合检索测试",
        chunk_strategy="recursive",
        chunk_size=512,
        chunk_overlap=100,
    )

    # 3. 上传点示例文本
    sample_texts = [
        {
            "title": "Python 介绍",
            "text": (
                "Python 是一种解释型、面向对象的高级编程语言。"
                "它具有简洁的语法和强大的功能，广泛应用于 Web 开发、数据科学、人工智能等领域。"
                "Python 的设计哲学强调代码的可读性和简洁性。\n\n"
                "FastAPI 是一个基于 Python 的现代 Web 框架，用于构建高性能的 RESTful API。"
                "它支持异步处理和自动生成 OpenAPI 文档。"
            ),
        },
        {
            "title": "React 基础",
            "text": (
                "React 是由 Facebook 开发的前端 JavaScript 库，用于构建用户界面。"
                "它采用组件化架构，通过虚拟 DOM 实现高效的页面渲染。\n\n"
                "React Hooks 是 React 16.8 引入的新特性，允许在函数组件中使用状态和其他 React 特性。"
                "常用的 Hooks 包括 useState、useEffect、useContext 等。"
            ),
        },
        {
            "title": "RAG 概念",
            "text": (
                "RAG（Retrieval-Augmented Generation）是一种结合信息检索和文本生成的 AI 技术。"
                "它先通过检索系统从知识库中找到相关文档片段，再交给大语言模型生成准确的回答。\n\n"
                "混合检索（Hybrid Search）结合了稠密向量检索和稀疏关键词检索两种方式的优势。"
                "稠密检索擅长语义匹配，稀疏检索擅长精确关键词匹配，"
                "通过 RRF（Reciprocal Rank Fusion）算法融合两者结果，可以显著提升召回率和准确率。"
            ),
        },
    ]

    for sample in sample_texts:
        count = await kb_mgr.upload_text(
            kb,
            text=sample["text"],
            title=sample["title"],
        )
        logger.info("Uploaded '%s': %d chunks", sample["title"], count)

    logger.info("KB stats: %s", kb.stats)

    # 4. 混合检索测试
    pipeline = RAGPipeline()

    queries = [
        "Python 和 React 分别是什么？",
        "什么是 RAG 技术？",
        "FastAPI 有什么特点？",
    ]

    for query in queries:
        logger.info("\n" + "=" * 60)
        logger.info("Query: %s", query)

        result = await pipeline.query(query, kb_or_ids=kb, top_k=3)

        logger.info("Answer: %s", result["answer"][:200])
        if result["sources"]:
            logger.info("Sources:")
            for s in result["sources"]:
                logger.info("  - %s (score=%.3f)", s["source"], s["score"])


if __name__ == "__main__":
    asyncio.run(main())
