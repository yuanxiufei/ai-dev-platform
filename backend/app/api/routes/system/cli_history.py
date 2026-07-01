"""CLI 执行历史 API (P2.9)

端点:
- GET /system/cli-history  — 查询 CLI 执行历史
"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Query, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["cli-history"])

LOG_FILE = Path("data/cli_history.jsonl")


@router.get("/cli-history")
async def cli_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """查询 CLI 执行历史 (最近 N 条)"""
    if not LOG_FILE.exists():
        return {"entries": [], "total": 0}

    try:
        lines = LOG_FILE.read_text(encoding="utf-8").strip().split("\n")
        entries = []
        for line in lines:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

        total = len(entries)
        # 倒序 (最新在前)
        entries.reverse()
        page = entries[offset : offset + limit]

        # 统计摘要
        success_count = sum(1 for e in page if e.get("exit_code") == 0)
        error_count = len(page) - success_count

        return {
            "entries": page,
            "total": total,
            "page_size": len(page),
            "success_count": success_count,
            "error_count": error_count,
        }
    except Exception as e:
        logger.exception("Failed to read CLI history")
        raise HTTPException(status_code=500, detail="Internal error reading CLI history")
