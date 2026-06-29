"""
记忆检索器 — 语义搜索 + 图遍历检索

自主设计，结合关键词搜索和图遍历：
- 关键词搜索（SQLite LIKE + FTS）
- 重要性加权排序
- BFS 图遍历关联检索
- Agent 上下文注入

纯 Python 实现。
"""

from __future__ import annotations

import logging
import math
import sqlite3
from typing import Any

from .memory_store import (
    MemoryNode,
    MemoryEdge,
    MemoryType,
    MemoryStore,
    get_memory_store,
)

logger = logging.getLogger("memory.retriever")


class MemoryRetriever:
    """
    记忆检索器

    综合多种检索策略：
    1. 关键词精确匹配
    2. 语义相关度（基于标签和类型匹配）
    3. 图遍历扩展（关联记忆）
    4. 重要性 + 新鲜度排序

    用法:
        retriever = MemoryRetriever(store)
        results = retriever.retrieve("how to structure the database", top_k=10)
    """

    def __init__(self, store: MemoryStore):
        self._store = store

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        memory_type: str | None = None,
        min_importance: float = 0.0,
        include_related: bool = True,
    ) -> list[dict[str, Any]]:
        """
        综合检索记忆

        Args:
            query: 搜索查询
            top_k: 返回结果数量
            memory_type: 过滤记忆类型
            min_importance: 最低重要性阈值
            include_related: 是否包含图遍历关联记忆

        Returns:
            排序后的结果列表，每项含 node + score
        """
        # 1. 关键词检索
        results = self._store.search_by_keyword(
            query, memory_type=memory_type, limit=top_k * 2,
            min_importance=min_importance,
        )

        # 2. 计算综合得分
        scored: list[tuple[float, MemoryNode]] = []
        for node in results:
            score = self._score_node(node, query)
            # 衰减因子
            score *= node.decay_score / (node.importance + 0.1)
            scored.append((score, node))

        scored.sort(key=lambda x: -x[0])
        top_nodes = scored[:top_k]

        # 3. 图遍历关联
        output: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for score, node in top_nodes:
            if node.id not in seen_ids:
                seen_ids.add(node.id)
                output.append({
                    "node": node.to_dict(),
                    "score": round(score, 4),
                    "related": [],
                })

        if include_related:
            for item in output:
                related_nodes = self._store.get_connected(item["node"]["id"], depth=1)
                for rn in related_nodes:
                    if rn.id not in seen_ids:
                        seen_ids.add(rn.id)
                        item["related"].append(rn.to_dict())

        return output

    def retrieve_as_context(
        self,
        query: str = "",
        max_items: int = 10,
    ) -> str:
        """
        检索并格式化为 Agent 可注入的上下文字符串

        Args:
            query: 检索查询
            max_items: 最多返回的记忆条数

        Returns:
            格式化的上下文字符串
        """
        if not query:
            # 无查询时返回最近记忆
            nodes = self._store.search_recent(limit=max_items)
            if not nodes:
                return ""
            lines = ["## Relevant Context from Memory\n"]
            for node in nodes:
                lines.append(f"- [{node.memory_type}] {node.content}")
            return "\n".join(lines)

        results = self.retrieve(query, top_k=max_items, include_related=False)
        if not results:
            return ""

        lines = ["## Relevant Context from Memory\n"]
        for item in results:
            node_data = item["node"]
            lines.append(
                f"- [{node_data['memory_type']}] "
                f"{node_data['content']} "
                f"(score: {item['score']:.2f})"
            )

        return "\n".join(lines)

    def search_conversation_history(
        self,
        session_id: str,
        query: str = "",
        limit: int = 20,
    ) -> list[MemoryNode]:
        """检索特定对话会话的记忆"""
        nodes = self._store.search_by_source(
            f"conversation:{session_id}",
            limit=limit,
        )
        if not query:
            return nodes

        # 在会话记忆中进行二次检索
        query_lower = query.lower()
        filtered = []
        for node in nodes:
            if query_lower in node.content.lower():
                filtered.append(node)
        return filtered[:limit]

    def get_decisions(
        self,
        project_context: str = "",
        limit: int = 10,
    ) -> list[MemoryNode]:
        """检索架构决策"""
        return self._store.search_by_keyword(
            project_context,
            memory_type=MemoryType.DECISION,
            limit=limit,
            min_importance=0.5,
        )

    def get_lessons(
        self,
        topic: str = "",
        limit: int = 10,
    ) -> list[MemoryNode]:
        """检索经验教训"""
        return self._store.search_by_keyword(
            topic,
            memory_type=MemoryType.LESSON,
            limit=limit,
            min_importance=0.3,
        )

    # ── 评分 ──────────────────────────────────────

    @staticmethod
    def _score_node(node: MemoryNode, query: str) -> float:
        """
        计算节点与查询的相关性得分

        因子：
        - 内容匹配度 (TF-like)
        - 标签匹配度
        - 类型权重
        - 重要性加权
        """
        score = 0.0
        query_lower = query.lower()
        content_lower = node.content.lower()

        # 内容匹配
        query_terms = query_lower.split()
        for term in query_terms:
            if term in content_lower:
                # TF-like: 出现次数越多得分越高
                count = content_lower.count(term)
                score += 1.0 + math.log(1 + count)

        # 标签匹配
        for tag in node.tags:
            if tag.lower() in query_lower:
                score += 2.0

        # 精确匹配加权
        if query_lower in content_lower:
            score += 5.0

        # 类型权重
        type_weight = {
            MemoryType.DECISION: 1.5,
            MemoryType.LESSON: 1.3,
            MemoryType.PATTERN: 1.2,
            MemoryType.CODE: 1.1,
            MemoryType.PREFERENCE: 1.4,
        }
        score *= type_weight.get(node.memory_type, 1.0)

        return score


# ── 全局单例 ──────────────────────────────────────

_global_retriever: MemoryRetriever | None = None


def init_retriever(store: MemoryStore | None = None) -> MemoryRetriever:
    """初始化全局检索器"""
    global _global_retriever
    if store is None:
        store = get_memory_store()
    _global_retriever = MemoryRetriever(store)
    logger.info("MemoryRetriever initialized")
    return _global_retriever


def get_retriever() -> MemoryRetriever:
    """获取全局检索器"""
    global _global_retriever
    if _global_retriever is None:
        return init_retriever()
    return _global_retriever
