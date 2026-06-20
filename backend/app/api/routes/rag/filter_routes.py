"""
文本过滤链 API 路由

借鉴 obsidian-clipper 的模板过滤器调试端点:
- 测试单个/组合过滤器
- 列出所有可用过滤器
- 预览过滤效果
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.rag.filters import (
    BUILTIN_FILTERS,
    FilterChain,
    build_filter_chain,
    create_rag_ingest_chain,
    create_markdown_clean_chain,
    create_webpage_clean_chain,
)

router = APIRouter(prefix="/rag/filters", tags=["RAG Filters"])


class FilterApplyRequest(BaseModel):
    text: str = Field(..., description="输入文本")
    filter_names: list[str] = Field(
        default_factory=list,
        description="过滤器名称列表（按顺序应用）",
    )
    preset: str = Field(
        default="",
        description='预设链: rag_ingest | markdown_clean | webpage_clean',
    )


class FilterApplyResponse(BaseModel):
    original: str = Field(..., description="原始文本")
    filtered: str = Field(..., description="过滤后文本")
    filters_applied: list[str] = Field(default_factory=list)
    original_length: int = 0
    filtered_length: int = 0
    compression_ratio: float = 0.0


class FilterInfo(BaseModel):
    name: str
    description: str
    class_name: str


# ── 端点 ──────────────────────────────────────────────────

@router.get("/list", response_model=list[FilterInfo])
async def list_filters():
    """列出所有可用过滤器"""
    descriptions = {
        "remove_html":       "去除 HTML 标签，保留文本结构",
        "strip_md":          "去除 Markdown 格式标记",
        "remove_urls":       "移除 URL 链接",
        "remove_boilerplate":"移除网页模板噪音（Cookie/导航/版权等）",
        "extract_code":      "提取代码块并追加到文本末尾",
        "normalize_ws":      "规范化空白字符",
        "truncate":          "截断到指定长度",
        "deduplicate_lines": "行级去重",
        "remove_pre":        "移除行首前缀",
        "safe_filename":     "生成安全文件名",
    }
    return [
        FilterInfo(
            name=name,
            description=descriptions.get(name, "自定义过滤器"),
            class_name=cls.__name__,
        )
        for name, cls in BUILTIN_FILTERS.items()
    ]


@router.post("/apply", response_model=FilterApplyResponse)
async def apply_filters(req: FilterApplyRequest):
    """应用过滤器链并返回预览结果"""
    if not req.text:
        raise HTTPException(status_code=400, detail="text is required")

    chain: FilterChain

    # 预设 > 自定义
    if req.preset == "rag_ingest":
        chain = create_rag_ingest_chain()
    elif req.preset == "markdown_clean":
        chain = create_markdown_clean_chain()
    elif req.preset == "webpage_clean":
        chain = create_webpage_clean_chain()
    elif req.filter_names:
        chain = build_filter_chain(req.filter_names)
    else:
        # 默认 RAG 摄入链
        chain = create_rag_ingest_chain()

    filtered = chain.apply(req.text)
    applied = [f.__class__.__name__ for f in chain.filters]

    return FilterApplyResponse(
        original=req.text,
        filtered=filtered,
        filters_applied=applied,
        original_length=len(req.text),
        filtered_length=len(filtered),
        compression_ratio=round(
            1 - (len(filtered) / len(req.text)) if req.text else 0, 4,
        ),
    )


@router.post("/preview")
async def preview_filter_chain(req: FilterApplyRequest):
    """
    预览过滤器链效果 (返回对比视图)

    使用 HTML 格式展示原始 vs 过滤后的对比
    """
    if not req.text:
        raise HTTPException(status_code=400, detail="text is required")

    chain = (
        build_filter_chain(req.filter_names)
        if req.filter_names
        else create_rag_ingest_chain()
    )
    filtered = chain.apply(req.text)

    return {
        "preset": req.preset or "custom",
        "filters": [f.__class__.__name__ for f in chain.filters],
        "original_preview": req.text[:500] + ("..." if len(req.text) > 500 else ""),
        "filtered_preview": filtered[:500] + ("..." if len(filtered) > 500 else ""),
        "original_length": len(req.text),
        "filtered_length": len(filtered),
        "reduction": f"{round((1 - len(filtered) / max(len(req.text), 1)) * 100, 1)}%",
    }
