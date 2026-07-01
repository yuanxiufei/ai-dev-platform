"""
事件-实体提取模块

借鉴 SAG src/ingestion/extract/extractor.ts:
  1. EventExtractor: 从文本切片中提取结构化事件 (title, summary, entities)
  2. EntityExtractor: 从事件中提取并归一化命名实体

支持:
  - LLM 提取 (OpenAI Function Calling / JSON mode)
  - 本地规则提取 (正则 + NER 回退)
  - 批量模式 (减少 API 调用)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger("app.core.rag.extraction")


# ── 事件提取提示词 ──────────────────────────────────────────

EVENT_EXTRACTION_PROMPT = """从以下文本片段中提取结构化事件。

对每个事件提供:
1. title: 简洁的标题 (≤50字)
2. summary: 一段话概述 (≤200字)  
3. entities: 事件涉及的关键实体列表

实体类型: person(人物), org(组织), concept(概念), technology(技术), 
         location(地点), event(事件), product(产品), other(其他)

输出严格 JSON 格式:
{
  "title": "...",
  "summary": "...",
  "entities": [
    {"name": "...", "type": "concept"},
    {"name": "...", "type": "person"}
  ]
}

文本:
{text}"""


ENTITY_EXTRACTION_PROMPT = """从以下查询中提取关键命名实体。
返回 JSON 数组，每个元素包含 name 和 type:
[{"name": "实体名", "type": "person|org|concept|technology|location|product"}, ...]

查询:
{query}"""


async def _default_llm_call(prompt: str) -> str:
    """默认 LLM 调用封装（异步）"""
    import os
    api_key = os.getenv("OPENAI_API_KEY", "")
    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    if not api_key:
        raise RuntimeError("No OPENAI_API_KEY configured")

    import httpx
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{api_base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个信息提取助手。只输出 JSON，不要有其他文字。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )
    data = resp.json()
    return data["choices"][0]["message"]["content"]


class EventExtractor:
    """
    事件提取器

    从文本切片中提取结构化事件:
      - title: 事件标题
      - summary: 事件概述
      - entities: 涉及的命名实体列表

    用法:
        extractor = EventExtractor(llm_fn=my_llm_call)
        event = await extractor.extract("Redis 使用 AOF 持久化机制...")
        # {"title": "Redis AOF 持久化", "summary": "...", "entities": [...]}
    """

    def __init__(self, llm_fn: Optional[callable] = None, model: str = "gpt-4o-mini"):
        self._llm = llm_fn or _default_llm_call
        self._model = model

    async def extract(self, text: str) -> Optional[dict[str, Any]]:
        """从文本提取单个事件"""
        if not text or len(text.strip()) < 10:
            return None

        prompt = EVENT_EXTRACTION_PROMPT.format(text=text[:3000])
        try:
            raw = await await_if_coroutine(self._llm(prompt))
            result = json.loads(raw) if isinstance(raw, str) else raw
            return result if result.get("title") else None
        except Exception as e:
            logger.warning("EventExtractor failed: %s", e)
            return None

    async def extract_batch(self, texts: list[str], max_concurrency: int = 5) -> list[Optional[dict]]:
        """批量提取事件"""
        import asyncio
        sem = asyncio.Semaphore(max_concurrency)

        async def _extract_one(t):
            async with sem:
                return await self.extract(t)

        return await asyncio.gather(*[_extract_one(t) for t in texts])


class EntityExtractor:
    """
    查询实体提取器

    从用户查询中提取关键命名实体，用于 GraphRAG 多跳检索的入口。

    用法:
        extractor = EntityExtractor(llm_fn=my_llm_call)
        entities = await extractor.extract("如何优化 PostgreSQL 查询性能?")
        # ["PostgreSQL", "查询性能"]
    """

    def __init__(self, llm_fn: Optional[callable] = None):
        self._llm = llm_fn or _default_llm_call

    async def extract(self, query: str) -> list[str]:
        """从查询提取实体名称列表"""
        if not query.strip():
            return []

        prompt = ENTITY_EXTRACTION_PROMPT.format(query=query)
        try:
            raw = await await_if_coroutine(self._llm(prompt))
            entities = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(entities, list):
                return [e["name"] if isinstance(e, dict) else str(e)
                        for e in entities if e]
            return []
        except Exception as e:
            logger.warning("EntityExtractor failed: %s", e)
            # 回退: 简单分词
            return self._fallback_extract(query)

    def _fallback_extract(self, query: str) -> list[str]:
        """本地回退: 用正则提取大写词汇和专有名词"""
        # 提取大写开头的连续词 (英文专名)
        en_pattern = r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b'
        en_matches = re.findall(en_pattern, query)

        # 提取中文 2-4 字有意义的词 (简单启发式)
        cn_pattern = r'[\u4e00-\u9fff]{2,4}'
        cn_matches = re.findall(cn_pattern, query)

        # 过滤常见停用词
        stopwords = {"如何", "怎么", "为什么", "什么", "哪些", "是否", "可以", "应该", "需要"}
        filtered = [w for w in en_matches + cn_matches
                    if w.lower() not in stopwords]

        # 去重，限制数量
        seen = set()
        result = []
        for w in filtered:
            if w.lower() not in seen:
                seen.add(w.lower())
                result.append(w)
                if len(result) >= 10:
                    break
        return result


# ── 辅助 ────────────────────────────────────────────────────

async def await_if_coroutine(result):
    """统一处理同步和异步调用：若是协程则 await，否则直接返回"""
    import asyncio
    if asyncio.iscoroutine(result):
        return await result
    return result


# ── 工厂函数 ────────────────────────────────────────────────

def create_event_extractor(llm_fn: Optional[callable] = None) -> EventExtractor:
    """创建事件提取器"""
    return EventExtractor(llm_fn=llm_fn)


def create_entity_extractor(llm_fn: Optional[callable] = None) -> EntityExtractor:
    """创建实体提取器"""
    return EntityExtractor(llm_fn=llm_fn)
