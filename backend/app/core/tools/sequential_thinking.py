"""
Sequential Thinking 工具 — 借鉴 Trae Agent 显式思维链

让 Agent 在关键决策点暂停并显式思考，支持：
- 交错思考-行动模式：think → act → think → act → ...
- 可修正的思考路径：支持分支、修正、从前一个思考点继续
- 思考过程可观察：轨迹记录中完整捕获思考链

协议（借鉴 Trae Agent sequentialthinking MCP tool）:
  - thought: 当前思考内容
  - thought_number: 当前思考序号（从1开始）
  - total_thoughts: 预估总思考步数（可调整）
  - next_thought_needed: 是否还需要继续思考
  - is_revision: 是否修正之前的思考
  - revises_thought: 修正哪个思考步
  - branch_from_thought: 从哪个思考步分支
  - branch_id: 分支标识
  - needs_more_thoughts: 是否需要更多思考步

用法:
    tool = SequentialThinkingTool()
    result = await tool.call(
        thought="首先需要理解项目结构...",
        thought_number=1,
        total_thoughts=3,
        next_thought_needed=True,
    )
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.tools.builtin_tool import BuiltinTool, ToolExecResult
from app.core.tools.schema import ToolParam, ParamType

logger = logging.getLogger("tools.sequential_thinking")


@dataclass
class ThoughtRecord:
    """单条思考记录"""
    thought: str
    thought_number: int
    total_thoughts: int
    next_thought_needed: bool
    is_revision: bool = False
    revises_thought: int = 0
    branch_from_thought: int = 0
    branch_id: str = ""
    needs_more_thoughts: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "thought": self.thought,
            "thought_number": self.thought_number,
            "total_thoughts": self.total_thoughts,
            "next_thought_needed": self.next_thought_needed,
            "is_revision": self.is_revision,
            "revises_thought": self.revises_thought,
            "branch_from_thought": self.branch_from_thought,
            "branch_id": self.branch_id,
            "needs_more_thoughts": self.needs_more_thoughts,
            "timestamp": self.timestamp,
        }


@dataclass
class ThinkingChain:
    """思考链 — 存储和查询完整思考路径"""
    thoughts: list[ThoughtRecord] = field(default_factory=list)
    session_id: str = ""

    def add_thought(self, thought: ThoughtRecord) -> None:
        self.thoughts.append(thought)

    def get_main_chain(self) -> list[ThoughtRecord]:
        """获取主思考链（非分支非修正）"""
        return [t for t in self.thoughts if not t.is_revision and not t.branch_from_thought]

    def get_revisions(self) -> list[ThoughtRecord]:
        """获取修正记录"""
        return [t for t in self.thoughts if t.is_revision]

    def get_branches(self) -> dict[str, list[ThoughtRecord]]:
        """按 branch_id 分组的分支"""
        branches: dict[str, list[ThoughtRecord]] = {}
        for t in self.thoughts:
            if t.branch_id:
                branches.setdefault(t.branch_id, []).append(t)
        return branches

    def to_summary(self) -> str:
        """生成思考链摘要"""
        if not self.thoughts:
            return "（无思考记录）"

        lines = ["## 🧠 思考链"]
        chain = self.get_main_chain()
        for t in chain:
            marker = "📌" if t.next_thought_needed else "✅"
            lines.append(
                f"{marker} 思考 {t.thought_number}/{t.total_thoughts}: "
                f"{t.thought[:100]}{'...' if len(t.thought) > 100 else ''}"
            )

        revisions = self.get_revisions()
        if revisions:
            lines.append(f"\n🔄 修正了 {len(revisions)} 个思考点")
            for r in revisions:
                lines.append(
                    f"  修正思考 #{r.revises_thought}: "
                    f"{r.thought[:80]}{'...' if len(r.thought) > 80 else ''}"
                )

        branches = self.get_branches()
        if branches:
            lines.append(f"\n🌿 {len(branches)} 个分支")
            for bid, bthoughts in branches.items():
                lines.append(f"  分支 '{bid}': {len(bthoughts)} 步")

        return "\n".join(lines)

    def to_json(self) -> str:
        """序列化为 JSON"""
        return json.dumps(
            {
                "session_id": self.session_id,
                "thoughts": [t.to_dict() for t in self.thoughts],
            },
            ensure_ascii=False,
            indent=2,
        )

    def save(self, filepath: str | Path) -> None:
        """持久化思考链到文件"""
        Path(filepath).write_text(self.to_json(), encoding="utf-8")
        logger.info("Thinking chain saved: %s (%d thoughts)", filepath, len(self.thoughts))


@dataclass
class SequentialThinkingTool(BuiltinTool):
    """
    Sequential Thinking 工具 — 显式思维链

    让 LLM 在工具调用循环中插入显式思考步骤，
    思考过程可被轨迹记录器捕获，也可在前端展示。
    """

    name: str = "sequential_thinking"
    description: str = (
        "显式思考工具。在进行复杂分析、设计决策或排查问题时，"
        "使用此工具记录你的思考过程。支持动态调整思考步数、"
        "修正之前的思考、创建分支探索替代方案。"
    )
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("thought", ParamType.STRING, required=True,
                  description="当前思考内容"),
        ToolParam("thought_number", ParamType.INTEGER, required=True,
                  description="当前思考序号（从1开始）"),
        ToolParam("total_thoughts", ParamType.INTEGER, required=True,
                  description="预估总思考步数"),
        ToolParam("next_thought_needed", ParamType.BOOLEAN, required=True,
                  description="是否还需要继续下一步思考"),
        ToolParam("is_revision", ParamType.BOOLEAN, required=False,
                  description="是否是修正之前的思考"),
        ToolParam("revises_thought", ParamType.INTEGER, required=False,
                  description="修正哪个思考步的序号"),
        ToolParam("branch_from_thought", ParamType.INTEGER, required=False,
                  description="从哪个思考步分支"),
        ToolParam("branch_id", ParamType.STRING, required=False,
                  description="分支标识（如 'alternative-approach-1'）"),
        ToolParam("needs_more_thoughts", ParamType.BOOLEAN, required=False,
                  description="是否需要更多思考步（动态调整 total_thoughts 的信号）"),
    ])
    category: str = "reasoning"
    tags: list[str] = field(default_factory=lambda: ["thinking", "reasoning", "planning", "cognitive"])

    def __post_init__(self):
        super().__post_init__()
        self._chains: dict[str, ThinkingChain] = {}  # session_id → chain

    def get_or_create_chain(self, session_id: str) -> ThinkingChain:
        """获取或创建会话的思考链"""
        if session_id not in self._chains:
            self._chains[session_id] = ThinkingChain(session_id=session_id)
        return self._chains[session_id]

    def get_chain_summary(self, session_id: str) -> str:
        """获取思考链摘要"""
        chain = self._chains.get(session_id)
        return chain.to_summary() if chain else "（无思考记录）"

    def get_chain_json(self, session_id: str) -> str:
        """获取思考链 JSON"""
        chain = self._chains.get(session_id)
        return chain.to_json() if chain else "{}"

    async def handler(
        self,
        thought: str,
        thought_number: int,
        total_thoughts: int,
        next_thought_needed: bool,
        is_revision: bool = False,
        revises_thought: int = 0,
        branch_from_thought: int = 0,
        branch_id: str = "",
        needs_more_thoughts: bool = False,
        session_id: str = "default",
    ) -> str:
        """
        记录一条思考

        Returns:
            思考链当前状态的摘要
        """
        record = ThoughtRecord(
            thought=thought,
            thought_number=thought_number,
            total_thoughts=total_thoughts,
            next_thought_needed=next_thought_needed,
            is_revision=is_revision,
            revises_thought=revises_thought,
            branch_from_thought=branch_from_thought,
            branch_id=branch_id,
            needs_more_thoughts=needs_more_thoughts,
        )

        chain = self.get_or_create_chain(session_id)
        chain.add_thought(record)

        logger.info(
            "Thought %d/%d (session=%s, revision=%s, branch=%s): %s",
            thought_number, total_thoughts, session_id,
            is_revision, bool(branch_id),
            thought[:80],
        )

        # 返回状态
        parts = [
            f"🧠 思考 {thought_number}/{total_thoughts} 已记录",
        ]
        if is_revision:
            parts.append(f"  （修正思考 #{revises_thought}）")
        if branch_id:
            parts.append(f"  （分支: {branch_id}，从思考 #{branch_from_thought}）")
        parts.append(f"\n{chain.to_summary()}")

        return "\n".join(parts)

    # ── 思考链辅助方法 ──

    def get_merged_thoughts(self, session_id: str = "default") -> str:
        """
        获取合并后的思考内容（用于注入到后续 LLM 上下文中）

        格式:
            <thinking>
            思考 1/3: ...
            思考 2/3: ...
            思考 3/3: ... ✅
            </thinking>
        """
        chain = self._chains.get(session_id)
        if not chain:
            return ""

        main_chain = chain.get_main_chain()
        parts = ["<thinking>"]
        for t in main_chain:
            status = "✅" if not t.next_thought_needed else "..."
            parts.append(f"思考 {t.thought_number}/{t.total_thoughts}: {t.thought} {status}")
        parts.append("</thinking>")
        return "\n".join(parts)

    def clear_chain(self, session_id: str = "default") -> None:
        """清除指定会话的思考链"""
        if session_id in self._chains:
            del self._chains[session_id]
            logger.info("Thinking chain cleared: %s", session_id)


# ── 工具注册 ──────────────────────────────────────────────────

def register_sequential_thinking_tool() -> SequentialThinkingTool:
    """注册 Sequential Thinking 工具到全局注册中心"""
    from app.core.tools.registry import get_tool_registry

    tool = SequentialThinkingTool()
    registry = get_tool_registry()
    registry.register_sync(tool)
    logger.info("SequentialThinkingTool registered")
    return tool
