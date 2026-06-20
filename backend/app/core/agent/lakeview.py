"""
Lakeview 步骤摘要 — 借鉴 Trae Agent Lakeview

使用 LLM 自动为 Agent 的每个执行步骤生成人类可读摘要，提供：
- 步骤级别摘要：每个 tool_call → 一行中文摘要
- 整体执行总结：完整运行结束后自动生成总结
- 标签分类：自动打标签（如 #文件操作 #搜索 #错误）
- 可注入 Agent 上下文：压缩的步骤摘要可替代原始 tool_results

与 TrajectoryRecorder 配合使用：
  Trajectory → 精确的技术审计数据
  Lakeview   → 人类友好的摘要和对 Agent 的上下文压缩
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("agent.lakeview")


# ── 摘要数据结构 ──────────────────────────────────────────────

@dataclass
class StepSummary:
    """单步摘要"""
    turn: int
    timestamp: float
    tag: str = ""                        # 标签: #文件操作 #搜索 #命令 #错误 #思考
    summary: str = ""                     # 人类可读摘要
    tool_name: str = ""                   # 工具名称
    tool_args_preview: str = ""           # 工具参数预览
    success: bool = True
    latency_ms: float = 0.0
    result_preview: str = ""              # 结果预览（截断）
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunSummary:
    """完整运行摘要"""
    agent_id: str = ""
    session_id: str = ""
    total_turns: int = 0
    total_tool_calls: int = 0
    total_tokens: int = 0
    total_latency_ms: float = 0.0
    steps: list[StepSummary] = field(default_factory=list)
    error: str = ""
    final_answer_preview: str = ""
    tags_summary: dict[str, int] = field(default_factory=lambda: {
        "#文件操作": 0, "#搜索": 0, "#命令": 0,
        "#错误": 0, "#思考": 0, "#编写代码": 0, "#其他": 0,
    })
    llm_summary: str = ""                 # LLM 生成的完整总结
    timestamp: float = field(default_factory=time.time)


# ── 标签推断规则 ──────────────────────────────────────────────

# 工具名 → 标签映射
_TOOL_TAG_MAP: dict[str, str] = {
    "read_file": "#文件操作",
    "write_file": "#文件操作",
    "edit_file": "#编写代码",
    "str_replace": "#编写代码",
    "create_file": "#文件操作",
    "delete_file": "#文件操作",
    "list_dir": "#文件操作",
    "search_code": "#搜索",
    "search_content": "#搜索",
    "grep_search": "#搜索",
    "web_search": "#搜索",
    "execute_command": "#命令",
    "bash": "#命令",
    "shell": "#命令",
    "run_command": "#命令",
    "sequential_thinking": "#思考",
    "think": "#思考",
    "ckg_search_function": "#搜索",
    "ckg_search_class": "#搜索",
    "ckg_search_method": "#搜索",
}

# 工具名前缀 → 标签映射（用于未精确匹配时）
_TOOL_PREFIX_TAG_MAP: dict[str, str] = {
    "read_": "#文件操作",
    "write_": "#文件操作",
    "edit_": "#编写代码",
    "search_": "#搜索",
    "find_": "#搜索",
    "exec": "#命令",
    "run_": "#命令",
    "bash_": "#命令",
    "think": "#思考",
}


def _infer_tag(tool_name: str) -> str:
    """根据工具名推断标签"""
    if tool_name in _TOOL_TAG_MAP:
        return _TOOL_TAG_MAP[tool_name]
    if tool_name.startswith("_") or tool_name == "":
        return "#其他"
    for prefix, tag in _TOOL_PREFIX_TAG_MAP.items():
        if tool_name.startswith(prefix) or prefix in tool_name:
            return tag
    return "#其他"


def _format_args_preview(args: dict[str, Any], max_len: int = 80) -> str:
    """格式化工具参数预览"""
    if not args:
        return ""

    # 优先展示 path / query / command 等关键参数
    key_params = []
    for key in ("path", "query", "command", "name", "slug", "pattern"):
        if key in args:
            val = str(args[key])
            if len(val) > 40:
                val = val[:37] + "..."
            key_params.append(f"{key}={val}")
            if len(key_params) >= 2:
                break

    if not key_params:
        # 展示前两个参数
        items = list(args.items())[:2]
        key_params = [f"{k}={str(v)[:30]}" for k, v in items]

    return ", ".join(key_params)


def _format_result_preview(result: Any, max_len: int = 120) -> str:
    """格式化结果预览"""
    if result is None:
        return ""
    result_str = str(result)
    if len(result_str) > max_len:
        return result_str[:max_len - 3] + "..."
    return result_str


# ── Lakeview 摘要生成器 ───────────────────────────────────────

@dataclass
class LakeviewSummarizer:
    """
    Lakeview 步骤摘要生成器

    用法:
        summarizer = LakeviewSummarizer()

        # 记录每个步骤
        for tool_result in results:
            summarizer.record_step(1, "read_file", {"path": "main.py"}, result)

        # 获取摘要
        summary = summarizer.get_run_summary()
        print(summary.to_markdown())
    """

    agent_id: str = ""
    session_id: str = ""
    steps: list[StepSummary] = field(default_factory=list)
    _start_time: float = field(default_factory=time.time)

    def start_run(self, agent_id: str = "", session_id: str = "") -> None:
        """开始新的运行"""
        self.agent_id = agent_id
        self.session_id = session_id
        self.steps.clear()
        self._start_time = time.time()

    def record_step(
        self,
        turn: int,
        tool_name: str,
        tool_args: dict[str, Any] | None = None,
        result: Any = None,
        success: bool = True,
        latency_ms: float = 0.0,
        error: str = "",
    ) -> StepSummary:
        """
        记录一个步骤

        Args:
            turn: 轮次
            tool_name: 工具名称
            tool_args: 工具参数
            result: 执行结果
            success: 是否成功
            latency_ms: 延迟（毫秒）
            error: 错误信息

        Returns:
            StepSummary
        """
        tag = _infer_tag(tool_name)
        if not success:
            tag = "#错误"

        step = StepSummary(
            turn=turn,
            timestamp=time.time(),
            tag=tag,
            tool_name=tool_name,
            tool_args_preview=_format_args_preview(tool_args or {}),
            success=success,
            latency_ms=latency_ms,
            result_preview=_format_result_preview(result) if success else error[:120],
        )

        # 自动生成摘要
        step.summary = self._generate_step_summary(step)

        self.steps.append(step)
        logger.info(
            "Lakeview step [%d]: %s %s — %s",
            turn, step.tag, step.tool_name, step.summary[:60],
        )

        return step

    def record_llm_step(
        self,
        turn: int,
        content: str,
        tokens_used: int = 0,
        latency_ms: float = 0.0,
    ) -> StepSummary:
        """记录 LLM 推理步骤（无工具调用）"""
        step = StepSummary(
            turn=turn,
            timestamp=time.time(),
            tag="#思考",
            tool_name="llm_response",
            tool_args_preview="",
            success=True,
            latency_ms=latency_ms,
            result_preview=_format_result_preview(content, 150),
        )
        step.summary = content[:100] + ("..." if len(content) > 100 else "")
        self.steps.append(step)
        return step

    def _generate_step_summary(self, step: StepSummary) -> str:
        """
        自动生成步骤摘要（不使用 LLM，基于规则）

        规则：
        - read_file + path → "读取 <filename>"
        - write_file + path → "写入 <filename>"
        - str_replace + path → "修改 <filename>"
        - search_* + query → "搜索 "<query>""
        - execute_command + command → "执行: <command>"
        - sequential_thinking → "深度思考中..."
        - 失败 → "❌ <工具名> 失败"
        """
        tool = step.tool_name
        args = step.tool_args_preview

        if not step.success:
            return f"❌ {tool} 失败"

        # 文件操作
        if tool == "read_file":
            return f"读取文件" + (f" {args}" if args else "")
        elif tool == "write_file":
            return f"写入文件" + (f" {args}" if args else "")
        elif tool == "str_replace":
            return f"精确修改" + (f" {args}" if args else "")
        elif tool in ("edit_file", "create_file"):
            return f"{'编辑' if tool == 'edit_file' else '创建'}文件" + (f" {args}" if args else "")
        elif tool == "list_dir":
            return f"列出目录内容" + (f" {args}" if args else "")
        elif tool == "delete_file":
            return f"删除文件" + (f" {args}" if args else "")

        # 搜索
        elif "search" in tool or "find" in tool.lower():
            return f"搜索" + (f" {args}" if args else "")
        elif tool == "web_search":
            return f"网络搜索" + (f" {args}" if args else "")

        # 命令
        elif "exec" in tool.lower() or "bash" in tool.lower() or tool in ("shell", "run_command"):
            return f"执行命令" + (f" {args}" if args else "")

        # 思考
        elif "think" in tool.lower() or "sequential" in tool.lower():
            return "深度思考中..."

        # 默认
        return f"{tool}" + (f" ({args})" if args else "")

    def get_run_summary(
        self,
        total_tokens: int = 0,
        error: str = "",
        final_answer: str = "",
    ) -> RunSummary:
        """获取完整运行摘要"""
        tags_summary = self._count_tags()
        return RunSummary(
            agent_id=self.agent_id,
            session_id=self.session_id,
            total_turns=len(set(s.turn for s in self.steps)),
            total_tool_calls=sum(1 for s in self.steps if s.tool_name != "llm_response"),
            total_tokens=total_tokens,
            total_latency_ms=sum(s.latency_ms for s in self.steps),
            steps=list(self.steps),
            error=error,
            final_answer_preview=final_answer[:200] if final_answer else "",
            tags_summary=tags_summary,
            llm_summary=self._generate_run_summary_text(),
            timestamp=time.time(),
        )

    def _count_tags(self) -> dict[str, int]:
        """统计各标签出现次数"""
        counts: dict[str, int] = {
            "#文件操作": 0, "#搜索": 0, "#命令": 0,
            "#错误": 0, "#思考": 0, "#编写代码": 0, "#其他": 0,
        }
        for step in self.steps:
            tag = step.tag if step.tag in counts else "#其他"
            counts[tag] += 1
        return counts

    def _generate_run_summary_text(self) -> str:
        """生成运行摘要文本"""
        parts = [f"## 📊 运行摘要 — {self.agent_id or 'Agent'}"]

        # 统计
        tool_calls = sum(1 for s in self.steps if s.tool_name != "llm_response")
        llm_calls = len(set(s.turn for s in self.steps))
        errors = sum(1 for s in self.steps if not s.success)
        total_latency = sum(s.latency_ms for s in self.steps)

        parts.append(f"- 🔄 {llm_calls} 轮 LLM 调用")
        parts.append(f"- 🔧 {tool_calls} 次工具调用")
        if errors:
            parts.append(f"- ⚠️ {errors} 次错误")
        parts.append(f"- ⏱️ 总延迟 {total_latency:.0f}ms")

        # 步骤时间线
        parts.append("\n### 步骤时间线")
        for step in self.steps:
            status = "✅" if step.success else "❌"
            parts.append(f"{status} [轮{step.turn}] {step.tag} {step.summary}")

        # 标签分布
        parts.append("\n### 操作分布")
        for tag, count in self._count_tags().items():
            if count > 0:
                bar = "█" * min(count, 20)
                parts.append(f"  {tag}: {count} {bar}")

        return "\n".join(parts)

    def get_compact_summary(self, max_tokens: int = 2000) -> str:
        """
        获取紧凑摘要（可注入 Agent 上下文）

        将步骤压缩为简短的摘要，适合在 token 紧张时使用。
        """
        lines = [f"<steps_summary agent='{self.agent_id}'>"]

        for step in self.steps:
            summary = step.summary or step.tool_name
            status = "✓" if step.success else "✗"
            lines.append(f"[{step.turn}] {status} {step.tag} {summary}")

        lines.append("</steps_summary>")

        result = "\n".join(lines)
        # 简单截断
        if len(result) > max_tokens * 4:
            lines = lines[:max(3, max_tokens * 4 // 100)]
            lines.append(f"  ... (截断 {len(self.steps) - len(lines)} 步)")
            result = "\n".join(lines)

        return result

    def to_markdown(self) -> str:
        """输出 Markdown 格式的完整摘要"""
        run = self.get_run_summary()
        return run.llm_summary

    def clear(self) -> None:
        """清除所有摘要记录"""
        self.steps.clear()
        logger.debug("Lakeview summarizer cleared")


# ── 全局单例 ──────────────────────────────────────────────────

_global_summarizer: LakeviewSummarizer | None = None


def get_lakeview_summarizer() -> LakeviewSummarizer:
    """获取全局 Lakeview 摘要生成器"""
    global _global_summarizer
    if _global_summarizer is None:
        _global_summarizer = LakeviewSummarizer()
    return _global_summarizer
