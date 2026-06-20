"""
RAG Pipeline — 完整检索增强生成闭环

借鉴 AstrBot Agent 工具思想:
  Query → Retrieve (混合检索+Rerank) → Compress (去重+截断) → Format → LLM Generate → Answer

支持:
  - 独立知识库查询
  - 多知识库联合查询
  - 上下文自动压缩 (Token 感知)
  - 引用来源标注
"""

from __future__ import annotations

import logging
from typing import Optional

from app.core.rag.config import get_rag_config
from app.core.rag.context_compressor import get_compressor, CompressConfig, CompressStrategy, ContextCompressor
from app.core.rag.knowledge_base import get_knowledge_base, KnowledgeBase

logger = logging.getLogger("app.core.rag.pipeline")


# ── Prompt 模板 ──────────────────────────────────────────

RAG_SYSTEM_PROMPT = """你是一个基于知识库的专业助手。请根据提供的参考知识回答问题。

规则：
1. 优先使用参考知识中的信息回答
2. 如果知识库中找不到答案，诚实告知而不是编造
3. 引用具体知识来源（"根据【知识 N】..."）
4. 回答简洁专业，避免冗余

参考知识：
{context}"""


# ── RAG Pipeline ─────────────────────────────────────────

class RAGPipeline:
    """RAG 完整流水线 —— 检索 → 压缩 → 生成"""

    def __init__(self, max_context_tokens: int = 3000):
        self._config = get_rag_config()
        self._kb_manager = get_knowledge_base()
        self._compressor: ContextCompressor = get_compressor(
            CompressConfig(
                max_tokens=max_context_tokens,
                strategy=CompressStrategy.HYBRID,
            )
        )
        self._llm = None  # 延迟加载

    async def query(
        self,
        question: str,
        kb_or_ids: KnowledgeBase | list[str] | None = None,
        top_k: int = 5,
        include_sources: bool = True,
        max_context_tokens: int = 3000,
    ) -> dict:
        """
        执行 RAG 查询

        全流程:
          1. 检索（通过 KnowledgeBaseManager → RetrievalManager）
             └ 内部: Dense + Sparse → RRF → Rerank
          2. 上下文压缩（去重 + Token 感知裁剪）
          3. LLM 生成回答
          4. 提取引用来源

        Args:
            question: 用户问题
            kb_or_ids: 知识库实例或 ID 列表（None = 所有）
            top_k: 检索返回数
            include_sources: 是否包含引用来源
            max_context_tokens: 上下文最大 token 数

        Returns:
            {
                "answer": str,
                "sources": [...],
                "context": str,
                "query": str,
                "compressed": bool,       # 是否被压缩
                "original_chunks": int,    # 原始 chunk 数
                "final_chunks": int,       # 压缩后 chunk 数
            }
        """
        # ── 1. 检索（内部含 Rerank） ──
        if isinstance(kb_or_ids, KnowledgeBase):
            results = await self._kb_manager.query(kb_or_ids, question, top_k)
        elif isinstance(kb_or_ids, list):
            results = await self._kb_manager.query_multi(kb_or_ids, question, top_k)
        else:
            all_kbs = self._kb_manager.list_all()
            kb_ids = [kb.kb_id for kb in all_kbs]
            if not kb_ids:
                return {
                    "answer": "没有可用的知识库",
                    "sources": [], "context": "", "query": question,
                    "compressed": False, "original_chunks": 0, "final_chunks": 0,
                }
            results = await self._kb_manager.query_multi(kb_ids, question, top_k)

        if not results:
            return {
                "answer": "未找到相关内容",
                "sources": [], "context": "", "query": question,
                "compressed": False, "original_chunks": 0, "final_chunks": 0,
            }

        original_chunks = len(results)

        # ── 2. 上下文压缩 ──
        # 如果指定了不同的 token 上限，临时调整
        if max_context_tokens != self._compressor._config.max_tokens:
            self._compressor._config.max_tokens = max_context_tokens

        compressed_results, context = self._compressor.compress(results)

        compressed = len(compressed_results) < original_chunks or any(
            "original_length" in r for r in compressed_results
        )

        if compressed:
            logger.info(
                "Context compressed: %d → %d chunks, %d tokens",
                original_chunks, len(compressed_results),
                self._compressor.estimate_tokens(compressed_results),
            )

        # ── 3. 生成回答 ──
        answer = await self._generate(question, context)

        # ── 4. 构建来源 ──
        sources = []
        if include_sources:
            seen = set()
            for r in compressed_results:
                src = r.get("metadata", {}).get("source", r.get("kb_name", ""))
                if src and src not in seen:
                    seen.add(src)
                    sources.append({
                        "source": src,
                        "score": r.get("rerank_score", r.get("rrf_score", r.get("score", 0))),
                        "content_preview": (
                            r["content"][:200] + "…"
                            if len(r["content"]) > 200 else r["content"]
                        ),
                        "truncated": "original_length" in r,
                    })

        return {
            "answer": answer,
            "sources": sources,
            "context": context,
            "query": question,
            "compressed": compressed,
            "original_chunks": original_chunks,
            "final_chunks": len(compressed_results),
        }

    async def _generate(self, question: str, context: str) -> str:
        """调用 LLM 生成回答"""
        prompt = RAG_SYSTEM_PROMPT.format(context=context)

        # 尝试通过项目内部的 LLM 引擎
        try:
            return await self._generate_via_llm(prompt, question)
        except Exception as e:
            logger.warning("LLM generation failed: %s", e)
            # 回退：直接返回上下文
            return f"基于知识库内容（共 {context.count('【知识')} 条）：\n\n{context[:3000]}"

    async def _generate_via_llm(self, system_prompt: str, question: str) -> str:
        """通过 LLM 引擎生成"""
        # 尝试本地 GGUF
        try:
            from app.core.rag.llm_engine import LLMEngine
            engine = LLMEngine()
            return await engine.generate(system_prompt, question)
        except ImportError:
            pass

        # 尝试 OpenAI API
        try:
            import os
            api_key = os.getenv("OPENAI_API_KEY", "")
            if api_key:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=api_key)
                resp = await client.chat.completions.create(
                    model=self._config.llm_model if self._config.llm_provider == "openai" else "gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question},
                    ],
                    temperature=self._config.llm_temperature,
                    max_tokens=self._config.llm_max_tokens,
                )
                return resp.choices[0].message.content or ""
        except Exception:
            pass

        raise RuntimeError("No LLM available")


# ── 快速 API ─────────────────────────────────────────────

async def rag_query(
    question: str,
    kb_ids: Optional[list[str]] = None,
    top_k: int = 5,
) -> dict:
    """RAG 快速查询入口"""
    pipeline = RAGPipeline()
    return await pipeline.query(question, kb_or_ids=kb_ids, top_k=top_k)


async def rag_search(
    query: str,
    kb_ids: Optional[list[str]] = None,
    top_k: int = 5,
) -> list[dict]:
    """
    纯检索接口（不生成回答）
    作为 Agent Tool 使用
    """
    mgr = get_knowledge_base()

    if kb_ids:
        return await mgr.query_multi(kb_ids, query, top_k)

    all_kbs = mgr.list_all()
    if not all_kbs:
        return []
    return await mgr.query_multi([kb.kb_id for kb in all_kbs], query, top_k)
