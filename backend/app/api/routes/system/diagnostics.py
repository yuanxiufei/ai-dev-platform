"""
系统诊断 API (Session 45)

对标 VSCode 诊断 API - 提供代码分析、问题检测和诊断列表。
支持前端 Error Lens + Problems Panel 使用。
"""

import re
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/system/diagnostics", tags=["system-diagnostics"])


# ── 数据模型 ──

class DiagnosticItem(BaseModel):
    """诊断条目"""
    file: str = Field(..., description="文件路径或名称")
    line: int = Field(..., description="行号 (1-based)")
    column: int = Field(default=1, description="列号 (1-based)")
    message: str = Field(..., description="诊断消息")
    severity: str = Field(..., description="严重级别: error / warning / info")
    code: Optional[str] = Field(default=None, description="规则代码")


class DiagnosticRequest(BaseModel):
    """诊断请求"""
    content: str = Field(..., description="代码内容")
    language: str = Field(default="plaintext", description="语言标识")
    file_path: Optional[str] = Field(default=None, description="文件路径")


class DiagnosticResponse(BaseModel):
    """诊断响应"""
    diagnostics: List[DiagnosticItem]
    summary: dict = Field(default_factory=lambda: {"error": 0, "warning": 0, "info": 0})


class BatchDiagnosticItem(BaseModel):
    """批量诊断的单个文件"""
    content: str
    language: str = "plaintext"
    file_path: str = "untitled"


class BatchDiagnosticRequest(BaseModel):
    """批量诊断请求"""
    files: List[BatchDiagnosticItem]


class BatchDiagnosticResponse(BaseModel):
    """批量诊断响应"""
    results: dict = Field(default_factory=dict, description="{file_path: DiagnosticResponse}")


# ── 诊断扫描核心逻辑 ──

# JS/TS 保留关键字
JS_KEYWORDS = {
    "if", "else", "for", "while", "do", "switch", "case", "break", "continue",
    "return", "throw", "try", "catch", "finally", "new", "delete", "typeof",
    "void", "this", "super", "class", "extends", "import", "export", "default",
    "from", "as", "async", "await", "yield", "function", "var", "let", "const",
    "true", "false", "null", "undefined", "NaN", "Infinity",
}

# 不应该在代码中使用的 console 方法
CONSOLE_METHODS = {"log", "debug", "warn", "info", "trace", "dir", "table", "time", "timeEnd"}

# 需要关注的关键词标签
TODO_TAGS = {"TODO", "FIXME", "HACK", "XXX", "OPTIMIZE", "BUG", "NOTE", "REVIEW"}


def scan_code(content: str, language: str, file_path: str = "untitled") -> List[DiagnosticItem]:
    """
    扫描代码内容，返回诊断条目列表。

    检测项:
      - TODO/FIXME/HACK/XXX 标签 → info
      - console.log/debug 等调试语句 (JS/TS) → warning
      - var 声明 (JS/TS, 不在注释中) → info
      - 空的 catch 块 → warning
      - 过长的行 (>120 chars) → info
      - Python: print() 调试语句 → warning
    """
    diagnostics: List[DiagnosticItem] = []
    lines = content.split("\n")
    is_js_ts = language in ("javascript", "typescript", "javascriptreact", "typescriptreact")
    is_python = language in ("python", "python3")
    is_css = language in ("css", "scss", "less", "sass")

    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()

        if not stripped:
            continue

        # ── 注释检测 ──
        is_comment = False
        if is_js_ts:
            is_comment = bool(re.match(r'^\s*//', line)) or ("/*" in line and "*/" not in line)
        elif is_python:
            is_comment = bool(re.match(r'^\s*#', line))
        elif is_css:
            is_comment = "/*" in line and "*/" not in line

        # ── TODO/FIXME/HACK/XXX 标签 → info ──
        for tag in TODO_TAGS:
            if re.search(r'\b' + tag + r'\b', line):
                msg = stripped if len(stripped) <= 80 else stripped[:77] + "..."
                diagnostics.append(DiagnosticItem(
                    file=file_path,
                    line=line_num,
                    column=1,
                    message=f"[{tag}] {msg}",
                    severity="info",
                    code=tag,
                ))
                break  # 每个行只报告一个标签

        # ── console 语句 (JS/TS) → warning ──
        if is_js_ts and not is_comment:
            console_match = re.search(r'\bconsole\.(\w+)\s*\(', line)
            if console_match:
                method = console_match.group(1)
                if method in CONSOLE_METHODS:
                    diagnostics.append(DiagnosticItem(
                        file=file_path,
                        line=line_num,
                        column=console_match.start() + 1,
                        message=f"console.{method}() 调试语句",
                        severity="warning",
                        code="no-console",
                    ))

        # ── var 声明 (JS/TS) → info ──
        if is_js_ts and not is_comment:
            # 排除字符串中的 var
            code_part = re.sub(r'["\'`].*?["\'`]', '', line)
            if re.search(r'\bvar\s+\w+', code_part):
                diagnostics.append(DiagnosticItem(
                    file=file_path,
                    line=line_num,
                    column=1,
                    message="使用 'var' 声明，建议改为 'const' 或 'let'",
                    severity="info",
                    code="no-var",
                ))

        # ── 空的 catch 块 → warning ──
        if not is_comment:
            if re.search(r'catch\s*\([^)]*\)\s*\{\s*\}', line):
                diagnostics.append(DiagnosticItem(
                    file=file_path,
                    line=line_num,
                    column=1,
                    message="空的 catch 块 — 静默忽略错误。添加错误日志或重新抛出。",
                    severity="warning",
                    code="no-empty-catch",
                ))

        # ── Python print() 调试 → warning ──
        if is_python and not is_comment:
            if re.search(r'\bprint\s*\(', line) and not (
                'print(' in line and ('->' in line or 'lambda' in line)
            ):
                diagnostics.append(DiagnosticItem(
                    file=file_path,
                    line=line_num,
                    column=1,
                    message="print() 调试语句，建议使用 logging",
                    severity="warning",
                    code="no-print",
                ))

        # ── 过长的行 → info ──
        if len(line.rstrip()) > 120 and not is_comment and not stripped.startswith("import"):
            diagnostics.append(DiagnosticItem(
                file=file_path,
                line=line_num,
                column=1,
                message=f"行过长 ({len(line.rstrip())} chars)，建议拆分或重构",
                severity="info",
                code="max-line-length",
            ))

        # ── Python 可变默认参数 → warning ──
        if is_python and re.search(r'def\s+\w+\s*\([^)]*=\s*(\[\s*\]|\{\s*\}|set\s*\(\s*\))', line):
            diagnostics.append(DiagnosticItem(
                file=file_path,
                line=line_num,
                column=1,
                message="可变对象作为默认参数 — 可能导致意外共享状态",
                severity="warning",
                code="mutable-default",
            ))

    return diagnostics


# ── API 端点 ──

@router.post("/analyze", response_model=DiagnosticResponse)
async def analyze_code(request: DiagnosticRequest):
    """
    分析代码内容，返回诊断条目列表。

    请求体:
      - content: 代码文本
      - language: 语言标识 (javascript, typescript, python, css 等)
      - file_path: 文件路径 (可选)
    """
    if not request.content.strip():
        return DiagnosticResponse(diagnostics=[], summary={"error": 0, "warning": 0, "info": 0})

    diagnostics = scan_code(request.content, request.language, request.file_path or "untitled")

    # 计数字段
    summary = {"error": 0, "warning": 0, "info": 0}
    for d in diagnostics:
        if d.severity in summary:
            summary[d.severity] += 1

    return DiagnosticResponse(diagnostics=diagnostics, summary=summary)


@router.post("/analyze-batch", response_model=BatchDiagnosticResponse)
async def analyze_batch(request: BatchDiagnosticRequest):
    """
    批量分析多个文件的代码内容。

    请求体:
      - files: 文件列表，每个包含 content, language, file_path
    """
    results: dict = {}
    for item in request.files:
        diagnostics = scan_code(item.content, item.language, item.file_path)
        summary = {"error": 0, "warning": 0, "info": 0}
        for d in diagnostics:
            if d.severity in summary:
                summary[d.severity] += 1
        results[item.file_path] = {
            "diagnostics": [d.model_dump() for d in diagnostics],
            "summary": summary,
        }

    return BatchDiagnosticResponse(results=results)


@router.get("/languages", response_model=List[str])
async def list_supported_languages():
    """返回支持诊断分析的语言列表"""
    return [
        "javascript", "typescript", "javascriptreact", "typescriptreact",
        "python", "python3",
        "css", "scss", "less", "sass",
        "html", "vue", "xml",
        "json", "yaml", "markdown",
    ]
