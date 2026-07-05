"""
代码操作 API (Session 48)

对标 VSCode codeAction contrib — 为诊断问题提供自动修复建议。
支持 QuickFix, Source Action, Refactoring 三类操作。
"""

from __future__ import annotations

import re
from typing import List, Optional
from enum import Enum

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/system/code-actions", tags=["system-code-actions"])


# ── 枚举与数据模型 ──

class CodeActionKind(str, Enum):
    QUICK_FIX = "quickfix"
    REFACTOR = "refactor"
    REFACTOR_EXTRACT = "refactor.extract"
    REFACTOR_INLINE = "refactor.inline"
    SOURCE = "source"
    SOURCE_ORGANIZE_IMPORTS = "source.organizeImports"
    SOURCE_FIX_ALL = "source.fixAll"

class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class DiagnosticItem(BaseModel):
    """诊断条目 (输入)"""
    message: str = Field(..., description="诊断消息")
    severity: DiagnosticSeverity = Field(default=DiagnosticSeverity.WARNING)
    code: Optional[str] = Field(default=None, description="规则代码, 如 'no-unused-vars'")
    line: int = Field(default=1, ge=1)
    column: int = Field(default=1, ge=1)
    source: Optional[str] = Field(default=None, description="来源, 如 'eslint'")

class CodeActionRequest(BaseModel):
    """代码操作请求"""
    content: str = Field(..., description="完整代码内容")
    language: str = Field(default="plaintext", description="语言标识符")
    diagnostics: List[DiagnosticItem] = Field(default_factory=list, description="诊断列表")
    range_start_line: Optional[int] = Field(default=None, description="光标/选区起始行")
    range_start_col: Optional[int] = Field(default=None)
    range_end_line: Optional[int] = Field(default=None)
    range_end_col: Optional[int] = Field(default=None)

class TextEdit(BaseModel):
    """文本编辑"""
    range_start_line: int
    range_start_col: int
    range_end_line: int
    range_end_col: int
    new_text: str = ""

class CodeAction(BaseModel):
    """代码操作"""
    title: str = Field(..., description="操作标题 (显示在灯泡菜单)")
    kind: CodeActionKind = Field(..., description="操作类型")
    is_preferred: bool = Field(default=False, description="是否为推荐操作")
    diagnostics: List[str] = Field(default_factory=list, description="关联的诊断消息")
    edits: List[TextEdit] = Field(default_factory=list, description="需要的编辑")
    command: Optional[str] = Field(default=None, description="代替编辑的命令名")

class CodeActionResponse(BaseModel):
    """代码操作响应"""
    actions: List[CodeAction] = Field(default_factory=list)
    source: str = Field(default="builtin", description="来源: builtin / ai")


# ── QuickFix 策略 ──

# 诊断消息 → 修复策略映射
FIX_STRATEGIES: dict[str, list[tuple[str, str]]] = {
    # ESLint / TypeScript
    "no-unused-vars": [("删除未使用的变量 (整行)", "delete_line")],
    "no-unused-imports": [("删除未使用的导入", "delete_line")],
    "no-extra-semi": [("删除多余分号", "remove_char")],
    "no-trailing-spaces": [("删除行尾空白", "trim_trailing")],
    "no-multiple-empty-lines": [("压缩连续空行为单行", "collapse_empty_lines")],
    "eol-last": [("在文件末尾添加换行", "append_newline")],
    "no-irregular-whitespace": [("替换为普通空格", "replace_whitespace")],
    "no-cond-assign": [("用括号包裹赋值表达式", "wrap_parens")],
    # Python
    "E302": [("在函数/类前添加2空行", "add_blank_lines_before")],
    "E501": [("拆分长行", "split_long_line")],
    "W291": [("删除行尾空白", "trim_trailing")],
    "W293": [("将空白行改为空行", "strip_blank_line")],
    "E303": [("删除多余空行", "collapse_empty_lines")],
    "F401": [("删除未使用的导入", "delete_line")],
    "F841": [("删除未使用的变量", "delete_line")],
    "E711": [("将比较改为 'is None'", "replace_text")],
    "E712": [("将比较改为 'is True'", "replace_text")],
    # HTML
    "missing-doctype": [("在顶部添加 <!DOCTYPE html>", "prepend_text")],
    "missing-lang": [("在 <html> 标签中添加 lang 属性", "add_attribute")],
    # CSS
    "empty-rules": [("删除空规则集", "delete_block")],
    "duplicate-selectors": [("保留第一个重复选择器声明", "keep_first")],
    # 通用
    "missing-semicolon": [("添加分号", "append_char")],
    "missing-comma": [("添加逗号", "append_char")],
    "unclosed-string": [("添加闭合引号", "append_char")],
    "unclosed-bracket": [("添加闭合括号", "append_char")],
}

# 已知诊断消息正则 (用于匹配)
DIAGNOSTIC_PATTERNS: dict[str, list[str]] = {
    "delete_line": [
        r"未使用.*(?:变量|导入|import|variable|function)",
        r"(?:is defined but never used|'[^']+' is assigned a value but never used)",
        r"(?:unused|no-unused)",
    ],
    "trim_trailing": [
        r"(?:trailing whitespace|行尾空白|Trailing spaces)",
    ],
    "collapse_empty_lines": [
        r"(?:multiple blank lines|多余空行|too many blank lines|multiple empty lines)",
    ],
    "append_newline": [
        r"(?:no newline|缺少换行|insert final newline)",
    ],
    "add_blank_lines_before": [
        r"(?:expected 2 blank lines|缺少空行|blank line)",
    ],
    "replace_whitespace": [
        r"(?:irregular whitespace|不可见字符|non-breaking space|\\u00a0)",
    ],
}

# 修复命令 → 内容编辑函数
def _get_line(content: str, line_no: int) -> str:
    lines = content.split("\n")
    idx = line_no - 1
    return lines[idx] if 0 <= idx < len(lines) else ""


def _execute_fix(content: str, diag: DiagnosticItem, strategy: str) -> Optional[str]:
    """执行修复，返回修改后的内容"""
    match strategy:
        case "delete_line":
            lines = content.split("\n")
            idx = diag.line - 1
            if 0 <= idx < len(lines):
                del lines[idx]
                return "\n".join(lines)
        case "trim_trailing":
            lines = content.split("\n")
            idx = diag.line - 1
            if 0 <= idx < len(lines):
                lines[idx] = lines[idx].rstrip()
                return "\n".join(lines)
        case "collapse_empty_lines":
            return re.sub(r'\n{3,}', '\n\n', content)
        case "append_newline":
            if not content.endswith("\n"):
                return content + "\n"
        case "add_blank_lines_before":
            lines = content.split("\n")
            idx = diag.line - 1
            if 0 < idx < len(lines) and lines[idx-1].strip() != "":
                lines.insert(idx, "")
                lines.insert(idx, "")
                return "\n".join(lines)
        case "strip_blank_line":
            lines = content.split("\n")
            idx = diag.line - 1
            if 0 <= idx < len(lines) and lines[idx].strip() == "":
                lines[idx] = ""
                return "\n".join(lines)
        case "replace_whitespace":
            lines = content.split("\n")
            idx = diag.line - 1
            if 0 <= idx < len(lines):
                lines[idx] = lines[idx].replace('\u00a0', ' ')
                return "\n".join(lines)
        case "split_long_line":
            lines = content.split("\n")
            idx = diag.line - 1
            if 0 <= idx < len(lines) and len(lines[idx]) > 79:
                line = lines[idx]
                # 尝试在最后一个运算符处拆分
                break_at = max(
                    line.rfind(" + ", 0, 79),
                    line.rfind(" - ", 0, 79),
                    line.rfind(" * ", 0, 79),
                    line.rfind(", ", 0, 79),
                    line.rfind(" and ", 0, 79),
                    line.rfind(" or ", 0, 79),
                )
                if break_at > 40:
                    indent = re.match(r'^(\s*)', line).group(1) + "    "
                    lines[idx] = line[:break_at]
                    lines.insert(idx + 1, indent + line[break_at:].strip())
                    return "\n".join(lines)
    return None


def _match_diagnostic(message: str) -> Optional[str]:
    """匹配诊断消息到修复策略类别"""
    for strategy, patterns in DIAGNOSTIC_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, message, re.IGNORECASE):
                return strategy
    return None


# ── Source Actions ──

def _organize_imports(content: str, language: str) -> Optional[str]:
    """整理导入语句（排序 + 去重 + 合并）"""
    import_patterns = {
        "javascript": r'^import\s+.*?(?:from\s+[\'"].*?[\'"];?)?\s*$|^const\s+.*?=\s*require\(.*?\)\s*;?\s*$',
        "typescript": r'^import\s+.*?(?:from\s+[\'"].*?[\'"];?)?\s*$',
        "python": r'^(?:import\s+\w|from\s+\w+\s+import).*$',
    }
    pattern = import_patterns.get(language)
    if not pattern:
        return None

    lines = content.split("\n")
    import_lines = []
    import_indices = []
    non_import_lines = []
    
    for i, line in enumerate(lines):
        if re.match(pattern, line.strip()):
            import_lines.append((i, line))
            import_indices.append(i)
        else:
            non_import_lines.append(line)
    
    if len(import_lines) <= 1:
        return None
    
    # 排序 + 去重
    seen = set()
    sorted_unique = []
    for idx, line in import_lines:
        stripped = line.strip()
        if stripped not in seen:
            seen.add(stripped)
            sorted_unique.append(line)
    sorted_unique.sort(key=lambda s: s.strip().lower())

    # 重建：在第一个导入位置开始，保持原有分组空行
    first_import_idx = import_indices[0]
    result_lines = lines[:first_import_idx] + sorted_unique + lines[import_indices[-1] + 1:]
    return "\n".join(result_lines)


def _fix_trailing_whitespace(content: str) -> str:
    """全局去除行尾空白（source.fixAll）"""
    lines = content.split("\n")
    return "\n".join(line.rstrip() for line in lines)


def _fix_missing_newline(content: str) -> str:
    """确保文件以换行结束"""
    if not content.endswith("\n"):
        return content + "\n"
    return content


# ── Refactoring ──

def _extract_method_suggestions(content: str, language: str) -> List[CodeAction]:
    """检测可提取为方法的代码块"""
    actions = []
    if language in ("python",):
        # 检测过长函数 (>30行) 中连续的注释块
        lines = content.split("\n")
        func_start = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r'^def\s+\w+\s*\(', stripped):
                func_start = i
            # 检测长段注释后跟代码的模式 (可能可提取)
            if i > 0 and stripped.startswith("#") and lines[i-1].strip() == "":
                # 连续注释块
                comment_end = i
                while comment_end < len(lines) and lines[comment_end].strip().startswith("#"):
                    comment_end += 1
                if comment_end - i >= 3:  # 3行以上注释
                    actions.append(CodeAction(
                        title=f"提取第 {i+1}-{comment_end} 行逻辑到独立方法 (refactor.extract)",
                        kind=CodeActionKind.REFACTOR_EXTRACT,
                        is_preferred=False,
                        diagnostics=["建议提取长代码块到独立函数"],
                    ))
                    break  # 每次只建议一个
    
    elif language in ("javascript", "typescript"):
        lines = content.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("// TODO:") or stripped.startswith("// FIXME:"):
                actions.append(CodeAction(
                    title=f"提取 TODO/FIXME 相关的代码块为独立函数 (refactor.extract)",
                    kind=CodeActionKind.REFACTOR_EXTRACT,
                    is_preferred=False,
                    diagnostics=[stripped],
                ))
                break
    
    return actions[:1]


# ── API 路由 ──

@router.post("", response_model=CodeActionResponse)
async def get_code_actions(req: CodeActionRequest) -> CodeActionResponse:
    """
    获取代码操作建议 (灯泡菜单)
    
    返回三类操作：
    - QuickFix: 针对诊断问题的修复
    - Source: 整理导入/全局修复
    - Refactor: 重构建议
    """
    actions: List[CodeAction] = []
    
    # ── 1. QuickFix: 针对诊断的修复 ──
    for diag in req.diagnostics:
        # 先尝试精确规则码匹配
        if diag.code and diag.code in FIX_STRATEGIES:
            for title, strategy in FIX_STRATEGIES[diag.code]:
                actions.append(CodeAction(
                    title=title,
                    kind=CodeActionKind.QUICK_FIX,
                    is_preferred=True,
                    diagnostics=[diag.message],
                    command=f"fix:{strategy}"
                ))
            continue
        
        # 再尝试消息模式匹配
        matched = _match_diagnostic(diag.message)
        if matched:
            actions.append(CodeAction(
                title=f"自动修复: {diag.message}",
                kind=CodeActionKind.QUICK_FIX,
                is_preferred=False,
                diagnostics=[diag.message],
                command=f"fix:{matched}"
            ))
    
    # ── 2. Source Actions ──
    if req.language in ("javascript", "typescript", "python"):
        organized = _organize_imports(req.content, req.language)
        if organized and organized != req.content:
            actions.append(CodeAction(
                title="整理导入语句 (Organize Imports)",
                kind=CodeActionKind.SOURCE_ORGANIZE_IMPORTS,
                is_preferred=False,
            ))
    
    # Source FixAll
    content_trimmed = _fix_trailing_whitespace(req.content)
    if content_trimmed != req.content:
        actions.append(CodeAction(
            title="修复所有: 去除行尾空白 (Fix All: Trim Whitespace)",
            kind=CodeActionKind.SOURCE_FIX_ALL,
            is_preferred=False,
        ))
    
    # ── 3. Refactoring ──
    refactor_actions = _extract_method_suggestions(req.content, req.language)
    actions.extend(refactor_actions)
    
    return CodeActionResponse(actions=actions, source="builtin")


@router.post("/apply", response_model=dict)
async def apply_code_action(
    content: str = Query(..., description="当前内容"),
    diagnostic_message: Optional[str] = Query(default=None, description="诊断消息"),
    diagnostic_code: Optional[str] = Query(default=None, description="诊断规则码"),
    diagnostic_line: int = Query(default=1, ge=1),
) -> dict:
    """
    应用代码操作 — 对内容执行修复并返回新内容
    
    返回: {"content": "修复后的内容", "changed": true/false}
    """
    diag = DiagnosticItem(
        message=diagnostic_message or "",
        line=diagnostic_line,
        code=diagnostic_code,
    )
    
    # 查找修复策略
    strategy: Optional[str] = None
    
    if diagnostic_code and diagnostic_code in FIX_STRATEGIES:
        _, strategy = FIX_STRATEGIES[diagnostic_code][0]
    else:
        strategy = _match_diagnostic(diag.message)
    
    if not strategy:
        return {"content": content, "changed": False, "reason": "no matching fix strategy"}
    
    new_content = _execute_fix(content, diag, strategy)
    if new_content is not None and new_content != content:
        return {"content": new_content, "changed": True}
    
    return {"content": content, "changed": False, "reason": "fix produced no change"}
