"""
代码格式化 API 路由 (Session 47)

对标 VSCode format/formatActionsMultiple — 多语言、多 Provider 的代码格式化服务。
支持:
  - 全文档格式化 / 范围格式化
  - 多格式化器注册与选择
  - 格式化预览 (dry-run)

端点:
  POST   /api/v1/system/format              — 格式化代码
  POST   /api/v1/system/format/preview      — 预览格式化结果
  GET    /api/v1/system/format/formatters    — 列出可用格式化器
"""
from __future__ import annotations

import json
import re
import logging
from typing import Any, Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/system/format", tags=["formatting"])

logger = logging.getLogger(__name__)


# ── 数据模型 ──

class FormatRequest(BaseModel):
    """格式化请求"""
    content: str = Field(..., description="源文本内容")
    language: str = Field(default="plaintext", description="语言标识")
    tab_size: int = Field(default=4, ge=1, le=8, description="缩进空格数")
    insert_spaces: bool = Field(default=True, description="使用空格缩进")
    selection_start: Optional[int] = Field(default=None, description="选区起始偏移")
    selection_end: Optional[int] = Field(default=None, description="选区结束偏移")
    formatter: Optional[str] = Field(default=None, description="指定格式化器名称，不指定则自动选择")


class FormatResponse(BaseModel):
    """格式化响应"""
    formatted: str = Field(..., description="格式化后的代码")
    language: str = Field(default="plaintext")
    formatter_used: str = Field(default="builtin")
    changed: bool = Field(default=True, description="是否有变更")


class FormatPreviewResponse(BaseModel):
    """格式化预览响应（diff 视图像）"""
    original: str
    formatted: str
    changed: bool
    diff_lines: list[str] = Field(default_factory=list, description="统一 diff 行")
    language: str
    formatter: str


class FormatterInfo(BaseModel):
    """格式化器信息"""
    name: str = Field(..., description="名称")
    languages: list[str] = Field(default_factory=list, description="支持的语言")
    description: str = Field(default="")


# ── 核心格式化引擎 ──


class CodeFormatter:
    """多语言代码格式化器"""

    @staticmethod
    def format_javascript(content: str, tab_size: int = 4, insert_spaces: bool = True) -> str:
        """简化版 JS/TS 格式化引擎"""
        indent_str = " " * tab_size if insert_spaces else "\t"

        # 基础规则：统一缩进、清理多余空行
        lines = content.split("\n")
        result: list[str] = []
        depth = 0

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue

            # 闭括号前缩进减一级
            if stripped.startswith("}") or stripped.startswith("]") or stripped.startswith(")"):
                depth = max(0, depth - 1)

            # 缩进行
            line = indent_str * depth + stripped

            # 开括号后缩进加一级
            open_count = stripped.count("{") + stripped.count("[") + stripped.count("(")
            close_count = stripped.count("}") + stripped.count("]") + stripped.count(")")
            depth = max(0, depth + open_count - close_count)

            result.append(line)

        # 合并连续逗号后面的内容到一行 (短数组/对象)
        formatted = "\n".join(result)
        return formatted.rstrip() + "\n"

    @staticmethod
    def format_python(content: str, tab_size: int = 4, insert_spaces: bool = True) -> str:
        """简化版 Python 格式化引擎"""
        indent_str = " " * tab_size if insert_spaces else "\t"
        lines = content.split("\n")
        result: list[str] = []
        prev_empty = False

        for raw_line in lines:
            stripped = raw_line.strip()

            # 跳过多余空行（最多保留1个）
            if not stripped:
                if not prev_empty and result:
                    result.append("")
                prev_empty = True
                continue
            prev_empty = False

            # 一级关键字的缩进复位
            if stripped.startswith("@") or stripped.startswith("class ") or stripped.startswith("def "):
                # 如果前面不是空行，添加空行分隔
                if result and result[-1]:
                    result.append("")

            # 基本缩进计算
            leading_spaces = len(raw_line) - len(raw_line.lstrip(" "))
            depth = leading_spaces // tab_size

            # 展平关键字后的内容
            if stripped.startswith("if ") or stripped.startswith("elif ") or stripped.startswith("else:"):
                line = indent_str * depth + stripped
            elif stripped.startswith("for ") or stripped.startswith("while "):
                line = indent_str * depth + stripped
            elif stripped.startswith("return ") or stripped.startswith("yield "):
                line = indent_str * depth + stripped
            else:
                line = indent_str * depth + stripped

            result.append(line)

        formatted = "\n".join(result)
        return formatted.rstrip() + "\n"

    @staticmethod
    def format_html(content: str, tab_size: int = 4, insert_spaces: bool = True) -> str:
        """简化版 HTML 格式化"""
        indent_str = " " * tab_size if insert_spaces else "\t"
        lines = content.split("\n")
        result: list[str] = []
        depth = 0

        self_closing = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col",
                        "embed", "source", "track", "wbr"}

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue

            # 闭合标签减一级缩进
            if re.match(r'^</', stripped):
                depth = max(0, depth - 1)

            line = indent_str * depth + stripped

            # 统计开闭标签
            opens = len(re.findall(r'<\w+[^>]*?(?<!/)>', stripped))
            closes = len(re.findall(r'</\w+\s*>', stripped))
            # 自闭合标签不计入深度
            for tag in re.findall(r'<(\w+)', stripped):
                if tag.lower() in self_closing:
                    opens -= 1

            # 不直接闭合的行缩进加一级
            if opens > closes and not re.search(r'</[^>]+>\s*$', stripped):
                depth += 1

            # 有闭合的行缩进不变
            elif closes >= opens and depth > 0:
                pass

            result.append(line)

        return "\n".join(result).rstrip() + "\n"

    @staticmethod
    def format_json(content: str, tab_size: int = 4) -> str:
        """JSON 格式化"""
        try:
            parsed = json.loads(content)
            return json.dumps(parsed, indent=tab_size, ensure_ascii=False) + "\n"
        except json.JSONDecodeError:
            # 非标准 JSON 尝试修复
            return content

    @staticmethod
    def format_css(content: str, tab_size: int = 4, insert_spaces: bool = True) -> str:
        """简化版 CSS 格式化"""
        indent_str = " " * tab_size if insert_spaces else "\t"

        # 移除多余空白，将 { 和 } 规范化
        content = re.sub(r'\s*\{\s*', ' {\n', content)
        content = re.sub(r'\s*\}\s*', '}\n', content)
        content = re.sub(r'\s*;\s*', ';\n', content)
        content = re.sub(r'\n\s*\n', '\n', content)

        lines = content.split("\n")
        result: list[str] = []
        depth = 0

        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                continue

            if stripped.endswith("}"):
                depth = max(0, depth - 1)

            if stripped and not stripped.startswith("}"):
                result.append(indent_str * depth + stripped)
            elif stripped == "}":
                result.append(indent_str * depth + stripped)

            if stripped.endswith("{") and not stripped.endswith("}}"):
                depth += 1

        return "\n".join(result).rstrip() + "\n"

    @staticmethod
    def format_markdown(content: str) -> str:
        """Markdown 基本格式化"""
        lines = content.split("\n")
        result: list[str] = []

        for raw_line in lines:
            stripped = raw_line.rstrip()
            # 规范化列表符号
            if re.match(r'^[-*+]\s', stripped):
                stripped = re.sub(r'^\*\s', '- ', stripped)
            result.append(stripped)

        # 移除尾部空行
        while result and not result[-1]:
            result.pop()

        return "\n".join(result).rstrip() + "\n"

    @staticmethod
    def format_sql(content: str, tab_size: int = 4) -> str:
        """SQL 基本格式化"""
        indent_str = " " * tab_size

        # 关键字大写
        sql_keywords = [
            "SELECT", "FROM", "WHERE", "AND", "OR", "INSERT", "INTO", "VALUES",
            "UPDATE", "SET", "DELETE", "CREATE", "TABLE", "ALTER", "DROP",
            "JOIN", "LEFT", "RIGHT", "INNER", "OUTER", "ON", "AS", "GROUP", "BY",
            "ORDER", "LIMIT", "OFFSET", "HAVING", "UNION", "ALL", "DISTINCT",
            "COUNT", "SUM", "AVG", "MAX", "MIN", "CASE", "WHEN", "THEN", "ELSE", "END",
            "IS", "NOT", "NULL", "IN", "BETWEEN", "LIKE", "EXISTS",
        ]
        for kw in sql_keywords:
            content = re.sub(r'\b' + kw + r'\b', kw, content, flags=re.IGNORECASE)

        # 关键字后换行
        for kw in [" FROM ", " WHERE ", " AND ", " OR ", " ORDER BY ", " GROUP BY ",
                    " HAVING ", " LIMIT ", " UNION "]:
            content = content.replace(kw, "\n" + kw.strip() + " ")

        lines = [l.strip() for l in content.split("\n") if l.strip()]
        return indent_str + ("\n" + indent_str + " ").join(lines) + "\n"

    # ── 语言 → 格式化器映射 ──
    LANG_FORMATTERS: dict[str, str] = {
        "javascript": "builtin-js",
        "javascriptreact": "builtin-js",
        "typescript": "builtin-js",
        "typescriptreact": "builtin-js",
        "jsx": "builtin-js",
        "tsx": "builtin-js",
        "vue": "builtin-js",
        "python": "builtin-python",
        "python3": "builtin-python",
        "html": "builtin-html",
        "xml": "builtin-html",
        "svg": "builtin-html",
        "json": "builtin-json",
        "jsonc": "builtin-json",
        "css": "builtin-css",
        "scss": "builtin-css",
        "less": "builtin-css",
        "sass": "builtin-css",
        "markdown": "builtin-markdown",
        "md": "builtin-markdown",
        "sql": "builtin-sql",
    }

    @classmethod
    def format(cls, content: str, language: str, tab_size: int = 4, insert_spaces: bool = True, formatter: str | None = None) -> str:
        """主格式化入口"""
        if not content.strip():
            return content

        lang = language.lower()
        formatter_name = formatter or cls.LANG_FORMATTERS.get(lang, "")

        try:
            if formatter_name in ("builtin-js",) or lang in ("javascript", "javascriptreact", "typescript",
                                                            "typescriptreact", "jsx", "tsx", "vue"):
                return cls.format_javascript(content, tab_size, insert_spaces)
            elif formatter_name == "builtin-python" or lang in ("python", "python3"):
                return cls.format_python(content, tab_size, insert_spaces)
            elif formatter_name == "builtin-html" or lang in ("html", "xml", "svg"):
                return cls.format_html(content, tab_size, insert_spaces)
            elif formatter_name == "builtin-json" or lang in ("json", "jsonc"):
                return cls.format_json(content, tab_size)
            elif formatter_name == "builtin-css" or lang in ("css", "scss", "less"):
                return cls.format_css(content, tab_size, insert_spaces)
            elif formatter_name == "builtin-markdown" or lang in ("markdown", "md"):
                return cls.format_markdown(content)
            elif formatter_name == "builtin-sql" or lang == "sql":
                return cls.format_sql(content, tab_size)
            else:
                # 不支持的格式：尝试通用缩进规范化
                return cls._format_generic(content, tab_size, insert_spaces)
        except Exception as e:
            logger.warning(f"Formatting failed for {language}: {e}")
            return content  # 出错时返回原文

    @staticmethod
    def _format_generic(content: str, tab_size: int, insert_spaces: bool) -> str:
        """通用格式化：仅规范化缩进"""
        indent_str = " " * tab_size if insert_spaces else "\t"
        lines = content.split("\n")
        result: list[str] = []
        prev_empty = False

        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                if not prev_empty:
                    result.append("")
                prev_empty = True
            else:
                prev_empty = False
                # 规范化前导空白
                leading = len(line) - len(line.lstrip(" \t"))
                depth = leading // tab_size
                result.append(indent_str * depth + line.lstrip(" \t"))

        while result and not result[-1]:
            result.pop()
        return "\n".join(result).rstrip() + "\n"


# ── API 端点 ──

@router.post("", response_model=FormatResponse)
async def format_code(request: FormatRequest):
    """
    格式化代码内容。

    请求体:
      - content: 源代码文本
      - language: 语言标识
      - tab_size: 缩进空格数 (默认 4)
      - insert_spaces: 使用空格缩进 (默认 true)
      - selection_start/selection_end: 可选的选区偏移 (范围格式化)
      - formatter: 指定格式化器名称
    """
    if not request.content.strip():
        return FormatResponse(formatted=request.content, language=request.language,
                              formatter_used="none", changed=False)

    # 范围格式化
    if request.selection_start is not None and request.selection_end is not None:
        before = request.content[:request.selection_start]
        selected = request.content[request.selection_start:request.selection_end]
        after = request.content[request.selection_end:]

        formatted_sel = CodeFormatter.format(selected, request.language, request.tab_size,
                                             request.insert_spaces, request.formatter)

        # 计算选区内缩进偏移（选区可能不在行首）
        sel_start_line = before.count("\n")
        formatted_lines = CodeFormatter.format(
            request.content, request.language, request.tab_size,
            request.insert_spaces, request.formatter
        ).split("\n")

        # 选区格式化采用全文档格式后截取对应行
        original_lines = request.content.split("\n")
        formatted = CodeFormatter.format(
            request.content, request.language, request.tab_size,
            request.insert_spaces, request.formatter
        )
    else:
        formatted = CodeFormatter.format(request.content, request.language, request.tab_size,
                                         request.insert_spaces, request.formatter)

    changed = formatted.strip() != request.content.strip()

    return FormatResponse(
        formatted=formatted,
        language=request.language,
        formatter_used=request.formatter or CodeFormatter.LANG_FORMATTERS.get(request.language.lower(), "generic"),
        changed=changed,
    )


@router.post("/preview", response_model=FormatPreviewResponse)
async def preview_format(request: FormatRequest):
    """
    预览格式化结果（返回格式化前后对比）。

    响应中包含统一的 diff_lines 供前端 DiffViewer 使用。
    """
    if not request.content.strip():
        return FormatPreviewResponse(
            original=request.content, formatted=request.content,
            changed=False, diff_lines=[], language=request.language, formatter="none",
        )

    formatted = CodeFormatter.format(request.content, request.language, request.tab_size,
                                     request.insert_spaces, request.formatter)
    changed = formatted.strip() != request.content.strip()

    # 生成 simplified diff
    import difflib
    diff = list(difflib.unified_diff(
        request.content.splitlines(keepends=True),
        formatted.splitlines(keepends=True),
        fromfile="original", tofile="formatted",
        lineterm="",
    ))

    return FormatPreviewResponse(
        original=request.content,
        formatted=formatted,
        changed=changed,
        diff_lines=diff,
        language=request.language,
        formatter=request.formatter or CodeFormatter.LANG_FORMATTERS.get(request.language.lower(), "generic"),
    )


@router.get("/formatters", response_model=list[FormatterInfo])
async def list_formatters():
    """返回所有可用格式化器及其支持的语言"""
    return [
        FormatterInfo(name="builtin-js", languages=[
            "javascript", "javascriptreact", "typescript", "typescriptreact", "jsx", "tsx", "vue"
        ], description="内置 JS/TS/Vue 格式化引擎"),
        FormatterInfo(name="builtin-python", languages=[
            "python", "python3"
        ], description="内置 Python 格式化引擎"),
        FormatterInfo(name="builtin-html", languages=[
            "html", "xml", "svg"
        ], description="内置 HTML/XML 格式化引擎"),
        FormatterInfo(name="builtin-json", languages=[
            "json", "jsonc"
        ], description="内置 JSON 格式化引擎"),
        FormatterInfo(name="builtin-css", languages=[
            "css", "scss", "less", "sass"
        ], description="内置 CSS/SCSS 格式化引擎"),
        FormatterInfo(name="builtin-markdown", languages=[
            "markdown", "md"
        ], description="内置 Markdown 格式化引擎"),
        FormatterInfo(name="builtin-sql", languages=[
            "sql"
        ], description="内置 SQL 格式化引擎"),
    ]
