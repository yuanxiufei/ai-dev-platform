"""
Git/SCM API — 对标 VSCode Git Extension API

端点:
  GET    /git/status              — 仓库状态 (branch, ahead/behind, changes)
  POST   /git/stage               — 暂存文件
  POST   /git/unstage             — 取消暂存
  POST   /git/stage-all           — 暂存全部
  POST   /git/unstage-all         — 取消暂存全部
  POST   /git/commit              — 提交
  POST   /git/push                — 推送到远程
  POST   /git/pull                — 从远程拉取
  POST   /git/discard             — 丢弃文件更改
  POST   /git/diff                — 获取差异
  GET    /git/branches            — 列出分支
  POST   /git/checkout            — 切换/创建分支
  GET    /git/log                 — 提交历史
  POST   /git/stash               — 暂存工作区
  POST   /git/stash-pop           — 恢复 stash
  POST   /git/blame               — 行归因
  GET    /git/remotes             — 远程仓库列表

安全: 依赖 AutoCLI 执行 git 命令, 限制在 PROJECT_ROOT 范围内
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system/git", tags=["Git"])

# 安全根路径
_ROOT = os.path.normpath(os.environ.get("PROJECT_ROOT", os.getcwd()))


def _resolve_repo(repo_path: str | None = None) -> str:
    """解析并验证仓库路径"""
    repo = os.path.normpath(os.path.join(_ROOT, repo_path or "."))
    if not repo.startswith(os.path.normpath(_ROOT)):
        raise HTTPException(403, "Path traversal not allowed")
    git_dir = os.path.join(repo, ".git")
    if not os.path.isdir(git_dir):
        raise HTTPException(400, f"Not a git repository: {repo}")
    return repo


async def _run_git(repo_path: str, *args: str, timeout: float = 30.0) -> str:
    """安全执行 git 命令, 返回 stdout"""
    import asyncio

    cmd = ["git", "-C", repo_path] + list(args)
    logger.debug("git: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"},
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode != 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(err_msg or f"git exited with code {proc.returncode}")

        return stdout.decode("utf-8", errors="replace").strip()
    except asyncio.TimeoutError:
        raise HTTPException(504, f"Git command timed out after {timeout}s")
    except RuntimeError as e:
        raise HTTPException(400, str(e))


# ── 请求模型 ──

class StageRequest(BaseModel):
    repo_path: str = "."
    file_path: str


class CommitRequest(BaseModel):
    repo_path: str = "."
    message: str = Field(..., min_length=1, max_length=4096)


class PushPullRequest(BaseModel):
    repo_path: str = "."
    remote: str = "origin"
    branch: str | None = None


class CheckoutRequest(BaseModel):
    repo_path: str = "."
    branch: str = Field(..., min_length=1)
    create_new: bool = False


class DiffRequest(BaseModel):
    repo_path: str = "."
    file: str | None = None
    staged: bool = False


class StashRequest(BaseModel):
    repo_path: str = "."
    message: str | None = None
    pop: bool = False


class BlameRequest(BaseModel):
    repo_path: str = "."
    file_path: str


# ── 响应模型 ──

class GitFileChange(BaseModel):
    path: str
    status: str  # staged|modified|added|deleted|untracked|renamed
    old_path: str | None = None


class GitStatusResponse(BaseModel):
    branch: str
    ahead: int
    behind: int
    changes: list[GitFileChange]


class DiffLine(BaseModel):
    type: str  # added|removed|context
    content: str
    line_number: int | None = None


class DiffHunk(BaseModel):
    header: str
    lines: list[DiffLine]


class DiffEntry(BaseModel):
    path: str
    old_path: str | None = None
    status: str
    additions: int
    deletions: int
    hunks: list[DiffHunk]


class BranchEntry(BaseModel):
    name: str
    is_current: bool
    is_remote: bool


class CommitEntry(BaseModel):
    hash: str
    short_hash: str
    message: str
    author: str
    email: str
    date: str


class BlameLine(BaseModel):
    line_number: int
    commit_hash: str
    author: str
    date: str
    summary: str
    time_ago: str


class RemoteEntry(BaseModel):
    name: str
    url: str
    fetch: bool
    push: bool


# ── 端点 ──


@router.get("/status", response_model=GitStatusResponse)
async def git_status(repo_path: str = Query(".")) -> GitStatusResponse:
    """
    获取仓库状态: 当前分支, ahead/behind 计数, 文件变更列表
    """
    repo = _resolve_repo(repo_path)

    # 获取当前分支
    branch_raw = await _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    # 获取 ahead/behind
    ahead = 0
    behind = 0
    try:
        # 获取远程跟踪分支
        upstream = await _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD@{upstream}")
        ahead_raw = await _run_git(repo, "rev-list", "--count", f"HEAD..{upstream}")
        behind_raw = await _run_git(repo, "rev-list", "--count", f"{upstream}..HEAD")
        ahead = int(behind_raw) if behind_raw else 0
        behind = int(ahead_raw) if ahead_raw else 0
    except Exception:
        pass

    # 获取变更 - porcelain v1 format
    status_raw = await _run_git(repo, "status", "--porcelain", "-u")
    changes = _parse_status(status_raw)

    return GitStatusResponse(
        branch=branch_raw,
        ahead=ahead,
        behind=behind,
        changes=changes,
    )


def _parse_status(raw: str) -> list[GitFileChange]:
    """解析 git status --porcelain 输出"""
    changes: list[GitFileChange] = []
    if not raw:
        return changes

    for line in raw.split("\n"):
        if len(line) < 3:
            continue
        xy = line[:2]
        path = line[3:].strip()

        # 检测重命名
        if " -> " in path and xy.startswith("R"):
            parts = path.split(" -> ")
            changes.append(GitFileChange(path=parts[1], status="renamed", old_path=parts[0]))
            continue

        # 索引 (staged)
        x = xy[0]
        if x in ("M", "A", "D", "R"):
            changes.append(GitFileChange(
                path=path,
                status="staged" if x == "M" else ("added" if x == "A" else ("deleted" if x == "D" else "renamed")),
            ))

        # 工作树 (unstaged)
        y = xy[1]
        if y == "M":
            # 避免与 staged 重复
            if not any(c.path == path and c.status == "staged" for c in changes):
                changes.append(GitFileChange(path=path, status="modified"))
        elif y == "D":
            if not any(c.path == path and c.status == "added" for c in changes):
                changes.append(GitFileChange(path=path, status="deleted"))

        # 未跟踪
        if xy == "??":
            changes.append(GitFileChange(path=path, status="untracked"))

    return changes


@router.post("/stage")
async def git_stage(req: StageRequest) -> dict:
    """暂存文件"""
    repo = _resolve_repo(req.repo_path)
    await _run_git(repo, "add", "--", req.file_path)
    return {"ok": True}


@router.post("/unstage")
async def git_unstage(req: StageRequest) -> dict:
    """取消暂存文件"""
    repo = _resolve_repo(req.repo_path)
    try:
        await _run_git(repo, "reset", "HEAD", "--", req.file_path)
    except HTTPException:
        # 如果文件未被追踪, 尝试 rm --cached
        await _run_git(repo, "rm", "--cached", "--", req.file_path)
    return {"ok": True}


@router.post("/stage-all")
async def git_stage_all(repo_path: str = Query(".")) -> dict:
    """暂存所有变更"""
    repo = _resolve_repo(repo_path)
    await _run_git(repo, "add", "-A")
    return {"ok": True}


@router.post("/unstage-all")
async def git_unstage_all(repo_path: str = Query(".")) -> dict:
    """取消暂存所有"""
    repo = _resolve_repo(repo_path)
    await _run_git(repo, "reset", "HEAD")
    return {"ok": True}


@router.post("/commit")
async def git_commit(req: CommitRequest) -> dict:
    """提交暂存的变更"""
    repo = _resolve_repo(req.repo_path)
    await _run_git(repo, "commit", "-m", req.message)
    return {"ok": True}


@router.post("/push")
async def git_push(req: PushPullRequest) -> dict:
    """推送到远程"""
    repo = _resolve_repo(req.repo_path)
    args = ["push", req.remote]
    if req.branch:
        args.append(req.branch)
    await _run_git(repo, *args)
    return {"ok": True}


@router.post("/pull")
async def git_pull(req: PushPullRequest) -> dict:
    """从远程拉取"""
    repo = _resolve_repo(req.repo_path)
    args = ["pull", req.remote]
    if req.branch:
        args.append(req.branch)
    await _run_git(repo, *args, timeout=120.0)
    return {"ok": True}


@router.post("/discard")
async def git_discard(req: StageRequest) -> dict:
    """丢弃工作区更改"""
    repo = _resolve_repo(req.repo_path)
    try:
        await _run_git(repo, "checkout", "--", req.file_path)
    except HTTPException:
        # 尝试 clean 未跟踪文件
        await _run_git(repo, "clean", "-f", "--", req.file_path)
    return {"ok": True}


@router.post("/diff", response_model=list[DiffEntry])
async def git_diff(req: DiffRequest) -> list[DiffEntry]:
    """获取文件或仓库的差异"""
    repo = _resolve_repo(req.repo_path)
    args = ["diff", "--unified=3"]
    if req.staged:
        args.append("--staged")
    if req.file:
        args.extend(["--", req.file])

    raw = await _run_git(repo, *args)
    return _parse_diff(repo, raw, req.file)


def _parse_diff(repo: str, raw: str, file_filter: str | None = None) -> list[DiffEntry]:
    """解析 unified diff 输出"""
    entries: list[DiffEntry] = []
    if not raw:
        return entries

    current: DiffEntry | None = None
    current_hunk: DiffHunk | None = None

    for line in raw.split("\n"):
        # 文件头
        if line.startswith("diff --git "):
            if current:
                _finalize_hunk(current, current_hunk)
                entries.append(current)
            file_info = line[11:]
            parts = file_info.split(" ")
            # 格式: a/path b/path
            a_path = parts[0][2:] if len(parts) > 0 else ""
            b_path = parts[1][2:] if len(parts) > 1 else a_path
            current = DiffEntry(
                path=b_path,
                old_path=a_path if a_path != b_path else None,
                status="modified",
                additions=0,
                deletions=0,
                hunks=[],
            )
            current_hunk = None
            continue

        if not current:
            continue

        # 新增/删除行计数
        if line.startswith("--- ") and current:
            continue
        if line.startswith("+++ ") and current:
            continue

        # Hunk 头
        if line.startswith("@@"):
            _finalize_hunk(current, current_hunk)
            current_hunk = DiffHunk(header=line, lines=[])
            continue

        if current_hunk is None:
            continue

        if line.startswith("+"):
            current_hunk.lines.append(DiffLine(type="added", content=line[1:]))
            current.additions += 1
        elif line.startswith("-"):
            current_hunk.lines.append(DiffLine(type="removed", content=line[1:]))
            current.deletions += 1
        elif line.startswith(" "):
            current_hunk.lines.append(DiffLine(type="context", content=line[1:]))

    _finalize_hunk(current, current_hunk)
    if current:
        entries.append(current)
    return entries


def _finalize_hunk(entry: DiffEntry | None, hunk: DiffHunk | None) -> None:
    if entry and hunk and hunk.lines:
        entry.hunks.append(hunk)


@router.get("/branches", response_model=list[BranchEntry])
async def git_branches(repo_path: str = Query(".")) -> list[BranchEntry]:
    """列出分支"""
    repo = _resolve_repo(repo_path)

    # 当前分支
    current_raw = await _run_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    current = current_raw.strip()

    # 本地分支
    local_raw = await _run_git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    local_branches = [b for b in local_raw.split("\n") if b]

    # 远程分支
    remote_raw = await _run_git(repo, "for-each-ref", "--format=%(refname:short)", "refs/remotes/")
    remote_branches = [b for b in remote_raw.split("\n") if b]

    result: list[BranchEntry] = []
    seen: set[str] = set()

    for b in local_branches:
        result.append(BranchEntry(name=b, is_current=(b == current), is_remote=False))
        seen.add(b)

    for b in remote_branches:
        # 去除 origin/ 前缀比较
        short = b.split("/", 1)[1] if "/" in b else b
        if short not in seen:
            result.append(BranchEntry(name=b, is_current=False, is_remote=True))

    return result


@router.post("/checkout")
async def git_checkout(req: CheckoutRequest) -> dict:
    """切换或创建分支"""
    repo = _resolve_repo(req.repo_path)
    if req.create_new:
        await _run_git(repo, "checkout", "-b", req.branch)
    else:
        await _run_git(repo, "checkout", req.branch)
    return {"ok": True, "branch": req.branch}


@router.get("/log", response_model=list[CommitEntry])
async def git_log(
    repo_path: str = Query("."),
    limit: int = Query(20, ge=1, le=500),
    branch: str | None = Query(None),
    file: str | None = Query(None),
) -> list[CommitEntry]:
    """获取提交历史"""
    repo = _resolve_repo(repo_path)
    fmt = "--format=%H||%h||%s||%an||%ae||%aI"
    args = ["log", fmt, f"-n{limit}"]
    if branch:
        args.append(branch)
    if file:
        args.extend(["--", file])

    raw = await _run_git(repo, *args)
    entries: list[CommitEntry] = []
    for line in raw.split("\n"):
        if not line.strip():
            continue
        parts = line.split("||", 5)
        if len(parts) >= 6:
            entries.append(CommitEntry(
                hash=parts[0],
                short_hash=parts[1],
                message=parts[2],
                author=parts[3],
                email=parts[4],
                date=parts[5],
            ))
    return entries


@router.post("/stash")
async def git_stash(req: StashRequest) -> dict:
    """暂存工作区变更 (stash save 或 pop)"""
    repo = _resolve_repo(req.repo_path)
    if req.pop:
        await _run_git(repo, "stash", "pop")
        return {"ok": True, "action": "pop"}
    else:
        args = ["stash", "push"]
        if req.message:
            args.extend(["-m", req.message])
        await _run_git(repo, *args)
        return {"ok": True, "action": "push"}


@router.post("/blame", response_model=list[BlameLine])
async def git_blame(req: BlameRequest) -> list[BlameLine]:
    """获取文件的每行归因信息 (git blame --porcelain)"""
    from datetime import datetime, timezone

    repo = _resolve_repo(req.repo_path)
    # 检查文件是否存在
    file_abs = os.path.join(repo, req.file_path)
    if not os.path.isfile(file_abs):
        raise HTTPException(404, f"File not found: {req.file_path}")

    raw = await _run_git(repo, "blame", "--porcelain", "--", req.file_path, timeout=60.0)
    return _parse_blame(raw)


def _parse_blame(raw: str) -> list[BlameLine]:
    """解析 git blame --porcelain 输出"""
    now = datetime.now(tz=timezone.utc)
    lines: list[BlameLine] = []
    blocks = raw.split("\n")
    i = 0

    while i < len(blocks):
        line_text = blocks[i]
        # 头部行: <hash> <orig-line> <final-line> <num-lines>
        header_match = __import__("re").match(
            r"^([0-9a-f]{40})\s+\d+\s+(\d+)\s*(\d*)", line_text
        )
        if not header_match:
            i += 1
            continue

        commit_hash = header_match.group(1)[:7]
        line_num = int(header_match.group(2))
        author = "unknown"
        timestamp = ""
        summary = ""

        # 读取后续 porcelain 字段
        for j in range(i + 1, min(i + 30, len(blocks))):
            pl = blocks[j]
            if pl.startswith("author "):
                author = pl[7:]
            elif pl.startswith("author-time "):
                ts = int(pl[12:])
                timestamp = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            elif pl.startswith("summary "):
                summary = pl[8:]
            elif pl.startswith("filename ") or __import__("re").match(r"^[0-9a-f]{40}\s", pl):
                break

        time_ago_str = _time_ago(now, timestamp) if timestamp else ""

        lines.append(BlameLine(
            line_number=line_num,
            commit_hash=commit_hash,
            author=author,
            date=timestamp,
            summary=summary,
            time_ago=time_ago_str,
        ))

        # 跳到下一个头部行
        i += 1
        while i < len(blocks):
            if __import__("re").match(r"^[0-9a-f]{40}\s+\d+\s+\d+", blocks[i]):
                break
            i += 1

    return lines


def _time_ago(now: datetime, iso_str: str) -> str:
    """计算相对时间"""
    try:
        dt = datetime.fromisoformat(iso_str)
        delta = now - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return f"{seconds}s ago"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        if months < 12:
            return f"{months}mo ago"
        return f"{months // 12}y ago"
    except Exception:
        return ""


@router.get("/remotes", response_model=list[RemoteEntry])
async def git_remotes(repo_path: str = Query(".")) -> list[RemoteEntry]:
    """列出远程仓库"""
    repo = _resolve_repo(repo_path)
    raw = await _run_git(repo, "remote", "-v")
    remotes: dict[str, RemoteEntry] = {}
    for line in raw.split("\n"):
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            url = parts[1]
            is_push = "(push)" in line
            if name not in remotes:
                remotes[name] = RemoteEntry(name=name, url=url, fetch=False, push=False)
            if is_push:
                remotes[name].push = True
                remotes[name].url = url
            else:
                remotes[name].fetch = True
    return list(remotes.values())


@router.post("/clone")
async def git_clone(
    url: str = Query(..., max_length=2048),
    target: str = Query(..., max_length=512),
    branch: str | None = Query(None, max_length=256),
) -> dict:
    """克隆仓库"""
    import asyncio

    target_abs = os.path.normpath(os.path.join(_ROOT, target))
    if not target_abs.startswith(os.path.normpath(_ROOT)):
        raise HTTPException(403, "Target path outside project root")
    if os.path.exists(target_abs):
        raise HTTPException(409, f"Target path already exists: {target}")

    args = ["clone", url, target_abs]
    if branch:
        args.extend(["-b", branch])

    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300.0)

    if proc.returncode != 0:
        raise HTTPException(400, stderr.decode("utf-8", errors="replace").strip())

    return {"ok": True, "path": target}
