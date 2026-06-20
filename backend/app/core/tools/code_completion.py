"""
代码补全管道 — FIM (Fill-in-the-Middle) + 上下文感知补全

借鉴 Continue autocomplete/ 和 Cline code-completion 设计：
- FIMCompletionEngine: Fill-in-the-Middle 代码补全引擎
- ContextAssembler: 上下文组装器（附近代码、import、类型、最近编辑）
- CompletionRanker: 补全结果排序器（相关性、类型匹配、活跃度）
- CompletionCache: 缓存层（LRU + 文件指纹）
- 多模型支持：通过 ModelRouter 选择最优代码模型

数据流：
    光标位置 → ContextAssembler 提取上下文 → 组装 FIM prompt
    → ModelRouter 生成补全 → CompletionRanker 排序 → 返回 top-K
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("tools.code_completion")


# ══════════════════════════════════════════════════════════════
# 数据模型
# ══════════════════════════════════════════════════════════════


class CompletionTrigger(str, Enum):
    """触发补全的事件类型"""
    KEYSTROKE = "keystroke"       # 输入字符后
    DOT = "dot"                   # 输入 . 后（属性/方法）
    IMPORT = "import"             # import 语句后
    FUNCTION_CALL = "function_call"  # 函数调用 (
    NEWLINE = "newline"           # 换行后
    MANUAL = "manual"             # 手动触发 (Ctrl+Space)


@dataclass
class CursorContext:
    """光标上下文的抽象表示"""
    # 光标前后文本
    prefix: str = ""       # 光标前的代码
    suffix: str = ""       # 光标后的代码

    # 文件信息
    file_path: str = ""
    language: str = ""     # python/typescript/javascript/vue/...
    file_content: str = ""  # 完整文件内容

    # 元信息
    cursor_line: int = 0
    cursor_column: int = 0
    tab_size: int = 4
    indent_style: str = "space"  # space | tab

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix_chars": len(self.prefix),
            "suffix_chars": len(self.suffix),
            "file_path": self.file_path,
            "language": self.language,
            "cursor_line": self.cursor_line,
            "cursor_column": self.cursor_column,
        }


@dataclass
class CompletionItem:
    """单条补全结果"""
    text: str = ""
    """补全文本"""

    display_text: str = ""
    """显示用文本（可能包含注释）"""

    score: float = 0.0
    """综合评分 (0-1)"""

    # 匹配维度
    prefix_match_score: float = 0.0        # 前缀匹配度
    type_match_score: float = 0.0          # 类型匹配度
    liveness_score: float = 0.0            # 活跃度（最近使用/编辑频率）
    semantic_score: float = 0.0            # 语义相关性（如果有）

    # 来源信息
    model_used: str = ""
    provider: str = ""
    latency_ms: float = 0.0

    # 元数据
    source: str = "model"  # model | snippet | history | type_inference
    snippet_id: str = ""
    """如果是 snippet 库匹配，记录 ID"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "display_text": self.display_text or self.text,
            "score": round(self.score, 4),
            "prefix_match_score": round(self.prefix_match_score, 4),
            "type_match_score": round(self.type_match_score, 4),
            "liveness_score": round(self.liveness_score, 4),
            "semantic_score": round(self.semantic_score, 4),
            "model_used": self.model_used,
            "provider": self.provider,
            "source": self.source,
        }


@dataclass
class CompletionResult:
    """补全请求的完整结果"""
    completions: list[CompletionItem] = field(default_factory=list)
    context: CursorContext | None = None
    total_latency_ms: float = 0.0
    model_used: str = ""
    provider: str = ""
    cache_hit: bool = False
    truncated: bool = False  # 结果是否被截断

    @property
    def top(self) -> CompletionItem | None:
        return self.completions[0] if self.completions else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "completions": [c.to_dict() for c in self.completions[:10]],
            "total_latency_ms": round(self.total_latency_ms, 2),
            "model_used": self.model_used,
            "provider": self.provider,
            "cache_hit": self.cache_hit,
            "truncated": self.truncated,
        }


@dataclass
class LanguageConfig:
    """语言特定的补全配置"""
    # FIM 分隔符
    fim_prefix_token: str = "<fim_prefix>"
    fim_suffix_token: str = "<fim_suffix>"
    fim_middle_token: str = "<fim_middle>"

    # 上下文窗口
    max_prefix_lines: int = 100
    max_suffix_lines: int = 50
    max_context_chars: int = 4096

    # 代码识别
    import_pattern: str = r"^import |^from |^require\(|^use |^#include"
    function_pattern: str = r"def |function |class |fn |func "
    comment_pattern: str = r"#|//|/\*|<!--"


# 语言配置表
LANGUAGE_CONFIGS: dict[str, LanguageConfig] = {
    "python": LanguageConfig(
        import_pattern=r"^import |^from ",
        function_pattern=r"def |class |async def ",
        comment_pattern=r"#",
    ),
    "typescript": LanguageConfig(
        import_pattern=r"^import |^export |^require\(",
        function_pattern=r"function |class |interface |type |const |let |async ",
        comment_pattern=r"//|/\*",
    ),
    "javascript": LanguageConfig(
        import_pattern=r"^import |^export |^require\(",
        function_pattern=r"function |class |const |let |var |async ",
        comment_pattern=r"//|/\*",
    ),
    "vue": LanguageConfig(
        import_pattern=r"^import |^export |^require\(",
        function_pattern=r"function |class |const |let |export default",
        comment_pattern=r"//|/\*|<!--",
    ),
    "go": LanguageConfig(
        import_pattern=r"^import |^package ",
        function_pattern=r"func |type |var |const ",
        comment_pattern=r"//|/\*",
    ),
    "rust": LanguageConfig(
        import_pattern=r"^use |^extern crate |^mod ",
        function_pattern=r"fn |struct |impl |enum |trait |pub ",
        comment_pattern=r"//|/\*",
    ),
}


# ══════════════════════════════════════════════════════════════
# 上下文组装器
# ══════════════════════════════════════════════════════════════


class ContextAssembler:
    """上下文组装器 — 从文件内容中提取 FM 所需的上下文

    借鉴 Continue autocomplete 的上下文策略：
    - 滑动窗口提取 prefix/suffix
    - 识别 import/function/class 边界
    - 提取类型信息（对于 typed 语言）
    - 最近编辑的文件列表
    """

    def __init__(self, config: LanguageConfig | None = None) -> None:
        self.config: dict[str, LanguageConfig] = {}

    def get_config(self, language: str) -> LanguageConfig:
        return LANGUAGE_CONFIGS.get(language, LanguageConfig())

    def assemble(
        self,
        file_content: str,
        cursor_line: int,
        cursor_column: int,
        file_path: str = "",
        language: str = "",
        recent_files: list[str] | None = None,
    ) -> CursorContext:
        """从文件内容构建 CursorContext"""
        if not language:
            language = self._infer_language(file_path)

        lines = file_content.split("\n") if file_content else [""]

        # 前缀：光标前的行 + 当前行光标前部分
        prefix_lines = lines[:cursor_line]
        prefix_current = lines[cursor_line][:cursor_column] if cursor_line < len(lines) else ""
        prefix = "\n".join(prefix_lines + [prefix_current])

        # 后缀：当前行光标后部分 + 光标后的行
        suffix_current = lines[cursor_line][cursor_column:] if cursor_line < len(lines) else ""
        suffix_lines = lines[cursor_line + 1:] if cursor_line + 1 < len(lines) else []
        suffix = "\n".join([suffix_current] + suffix_lines)

        # 截断
        lang_config = self.get_config(language)
        prefix_lines_list = prefix.split("\n")
        if len(prefix_lines_list) > lang_config.max_prefix_lines:
            prefix = "\n".join(prefix_lines_list[-lang_config.max_prefix_lines:])

        suffix_lines_list = suffix.split("\n")
        if len(suffix_lines_list) > lang_config.max_suffix_lines:
            suffix = "\n".join(suffix_lines_list[:lang_config.max_suffix_lines])

        if len(prefix) > lang_config.max_context_chars:
            prefix = prefix[-lang_config.max_context_chars:]
        if len(suffix) > lang_config.max_context_chars:
            suffix = suffix[:lang_config.max_context_chars]

        return CursorContext(
            prefix=prefix,
            suffix=suffix,
            file_path=file_path,
            language=language,
            file_content=file_content,
            cursor_line=cursor_line,
            cursor_column=cursor_column,
        )

    def _infer_language(self, file_path: str) -> str:
        """从文件路径推断语言"""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".vue": "vue",
            ".svelte": "vue",
            ".go": "go",
            ".rs": "rust",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".java": "java",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".sql": "sql",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".md": "markdown",
        }
        ext = Path(file_path).suffix.lower()
        return ext_map.get(ext, "")

    def extract_imports(self, file_content: str, language: str) -> list[str]:
        """提取文件中的所有 import 语句"""
        lang_config = self.get_config(language)
        pattern = re.compile(lang_config.import_pattern, re.MULTILINE)
        return [m.group(0).strip() for m in pattern.finditer(file_content)]

    def extract_functions(self, file_content: str, language: str) -> list[str]:
        """提取文件中的所有函数/类/方法签名"""
        lang_config = self.get_config(language)
        pattern = re.compile(
            rf"^[ \t]*({lang_config.function_pattern}).*$",
            re.MULTILINE,
        )
        return [m.group(0).strip() for m in pattern.finditer(file_content)]


# ══════════════════════════════════════════════════════════════
# 补全排名器
# ══════════════════════════════════════════════════════════════


class CompletionRanker:
    """补全结果排序器

    多维度评分：
    - prefix_match: 与前缀的字符级匹配（编辑距离）
    - type_match: 类型/模式匹配（对 typed 语言）
    - liveness: 活跃度（最近使用的 API/函数/变量）
    - semantic: 语义相关性（如果有）
    """

    def __init__(self) -> None:
        self._freq_map: dict[str, int] = {}  # 函数/变量使用频率
        self._recent_items: list[str] = []    # 最近使用的项 (FIFO)

    def record_usage(self, identifier: str) -> None:
        """记录标识符使用（增加活跃度）"""
        self._freq_map[identifier] = self._freq_map.get(identifier, 0) + 1
        self._recent_items.append(identifier)
        if len(self._recent_items) > 500:
            self._recent_items = self._recent_items[-200:]

    def rank(
        self,
        completions: list[CompletionItem],
        prefix: str = "",
        language: str = "",
        context_imports: list[str] | None = None,
    ) -> list[CompletionItem]:
        """对补全列表进行多维度评分和排序"""
        for item in completions:
            # 前缀匹配度 (Jaccard / 编辑距离)
            item.prefix_match_score = self._score_prefix_match(item.text, prefix)

            # 类型匹配度 (启发式)
            item.type_match_score = self._score_type_match(item.text, language)

            # 活跃度
            item.liveness_score = self._score_liveness(item.text)

            # 综合评分 (加权)
            item.score = (
                item.prefix_match_score * 0.40
                + item.type_match_score * 0.25
                + item.liveness_score * 0.20
                + item.semantic_score * 0.15
            )

        # 排序 + 去重
        seen: set[str] = set()
        unique: list[CompletionItem] = []
        for item in sorted(completions, key=lambda x: x.score, reverse=True):
            normalized = item.text.strip()
            if normalized not in seen:
                seen.add(normalized)
                unique.append(item)

        return unique

    def _score_prefix_match(self, text: str, prefix: str) -> float:
        """前缀匹配评分 — 基于公共前缀长度"""
        if not prefix or not text:
            return 0.3  # 无前缀信息，给中等分数

        # 按行匹配
        prefix_last_line = prefix.rstrip().split("\n")[-1]
        text_first_line = text.lstrip().split("\n")[0]

        if not prefix_last_line or not text_first_line:
            return 0.3

        # 最长公共前缀
        common_len = 0
        min_len = min(len(prefix_last_line), len(text_first_line))
        for i in range(min_len):
            if prefix_last_line[i] == text_first_line[i]:
                common_len += 1
            else:
                break

        ratio = common_len / max(len(prefix_last_line), 1)
        return min(ratio, 1.0)

    def _score_type_match(self, text: str, language: str) -> float:
        """类型匹配评分 — 检查补全是否匹配语言模式"""
        score = 0.5  # 默认中等

        # Python: 检查是否有 def/class/import
        if language == "python":
            if re.match(r"^\s*def |^\s*class |^\s*async def ", text):
                score += 0.2
            if re.match(r"^\s*import |^\s*from ", text):
                score += 0.1

        # TypeScript/JavaScript
        elif language in ("typescript", "javascript"):
            if re.match(r"^\s*(export )?(async )?function ", text):
                score += 0.2
            if re.match(r"^\s*(export )?class |^\s*(export )?interface ", text):
                score += 0.2

        return min(score, 1.0)

    def _score_liveness(self, text: str) -> float:
        """活跃度评分 — 基于使用频率"""
        # 从补全文本中提取标识符
        identifiers = re.findall(r"\b[a-zA-Z_]\w*\b", text[:100])
        if not identifiers:
            return 0.3

        # 取最大频率
        max_freq = max(
            (self._freq_map.get(ident, 0) for ident in identifiers),
            default=0,
        )

        if max_freq == 0:
            return 0.3
        # 对数缩放
        import math
        return min(0.3 + 0.7 * math.log(max_freq + 1) / 10, 1.0)


# ══════════════════════════════════════════════════════════════
# 缓存层
# ══════════════════════════════════════════════════════════════


class CompletionCache:
    """补全缓存 — LRU + 文件指纹

    策略：
    1. 以 (file_hash, cursor_line, cursor_col, prefix_hash) 为 key
    2. LRU 淘汰（默认 1000 条）
    3. 文件内容变更自动 invalidate
    """

    def __init__(self, max_size: int = 1000) -> None:
        self._cache: OrderedDict[str, CompletionResult] = OrderedDict()
        self._max_size = max_size
        self._file_fingerprints: dict[str, str] = {}
        self._hits = 0
        self._misses = 0

    def _make_key(self, context: CursorContext) -> str:
        """生成缓存键"""
        prefix_hash = hashlib.md5(
            context.prefix[-500:].encode()
        ).hexdigest()[:12]
        suffix_hash = hashlib.md5(
            context.suffix[:200].encode()
        ).hexdigest()[:12]
        return f"{context.file_path}:{context.cursor_line}:{context.cursor_column}:{prefix_hash}:{suffix_hash}"

    def _file_fingerprint(self, file_path: str) -> str:
        """文件指纹 (mtime + size)"""
        try:
            stat = os.stat(file_path)
            return f"{stat.st_mtime}:{stat.st_size}"
        except OSError:
            return ""

    def is_stale(self, file_path: str) -> bool:
        """检查缓存的指纹是否过期"""
        fp = self._file_fingerprint(file_path)
        if not fp:
            return True
        old_fp = self._file_fingerprints.get(file_path, "")
        return fp != old_fp

    def get(self, context: CursorContext) -> CompletionResult | None:
        """获取缓存结果"""
        if self.is_stale(context.file_path):
            self._invalidate_file(context.file_path)
            self._misses += 1
            return None

        key = self._make_key(context)
        result = self._cache.get(key)
        if result is not None:
            # Move to end (LRU)
            self._cache.move_to_end(key)
            self._hits += 1
            return result

        self._misses += 1
        return None

    def put(self, context: CursorContext, result: CompletionResult) -> None:
        """存入缓存"""
        # 更新文件指纹
        fp = self._file_fingerprint(context.file_path)
        if fp:
            self._file_fingerprints[context.file_path] = fp

        key = self._make_key(context)
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = result

        # LRU 淘汰
        while len(self._cache) > self._max_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]

    def _invalidate_file(self, file_path: str) -> None:
        """失效某个文件的所有缓存"""
        to_remove = [
            k for k in self._cache
            if k.startswith(f"{file_path}:")
        ]
        for k in to_remove:
            del self._cache[k]

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._file_fingerprints.clear()

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total > 0 else 0.0

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self.hit_rate, 4),
        }


# ══════════════════════════════════════════════════════════════
# FIM 补全引擎
# ══════════════════════════════════════════════════════════════


class FIMCompletionEngine:
    """FIM 代码补全引擎

    完整的代码补全管道：
    ContextAssembler → CompletionCache → FIM Prompt → ModelRouter → CompletionRanker → 返回
    """

    def __init__(
        self,
        assembler: ContextAssembler | None = None,
        ranker: CompletionRanker | None = None,
        cache: CompletionCache | None = None,
    ) -> None:
        self._assembler = assembler or ContextAssembler()
        self._ranker = ranker or CompletionRanker()
        self._cache = cache or CompletionCache()

    async def complete(
        self,
        file_content: str,
        cursor_line: int,
        cursor_column: int,
        file_path: str = "",
        language: str = "",
        trigger: CompletionTrigger = CompletionTrigger.KEYSTROKE,
        top_k: int = 5,
        temperature: float = 0.1,
        max_tokens: int = 256,
    ) -> CompletionResult:
        """执行代码补全

        Args:
            file_content: 完整文件内容
            cursor_line: 光标行号 (0-based)
            cursor_column: 光标列号 (0-based)
            file_path: 文件路径（用于语言推断和缓存）
            language: 编程语言（可选，自动推断）
            trigger: 触发类型
            top_k: 返回前 K 条结果
            temperature: 生成温度（越低越确定）
            max_tokens: 最大生成 token 数

        Returns:
            CompletionResult 包含排序后的补全列表
        """
        t_start = time.perf_counter()

        # 1. 组装上下文
        context = self._assembler.assemble(
            file_content, cursor_line, cursor_column,
            file_path=file_path, language=language,
        )

        # 2. 检查缓存
        cached = self._cache.get(context)
        if cached is not None:
            cached.cache_hit = True
            return cached

        # 3. 构建 FIM prompt
        lang_config = self._assembler.get_config(context.language)
        fim_prompt = self._build_fim_prompt(
            context.prefix,
            context.suffix,
            lang_config,
            context.language,
        )

        # 4. 调用模型
        result = await self._generate_completions(
            fim_prompt, context, trigger, top_k,
            temperature, max_tokens,
        )

        # 5. 排名
        context_imports = self._assembler.extract_imports(file_content, context.language)
        result.completions = self._ranker.rank(
            result.completions, prefix=context.prefix,
            language=context.language, context_imports=context_imports,
        )

        result.context = context
        result.total_latency_ms = (time.perf_counter() - t_start) * 1000

        # 6. 缓存
        self._cache.put(context, result)

        return result

    def _build_fim_prompt(
        self,
        prefix: str,
        suffix: str,
        config: LanguageConfig,
        language: str,
    ) -> str:
        """构建 FIM 格式的 prompt

        标准格式（DeepSeek / StarCoder 兼容）:
        师傅<fim_prefix>prefix<fim_suffix>suffix<fim_middle>
        """
        parts = [
            f"// Language: {language}\n",
            config.fim_prefix_token,
            prefix,
            config.fim_suffix_token,
            suffix,
            config.fim_middle_token,
        ]
        return "".join(parts)

    async def _generate_completions(
        self,
        fim_prompt: str,
        context: CursorContext,
        trigger: CompletionTrigger,
        top_k: int,
        temperature: float,
        max_tokens: int,
    ) -> CompletionResult:
        """调用模型生成补全"""
        result = CompletionResult()

        try:
            from app.core.model_router import get_model_router, ModelRequest, ModelCapability

            router = get_model_router()
            request = ModelRequest(
                messages=[{"role": "user", "content": fim_prompt}],
                capability=ModelCapability.CODE_GENERATION,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            response = await router.generate(request)

            # 解析模型返回为多条补全
            completions = self._parse_completions(
                response.content or "",
                top_k,
            )

            for comp in completions:
                comp.model_used = response.model_used or ""
                comp.provider = response.provider or ""
                comp.latency_ms = response.latency_ms or 0.0

            result.completions = completions
            result.model_used = response.model_used or ""
            result.provider = response.provider or ""

        except Exception as e:
            logger.warning("Code completion generation failed: %s", e)
            # Fallback: 返回空结果而非崩溃
            result.completions = []

        return result

    def _parse_completions(
        self,
        raw_text: str,
        top_k: int,
    ) -> list[CompletionItem]:
        """解析模型原始输出为多个候选补全"""
        if not raw_text or not raw_text.strip():
            return []

        # 按双换行分割多条补全
        candidates = re.split(r"\n{2,}", raw_text.strip())
        if len(candidates) < top_k:
            # 也按单换行分割
            candidates = [c.strip() for c in raw_text.strip().split("\n") if c.strip()]

        # 处理 FIM 标记残留
        clean = []
        for c in candidates:
            c = c.replace("<fim_prefix>", "").replace("<fim_suffix>", "").replace("<fim_middle>", "")
            c = c.replace("</fim_prefix>", "").replace("</fim_suffix>", "").replace("</fim_middle>", "")
            c = c.strip()
            if c:
                clean.append(c)

        # 去重 + 去前缀匹配部分
        seen = set()
        items: list[CompletionItem] = []
        for text in clean[:top_k * 2]:
            if text not in seen and len(text) > 0:
                seen.add(text)
                items.append(CompletionItem(
                    text=text,
                    display_text=text,
                    source="model",
                ))

        return items[:top_k]

    # ── 便捷方法 ────────────────────────────────────────

    def record_accept(self, completion_text: str) -> None:
        """记录用户接受了某条补全（反馈给 ranker）"""
        self._ranker.record_usage(completion_text.strip())

    def invalidate_cache(self, file_path: str) -> None:
        """失效指定文件的缓存"""
        self._cache._invalidate_file(file_path)

    @property
    def cache_stats(self) -> dict[str, Any]:
        """缓存统计"""
        return self._cache.stats


# ══════════════════════════════════════════════════════════════
# 注册为 Agent 工具
# ══════════════════════════════════════════════════════════════


def register_code_completion_tools() -> None:
    """注册代码补全相关工具到全局 ToolRegistry"""
    try:
        from app.core.tools.registry import register_tool
        from app.core.tools.schema import ToolParam, ParamType

        @register_tool(
            "code_completion",
            "Trigger code completion at the current cursor position. "
            "Provides intelligent code suggestions based on context. "
            "Returns top candidates sorted by relevance score.",
            [
                ToolParam("file_path", ParamType.STRING,
                          description="Absolute or workspace-relative file path"),
                ToolParam("file_content", ParamType.STRING,
                          description="Full current file content"),
                ToolParam("cursor_line", ParamType.INTEGER,
                          description="Cursor line number (0-based)"),
                ToolParam("cursor_column", ParamType.INTEGER,
                          description="Cursor column number (0-based)"),
                ToolParam("language", ParamType.STRING, required=False,
                          description="Programming language (inferred from extension if omitted)"),
                ToolParam("trigger", ParamType.STRING, required=False,
                          description="Completion trigger: keystroke|dot|import|function_call|newline|manual"),
                ToolParam("top_k", ParamType.INTEGER, required=False,
                          description="Number of completions to return (default: 5)"),
            ],
            category="code",
        )
        async def _code_completion(
            file_path: str,
            file_content: str,
            cursor_line: int,
            cursor_column: int,
            language: str = "",
            trigger: str = "manual",
            top_k: int = 5,
        ) -> str:
            """Agent 可调用的代码补全工具"""
            import json

            engine = get_completion_engine()
            try:
                trig = CompletionTrigger(trigger)
            except ValueError:
                trig = CompletionTrigger.MANUAL

            result = await engine.complete(
                file_content=file_content,
                cursor_line=cursor_line,
                cursor_column=cursor_column,
                file_path=file_path,
                language=language,
                trigger=trig,
                top_k=min(top_k, 10),
            )

            return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)

        @register_tool(
            "code_analyze_context",
            "Analyze the code context around a cursor position. "
            "Returns imports, function signatures, and variable declarations "
            "visible from the current scope. Useful for understanding code before editing.",
            [
                ToolParam("file_path", ParamType.STRING,
                          description="Absolute or workspace-relative file path"),
                ToolParam("file_content", ParamType.STRING,
                          description="Full current file content"),
                ToolParam("cursor_line", ParamType.INTEGER,
                          description="Cursor line number (0-based)"),
                ToolParam("language", ParamType.STRING, required=False,
                          description="Programming language"),
            ],
            category="code",
        )
        async def _code_analyze_context(
            file_path: str,
            file_content: str,
            cursor_line: int,
            language: str = "",
        ) -> str:
            """分析代码上下文"""
            import json

            assembler = ContextAssembler()
            if not language:
                language = assembler._infer_language(file_path)

            imports = assembler.extract_imports(file_content, language)
            functions = assembler.extract_functions(file_content, language)

            # 找出光标附近的函数/类
            lines = file_content.split("\n")
            nearby: list[str] = []
            for i in range(max(0, cursor_line - 10), min(len(lines), cursor_line + 5)):
                line = lines[i].rstrip()
                if line and not line.startswith(("#", "//", "/*", "*")):
                    nearby.append(f"L{i+1}: {line}")

            return json.dumps({
                "file_path": file_path,
                "language": language,
                "cursor_line": cursor_line,
                "imports": imports[:30],
                "top_level_definitions": functions[:30],
                "nearby_code": nearby[:20],
            }, ensure_ascii=False, indent=2)

        logger.info("Code completion tools registered: code_completion, code_analyze_context")

    except Exception as e:
        logger.warning("Failed to register code completion tools: %s", e)


# ══════════════════════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════════════════════

_completion_engine: FIMCompletionEngine | None = None


def get_completion_engine() -> FIMCompletionEngine:
    """获取全局 FIMCompletionEngine 单例"""
    global _completion_engine
    if _completion_engine is None:
        _completion_engine = FIMCompletionEngine()
        register_code_completion_tools()
    return _completion_engine


def init_completion_engine(
    assembler: ContextAssembler | None = None,
    ranker: CompletionRanker | None = None,
    cache: CompletionCache | None = None,
) -> FIMCompletionEngine:
    """初始化全局 FIMCompletionEngine"""
    global _completion_engine
    _completion_engine = FIMCompletionEngine(
        assembler=assembler,
        ranker=ranker,
        cache=cache,
    )
    register_code_completion_tools()
    return _completion_engine
