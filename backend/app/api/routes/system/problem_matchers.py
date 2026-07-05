"""
Problem Matchers — VSCode 任务输出解析器

借鉴 VSCode workbench/contrib/tasks/common/problemMatcher.ts
将构建/测试/终端输出解析为结构化诊断 (文件+行+列+严重级别+消息+代码)

功能:
  POST /system/problem-matchers/parse   — 用指定匹配器解析输出
  GET  /system/problem-matchers         — 列出所有内置+自定义匹配器
  POST /system/problem-matchers/custom  — 注册自定义匹配器
  DELETE /system/problem-matchers/custom/{id} — 删除自定义匹配器

架构:
  - 10+ 内置标准匹配器 (ESLint/TypeScript/Python/Go/Rust/C++/Java)
  - 支持 SingleLine / MultiLine 两种解析模式
  - 自定义匹配器持久化到 ~/.ai-fullstack/platform/problem-matchers.json
"""

import json
import re
import os
from pathlib import Path
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/system/problem-matchers", tags=["system"])


# ═══════════════════════════════════════════════════
# 类型定义
# ═══════════════════════════════════════════════════

class SeverityLevel(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    HINT = "hint"


class MatcherMode(str, Enum):
    SINGLE_LINE = "single_line"
    MULTI_LINE = "multi_line"


class ProblemPattern(BaseModel):
    """单个正则捕获组"""
    regexp: str
    file_group: int = 1
    line_group: int = 2
    column_group: Optional[int] = 3
    end_line_group: Optional[int] = None
    end_column_group: Optional[int] = None
    message_group: int = 4
    severity_group: Optional[int] = None
    code_group: Optional[int] = None
    kind: str = "file"  # file | location


class ProblemMatcherDef(BaseModel):
    """问题匹配器定义 (可序列化)"""
    id: str
    label: str
    owner: str = "build"
    source: str = ""
    mode: MatcherMode = MatcherMode.SINGLE_LINE
    pattern: ProblemPattern
    file_location: str = "relative"  # absolute | relative | autoDetect
    severity: SeverityLevel = SeverityLevel.ERROR
    watching: Optional[dict] = None  # { beginsPattern, endsPattern }


class ParseRequest(BaseModel):
    """解析请求"""
    matcher_id: str = Field(description="匹配器 ID，或 'auto' 自动检测")
    content: str = Field(description="构建/终端输出文本 (每行一条)")


class DiagnosticItem(BaseModel):
    """结构化诊断条目"""
    file_path: str
    line: int
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None
    severity: SeverityLevel
    message: str
    code: Optional[str] = None
    source: str = ""
    matcher: str = ""
    raw_line: str = ""


class ParseResponse(BaseModel):
    diagnostics: list[DiagnosticItem]
    total: int
    matcher_used: str
    lines_processed: int


# ═══════════════════════════════════════════════════
# 内置标准匹配器 (借鉴 VSCode problemMatchers)
# ═══════════════════════════════════════════════════

BUILTIN_MATCHERS: dict[str, ProblemMatcherDef] = {
    # ── JavaScript / TypeScript ──
    "eslint-compact": ProblemMatcherDef(
        id="eslint-compact",
        label="ESLint Compact",
        owner="eslint",
        source="eslint",
        pattern=ProblemPattern(
            regexp=r"^(.+):\s+line\s+(\d+),\s+col\s+(\d+),\s+(Error|Warning|Info)\s*-\s*(.+?)\s*\((.+?)\)\s*$",
            file_group=1, line_group=2, column_group=3,
            severity_group=4, message_group=5, code_group=6,
        ),
    ),
    "eslint-stylish": ProblemMatcherDef(
        id="eslint-stylish",
        label="ESLint Stylish",
        owner="eslint",
        source="eslint",
        pattern=ProblemPattern(
            regexp=r"^\s+(\d+):(\d+)\s+(error|warning)\s+(.+?)\s+(.+)$",
            line_group=1, column_group=2,
            severity_group=3, message_group=4, code_group=5,
            file_group=-1,  # 文件由上一行的非匹配行提供
        ),
        mode=MatcherMode.MULTI_LINE,
    ),
    "tsc": ProblemMatcherDef(
        id="tsc",
        label="TypeScript Compiler",
        owner="typescript",
        source="tsc",
        pattern=ProblemPattern(
            regexp=r"^(.+)\((\d+),(\d+)\):\s+(error|warning)\s+(TS\d+):\s+(.+)$",
            file_group=1, line_group=2, column_group=3,
            severity_group=4, message_group=6, code_group=5,
        ),
    ),
    # ── Python ──
    "python-flake8": ProblemMatcherDef(
        id="python-flake8",
        label="Python Flake8",
        owner="python",
        source="flake8",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):(\d+):\s+([EWCNF]\d{3})\s+(.+)$",
            file_group=1, line_group=2, column_group=3,
            code_group=4, message_group=5,
        ),
    ),
    "python-pylint": ProblemMatcherDef(
        id="python-pylint",
        label="Python Pylint",
        owner="python",
        source="pylint",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):(\d+):\s+([A-Z]\d{4}):\s+(.+)$",
            file_group=1, line_group=2, column_group=3,
            code_group=4, message_group=5,
        ),
    ),
    "python-mypy": ProblemMatcherDef(
        id="python-mypy",
        label="Python Mypy",
        owner="python",
        source="mypy",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):\s+(error|warning|note):\s+(.+?)(?:\s+\[(.+?)\])?\s*$",
            file_group=1, line_group=2,
            severity_group=3, message_group=4, code_group=5,
        ),
    ),
    "python-pytest": ProblemMatcherDef(
        id="python-pytest",
        label="Python pytest",
        owner="python",
        source="pytest",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):\s+(.+?:)?\s+(?:assert|raise\s+)?(.+)$",
            file_group=1, line_group=2, message_group=4, code_group=3,
        ),
    ),
    # ── Go ──
    "go-compiler": ProblemMatcherDef(
        id="go-compiler",
        label="Go Compiler",
        owner="go",
        source="go",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):(\d+):\s+(.+)$",
            file_group=1, line_group=2, column_group=3, message_group=4,
        ),
    ),
    "go-vet": ProblemMatcherDef(
        id="go-vet",
        label="Go Vet",
        owner="go",
        source="go vet",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):(\d+):\s+(.+)$",
            file_group=1, line_group=2, column_group=3, message_group=4,
        ),
    ),
    # ── Rust ──
    "rustc": ProblemMatcherDef(
        id="rustc",
        label="Rust Compiler",
        owner="rust",
        source="rustc",
        pattern=ProblemPattern(
            regexp=r"^(error|warning|note|help)\[?(.{1,10})\]?\]:\s+(.+)$",
            severity_group=1, code_group=2, message_group=3,
            # 文件/行来自前一行 "--> file:line:col" 模式
        ),
        mode=MatcherMode.MULTI_LINE,
    ),
    "rust-cargo": ProblemMatcherDef(
        id="rust-cargo",
        label="Rust Cargo Check",
        owner="rust",
        source="cargo",
        pattern=ProblemPattern(
            regexp=r"^\s+-->\s+(.+):(\d+):(\d+)$",
            file_group=1, line_group=2, column_group=3,
        ),
        mode=MatcherMode.MULTI_LINE,
    ),
    # ── C / C++ ──
    "mscompile": ProblemMatcherDef(
        id="mscompile",
        label="MSVC / MSBuild",
        owner="cpp",
        source="msbuild",
        pattern=ProblemPattern(
            regexp=r"^(.+)\((\d+)(?:,(\d+))?\)\s*:\s*(error|warning|info)\s+(\w+):\s+(.+)$",
            file_group=1, line_group=2, column_group=3,
            severity_group=4, code_group=5, message_group=6,
        ),
    ),
    "gcc": ProblemMatcherDef(
        id="gcc",
        label="GCC / G++",
        owner="cpp",
        source="gcc",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):(\d+):\s+(fatal\s+)?(error|warning|note):\s+(.+)$",
            file_group=1, line_group=2, column_group=3,
            severity_group=5, message_group=6,
        ),
    ),
    # ── Java ──
    "java-javac": ProblemMatcherDef(
        id="java-javac",
        label="Java Compiler (javac)",
        owner="java",
        source="javac",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):\s+(error|warning):\s+(.+)$",
            file_group=1, line_group=2, severity_group=3, message_group=4,
        ),
    ),
    # ── 通用 ──
    "generic-compiler": ProblemMatcherDef(
        id="generic-compiler",
        label="Generic Compiler (file:line: message)",
        owner="generic",
        source="compiler",
        pattern=ProblemPattern(
            regexp=r"^(.+):(\d+):?(\d+)?:?\s*(error|warning|info)?:?\s*(.+)$",
            file_group=1, line_group=2, column_group=3,
            severity_group=4, message_group=5,
        ),
    ),
}


# ═══════════════════════════════════════════════════
# 自定义匹配器持久化
# ═══════════════════════════════════════════════════

_CUSTOM_MATCHERS_FILE = Path.home() / ".ai-fullstack" / "platform" / "problem-matchers.json"
_custom_matchers: dict[str, ProblemMatcherDef] = {}


def _load_custom_matchers() -> None:
    """从磁盘加载自定义匹配器"""
    global _custom_matchers
    try:
        if _CUSTOM_MATCHERS_FILE.exists():
            data = json.loads(_CUSTOM_MATCHERS_FILE.read_text(encoding="utf-8"))
            _custom_matchers = {
                m["id"]: ProblemMatcherDef(**m)
                for m in data.get("matchers", [])
            }
    except Exception:
        _custom_matchers = {}


def _save_custom_matchers() -> None:
    """持久化自定义匹配器到磁盘"""
    _CUSTOM_MATCHERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "matchers": [m.model_dump() for m in _custom_matchers.values()],
        "version": 1,
    }
    _CUSTOM_MATCHERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# 启动加载
_load_custom_matchers()


def _get_all_matchers() -> dict[str, ProblemMatcherDef]:
    """获取所有匹配器 (内置 + 自定义, 自定义覆盖内置)"""
    all_matchers = dict(BUILTIN_MATCHERS)
    all_matchers.update(_custom_matchers)
    return all_matchers


# ═══════════════════════════════════════════════════
# 解析引擎
# ═══════════════════════════════════════════════════

def _parse_severity(raw: Optional[str]) -> SeverityLevel:
    """将字符串转换为 SeverityLevel"""
    if not raw:
        return SeverityLevel.ERROR
    raw_lower = raw.lower().strip()
    if raw_lower in ("error", "fatal", "err"):
        return SeverityLevel.ERROR
    if raw_lower in ("warning", "warn"):
        return SeverityLevel.WARNING
    if raw_lower in ("info", "information"):
        return SeverityLevel.INFO
    if raw_lower in ("hint", "note", "help"):
        return SeverityLevel.HINT
    return SeverityLevel.ERROR


def _apply_pattern(line: str, matcher: ProblemMatcherDef) -> Optional[DiagnosticItem]:
    """对单行应用匹配模式"""
    pattern = matcher.pattern
    try:
        m = re.match(pattern.regexp, line)
    except re.error:
        return None
    if not m:
        return None

    groups = m.groups()
    total_groups = len(groups)

    def _group(idx: int) -> Optional[str]:
        if idx <= 0 or idx > total_groups:
            return None
        val = groups[idx - 1]
        return val.strip() if val else None

    file_path = _group(pattern.file_group) or ""
    line_num = _group(pattern.line_group)
    col_num = _group(pattern.column_group)
    end_line = _group(pattern.end_line_group)
    end_col = _group(pattern.end_column_group)
    message = _group(pattern.message_group) or "unknown error"
    severity_raw = _group(pattern.severity_group)
    code = _group(pattern.code_group)

    return DiagnosticItem(
        file_path=file_path,
        line=int(line_num) if line_num and line_num.isdigit() else 1,
        column=int(col_num) if col_num and col_num.isdigit() else None,
        end_line=int(end_line) if end_line and end_line.isdigit() else None,
        end_column=int(end_col) if end_col and end_col.isdigit() else None,
        severity=_parse_severity(severity_raw),
        message=message,
        code=code,
        source=matcher.source,
        matcher=matcher.id,
        raw_line=line.rstrip(),
    )


def _parse_single_line(matcher: ProblemMatcherDef, content: str) -> list[DiagnosticItem]:
    """单行解析：每行独立匹配"""
    results: list[DiagnosticItem] = []
    for line in content.splitlines():
        if not line.strip():
            continue
        diag = _apply_pattern(line, matcher)
        if diag:
            results.append(diag)
    return results


def _parse_multi_line(matcher: ProblemMatcherDef, content: str) -> list[DiagnosticItem]:
    """多行解析：跟踪文件上下文 (借鉴 VSCode MultiLineMatcher)"""
    results: list[DiagnosticItem] = []
    lines = content.splitlines()
    current_file: Optional[str] = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        # 对于多行模式，尝试直接匹配
        diag = _apply_pattern(line, matcher)
        if diag:
            # 多行匹配器可能只提供行/列但无文件，使用上下文文件
            if not diag.file_path and current_file:
                diag.file_path = current_file
            if diag.message and diag.message.strip():
                results.append(diag)
            continue

        # 回退：尝试推断文件上下文 (行不含错误标记但看起来像文件路径)
        # 检测 rustc 风格: "--> file:line:col"
        rust_arrow = re.match(r"^\s*-->\s+(.+):(\d+):(\d+)$", stripped)
        if rust_arrow:
            current_file = rust_arrow.group(1)
            # 继续查找下一行的消息
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                msg_match = re.match(r"^(error|warning|note|help)\[?(.{1,10})\]?\]:\s+(.+)$", next_line)
                if msg_match:
                    results.append(DiagnosticItem(
                        file_path=current_file,
                        line=int(rust_arrow.group(2)),
                        column=int(rust_arrow.group(3)),
                        severity=_parse_severity(msg_match.group(1)),
                        code=msg_match.group(2),
                        message=msg_match.group(3),
                        source=matcher.source,
                        matcher=matcher.id,
                        raw_line=line.rstrip(),
                    ))
            continue

        # eslint-stylish: 文件头行 "path/to/file"
        if current_file is None and not re.search(r"[:=]", stripped):
            if "/" in stripped or "." in stripped:
                current_file = stripped

    return results


def _parse_content(content: str, matcher: ProblemMatcherDef) -> list[DiagnosticItem]:
    """主解析入口"""
    if matcher.mode == MatcherMode.SINGLE_LINE:
        return _parse_single_line(matcher, content)
    else:
        return _parse_multi_line(matcher, content)


def _auto_detect_matcher(content: str) -> Optional[ProblemMatcherDef]:
    """自动检测最适合的匹配器"""
    first_line = content.strip().split("\n")[0] if content.strip() else ""

    # 特征向量检测
    detection_order = [
        ("rustc", r"^\s*-->\s+|^(error|warning|note|help)\[.{1,10}\]"),
        ("tsc", r"TS\d+"),
        ("eslint-stylish", r"^\s+\d+:\d+\s+(error|warning)"),
        ("python-flake8", r"[EWCNF]\d{3}"),
        ("python-pylint", r"[A-Z]\d{4}:"),
        ("mscompile", r"\)\s*:\s*(error|warning)\s+\w+"),
        ("gcc", r"^(fatal )?(error|warning|note):"),
        ("python-mypy", r"^(error|warning|note):\s+.*\[.+\]$"),
        ("java-javac", r"\.java:\d+:\s+(error|warning):"),
        ("go-compiler", r"\.go:\d+:\d+:"),
        ("eslint-compact", r"line\s+\d+,\s+col\s+\d+,"),
        ("generic-compiler", r".+:\d+:?\d*:?\s*(error|warning)?"),
    ]

    for matcher_id, pattern in detection_order:
        if re.search(pattern, first_line, re.IGNORECASE):
            return _get_all_matchers().get(matcher_id)

    # 回退：generic
    return BUILTIN_MATCHERS.get("generic-compiler")


# ═══════════════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════════════

@router.post("/parse", response_model=ParseResponse)
async def parse_output(req: ParseRequest) -> ParseResponse:
    """
    解析构建/任务输出为结构化诊断。

    支持:
    - matcher_id="auto": 自动检测最适合的匹配器
    - matcher_id="eslint-compact": 显式指定内置匹配器
    - matcher_id="my-custom": 使用自定义匹配器
    """
    all_matchers = _get_all_matchers()

    # 选择匹配器
    if req.matcher_id == "auto":
        matcher = _auto_detect_matcher(req.content)
        if matcher is None:
            raise HTTPException(status_code=400, detail="无法自动检测匹配器, 请显式指定 matcher_id")
    elif req.matcher_id in all_matchers:
        matcher = all_matchers[req.matcher_id]
    else:
        raise HTTPException(
            status_code=404,
            detail=f"未知匹配器: '{req.matcher_id}'。可用: {list(all_matchers.keys())[:10]}..."
        )

    diagnostics = _parse_content(req.content, matcher)
    return ParseResponse(
        diagnostics=diagnostics,
        total=len(diagnostics),
        matcher_used=matcher.id,
        lines_processed=len(req.content.splitlines()),
    )


@router.get("")
async def list_matchers() -> dict:
    """列出所有可用匹配器 (内置 + 自定义)"""
    all_matchers = _get_all_matchers()
    return {
        "total": len(all_matchers),
        "matchers": [
            {
                "id": m.id,
                "label": m.label,
                "owner": m.owner,
                "source": m.source,
                "mode": m.mode.value,
                "is_builtin": m.id in BUILTIN_MATCHERS,
                "is_custom": m.id in _custom_matchers,
                "severity": m.severity.value,
            }
            for m in all_matchers.values()
        ],
    }


@router.post("/custom")
async def register_custom_matcher(matcher: ProblemMatcherDef) -> dict:
    """注册自定义问题匹配器 (持久化到磁盘)"""
    all_matchers = _get_all_matchers()

    if matcher.id in BUILTIN_MATCHERS:
        raise HTTPException(
            status_code=409,
            detail=f"'{matcher.id}' 是内置匹配器, 不可覆盖。请使用不同的 ID。"
        )

    # 验证正则合法性
    try:
        re.compile(matcher.pattern.regexp)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"无效的正则表达式: {e}")

    _custom_matchers[matcher.id] = matcher
    _save_custom_matchers()

    return {"status": "ok", "id": matcher.id, "label": matcher.label}


@router.delete("/custom/{matcher_id}")
async def delete_custom_matcher(matcher_id: str) -> dict:
    """删除自定义匹配器"""
    if matcher_id not in _custom_matchers:
        raise HTTPException(status_code=404, detail=f"自定义匹配器 '{matcher_id}' 不存在")

    del _custom_matchers[matcher_id]
    _save_custom_matchers()

    return {"status": "deleted", "id": matcher_id}
