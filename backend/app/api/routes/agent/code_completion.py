"""
代码补全 API 路由 — FIM 补全 + 上下文分析

端点：
  POST   /agent/code-completion/complete              — 执行代码补全
  POST   /agent/code-completion/analyze-context       — 分析代码上下文
  POST   /agent/code-completion/feedback              — 补全反馈（接受/拒绝）
  GET    /agent/code-completion/cache-stats           — 缓存统计
  DELETE /agent/code-completion/cache                 — 清空缓存
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.core.tools.code_completion import (
    FIMCompletionEngine,
    CompletionTrigger,
    get_completion_engine,
    ContextAssembler,
)

logger = logging.getLogger("api.code_completion")

router = APIRouter(
    prefix="/agent/code-completion",
    tags=["Agent - Code Completion"],
)


def _engine() -> FIMCompletionEngine:
    return get_completion_engine()


# ── 补全 ─────────────────────────────────────────────────────


@router.post("/complete")
async def code_complete(payload: dict[str, Any]) -> dict[str, Any]:
    """执行代码补全

    Body:
        file_content: str           — 完整文件内容 (required)
        cursor_line: int            — 光标行号 0-based (required)
        cursor_column: int          — 光标列号 0-based (required)
        file_path: str = ""         — 文件路径
        language: str = ""          — 语言（自动推断）
        trigger: str = "keystroke"  — 触发类型
        top_k: int = 5              — 返回数量
        temperature: float = 0.1    — 温度
        max_tokens: int = 256       — 最大 token
    """
    # 校验必填参数
    file_content = payload.get("file_content", "")
    if not file_content:
        raise HTTPException(status_code=400, detail="file_content is required")

    cursor_line = payload.get("cursor_line", 0)
    cursor_column = payload.get("cursor_column", 0)

    try:
        trigger = CompletionTrigger(payload.get("trigger", "keystroke"))
    except ValueError:
        trigger = CompletionTrigger.KEYSTROKE

    engine = _engine()
    result = await engine.complete(
        file_content=file_content,
        cursor_line=int(cursor_line),
        cursor_column=int(cursor_column),
        file_path=payload.get("file_path", ""),
        language=payload.get("language", ""),
        trigger=trigger,
        top_k=int(payload.get("top_k", 5)),
        temperature=float(payload.get("temperature", 0.1)),
        max_tokens=int(payload.get("max_tokens", 256)),
    )

    return {
        **result.to_dict(),
        "context": result.context.to_dict() if result.context else None,
    }


@router.post("/analyze-context")
async def analyze_context(payload: dict[str, Any]) -> dict[str, Any]:
    """分析光标周围的代码上下文

    Body:
        file_content: str       — 完整文件内容 (required)
        file_path: str = ""     — 文件路径
        cursor_line: int = 0    — 光标行号
        language: str = ""      — 语言
    """
    file_content = payload.get("file_content", "")
    if not file_content:
        raise HTTPException(status_code=400, detail="file_content is required")

    file_path = payload.get("file_path", "")
    cursor_line = int(payload.get("cursor_line", 0))
    language = payload.get("language", "")

    assembler = ContextAssembler()
    if not language:
        language = assembler._infer_language(file_path)

    imports = assembler.extract_imports(file_content, language)
    functions = assembler.extract_functions(file_content, language)

    # 光标附近的代码
    lines = file_content.split("\n")
    nearby: list[dict[str, Any]] = []
    for i in range(max(0, cursor_line - 10), min(len(lines), cursor_line + 5)):
        line_text = lines[i].rstrip()
        if line_text and not line_text.startswith(("#", "//", "/*", "*")):
            nearby.append({
                "line": i + 1,
                "is_cursor": i == cursor_line,
                "content": line_text,
            })

    return {
        "file_path": file_path,
        "language": language,
        "cursor_line": cursor_line,
        "total_lines": len(lines),
        "imports": imports[:30],
        "top_level_definitions": functions[:30],
        "nearby_code": nearby[:20],
    }


@router.post("/feedback")
async def completion_feedback(payload: dict[str, Any]) -> dict[str, Any]:
    """补全反馈 — 用户接受或拒绝某条补全

    Body:
        completion_text: str    — 补全文本
        accepted: bool          — 是否接受
    """
    completion_text = payload.get("completion_text", "")
    accepted = payload.get("accepted", False)

    if accepted and completion_text:
        engine = _engine()
        engine.record_accept(completion_text)
        return {"message": "Feedback recorded: accepted", "text": completion_text}

    return {"message": "Feedback recorded: rejected"}


# ── 缓存管理 ─────────────────────────────────────────────────


@router.get("/cache-stats")
async def cache_stats() -> dict[str, Any]:
    """获取补全缓存统计"""
    engine = _engine()
    return engine.cache_stats


@router.delete("/cache")
async def clear_cache(
    file_path: str | None = Query(None, description="指定文件路径（空=全部清除）"),
) -> dict[str, Any]:
    """清空补全缓存"""
    engine = _engine()
    if file_path:
        engine.invalidate_cache(file_path)
        return {"message": f"Cache invalidated for: {file_path}"}
    else:
        engine._cache.clear()
        return {"message": "All cache cleared"}
