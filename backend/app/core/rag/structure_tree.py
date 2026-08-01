"""
文档结构树 — 借鉴 RAGFlow 的标题层级解析

从解析后的文本中提取标题层级（Markdown/HTML 风格 # H1~H6），
构建可序列化的树形结构，辅助用户理解文档组织。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HeadingNode:
    """标题节点（可序列化）"""
    level: int  # 1~6
    text: str
    position: int  # 在原文中的字符偏移
    children: list[HeadingNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "text": self.text,
            "position": self.position,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> HeadingNode:
        node = cls(
            level=data["level"],
            text=data["text"],
            position=data["position"],
        )
        node.children = [cls.from_dict(c) for c in data.get("children", [])]
        return node


def extract_headings(text: str, max_headings: int = 200) -> list[HeadingNode]:
    """从 Markdown/文本中提取标题层级列表（行级解析）

    识别模式：
    - Markdown: `# Title`, `## Sub Title`, `### Sub-sub`
    - HTML-like: `<h1>`, `<h2>`, `<h3>`
    - 纯文本大写行 + 末尾无标点（宽松）

    返回所有标题节点组成的扁平列表，调用者负责构建树。
    """
    headings: list[HeadingNode] = []
    offset = 0

    for line in text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped:
            offset += len(line) + 1
            continue

        level = 0
        title_text = ""

        # Markdown 风格
        md_match = re.match(r"^(#{1,6})\s+(.+)$", line_stripped)
        if md_match:
            level = len(md_match.group(1))
            title_text = md_match.group(2).strip()
        # HTML 风格
        elif (html_match := re.match(r"^<h([1-6])>(.*?)</h\1>$", line_stripped, re.IGNORECASE)):
            level = int(html_match.group(1))
            title_text = html_match.group(2).strip()
        # 纯文本宽松 (全大写短行, 无标点结尾) — 只作为 H1 候选
        elif (
            len(line_stripped) <= 80
            and line_stripped.isascii()
            and line_stripped == line_stripped.upper()
            and not re.search(r"[.,;:!?。，；：！？]$", line_stripped)
            and not re.match(r"^[-\s]*$", line_stripped)
        ):
            level = 1
            title_text = line_stripped

        if level and title_text:
            headings.append(HeadingNode(
                level=level,
                text=title_text[:120],
                position=offset,
            ))

        if len(headings) >= max_headings:
            break

        offset += len(line) + 1

    return headings


def build_tree(headings: list[HeadingNode]) -> list[HeadingNode]:
    """将扁平标题列表构建为树形结构

    规则：level N 的标题是级别 < N 的最近标题的子节点。
    """
    root: list[HeadingNode] = []
    # stack 保存 (level, node) 作为当前嵌套路径
    stack: list[list[HeadingNode]] = [root]

    for node in headings:
        # 回退 stack 直到找到合适的父级
        while len(stack) > 1 and stack[-2] is not root and node.level <= len(stack) - 1:
            stack.pop()

        # 找到挂载点
        parent_list = stack[-1]
        parent_list.append(node)
        # 将新节点作为子级容器压入 stack
        stack.append(node.children)

    return root


def annotate_chunks_with_headings(
    text: str,
    headings: list[HeadingNode],
) -> dict[int, str]:
    """计算每个字符位置对应的标题路径（BFS 前缀）

    返回: {char_position: "H1 > H2 > H3"} 映射，适合 chunk 定位。
    """
    if not headings:
        return {}

    path_map: dict[int, str] = {}
    current_path: list[str] = []

    # 构建 tree 获取正确层级关系
    tree = build_tree(headings)

    def _walk(nodes: list[HeadingNode], path_prefix: list[str]):
        for n in nodes:
            p = path_prefix + [n.text]
            path_map[n.position] = " > ".join(p)
            _walk(n.children, p)

    _walk(tree, [])
    return path_map


def get_heading_path_for_chunk(
    chunk_start: int,
    heading_positions: dict[int, str],
) -> Optional[str]:
    """给定 chunk 的起始偏移，返回其所属的标题路径

    chunk 属于 ≤ 其起始偏移的最近标题。
    """
    if not heading_positions:
        return None
    # 找到 ≤ chunk_start 的最大 key
    candidate = None
    for pos, path in sorted(heading_positions.items()):
        if pos <= chunk_start:
            candidate = path
        else:
            break
    return candidate


def structure_tree_to_markdown(tree: list[HeadingNode], prefix: str = "") -> str:
    """将结构化树转为 Markdown 目录"""
    lines: list[str] = []
    for node in tree:
        indent = "  " * (node.level - 1)
        lines.append(f"{indent}- {node.text}")
        if node.children:
            lines.append(structure_tree_to_markdown(node.children, prefix))
    return "\n".join(lines)
