"""
知识图谱引擎 — 借鉴 Obsidian (Wikilinks + JSON Canvas + Frontmatter)

核心能力：
- WikiLinks 解析 — [[entry]] 双向链接 + 反向链接索引
- Frontmatter 元数据 — tags/aliases/status/dates 结构化属性
- JSON Canvas 生成 — 从 Memory 关系自动生成知识图谱（node/edge/group）
- Callouts 解析 — 富文本块（note/warning/tip/info/danger）

Spec: https://jsoncanvas.org/spec/1.0/
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("app.core.knowledge_graph")

# ── 常量 ───────────────────────────────────────────────

CANVAS_VERSION = "1.0"
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
CALLOUT_RE = re.compile(r">\s*\[!(\w+)\]([+-])?\s*(.*)", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
TAG_RE = re.compile(r"#([\w\-/]+)")

CANVAS_COLORS = {"1": "#E74C3C", "2": "#E67E22", "3": "#F1C40F", "4": "#2ECC71", "5": "#1ABC9C", "6": "#9B59B6"}

CALLOUT_COLORS = {
    "note":      "4",
    "tip":       "5",
    "info":      "5",
    "warning":   "2",
    "danger":    "1",
    "bug":       "1",
    "example":   "4",
    "quote":     "3",
    "todo":      "6",
    "question":  "6",
    "success":   "4",
    "failure":   "1",
    "abstract":  "6",
    "important": "1",
}


# ── 数据结构 ───────────────────────────────────────────

@dataclass
class WikiLink:
    """解析后的 [[link]]"""
    target: str
    display: Optional[str] = None
    heading: Optional[str] = None
    block_id: Optional[str] = None

    @property
    def target_key(self) -> str:
        return self.target.split("#")[0].split("|")[0].strip()


@dataclass
class ParsedFrontmatter:
    """解析后的 YAML frontmatter"""
    title: str = ""
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    status: str = ""
    priority: str = ""
    due_date: str = ""
    created: str = ""
    updated: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class CalloutBlock:
    """解析后的 Callout"""
    type: str          # note / warning / tip / info / danger ...
    title: str = ""
    content: str = ""
    folded_default: bool = False  # - 折叠, + 展开


@dataclass
class CanvasNode:
    """
    JSON Canvas 节点 — 完整兼容 JSON Canvas Spec 1.0

    借鉴 jsoncanvas (MIT) 规范:
      - text:  纯文本节点 (type="text" → 属性: text)
      - file:  文件引用节点 (type="file" → 属性: file, subpath)
      - link:  URL 引用节点 (type="link" → 属性: url)
      - group: 视觉容器节点 (type="group" → 属性: label, background, backgroundStyle)
    """
    id: str
    type: str  # text / file / link / group
    x: int = 0
    y: int = 0
    width: int = 400
    height: int = 200
    # text type
    text: str = ""
    # file type
    file: str = ""
    subpath: str = ""          # 以 # 开头的子路径（如 #heading 或 #^block）
    # link type
    url: str = ""
    # group type
    label: str = ""
    background: str = ""       # 背景图路径
    backgroundStyle: str = ""  # "cover" / "ratio" / "repeat"
    # common
    color: str = ""


@dataclass
class CanvasEdge:
    """JSON Canvas 边"""
    id: str
    fromNode: str
    toNode: str
    fromSide: str = ""
    toSide: str = ""
    fromEnd: str = "none"
    toEnd: str = "arrow"
    label: str = ""
    color: str = ""


@dataclass
class CanvasData:
    """完整的 Canvas 文件"""
    nodes: list[CanvasNode] = field(default_factory=list)
    edges: list[CanvasEdge] = field(default_factory=list)

    def to_dict(self) -> dict:
        """
        序列化为 JSON Canvas 格式字典

        注意: x/y 可能为 0 (合法值), 需要保留
        fromEnd="none" 也是规范默认值,需保留
        """
        def _filter_node(n: CanvasNode) -> dict:
            d = {}
            for k, v in n.__dict__.items():
                if v is not None and v != "":
                    d[k] = v
                elif k in ("x", "y"):
                    d[k] = v  # 0 是合法坐标
            # 始终确保 id/type 存在
            d.setdefault("id", n.id)
            d.setdefault("type", n.type)
            return d

        def _filter_edge(e: CanvasEdge) -> dict:
            d = {}
            for k, v in e.__dict__.items():
                if v is not None and v != "":
                    d[k] = v
            # 始终确保 id/fromNode/toNode 存在
            d.setdefault("id", e.id)
            d.setdefault("fromNode", e.fromNode)
            d.setdefault("toNode", e.toNode)
            return d

        return {
            "nodes": [_filter_node(n) for n in self.nodes],
            "edges": [_filter_edge(e) for e in self.edges],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass
class BacklinkIndex:
    """反向链接索引 — 谁链接到我"""
    target_key: str
    sources: list[str] = field(default_factory=list)  # 来源 memory key 列表
    count: int = 0


# ── 解析器 ─────────────────────────────────────────────

def parse_wikilinks(text: str) -> list[WikiLink]:
    """解析 [[target]] / [[target|display]] / [[target#heading]]"""
    results: list[WikiLink] = []
    for m in WIKILINK_RE.finditer(text):
        raw = m.group(1)
        link = WikiLink(target=raw)

        # 处理 #heading 或 #^block-id
        if "#" in raw:
            base, _, ref = raw.partition("#")
            link.target = base
            if ref.startswith("^"):
                link.block_id = ref[1:]
            else:
                link.heading = ref

        # 处理 |display
        if "|" in link.target:
            link.target, link.display = link.target.split("|", 1)
            link.target = link.target.strip()

        link.target = link.target.strip()
        results.append(link)
    return results


def parse_frontmatter(text: str) -> ParsedFrontmatter:
    """解析 YAML frontmatter（轻量解析，不依赖 PyYAML）"""
    fm = ParsedFrontmatter()
    m = FRONTMATTER_RE.match(text)
    if not m:
        return fm

    yaml_text = m.group(1)
    for line in yaml_text.split("\n"):
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("#"):
            continue

        if ":" in line_stripped:
            key, _, val = line_stripped.partition(":")
            key = key.strip()
            val = val.strip().strip("\"'")

            if key == "title":
                fm.title = val
            elif key == "tags" and val == "":
                pass  # tags as list handled below
            elif key == "aliases" and val == "":
                pass
            elif key == "status":
                fm.status = val
            elif key == "priority":
                fm.priority = val
            elif key == "due_date":
                fm.due_date = val
            elif key in ("date", "created"):
                fm.created = val
            elif key in ("updated",):
                fm.updated = val
            else:
                fm.extra[key] = val

        elif line_stripped.startswith("- ") and line_stripped[2:].strip():
            item_val = line_stripped[2:].strip().strip("\"'")
            # Determine which list we're in (crude but works)
            # Look back for last key
            _last_key = ""
            for pline in yaml_text[:yaml_text.find(line)].split("\n"):
                pline = pline.strip()
                if pline.endswith(":") and not pline.startswith("-"):
                    _last_key = pline[:-1].strip()
            if _last_key == "tags":
                fm.tags.append(item_val)
            elif _last_key == "aliases":
                fm.aliases.append(item_val)

    return fm


def parse_callouts(text: str) -> list[CalloutBlock]:
    """解析 > [!type] 格式的 Callout 块"""
    results: list[CalloutBlock] = []
    current: Optional[CalloutBlock] = None
    content_lines: list[str] = []

    for line in text.split("\n"):
        m = CALLOUT_RE.match(line)
        if m:
            if current:
                current.content = "\n".join(content_lines).strip()
                results.append(current)
                content_lines = []

            ctype = m.group(1).lower()
            fold = m.group(2) or ""
            title = m.group(3).strip() or ctype.capitalize()

            current = CalloutBlock(
                type=ctype,
                title=title,
                folded_default=(fold == "-"),
            )
        elif current and line.startswith(">"):
            # Continuation of callout
            content_lines.append(line[1:].strip())
        else:
            if current:
                current.content = "\n".join(content_lines).strip()
                results.append(current)
                current = None
                content_lines = []

    if current:
        current.content = "\n".join(content_lines).strip()
        results.append(current)

    return results


def extract_tags(text: str) -> list[str]:
    """提取 #tag 和 #nested/tag"""
    tags = set()
    for m in TAG_RE.finditer(text):
        tag = m.group(1)
        # Filter out markdown headings (## Heading)
        if tag and not tag.startswith("#"):
            tags.add(tag)
    return sorted(tags)


def parse_memory_value(value: str) -> dict:
    """
    完整解析 memory value — frontmatter + wikilinks + callouts + tags

    Returns: {
        "frontmatter": ParsedFrontmatter,
        "wikilinks": [WikiLink],
        "callouts": [CalloutBlock],
        "tags": [str],
        "plain_text": str  # 去除标记后的纯文本
    }
    """
    fm = parse_frontmatter(value)
    body = value
    fm_match = FRONTMATTER_RE.match(value)
    if fm_match:
        body = value[fm_match.end():]

    wikilinks = parse_wikilinks(body)
    callouts = parse_callouts(body)
    tags = extract_tags(body)

    # 提取纯文本
    plain = body
    plain = WIKILINK_RE.sub(r"\1", plain)
    plain = CALLOUT_RE.sub(r"[!\1] \3", plain)

    return {
        "frontmatter": fm,
        "wikilinks": wikilinks,
        "callouts": callouts,
        "tags": tags,
        "plain_text": plain.strip(),
    }


# ── 链接索引 ───────────────────────────────────────────

class LinkIndex:
    """
    双向链接索引管理器

    维护:
    - forward: { source_key: [target_keys...] }
    - backlinks: { target_key: [source_keys...] }
    """

    def __init__(self):
        self._forward: dict[str, list[str]] = {}
        self._backlinks: dict[str, list[str]] = {}

    def index_memory(self, key: str, value: str) -> list[WikiLink]:
        """索引一条记忆，返回发现的链接"""
        links = parse_wikilinks(value)
        targets = [l.target_key for l in links]

        # 正向链接
        self._forward[key] = targets

        # 反向链接 — 更新所有被链接指向的条目
        for tgt in targets:
            if tgt not in self._backlinks:
                self._backlinks[tgt] = []
            if key not in self._backlinks[tgt]:
                self._backlinks[tgt].append(key)

        return links

    def remove_memory(self, key: str) -> None:
        """移除一条记忆的索引"""
        targets = self._forward.pop(key, [])
        for tgt in targets:
            if tgt in self._backlinks and key in self._backlinks[tgt]:
                self._backlinks[tgt].remove(key)

    def get_forward_links(self, key: str) -> list[str]:
        """正向链接 — 我链接了谁"""
        return self._forward.get(key, [])

    def get_backlinks(self, key: str) -> list[str]:
        """反向链接 — 谁链接了我"""
        return list(set(self._backlinks.get(key, [])))

    def get_all_backlinks(self) -> list[BacklinkIndex]:
        """所有反向链接索引"""
        return [
            BacklinkIndex(target_key=k, sources=v, count=len(v))
            for k, v in self._backlinks.items() if v
        ]

    def get_orphans(self, all_keys: set[str]) -> list[str]:
        """孤立节点 — 没有任何链接的记忆"""
        linked = set(self._forward.keys()) | set(self._backlinks.keys())
        return sorted(all_keys - linked)

    def to_graph_data(self) -> dict:
        """转为图数据结构 {nodes: [{id,label}], edges: [{from,to}]}"""
        nodes = {}
        edges = []

        for src, tgts in self._forward.items():
            nodes[src] = True
            for tgt in tgts:
                nodes[tgt] = True
                edges.append({"from": src, "to": tgt})

        return {
            "nodes": [{"id": k, "label": k} for k in nodes],
            "edges": edges,
        }


# ── Canvas 生成器 ──────────────────────────────────────

class CanvasGenerator:
    """
    从 Memory 关系自动生成 JSON Canvas

    Usage:
        gen = CanvasGenerator()
        canvas = gen.from_link_index(link_index, memory_data)
        json_str = canvas.to_json()
    """

    def __init__(self):
        self._node_id_cache: dict[str, str] = {}
        self._auto_layout_x = 0
        self._auto_layout_y = 0
        self._col_width = 450
        self._row_height = 300
        self._cols = 3

    def _gen_id(self, seed: str = "") -> str:
        if seed and seed in self._node_id_cache:
            return self._node_id_cache[seed]
        raw = (seed + uuid.uuid4().hex) if seed else uuid.uuid4().hex
        hid = hashlib.md5(raw.encode()).hexdigest()[:16]
        if seed:
            self._node_id_cache[seed] = hid
        return hid

    def _next_pos(self) -> tuple[int, int]:
        x = self._auto_layout_x
        y = self._auto_layout_y
        self._auto_layout_x += self._col_width
        if self._auto_layout_x >= self._cols * self._col_width:
            self._auto_layout_x = 0
            self._auto_layout_y += self._row_height
        return x, y

    def from_memories(
        self,
        memories: list[dict],
        include_callouts: bool = True,
    ) -> CanvasData:
        """
        从记忆列表生成 Canvas

        Args:
            memories: [{"key": ..., "value": ..., "domain": ..., "importance": ...}, ...]
            include_callouts: 是否将 callout 转换为独立节点
        """
        canvas = CanvasData()
        link_index = LinkIndex()

        # 1. 索引所有 wikilinks
        for mem in memories:
            link_index.index_memory(mem["key"], mem.get("value", ""))

        # 2. 按 domain 分组
        domains: dict[str, list[dict]] = {}
        for mem in memories:
            d = mem.get("domain", "general")
            domains.setdefault(d, []).append(mem)

        # 3. 为每个 domain 创建 group + nodes
        for domain_name, mems in domains.items():
            group = self._create_domain_group(domain_name, mems)
            canvas.nodes.append(group)

            for idx, mem in enumerate(mems):
                node = self._memory_to_node(mem, group.id, idx)
                canvas.nodes.append(node)

                # 正向边
                for tgt in link_index.get_forward_links(mem["key"]):
                    edge = CanvasEdge(
                        id=self._gen_id(f"e_{mem['key']}_{tgt}"),
                        fromNode=node.id,
                        toNode=self._gen_id(tgt),
                        label="links to",
                        color="5",
                    )
                    canvas.edges.append(edge)

                # 反向边（防止重复）
                for src in link_index.get_backlinks(mem["key"]):
                    edge_id = f"back_{src}_{mem['key']}"
                    existing = [e for e in canvas.edges if e.id == self._gen_id(edge_id)]
                    if not existing:
                        edge = CanvasEdge(
                            id=self._gen_id(edge_id),
                            fromNode=self._gen_id(src),
                            toNode=node.id,
                            label="backlink",
                            color="3",
                            fromEnd="none",
                            toEnd="arrow",
                        )
                        canvas.edges.append(edge)

                # Callout 节点
                if include_callouts:
                    parsed = parse_memory_value(mem.get("value", ""))
                    callout_offset_y = 0
                    for co in parsed["callouts"]:
                        cn = self._callout_to_node(co, node.id, callout_offset_y)
                        canvas.nodes.append(cn)
                        edge = CanvasEdge(
                            id=self._gen_id(f"co_{mem['key']}_{co.type}"),
                            fromNode=node.id,
                            toNode=cn.id,
                            label=co.type,
                            color=CALLOUT_COLORS.get(co.type, "5"),
                        )
                        canvas.edges.append(edge)
                        callout_offset_y += 80

        return canvas

    def _create_domain_group(self, domain: str, mems: list[dict]) -> CanvasNode:
        x, y = self._next_pos()
        count = len(mems)
        return CanvasNode(
            id=self._gen_id(f"group_{domain}"),
            type="group",
            x=max(x - 20, -1000),
            y=max(y - 20, -1000),
            width=self._col_width - 60,
            height=count * self._row_height + 100,
            label=f"Domain: {domain}",
            color="4",
        )

    def _memory_to_node(self, mem: dict, group_id: str, index: int) -> CanvasNode:
        key = mem["key"]
        parsing = parse_memory_value(mem.get("value", ""))
        fm = parsing["frontmatter"]

        # Node text
        lines = [f"## {key}"]
        if fm.title:
            lines.append(f"*{fm.title}*")
        if fm.tags:
            lines.append(f"{' '.join(f'#{t}' for t in fm.tags)}")
        if fm.status:
            lines.append(f"Status: **{fm.status}**")
        if fm.priority:
            lines.append(f"Priority: {fm.priority}")

        importance = mem.get("importance", 0.5)
        if importance >= 0.8:
            color = "1"  # Red = high importance
        elif importance >= 0.5:
            color = "3"  # Yellow = medium
        else:
            color = "5"  # Cyan = low

        x, y = self._next_pos()
        return CanvasNode(
            id=self._gen_id(key),
            type="text",
            x=x,
            y=y,
            width=380,
            height=180,
            text="\n".join(lines),
            color=color,
        )

    def _callout_to_node(self, co: CalloutBlock, parent_node_id: str, offset_y: int = 0) -> CanvasNode:
        color = CALLOUT_COLORS.get(co.type, "5")
        text = f"[!{co.type}] {co.title}\n\n{co.content[:200]}"
        return CanvasNode(
            id=self._gen_id(f"callout_{parent_node_id}_{co.type}_{hash(co.content) & 0xFFFF}"),
            type="text",
            x=410,
            y=offset_y,
            width=300,
            height=min(60 + len(co.content) // 3, 200),
            text=text,
            color=color,
        )


# ── 导出 ───────────────────────────────────────────────

__all__ = [
    # 解析器
    "parse_wikilinks",
    "parse_frontmatter",
    "parse_callouts",
    "extract_tags",
    "parse_memory_value",
    # 数据结构
    "WikiLink",
    "ParsedFrontmatter",
    "CalloutBlock",
    "CanvasNode",
    "CanvasEdge",
    "CanvasData",
    "BacklinkIndex",
    # 引擎
    "LinkIndex",
    "CanvasGenerator",
    # 常量
    "CANVAS_COLORS",
    "CALLOUT_COLORS",
    "WIKILINK_RE",
    "CALLOUT_RE",
    "FRONTMATTER_RE",
    "TAG_RE",
]
