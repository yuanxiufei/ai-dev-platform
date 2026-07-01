"""
Agent 自省/反思模块 — 借鉴 Trae Agent reflect + DeerFlow Guardrail

LLM 自省机制：
- ReflectionManager: 全局反思管理器（before_task / after_run / periodic）
- AgentReflector: 单次反思执行器
- SelfCritique: 自我批评/验证器
- ReflectionPrompt: 反思提示词模板

数据流：
  AgentRunner.finalize() → ReflectionManager.after_run()
  → AgentReflector.reflect(question, context) → ModelRouter.generate()
  → ReflectionResult(score, issues, suggestions)
  → 注入到下一次 Agent 运行的 system prompt

核心设计：
- 反思不是惩罚性而是建设性的（改进建议+评分反馈）
- 支持多维度评估：安全性、正确性、效率、完整性
- 反思结果作为长期记忆持久化
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("agent.reflection")


# ── 数据模型 ──────────────────────────────────────────


@dataclass
class ReflectionConfig:
    """反思配置"""
    enabled: bool = True
    """是否启用反思"""
    reflect_on_every_turn: bool = False
    """每轮都反思（默认仅结束时反思）"""
    reflect_on_error: bool = True
    """错误时自动反思"""
    max_reflection_tokens: int = 2048
    """反思最大 token"""
    dimensions: list[str] = field(default_factory=lambda: [
        "safety",      # 安全性：是否产生了危险操作
        "correctness", # 正确性：结果是否符合预期
        "efficiency",  # 效率：是否有不必要的工具调用
        "completeness",# 完整性：是否遗漏了关键步骤
    ])
    """反思评估维度"""
    self_critique_enabled: bool = True
    """是否启用 SelfCritique（自我批评）"""
    save_to_memory: bool = True
    """反思结果存入长期记忆"""


@dataclass
class ReflectionResult:
    """单次反思结果"""
    run_id: str = ""
    question: str = ""
    """触发反思的问题"""
    score: float = 0.0
    """综合评分 0-100"""
    dimension_scores: dict[str, float] = field(default_factory=dict)
    """各维度评分"""
    issues: list[str] = field(default_factory=list)
    """发现的问题"""
    suggestions: list[str] = field(default_factory=list)
    """改进建议"""
    raw_response: str = ""
    """LLM 原始反思输出"""
    model_used: str = ""
    provider: str = ""
    latency_ms: float = 0.0
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "question": self.question,
            "score": self.score,
            "dimension_scores": self.dimension_scores,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "raw_response": self.raw_response[:1000],
            "model_used": self.model_used,
            "provider": self.provider,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp,
        }

    def summary(self) -> str:
        """人类可读摘要"""
        parts = [f"Reflection Score: {self.score:.1f}/100"]
        if self.dimension_scores:
            dims = ", ".join(f"{k}={v:.0f}" for k, v in self.dimension_scores.items())
            parts.append(f"Dimensions: {dims}")
        if self.issues:
            parts.append(f"Issues ({len(self.issues)}): " + "; ".join(self.issues[:3]))
        if self.suggestions:
            parts.append(f"Suggestions: " + "; ".join(self.suggestions[:3]))
        return " | ".join(parts)


@dataclass
class ReflectionPrompt:
    """反思提示词模板"""
    intro: str = "You are an expert code reviewer and agent quality evaluator."
    task_description: str = ""
    agent_actions: str = ""
    final_output: str = ""
    dimensions: list[str] = field(default_factory=list)

    def build(self) -> str:
        dim_list = "\n".join(f"{i+1}. {d}" for i, d in enumerate(self.dimensions))
        prompt = f"""{self.intro}

## Task
{self.task_description}

## Agent Actions
{self.agent_actions}

## Final Output
{self.final_output}

## Evaluation Dimensions
Please score 0-100 on each:
{dim_list}

## Output Format
Respond in JSON:
```json
{{
  "overall_score": <0-100>,
  "dimension_scores": {{"safety": <0-100>, "correctness": <0-100>, "efficiency": <0-100>, "completeness": <0-100>}},
  "issues": ["<specific issue>"],
  "suggestions": ["<actionable suggestion>"],
  "verdict": "PASS|WARN|FAIL"
}}
```

Be specific and actionable. Only report issues that actually occurred."""
        return prompt


@dataclass
class SelfCritique:
    """自我批评 — 借鉴 Trae Agent 的 self-critique 机制

    在 Agent 产出关键结果后，让 LLM 自我检查：
    - 是否有逻辑错误
    - 是否有遗漏的边界条件
    - 输出格式是否正确
    """

    enabled: bool = True
    max_retries: int = 1
    """最多自我修正重试次数"""

    def build_prompt(self, original_output: str, success_criteria: str) -> str:
        return f"""You are a self-critique system. Review your own output critically.

## Success Criteria
{success_criteria}

## Your Output
{original_output}

## Self-Check
Answer honestly:
1. Does the output fully meet ALL success criteria? (Y/N, explain)
2. Are there any logical errors or incorrect assumptions? (Y/N, list)
3. Are there any missing edge cases or boundary conditions? (Y/N, list)
4. Is the output format correct and complete? (Y/N, explain)

If you answered "N" to any question, fix the issues and output the corrected version.
Otherwise, output the original output unchanged.

## Response Format
```json
{{
  "meets_criteria": true/false,
  "issues_found": ["..."],
  "fixed_output": "<original or corrected output>"
}}
```"""


# ── AgentReflector — 单次反思执行器 ────────────────────


class AgentReflector:
    """Agent 反思执行器

    调用 LLM 对 Agent 运行结果进行多维度评估。
    """

    def __init__(self, config: ReflectionConfig | None = None) -> None:
        self.config = config or ReflectionConfig()
        self._critique = SelfCritique()

    async def reflect(
        self,
        question: str,
        task_description: str = "",
        agent_actions: str = "",
        final_output: str = "",
        run_id: str = "",
    ) -> ReflectionResult:
        """执行反思评估"""
        t0 = time.monotonic()

        result = ReflectionResult(
            run_id=run_id,
            question=question,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        prompt = ReflectionPrompt(
            task_description=task_description,
            agent_actions=agent_actions,
            final_output=final_output,
            dimensions=self.config.dimensions,
        ).build()

        try:
            from app.core.model_router import (
                ModelCapability, ModelRequest, get_model_router,
            )

            router = get_model_router()
            request = ModelRequest(
                capability=ModelCapability.CODE_GENERATION,
                prompt=prompt,
                max_tokens=self.config.max_reflection_tokens,
                temperature=0.3,
            )
            response = await router.generate(request)

            result.raw_response = response.content
            result.model_used = response.model
            result.provider = response.provider
            result.latency_ms = (time.monotonic() - t0) * 1000

            # 解析 JSON
            parsed = self._parse_reflection_json(response.content)
            if parsed:
                result.score = parsed.get("overall_score", 0.0)
                result.dimension_scores = parsed.get("dimension_scores", {})
                result.issues = parsed.get("issues", [])
                result.suggestions = parsed.get("suggestions", [])

            logger.info(
                "Reflection done: score=%.1f issues=%d suggestions=%d latency=%.0fms model=%s",
                result.score, len(result.issues), len(result.suggestions),
                result.latency_ms, result.model_used,
            )

        except Exception as e:
            logger.warning("Reflection failed: %s", e)
            result.issues = [f"Reflection error: {str(e)[:200]}"]
            result.score = -1.0
            result.latency_ms = (time.monotonic() - t0) * 1000

        return result

    def _parse_reflection_json(self, raw: str) -> dict[str, Any] | None:
        """解析反思 JSON 输出"""
        # 尝试提取 JSON 块
        import re as _re
        json_match = _re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, _re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # 尝试提取花括号内容
        brace_match = _re.search(r'\{.*\}', raw, _re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse reflection JSON from: %s", raw[:500])
        return None

    async def self_critique(
        self,
        original_output: str,
        success_criteria: str,
    ) -> tuple[str, bool]:
        """自我批评 + 自动修正

        返回 (fixed_output, was_modified)
        """
        if not self.config.self_critique_enabled:
            return original_output, False

        prompt = self._critique.build_prompt(original_output, success_criteria)

        try:
            from app.core.model_router import (
                ModelCapability, ModelRequest, get_model_router,
            )

            router = get_model_router()
            request = ModelRequest(
                capability=ModelCapability.CODE_GENERATION,
                prompt=prompt,
                max_tokens=self.config.max_reflection_tokens,
                temperature=0.2,
            )
            response = await router.generate(request)

            parsed = self._parse_reflection_json(response.content)
            if parsed:
                meets = parsed.get("meets_criteria", True)
                fixed = parsed.get("fixed_output", original_output)
                issues = parsed.get("issues_found", [])
                if issues:
                    logger.info("Self-critique found %d issues", len(issues))
                return fixed, not meets

        except Exception as e:
            logger.warning("Self-critique failed: %s", e)

        return original_output, False


# ── ReflectionManager — 全局反思管理器 ────────────────


class ReflectionManager:
    """全局反思管理器

    生命周期：
    - before_task: 根据历史反思结果调整 system prompt
    - after_run: 运行反思评估 + 存入记忆
    - periodic: 定时评估 Agent 整体表现趋势
    """

    def __init__(self, config: ReflectionConfig | None = None) -> None:
        self.config = config or ReflectionConfig()
        self._reflector = AgentReflector(self.config)
        self._history: list[ReflectionResult] = []
        self._max_history = 50

    async def after_run(
        self,
        run_result: Any,  # AgentRunResult
        task_description: str = "",
        agent_actions: str = "",
    ) -> ReflectionResult | None:
        """Agent 运行结束后反思"""
        if not self.config.enabled:
            return None

        question = self._build_question(run_result)
        final_output = getattr(run_result, "final_answer", "") or ""

        result = await self._reflector.reflect(
            question=question,
            task_description=task_description,
            agent_actions=agent_actions,
            final_output=final_output,
            run_id=getattr(run_result, "run_id", ""),
        )

        self._history.append(result)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        # 存入长期记忆
        if self.config.save_to_memory and result.score >= 0:
            await self._save_to_memory(result)

        return result

    def _build_question(self, run_result: Any) -> str:
        """根据运行结果构建反思问题"""
        success = getattr(run_result, "success", True)
        turns = getattr(run_result, "turns", 0)
        tool_calls = getattr(run_result, "total_tool_calls", 0)
        error = getattr(run_result, "error", "") or ""

        if not success:
            return f"Agent failed after {turns} turns with error: {error}. What went wrong and how to improve?"
        if tool_calls == 0:
            return f"Agent completed in {turns} turns without any tool calls. Was the answer complete and correct?"
        if turns > 10:
            return f"Agent took {turns} turns and {tool_calls} tool calls. Was this efficient? Could it be done in fewer steps?"
        return f"Evaluate the agent run ({turns} turns, {tool_calls} tool calls) for quality and correctness."

    async def build_system_prompt_augmentation(self) -> str:
        """从历史反思中提取系统提示增强

        将最近失败的反思结果转化为具体指导注入 system prompt。
        """
        if not self._history:
            return ""

        recent = self._history[-5:]
        failures = [r for r in recent if r.score < 50]
        if not failures:
            return ""

        recent_issues: list[str] = []
        for f in failures:
            recent_issues.extend(f.issues[:2])

        # 去重
        seen: set[str] = set()
        unique: list[str] = []
        for issue in recent_issues:
            key = issue[:50].lower()
            if key not in seen:
                seen.add(key)
                unique.append(issue)

        if not unique:
            return ""

        lines = [
            "\n## Recent Performance Feedback (from self-reflection)",
            "Based on previous runs, pay special attention to:",
        ]
        for i, issue in enumerate(unique[:5], 1):
            lines.append(f"{i}. {issue}")

        return "\n".join(lines) + "\n"

    async def _save_to_memory(self, result: ReflectionResult) -> None:
        """将反思结果持久化到记忆系统 — 使用 MemoryExtractor 提取 LESSON 类型"""
        try:
            # 使用图存储（MemoryNode/Edge），而非向量层 key-value 存储
            from app.core.memory.memory_store import get_memory_store as get_graph_store
            from app.core.memory.memory_extractor import MemoryExtractor
        except ImportError:
            return  # Memory 系统未加载，静默跳过

        try:
            # 构建反思文本（issues + suggestions）
            reflection_text = ReflectionManager._build_reflection_text(result)
            if not reflection_text:
                return

            store = get_graph_store()
            extractor = MemoryExtractor(store)

            # 提取 LESSON 类型的记忆节点
            nodes = extractor.extract_from_reflection(
                reflection_text=reflection_text,
                agent_id=result.run_id,
            )

            # 保存每个节点到图存储
            for node in nodes:
                store.save(node)

            if nodes:
                logger.info(
                    "Saved %d reflection lessons to graph memory (score=%.1f, run_id=%s)",
                    len(nodes), result.score, result.run_id,
                )
            else:
                # 如果没有提取到结构化教训，至少保存原始反思摘要
                import time as _time
                from app.core.memory.memory_store import MemoryNode, MemoryType as MT
                summary_node = MemoryNode(
                    content=result.summary(),
                    memory_type=MT.LESSON,
                    importance=max(0.1, min(1.0, result.score / 100.0)),
                    created_at=_time.time(),
                    source=f"reflection:{result.run_id}",
                    tags=["lesson", "reflection", "summary"],
                    metadata=result.to_dict(),
                )
                store.save(summary_node)
                logger.info(
                    "Saved reflection summary to memory (score=%.1f, run_id=%s)",
                    result.score, result.run_id,
                )

        except Exception as e:
            logger.warning("Failed to save reflection to memory: %s", e)

    @staticmethod
    def _build_reflection_text(result: ReflectionResult) -> str:
        """将 ReflectionResult 构建为适合 MemoryExtractor 解析的文本"""
        lines: list[str] = []
        if result.issues:
            for issue in result.issues:
                lines.append(issue)
        if result.suggestions:
            for s in result.suggestions:
                lines.append(s)
        if result.dimension_scores:
            dims = ", ".join(
                f"{k}={v:.0f}" for k, v in result.dimension_scores.items()
            )
            lines.append(
                f"The agent achieved dimension scores: {dims} "
                f"(overall {result.score:.0f}/100)."
            )
        return "\n".join(lines)

    @property
    def recent_scores(self) -> list[float]:
        return [r.score for r in self._history if r.score >= 0]

    @property
    def average_score(self) -> float:
        scores = self.recent_scores
        return sum(scores) / len(scores) if scores else 0.0


# ── 全局单例 ──────────────────────────────────────────

_reflection_manager: ReflectionManager | None = None


def init_reflection_manager(config: ReflectionConfig | None = None) -> ReflectionManager:
    global _reflection_manager
    _reflection_manager = ReflectionManager(config)
    logger.info("ReflectionManager initialized (reflect_on_error=%s, dimensions=%s)",
                _reflection_manager.config.reflect_on_error,
                _reflection_manager.config.dimensions)
    return _reflection_manager


def get_reflection_manager() -> ReflectionManager:
    global _reflection_manager
    if _reflection_manager is None:
        _reflection_manager = ReflectionManager()
    return _reflection_manager
