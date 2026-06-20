"""
Lakeview API — Agent 步骤摘要路由

提供:
- GET  /agent/lakeview/{session_id}           — 获取摘要
- GET  /agent/lakeview/{session_id}/compact   — 获取紧凑摘要
- GET  /agent/lakeview/{session_id}/markdown  — 获取 Markdown 摘要
- DELETE /agent/lakeview/{session_id}          — 清除摘要
"""

from fastapi import APIRouter, HTTPException

from app.core.agent.lakeview import LakeviewSummarizer, get_lakeview_summarizer

router = APIRouter(prefix="/agent/lakeview", tags=["Agent Lakeview"])


def _get_summarizer() -> LakeviewSummarizer:
    return get_lakeview_summarizer()


@router.get("/{session_id}")
async def get_lakeview(session_id: str):
    """获取会话的完整运行摘要"""
    s = _get_summarizer()
    if s.session_id != session_id:
        raise HTTPException(status_code=404, detail=f"No summary found for session: {session_id}")

    run = s.get_run_summary()
    return {
        "data": {
            "agent_id": run.agent_id,
            "session_id": run.session_id,
            "total_turns": run.total_turns,
            "total_tool_calls": run.total_tool_calls,
            "total_tokens": run.total_tokens,
            "total_latency_ms": run.total_latency_ms,
            "error": run.error,
            "final_answer_preview": run.final_answer_preview,
            "tags_summary": run.tags_summary,
            "steps": [
                {
                    "turn": st.turn,
                    "tag": st.tag,
                    "summary": st.summary,
                    "tool_name": st.tool_name,
                    "tool_args_preview": st.tool_args_preview,
                    "success": st.success,
                    "latency_ms": st.latency_ms,
                    "result_preview": st.result_preview,
                }
                for st in run.steps
            ],
        }
    }


@router.get("/{session_id}/compact")
async def get_lakeview_compact(session_id: str, max_tokens: int = 2000):
    """获取紧凑摘要（适合注入 Agent 上下文）"""
    s = _get_summarizer()
    if s.session_id != session_id:
        raise HTTPException(status_code=404, detail=f"No summary found for session: {session_id}")

    compact = s.get_compact_summary(max_tokens)
    return {"data": {"compact_summary": compact}}


@router.get("/{session_id}/markdown")
async def get_lakeview_markdown(session_id: str):
    """获取 Markdown 格式摘要"""
    s = _get_summarizer()
    if s.session_id != session_id:
        raise HTTPException(status_code=404, detail=f"No summary found for session: {session_id}")

    md = s.to_markdown()
    return {"data": {"markdown": md}}


@router.delete("/{session_id}")
async def clear_lakeview(session_id: str):
    """清除会话摘要"""
    s = _get_summarizer()
    s.clear()
    return {"message": f"Lakeview cleared for session: {session_id}"}
