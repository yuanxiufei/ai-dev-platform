"""
文本过滤器链 — 借鉴 obsidian-clipper filters/ 的可组合管道模式

obsidian-clipper 有 50+ 个基于 Nunjucks-Jinja2 的过滤器。我们借鉴其设计理念，
实现一个可组合的 Python 过滤器链，用于 RAG 文档摄入的预处理/后处理。

过滤器类型 (借鉴 obsidian-clipper):
  remove_html       — 去除 HTML 标签
  strip_md          — 去除 Markdown 格式
  remove_urls       — 移除 URL
  remove_boilerplate— 移除页面模板噪音
  extract_code      — 提取代码块
  normalize_ws      — 规范化空白
  truncate          — 截断到指定长度
  deduplicate_lines — 行级去重
  remove_pre        — 移除前缀模式
  safe_filename     — 安全文件名
"""

from __future__ import annotations

import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

logger = logging.getLogger("app.core.rag.filters")

# ── 便捷函数 ──────────────────────────────────────────────


# ── Filter 基类 ───────────────────────────────────────────

class BaseFilter(ABC):
    """文本过滤器基类 — 借鉴 obsidian-clipper filter 模式"""

    @abstractmethod
    def apply(self, text: str, **kwargs: Any) -> str:
        """应用过滤"""

    def __or__(self, other: "BaseFilter") -> "FilterChain":
        """管道操作符: filter_a | filter_b → FilterChain"""
        return FilterChain([self, other])

    def __ror__(self, other: "FilterChain") -> "FilterChain":
        """反向管道: chain | filter"""
        if isinstance(other, FilterChain):
            other.filters.append(self)
            return other
        return FilterChain([self])


class FilterChain(BaseFilter):
    """过滤器链 — 可组合 + 可动态增删"""

    def __init__(self, filters: list[BaseFilter] | None = None):
        self.filters: list[BaseFilter] = filters or []

    def add(self, f: BaseFilter) -> "FilterChain":
        """添加过滤器"""
        self.filters.append(f)
        return self

    def apply(self, text: str, **kwargs: Any) -> str:
        """依次应用所有过滤器"""
        result = text
        for f in self.filters:
            try:
                result = f.apply(result, **kwargs)
            except Exception as e:
                logger.warning("Filter '%s' failed: %s", f.__class__.__name__, e)
        return result

    def __call__(self, text: str, **kwargs: Any) -> str:
        return self.apply(text, **kwargs)

    def __or__(self, other: BaseFilter) -> "FilterChain":
        self.filters.append(other)
        return self


# ── 内置过滤器 ─────────────────────────────────────────────

class RemoveHTMLFilter(BaseFilter):
    """去除 HTML 标签 — 借鉴 obsidian-clipper remove_html"""

    def apply(self, text: str, **kwargs: Any) -> str:
        from app.core.rag.metadata.sanitizer import HTMLSanitizer, SanitizeLevel
        level = kwargs.get("sanitize_level", SanitizeLevel.NORMAL)
        return HTMLSanitizer(level=level).sanitize(text)


class StripMarkdownFilter(BaseFilter):
    """去除 Markdown 格式 — 借鉴 obsidian-clipper strip_md"""

    def apply(self, text: str, **kwargs: Any) -> str:
        # 去除粗体/斜体/删除线
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"\1", text)
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"~~(.+?)~~", r"\1", text)
        # 去除行内代码
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # 去除图片
        text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
        # 链接只保留文本
        text = re.sub(r"\[([^\]]+)\]\(.*?\)", r"\1", text)
        # 去除标题标记
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        # 去除块引用
        text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
        # 去除水平线
        text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
        return text


class RemoveURLsFilter(BaseFilter):
    """移除 URL — 借鉴 obsidian-clipper remove_urls"""

    _URL_PATTERN = re.compile(
        r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[^\s\'"<>]*)?'
    )

    def apply(self, text: str, **kwargs: Any) -> str:
        if kwargs.get("keep_domains"):
            return text  # 保留 URL 模式
        return self._URL_PATTERN.sub(" [URL] ", text)


class RemoveBoilerplateFilter(BaseFilter):
    """
    移除页面模板噪音 — 借鉴 obsidian-clipper readability 思路

    删除常见噪音片段:
    - Cookie / GDPR 同意横幅
    - 导航栏残余文本
    - 页脚/版权声明
    - 面包屑导航
    - "Subscribe / Sign Up / Log In" 行
    """

    _BOILERPLATE_PATTERNS: list[re.Pattern] = []

    def __init__(self):
        patterns = [
            # Cookie / GDPR
            r'(?i)(?:this\s+site\s+uses?\s+cookies?[^.]*\.)',
            r'(?i)(?:we\s+use\s+cookies?[^.]*\.)',
            r'(?i)(?:accept\s+(?:all\s+)?cookies?)',
            r'(?i)(?:cookie\s+(?:preferences|settings))',
            # 导航残骸
            r'(?i)^(?:\s*(?:home|about|contact|login|sign\s*(?:up|in))\s*\|?\s*){2,}',
            r'(?i)^\s*(?:menu|navigation|skip\s+to\s+content)\s*$',
            # 社交媒体残骸
            r'(?i)(?:follow\s+us\s+on\s+|share\s+on\s+)(?:twitter|facebook|instagram|linkedin|youtube)',
            r'(?i)(?:subscribe\s+(?:to\s+)?(?:our\s+)?(?:newsletter|channel|feed|updates))',
            # 版权/页脚残骸
            r'(?i)^\s*©\s*\d{4}.*$',
            r'(?i)^\s*(?:all\s+rights?\s+reserved\.?)\s*$',
            r'(?i)^\s*(?:terms\s+(?:of\s+(?:service|use)|&?\s*conditions)|privacy\s+policy)',
            # 面包屑
            r'(?i)^\s*you\s+are\s+here\s*:\s*',
            r'(?i)(?:\s+[>»›]\s+){2,}',
            # 评论区残骸
            r'(?i)^\s*(?:\d+\s+)?(?:comments?|replies?|responses?)\s*$',
            r'(?i)^\s*(?:leave\s+a\s+comment|add\s+comment|reply)\s*$',
        ]
        self._patterns = [re.compile(p) for p in patterns]

    def apply(self, text: str, **kwargs: Any) -> str:
        result = text
        for p in self._patterns:
            result = p.sub("", result)
        return result


class ExtractCodeFilter(BaseFilter):
    """提取代码块 — 借鉴 obsidian-clipper"""

    _FENCE_PATTERN = re.compile(
        r'```(\w*)\n(.*?)```', re.DOTALL
    )

    def apply(self, text: str, **kwargs: Any) -> str:
        code_blocks = self._FENCE_PATTERN.findall(text)
        if not code_blocks:
            return text
        languages: dict[str, list[str]] = {}
        for lang, code in code_blocks:
            languages.setdefault(lang or "text", []).append(code.strip())

        result_parts = [text]
        result_parts.append("\n\n--- Extracted Code Blocks ---")
        for lang, blocks in languages.items():
            result_parts.append(f"\n### {lang}")
            for i, b in enumerate(blocks, 1):
                result_parts.append(f"\n```{lang}\n{b}\n```")
        return "\n".join(result_parts)


class NormalizeWhitespaceFilter(BaseFilter):
    """规范化空白 — 借鉴 obsidian-clipper"""

    def apply(self, text: str, **kwargs: Any) -> str:
        # 压缩连续空格
        text = re.sub(r"[ \t]+", " ", text)
        # 压缩连续换行 (保留最多双换行)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 移除行尾空白
        text = re.sub(r"[ \t]+\n", "\n", text)
        # 移除行首空白
        text = re.sub(r"\n[ \t]+", "\n", text)
        return text.strip()


class TruncateFilter(BaseFilter):
    """截断 — 借鉴 obsidian-clipper slice / truncate"""

    def apply(self, text: str, **kwargs: Any) -> str:
        max_len = kwargs.get("max_length", 8192)
        if len(text) <= max_len:
            return text
        # 尝试在词边界截断
        truncated = text[:max_len]
        last_space = truncated.rfind(" ")
        if last_space > max_len * 0.8:
            truncated = truncated[:last_space]
        return truncated + ("..." if kwargs.get("add_ellipsis", True) else "")


class DeduplicateLinesFilter(BaseFilter):
    """行级去重 — 保留首次出现的顺序"""

    def apply(self, text: str, **kwargs: Any) -> str:
        seen: set[str] = set()
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and stripped not in seen:
                seen.add(stripped)
                lines.append(line)
            elif not stripped:
                lines.append(line)  # 保留空行
        return "\n".join(lines)


class RemovePrefixFilter(BaseFilter):
    """移除前缀模式 — 借鉴 obsidian-clipper"""

    def apply(self, text: str, **kwargs: Any) -> str:
        prefix = kwargs.get("prefix", "")
        if not prefix:
            return text
        if isinstance(prefix, str):
            prefix = re.escape(prefix)
        return re.sub(rf"^{prefix}", "", text, flags=re.MULTILINE)


class SafeFilenameFilter(BaseFilter):
    """安全文件名 — 借鉴 obsidian-clipper safe_name"""

    def apply(self, text: str, **kwargs: Any) -> str:
        # 保留字母数字和部分特殊字符
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
        # 替换不安全字符
        text = re.sub(r'[<>:"/\\|?*\'#\[\]]', "-", text)
        # 压缩连字符
        text = re.sub(r"-{2,}", "-", text)
        # 截断
        max_len = kwargs.get("max_length", 128)
        text = text[:max_len].strip(" -_.")
        return text or "untitled"


# ── 预设过滤器链 ──────────────────────────────────────────

def create_rag_ingest_chain() -> FilterChain:
    """RAG 摄入用过滤器链"""
    return FilterChain([
        RemoveHTMLFilter(),
        RemoveBoilerplateFilter(),
        RemoveURLsFilter(),
        NormalizeWhitespaceFilter(),
        DeduplicateLinesFilter(),
    ])


def create_markdown_clean_chain() -> FilterChain:
    """Markdown 清洗过滤器链"""
    return FilterChain([
        StripMarkdownFilter(),
        RemoveURLsFilter(),
        NormalizeWhitespaceFilter(),
    ])


def create_webpage_clean_chain() -> FilterChain:
    """网页内容清洗过滤器链"""
    return FilterChain([
        RemoveHTMLFilter(),
        RemoveBoilerplateFilter(),
        RemoveURLsFilter(),
        NormalizeWhitespaceFilter(),
        DeduplicateLinesFilter(),
        TruncateFilter(),
    ])


# ── 元数据过滤 DSL ──────────────────────────────────────────
# 借鉴 RAGFlow Where 过滤设计，支持复合条件"


class WhereFilter:
    """
    统一元数据过滤 DSL — 支持复合条件查询

    运算符:
        $eq / 隐式  — 等于
        $ne         — 不等于
        $gt/$gte    — 大于/大于等于
        $lt/$lte    — 小于/小于等于
        $in/$nin   — 在列表中 / 不在列表中
        $contains   — LIKE %value%
        $regex      — SQLite REGEXP
        $exists     — 字段存在(true) / 不存在(false)
        $and / $or  — 逻辑组合

    Example:
        {
            "source": "docs",
            "date": {"$gte": "2024-01-01"},
            "$or": [{"category": "python"}, {"category": "fastapi"}]
        }
    """

    _OPS = {
        "$eq": "=",
        "$ne": "!=",
        "$gt": ">",
        "$gte": ">=",
        "$lt": "<",
        "$lte": "<=",
    }

    @classmethod
    def to_sql(cls, filter_dict: dict | None) -> tuple[str, list]:
        """
        将 filter 字典转换为 SQL WHERE 子句和参数列表。

        Returns:
            ("WHERE ...", [params]) 或 ("", [])（无过滤条件时）
        """
        if not filter_dict:
            return "", []

        clauses, params = cls._build_clauses(filter_dict)
        if not clauses:
            return "", []
        return "WHERE " + " AND ".join(clauses), params

    @classmethod
    def _build_clauses(cls, filter_dict: dict) -> tuple[list[str], list]:
        """递归构建 SQL 子句"""
        clauses: list[str] = []
        params: list = []

        for key, value in filter_dict.items():
            if key == "$or":
                or_clauses, or_params = cls._build_logical(value, "OR")
                if or_clauses:
                    clauses.append("(" + " OR ".join(or_clauses) + ")")
                    params.extend(or_params)
            elif key == "$and":
                and_clauses, and_params = cls._build_logical(value, "AND")
                if and_clauses:
                    clauses.append("(" + " AND ".join(and_clauses) + ")")
                    params.extend(and_params)
            elif isinstance(value, dict):
                # 运算符风格键过滤: {field: {$op: val}}
                for op, op_val in value.items():
                    sql, p = cls._op_to_sql(key, op, op_val)
                    if sql:
                        clauses.append(sql)
                        params.extend(p)
            else:
                # 简单等值: {field: value}
                clauses.append(f"metadata->>'{key}' = %s")
                params.append(str(value))

        return clauses, params

    @classmethod
    def _build_logical(
        cls, conditions: list[dict], operator: str
    ) -> tuple[list[str], list]:
        """构建 $and / $or 逻辑组合"""
        sub_clauses: list[str] = []
        all_params: list = []
        for cond in conditions:
            inner, inner_params = cls._build_clauses(cond)
            if inner:
                sub_clauses.append("(" + " AND ".join(inner) + ")")
                all_params.extend(inner_params)
        return sub_clauses, all_params

    @classmethod
    def _op_to_sql(cls, field: str, op: str, value) -> tuple[str, list]:
        """将单个运算符转为 SQL 片段（PostgreSQL jsonb 语法）"""
        col = f"metadata->>'{field}'"

        if op in cls._OPS:
            return f"{col} {cls._OPS[op]} %s", [str(value)]

        if op == "$in":
            if not isinstance(value, list) or not value:
                return "", []
            placeholders = ",".join(["%s"] * len(value))
            return f"{col} IN ({placeholders})", [str(v) for v in value]

        if op == "$nin":
            if not isinstance(value, list) or not value:
                return "", []
            placeholders = ",".join(["%s"] * len(value))
            return f"{col} NOT IN ({placeholders})", [str(v) for v in value]

        if op == "$contains":
            return f"{col} LIKE %s", [f"%{value}%"]

        if op == "$regex":
            return f"{col} ~ %s", [str(value)]

        if op == "$exists":
            if value:
                return (
                    f"(metadata->>'{field}' IS NOT NULL "
                    f"AND metadata->>'{field}' != '')",
                    [],
                )
            return (
                f"(metadata->>'{field}' IS NULL "
                f"OR metadata->>'{field}' = '')",
                [],
            )

        logger.warning("Unknown filter operator: %s on field '%s'", op, field)
        return "", []

    # ── 向量后过滤（内存匹配）────────────────────────────────

    @classmethod
    def match(cls, metadata: dict, filter_dict: dict | None) -> bool:
        """
        检查 metadata 是否匹配 filter dict。
        用于向量搜索后的内存级别后过滤。
        """
        if not filter_dict:
            return True

        for key, value in filter_dict.items():
            if key == "$or":
                if not any(cls.match(metadata, cond) for cond in value):
                    return False
            elif key == "$and":
                if not all(cls.match(metadata, cond) for cond in value):
                    return False
            elif isinstance(value, dict):
                for op, op_val in value.items():
                    if not cls._eval_op(metadata.get(key), op, op_val):
                        return False
            else:
                # 简单等值比较
                if str(metadata.get(key, "")) != str(value):
                    return False

        return True

    @classmethod
    def _eval_op(cls, field_val, op: str, target_val) -> bool:
        """内存评估单个运算符"""
        try:
            if op == "$eq" or op not in {
                "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin",
                "$contains", "$regex", "$exists",
            }:
                return str(field_val) == str(target_val)
            if op == "$ne":
                return str(field_val) != str(target_val)
            if op == "$gt":
                return float(field_val) > float(target_val)
            if op == "$gte":
                return float(field_val) >= float(target_val)
            if op == "$lt":
                return float(field_val) < float(target_val)
            if op == "$lte":
                return float(field_val) <= float(target_val)
            if op == "$in":
                return str(field_val) in [str(v) for v in target_val]
            if op == "$nin":
                return str(field_val) not in [str(v) for v in target_val]
            if op == "$contains":
                return str(target_val) in str(field_val)
            if op == "$regex":
                return bool(re.search(str(target_val), str(field_val)))
            if op == "$exists":
                if target_val:
                    return field_val is not None and str(field_val).strip() != ""
                return field_val is None or str(field_val).strip() == ""
        except (ValueError, TypeError):
            return False
        return False


# ── 导出注册表 ─────────────────────────────────────────────

BUILTIN_FILTERS: dict[str, type[BaseFilter]] = {
    "remove_html":       RemoveHTMLFilter,
    "strip_md":          StripMarkdownFilter,
    "remove_urls":       RemoveURLsFilter,
    "remove_boilerplate":RemoveBoilerplateFilter,
    "extract_code":      ExtractCodeFilter,
    "normalize_ws":      NormalizeWhitespaceFilter,
    "truncate":          TruncateFilter,
    "deduplicate_lines": DeduplicateLinesFilter,
    "remove_pre":        RemovePrefixFilter,
    "safe_filename":     SafeFilenameFilter,
}


def build_filter_chain(filter_names: list[str]) -> FilterChain:
    """根据名称列表构建过滤器链"""
    chain = FilterChain()
    for name in filter_names:
        cls = BUILTIN_FILTERS.get(name)
        if cls:
            chain.add(cls())
        else:
            logger.warning("Unknown filter: %s", name)
    return chain
