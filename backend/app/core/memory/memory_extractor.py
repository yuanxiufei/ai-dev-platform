"""
记忆提取器 — 从对话/代码变更/反思结果中提取结构化记忆

自主设计，借鉴 cognee 的 remember() / cognify() 模式：
- 从 LLM 对话中提取知识点
- 从代码变更中提取模式
- 从 Agent 反思中保存教训

纯 Python 实现。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from .memory_store import MemoryNode, MemoryEdge, MemoryType, RelationType, MemoryStore

logger = logging.getLogger("memory.extractor")


class MemoryExtractor:
    """
    记忆提取器

    职责：将非结构化的输入（对话、代码、反思）转为结构化的 MemoryNode。

    用法:
        extractor = MemoryExtractor(store)
        nodes = extractor.extract_from_conversation(messages)
        for node in nodes:
            store.save(node)
    """

    def __init__(self, store: MemoryStore):
        self._store = store

    # ── 从对话提取 ────────────────────────────────

    def extract_from_conversation(
        self,
        messages: list[dict],
        session_id: str = "",
    ) -> list[MemoryNode]:
        """
        从对话消息中提取结构化记忆。

        规则：
        - 用户消息中的明确决策 → DECISION 类型
        - Assistant 生成的代码模式 → PATTERN 类型
        - 明显的错误修复 → LESSON 类型
        - 其他事实性信息 → FACT 类型

        Returns:
            提取的记忆节点列表
        """
        nodes: list[MemoryNode] = []
        now = time.time()

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if not content or len(content) < 20:
                continue

            # 用户消息
            if role == "user":
                # 提取明确的决策/偏好
                decisions = self._extract_decisions(content)
                for decision in decisions:
                    nodes.append(MemoryNode(
                        content=decision,
                        memory_type=MemoryType.DECISION,
                        importance=0.8,
                        created_at=now,
                        source=f"conversation:{session_id}",
                        tags=["decision", "user"],
                    ))

                # 提取偏好
                prefs = self._extract_preferences(content)
                for pref in prefs:
                    nodes.append(MemoryNode(
                        content=pref,
                        memory_type=MemoryType.PREFERENCE,
                        importance=0.6,
                        created_at=now,
                        source=f"conversation:{session_id}",
                        tags=["preference", "user"],
                    ))

            # Assistant 消息
            elif role == "assistant":
                # 提取代码模式
                patterns = self._extract_code_patterns(content)
                for pattern in patterns:
                    nodes.append(MemoryNode(
                        content=pattern,
                        memory_type=MemoryType.PATTERN,
                        importance=0.5,
                        created_at=now,
                        source=f"conversation:{session_id}",
                        tags=["code", "pattern"],
                    ))

                # 提取技术事实
                facts = self._extract_technical_facts(content)
                for fact in facts:
                    nodes.append(MemoryNode(
                        content=fact,
                        memory_type=MemoryType.FACT,
                        importance=0.4,
                        created_at=now,
                        source=f"conversation:{session_id}",
                        tags=["fact"],
                    ))

        # 建立对话流转关系
        for i in range(len(nodes) - 1):
            self._store.add_edge(
                nodes[i].id, nodes[i + 1].id,
                RelationType.CONVERSATION_FLOW,
                weight=0.3,
            )

        if nodes:
            logger.info("Extracted %d memories from conversation %s",
                        len(nodes), session_id[:12])
        return nodes

    # ── 从代码变更提取 ──────────────────────────────

    def extract_from_code_change(
        self,
        diff_text: str,
        description: str = "",
    ) -> list[MemoryNode]:
        """
        从代码变更中提取记忆。

        识别：
        - 重构模式
        - API 变更
        - 新增功能
        - Bug 修复
        """
        nodes: list[MemoryNode] = []
        now = time.time()

        # 检测重构
        if self._is_refactor(diff_text):
            nodes.append(MemoryNode(
                content=f"Refactored: {description}" if description else "Code refactoring performed",
                memory_type=MemoryType.CODE,
                importance=0.5,
                created_at=now,
                source="code_change",
                tags=["refactor"],
                metadata={"diff_summary": diff_text[:500]},
            ))

        # 检测 Bug 修复
        if self._is_bugfix(diff_text):
            nodes.append(MemoryNode(
                content=f"Bug fixed: {description}" if description else "Bug fix applied",
                memory_type=MemoryType.LESSON,
                importance=0.7,
                created_at=now,
                source="code_change",
                tags=["bugfix", "lesson"],
                metadata={"diff_summary": diff_text[:500]},
            ))

        if nodes:
            logger.info("Extracted %d memories from code change", len(nodes))
        return nodes

    # ── 从反思提取 ────────────────────────────────

    def extract_from_reflection(
        self,
        reflection_text: str,
        agent_id: str = "",
    ) -> list[MemoryNode]:
        """
        从 Agent 反思结果中提取经验教训。

        反思文本示例：'The code generation was too verbose. Use shorter variable names.'
        """
        nodes: list[MemoryNode] = []
        now = time.time()

        # 提取教训（以 "should" / "must" / "better to" 开头的句子）
        sentences = re.split(r'[.。!！\n]', reflection_text)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence or len(sentence) < 15:
                continue

            is_lesson = any(
                keyword in sentence.lower()
                for keyword in ["should", "must", "better", "avoid", "need to", "ought to"]
            )
            is_positive = any(
                keyword in sentence.lower()
                for keyword in ["worked", "success", "good", "effective", "well"]
            )

            if is_lesson or is_positive:
                nodes.append(MemoryNode(
                    content=sentence.strip(),
                    memory_type=MemoryType.LESSON,
                    importance=0.6 if is_lesson else 0.4,
                    created_at=now,
                    source=f"reflection:{agent_id}",
                    tags=["lesson", "reflection"],
                ))

        if nodes:
            logger.info("Extracted %d memories from reflection", len(nodes))
        return nodes

    # ── 内部提取规则 ────────────────────────────────

    @staticmethod
    def _extract_decisions(text: str) -> list[str]:
        """从文本中提取明确决策"""
        decisions: list[str] = []
        # 匹配 "use X" / "choose X" / "go with X" 等模式
        patterns = [
            r"(?:use|using|choose|chose|go with|went with|decide to|decided to)\s+([^.]+)",
            r"(?:I (?:want|need|prefer|like))\s+([^.]+)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                decision = match.group(1).strip()
                if 10 < len(decision) < 200:
                    decisions.append(decision)
        return decisions[:3]  # 最多3条

    @staticmethod
    def _extract_preferences(text: str) -> list[str]:
        """提取用户偏好"""
        prefs: list[str] = []
        patterns = [
            r"(?:prefer|favor|like|rather)\s+([^.]+)",
            r"(?:don't|do not|never)\s+(?:want|like|use)\s+([^.]+)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                pref = match.group(1).strip()
                if 10 < len(pref) < 200:
                    prefs.append(pref)
        return prefs[:2]

    @staticmethod
    def _extract_code_patterns(text: str) -> list[str]:
        """提取代码模式"""
        patterns: list[str] = []
        # 提取被 ``` 包裹的代码块说明
        code_blocks = re.findall(r'```\w*\n(.*?)```', text, re.DOTALL)
        for block in code_blocks:
            if 20 < len(block) < 500:
                # 取第一行作为描述
                first_line = block.strip().split('\n')[0]
                if first_line and not first_line.startswith('#'):
                    patterns.append(f"Code pattern: {first_line}")
        return patterns[:2]

    @staticmethod
    def _extract_technical_facts(text: str) -> list[str]:
        """提取技术事实"""
        facts: list[str] = []
        # 识别 "The X is Y" / "X uses Y" 等事实性陈述
        patterns = [
            r"(?:The|A)\s+(\w+)\s+(?:is|uses|relies on|depends on|requires)\s+([^.]+)",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                fact = f"{match.group(1)}: {match.group(2).strip()}"
                if 15 < len(fact) < 300:
                    facts.append(fact)
        return facts[:3]

    # ── 变更分类 ────────────────────────────────────

    @staticmethod
    def _is_refactor(diff_text: str) -> bool:
        """判断是否是重构变更"""
        added = diff_text.count('\n+')
        removed = diff_text.count('\n-')
        # 重构通常增删行数接近
        if added == 0 or removed == 0:
            return False
        ratio = min(added, removed) / max(added, removed)
        return ratio > 0.6  # 增删行数相近

    @staticmethod
    def _is_bugfix(diff_text: str) -> bool:
        """判断是否是 Bug 修复"""
        keywords = ["fix", "bug", "issue", "error", "crash", "null", "undefined", "exception"]
        text_lower = diff_text.lower()
        return any(kw in text_lower for kw in keywords)


# ── 便捷函数 ──────────────────────────────────────

def extract_and_save(
    store: MemoryStore,
    messages: list[dict],
    session_id: str = "",
) -> list[MemoryNode]:
    """从对话中提取并保存记忆（一步完成）"""
    extractor = MemoryExtractor(store)
    nodes = extractor.extract_from_conversation(messages, session_id=session_id)
    for node in nodes:
        store.save(node)
    return nodes
