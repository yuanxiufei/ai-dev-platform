"""
全文本搜索 API — 对标 VSCode workbench/services/search (ripgrep)

数据源:
  - 文件搜索: os.walk/os.scandir 文件系统遍历 (rename/glob pattern 过滤)
  - 内容搜索: subprocess (rg/grep) 或 Python 内置 re 逐行扫描
  - 替换引擎: 文件内容精确替换 (Python re.sub)

端点:
  POST /system/search/text       — 文本内容搜索
  POST /system/search/files      — 文件名搜索
  POST /system/search/replace    — 批量替换
  GET  /system/search/engines     — 检测可用搜索引擎

对标 VSCode API:
  - ISearchService.textSearch() → POST /text
  - ISearchService.fileSearch() → POST /files
  - TextSearchComplete.replace() → POST /replace
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import shutil
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system/search", tags=["Search"])

# ── 安全限制 ──
# 搜索路径不允许超出项目根目录
_PROJECT_ROOT = os.environ.get("PROJECT_ROOT", os.getcwd())
_MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
_MAX_RESULTS = 200
_MAX_MATCHES_PER_FILE = 100
_DEFAULT_EXCLUDE_PATTERNS = [
    "node_modules", ".git", "__pycache__", "dist", "build",
    ".venv", "venv", ".tox", ".eggs", "*.pyc", "*.pyo",
    ".DS_Store", "Thumbs.db", "target", ".next", ".nuxt",
    "coverage", ".nyc_output", "*.min.js", "*.min.css",
]


# ── 请求/响应模型 ──

class TextSearchRequest(BaseModel):
    """文本内容搜索请求"""
    query: str = Field(..., min_length=1, max_length=4096, description="搜索内容，支持正则")
    path: str = Field(default=".", description="搜索根目录 (相对于 PROJECT_ROOT)")
    include_patterns: list[str] | None = Field(default=None, description="文件类型过滤 (glob)")
    exclude_patterns: list[str] | None = Field(default=None, description="排除路径 (glob)")
    use_regex: bool = Field(default=False, description="是否为正则搜索")
    case_sensitive: bool = Field(default=False, description="是否区分大小写")
    whole_word: bool = Field(default=False, description="是否全词匹配")
    max_results: int = Field(default=200, ge=1, le=1000)
    context_lines: int = Field(default=0, ge=0, le=10, description="上下文行数")


class FileSearchRequest(BaseModel):
    """文件名搜索请求"""
    pattern: str = Field(..., min_length=1, max_length=1024, description="文件名模式 (支持 glob)")
    path: str = Field(default=".", description="搜索根目录")
    exclude_patterns: list[str] | None = Field(default=None)
    max_results: int = Field(default=200, ge=1, le=2000)


class ReplaceRequest(BaseModel):
    """搜索替换请求"""
    query: str = Field(..., min_length=1, max_length=4096)
    replace_with: str = Field(..., max_length=65536)
    path: str = Field(default=".")
    include_patterns: list[str] | None = Field(default=None)
    exclude_patterns: list[str] | None = Field(default=None)
    use_regex: bool = Field(default=False)
    case_sensitive: bool = Field(default=False)
    whole_word: bool = Field(default=False)
    file_path: str | None = Field(default=None, description="单文件路径，提供后忽略 path/include/exclude")
    line: int | None = Field(default=None, description="指定行号，只替换该行")


class SearchMatch(BaseModel):
    """单次匹配结果"""
    file: str
    line: int
    column: int
    match_text: str
    match_length: int
    line_text: str
    preview_before: str = ""
    preview_after: str = ""


class TextSearchResponse(BaseModel):
    results: list[SearchMatch]
    total_matches: int
    files_scanned: int
    engine: str  # "ripgrep" / "grep" / "python-re"
    elapsed_ms: float


class FileSearchResponse(BaseModel):
    results: list[str]
    total: int
    elapsed_ms: float


class ReplaceResponse(BaseModel):
    replaced: int  # 替换次数
    files_modified: int
    errors: list[str] = []


# ── 搜索引擎选择 ──

def _find_ripgrep() -> str | None:
    """查找 ripgrep 二进制"""
    rg = shutil.which("rg") or shutil.which("ripgrep")
    if rg:
        try:
            subprocess.run([rg, "--version"], capture_output=True, timeout=5)
            return rg
        except Exception:
            pass
    return None


def _find_grep() -> str | None:
    """查找 grep 二进制"""
    g = shutil.which("grep")
    if g:
        try:
            subprocess.run([g, "--version"], capture_output=True, timeout=5)
            return g
        except Exception:
            pass
    return None


# ── ripgrep 搜索 ──

def _rg_text_search(
    query: str, root: str, include_patterns: list[str] | None,
    exclude_patterns: list[str] | None,
    use_regex: bool, case_sensitive: bool, whole_word: bool,
    max_results: int, context_lines: int,
) -> tuple[list[SearchMatch], int, int, float]:
    """使用 ripgrep 进行文本搜索"""
    import time
    t0 = time.time()

    rg = _find_ripgrep()
    if not rg:
        return [], 0, 0, 0.0

    cmd = [rg, "--no-heading", "--line-number", "--column", "--color=never",
           "--max-count", str(_MAX_MATCHES_PER_FILE),
           "--max-filesize", str(_MAX_FILE_SIZE_BYTES), "M"]

    if use_regex:
        # rg 默认支持正则，但需要确保没有 PCRE 语法
        cmd.extend(["--engine", "auto"])
    else:
        cmd.append("--fixed-strings")

    if not case_sensitive:
        cmd.append("--ignore-case")

    if whole_word:
        cmd.append("--word-regexp")

    if context_lines > 0:
        cmd.extend(["--context", str(context_lines)])

    # include patterns
    if include_patterns:
        for pat in include_patterns:
            cmd.extend(["--glob", pat.strip()])

    # exclude patterns
    all_exclude = _DEFAULT_EXCLUDE_PATTERNS + (exclude_patterns or [])
    for pat in all_exclude:
        cmd.extend(["--glob", f"!{pat.strip()}"])

    cmd.append("--")  # 分隔符
    cmd.append(query)
    cmd.append(root)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                                cwd=root, encoding="utf-8", errors="replace")
        output = result.stdout
    except subprocess.TimeoutExpired:
        return [], 0, 0, time.time() - t0
    except Exception as e:
        logger.warning(f"ripgrep failed: {e}")
        return [], 0, 0, time.time() - t0

    matches = _parse_rg_output(output, root, max_results)
    files_scanned = len(set(m.file for m in matches))
    elapsed = (time.time() - t0) * 1000
    return matches, len(matches), files_scanned, elapsed


def _parse_rg_output(output: str, root: str, max_results: int) -> list[SearchMatch]:
    """解析 ripgrep 输出"""
    from pathlib import PurePath
    matches: list[SearchMatch] = []
    cnt = 0

    for line in output.splitlines():
        if not line.strip() or line.startswith("--"):
            continue
        try:
            # rg 格式: file:line:column:text
            # 或: file:line:text (无 column)
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            file_path = parts[0]
            try:
                line_num = int(parts[1])
                col_part = parts[2]
                # 尝试解析 column
                col = 1
                text = col_part
                if ":" in col_part:
                    col_str, text = col_part.split(":", 1)
                    try:
                        col = int(col_str)
                    except ValueError:
                        text = col_part
                if line_num <= 0:
                    continue
            except ValueError:
                continue

            # 相对化路径
            try:
                rel = str(PurePath(file_path).relative_to(root))
            except ValueError:
                rel = file_path

            match_text = ""
            # 从 line_text 提取匹配部分
            stripped = text.strip()
            matches.append(SearchMatch(
                file=rel,
                line=line_num,
                column=col,
                match_text=stripped,
                match_length=len(stripped),
                line_text=text,
            ))
            cnt += 1
            if cnt >= max_results:
                break
        except Exception:
            continue

    return matches


# ── Python re 搜索 (回退) ──

def _py_text_search(
    query: str, root: str, include_patterns: list[str] | None,
    exclude_patterns: list[str] | None,
    use_regex: bool, case_sensitive: bool, whole_word: bool,
    max_results: int, context_lines: int,
) -> tuple[list[SearchMatch], int, int, float]:
    """Python 内置正则逐行扫描回退"""
    import time
    t0 = time.time()

    # 构建正则
    flags = 0 if case_sensitive else re.IGNORECASE
    if use_regex:
        try:
            pattern_s = query
            if whole_word:
                pattern_s = rf"\b{query}\b"
            pattern = re.compile(pattern_s, flags)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex: {e}")
    else:
        escaped = re.escape(query)
        pattern_s = rf"\b{escaped}\b" if whole_word else escaped
        pattern = re.compile(pattern_s, flags)

    matches: list[SearchMatch] = []
    all_exclude = set(_DEFAULT_EXCLUDE_PATTERNS + (exclude_patterns or []))
    files_scanned = 0

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # 过滤目录
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = [d for d in dirnames if not _is_excluded(
            os.path.join(rel_dir, d), all_exclude)]

        for fname in filenames:
            if len(matches) >= max_results:
                break
            fpath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(fpath, root)
            if _is_excluded(rel_path, all_exclude):
                continue
            if include_patterns and not any(
                fnmatch(rel_path, p.strip()) for p in include_patterns
            ):
                continue
            if not _is_text_file(fname):
                continue
            try:
                fsize = os.path.getsize(fpath)
                if fsize > _MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            files_scanned += 1
            try:
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    for lineno, line in enumerate(f, 1):
                        if len(matches) >= max_results:
                            break
                        for m in pattern.finditer(line):
                            matches.append(SearchMatch(
                                file=rel_path,
                                line=lineno,
                                column=m.start() + 1,
                                match_text=m.group(),
                                match_length=len(m.group()),
                                line_text=line.rstrip("\n\r"),
                            ))
                            if len(matches) >= max_results:
                                break
            except Exception:
                continue

        if len(matches) >= max_results:
            break

    elapsed = (time.time() - t0) * 1000
    return matches, len(matches), files_scanned, elapsed


# ── 文件名搜索 ──

def _file_search(
    pattern: str, root: str, exclude_patterns: list[str] | None, max_results: int,
) -> tuple[list[str], int, float]:
    """文件名搜索"""
    import time
    t0 = time.time()

    # 如果包含通配符，做 glob 匹配
    has_wildcard = any(c in pattern for c in "*?[]")
    all_exclude = set(_DEFAULT_EXCLUDE_PATTERNS + (exclude_patterns or []))
    results: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        dirnames[:] = [d for d in dirnames if not _is_excluded(
            os.path.join(rel_dir, d), all_exclude)]

        for fname in filenames:
            if len(results) >= max_results:
                break
            fpath = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(fpath, root)
            if _is_excluded(rel_path, all_exclude):
                continue

            if has_wildcard:
                if fnmatch(fname, pattern):
                    results.append(rel_path)
            else:
                if fnmatch(fname, f"*{pattern}*"):
                    results.append(rel_path)

        if len(results) >= max_results:
            break

    elapsed = (time.time() - t0) * 1000
    return results, len(results), elapsed


# ── 替换引擎 ──

def _replace_in_file(
    file_path: str, query: str, replace_with: str,
    use_regex: bool, case_sensitive: bool, whole_word: bool,
    target_line: int | None,
) -> tuple[int, int]:
    """在文件中执行替换，返回 (替换次数, 修改文件数)"""
    abs_path = _resolve_path(file_path)
    if not os.path.isfile(abs_path):
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    flags = 0 if case_sensitive else re.IGNORECASE
    if use_regex:
        try:
            pattern_s = query
            if whole_word:
                pattern_s = rf"\b{query}\b"
            pattern = re.compile(pattern_s, flags)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex: {e}")
    else:
        escaped = re.escape(query)
        pattern_s = rf"\b{escaped}\b" if whole_word else escaped
        pattern = re.compile(pattern_s, flags)

    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {e}")

    replaced = 0
    if target_line is not None:
        if 0 < target_line <= len(lines):
            line = lines[target_line - 1]
            new_line, n = pattern.subn(replace_with, line)
            if n > 0:
                lines[target_line - 1] = new_line
                replaced = n
    else:
        for i, line in enumerate(lines):
            new_line, n = pattern.subn(replace_with, line)
            if n > 0:
                lines[i] = new_line
                replaced += n

    if replaced > 0:
        try:
            with open(abs_path, "w", encoding="utf-8", errors="replace") as f:
                f.writelines(lines)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to write file: {e}")

    files_modified = 1 if replaced > 0 else 0
    return replaced, files_modified


# ── 辅助函数 ──

def _resolve_path(rel_path: str) -> str:
    """将相对路径解析并安全检查"""
    abs_path = os.path.normpath(os.path.join(_PROJECT_ROOT, rel_path))
    # 不允许超出 PROJECT_ROOT
    if not abs_path.startswith(os.path.normpath(_PROJECT_ROOT)):
        raise HTTPException(status_code=403, detail="Path traversal not allowed")
    return abs_path


def _is_excluded(path: str, exclude_patterns: set[str]) -> bool:
    """检查路径是否被排除"""
    parts = Path(path).parts
    for p in parts:
        for ep in exclude_patterns:
            if fnmatch(p, ep.strip()):
                return True
    for ep in exclude_patterns:
        if fnmatch(path, ep.strip()):
            return True
    return False


def _is_text_file(filename: str) -> bool:
    """判断是否为文本文件"""
    text_extensions = {
        ".py", ".js", ".ts", ".jsx", ".tsx", ".vue", ".svelte",
        ".html", ".htm", ".css", ".scss", ".sass", ".less",
        ".json", ".yaml", ".yml", ".toml", ".xml", ".svg",
        ".md", ".markdown", ".rst", ".txt", ".log",
        ".rs", ".go", ".java", ".kt", ".swift", ".c", ".cpp", ".h", ".hpp",
        ".rb", ".php", ".lua", ".sh", ".bash", ".zsh", ".fish",
        ".sql", ".graphql", ".proto", ".env", ".cfg", ".ini",
        ".dockerfile", ".makefile", ".cmake",
    }
    ext = os.path.splitext(filename)[1].lower()
    if ext in text_extensions:
        return True
    # Dockerfile, Makefile 无后缀
    basename = os.path.basename(filename).lower()
    if basename in ("dockerfile", "makefile", ".gitignore", ".env", "license", "readme"):
        return True
    return False


# ── 路由 ──

@router.post("/text", response_model=TextSearchResponse)
async def text_search(req: TextSearchRequest) -> TextSearchResponse:
    """
    文本内容搜索 (对标 VSCode ISearchService.textSearch)

    优先级: ripgrep → Python re 回退
    """
    root = _resolve_path(req.path)
    if not os.path.isdir(root):
        raise HTTPException(status_code=400, detail=f"Not a directory: {req.path}")

    # 尝试 ripgrep
    if _find_ripgrep():
        matches, total, scanned, elapsed = _rg_text_search(
            req.query, root, req.include_patterns, req.exclude_patterns,
            req.use_regex, req.case_sensitive, req.whole_word,
            min(req.max_results, _MAX_RESULTS), req.context_lines,
        )
        engine = "ripgrep"
    else:
        matches, total, scanned, elapsed = [], 0, 0, 0
        engine = "ripgrep"

    # 如果 ripgrep 无结果，回退到 Python
    if not matches and not engine.startswith("python"):
        py_matches, py_total, py_scanned, py_elapsed = _py_text_search(
            req.query, root, req.include_patterns, req.exclude_patterns,
            req.use_regex, req.case_sensitive, req.whole_word,
            min(req.max_results, _MAX_RESULTS), req.context_lines,
        )
        if not matches or py_total > total:
            matches, total, scanned, elapsed, engine = py_matches, py_total, py_scanned, py_elapsed, "python-re"

    return TextSearchResponse(
        results=matches[:req.max_results],
        total_matches=total,
        files_scanned=scanned,
        engine=engine,
        elapsed_ms=round(elapsed, 2),
    )


@router.post("/files", response_model=FileSearchResponse)
async def file_search(req: FileSearchRequest) -> FileSearchResponse:
    """文件名搜索 (对标 VSCode ISearchService.fileSearch)"""
    root = _resolve_path(req.path)
    if not os.path.isdir(root):
        raise HTTPException(status_code=400, detail=f"Not a directory: {req.path}")

    results, total, elapsed = _file_search(
        req.pattern, root, req.exclude_patterns,
        min(req.max_results, _MAX_RESULTS * 2),
    )
    return FileSearchResponse(
        results=results[:req.max_results],
        total=total,
        elapsed_ms=round(elapsed, 2),
    )


@router.post("/replace", response_model=ReplaceResponse)
async def search_replace(req: ReplaceRequest) -> ReplaceResponse:
    """
    搜索替换 (对标 VSCode TextSearchComplete)

    支持全项目批次替换或单文件/单行精确替换
    """
    errors: list[str] = []
    total_replaced = 0
    files_modified = 0

    if req.file_path:
        # 单文件替换
        try:
            r, fm = _replace_in_file(
                req.file_path, req.query, req.replace_with,
                req.use_regex, req.case_sensitive, req.whole_word,
                req.line,
            )
            total_replaced += r
            files_modified += fm
        except HTTPException:
            raise
        except Exception as e:
            errors.append(f"Failed to replace in {req.file_path}: {e}")
    else:
        # 全项目搜索替换
        root = _resolve_path(req.path)
        if not os.path.isdir(root):
            raise HTTPException(status_code=400, detail=f"Not a directory: {req.path}")

        # 先搜索匹配文件
        _, py_matches, _, _ = _py_text_search(
            req.query, root, req.include_patterns, req.exclude_patterns,
            req.use_regex, req.case_sensitive, req.whole_word,
            10, 0,
        )
        modified_files = list(dict.fromkeys(m.file for m in py_matches))

        for fpath in modified_files:
            try:
                r, fm = _replace_in_file(
                    fpath, req.query, req.replace_with,
                    req.use_regex, req.case_sensitive, req.whole_word,
                    None,
                )
                total_replaced += r
                files_modified += fm
            except Exception as e:
                errors.append(f"Failed to replace in {fpath}: {e}")

    return ReplaceResponse(
        replaced=total_replaced,
        files_modified=files_modified,
        errors=errors,
    )


@router.get("/engines")
async def search_engines() -> dict[str, Any]:
    """检测可用搜索引擎"""
    rg = _find_ripgrep()
    g = _find_grep()
    return {
        "engines": {
            "ripgrep": {"available": rg is not None, "path": rg},
            "grep": {"available": g is not None, "path": g},
            "python_re": {"available": True},
        },
        "max_file_size_mb": _MAX_FILE_SIZE_BYTES // (1024 * 1024),
        "max_results": _MAX_RESULTS,
    }
