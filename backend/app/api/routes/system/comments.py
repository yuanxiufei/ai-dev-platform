"""
Comments API — 代码评审评论系统

参考: VSCode workbench/contrib/comments
端点:
  GET    /comments/list           — 获取文件的评论列表
  GET    /comments/count          — 获取未解决评论计数
  POST   /comments                — 添加评论
  POST   /comments/{id}/reply     — 回复评论
  PATCH  /comments/{id}           — 编辑评论
  POST   /comments/{id}/resolve   — 解决/取消解决
  POST   /comments/{id}/suggestion/accept — 接受建议
  DELETE /comments/{id}           — 删除评论
  DELETE /comments                — 清除文件所有评论 / 全部清除

持久化: SQLite 数据库, 按工作区隔离
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/comments", tags=["Comments"])

_ROOT = os.path.normpath(os.environ.get("PROJECT_ROOT", os.getcwd()))
_DB_DIR = os.path.join(_ROOT, ".data", "comments")
_DB_PATH = os.path.join(_DB_DIR, "comments.db")

# 确保目录存在
os.makedirs(_DB_DIR, exist_ok=True)


def _get_db() -> sqlite3.Connection:
    """获取数据库连接"""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    """初始化数据库表"""
    with _get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                workspace_id TEXT NOT NULL DEFAULT 'default',
                file_path TEXT NOT NULL,
                line INTEGER NOT NULL,
                end_line INTEGER,
                body TEXT NOT NULL,
                author_name TEXT NOT NULL DEFAULT 'User',
                author_avatar TEXT,
                created_at REAL NOT NULL,
                resolved INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'active',
                context_snippet TEXT DEFAULT '',
                label TEXT DEFAULT NULL,
                suggestion TEXT DEFAULT NULL,
                parent_id TEXT DEFAULT NULL,
                FOREIGN KEY (parent_id) REFERENCES comments(id) ON DELETE CASCADE
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_comments_file
            ON comments(workspace_id, file_path)
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS idx_comments_parent
            ON comments(parent_id)
        """)
        db.commit()


_init_db()


# ── 请求模型 ──

class AddCommentRequest(BaseModel):
    file_path: str
    line: int = Field(..., ge=1)
    body: str = Field(..., min_length=1, max_length=50000)
    workspace_id: str = "default"
    author_name: str = "User"
    author_avatar: str | None = None
    label: str | None = None  # review|suggestion|question|issue
    suggestion: str | None = None
    end_line: int | None = None
    context_snippet: str = ""


class ReplyRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=50000)
    author_name: str = "User"
    author_avatar: str | None = None


class EditCommentRequest(BaseModel):
    body: str = Field(..., min_length=1, max_length=50000)
    state: str | None = None


# ── 响应模型 ──

class CommentAuthor(BaseModel):
    name: str
    avatar: str | None = None


class CommentOut(BaseModel):
    id: str
    file_path: str
    line: int
    end_line: int | None = None
    body: str
    author: CommentAuthor
    created_at: float
    resolved: bool
    state: str
    context_snippet: str = ""
    label: str | None = None
    suggestion: str | None = None
    replies: list["CommentOut"] = []


class UnresolvedCounts(BaseModel):
    total: int
    by_file: dict[str, int]


# ── 辅助函数 ──

def _row_to_comment(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "file_path": row["file_path"],
        "line": row["line"],
        "end_line": row["end_line"],
        "body": row["body"],
        "author": {"name": row["author_name"], "avatar": row["author_avatar"]},
        "created_at": row["created_at"],
        "resolved": bool(row["resolved"]),
        "state": row["state"],
        "context_snippet": row["context_snippet"] or "",
        "label": row["label"],
        "suggestion": row["suggestion"],
        "replies": [],
    }


def _build_tree(rows: list[sqlite3.Row]) -> list[dict]:
    """从扁平行构建评论树"""
    comments: dict[str, dict] = {}
    roots: list[dict] = []
    for row in rows:
        c = _row_to_comment(row)
        comments[c["id"]] = c
        if row["parent_id"]:
            if row["parent_id"] in comments:
                comments[row["parent_id"]]["replies"].append(c)
        else:
            roots.append(c)
    return roots


# ── 端点 ──


@router.get("/list", response_model=list[CommentOut])
async def list_comments(
    workspace_id: str = Query("default"),
    file_path: str | None = Query(None),
    include_resolved: bool = Query(False),
) -> list[dict]:
    """获取评论列表 (可选按文件过滤)"""
    with _get_db() as db:
        if file_path:
            rows = db.execute(
                """SELECT * FROM comments
                   WHERE workspace_id = ? AND file_path = ? AND parent_id IS NULL
                   ORDER BY line ASC, created_at ASC""",
                (workspace_id, file_path),
            ).fetchall()
            # 获取所有回复
            all_rows = list(rows)
            reply_rows = db.execute(
                """SELECT * FROM comments
                   WHERE workspace_id = ? AND file_path = ? AND parent_id IS NOT NULL
                   ORDER BY created_at ASC""",
                (workspace_id, file_path),
            ).fetchall()
            all_rows.extend(reply_rows)
        else:
            rows = db.execute(
                """SELECT * FROM comments
                   WHERE workspace_id = ?
                   ORDER BY file_path ASC, line ASC, created_at ASC""",
                (workspace_id,),
            ).fetchall()
            all_rows = list(rows)

        result = _build_tree(all_rows)

        if not include_resolved:
            result = [c for c in result if c["state"] != "resolved"]

        return result


@router.get("/count", response_model=UnresolvedCounts)
async def comments_count(workspace_id: str = Query("default")) -> UnresolvedCounts:
    """获取未解决评论计数"""
    with _get_db() as db:
        rows = db.execute(
            """SELECT file_path, COUNT(*) as cnt
               FROM comments
               WHERE workspace_id = ? AND state != 'resolved' AND parent_id IS NULL
               GROUP BY file_path""",
            (workspace_id,),
        ).fetchall()
        by_file = {row["file_path"]: row["cnt"] for row in rows}
        total = sum(by_file.values())
        return UnresolvedCounts(total=total, by_file=by_file)


@router.post("", response_model=CommentOut)
async def add_comment(req: AddCommentRequest) -> dict:
    """添加新评论"""
    cid = f"comment-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
    now = time.time()

    with _get_db() as db:
        db.execute(
            """INSERT INTO comments (id, workspace_id, file_path, line, end_line, body,
               author_name, author_avatar, created_at, resolved, state, context_snippet, label, suggestion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?, ?, ?)""",
            (cid, req.workspace_id, req.file_path, req.line, req.end_line,
             req.body, req.author_name, req.author_avatar, now,
             req.context_snippet, req.label, req.suggestion),
        )
        db.commit()

    return {
        "id": cid,
        "file_path": req.file_path,
        "line": req.line,
        "end_line": req.end_line,
        "body": req.body,
        "author": {"name": req.author_name, "avatar": req.author_avatar},
        "created_at": now,
        "resolved": False,
        "state": "active",
        "context_snippet": req.context_snippet,
        "label": req.label,
        "suggestion": req.suggestion,
        "replies": [],
    }


@router.post("/{comment_id}/reply", response_model=CommentOut)
async def add_reply(comment_id: str, req: ReplyRequest) -> dict:
    """回复评论"""
    with _get_db() as db:
        parent = db.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        if not parent:
            raise HTTPException(404, "Comment not found")
        if parent["parent_id"]:
            raise HTTPException(400, "Cannot reply to a reply")

        rid = f"reply-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"
        now = time.time()
        db.execute(
            """INSERT INTO comments (id, workspace_id, file_path, line, end_line, body,
               author_name, author_avatar, created_at, resolved, state, parent_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'active', ?)""",
            (rid, parent["workspace_id"], parent["file_path"], parent["line"],
             parent["end_line"], req.body, req.author_name, req.author_avatar,
             now, comment_id),
        )
        db.commit()

    return {
        "id": rid,
        "file_path": parent["file_path"],
        "line": parent["line"],
        "end_line": parent["end_line"],
        "body": req.body,
        "author": {"name": req.author_name, "avatar": req.author_avatar},
        "created_at": now,
        "resolved": False,
        "state": "active",
        "context_snippet": "",
        "label": None,
        "suggestion": None,
        "replies": [],
    }


@router.patch("/{comment_id}")
async def edit_comment(comment_id: str, req: EditCommentRequest) -> dict:
    """编辑评论"""
    with _get_db() as db:
        row = db.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Comment not found")

        db.execute(
            "UPDATE comments SET body = ? WHERE id = ?",
            (req.body, comment_id),
        )
        if req.state and req.state in ("active", "resolved", "outdated"):
            db.execute(
                "UPDATE comments SET state = ?, resolved = ? WHERE id = ?",
                (req.state, 1 if req.state == "resolved" else 0, comment_id),
            )
        db.commit()

    return {"ok": True, "id": comment_id}


@router.post("/{comment_id}/resolve")
async def toggle_resolve(comment_id: str) -> dict:
    """切换评论解决状态"""
    with _get_db() as db:
        row = db.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Comment not found")

        is_resolved = bool(row["resolved"])
        new_resolved = not is_resolved
        new_state = "resolved" if new_resolved else "active"

        db.execute(
            "UPDATE comments SET resolved = ?, state = ? WHERE id = ?",
            (int(new_resolved), new_state, comment_id),
        )

        # 如果是主评论, 同时更新所有回复
        if not row["parent_id"] and new_resolved:
            db.execute(
                """UPDATE comments
                   SET resolved = 1, state = 'resolved'
                   WHERE parent_id = ?""",
                (comment_id,),
            )
        elif not row["parent_id"] and not new_resolved:
            db.execute(
                """UPDATE comments
                   SET resolved = 0, state = 'active'
                   WHERE parent_id = ?""",
                (comment_id,),
            )

        db.commit()

    return {"ok": True, "resolved": new_resolved, "state": new_state}


@router.post("/{comment_id}/suggestion/accept")
async def accept_suggestion(comment_id: str) -> dict:
    """接受评论中的代码建议"""
    with _get_db() as db:
        row = db.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Comment not found")
        suggestion = row["suggestion"]
        if not suggestion:
            raise HTTPException(400, "Comment has no suggestion")

        # 标记为已解决
        db.execute(
            "UPDATE comments SET resolved = 1, state = 'resolved' WHERE id = ?",
            (comment_id,),
        )
        db.commit()

    return {"ok": True, "suggestion": suggestion, "file_path": row["file_path"], "line": row["line"]}


@router.delete("/{comment_id}")
async def delete_comment(comment_id: str) -> dict:
    """删除评论 (级联删除回复)"""
    with _get_db() as db:
        row = db.execute("SELECT * FROM comments WHERE id = ?", (comment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Comment not found")

        db.execute("DELETE FROM comments WHERE id = ? OR parent_id = ?", (comment_id, comment_id))
        db.commit()

    return {"ok": True}


@router.delete("")
async def clear_comments(
    workspace_id: str = Query("default"),
    file_path: str | None = Query(None),
) -> dict:
    """清除评论: 指定文件 或 全部工作区"""
    with _get_db() as db:
        if file_path:
            db.execute(
                "DELETE FROM comments WHERE workspace_id = ? AND file_path = ?",
                (workspace_id, file_path),
            )
            return {"ok": True, "cleared_file": file_path}
        else:
            db.execute(
                "DELETE FROM comments WHERE workspace_id = ?",
                (workspace_id,),
            )
            return {"ok": True, "cleared_all": True}
