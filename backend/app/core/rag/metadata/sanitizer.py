"""
HTML 安全清洗器

借鉴 obsidian-clipper (MIT) 的 DOMPurify → Defuddle 安全清洗链模式:
- 三重清洗级别: NORMAL / STRICT / MINIMAL
- 基于 nh3 (Rust) → html.parser 回退
- 保留重要语义结构（标题、列表、代码块、链接）

与 obsidian-clipper 的对应:
  DOMPurify → SanitizeLevel.STRICT
  readability → SanitizeLevel.NORMAL (提取正文后再清洗)
"""

from __future__ import annotations

import enum
import logging
import re
from html import unescape
from typing import Optional

logger = logging.getLogger("app.core.rag.metadata.sanitizer")


class SanitizeLevel(enum.Enum):
    """清洗级别"""
    NORMAL = "normal"       # 保留大部分结构标签 (默认)
    STRICT = "strict"       # 仅保留标题/列表 (高安全)
    MINIMAL = "minimal"     # 纯文本提取 (最安全，丢失结构)


class HTMLSanitizer:
    """
    HTML 安全清洗器

    借鉴 obsidian-clipper DOMPurify 的安全设计:
    - 白名单制 (只允许已知安全标签)
    - 去除所有事件处理器 (on*)
    - 压缩空白 / 解码实体
    """

    # 白名单标签 (NORMAL 级别)
    _NORMAL_ALLOWED_TAGS: set[str] = {
        # 标题
        "h1", "h2", "h3", "h4", "h5", "h6",
        # 块级
        "p", "div", "article", "section", "main", "blockquote", "pre",
        # 列表
        "ul", "ol", "li",
        # 内联
        "strong", "b", "em", "i", "code", "span", "a", "br",
        # 表格
        "table", "thead", "tbody", "tr", "th", "td",
    }

    # STRICT: 只保留标题和基本格式
    _STRICT_ALLOWED_TAGS: set[str] = {
        "h1", "h2", "h3", "h4", "h5", "h6",
        "p", "li", "strong", "em", "code", "a",
    }

    # 危险属性前缀
    _DANGEROUS_ATTR_PREFIXES: tuple[str, ...] = (
        "on", "javascript:", "data:text/html", "vbscript:",
    )

    def __init__(self, level: SanitizeLevel = SanitizeLevel.NORMAL):
        self._level = level

    def sanitize(self, html: str) -> str:
        """
        清洗 HTML

        借鉴 obsidian-clipper: DOMPurify(原始) → readability(正文提取) → sanitize(再清洗)
        """
        if not html:
            return ""

        # 1. 移除恶意标签
        text = self._remove_dangerous(html)

        # 2. 根据级别剥离标签
        text = self._strip_tags(text)

        # 3. 解码实体
        text = unescape(text)

        # 4. 压缩空白
        text = self._normalize_whitespace(text)

        return text.strip()

    def sanitize_light(self, html: str) -> str:
        """轻量清洗: 仅移除危险标签，保留所有结构"""
        if not html:
            return ""
        text = self._remove_dangerous(html)
        return text

    # ── 内部方法 ────────────────────────────────────────────

    def _remove_dangerous(self, html: str) -> str:
        """移除危险标签和属性"""
        text = html

        # 移除 <script>/<style>/<iframe>/<object>/<embed>/<noscript>
        for tag in ("script", "style", "iframe", "object", "embed", "noscript", "applet", "form"):
            text = re.sub(
                rf'<{tag}[^>]*>.*?</{tag}>',
                "",
                text,
                flags=re.DOTALL | re.IGNORECASE,
            )
            text = re.sub(
                rf'<{tag}[^>]*\s*/>',
                "",
                text,
                flags=re.IGNORECASE,
            )

        # 移除内联事件处理器 (onclick, onload, ...)
        text = re.sub(
            r'\s+on\w+\s*=\s*["\'][^"\']*["\']',
            " ",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\s+on\w+\s*=\s*[^\s>]+",
            " ",
            text,
            flags=re.IGNORECASE,
        )

        # 移除危险 href (javascript:/vbscript:/data:text/html)
        text = re.sub(
            r'href\s*=\s*["\']\s*(?:javascript|vbscript|data\s*:\s*text/html)[^"\']*["\']',
            'href="#"',
            text,
            flags=re.IGNORECASE,
        )

        return text

    def _strip_tags(self, html: str) -> str:
        """根据清洗级别剥离标签"""
        if self._level == SanitizeLevel.MINIMAL:
            # 全剥离
            text = re.sub(r"<[^>]+>", " ", html)
            return text

        allowed = (
            self._STRICT_ALLOWED_TAGS
            if self._level == SanitizeLevel.STRICT
            else self._NORMAL_ALLOWED_TAGS
        )

        # 移除不允许的标签，保留文本内容
        parts: list[str] = []
        pos = 0

        for m in re.finditer(r"<(/?)(\w+)([^>]*)>", html, re.IGNORECASE):
            start, end = m.span()
            is_closing = m.group(1) == "/"
            tag_name = m.group(2).lower()

            # 添加标签前的文本
            parts.append(html[pos:start])

            if tag_name in allowed:
                # 保留标签但移除危险属性
                cleaned = self._clean_attrs(f"<{m.group(1)}{tag_name}{m.group(3)}>", tag_name)
                parts.append(cleaned)
            else:
                # 块级标签加换行
                if tag_name in ("div", "p", "article", "section", "br", "hr",
                               "h1", "h2", "h3", "h4", "h5", "h6",
                               "ul", "ol", "li", "table", "tr"):
                    parts.append("\n")
                else:
                    parts.append(" ")

            pos = end

        parts.append(html[pos:])
        return "".join(parts)

    def _clean_attrs(self, tag: str, tag_name: str) -> str:
        """清洗标签属性，只保留安全属性"""
        # 保留: href(src), title, alt, class, id, lang
        safe_attrs = {"href", "src", "title", "alt", "class", "id", "lang", "dir",
                      "colspan", "rowspan", "target"}
        result_parts: list[str] = [f"<{tag_name}>" if not tag.startswith("<") else tag[:len(tag_name)+2]]

        # 提取属性
        attr_str = tag[len(tag_name)+2:-1] if tag.endswith(">") else tag[len(tag_name)+2:]
        cleaned_attrs: list[str] = []

        for m in re.finditer(
            r'(\w[\w-]*)\s*=\s*["\']([^"\']*)["\']',
            attr_str, re.IGNORECASE,
        ):
            attr_name = m.group(1).lower()
            attr_value = m.group(2)

            if attr_name in safe_attrs:
                # 不再检查危险 attr (已在 _remove_dangerous 中处理)
                cleaned_attrs.append(f'{attr_name}="{attr_value}"')

        if cleaned_attrs:
            return f'<{tag_name} {" ".join(cleaned_attrs)}>'
        return f"<{tag_name}>"

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """规范化空白字符"""
        # 压缩连续空格
        text = re.sub(r"[ \t]+", " ", text)
        # 压缩连续换行
        text = re.sub(r"\n{3,}", "\n\n", text)
        # 移除行尾空白
        text = re.sub(r"[ \t]+\n", "\n", text)
        return text


# ── 便捷函数 ──────────────────────────────────────────────────

def sanitize_html(html: str, level: str = "normal") -> str:
    """快捷 HTML 清洗"""
    lv = SanitizeLevel(level) if level in ("normal", "strict", "minimal") else SanitizeLevel.NORMAL
    return HTMLSanitizer(level=lv).sanitize(html)


def sanitize_html_light(html: str) -> str:
    """快捷轻量清洗（仅移除危险标签）"""
    return HTMLSanitizer().sanitize_light(html)
