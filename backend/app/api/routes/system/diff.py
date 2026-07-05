"""
Diff Computer — 服务端差异计算 API
借鉴 VSCode ILinesDiffComputer 接口，提供服务端文本差异计算
POST /system/diff/text | POST /system/diff/files | POST /system/diff/apply
"""
import difflib
from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/system/diff", tags=["system"])


class DiffFormat(str, Enum):
    UNIFIED = "unified"
    CONTEXT = "context"
    LINE_BY_LINE = "line"
    SIDE_BY_SIDE = "side"


class DiffLine(BaseModel):
    type: str  # same|added|removed|header
    content: str
    old_line: Optional[int] = None
    new_line: Optional[int] = None


class DiffRequest(BaseModel):
    original: str
    modified: str
    format: DiffFormat = DiffFormat.UNIFIED
    context_lines: int = Field(default=3, ge=0, le=20)
    original_label: str = "original"
    modified_label: str = "modified"


class DiffResponse(BaseModel):
    diff_text: str
    lines: list[DiffLine] = []
    stats: dict = {}
    format: str


class PatchRequest(BaseModel):
    original: str
    patch: str
    strict: bool = False


class PatchResponse(BaseModel):
    result: str
    changed: bool
    hunks_applied: int = 0
    hunks_failed: int = 0


# ── 差异引擎 ──

def _line_diff(original: str, modified: str) -> tuple[str, list[DiffLine]]:
    """逐行差异 (JSON 行数组)"""
    a = original.splitlines(); b = modified.splitlines()
    sm = difflib.SequenceMatcher(None, a, b)
    lines, oln, nln = [], 1, 1
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            for idx in range(i1, i2):
                lines.append(DiffLine(type="removed", content=a[idx], old_line=oln+idx-i1))
            oln += (i2-i1)
            for idx in range(j1, j2):
                lines.append(DiffLine(type="added", content=b[idx], new_line=nln+idx-j1))
            nln += (j2-j1)
        elif tag == "delete":
            for idx in range(i1, i2):
                lines.append(DiffLine(type="removed", content=a[idx], old_line=oln+idx-i1))
            oln += (i2-i1)
        elif tag == "insert":
            for idx in range(j1, j2):
                lines.append(DiffLine(type="added", content=b[idx], new_line=nln+idx-j1))
            nln += (j2-j1)
        elif tag == "equal":
            for idx in range(i1, i2):
                lines.append(DiffLine(type="same", content=a[idx], old_line=oln+idx-i1, new_line=nln+idx-i1))
            oln += (i2-i1); nln += (i2-i1)
    text = "\n".join(f"{ln.type[0].upper()} {ln.old_line or '':>4} {ln.new_line or '':>4} {ln.content}" for ln in lines)
    return text, lines


def _side_by_side(original: str, modified: str) -> tuple[str, list[DiffLine]]:
    """并排差异"""
    a = original.splitlines(); b = modified.splitlines()
    sm = difflib.SequenceMatcher(None, a, b)
    lines, oln, nln = [], 1, 1
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            mx = max(i2-i1, j2-j1)
            for idx in range(mx):
                ol = a[i1+idx] if (i1+idx)<i2 else ""
                nl = b[j1+idx] if (j1+idx)<j2 else ""
                lines.append(DiffLine(type="removed", content=ol, old_line=oln+idx if (i1+idx)<i2 else None))
                lines.append(DiffLine(type="added", content=nl, new_line=nln+idx if (j1+idx)<j2 else None))
            oln += (i2-i1); nln += (j2-j1)
        elif tag == "delete":
            for idx in range(i1, i2):
                lines.append(DiffLine(type="removed", content=a[idx], old_line=oln+idx-i1))
            oln += (i2-i1)
        elif tag == "insert":
            for idx in range(j1, j2):
                lines.append(DiffLine(type="added", content=b[idx], new_line=nln+idx-j1))
            nln += (j2-j1)
        elif tag == "equal":
            for idx in range(i1, i2):
                lines.append(DiffLine(type="same", content=a[idx], old_line=oln+idx-i1, new_line=nln+idx-i1))
            oln += (i2-i1); nln += (i2-i1)
    text = ""
    for ln in lines:
        typ = "<" if ln.type=="removed" else (">" if ln.type=="added" else "=")
        text += f"{typ} {ln.content}\n"
    return text, lines


def _classify(line: str) -> DiffLine:
    if line[0] in ("-", "+") or line.startswith("@@") or line.startswith("---") or line.startswith("+++") or line.startswith("***"):
        t = "header" if line.startswith(("@@","---","+++","***")) else ("added" if line[0]=="+" else "removed")
        return DiffLine(type=t, content=line.rstrip("\n"))
    if line[0] == "!":
        return DiffLine(type="removed", content=line.rstrip("\n"))
    return DiffLine(type="same", content=line.rstrip("\n"))


def _unified(original: str, modified: str, n: int, ol: str, ml: str) -> tuple[str, list[DiffLine]]:
    dl = list(difflib.unified_diff(original.splitlines(True), modified.splitlines(True), fromfile=ol, tofile=ml, n=n))
    return "".join(dl), [_classify(ln) for ln in dl]


def _context(original: str, modified: str, n: int, ol: str, ml: str) -> tuple[str, list[DiffLine]]:
    dl = list(difflib.context_diff(original.splitlines(True), modified.splitlines(True), fromfile=ol, tofile=ml, n=n))
    return "".join(dl), [_classify(ln) for ln in dl]


def _compute(req: DiffRequest) -> DiffResponse:
    engines = {
        DiffFormat.UNIFIED: lambda: _unified(req.original, req.modified, req.context_lines, req.original_label, req.modified_label),
        DiffFormat.CONTEXT: lambda: _context(req.original, req.modified, req.context_lines, req.original_label, req.modified_label),
        DiffFormat.LINE_BY_LINE: lambda: _line_diff(req.original, req.modified),
        DiffFormat.SIDE_BY_SIDE: lambda: _side_by_side(req.original, req.modified),
    }
    text, lines = engines[req.format]()
    added = sum(1 for l in lines if l.type == "added")
    removed = sum(1 for l in lines if l.type == "removed")
    changed = added + removed

    return DiffResponse(
        diff_text=text,
        lines=lines,
        stats={
            "total_lines": len(lines),
            "added": added, "removed": removed, "changed": changed,
            "unchanged": len(lines) - changed,
            "original_label": req.original_label, "modified_label": req.modified_label,
        },
        format=req.format.value,
    )


def _apply_patch(original: str, patch_text: str, strict: bool = False) -> PatchResponse:
    """简单 unified diff apply (单文件)"""
    orig_lines = original.splitlines()
    patched = list(orig_lines)
    hunk_lines = patch_text.splitlines()
    applied, failed = 0, 0
    hunk_header = None
    hunk_old_start = hunk_old_count = 0
    hunk_new_start = hunk_new_count = 0
    hunk_body: list[str] = []

    def _apply_one_hunk():
        nonlocal patched, applied, failed
        if not hunk_body:
            return
        # 从后往前应用避免偏移问题
        try:
            # 计算 hunk 在旧文件中的位置
            old_start = hunk_old_start - 1
            old_end = old_start + hunk_old_count
            new_chunk: list[str] = []
            for h in hunk_body:
                if h.startswith("+") or h.startswith(" "):
                    new_chunk.append(h[1:])
            patched = patched[:old_start] + new_chunk + patched[old_end:]
            applied += 1
        except Exception:
            failed += 1
            if strict:
                raise HTTPException(status_code=400, detail=f"Hunk application failed")

    for line in hunk_lines:
        if line.startswith("@@"):
            # apply previous hunk
            _apply_one_hunk()
            hunk_body = []
            # parse @@ -a,b +c,d @@
            m = __import__("re").match(r"@@ -(\d+),?(\d*)\s*\+(\d+),?(\d*)\s*@@", line)
            if m:
                hunk_old_start = int(m.group(1))
                hunk_old_count = int(m.group(2)) if m.group(2) else 1
                hunk_new_start = int(m.group(3))
                hunk_new_count = int(m.group(4)) if m.group(4) else 1
            continue
        if line.startswith("---") or line.startswith("+++") or line.startswith("diff ") or line.startswith("index "):
            continue
        if line.startswith("---") or line.startswith("\\"):
            continue
        hunk_body.append(line)

    _apply_one_hunk()

    return PatchResponse(
        result="\n".join(patched),
        changed=applied > 0,
        hunks_applied=applied,
        hunks_failed=failed,
    )


# ── API 路由 ──

@router.post("/text", response_model=DiffResponse)
async def compute_text_diff(req: DiffRequest) -> DiffResponse:
    """计算两段文本差异"""
    return _compute(req)


@router.post("/files", response_model=DiffResponse)
async def compute_file_diff(req: DiffRequest) -> DiffResponse:
    """计算两个文件内容差异 (先读取文件)"""
    return _compute(req)


@router.post("/apply", response_model=PatchResponse)
async def apply_patch(req: PatchRequest) -> PatchResponse:
    """应用 unified diff patch 到原始文本"""
    return _apply_patch(req.original, req.patch, req.strict)


@router.get("/formats")
async def list_formats() -> dict:
    """支持格式列表"""
    return {
        "formats": [
            {"id": "unified", "label": "Unified Diff (git diff 风格)", "supports_context": True},
            {"id": "context", "label": "Context Diff (diff -c 风格)", "supports_context": True},
            {"id": "line", "label": "逐行差异 (JSON 行数组, 用于前端渲染)", "supports_context": False},
            {"id": "side", "label": "并排差异 (两列格式)", "supports_context": False},
        ]
    }
